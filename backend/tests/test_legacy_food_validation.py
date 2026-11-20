from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app import household_models, nutrition_models  # noqa: F401


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

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


def test_legacy_food_endpoint_rejects_non_finite_nutrient_values(client: TestClient) -> None:
    credentials = {
        "username": "legacy-validation",
        "password": "correct-horse-battery-staple",
    }
    assert client.post("/api/auth/register", json=credentials).status_code == 201
    assert client.post("/api/auth/login", json=credentials).status_code == 200

    prefix = '{"food_name":"Legacy meal","meal_type":"lunch","amount_g":100,"calories":'
    suffix = ',"protein_g":10,"carbs_g":20,"fat_g":5}'
    for invalid_value in ("NaN", "Infinity", "-Infinity"):
        response = client.post(
            "/api/food",
            content=prefix + invalid_value + suffix,
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400

    valid = client.post("/api/food", json={
        "food_name": "Legacy meal",
        "meal_type": "lunch",
        "amount_g": 100,
        "calories": 120,
        "protein_g": 10,
        "carbs_g": 20,
        "fat_g": 5,
    })
    assert valid.status_code == 201
