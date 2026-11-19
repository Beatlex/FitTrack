from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

class Food(Base):
    __tablename__ = "foods"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True)
    basis_g: Mapped[float] = mapped_column(Float, nullable=False, default=100)
    calories: Mapped[float] = mapped_column(Float, nullable=False)
    protein_g: Mapped[float] = mapped_column(Float, nullable=False)
    carbs_g: Mapped[float] = mapped_column(Float, nullable=False)
    fat_g: Mapped[float] = mapped_column(Float, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class NutritionGoal(Base):
    __tablename__ = "nutrition_goals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    calories: Mapped[float] = mapped_column(Float, nullable=False)
    protein_g: Mapped[float] = mapped_column(Float, nullable=False)
    carbs_g: Mapped[float] = mapped_column(Float, nullable=False)
    fat_g: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class MealEntry(Base):
    __tablename__ = "meal_entries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    food_id: Mapped[int | None] = mapped_column(ForeignKey("foods.id"), nullable=True)
    consumed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    meal_type: Mapped[str] = mapped_column(String(20), nullable=False)
    food_name: Mapped[str] = mapped_column(String(160), nullable=False)
    amount_g: Mapped[float] = mapped_column(Float, nullable=False)
    calories: Mapped[float] = mapped_column(Float, nullable=False)
    protein_g: Mapped[float] = mapped_column(Float, nullable=False)
    carbs_g: Mapped[float] = mapped_column(Float, nullable=False)
    fat_g: Mapped[float] = mapped_column(Float, nullable=False)


class MealIngredient(Base):
    __tablename__ = "meal_ingredients"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meal_entry_id: Mapped[int] = mapped_column(ForeignKey("meal_entries.id", ondelete="CASCADE"), nullable=False, index=True)
    food_id: Mapped[int | None] = mapped_column(ForeignKey("foods.id"), nullable=True)
    food_name: Mapped[str] = mapped_column(String(160), nullable=False)
    amount_g: Mapped[float] = mapped_column(Float, nullable=False)
    calories: Mapped[float] = mapped_column(Float, nullable=False)
    protein_g: Mapped[float] = mapped_column(Float, nullable=False)
    carbs_g: Mapped[float] = mapped_column(Float, nullable=False)
    fat_g: Mapped[float] = mapped_column(Float, nullable=False)
