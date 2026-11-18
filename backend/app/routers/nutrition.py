from datetime import date, datetime, time, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User
from ..nutrition_models import Food, MealEntry, MealIngredient, NutritionGoal
from ..nutrition_schemas import FoodCreate, GoalUpdate, MealCreate
from ..dependencies import current_user

router = APIRouter(prefix="/api/nutrition", tags=["nutrition"])
MACROS = ("calories", "protein_g", "carbs_g", "fat_g")

def visible_foods_statement(user_id: int):
    return select(Food).where(or_(Food.is_system.is_(True), Food.owner_id == user_id))

def food_dict(food: Food) -> dict:
    return {"id": food.id, "name": food.name, "brand": food.brand, "basis_g": food.basis_g,
            **{key: getattr(food, key) for key in MACROS}, "is_system": food.is_system}

def ingredient_dict(item: MealIngredient) -> dict:
    return {"id": item.id, "food_id": item.food_id, "food_name": item.food_name,
            "amount_g": item.amount_g, **{key: getattr(item, key) for key in MACROS}}

def meal_dict(meal: MealEntry, ingredients: list[MealIngredient] | None = None) -> dict:
    return {"id": meal.id, "food_id": meal.food_id, "food_name": meal.food_name,
            "consumed_at": meal.consumed_at.isoformat(), "meal_type": meal.meal_type,
            "amount_g": meal.amount_g, **{key: getattr(meal, key) for key in MACROS},
            "ingredients": [ingredient_dict(item) for item in (ingredients or [])]}

@router.get("/foods")
def search_foods(q: str = Query(default="", max_length=100), db: Session = Depends(get_db),
                 user: User = Depends(current_user)):
    statement = visible_foods_statement(user.id)
    if q.strip():
        statement = statement.where(Food.name.ilike(f"%{q.strip()}%"))
    return [food_dict(food) for food in db.scalars(statement.order_by(Food.name).limit(50)).all()]

@router.post("/foods", status_code=201)
def create_food(data: FoodCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    food = Food(owner_id=user.id, name=data.name, brand=data.brand, basis_g=data.basis_g,
        calories=data.calories, protein_g=data.protein_g, carbs_g=data.carbs_g, fat_g=data.fat_g)
    db.add(food)
    db.commit()
    db.refresh(food)
    return food_dict(food)

@router.get("/goals")
def get_goals(db: Session = Depends(get_db), user: User = Depends(current_user)):
    goal = db.scalar(select(NutritionGoal).where(NutritionGoal.user_id == user.id))
    return None if goal is None else {key: getattr(goal, key) for key in MACROS}

@router.put("/goals")
def set_goals(data: GoalUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    goal = db.scalar(select(NutritionGoal).where(NutritionGoal.user_id == user.id))
    if goal is None:
        goal = NutritionGoal(user_id=user.id, **data.model_dump())
        db.add(goal)
    else:
        for key, value in data.model_dump().items():
            setattr(goal, key, value)
    db.commit()
    db.refresh(goal)
    return {key: getattr(goal, key) for key in MACROS}

@router.get("/day")
def get_day(day: date = Query(default_factory=date.today), db: Session = Depends(get_db),
            user: User = Depends(current_user)):
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    end = datetime.combine(day, time.max, tzinfo=timezone.utc)
    meals = db.scalars(select(MealEntry).where(MealEntry.user_id == user.id,
        MealEntry.consumed_at >= start, MealEntry.consumed_at <= end)
        .order_by(MealEntry.consumed_at, MealEntry.id)).all()
    meal_ids = [meal.id for meal in meals]
    ingredient_rows = db.scalars(select(MealIngredient).where(
        MealIngredient.meal_entry_id.in_(meal_ids)
    ).order_by(MealIngredient.id)).all() if meal_ids else []
    by_meal: dict[int, list[MealIngredient]] = {}
    for item in ingredient_rows:
        by_meal.setdefault(item.meal_entry_id, []).append(item)
    consumed = {key: round(sum(getattr(meal, key) for meal in meals), 2) for key in MACROS}
    goal = db.scalar(select(NutritionGoal).where(NutritionGoal.user_id == user.id))
    goals = None if goal is None else {key: getattr(goal, key) for key in MACROS}
    remaining = None if goals is None else {key: round(goals[key] - consumed[key], 2) for key in MACROS}
    return {"date": day.isoformat(), "goals": goals, "consumed": consumed, "remaining": remaining,
            "entries": [meal_dict(meal, by_meal.get(meal.id, [])) for meal in meals]}

@router.post("/meals", status_code=201)
def add_meal(data: MealCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    requested = data.ingredients or []
    if data.food_id is not None and data.amount_g is not None:
        requested = [{"food_id": data.food_id, "amount_g": data.amount_g}]
    food_ids = {item.food_id for item in requested}
    foods = db.scalars(visible_foods_statement(user.id).where(Food.id.in_(food_ids))).all()
    food_by_id = {food.id: food for food in foods}
    if len(food_by_id) != len(food_ids):
        raise HTTPException(404, "Mindestens ein Lebensmittel wurde nicht gefunden.")
    resolved = []
    totals = {key: 0.0 for key in MACROS}
    total_amount = 0.0
    for item in requested:
        food = food_by_id[item.food_id]
        factor = item.amount_g / food.basis_g
        nutrients = {key: round(getattr(food, key) * factor, 2) for key in MACROS}
        total_amount += item.amount_g
        for key, value in nutrients.items():
            totals[key] += value
        resolved.append({"food_id": food.id, "food_name": food.name, "amount_g": item.amount_g, **nutrients})
    consumed_at = data.consumed_at or datetime.now(timezone.utc)
    if consumed_at.tzinfo is None:
        consumed_at = consumed_at.replace(tzinfo=timezone.utc)
    meal = MealEntry(user_id=user.id, food_id=resolved[0]["food_id"] if len(resolved) == 1 else None,
        food_name=data.meal_name, consumed_at=consumed_at, meal_type=data.meal_type,
        amount_g=round(total_amount, 2), **{key: round(value, 2) for key, value in totals.items()})
    db.add(meal)
    db.flush()
    for item in resolved:
        db.add(MealIngredient(meal_entry_id=meal.id, **item))
    db.commit()
    db.refresh(meal)
    ingredients = db.scalars(select(MealIngredient).where(MealIngredient.meal_entry_id == meal.id)).all()
    return meal_dict(meal, ingredients)

@router.delete("/meals/{entry_id}", status_code=204)
def delete_meal(entry_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    meal = db.scalar(select(MealEntry).where(MealEntry.id == entry_id, MealEntry.user_id == user.id))
    if meal is None:
        raise HTTPException(404, "Mahlzeit nicht gefunden.")
    db.execute(delete(MealIngredient).where(MealIngredient.meal_entry_id == meal.id))
    db.delete(meal)
    db.commit()
