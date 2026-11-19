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
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
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
    assert client.post("/api/household", json={"name": "Owner Household"}).status_code == 201
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
    assert client.get("/api/nutrition/foods?q=Haferflocken").json() == []

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
    assert client.get("/api/nutrition/foods?q=Haferflocken").json() == []


def test_invitation_authorization_duplicate_and_owner_protection(client: TestClient) -> None:
    register(client, "owner-account")
    register(client, "member-account")
    login(client, "owner-account")
    assert client.post("/api/household", json={"name": "Owner Household"}).status_code == 201
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
    assert client.delete("/api/household/leave").status_code == 204
    assert client.get("/api/household").json()["household"] is None
    assert client.delete(f"/api/household/invitations/{invitation.json()['id']}").status_code == 404


def test_invitee_can_decline_and_owner_can_revoke_pending_invitation(client: TestClient) -> None:
    register(client, "invite-owner")
    register(client, "invite-target")
    login(client, "invite-owner")
    assert client.post("/api/household", json={"name": "Invite Household"}).status_code == 201
    invitation = client.post("/api/household/invitations", json={"username": "invite-target"}).json()
    client.post("/api/auth/logout")
    login(client, "invite-target")
    assert client.delete(f"/api/household/invitations/{invitation['id']}").status_code == 204
    assert client.get("/api/household").json()["invitations"] == []

    client.post("/api/auth/logout")
    login(client, "invite-owner")
    second = client.post("/api/household/invitations", json={"username": "invite-target"}).json()
    assert client.delete(f"/api/household/invitations/{second['id']}").status_code == 204


def test_any_user_can_create_named_household_and_invite_multiple_members(client: TestClient) -> None:
    register(client, "first-admin")
    register(client, "second-member")
    register(client, "third-member")
    register(client, "fourth-pending")
    login(client, "second-member")

    created = client.post("/api/household", json={"name": "WG Sonnenschein"})
    assert created.status_code == 201
    assert created.json()["name"] == "WG Sonnenschein"
    assert created.json()["current_user_role"] == "owner"
    assert len(created.json()["members"]) == 1
    food = client.post("/api/nutrition/foods", json={
        "name": "Private Haferflocken", "basis_g": 100, "calories": 370,
        "protein_g": 13, "carbs_g": 59, "fat_g": 7,
    })
    assert food.status_code == 201
    assert client.post("/api/household", json={"name": "Zweiter Haushalt"}).status_code == 409

    assert client.post("/api/household/invitations", json={"username": "first-admin"}).status_code == 201
    assert client.post("/api/household/invitations", json={"username": "third-member"}).status_code == 201
    assert client.post("/api/household/invitations", json={"username": "fourth-pending"}).status_code == 201
    assert len(client.get("/api/household").json()["pending_invitations"]) == 3

    client.post("/api/auth/logout")
    login(client, "third-member")
    incoming = client.get("/api/household").json()["invitations"]
    assert len(incoming) == 1
    assert client.post("/api/household/invitations/" + str(incoming[0]["id"]) + "/accept").status_code == 200

    client.post("/api/auth/logout")
    login(client, "first-admin")
    incoming = client.get("/api/household").json()["invitations"]
    assert len(incoming) == 1
    assert client.post("/api/household/invitations/" + str(incoming[0]["id"]) + "/accept").status_code == 200

    client.post("/api/auth/logout")
    login(client, "second-member")
    joined = client.get("/api/household").json()["household"]
    assert joined["current_user_role"] == "owner"
    assert len(joined["members"]) == 3
    assert client.delete("/api/household/leave").status_code == 409

    # Remove the other two members, then dissolve the household as its creator.
    for member in joined["members"]:
        if member["user_id"] != joined["owner_id"]:
            assert client.delete("/api/household/members/" + str(member["user_id"])).status_code == 204
    assert len(client.get("/api/household").json()["household"]["members"]) == 1
    assert client.delete("/api/household/leave").status_code == 204
    after_delete = client.get("/api/household").json()
    assert after_delete["household"] is None
    assert after_delete["invitations"] == []
    private_catalog = client.get("/api/nutrition/foods?q=Private%20Haferflocken")
    assert private_catalog.status_code == 200
    assert len(private_catalog.json()) == 1


def test_pre_household_foods_and_recipes_become_shared_after_household_join(client: TestClient) -> None:
    register(client, "catalog-owner")
    login(client, "catalog-owner")
    oats = client.post("/api/nutrition/foods", json={
        "name": "Vorhandene Haferflocken", "basis_g": 100, "calories": 370,
        "protein_g": 13, "carbs_g": 59, "fat_g": 7,
    })
    assert oats.status_code == 201
    recipe = client.post("/api/nutrition/recipes", json={
        "name": "Altes Overnight Oats Rezept", "meal_type": "breakfast",
        "ingredients": [{"food_id": oats.json()["id"], "amount_g": 60}],
    })
    assert recipe.status_code == 201
    assert client.get("/api/nutrition/foods?q=Vorhandene").json()[0]["id"] == oats.json()["id"]

    household = client.post("/api/household", json={"name": "Gemeinsamer Haushalt"})
    assert household.status_code == 201
    # The creator's pre-existing catalog is now attached to the new household.
    assert client.get("/api/nutrition/foods?q=Vorhandene").json()[0]["id"] == oats.json()["id"]

    register(client, "catalog-guest")
    invitation = client.post("/api/household/invitations", json={"username": "catalog-guest"})
    assert invitation.status_code == 201
    client.post("/api/auth/logout")
    login(client, "catalog-guest")
    guest_food = client.post("/api/nutrition/foods", json={
        "name": "Eigene Banane", "basis_g": 100, "calories": 89,
        "protein_g": 1.1, "carbs_g": 23, "fat_g": 0.3,
    })
    assert guest_food.status_code == 201
    assert client.post(f"/api/household/invitations/{invitation.json()['id']}/accept").status_code == 200

    shared_foods = client.get("/api/nutrition/foods?q=Vorhandene")
    assert shared_foods.status_code == 200
    assert [item["id"] for item in shared_foods.json()] == [oats.json()["id"]]
    shared_recipes = client.get("/api/nutrition/recipes?q=Altes")
    assert shared_recipes.status_code == 200
    assert len(shared_recipes.json()) == 1
    assert shared_recipes.json()[0]["name"] == "Altes Overnight Oats Rezept"
    assert len(client.get("/api/nutrition/foods?q=Eigene Banane").json()) == 1
    # Shared foods are usable as ingredients by the newly joined member.
    logged = client.post("/api/nutrition/meals", json={
        "meal_name": "Gemeinsames Frühstück", "meal_type": "breakfast",
        "ingredients": [{"food_id": oats.json()["id"], "amount_g": 30}],
    })
    assert logged.status_code == 201
    # Leaving restores the member's own catalog to private visibility.
    assert client.delete("/api/household/leave").status_code == 204
    assert client.get("/api/nutrition/foods?q=Vorhandene").json() == []
    assert len(client.get("/api/nutrition/foods?q=Eigene Banane").json()) == 1
