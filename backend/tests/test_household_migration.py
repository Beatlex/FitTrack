from sqlalchemy import create_engine, text

from app.migrate_household import upgrade


def test_household_migration_assigns_existing_users_and_shared_catalog_once() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        connection.execute(text("""CREATE TABLE foods (
            id INTEGER PRIMARY KEY, owner_id INTEGER, is_shared BOOLEAN NOT NULL DEFAULT 1
        )"""))
        connection.execute(text("""CREATE TABLE meal_templates (
            id INTEGER PRIMARY KEY, owner_id INTEGER, is_shared BOOLEAN NOT NULL DEFAULT 1
        )"""))
        connection.execute(text("INSERT INTO users(id) VALUES (1), (2)"))
        connection.execute(text("INSERT INTO foods(id, owner_id, is_shared) VALUES (1, 1, 1)"))
        connection.execute(text("INSERT INTO meal_templates(id, owner_id, is_shared) VALUES (1, 1, 1)"))

    upgrade(engine)
    with engine.begin() as connection:
        household_id = connection.execute(text("SELECT id FROM households")).scalar_one()
        assert connection.execute(text("SELECT COUNT(*) FROM household_members")).scalar_one() == 2
        assert connection.execute(text("SELECT COUNT(*) FROM household_invitations")).scalar_one() == 0
        assert connection.execute(text("SELECT household_id FROM foods WHERE id = 1")).scalar_one() == household_id
        assert connection.execute(text("SELECT household_id FROM meal_templates WHERE id = 1")).scalar_one() == household_id
        connection.execute(text("DELETE FROM household_members WHERE user_id = 2"))

    # Re-running the migration must not silently re-add a user who left.
    upgrade(engine)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM household_members")).scalar_one() == 1
        assert connection.execute(text("SELECT role FROM household_members WHERE user_id = 1")).scalar_one() == "owner"

    engine.dispose()
