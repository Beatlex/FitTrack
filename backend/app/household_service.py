from sqlalchemy import select
from sqlalchemy.orm import Session

from .household_models import HouseholdMember


def household_id_for_user(db: Session, user_id: int) -> int | None:
    household_id = db.scalar(
        select(HouseholdMember.household_id).where(HouseholdMember.user_id == user_id)
    )
    return household_id
