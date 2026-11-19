"""Add nutrition tables to an existing FitTrack SQLite database.

Safe additive migration: existing user, body-measurement and food-entry rows are untouched.
Run from backend: python -m app.migrate_nutrition
"""
from sqlalchemy import text
from .database import engine

def upgrade() -> None:
    statements = (
        """CREATE TABLE IF NOT EXISTS foods (
          id INTEGER PRIMARY KEY, owner_id INTEGER NULL REFERENCES users(id),
          name VARCHAR(160) NOT NULL, brand VARCHAR(100), basis_g FLOAT NOT NULL DEFAULT 100,
          calories FLOAT NOT NULL, protein_g FLOAT NOT NULL, carbs_g FLOAT NOT NULL, fat_g FLOAT NOT NULL,
          is_system BOOLEAN NOT NULL DEFAULT 0, created_at DATETIME NOT NULL)""",
        "CREATE INDEX IF NOT EXISTS ix_foods_owner_id ON foods(owner_id)",
        "CREATE INDEX IF NOT EXISTS ix_foods_name ON foods(name)",
        """CREATE TABLE IF NOT EXISTS nutrition_goals (
          id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL UNIQUE REFERENCES users(id),
          calories FLOAT NOT NULL, protein_g FLOAT NOT NULL, carbs_g FLOAT NOT NULL, fat_g FLOAT NOT NULL,
          updated_at DATETIME NOT NULL)""",
        "CREATE INDEX IF NOT EXISTS ix_nutrition_goals_user_id ON nutrition_goals(user_id)",
        """CREATE TABLE IF NOT EXISTS meal_entries (
          id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
          food_id INTEGER NULL REFERENCES foods(id), consumed_at DATETIME NOT NULL,
          meal_type VARCHAR(20) NOT NULL, food_name VARCHAR(160) NOT NULL, amount_g FLOAT NOT NULL,
          calories FLOAT NOT NULL, protein_g FLOAT NOT NULL, carbs_g FLOAT NOT NULL, fat_g FLOAT NOT NULL)""",
        "CREATE INDEX IF NOT EXISTS ix_meal_entries_user_id ON meal_entries(user_id)",
        "CREATE INDEX IF NOT EXISTS ix_meal_entries_consumed_at ON meal_entries(consumed_at)",
        """CREATE TABLE IF NOT EXISTS meal_ingredients (
          id INTEGER PRIMARY KEY, meal_entry_id INTEGER NOT NULL REFERENCES meal_entries(id) ON DELETE CASCADE,
          food_id INTEGER NULL REFERENCES foods(id), food_name VARCHAR(160) NOT NULL, amount_g FLOAT NOT NULL,
          calories FLOAT NOT NULL, protein_g FLOAT NOT NULL, carbs_g FLOAT NOT NULL, fat_g FLOAT NOT NULL)""",
        "CREATE INDEX IF NOT EXISTS ix_meal_ingredients_meal_entry_id ON meal_ingredients(meal_entry_id)",
        """CREATE TABLE IF NOT EXISTS meal_templates (id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id), name VARCHAR(160) NOT NULL, meal_type VARCHAR(20) NOT NULL, is_favorite BOOLEAN NOT NULL DEFAULT 0, created_at DATETIME NOT NULL)""",
        "CREATE INDEX IF NOT EXISTS ix_meal_templates_owner_id ON meal_templates(owner_id)",
        """CREATE TABLE IF NOT EXISTS meal_template_ingredients (id INTEGER PRIMARY KEY, template_id INTEGER NOT NULL REFERENCES meal_templates(id) ON DELETE CASCADE, food_id INTEGER NOT NULL REFERENCES foods(id), amount_g FLOAT NOT NULL)""",
        "CREATE INDEX IF NOT EXISTS ix_meal_template_ingredients_template_id ON meal_template_ingredients(template_id)",
    )
    with engine.begin() as connection:
        columns = {row[1] for row in connection.execute(text("PRAGMA table_info(foods)"))}
        if "is_favorite" not in columns:
            connection.execute(text("ALTER TABLE foods ADD COLUMN is_favorite BOOLEAN NOT NULL DEFAULT 0"))
        for statement in statements:
            connection.execute(text(statement))

if __name__ == "__main__":
    upgrade()
    print("Nutrition schema is up to date.")
