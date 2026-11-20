import logging
import os
from math import isfinite
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from .database import Base, engine, get_db
from .dependencies import current_user
from .concurrency import commit_versioned_change
from .models import FoodEntry, Measurement, User
from . import nutrition_models  # Register nutrition tables before create_all
from .nutrition_models import MealEntry
from . import household_models  # Register household tables before create_all
from .schemas import MeasurementCreate, MeasurementUpdate
from .account_service import delete_account as delete_account_data
from .migrate_catalog_access import upgrade as migrate_catalog_access
from .migrate_catalog_audit import upgrade as migrate_catalog_audit
from .migrate_user_timezone import upgrade as migrate_user_timezone
from .timezones import list_available_timezones, local_day_bounds, local_today, normalize_utc, validated_timezone

Base.metadata.create_all(bind=engine)

# Additive, idempotent bootstrap migrations for existing local SQLite databases.
migrate_catalog_access()
migrate_catalog_audit()
migrate_user_timezone()
password_hasher = PasswordHash.recommended()

is_production = os.getenv("APP_ENV", "development").lower() == "production"
session_secret = os.getenv("SESSION_SECRET")
if not session_secret:
    if is_production:
        raise RuntimeError("SESSION_SECRET muss im Produktionsbetrieb gesetzt sein.")
    session_secret = "fittrack-local-development-secret-change-before-deployment"
    logging.warning("FitTrack nutzt einen lokalen Entwicklungsschlüssel. Vor einem produktiven Betrieb SESSION_SECRET setzen.")
if len(session_secret) < 32:
    raise RuntimeError("SESSION_SECRET muss mindestens 32 Zeichen lang sein.")
cookie_secure = os.getenv("COOKIE_SECURE", "false").lower() == "true"
if is_production and not cookie_secure:
    raise RuntimeError("COOKIE_SECURE=true ist im Produktionsbetrieb erforderlich.")

class TimezoneUpdateRequest(BaseModel):
    timezone_name: str = Field(min_length=1, max_length=64)


class AccountDeletionRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)
    confirmation: str = Field(min_length=3, max_length=40)


