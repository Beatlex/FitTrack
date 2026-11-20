"""Consistent HTTP conflict handling for optimistic ORM updates."""
from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError


def commit_versioned_change(db: Session, *, detail: str) -> None:
    """Commit a version-checked change or return a retryable HTTP 409."""
    try:
        db.commit()
    except StaleDataError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=detail,
        ) from exc
