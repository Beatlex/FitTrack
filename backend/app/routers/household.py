from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..audit_service import record_catalog_event
from ..dependencies import current_user
from ..household_models import Household, HouseholdInvitation, HouseholdMember
from ..models import User
from ..nutrition_models import (
    CatalogAuditEvent, Food, FoodAccess, MealTemplate, RecipeAccess,
)
from ..catalog_access import (
    grant_owned_catalog_to_household,
    grant_household_catalog_to_member,
    revoke_household_access_for_member,
    grant_food_to_user,
    revoke_food_from_user,
    grant_recipe_to_user,
    revoke_recipe_from_user,
)

router = APIRouter(prefix="/api/household", tags=["household"])


class HouseholdCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class InvitationCreate(BaseModel):
    username: str = Field(min_length=3, max_length=40, pattern=r"^[a-zA-Z0-9_.-]+$")


def membership_for_user(db: Session, user_id: int) -> HouseholdMember | None:
    return db.scalar(select(HouseholdMember).where(HouseholdMember.user_id == user_id))


def require_owner(db: Session, user_id: int, household_id: int) -> HouseholdMember:
    membership = db.scalar(select(HouseholdMember).where(
        HouseholdMember.user_id == user_id,
        HouseholdMember.household_id == household_id,
        HouseholdMember.role == "owner",
    ))
    if membership is None:
        raise HTTPException(403, "Nur der Haushaltsinhaber darf diese Aktion ausführen.")
    return membership



def share_owned_catalog(db: Session, user_id: int, household_id: int) -> None:
    """Move a member's pre-existing private catalog into their new household."""
    db.flush()
    db.execute(update(Food).where(
        Food.owner_id == user_id, Food.household_id.is_(None), Food.is_system.is_(False)
    ).values(household_id=household_id, is_shared=True))
    db.execute(update(MealTemplate).where(
        MealTemplate.owner_id == user_id, MealTemplate.household_id.is_(None)
    ).values(household_id=household_id, is_shared=True))
    db.flush()
    grant_owned_catalog_to_household(db, user_id, household_id)


def privatize_owned_catalog(db: Session, user_id: int, household_id: int) -> None:
    """Detach a departing member's owned catalog from household-wide sharing.

    RecipeIngredientAccess preserves access needed by other members' existing
    recipes, without keeping the food in the household's selectable catalog.
    """
    db.execute(update(Food).where(
        Food.owner_id == user_id, Food.household_id == household_id,
    ).values(household_id=None, is_shared=False))
    db.execute(update(MealTemplate).where(
        MealTemplate.owner_id == user_id, MealTemplate.household_id == household_id
    ).values(household_id=None, is_shared=False))

def household_payload(db: Session, household: Household, user_id: int) -> dict:
    members = db.execute(
        select(HouseholdMember, User.username)
        .join(User, User.id == HouseholdMember.user_id)
        .where(HouseholdMember.household_id == household.id)
        .order_by(HouseholdMember.joined_at, HouseholdMember.id)
    ).all()
    return {
        "id": household.id,
        "name": household.name,
        "owner_id": household.owner_id,
        "current_user_id": user_id,
        "current_user_role": next((m.role for m, _ in members if m.user_id == user_id), None),
        "members": [
            {"user_id": member.user_id, "username": username, "role": member.role,
             "joined_at": member.joined_at.isoformat()}
            for member, username in members
        ],
    }




def _catalog_access_context(db: Session, user_id: int):
    membership = membership_for_user(db, user_id)
    if membership is None:
        raise HTTPException(409, "Du musst einem Haushalt angehören.")
    require_owner(db, user_id, membership.household_id)
    return membership


def _require_catalog_member(db: Session, household_id: int, target_user_id: int) -> HouseholdMember:
    target = db.scalar(select(HouseholdMember).where(
        HouseholdMember.household_id == household_id,
        HouseholdMember.user_id == target_user_id,
    ))
    if target is None:
        raise HTTPException(404, "Haushaltsmitglied nicht gefunden.")
    return target


