from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import current_user
from ..household_models import Household, HouseholdInvitation, HouseholdMember
from ..models import User
from ..nutrition_models import Food, MealTemplate, MealTemplateIngredient

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
    db.execute(update(Food).where(
        Food.owner_id == user_id, Food.household_id.is_(None), Food.is_system.is_(False)
    ).values(household_id=household_id, is_shared=True))
    db.execute(update(MealTemplate).where(
        MealTemplate.owner_id == user_id, MealTemplate.household_id.is_(None)
    ).values(household_id=household_id, is_shared=True))


def privatize_owned_catalog(db: Session, user_id: int, household_id: int) -> None:
    """Make a departing member's catalog private, retaining foods used by others' recipes."""
    used_by_other_recipe = select(MealTemplateIngredient.food_id).join(
        MealTemplate, MealTemplate.id == MealTemplateIngredient.template_id
    ).where(
        MealTemplate.household_id == household_id,
        MealTemplate.owner_id != user_id,
    )
    db.execute(update(Food).where(
        Food.owner_id == user_id, Food.household_id == household_id,
        Food.id.not_in(used_by_other_recipe),
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
    privatize_owned_catalog(db, user.id, membership.household_id)
    db.delete(membership)
    db.commit()
    return Response(status_code=204)

