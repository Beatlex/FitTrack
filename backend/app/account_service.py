"""Transactional account deletion while preserving shared catalog dependencies."""
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from .household_models import Household, HouseholdInvitation, HouseholdMember
from .models import FoodEntry, Measurement, User
from .nutrition_models import (
    Food,
    FoodAccess,
    FoodHiddenByUser,
    MealEntry,
    MealIngredient,
    MealTemplate,
    MealTemplateFavorite,
    MealTemplateIngredient,
    NutritionGoal,
    RecipeAccess,
    RecipeHiddenByUser,
    RecipeIngredientAccess,
)


def _food_has_retained_references(db: Session, food_id: int) -> bool:
    reference_checks = (
        select(MealTemplateIngredient.id).where(
            MealTemplateIngredient.food_id == food_id
        ),
        select(MealEntry.id).where(MealEntry.food_id == food_id),
        select(MealIngredient.id).where(MealIngredient.food_id == food_id),
    )
    return any(db.scalar(statement.limit(1)) is not None for statement in reference_checks)


def delete_account(db: Session, user: User) -> None:
    """Delete personal data and credentials without deleting others' shared data.

    The caller must verify the password and explicit confirmation before
    invoking this operation. All changes are committed by the caller.
    """
    membership = db.scalar(select(HouseholdMember).where(
        HouseholdMember.user_id == user.id
    ))
    household = db.get(Household, membership.household_id) if membership else db.scalar(
        select(Household).where(Household.owner_id == user.id)
    )

    remaining_members = []
    if household is not None:
        remaining_members = db.scalars(
            select(HouseholdMember)
            .where(
                HouseholdMember.household_id == household.id,
                HouseholdMember.user_id != user.id,
            )
            .order_by(HouseholdMember.joined_at, HouseholdMember.id)
        ).all()

    # Transfer household ownership before removing the account. The owner is
    # never silently replaced with a user outside the household.
    delete_household = False
    if household is not None and household.owner_id == user.id:
        if remaining_members:
            new_owner = remaining_members[0]
            household.owner_id = new_owner.user_id
            new_owner.role = "owner"
        else:
            delete_household = True

    # Personal logs are removed before deciding whether a food still has
    # retained references. Nutrient snapshots belonging to other users remain.
    user_meal_ids = select(MealEntry.id).where(MealEntry.user_id == user.id)
    db.execute(delete(MealIngredient).where(
        MealIngredient.meal_entry_id.in_(user_meal_ids)
    ))
    db.execute(delete(MealEntry).where(MealEntry.user_id == user.id))
    db.execute(delete(FoodEntry).where(FoodEntry.user_id == user.id))
    db.execute(delete(Measurement).where(Measurement.user_id == user.id))
    db.execute(delete(NutritionGoal).where(NutritionGoal.user_id == user.id))
    db.execute(delete(MealTemplateFavorite).where(
        MealTemplateFavorite.user_id == user.id
    ))

    # Shared recipes survive and receive a remaining household owner (or,
    # outside a household, a user who still has an explicit recipe grant).
    owned_recipes = db.scalars(select(MealTemplate).where(
        MealTemplate.owner_id == user.id
    )).all()
    for recipe in owned_recipes:
        other_grant_user = db.scalar(
            select(RecipeAccess.user_id)
            .where(
                RecipeAccess.recipe_id == recipe.id,
                RecipeAccess.user_id != user.id,
            )
            .order_by(RecipeAccess.user_id)
            .limit(1)
        )
        if other_grant_user is not None:
            new_owner_id = (
                household.owner_id
                if household is not None and household.owner_id != user.id
                else other_grant_user
            )
            recipe.owner_id = new_owner_id
        else:
            db.execute(delete(MealTemplateIngredient).where(
                MealTemplateIngredient.template_id == recipe.id
            ))
            db.execute(delete(MealTemplateFavorite).where(
                MealTemplateFavorite.template_id == recipe.id
            ))
            db.delete(recipe)

    db.flush()

    # Shared foods are retained with a neutral owner reference. Foods no
    # longer shared but still referenced by recipes or other users' meal
    # snapshots are archived rather than deleted.
    owned_foods = db.scalars(select(Food).where(Food.owner_id == user.id)).all()
    for food in owned_foods:
        other_grant = db.scalar(select(FoodAccess.user_id).where(
            FoodAccess.food_id == food.id,
            FoodAccess.user_id != user.id,
        ).limit(1))
        if other_grant is not None:
            food.owner_id = None
        elif _food_has_retained_references(db, food.id):
            food.owner_id = None
            food.household_id = None
            food.is_active = False
        else:
            db.delete(food)

    # Remove all account-scoped grants, hidden markers, invitations and
    # membership rows only after shared records have been classified.
    db.execute(delete(FoodAccess).where(FoodAccess.user_id == user.id))
    db.execute(delete(RecipeAccess).where(RecipeAccess.user_id == user.id))
    db.execute(delete(RecipeIngredientAccess).where(
        RecipeIngredientAccess.user_id == user.id
    ))
    db.execute(delete(FoodHiddenByUser).where(FoodHiddenByUser.user_id == user.id))
    db.execute(delete(RecipeHiddenByUser).where(RecipeHiddenByUser.user_id == user.id))
    db.execute(delete(HouseholdInvitation).where(
        (HouseholdInvitation.invited_user_id == user.id)
        | (HouseholdInvitation.invited_by_user_id == user.id)
    ))
    db.execute(delete(HouseholdMember).where(HouseholdMember.user_id == user.id))

    if delete_household and household is not None:
        # A final-member household has no remaining recipients. Detach retained
        # dependency records before removing the household container.
        db.execute(update(Food).where(
            Food.household_id == household.id
        ).values(household_id=None, is_shared=False))
        db.execute(update(MealTemplate).where(
            MealTemplate.household_id == household.id
        ).values(household_id=None, is_shared=False))
        db.delete(household)

    db.delete(user)
