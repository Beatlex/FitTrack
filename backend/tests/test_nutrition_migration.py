from sqlalchemy import create_engine, text

from app.migrate_nutrition import upgrade


def test_nutrition_migration_upgrades_legacy_tables_and_is_repeatable() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        connection.execute(text(
            "CREATE TABLE foods (id INTEGER PRIMARY KEY, owner_id INTEGER NULL REFERENCES users(id), "
            "name VARCHAR(160) NOT NULL, brand VARCHAR(100), basis_g FLOAT NOT NULL DEFAULT 100, "
            "calories FLOAT NOT NULL, protein_g FLOAT NOT NULL, carbs_g FLOAT NOT NULL, fat_g FLOAT NOT NULL, "
            "is_system BOOLEAN NOT NULL DEFAULT 0, created_at DATETIME NOT NULL)"
        ))
        connection.execute(text(
            "CREATE TABLE meal_templates (id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id), "
            "name VARCHAR(160) NOT NULL, meal_type VARCHAR(20) NOT NULL, "
            "is_favorite BOOLEAN NOT NULL DEFAULT 0, created_at DATETIME NOT NULL)"
        ))
        connection.execute(text("INSERT INTO users(id) VALUES (1)"))
        connection.execute(text(
            "INSERT INTO foods(id, owner_id, name, calories, protein_g, carbs_g, fat_g, created_at) "
            "VALUES (1, 1, 'Haferflocken', 370, 13, 59, 7, CURRENT_TIMESTAMP)"
        ))
        connection.execute(text(
            "INSERT INTO meal_templates(id, owner_id, name, meal_type, is_favorite, created_at) "
            "VALUES (1, 1, 'Overnight Oats', 'breakfast', 1, CURRENT_TIMESTAMP)"
        ))

    upgrade(engine)
    upgrade(engine)

    with engine.connect() as connection:
        food_columns = {row[1] for row in connection.execute(text("PRAGMA table_info(foods)"))}
        recipe_columns = {row[1] for row in connection.execute(text("PRAGMA table_info(meal_templates)"))}
        assert {"is_active", "is_favorite", "is_shared"} <= food_columns
        assert "is_shared" in recipe_columns
        assert connection.execute(text("SELECT is_shared FROM foods WHERE id = 1")).scalar_one() == 1
        assert connection.execute(text("SELECT is_shared FROM meal_templates WHERE id = 1")).scalar_one() == 1
        assert connection.execute(text(
            "SELECT COUNT(*) FROM meal_template_favorites WHERE user_id = 1 AND template_id = 1"
        )).scalar_one() == 1

    engine.dispose()
