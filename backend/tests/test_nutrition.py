from collections.abc import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from app.database import Base, get_db
from app.main import app
from app import nutrition_models  # noqa: F401

@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    testing = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    def override_get_db():
        db: Session = testing()
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()

def login(client: TestClient, username: str) -> None:
    password = "correct-horse-battery-staple"
    assert client.post("/api/auth/register", json={"username": username, "password": password}).status_code == 201
    assert client.post("/api/auth/login", json={"username": username, "password": password}).status_code == 200

def test_overnight_oats_breakfast_and_daily_remaining(client: TestClient) -> None:
    login(client, "oats-user")
    targets = {"calories": 2200, "protein_g": 160, "carbs_g": 220, "fat_g": 70}
    assert client.put("/api/nutrition/goals", json=targets).status_code == 200
    oats = client.post("/api/nutrition/foods", json={
        "name": "Overnight Oats", "brand": "FitTrack Test", "basis_g": 100,
        "calories": 150, "protein_g": 6, "carbs_g": 23, "fat_g": 4,
    })
    assert oats.status_code == 201
    meal = client.post("/api/nutrition/meals", json={
        "food_id": oats.json()["id"], "amount_g": 300, "meal_type": "breakfast",
    })
    assert meal.status_code == 201
    assert meal.json()["calories"] == 450
    day = client.get("/api/nutrition/day").json()
    assert day["consumed"]["calories"] == 450
    assert day["remaining"]["calories"] == 1750
    assert day["remaining"]["protein_g"] == 142
    assert day["entries"][0]["meal_type"] == "breakfast"

def test_goals_and_foods_are_isolated_per_user(client: TestClient) -> None:
    login(client, "first-owner")
    goal = {"calories": 2000, "protein_g": 100, "carbs_g": 200, "fat_g": 60}
    assert client.put("/api/nutrition/goals", json=goal).status_code == 200
    food = client.post("/api/nutrition/foods", json={
        "name": "Private Oats", "calories": 100, "protein_g": 4, "carbs_g": 15, "fat_g": 2,
    }).json()
    client.post("/api/auth/logout")
    login(client, "second-owner")
    assert client.get("/api/nutrition/goals").json() is None
    assert client.get("/api/nutrition/foods?q=Private").json() == []
    assert client.post("/api/nutrition/meals", json={
        "food_id": food["id"], "amount_g": 100, "meal_type": "breakfast",
    }).status_code == 404

def test_invalid_nutrients_and_meal_type_are_rejected(client: TestClient) -> None:
    login(client, "validation-user")
    assert client.put("/api/nutrition/goals", json={
        "calories": -1, "protein_g": 1, "carbs_g": 1, "fat_g": 1,
    }).status_code == 422
    assert client.post("/api/nutrition/foods", json={
        "name": "   ", "calories": 1, "protein_g": 1, "carbs_g": 1, "fat_g": 1,
    }).status_code == 422


def test_recipe_with_multiple_ingredients_sums_nutrients_and_deletes_cleanly(client: TestClient) -> None:
    login(client, "recipe-owner")
    oats = client.post("/api/nutrition/foods", json={
        "name": "Haferflocken", "basis_g": 100, "calories": 370,
        "protein_g": 13, "carbs_g": 59, "fat_g": 7,
    }).json()
    milk = client.post("/api/nutrition/foods", json={
        "name": "Milch", "basis_g": 100, "calories": 64,
        "protein_g": 3.4, "carbs_g": 4.8, "fat_g": 3.5,
    }).json()
    meal = client.post("/api/nutrition/meals", json={
        "meal_name": "Overnight Oats",
        "meal_type": "breakfast",
        "ingredients": [
            {"food_id": oats["id"], "amount_g": 50},
            {"food_id": milk["id"], "amount_g": 150},
        ],
    })
    assert meal.status_code == 201
    payload = meal.json()
    assert payload["food_name"] == "Overnight Oats"
    assert payload["amount_g"] == 200
    assert payload["calories"] == 281
    assert len(payload["ingredients"]) == 2
    assert payload["ingredients"][0]["food_name"] == "Haferflocken"
    day = client.get("/api/nutrition/day").json()
    assert day["consumed"]["calories"] == 281
    assert len(day["entries"]) == 1

    deleted = client.delete(f"/api/nutrition/meals/{payload['id']}")
    assert deleted.status_code == 204
    after_delete = client.get("/api/nutrition/day").json()
    assert after_delete["consumed"]["calories"] == 0
    assert after_delete["entries"] == []