@router.get("/catalog-access")
def get_catalog_access(db: Session = Depends(get_db), user: User = Depends(current_user)):
    membership = _catalog_access_context(db, user.id)
    household_id = membership.household_id
    members = db.execute(
        select(HouseholdMember, User.username)
        .join(User, User.id == HouseholdMember.user_id)
        .where(HouseholdMember.household_id == household_id)
        .order_by(HouseholdMember.joined_at, HouseholdMember.id)
    ).all()
    foods = db.scalars(select(Food).where(
        Food.household_id == household_id,
        Food.is_active.is_(True),
        Food.is_system.is_(False),
    ).order_by(Food.name, Food.id)).all()
    recipes = db.scalars(select(MealTemplate).where(
        MealTemplate.household_id == household_id,
    ).order_by(MealTemplate.name, MealTemplate.id)).all()
    food_ids = [item.id for item in foods]
    recipe_ids = [item.id for item in recipes]
    food_grants = set(db.execute(select(FoodAccess.food_id, FoodAccess.user_id).where(
        FoodAccess.food_id.in_(food_ids),
    )).all()) if food_ids else set()
    recipe_grants = set(db.execute(select(RecipeAccess.recipe_id, RecipeAccess.user_id).where(
        RecipeAccess.recipe_id.in_(recipe_ids),
    )).all()) if recipe_ids else set()
    return {
        "members": [
            {"user_id": member.user_id, "username": username, "role": member.role}
            for member, username in members
        ],
        "foods": [
            {"id": item.id, "name": item.name, "owner_id": item.owner_id,
             "granted_user_ids": sorted(uid for food_id, uid in food_grants if food_id == item.id)}
            for item in foods
        ],
        "recipes": [
            {"id": item.id, "name": item.name, "owner_id": item.owner_id,
             "granted_user_ids": sorted(uid for recipe_id, uid in recipe_grants if recipe_id == item.id)}
            for item in recipes
        ],
    }


