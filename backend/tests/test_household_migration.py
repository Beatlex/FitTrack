from sqlalchemy import create_engine, text

from app.migrate_household import upgrade


def test_household_migration_is_additive_and_does_not_auto_join_users() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        connection.execute(text("""CREATE TABLE foods (
            id INTEGER PRIMARY KEY, owner_id INTEGER, is_shared BOOLEAN NOT NULL DEFAULT 1
        )"""))
        connection.execute(text("""CREATE TABLE meal_templates (
            id INTEGER PRIMARY KEY, owner_id INTEGER, is_shared BOOLEAN NOT NULL DEFAULT 1
        )"""))
        connection.execute(text("INSERT INTO users(id) VALUES (1), (2), (3)"))
        connection.execute(text("INSERT INTO foods(id, owner_id, is_shared) VALUES (1, 1, 1)"))
        connection.execute(text("INSERT INTO meal_templates(id, owner_id, is_shared) VALUES (1, 1, 1)"))

    upgrade(engine)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM households")).scalar_one() == 0
        assert connection.execute(text("SELECT COUNT(*) FROM household_members")).scalar_one() == 0
        assert connection.execute(text("SELECT COUNT(*) FROM household_invitations")).scalar_one() == 0
        assert connection.execute(text("SELECT household_id FROM foods WHERE id = 1")).scalar_one() is None
        assert connection.execute(text("SELECT household_id FROM meal_templates WHERE id = 1")).scalar_one() is None

    # Re-running the migration must remain safe and must not create memberships.
    upgrade(engine)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM households")).scalar_one() == 0
        assert connection.execute(text("SELECT COUNT(*) FROM household_members")).scalar_one() == 0

    engine.dispose()
