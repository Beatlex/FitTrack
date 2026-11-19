from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

class Food(Base):
    __tablename__ = "foods"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    household_id: Mapped[int | None] = mapped_column(ForeignKey("households.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True)
    basis_g: Mapped[float] = mapped_column(Float, nullable=False, default=100)
    calories: Mapped[float] = mapped_column(Float, nullable=False)
    protein_g: Mapped[float] = mapped_column(Float, nullable=False)
    carbs_g: Mapped[float] = mapped_column(Float, nullable=False)
    fat_g: Mapped[float] = mapped_column(Float, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Shared by the two current household accounts; replace with explicit ACLs later.
    is_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
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


class MealTemplate(Base):
    __tablename__ = "meal_templates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    household_id: Mapped[int | None] = mapped_column(ForeignKey("households.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    meal_type: Mapped[str] = mapped_column(String(20), nullable=False)
    is_favorite: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MealTemplateIngredient(Base):
    __tablename__ = "meal_template_ingredients"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("meal_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    food_id: Mapped[int] = mapped_column(ForeignKey("foods.id"), nullable=False)
    amount_g: Mapped[float] = mapped_column(Float, nullable=False)


class MealTemplateFavorite(Base):
    __tablename__ = "meal_template_favorites"
    __table_args__ = (UniqueConstraint("user_id", "template_id", name="uq_meal_template_favorite_user_template"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("meal_templates.id", ondelete="CASCADE"), nullable=False, index=True)



class FoodAccess(Base):
    """Explicit per-user read/write grant for a catalog food."""
    __tablename__ = "food_access"
    __table_args__ = (
        UniqueConstraint("food_id", "user_id", name="uq_food_access_food_user"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    food_id: Mapped[int] = mapped_column(
        ForeignKey("foods.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RecipeAccess(Base):
    """Explicit per-user read/write grant for a saved recipe."""
    __tablename__ = "recipe_access"
    __table_args__ = (
        UniqueConstraint("recipe_id", "user_id", name="uq_recipe_access_recipe_user"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("meal_templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FoodHiddenByUser(Base):
    """Per-user hide marker; hiding never deletes the shared food."""
    __tablename__ = "food_hidden_by_user"
    __table_args__ = (
        UniqueConstraint("food_id", "user_id", name="uq_food_hidden_food_user"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    food_id: Mapped[int] = mapped_column(
        ForeignKey("foods.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hidden_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RecipeHiddenByUser(Base):
    """Per-user hide marker; hiding never deletes the shared recipe."""
    __tablename__ = "recipe_hidden_by_user"
    __table_args__ = (
        UniqueConstraint("recipe_id", "user_id", name="uq_recipe_hidden_recipe_user"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("meal_templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hidden_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RecipeIngredientAccess(Base):
    """Contextual ingredient access without general food-catalog visibility."""
    __tablename__ = "recipe_ingredient_access"
    __table_args__ = (
        UniqueConstraint("recipe_id", "food_id", "user_id", name="uq_recipe_ingredient_access_recipe_food_user"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("meal_templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    food_id: Mapped[int] = mapped_column(
        ForeignKey("foods.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
