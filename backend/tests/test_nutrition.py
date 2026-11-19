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
    if client.get("/api/household").json()["household"] is None:
        assert client.post("/api/household", json={"name": username + " Household"}).status_code == 201



def invite_and_switch_to_second_user(client: TestClient, username: str) -> None:
    password = "correct-horse-battery-staple"
    assert client.post("/api/auth/register", json={
        "username": username, "password": password,
    }).status_code == 201
    invitation = client.post("/api/household/invitations", json={"username": username})
    assert invitation.status_code == 201
    invitation_id = invitation.json()["id"]
    assert client.post("/api/auth/logout").status_code == 200
    assert client.post("/api/auth/login", json={
        "username": username, "password": password,
    }).status_code == 200
    assert client.post(f"/api/household/invitations/{invitation_id}/accept").status_code == 200


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


def test_second_user_can_use_shared_food_and_meal_limits_are_enforced(client: TestClient) -> None:
    login(client, "recipe-first")
    private_food = client.post("/api/nutrition/foods", json={
        "name": "Private Ingredient", "calories": 100, "protein_g": 1, "carbs_g": 1, "fat_g": 1,
    }).json()
    invite_and_switch_to_second_user(client, "recipe-second")
    response = client.post("/api/nutrition/meals", json={
        "meal_name": "Unauthorized recipe",
        "meal_type": "breakfast",
        "ingredients": [{"food_id": private_food["id"], "amount_g": 100}],
    })
    assert response.status_code == 201

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


def test_food_can_be_updated_and_archived_without_changing_historical_entries(client: TestClient) -> None:
    login(client, "food-maintenance")
    created = client.post("/api/nutrition/foods", json={
        "name": "Haferflocken", "basis_g": 100, "calories": 370,
        "protein_g": 13, "carbs_g": 59, "fat_g": 7,
    })
    assert created.status_code == 201
    food_id = created.json()["id"]
    logged = client.post("/api/nutrition/meals", json={
        "meal_name": "Oats Frühstück", "meal_type": "breakfast",
        "ingredients": [{"food_id": food_id, "amount_g": 50}],
    })
    assert logged.status_code == 201
    assert logged.json()["calories"] == 185

    updated = client.put(f"/api/nutrition/foods/{food_id}", json={
        "name": "Haferflocken fein", "basis_g": 100, "calories": 400,
        "protein_g": 14, "carbs_g": 62, "fat_g": 8,
    })
    assert updated.status_code == 200
    assert updated.json()["name"] == "Haferflocken fein"
    assert updated.json()["calories"] == 400
    # Existing entries retain the nutrient snapshot from the time of logging.
    day = client.get("/api/nutrition/day").json()
    assert day["consumed"]["calories"] == 185
    assert day["entries"][0]["ingredients"][0]["food_name"] == "Haferflocken"
    assert day["entries"][0]["ingredients"][0]["calories"] == 185

    duplicate = client.post("/api/nutrition/foods", json={
        "name": "HAFERFLOCKEN FEIN", "basis_g": 100, "calories": 400,
        "protein_g": 14, "carbs_g": 62, "fat_g": 8,
    })
    assert duplicate.status_code == 409

    archived = client.delete(f"/api/nutrition/foods/{food_id}")
    assert archived.status_code == 204
    assert client.get("/api/nutrition/foods?q=Haferflocken").json() == []
    assert client.post("/api/nutrition/meals", json={
        "meal_name": "No longer selectable", "meal_type": "breakfast",
        "ingredients": [{"food_id": food_id, "amount_g": 50}],
    }).status_code == 404
    # Historical data remains readable after archiving the source food.
    assert client.get("/api/nutrition/day").json()["consumed"]["calories"] == 185


