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
