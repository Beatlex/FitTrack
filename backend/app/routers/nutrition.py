from datetime import date, datetime, time, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User
from ..nutrition_models import Food, MealEntry, NutritionGoal
from ..nutrition_schemas import FoodCreate, GoalUpdate, MealCreate
from ..dependencies import current_user

router = APIRouter(prefix="/api/nutrition", tags=["nutrition"])
MACROS = ("calories", "protein_g", "carbs_g", "fat_g")

def food_dict(food: Food) -> dict:
    return {"id": food.id, "name": food.name, "brand": food.brand, "basis_g": food.basis_g,
            **{key: getattr(food, key) for key in MACROS}, "is_system": food.is_system}

def meal_dict(meal: MealEntry) -> dict:
    return {"id": meal.id, "food_id": meal.food_id, "food_name": meal.food_name,
            "consumed_at": meal.consumed_at.isoformat(), "meal_type": meal.meal_type,
            "amount_g": meal.amount_g, **{key: getattr(meal, key) for key in MACROS}}

@router.get("/foods")
def search_foods(q: str = Query(default="", max_length=100), db: Session = Depends(get_db),
                 user: User = Depends(current_user)):
    statement = select(Food).where(or_(Food.is_system.is_(True), Food.owner_id == user.id))
    if q.strip():
        statement = statement.where(Food.name.ilike(f"%{q.strip()}%"))
    return [food_dict(f) for f in db.scalars(statement.order_by(Food.name).limit(50)).all()]

@router.post("/foods", status_code=201)
def create_food(data: FoodCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    food = Food(owner_id=user.id, name=data.name, brand=data.brand, basis_g=data.basis_g,
        calories=data.calories, protein_g=data.protein_g, carbs_g=data.carbs_g, fat_g=data.fat_g)
    db.add(food); db.commit(); db.refresh(food)
    return food_dict(food)

@router.get("/goals")
def get_goals(db: Session = Depends(get_db), user: User = Depends(current_user)):
    goal = db.scalar(select(NutritionGoal).where(NutritionGoal.user_id == user.id))
    return None if goal is None else {key: getattr(goal, key) for key in MACROS}

@router.put("/goals")
def set_goals(data: GoalUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    goal = db.scalar(select(NutritionGoal).where(NutritionGoal.user_id == user.id))
    if goal is None:
        goal = NutritionGoal(user_id=user.id, **data.model_dump()); db.add(goal)
    else:
        for key, value in data.model_dump().items(): setattr(goal, key, value)
    db.commit(); db.refresh(goal)
    return {key: getattr(goal, key) for key in MACROS}

@router.get("/day")
def get_day(day: date = Query(default_factory=date.today), db: Session = Depends(get_db),
            user: User = Depends(current_user)):
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    end = datetime.combine(day, time.max, tzinfo=timezone.utc)
    meals = db.scalars(select(MealEntry).where(MealEntry.user_id == user.id,
        MealEntry.consumed_at >= start, MealEntry.consumed_at <= end)
        .order_by(MealEntry.consumed_at, MealEntry.id)).all()
    consumed = {key: round(sum(getattr(m, key) for m in meals), 2) for key in MACROS}
    goal = db.scalar(select(NutritionGoal).where(NutritionGoal.user_id == user.id))
    goals = None if goal is None else {key: getattr(goal, key) for key in MACROS}
    remaining = None if goals is None else {key: round(goals[key] - consumed[key], 2) for key in MACROS}
    return {"date": day.isoformat(), "goals": goals, "consumed": consumed, "remaining": remaining,
            "entries": [meal_dict(m) for m in meals]}

@router.post("/meals", status_code=201)
def add_meal(data: MealCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    food = db.scalar(select(Food).where(Food.id == data.food_id,
        or_(Food.is_system.is_(True), Food.owner_id == user.id)))
    if food is None: raise HTTPException(404, "Lebensmittel nicht gefunden.")
    factor = data.amount_g / food.basis_g
    consumed_at = datetime.fromisoformat(data.consumed_at) if data.consumed_at else datetime.now(timezone.utc)
    if consumed_at.tzinfo is None: consumed_at = consumed_at.replace(tzinfo=timezone.utc)
    meal = MealEntry(user_id=user.id, food_id=food.id, food_name=food.name, consumed_at=consumed_at,
        meal_type=data.meal_type, amount_g=data.amount_g,
        **{key: round(getattr(food, key) * factor, 2) for key in MACROS})
    db.add(meal); db.commit(); db.refresh(meal)
    return meal_dict(meal)

@router.delete("/meals/{entry_id}", status_code=204)
def delete_meal(entry_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    meal = db.scalar(select(MealEntry).where(MealEntry.id == entry_id, MealEntry.user_id == user.id))
    if meal is None: raise HTTPException(404, "Mahlzeit nicht gefunden.")
    db.delete(meal); db.commit()
