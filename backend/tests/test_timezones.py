from collections.abc import Generator
from datetime import date
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
import app.main as main_module
import app.routers.nutrition as nutrition_router_module
from app.migrate_user_timezone import upgrade
from app.timezones import local_day_bounds


@pytest.mark.parametrize(
    ("day", "timezone_name", "expected_hours"),
    [
        (date(2026, 3, 29), "Europe/Berlin", 23),
        (date(2026, 10, 25), "Europe/Berlin", 25),
        (date(2026, 3, 29), "UTC", 24),
    ],
)
def test_local_day_bounds_respect_dst(day, timezone_name, expected_hours):
    start, end = local_day_bounds(day, timezone_name)
    assert (end - start).total_seconds() == expected_hours * 60 * 60
    assert start.tzinfo is not None and end.tzinfo is not None


def test_timezone_migration_is_additive_and_idempotent():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(40) NOT NULL)"
        )
    upgrade(engine)
    upgrade(engine)
    columns = {column["name"] for column in inspect(engine).get_columns("users")}
    assert "timezone_name" in columns
    engine.dispose()


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


def register_and_login(client: TestClient, username: str = "timezone-user") -> None:
    password = "correct-horse-battery-staple"
    assert client.post(
        "/api/auth/register",
        json={"username": username, "password": password},
    ).status_code == 201
    assert client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    ).status_code == 200
    assert client.post("/api/household", json={"name": "Timezone household"}).status_code == 201


def test_timezone_choices_match_server_timezone_database(client: TestClient):
    register_and_login(client)
    response = client.get("/api/auth/timezones")
    assert response.status_code == 200
    zones = response.json()
    assert "Europe/Berlin" in zones
    assert "UTC" in zones
    assert zones == sorted(set(zones))


def test_timezone_preference_is_validated_and_returned(client: TestClient):
    register_and_login(client)
    assert client.get("/api/auth/me").json()["timezone_name"] is None

    saved = client.patch(
        "/api/auth/timezone",
        json={"timezone_name": "Europe/Berlin"},
    )
    assert saved.status_code == 200
    assert saved.json() == {"timezone_name": "Europe/Berlin"}
    assert client.get("/api/auth/me").json()["timezone_name"] == "Europe/Berlin"

    invalid = client.patch(
        "/api/auth/timezone",
        json={"timezone_name": "Mars/Olympus_Mons"},
    )
    assert invalid.status_code == 422
    assert client.get("/api/auth/me").json()["timezone_name"] == "Europe/Berlin"


def test_nutrition_and_dashboard_share_dst_aware_local_day(client: TestClient, monkeypatch):
    register_and_login(client)
    assert client.patch(
        "/api/auth/timezone",
        json={"timezone_name": "Europe/Berlin"},
    ).status_code == 200

    food = client.post("/api/nutrition/foods", json={
        "name": "DST Test Food",
        "basis_g": 100,
        "calories": 200,
        "protein_g": 10,
        "carbs_g": 20,
        "fat_g": 5,
    })
    assert food.status_code == 201
    food_id = food.json()["id"]

    # Europe/Berlin's 2026-03-29 calendar day is [2026-03-28 23:00Z,
    # 2026-03-29 22:00Z): exactly 23 hours across the spring DST transition.
    timestamps = [
        ("2026-03-28T22:30:00+00:00", False),
        # Same instant is previous local day; offsets must be normalized to UTC.
        ("2026-03-28T23:30:00+02:00", False),
        ("2026-03-28T23:30:00+00:00", True),
        ("2026-03-29T21:30:00+00:00", True),
        ("2026-03-29T22:30:00+00:00", False),
    ]
    for timestamp, _included in timestamps:
        response = client.post("/api/nutrition/meals", json={
            "meal_name": "DST boundary meal",
            "meal_type": "snack",
            "food_id": food_id,
            "amount_g": 50,
            "consumed_at": timestamp,
        })
        assert response.status_code == 201, response.text

    daily = client.get("/api/nutrition/day?day=2026-03-29")
    assert daily.status_code == 200
    assert daily.json()["date"] == "2026-03-29"
    assert len(daily.json()["entries"]) == 2
    assert daily.json()["consumed"]["calories"] == 200

    monkeypatch.setattr(nutrition_router_module, "local_today", lambda _timezone: date(2026, 3, 29))
    default_day = client.get("/api/nutrition/day")
    assert default_day.status_code == 200
    assert default_day.json()["date"] == "2026-03-29"

    monkeypatch.setattr(main_module, "local_today", lambda _timezone: date(2026, 3, 29))
    dashboard = client.get("/api/dashboard")
    assert dashboard.status_code == 200
    assert dashboard.json()["today"]["calories"] == daily.json()["consumed"]["calories"]


def test_local_day_bounds_use_real_iana_rules_not_fixed_offsets():
    spring_start, spring_end = local_day_bounds(date(2026, 3, 29), "Europe/Berlin")
    autumn_start, autumn_end = local_day_bounds(date(2026, 10, 25), "Europe/Berlin")
    assert spring_start.astimezone(ZoneInfo("Europe/Berlin")).hour == 0
    assert spring_end.astimezone(ZoneInfo("Europe/Berlin")).hour == 0
    assert autumn_start.utcoffset().total_seconds() == 0
    assert autumn_end.utcoffset().total_seconds() == 0
    assert (spring_end - spring_start).total_seconds() == 23 * 3600
    assert (autumn_end - autumn_start).total_seconds() == 25 * 3600
