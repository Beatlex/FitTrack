from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.concurrency import commit_versioned_change
from app.database import Base
from app.models import User
from app.nutrition_models import Food
from app import household_models, nutrition_models  # noqa: F401
from fastapi import HTTPException


def test_versioned_catalog_updates_reject_a_late_concurrent_writer(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'concurrency.sqlite'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with sessions.begin() as db:
        user = User(username="concurrency-user", password_hash="not-a-real-login-hash")
        db.add(user)
        db.flush()
        food = Food(
            owner_id=user.id, name="Original", basis_g=100, calories=100,
            protein_g=5, carbs_g=10, fat_g=2,
        )
        db.add(food)
        db.flush()
        food_id = food.id

    first = sessions()
    second = sessions()
    try:
        first_food = first.get(Food, food_id)
        second_food = second.get(Food, food_id)
        assert first_food is not None and second_food is not None
        assert first_food.version == second_food.version == 1

        first_food.name = "First writer"
        first.commit()
        assert first_food.version == 2

        second_food.name = "Stale writer"
        try:
            commit_versioned_change(
                second,
                detail="The catalog item changed. Reload before retrying.",
            )
        except HTTPException as exc:
            assert exc.status_code == 409
        else:
            raise AssertionError("A stale concurrent write must be rejected.")
    finally:
        first.close()
        second.close()

    with sessions() as verify:
        saved = verify.scalar(select(Food).where(Food.id == food_id))
        assert saved is not None
        assert saved.name == "First writer"
        assert saved.version == 2

    engine.dispose()
