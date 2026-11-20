from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

class Nutrients(BaseModel):
    model_config = ConfigDict(extra="forbid")
    calories: float = Field(ge=0, le=10000)
    protein_g: float = Field(ge=0, le=1000)
    carbs_g: float = Field(ge=0, le=1000)
    fat_g: float = Field(ge=0, le=1000)

class FoodCreate(Nutrients):
    name: str = Field(min_length=1, max_length=160)
    brand: str | None = Field(default=None, max_length=100)
    basis_g: float = Field(default=100, gt=0, le=10000)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Lebensmittelname darf nicht leer sein.")
        return value

class FoodUpdate(FoodCreate):
    version: int = Field(default=1, gt=0)

class GoalUpdate(Nutrients):
    pass

class MealIngredientInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    food_id: int = Field(gt=0)
    amount_g: float = Field(gt=0, le=10000)

class MealCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    meal_name: str = Field(default="Mahlzeit", min_length=1, max_length=160)
    meal_type: str = Field(pattern="^(breakfast|lunch|dinner|snack)$")
    consumed_at: datetime | None = None
    ingredients: list[MealIngredientInput] = Field(default_factory=list, max_length=30)
    food_id: int | None = Field(default=None, gt=0)
    amount_g: float | None = Field(default=None, gt=0, le=10000)

    @field_validator("meal_name")
    @classmethod
    def clean_meal_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Mahlzeitenname darf nicht leer sein.")
        return value

    @model_validator(mode="after")
    def require_ingredients(self):
        has_ingredients = bool(self.ingredients)
        has_legacy_food = self.food_id is not None and self.amount_g is not None
        if has_ingredients == has_legacy_food:
            raise ValueError("Bitte Zutaten angeben oder genau ein Lebensmittel auswählen.")
        if (self.food_id is None) != (self.amount_g is None):
            raise ValueError("Lebensmittel und Menge müssen gemeinsam angegeben werden.")
        return self

class RecipeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=160)
    meal_type: str = Field(pattern="^(breakfast|lunch|dinner|snack)$")
    ingredients: list[MealIngredientInput] = Field(min_length=1, max_length=30)

    @field_validator("name")
    @classmethod
    def clean_recipe_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Gerichtname darf nicht leer sein.")
        return value


class RecipeUpdate(RecipeCreate):
    version: int = Field(default=1, gt=0)


class FavoriteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_favorite: bool
