from datetime import date, datetime, time, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User
from ..nutrition_models import Food, MealEntry, MealIngredient, MealTemplate, MealTemplateIngredient, NutritionGoal
from ..nutrition_schemas import FavoriteUpdate, FoodCreate, FoodUpdate, GoalUpdate, MealCreate, RecipeCreate, RecipeUpdate
from ..dependencies import current_user

router = APIRouter(prefix="/api/nutrition", tags=["nutrition"])
MACROS = ("calories", "protein_g", "carbs_g", "fat_g")

def visible_foods_statement(user_id: int):
    return select(Food).where(or_(Food.is_system.is_(True), Food.owner_id == user_id))

def food_dict(food: Food) -> dict:
    return {"id": food.id, "name": food.name, "brand": food.brand, "basis_g": food.basis_g,
            **{key: getattr(food, key) for key in MACROS}, "is_system": food.is_system, "is_favorite": food.is_favorite}

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
    statement = statement.where(Food.is_active.is_(True))
    if q.strip():
        statement = statement.where(Food.name.ilike(f"%{q.strip()}%"))
    return [food_dict(food) for food in db.scalars(statement.order_by(Food.is_favorite.desc(), Food.name).limit(100)).all()]

@router.post("/foods", status_code=201)
def create_food(data: FoodCreate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    duplicate = db.scalar(select(Food).where(Food.owner_id == user.id, Food.is_active.is_(True), func.lower(Food.name) == data.name.lower()))
    if duplicate is not None:
        raise HTTPException(409, "Dieses Lebensmittel existiert bereits in deiner Sammlung.")
    food = Food(owner_id=user.id, name=data.name, brand=data.brand, basis_g=data.basis_g,
        calories=data.calories, protein_g=data.protein_g, carbs_g=data.carbs_g, fat_g=data.fat_g)
    db.add(food)
    db.commit()
    db.refresh(food)
    return food_dict(food)


@router.put("/foods/{food_id}")
def update_food(food_id: int, data: FoodUpdate, db: Session = Depends(get_db),
                user: User = Depends(current_user)):
    food = db.scalar(select(Food).where(
        Food.id == food_id, Food.owner_id == user.id, Food.is_active.is_(True)
    ))
    if food is None:
        raise HTTPException(404, "Lebensmittel nicht gefunden.")
    duplicate = db.scalar(select(Food).where(
        Food.owner_id == user.id, Food.is_active.is_(True),
        func.lower(Food.name) == data.name.lower(), Food.id != food_id
    ))
    if duplicate is not None:
        raise HTTPException(409, "Ein anderes Lebensmittel mit diesem Namen existiert bereits.")
    for key, value in data.model_dump().items():
        setattr(food, key, value)
    db.commit()
    db.refresh(food)
    return food_dict(food)


@router.delete("/foods/{food_id}", status_code=200)
def archive_food(food_id: int, db: Session = Depends(get_db),
                 user: User = Depends(current_user)):
    food = db.scalar(select(Food).where(
        Food.id == food_id, Food.owner_id == user.id, Food.is_active.is_(True)
    ))
    if food is None:
        raise HTTPException(404, "Lebensmittel nicht gefunden.")
    # Soft archive preserves foreign keys and historical meal snapshots.
    food.is_active = False
    food.is_favorite = False
    db.commit()
    return {"message": "Lebensmittel archiviert."}

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
    requested = [(item.food_id, item.amount_g) for item in data.ingredients]
    if data.food_id is not None and data.amount_g is not None:
        requested = [(data.food_id, data.amount_g)]
    food_ids = {food_id for food_id, _ in requested}
    foods = db.scalars(visible_foods_statement(user.id).where(Food.id.in_(food_ids), Food.is_active.is_(True))).all()
    food_by_id = {food.id: food for food in foods}
    if len(food_by_id) != len(food_ids):
        raise HTTPException(404, "Mindestens ein Lebensmittel wurde nicht gefunden.")
    resolved = []
    totals = {key: 0.0 for key in MACROS}
    total_amount = 0.0
    for food_id, amount_g in requested:
        food = food_by_id[food_id]
        factor = amount_g / food.basis_g
        nutrients = {key: round(getattr(food, key) * factor, 2) for key in MACROS}
        total_amount += amount_g
        for key, value in nutrients.items():
            totals[key] += value
        resolved.append({"food_id": food.id, "food_name": food.name, "amount_g": amount_g, **nutrients})
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


@router.patch("/foods/{food_id}/favorite")
def set_food_favorite(food_id: int, data: FavoriteUpdate, db: Session = Depends(get_db),
                      user: User = Depends(current_user)):
    food = db.scalar(select(Food).where(Food.id == food_id, Food.owner_id == user.id, Food.is_active.is_(True)))
    if food is None:
        raise HTTPException(404, "Lebensmittel nicht gefunden.")
    food.is_favorite = data.is_favorite
    db.commit()
    db.refresh(food)
    return food_dict(food)


def recipe_dict(template: MealTemplate, db: Session, user_id: int) -> dict:
    rows = db.scalars(select(MealTemplateIngredient).where(
        MealTemplateIngredient.template_id == template.id
    ).order_by(MealTemplateIngredient.id)).all()
    food_ids = {row.food_id for row in rows}
    foods = db.scalars(visible_foods_statement(user_id).where(Food.id.in_(food_ids))).all()
    by_id = {food.id: food for food in foods}
    ingredients = []
    totals = {key: 0.0 for key in MACROS}
    for row in rows:
        food = by_id.get(row.food_id)
        if food is None:
            continue
        factor = row.amount_g / food.basis_g
        nutrients = {key: round(getattr(food, key) * factor, 2) for key in MACROS}
        for key, value in nutrients.items():
            totals[key] += value
        ingredients.append({"food_id": food.id, "food_name": food.name,
                            "amount_g": row.amount_g, **nutrients})
    return {"id": template.id, "name": template.name, "meal_type": template.meal_type,
            "is_favorite": template.is_favorite, "ingredients": ingredients,
            "amount_g": round(sum(item["amount_g"] for item in ingredients), 2),
            **{key: round(value, 2) for key, value in totals.items()}}


@router.get("/recipes")
def list_recipes(q: str = Query(default="", max_length=100), favorites_only: bool = False,
                 db: Session = Depends(get_db), user: User = Depends(current_user)):
    statement = select(MealTemplate).where(MealTemplate.owner_id == user.id)
    if q.strip():
        statement = statement.where(MealTemplate.name.ilike(f"%{q.strip()}%"))
    if favorites_only:
        statement = statement.where(MealTemplate.is_favorite.is_(True))
    templates = db.scalars(statement.order_by(
        MealTemplate.is_favorite.desc(), MealTemplate.name, MealTemplate.id
    ).limit(100)).all()
    if not templates:
        return []
    template_ids = [item.id for item in templates]
    rows = db.scalars(select(MealTemplateIngredient).where(
        MealTemplateIngredient.template_id.in_(template_ids)
    ).order_by(MealTemplateIngredient.id)).all()
    food_ids = {row.food_id for row in rows}
    foods = db.scalars(visible_foods_statement(user.id).where(Food.id.in_(food_ids))).all()
    by_food = {food.id: food for food in foods}
    by_template: dict[int, list[MealTemplateIngredient]] = {}
    for row in rows:
        by_template.setdefault(row.template_id, []).append(row)
    result = []
    for template in templates:
        ingredients = []
        totals = {key: 0.0 for key in MACROS}
        for row in by_template.get(template.id, []):
            food = by_food.get(row.food_id)
            if food is None:
                continue
            factor = row.amount_g / food.basis_g
            nutrients = {key: round(getattr(food, key) * factor, 2) for key in MACROS}
            for key, value in nutrients.items():
                totals[key] += value
            ingredients.append({"food_id": food.id, "food_name": food.name,
                                "amount_g": row.amount_g, **nutrients})
        result.append({"id": template.id, "name": template.name, "meal_type": template.meal_type,
            "is_favorite": template.is_favorite, "ingredients": ingredients,
            "amount_g": round(sum(item["amount_g"] for item in ingredients), 2),
            **{key: round(value, 2) for key, value in totals.items()}})
    return result


@router.post("/recipes", status_code=201)
def create_recipe(data: RecipeCreate, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    ids = {item.food_id for item in data.ingredients}
    foods = db.scalars(visible_foods_statement(user.id).where(
        Food.id.in_(ids), Food.is_active.is_(True)
    )).all()
    by_id = {food.id: food for food in foods}
    if len(by_id) != len(ids):
        raise HTTPException(404, "Mindestens ein aktives Lebensmittel wurde nicht gefunden.")
    existing = db.scalar(select(MealTemplate).where(
        MealTemplate.owner_id == user.id,
        func.lower(MealTemplate.name) == data.name.lower(),
    ))
    if existing is not None:
        raise HTTPException(409, "Ein Gericht mit diesem Namen existiert bereits.")
    template = MealTemplate(owner_id=user.id, name=data.name, meal_type=data.meal_type)
    db.add(template)
    db.flush()
    for item in data.ingredients:
        db.add(MealTemplateIngredient(template_id=template.id,
                                      food_id=item.food_id, amount_g=item.amount_g))
    db.commit()
    db.refresh(template)
    return recipe_dict(template, db, user.id)



@router.put("/recipes/{recipe_id}")
def update_recipe(recipe_id: int, data: RecipeUpdate, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    template = db.scalar(select(MealTemplate).where(
        MealTemplate.id == recipe_id, MealTemplate.owner_id == user.id
    ))
    if template is None:
        raise HTTPException(404, "Gericht nicht gefunden.")
    duplicate = db.scalar(select(MealTemplate).where(
        MealTemplate.owner_id == user.id,
        func.lower(MealTemplate.name) == data.name.lower(),
        MealTemplate.id != recipe_id
    ))
    if duplicate is not None:
        raise HTTPException(409, "Ein anderes Gericht mit diesem Namen existiert bereits.")
    ids = {item.food_id for item in data.ingredients}
    foods = db.scalars(visible_foods_statement(user.id).where(
        Food.id.in_(ids), Food.is_active.is_(True)
    )).all()
    if len({food.id for food in foods}) != len(ids):
        raise HTTPException(404, "Mindestens ein aktives Lebensmittel wurde nicht gefunden.")
    template.name = data.name
    template.meal_type = data.meal_type
    db.execute(delete(MealTemplateIngredient).where(
        MealTemplateIngredient.template_id == template.id
    ))
    for item in data.ingredients:
        db.add(MealTemplateIngredient(
            template_id=template.id, food_id=item.food_id, amount_g=item.amount_g
        ))
    db.commit()
    db.refresh(template)
    return recipe_dict(template, db, user.id)

@router.patch("/recipes/{recipe_id}/favorite")
def set_recipe_favorite(recipe_id: int, data: FavoriteUpdate, db: Session = Depends(get_db),
                        user: User = Depends(current_user)):
    template = db.scalar(select(MealTemplate).where(
        MealTemplate.id == recipe_id, MealTemplate.owner_id == user.id
    ))
    if template is None:
        raise HTTPException(404, "Gericht nicht gefunden.")
    template.is_favorite = data.is_favorite
    db.commit()
    db.refresh(template)
    return recipe_dict(template, db, user.id)


@router.post("/recipes/{recipe_id}/log", status_code=201)
def log_recipe(recipe_id: int, db: Session = Depends(get_db),
               user: User = Depends(current_user)):
    template = db.scalar(select(MealTemplate).where(
        MealTemplate.id == recipe_id, MealTemplate.owner_id == user.id
    ))
    if template is None:
        raise HTTPException(404, "Gericht nicht gefunden.")
    details = recipe_dict(template, db, user.id)
    if not details["ingredients"]:
        raise HTTPException(409, "Das Gericht enthält keine verfügbaren Zutaten.")
    meal = MealEntry(user_id=user.id, food_id=None, food_name=template.name,
        consumed_at=datetime.now(timezone.utc), meal_type=template.meal_type,
        amount_g=details["amount_g"],
        **{key: details[key] for key in MACROS})
    db.add(meal)
    db.flush()
    for item in details["ingredients"]:
        db.add(MealIngredient(meal_entry_id=meal.id, food_id=item["food_id"],
            food_name=item["food_name"], amount_g=item["amount_g"],
            **{key: item[key] for key in MACROS}))
    db.commit()
    db.refresh(meal)
    rows = db.scalars(select(MealIngredient).where(
        MealIngredient.meal_entry_id == meal.id
    ).order_by(MealIngredient.id)).all()
    return meal_dict(meal, rows)


@router.delete("/recipes/{recipe_id}", status_code=204)
def delete_recipe(recipe_id: int, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    template = db.scalar(select(MealTemplate).where(
        MealTemplate.id == recipe_id, MealTemplate.owner_id == user.id
    ))
    if template is None:
        raise HTTPException(404, "Gericht nicht gefunden.")
    db.execute(delete(MealTemplateIngredient).where(
        MealTemplateIngredient.template_id == template.id
    ))
    db.delete(template)
    db.commit()
    from fastapi import Response
    return Response(status_code=204)
