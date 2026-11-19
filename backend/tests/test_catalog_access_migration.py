from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.household_models import Household, HouseholdMember
from app.models import User
from app.nutrition_models import Food, FoodAccess, MealTemplate, RecipeAccess
from app.migrate_catalog_access import upgrade


def test_catalog_access_migration_backfills_owners_and_household_members_idempotently():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        first = User(username="acl-first", password_hash="test-hash")
        second = User(username="acl-second", password_hash="test-hash")
        db.add_all([first, second])
        db.flush()

        household = Household(name="ACL Test", owner_id=first.id)
        db.add(household)
        db.flush()
        db.add_all([
            HouseholdMember(household_id=household.id, user_id=first.id, role="owner"),
            HouseholdMember(household_id=household.id, user_id=second.id, role="member"),
        ])
        private_food = Food(
            owner_id=first.id, name="Private Food", basis_g=100,
            calories=10, protein_g=1, carbs_g=1, fat_g=1,
        )
        shared_food = Food(
            owner_id=first.id, household_id=household.id, name="Shared Food",
            basis_g=100, calories=20, protein_g=2, carbs_g=2, fat_g=2,
        )
        shared_recipe = MealTemplate(
            owner_id=first.id, household_id=household.id,
            name="Shared Recipe", meal_type="lunch",
        )
        db.add_all([private_food, shared_food, shared_recipe])
        db.commit()
        private_food_id = private_food.id
        shared_food_id = shared_food.id
        shared_recipe_id = shared_recipe.id
        first_id, second_id = first.id, second.id

    upgrade(bind=engine)
    upgrade(bind=engine)

    with Session(engine) as db:
        private_grants = set(db.scalars(
            select(FoodAccess.user_id).where(FoodAccess.food_id == private_food_id)
        ))
        shared_grants = set(db.scalars(
            select(FoodAccess.user_id).where(FoodAccess.food_id == shared_food_id)
        ))
        recipe_grants = set(db.scalars(
            select(RecipeAccess.user_id).where(RecipeAccess.recipe_id == shared_recipe_id)
        ))
        assert private_grants == {first_id}
        assert shared_grants == {first_id, second_id}
        assert recipe_grants == {first_id, second_id}
        assert db.scalar(select(func.count()).select_from(FoodAccess)) == 3
        assert db.scalar(select(func.count()).select_from(RecipeAccess)) == 2

    Base.metadata.drop_all(bind=engine)
    engine.dispose()