def test_recipe_can_be_edited_and_keeps_old_logged_snapshot(client: TestClient) -> None:
    login(client, "recipe-maintenance")
    oats = client.post("/api/nutrition/foods", json={
        "name": "Oats", "basis_g": 100, "calories": 370,
        "protein_g": 13, "carbs_g": 59, "fat_g": 7,
    }).json()
    milk = client.post("/api/nutrition/foods", json={
        "name": "Milch", "basis_g": 100, "calories": 64,
        "protein_g": 3.4, "carbs_g": 4.8, "fat_g": 3.5,
    }).json()
    recipe = client.post("/api/nutrition/recipes", json={
        "name": "Overnight Oats", "meal_type": "breakfast",
        "ingredients": [{"food_id": oats["id"], "amount_g": 50}],
    }).json()
    logged = client.post(f"/api/nutrition/recipes/{recipe['id']}/log")
    assert logged.status_code == 201
    assert logged.json()["calories"] == 185

    updated = client.put(f"/api/nutrition/recipes/{recipe['id']}", json={
        "name": "Overnight Oats Deluxe", "meal_type": "breakfast",
        "ingredients": [
            {"food_id": oats["id"], "amount_g": 50},
            {"food_id": milk["id"], "amount_g": 150},
        ],
    })
    assert updated.status_code == 200
    assert updated.json()["name"] == "Overnight Oats Deluxe"
    assert updated.json()["calories"] == 281
    # Editing a reusable recipe must not rewrite an already logged meal.
    day = client.get("/api/nutrition/day").json()
    assert day["consumed"]["calories"] == 185
    assert day["entries"][0]["food_name"] == "Overnight Oats"
    assert day["entries"][0]["calories"] == 185


def test_foods_and_recipes_are_shared_but_recipe_favorites_are_per_user(client: TestClient) -> None:
    login(client, "shared-catalog-owner")
    oats = client.post("/api/nutrition/foods", json={
        "name": "Haferflocken", "basis_g": 100, "calories": 370,
        "protein_g": 13, "carbs_g": 59, "fat_g": 7,
    })
    assert oats.status_code == 201
    recipe = client.post("/api/nutrition/recipes", json={
        "name": "Overnight Oats", "meal_type": "breakfast",
        "ingredients": [{"food_id": oats.json()["id"], "amount_g": 50}],
    })
    assert recipe.status_code == 201

    invite_and_switch_to_second_user(client, "shared-catalog-second")
    visible_foods = client.get("/api/nutrition/foods?q=Haferflocken")
    assert visible_foods.status_code == 200
    assert len(visible_foods.json()) == 1
    visible_recipes = client.get("/api/nutrition/recipes")
    assert len(visible_recipes.json()) == 1
    recipe_id = visible_recipes.json()[0]["id"]

    # Either household user can maintain shared master data and recipes.
    updated_food = client.put(f"/api/nutrition/foods/{oats.json()['id']}", json={
        "name": "Haferflocken zart", "basis_g": 100, "calories": 380,
        "protein_g": 14, "carbs_g": 60, "fat_g": 7,
    })
    assert updated_food.status_code == 200
    updated_recipe = client.put(f"/api/nutrition/recipes/{recipe_id}", json={
        "name": "Overnight Oats Deluxe", "meal_type": "breakfast",
        "ingredients": [{"food_id": oats.json()["id"], "amount_g": 50}],
    })
    assert updated_recipe.status_code == 200

    # Favorite state belongs to the logged-in user, not to the shared recipe.
    assert client.patch(f"/api/nutrition/recipes/{recipe_id}/favorite",
                        json={"is_favorite": True}).status_code == 200
    assert len(client.get("/api/nutrition/recipes?favorites_only=true").json()) == 1
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"username": "shared-catalog-owner", "password": "correct-horse-battery-staple"}).status_code == 200
    assert len(client.get("/api/nutrition/recipes").json()) == 1
    assert client.get("/api/nutrition/recipes?favorites_only=true").json() == []
    assert client.get("/api/nutrition/foods?q=zart").json()[0]["calories"] == 380

    # A food referenced by a saved recipe cannot be archived accidentally.
    assert client.delete(f"/api/nutrition/foods/{oats.json()['id']}").status_code == 409


def test_shared_catalog_duplicate_detection_and_system_food_protection(client: TestClient) -> None:
    login(client, "shared-duplicate-a")
    food = client.post("/api/nutrition/foods", json={
        "name": "Naturjoghurt", "basis_g": 100, "calories": 65,
        "protein_g": 4, "carbs_g": 5, "fat_g": 3,
    })
    assert food.status_code == 201
    invite_and_switch_to_second_user(client, "shared-duplicate-b")
    duplicate = client.post("/api/nutrition/foods", json={
        "name": "naturjoghurt", "basis_g": 100, "calories": 65,
        "protein_g": 4, "carbs_g": 5, "fat_g": 3,
    })
    assert duplicate.status_code == 409


