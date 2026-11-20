"""Write immutable audit records for shared catalog mutations.

This module deliberately does not commit: the caller records the event in the
same transaction as the catalog change so an audit row can never describe a
change that failed to persist.
"""
from sqlalchemy.orm import Session

from .models import User
from .nutrition_models import CatalogAuditEvent


def record_catalog_event(
    db: Session,
    *,
    actor: User,
    household_id: int | None,
    entity_type: str,
    entity_id: int,
    entity_name: str,
    action: str,
    changes: dict,
) -> None:
    db.add(CatalogAuditEvent(
        household_id=household_id,
        actor_user_id=actor.id,
        actor_username=actor.username,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_name=entity_name,
        action=action,
        changes=changes,
    ))
