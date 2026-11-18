from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(
        bind=test_engine,
        autoflush=False,
        autocommit=False,
    )
    Base.metadata.create_all(bind=test_engine)

    def override_get_db():
        db: Session = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


def register_and_login(client: TestClient, username: str) -> None:
    password = "correct-horse-battery-staple"
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": password},
    )
    assert response.status_code == 201
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200


def test_measurement_create_update_and_delete(client: TestClient) -> None:
    register_and_login(client, "first-user")

    created = client.post("/api/measurements", json={"weight_kg": 82.4})
    assert created.status_code == 201
    entry_id = created.json()["id"]
    assert created.json()["weight_kg"] == 82.4

    updated = client.patch(
        f"/api/measurements/{entry_id}",
        json={"weight_kg": 81.9, "waist_cm": 88.0},
    )
    assert updated.status_code == 200
    assert updated.json()["weight_kg"] == 81.9
    assert updated.json()["waist_cm"] == 88.0

    deleted = client.delete(f"/api/measurements/{entry_id}")
    assert deleted.status_code == 204
    assert client.get("/api/measurements").json() == []


def test_measurement_requires_at_least_one_value(client: TestClient) -> None:
    register_and_login(client, "first-user")
    response = client.post("/api/measurements", json={})
    assert response.status_code == 422


def test_users_cannot_read_or_modify_each_others_measurements(client: TestClient) -> None:
    register_and_login(client, "first-user")
    created = client.post("/api/measurements", json={"weight_kg": 82.4})
    entry_id = created.json()["id"]

    client.post("/api/auth/logout")
    register_and_login(client, "second-user")

    assert client.get("/api/measurements").json() == []
    assert client.patch(
        f"/api/measurements/{entry_id}",
        json={"weight_kg": 70.0},
    ).status_code == 404
    assert client.delete(f"/api/measurements/{entry_id}").status_code == 404


def test_measurement_rejects_invalid_ranges(client: TestClient) -> None:
    register_and_login(client, "first-user")
    response = client.post("/api/measurements", json={"weight_kg": 0})
    assert response.status_code == 422
