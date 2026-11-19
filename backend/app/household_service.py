from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .household_models import HouseholdMember


def household_id_for_user(db: Session, user_id: int) -> int:
    household_id = db.scalar(
        select(HouseholdMember.household_id).where(HouseholdMember.user_id == user_id)
    )
    if household_id is None:
        raise HTTPException(409, "Du bist noch keinem Haushalt zugeordnet. Bitte nimm zuerst eine Einladung an.")
    return household_id
