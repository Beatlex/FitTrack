"""Centralized catalog ACL operations.

Authorization is always evaluated for the authenticated user ID supplied by
the API layer. Contextual recipe-ingredient grants never grant picker access.
"""
from sqlalchemy import select

from .household_models import HouseholdMember
from .nutrition_models import (
    Food,
    FoodAccess,
    FoodHiddenByUser,
    MealTemplate,
    MealTemplateIngredient,
    RecipeAccess,
    RecipeHiddenByUser,
    RecipeIngredientAccess,
)


def visible_foods_statement(user_id: int):
    has_grant = select(FoodAccess.id).where(
        FoodAccess.food_id == Food.id,
        FoodAccess.user_id == user_id,
    ).exists()
    is_hidden = select(FoodHiddenByUser.id).where(
        FoodHiddenByUser.food_id == Food.id,
        FoodHiddenByUser.user_id == user_id,
    ).exists()
    return select(Food).where(
        (Food.is_system.is_(True) | has_grant),
        ~is_hidden,
    )


def visible_recipes_statement(user_id: int):
    has_grant = select(RecipeAccess.id).where(
        RecipeAccess.recipe_id == MealTemplate.id,
        RecipeAccess.user_id == user_id,
    ).exists()
    is_hidden = select(RecipeHiddenByUser.id).where(
        RecipeHiddenByUser.recipe_id == MealTemplate.id,
        RecipeHiddenByUser.user_id == user_id,
    ).exists()
    return select(MealTemplate).where(has_grant, ~is_hidden)


def _grant_food(db, food_id: int, user_ids: set[int]) -> None:
    existing = set(db.scalars(select(FoodAccess.user_id).where(
        FoodAccess.food_id == food_id,
        FoodAccess.user_id.in_(user_ids),
    ))) if user_ids else set()
    db.add_all(
        FoodAccess(food_id=food_id, user_id=user_id)
        for user_id in user_ids - existing
    )


def _grant_recipe(db, recipe_id: int, user_ids: set[int]) -> None:
    if not user_ids:
        return
    existing = set(db.scalars(select(RecipeAccess.user_id).where(
        RecipeAccess.recipe_id == recipe_id,
        RecipeAccess.user_id.in_(user_ids),
    )))
    db.add_all(
        RecipeAccess(recipe_id=recipe_id, user_id=user_id)
        for user_id in user_ids - existing
    )
    food_ids = set(db.scalars(select(MealTemplateIngredient.food_id).where(
        MealTemplateIngredient.template_id == recipe_id,
    )))
    for food_id in food_ids:
        contextual_existing = set(db.scalars(select(RecipeIngredientAccess.user_id).where(
            RecipeIngredientAccess.recipe_id == recipe_id,
            RecipeIngredientAccess.food_id == food_id,
            RecipeIngredientAccess.user_id.in_(user_ids),
        )))
        db.add_all(
            RecipeIngredientAccess(
                recipe_id=recipe_id, food_id=food_id, user_id=user_id
            )
            for user_id in user_ids - contextual_existing
        )


def grant_food_to_household(db, food_id: int, household_id: int) -> None:
    user_ids = set(db.scalars(select(HouseholdMember.user_id).where(
        HouseholdMember.household_id == household_id,
    )))
    _grant_food(db, food_id, user_ids)


def grant_recipe_to_household(db, recipe_id: int, household_id: int) -> None:
    user_ids = set(db.scalars(select(HouseholdMember.user_id).where(
        HouseholdMember.household_id == household_id,
    )))
    _grant_recipe(db, recipe_id, user_ids)


def grant_owned_catalog_to_household(db, user_id: int, household_id: int) -> None:
    members = set(db.scalars(select(HouseholdMember.user_id).where(
        HouseholdMember.household_id == household_id,
    )))
    food_ids = set(db.scalars(select(Food.id).where(
        Food.owner_id == user_id,
        Food.household_id == household_id,
        Food.is_system.is_(False),
    )))
    recipe_ids = set(db.scalars(select(MealTemplate.id).where(
        MealTemplate.owner_id == user_id,
        MealTemplate.household_id == household_id,
    )))
    for food_id in food_ids:
        _grant_food(db, food_id, members)
    for recipe_id in recipe_ids:
        _grant_recipe(db, recipe_id, members)


def grant_new_food(db, food: Food, user_id: int, household_id: int | None) -> None:
    if household_id is None:
        _grant_food(db, food.id, {user_id})
    else:
        grant_food_to_household(db, food.id, household_id)


def grant_new_recipe(db, recipe: MealTemplate, user_id: int, household_id: int | None) -> None:
    if household_id is None:
        _grant_recipe(db, recipe.id, {user_id})
    else:
        grant_recipe_to_household(db, recipe.id, household_id)



def grant_household_catalog_to_member(db, user_id: int, household_id: int) -> None:
    """Grant a joining member all currently household-scoped catalog records."""
    food_ids = set(db.scalars(select(Food.id).where(
        Food.household_id == household_id,
        Food.is_system.is_(False),
    )))
    recipe_ids = set(db.scalars(select(MealTemplate.id).where(
        MealTemplate.household_id == household_id,
    )))
    for food_id in food_ids:
        _grant_food(db, food_id, {user_id})
    for recipe_id in recipe_ids:
        _grant_recipe(db, recipe_id, {user_id})


def revoke_household_access_for_member(db, user_id: int, household_id: int) -> None:
    """Revoke household shares while retaining creator ownership and recipe dependencies."""
    household_food_ids = select(Food.id).where(
        Food.household_id == household_id,
        Food.owner_id != user_id,
    )
    household_recipe_ids = select(MealTemplate.id).where(
        MealTemplate.household_id == household_id,
        MealTemplate.owner_id != user_id,
    )
    db.query(FoodAccess).filter(
        FoodAccess.user_id == user_id,
        FoodAccess.food_id.in_(household_food_ids),
    ).delete(synchronize_session=False)
    db.query(RecipeAccess).filter(
        RecipeAccess.user_id == user_id,
        RecipeAccess.recipe_id.in_(household_recipe_ids),
    ).delete(synchronize_session=False)

    # A departing creator's catalog becomes private; remove other members'
    # general grants, but keep contextual dependency grants for existing recipes.
    owned_food_ids = select(Food.id).where(
        Food.owner_id == user_id,
        Food.household_id == household_id,
    )
    owned_recipe_ids = select(MealTemplate.id).where(
        MealTemplate.owner_id == user_id,
        MealTemplate.household_id == household_id,
    )
    db.query(FoodAccess).filter(
        FoodAccess.food_id.in_(owned_food_ids),
        FoodAccess.user_id != user_id,
    ).delete(synchronize_session=False)
    db.query(RecipeAccess).filter(
        RecipeAccess.recipe_id.in_(owned_recipe_ids),
        RecipeAccess.user_id != user_id,
    ).delete(synchronize_session=False)


def sync_recipe_ingredient_grants(db, recipe_id: int) -> None:
    """Rebuild contextual grants after recipe ingredients are replaced."""
    db.query(RecipeIngredientAccess).filter(
        RecipeIngredientAccess.recipe_id == recipe_id,
    ).delete(synchronize_session=False)
    users = set(db.scalars(select(RecipeAccess.user_id).where(
        RecipeAccess.recipe_id == recipe_id,
    )))
    _grant_recipe(db, recipe_id, users)