app = FastAPI(title="FitTrack API", version="0.2.0")
app.add_middleware(
    SessionMiddleware,
    secret_key=session_secret,
    same_site="lax",
    https_only=cookie_secure,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def measurement_to_dict(entry: Measurement) -> dict:
    measured_at = normalize_utc(entry.measured_at)
    fields = ("weight_kg", "waist_cm", "chest_cm", "hip_cm", "arm_cm", "thigh_cm")
    return {
        "id": entry.id,
        "measured_at": measured_at.isoformat(),
        **{field: getattr(entry, field) for field in fields},
    }


def food_to_dict(entry: FoodEntry) -> dict:
    fields = ("meal_type", "food_name", "amount_g", "calories", "protein_g", "carbs_g", "fat_g")
    return {
        "id": entry.id,
        "consumed_at": normalize_utc(entry.consumed_at).isoformat(),
        **{field: getattr(entry, field) for field in fields},
    }


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/auth/register", status_code=201)
def register(data: dict, db: Session = Depends(get_db)):
    username = str(data.get("username", "")).strip().lower()
    password = str(data.get("password", ""))
    if not 3 <= len(username) <= 40 or len(password) < 10:
        raise HTTPException(400, "Benutzername: 3–40 Zeichen; Passwort: mindestens 10 Zeichen.")
    if db.scalar(select(User).where(User.username == username)):
        raise HTTPException(409, "Benutzername bereits vergeben.")
    user = User(username=username, password_hash=password_hasher.hash(password))
    db.add(user)
    db.flush()
    # Household membership is opt-in: each account can create or join one later.
    db.commit()
    db.refresh(user)
    return {"id": user.id, "username": user.username}


@app.post("/api/auth/login")
def login(data: dict, request: Request, db: Session = Depends(get_db)):
    username = str(data.get("username", "")).strip().lower()
    user = db.scalar(select(User).where(User.username == username))
    if user is None or not password_hasher.verify(str(data.get("password", "")), user.password_hash):
        raise HTTPException(401, "Benutzername oder Passwort falsch.")
    request.session.clear()
    request.session["user_id"] = user.id
    return {"id": user.id, "username": user.username, "timezone_name": user.timezone_name}


@app.post("/api/auth/logout")
def logout(request: Request):
    request.session.clear()
    return {"status": "ok"}


@app.get("/api/auth/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "username": user.username, "timezone_name": user.timezone_name}


@app.get("/api/auth/timezones")
def get_available_timezones(user: User = Depends(current_user)):
    """Expose only identifiers supported by this backend's timezone database."""
    return list_available_timezones()


@app.patch("/api/auth/timezone")
def update_timezone(
    data: TimezoneUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    try:
        validated_timezone(data.timezone_name)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    user.timezone_name = data.timezone_name
    db.commit()
    db.refresh(user)
    return {"timezone_name": user.timezone_name}



@app.delete("/api/auth/account", status_code=204)
def delete_own_account(
    data: AccountDeletionRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if not password_hasher.verify(data.password, user.password_hash):
        raise HTTPException(403, "Das Passwort ist nicht korrekt.")
    if data.confirmation != user.username:
        raise HTTPException(400, "Bitte bestätige die Kontolöschung mit deinem Benutzernamen.")

    delete_account_data(db, user)
    commit_versioned_change(
        db, detail="Gemeinsame Katalogdaten wurden gleichzeitig geändert. Bitte lade die Seite neu und wiederhole die Kontolöschung."
    )
    request.session.clear()
    return Response(status_code=204)

@app.get("/api/measurements")
def list_measurements(db: Session = Depends(get_db), user: User = Depends(current_user)):
    entries = db.scalars(
        select(Measurement)
        .where(Measurement.user_id == user.id)
        .order_by(Measurement.measured_at.desc(), Measurement.id.desc())
    ).all()
    return [measurement_to_dict(entry) for entry in entries]


@app.post("/api/measurements", status_code=201)
def add_measurement(
    data: MeasurementCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    values = data.model_dump(exclude={"measured_at"})
    measured_at = normalize_utc(data.measured_at or datetime.now(timezone.utc))
    entry = Measurement(user_id=user.id, measured_at=measured_at, **values)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return measurement_to_dict(entry)


@app.patch("/api/measurements/{entry_id}")
def update_measurement(
    entry_id: int,
    data: MeasurementUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    entry = db.scalar(
        select(Measurement).where(
            Measurement.id == entry_id,
            Measurement.user_id == user.id,
        )
    )
    if entry is None:
        raise HTTPException(404, "Messung nicht gefunden.")

    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        if field == "measured_at" and value is None:
            raise HTTPException(400, "Das Messdatum darf nicht leer sein.")
        setattr(entry, field, normalize_utc(value) if field == "measured_at" else value)

    measurement_fields = ("weight_kg", "waist_cm", "chest_cm", "hip_cm", "arm_cm", "thigh_cm")
    if not any(getattr(entry, field) is not None for field in measurement_fields):
        raise HTTPException(400, "Eine Messung muss mindestens einen Körperwert enthalten.")

    db.commit()
    db.refresh(entry)
    return measurement_to_dict(entry)


@app.delete("/api/measurements/{entry_id}", status_code=204)
def delete_measurement(
    entry_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    entry = db.scalar(
        select(Measurement).where(
            Measurement.id == entry_id,
            Measurement.user_id == user.id,
        )
    )
    if entry is None:
        raise HTTPException(404, "Messung nicht gefunden.")
    db.delete(entry)
    db.commit()
    return Response(status_code=204)


@app.get("/api/food")
def list_food(db: Session = Depends(get_db), user: User = Depends(current_user)):
    entries = db.scalars(
        select(FoodEntry)
        .where(FoodEntry.user_id == user.id)
        .order_by(FoodEntry.consumed_at.desc())
        .limit(100)
    ).all()
    return [food_to_dict(entry) for entry in entries]


@app.post("/api/food", status_code=201)
def add_food(data: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    food_name = str(data.get("food_name", "")).strip()
    if not food_name or len(food_name) > 160:
        raise HTTPException(400, "Lebensmittelname fehlt oder ist zu lang.")
    try:
        fields = ("amount_g", "calories", "protein_g", "carbs_g", "fat_g")
        values = {field: float(data.get(field) or 0) for field in fields}
        consumed_at = normalize_utc(
            datetime.fromisoformat(data["consumed_at"])
            if data.get("consumed_at")
            else datetime.now(timezone.utc)
        )
    except (ValueError, TypeError):
        raise HTTPException(400, "Ungültige Nährwerte oder Zeit.")
    if any(not isfinite(value) or value < 0 or value > 100000 for value in values.values()):
        raise HTTPException(400, "Nährwerte müssen zwischen 0 und 100000 liegen.")
    entry = FoodEntry(
        user_id=user.id,
        food_name=food_name,
        meal_type=str(data.get("meal_type", "other"))[:20],
        consumed_at=consumed_at,
        **values,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return food_to_dict(entry)


@app.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db), user: User = Depends(current_user)):
    today = local_today(user.timezone_name)
    start, end = local_day_bounds(today, user.timezone_name)
    entries = db.scalars(
        select(MealEntry).where(
            MealEntry.user_id == user.id,
            MealEntry.consumed_at >= start,
            MealEntry.consumed_at < end,
        )
    ).all()
    latest = db.scalar(
        select(Measurement)
        .where(Measurement.user_id == user.id, Measurement.weight_kg.is_not(None))
        .order_by(Measurement.measured_at.desc(), Measurement.id.desc())
    )
    macro_fields = ("calories", "protein_g", "carbs_g", "fat_g")
    return {
        "username": user.username,
        "today": {field: sum(getattr(entry, field) for entry in entries) for field in macro_fields},
        "latest_measurement": measurement_to_dict(latest) if latest else None,
    }


from .routers.nutrition import router as nutrition_router
from .routers.household import router as household_router
app.include_router(nutrition_router)
app.include_router(household_router)
