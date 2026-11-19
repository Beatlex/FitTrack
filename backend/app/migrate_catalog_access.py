"""Create normalized per-user catalog access and hide-marker tables.

Run from backend: python -m app.migrate_catalog_access
The migration is additive, transactional, and safe to run repeatedly.
"""
from sqlalchemy import text

from .database import engine


def upgrade(bind=engine) -> None:
    with bind.begin() as connection:
        statements = (
            """CREATE TABLE IF NOT EXISTS food_access (
                id INTEGER PRIMARY KEY,
                food_id INTEGER NOT NULL REFERENCES foods(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                granted_at DATETIME NOT NULL,
                CONSTRAINT uq_food_access_food_user UNIQUE(food_id, user_id)
            )""",
            "CREATE INDEX IF NOT EXISTS ix_food_access_food_id ON food_access(food_id)",
            "CREATE INDEX IF NOT EXISTS ix_food_access_user_id ON food_access(user_id)",
            """CREATE TABLE IF NOT EXISTS recipe_access (
                id INTEGER PRIMARY KEY,
                recipe_id INTEGER NOT NULL REFERENCES meal_templates(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                granted_at DATETIME NOT NULL,
                CONSTRAINT uq_recipe_access_recipe_user UNIQUE(recipe_id, user_id)
            )""",
            "CREATE INDEX IF NOT EXISTS ix_recipe_access_recipe_id ON recipe_access(recipe_id)",
            "CREATE INDEX IF NOT EXISTS ix_recipe_access_user_id ON recipe_access(user_id)",
            """CREATE TABLE IF NOT EXISTS food_hidden_by_user (
                id INTEGER PRIMARY KEY,
                food_id INTEGER NOT NULL REFERENCES foods(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                hidden_at DATETIME NOT NULL,
                CONSTRAINT uq_food_hidden_food_user UNIQUE(food_id, user_id)
            )""",
            "CREATE INDEX IF NOT EXISTS ix_food_hidden_by_user_food_id ON food_hidden_by_user(food_id)",
            "CREATE INDEX IF NOT EXISTS ix_food_hidden_by_user_user_id ON food_hidden_by_user(user_id)",
            """CREATE TABLE IF NOT EXISTS recipe_hidden_by_user (
                id INTEGER PRIMARY KEY,
                recipe_id INTEGER NOT NULL REFERENCES meal_templates(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                hidden_at DATETIME NOT NULL,
                CONSTRAINT uq_recipe_hidden_recipe_user UNIQUE(recipe_id, user_id)
            )""",
            "CREATE INDEX IF NOT EXISTS ix_recipe_hidden_by_user_recipe_id ON recipe_hidden_by_user(recipe_id)",
            "CREATE INDEX IF NOT EXISTS ix_recipe_hidden_by_user_user_id ON recipe_hidden_by_user(user_id)",
        )
        for statement in statements:
            connection.execute(text(statement))

        # Preserve the existing visibility contract during rollout:
        # private items remain available to their owner; household items are
        # granted to every current member plus their recorded creator.
        connection.execute(text("""
            INSERT OR IGNORE INTO food_access (food_id, user_id, granted_at)
            SELECT f.id, f.owner_id, CURRENT_TIMESTAMP
            FROM foods AS f
            WHERE f.owner_id IS NOT NULL AND f.is_system = 0
        """))
        connection.execute(text("""
            INSERT OR IGNORE INTO food_access (food_id, user_id, granted_at)
            SELECT f.id, hm.user_id, CURRENT_TIMESTAMP
            FROM foods AS f
            JOIN household_members AS hm ON hm.household_id = f.household_id
            WHERE f.household_id IS NOT NULL AND f.is_system = 0
        """))
        connection.execute(text("""
            INSERT OR IGNORE INTO recipe_access (recipe_id, user_id, granted_at)
            SELECT r.id, r.owner_id, CURRENT_TIMESTAMP
            FROM meal_templates AS r
            WHERE r.owner_id IS NOT NULL
        """))
        connection.execute(text("""
            INSERT OR IGNORE INTO recipe_access (recipe_id, user_id, granted_at)
            SELECT r.id, hm.user_id, CURRENT_TIMESTAMP
            FROM meal_templates AS r
            JOIN household_members AS hm ON hm.household_id = r.household_id
            WHERE r.household_id IS NOT NULL
        """))


if __name__ == "__main__":
    upgrade()
    print("Catalog access schema is up to date.")