@router.get("/audit")
def get_household_audit(
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    membership = _catalog_access_context(db, user.id)
    events = db.scalars(
        select(CatalogAuditEvent)
        .where(CatalogAuditEvent.household_id == membership.household_id)
        .order_by(CatalogAuditEvent.created_at.desc(), CatalogAuditEvent.id.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": event.id,
            "actor_username": event.actor_username,
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "entity_name": event.entity_name,
            "action": event.action,
            "changes": event.changes,
            "created_at": event.created_at.isoformat(),
        }
        for event in events
    ]

@router.put("/catalog-access/foods/{food_id}/members/{target_user_id}", status_code=204)
def grant_food_access(food_id: int, target_user_id: int,
                      db: Session = Depends(get_db), user: User = Depends(current_user)):
    membership = _catalog_access_context(db, user.id)
    target = _require_catalog_member(db, membership.household_id, target_user_id)
    food = db.scalar(select(Food).where(
        Food.id == food_id,
        Food.household_id == membership.household_id,
        Food.is_active.is_(True),
        Food.is_system.is_(False),
    ))
    if food is None:
        raise HTTPException(404, "Haushalts-Lebensmittel nicht gefunden.")
    if target.role == "owner" or food.owner_id == target_user_id:
        raise HTTPException(409, "Der Haushaltsinhaber und der Ersteller behalten ihren Zugriff.")
    grant_food_to_user(db, food.id, target.user_id)
    db.commit()
    return Response(status_code=204)


@router.delete("/catalog-access/foods/{food_id}/members/{target_user_id}", status_code=204)
def revoke_food_access(food_id: int, target_user_id: int,
                       db: Session = Depends(get_db), user: User = Depends(current_user)):
    membership = _catalog_access_context(db, user.id)
    target = _require_catalog_member(db, membership.household_id, target_user_id)
    food = db.scalar(select(Food).where(
        Food.id == food_id,
        Food.household_id == membership.household_id,
        Food.is_active.is_(True),
        Food.is_system.is_(False),
    ))
    if food is None:
        raise HTTPException(404, "Haushalts-Lebensmittel nicht gefunden.")
    if target.role == "owner" or food.owner_id == target_user_id:
        raise HTTPException(409, "Der Haushaltsinhaber und der Ersteller behalten ihren Zugriff.")
    revoke_food_from_user(db, food.id, target.user_id)
    db.commit()
    return Response(status_code=204)


@router.put("/catalog-access/recipes/{recipe_id}/members/{target_user_id}", status_code=204)
def grant_recipe_access(recipe_id: int, target_user_id: int,
                        db: Session = Depends(get_db), user: User = Depends(current_user)):
    membership = _catalog_access_context(db, user.id)
    target = _require_catalog_member(db, membership.household_id, target_user_id)
    recipe = db.scalar(select(MealTemplate).where(
        MealTemplate.id == recipe_id,
        MealTemplate.household_id == membership.household_id,
    ))
    if recipe is None:
        raise HTTPException(404, "Haushalts-Gericht nicht gefunden.")
    if target.role == "owner" or recipe.owner_id == target_user_id:
        raise HTTPException(409, "Der Haushaltsinhaber und der Ersteller behalten ihren Zugriff.")
    grant_recipe_to_user(db, recipe.id, target.user_id)
    db.commit()
    return Response(status_code=204)


@router.delete("/catalog-access/recipes/{recipe_id}/members/{target_user_id}", status_code=204)
def revoke_recipe_access(recipe_id: int, target_user_id: int,
                         db: Session = Depends(get_db), user: User = Depends(current_user)):
    membership = _catalog_access_context(db, user.id)
    target = _require_catalog_member(db, membership.household_id, target_user_id)
    recipe = db.scalar(select(MealTemplate).where(
        MealTemplate.id == recipe_id,
        MealTemplate.household_id == membership.household_id,
    ))
    if recipe is None:
        raise HTTPException(404, "Haushalts-Gericht nicht gefunden.")
    if target.role == "owner" or recipe.owner_id == target_user_id:
        raise HTTPException(409, "Der Haushaltsinhaber und der Ersteller behalten ihren Zugriff.")
    revoke_recipe_from_user(db, recipe.id, target.user_id)
    db.commit()
    return Response(status_code=204)


@router.post("", status_code=201)
def create_household(data: HouseholdCreate, db: Session = Depends(get_db),
                     user: User = Depends(current_user)):
    if membership_for_user(db, user.id) is not None:
        raise HTTPException(409, "Du gehörst bereits einem Haushalt an.")
    name = data.name.strip()
    if not name:
        raise HTTPException(422, "Bitte gib einen Haushaltsnamen ein.")
    household = Household(name=name, owner_id=user.id)
    db.add(household)
    db.flush()
    db.add(HouseholdMember(household_id=household.id, user_id=user.id, role="owner"))
    share_owned_catalog(db, user.id, household.id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Der Haushalt konnte nicht erstellt werden. Bitte lade die Seite neu.")
    db.refresh(household)
    return household_payload(db, household, user.id)


@router.get("")
def get_household(db: Session = Depends(get_db), user: User = Depends(current_user)):
    membership = membership_for_user(db, user.id)
    incoming = db.execute(
        select(HouseholdInvitation, Household.name, User.username)
        .join(Household, Household.id == HouseholdInvitation.household_id)
        .join(User, User.id == HouseholdInvitation.invited_by_user_id)
        .where(HouseholdInvitation.invited_user_id == user.id)
        .order_by(HouseholdInvitation.created_at.desc())
    ).all()
    invitations = [
        {"id": invitation.id, "household_name": name, "invited_by": inviter,
         "created_at": invitation.created_at.isoformat()}
        for invitation, name, inviter in incoming
    ]
    if membership is None:
        return {"household": None, "invitations": invitations}
    household = db.get(Household, membership.household_id)
    if household is None:
        raise HTTPException(409, "Haushaltszuordnung ist ungültig. Bitte Administrator kontaktieren.")
    outgoing = db.execute(
        select(HouseholdInvitation, User.username)
        .join(User, User.id == HouseholdInvitation.invited_user_id)
        .where(HouseholdInvitation.household_id == household.id)
        .order_by(HouseholdInvitation.created_at.desc())
    ).all()
    return {
        "household": household_payload(db, household, user.id),
        "invitations": invitations,
        "pending_invitations": [
            {"id": invitation.id, "username": username,
             "created_at": invitation.created_at.isoformat()}
            for invitation, username in outgoing
        ],
    }


@router.post("/invitations", status_code=201)
def invite_user(data: InvitationCreate, db: Session = Depends(get_db),
                user: User = Depends(current_user)):
    membership = membership_for_user(db, user.id)
    if membership is None:
        raise HTTPException(409, "Du musst zuerst einem Haushalt angehören.")
    require_owner(db, user.id, membership.household_id)
    target = db.scalar(select(User).where(User.username == data.username.strip().lower()))
    if target is None:
        raise HTTPException(404, "Ein Benutzer mit diesem Namen wurde nicht gefunden.")
    if target.id == user.id:
        raise HTTPException(400, "Du kannst dich nicht selbst einladen.")
    if db.scalar(select(HouseholdMember.id).where(HouseholdMember.user_id == target.id)):
        raise HTTPException(409, "Dieser Benutzer gehört bereits einem Haushalt an.")
    existing = db.scalar(select(HouseholdInvitation).where(
        HouseholdInvitation.household_id == membership.household_id,
        HouseholdInvitation.invited_user_id == target.id,
    ))
    if existing is not None:
        raise HTTPException(409, "Für diesen Benutzer besteht bereits eine offene Einladung.")
    invitation = HouseholdInvitation(
        household_id=membership.household_id,
        invited_user_id=target.id,
        invited_by_user_id=user.id,
    )
    db.add(invitation)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Die Einladung konnte nicht angelegt werden. Bitte erneut laden.")
    db.refresh(invitation)
    return {"id": invitation.id, "username": target.username, "status": "pending"}


@router.post("/invitations/{invitation_id}/accept")
def accept_invitation(invitation_id: int, db: Session = Depends(get_db),
                      user: User = Depends(current_user)):
    invitation = db.scalar(select(HouseholdInvitation).where(
        HouseholdInvitation.id == invitation_id,
        HouseholdInvitation.invited_user_id == user.id,
    ))
    if invitation is None:
        raise HTTPException(404, "Einladung nicht gefunden.")
    if membership_for_user(db, user.id) is not None:
        raise HTTPException(409, "Du gehörst bereits einem Haushalt an.")
    db.add(HouseholdMember(
        household_id=invitation.household_id, user_id=user.id, role="member"
    ))
    share_owned_catalog(db, user.id, invitation.household_id)
    grant_household_catalog_to_member(db, user.id, invitation.household_id)
    db.delete(invitation)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Die Einladung wurde zwischenzeitlich bereits verwendet.")
    return {"status": "accepted"}


@router.delete("/invitations/{invitation_id}", status_code=204)
def cancel_or_decline_invitation(invitation_id: int, db: Session = Depends(get_db),
                                 user: User = Depends(current_user)):
    invitation = db.get(HouseholdInvitation, invitation_id)
    if invitation is None:
        raise HTTPException(404, "Einladung nicht gefunden.")
    membership = membership_for_user(db, user.id)
    is_owner = membership is not None and membership.household_id == invitation.household_id and membership.role == "owner"
    if user.id != invitation.invited_user_id and not is_owner:
        raise HTTPException(404, "Einladung nicht gefunden.")
    db.delete(invitation)
    db.commit()
    return Response(status_code=204)


@router.delete("/members/{member_user_id}", status_code=204)
def remove_member(member_user_id: int, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    membership = membership_for_user(db, user.id)
    if membership is None:
        raise HTTPException(404, "Haushalt nicht gefunden.")
    target = db.scalar(select(HouseholdMember).where(
        HouseholdMember.household_id == membership.household_id,
        HouseholdMember.user_id == member_user_id,
    ))
    if target is None:
        raise HTTPException(404, "Mitglied nicht gefunden.")
    if member_user_id == user.id:
        if target.role == "owner":
            raise HTTPException(409, "Der Haushaltsinhaber kann den Haushalt nicht verlassen. Eine Eigentümerübergabe wird später ergänzt.")
    else:
        require_owner(db, user.id, membership.household_id)
        if target.role == "owner":
            raise HTTPException(409, "Der Haushaltsinhaber kann nicht entfernt werden.")
    revoke_household_access_for_member(db, target.user_id, target.household_id)
    privatize_owned_catalog(db, target.user_id, target.household_id)
    db.delete(target)
    db.commit()
    return Response(status_code=204)


@router.delete("/leave", status_code=204)
def leave_household(db: Session = Depends(get_db), user: User = Depends(current_user)):
    membership = membership_for_user(db, user.id)
    if membership is None:
        raise HTTPException(404, "Haushalt nicht gefunden.")
    household = db.get(Household, membership.household_id)
    if membership.role == "owner":
        other_member = db.scalar(select(HouseholdMember).where(
            HouseholdMember.household_id == membership.household_id,
            HouseholdMember.user_id != user.id,
        ))
        if other_member is not None:
            raise HTTPException(409, "Übertrage zuerst die Admin-Rolle an ein anderes Mitglied.")
        if household is not None:
            # Preserve catalog entries as private records owned by their creators.
            db.execute(update(Food).where(Food.household_id == household.id).values(
                household_id=None, is_shared=False
            ))
            db.execute(update(MealTemplate).where(MealTemplate.household_id == household.id).values(
                household_id=None, is_shared=False
            ))
            db.delete(household)
        db.commit()
        return Response(status_code=204)
    revoke_household_access_for_member(db, user.id, membership.household_id)
    privatize_owned_catalog(db, user.id, membership.household_id)
    db.delete(membership)
    db.commit()
    return Response(status_code=204)