def test_recipe_rejects_foreign_ingredient_and_too_many_ingredients(client: TestClient) -> None:
    login(client, "recipe-first")
    private_food = client.post("/api/nutrition/foods", json={
        "name": "Private Ingredient", "calories": 100, "protein_g": 1, "carbs_g": 1, "fat_g": 1,
    }).json()
    client.post("/api/auth/logout")
    login(client, "recipe-second")
    response = client.post("/api/nutrition/meals", json={
        "meal_name": "Unauthorized recipe",
        "meal_type": "breakfast",
        "ingredients": [{"food_id": private_food["id"], "amount_g": 100}],
    })
    assert response.status_code == 404

    too_many = [{"food_id": 999, "amount_g": 1} for _ in range(31)]
    invalid = client.post("/api/nutrition/meals", json={
        "meal_name": "Too many ingredients", "meal_type": "breakfast", "ingredients": too_many,
    })
    assert invalid.status_code == 422


def test_saved_recipe_favorites_and_logging_update_daily_totals(client: TestClient) -> None:
    login(client, "recipe-library")
    oats = client.post("/api/nutrition/foods", json={
        "name": "Haferflocken", "basis_g": 100, "calories": 370,
        "protein_g": 13, "carbs_g": 59, "fat_g": 7,
    })
    assert oats.status_code == 201
    milk = client.post("/api/nutrition/foods", json={
        "name": "Milch", "basis_g": 100, "calories": 64,
        "protein_g": 3.4, "carbs_g": 4.8, "fat_g": 3.5,
    })
    assert milk.status_code == 201
    recipe = client.post("/api/nutrition/recipes", json={
        "name": "Overnight Oats", "meal_type": "breakfast",
        "ingredients": [
            {"food_id": oats.json()["id"], "amount_g": 50},
            {"food_id": milk.json()["id"], "amount_g": 150},
        ],
    })
    assert recipe.status_code == 201
    assert recipe.json()["calories"] == 281
    assert len(recipe.json()["ingredients"]) == 2

    favorite = client.patch(f"/api/nutrition/recipes/{recipe.json()['id']}/favorite",
                            json={"is_favorite": True})
    assert favorite.status_code == 200
    assert favorite.json()["is_favorite"] is True
    assert len(client.get("/api/nutrition/recipes?favorites_only=true").json()) == 1

    logged = client.post(f"/api/nutrition/recipes/{recipe.json()['id']}/log")
    assert logged.status_code == 201
    assert logged.json()["food_name"] == "Overnight Oats"
    assert len(logged.json()["ingredients"]) == 2
    day = client.get("/api/nutrition/day").json()
    assert day["consumed"]["calories"] == 281
    assert day["entries"][0]["meal_type"] == "breakfast"


def test_recipe_and_food_duplicates_are_rejected_and_favorites_are_private(client: TestClient) -> None:
    login(client, "recipe-private-a")
    food = client.post("/api/nutrition/foods", json={
        "name": "Banane", "calories": 89, "protein_g": 1.1, "carbs_g": 23, "fat_g": 0.3,
    })
    assert food.status_code == 201
    duplicate_food = client.post("/api/nutrition/foods", json={
        "name": "banane", "calories": 89, "protein_g": 1.1, "carbs_g": 23, "fat_g": 0.3,
    })
    assert duplicate_food.status_code == 409
    recipe = client.post("/api/nutrition/recipes", json={
        "name": "Bananen Snack", "meal_type": "snack",
        "ingredients": [{"food_id": food.json()["id"], "amount_g": 120}],
    })
    assert recipe.status_code == 201
    duplicate_recipe = client.post("/api/nutrition/recipes", json={
        "name": "bananen snack", "meal_type": "snack",
        "ingredients": [{"food_id": food.json()["id"], "amount_g": 120}],
    })
    assert duplicate_recipe.status_code == 409

    client.post("/api/auth/logout")
    login(client, "recipe-private-b")
    assert client.get("/api/nutrition/recipes").json() == []
    assert client.get("/api/nutrition/foods?q=Banane").json() == []
    assert client.patch(f"/api/nutrition/recipes/{recipe.json()['id']}/favorite",
                        json={"is_favorite": True}).status_code == 404