def test_personal_hide_restore_and_recipe_dependency_access_are_separate(client: TestClient) -> None:
    login(client, "acl-hide-owner")
    food = client.post("/api/nutrition/foods", json={
        "name": "ACL Hafer", "basis_g": 100, "calories": 370,
        "protein_g": 13, "carbs_g": 59, "fat_g": 7,
    }).json()
    recipe = client.post("/api/nutrition/recipes", json={
        "name": "ACL Frühstück", "meal_type": "breakfast",
        "ingredients": [{"food_id": food["id"], "amount_g": 50}],
    }).json()

    invite_and_switch_to_second_user(client, "acl-hide-member")
    assert len(client.get("/api/nutrition/foods?q=ACL").json()) == 1
    assert len(client.get("/api/nutrition/recipes?q=ACL").json()) == 1

    assert client.post(f"/api/nutrition/foods/{food['id']}/hide").status_code == 204
    assert client.get("/api/nutrition/foods?q=ACL").json() == []
    visible_recipe = client.get("/api/nutrition/recipes?q=ACL").json()
    assert len(visible_recipe) == 1
    assert visible_recipe[0]["ingredients"][0]["food_name"] == "ACL Hafer"
    assert client.post(f"/api/nutrition/recipes/{recipe['id']}/log").status_code == 201

    assert client.delete(f"/api/nutrition/foods/{food['id']}/hide").status_code == 204
    assert len(client.get("/api/nutrition/foods?q=ACL").json()) == 1
    assert client.post(f"/api/nutrition/recipes/{recipe['id']}/hide").status_code == 204
    assert client.get("/api/nutrition/recipes?q=ACL").json() == []
    assert client.delete(f"/api/nutrition/recipes/{recipe['id']}/hide").status_code == 204
    assert len(client.get("/api/nutrition/recipes?q=ACL").json()) == 1

    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={
        "username": "acl-hide-owner", "password": "correct-horse-battery-staple",
    }).status_code == 200
    assert len(client.get("/api/nutrition/foods?q=ACL").json()) == 1
    assert len(client.get("/api/nutrition/recipes?q=ACL").json()) == 1


def test_departing_food_owner_loses_picker_access_but_existing_recipe_dependency_survives(client: TestClient) -> None:
    login(client, "acl-dependency-owner")
    invite_and_switch_to_second_user(client, "acl-dependency-member")
    member_food = client.post("/api/nutrition/foods", json={
        "name": "Mitglieds-Zutat", "basis_g": 100, "calories": 80,
        "protein_g": 4, "carbs_g": 10, "fat_g": 2,
    }).json()

    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={
        "username": "acl-dependency-owner", "password": "correct-horse-battery-staple",
    }).status_code == 200
    recipe = client.post("/api/nutrition/recipes", json={
        "name": "Rezept mit Mitgliederzutat", "meal_type": "lunch",
        "ingredients": [{"food_id": member_food["id"], "amount_g": 100}],
    })
    assert recipe.status_code == 201

    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={
        "username": "acl-dependency-member", "password": "correct-horse-battery-staple",
    }).status_code == 200
    assert client.delete("/api/household/leave").status_code == 204

    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={
        "username": "acl-dependency-owner", "password": "correct-horse-battery-staple",
    }).status_code == 200
    assert client.get("/api/nutrition/foods?q=Mitglieds-Zutat").json() == []
    remaining_recipe = client.get("/api/nutrition/recipes?q=Mitgliederzutat")
    assert remaining_recipe.status_code == 200
    assert len(remaining_recipe.json()) == 1
    assert remaining_recipe.json()[0]["ingredients"][0]["food_name"] == "Mitglieds-Zutat"
    logged = client.post(f"/api/nutrition/recipes/{recipe.json()['id']}/log")
    assert logged.status_code == 201
    assert logged.json()["calories"] == 80
