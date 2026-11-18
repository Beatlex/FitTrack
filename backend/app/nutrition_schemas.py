from pydantic import BaseModel, ConfigDict, Field, field_validator

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

class GoalUpdate(Nutrients):
    pass

class MealCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    food_id: int
    amount_g: float = Field(gt=0, le=10000)
    meal_type: str = Field(pattern="^(breakfast|lunch|dinner|snack)$")
    consumed_at: str | None = None
