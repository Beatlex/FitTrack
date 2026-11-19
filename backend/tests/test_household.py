from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app import household_models, nutrition_models  # noqa: F401


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


PASSWORD = "correct-horse-battery-staple"


def register(client: TestClient, username: str) -> None:
    response = client.post("/api/auth/register", json={"username": username, "password": PASSWORD})
    assert response.status_code == 201


def login(client: TestClient, username: str) -> None:
    response = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200


def test_invitation_requires_acceptance_and_grants_household_catalog_access(client: TestClient) -> None:
    register(client, "household-owner")
    login(client, "household-owner")
    owner_household = client.get("/api/household").json()["household"]
    assert owner_household["current_user_role"] == "owner"
    assert len(owner_household["members"]) == 1

    food = client.post("/api/nutrition/foods", json={
        "name": "Haferflocken", "basis_g": 100, "calories": 370,
        "protein_g": 13, "carbs_g": 59, "fat_g": 7,
    })
    assert food.status_code == 201

    register(client, "household-guest")
    invitation = client.post("/api/household/invitations", json={"username": "household-guest"})
    assert invitation.status_code == 201
    invitation_id = invitation.json()["id"]

    client.post("/api/auth/logout")
    login(client, "household-guest")
    before_accept = client.get("/api/household").json()
    assert before_accept["household"] is None
    assert len(before_accept["invitations"]) == 1
    assert client.get("/api/nutrition/foods?q=Haferflocken").status_code == 409

    accepted = client.post(f"/api/household/invitations/{invitation_id}/accept")
    assert accepted.status_code == 200
    joined = client.get("/api/household").json()["household"]
    assert joined["current_user_role"] == "member"
    assert len(joined["members"]) == 2
    assert len(client.get("/api/nutrition/foods?q=Haferflocken").json()) == 1

    # Ordinary members cannot invite other accounts.
    assert client.post("/api/household/invitations", json={"username": "household-owner"}).status_code == 403

    # Owner revocation immediately removes catalog visibility, not personal data.
    client.post("/api/auth/logout")
    login(client, "household-owner")
    assert client.delete(f"/api/household/members/{joined['members'][1]['user_id']}").status_code == 204
    client.post("/api/auth/logout")
    login(client, "household-guest")
    assert client.get("/api/household").json()["household"] is None
    assert client.get("/api/nutrition/foods?q=Haferflocken").status_code == 409


def test_invitation_authorization_duplicate_and_owner_protection(client: TestClient) -> None:
    register(client, "owner-account")
    register(client, "member-account")
    login(client, "owner-account")
    assert client.post("/api/household/invitations", json={"username": "missing-account"}).status_code == 404
    assert client.post("/api/household/invitations", json={"username": "owner-account"}).status_code == 400

    invitation = client.post("/api/household/invitations", json={"username": "member-account"})
    assert invitation.status_code == 201
    assert client.post("/api/household/invitations", json={"username": "member-account"}).status_code == 409

    client.post("/api/auth/logout")
    login(client, "member-account")
    assert client.delete("/api/household/members/1").status_code == 404
    assert client.delete("/api/household/leave").status_code == 404
    assert client.post(f"/api/household/invitations/{invitation.json()['id']}/accept").status_code == 200
    assert client.delete("/api/household/members/1").status_code == 403
    assert client.delete("/api/household/leave").status_code == 204

    client.post("/api/auth/logout")
    login(client, "owner-account")
    assert client.delete("/api/household/leave").status_code == 409
    assert client.delete(f"/api/household/invitations/{invitation.json()['id']}").status_code == 404


def test_invitee_can_decline_and_owner_can_revoke_pending_invitation(client: TestClient) -> None:
    register(client, "invite-owner")
    register(client, "invite-target")
    login(client, "invite-owner")
    invitation = client.post("/api/household/invitations", json={"username": "invite-target"}).json()
    client.post("/api/auth/logout")
    login(client, "invite-target")
    assert client.delete(f"/api/household/invitations/{invitation['id']}").status_code == 204
    assert client.get("/api/household").json()["invitations"] == []

    client.post("/api/auth/logout")
    login(client, "invite-owner")
    second = client.post("/api/household/invitations", json={"username": "invite-target"}).json()
    assert client.delete(f"/api/household/invitations/{second['id']}").status_code == 204
