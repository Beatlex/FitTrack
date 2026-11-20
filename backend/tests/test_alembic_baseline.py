from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_baseline_preserves_legacy_user_data_and_is_repeatable(tmp_path: Path):
    database = tmp_path / "legacy-fittrack.db"
    engine = create_engine(f"sqlite:///{database}")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(40) NOT NULL UNIQUE, password_hash VARCHAR(255) NOT NULL)"
        ))
        connection.execute(text(
            "INSERT INTO users (id, username, password_hash) VALUES (7, 'legacy-user', 'argon-hash')"
        ))
    engine.dispose()

    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database}")

    command.upgrade(config, "head")
    command.upgrade(config, "head")

    migrated = create_engine(f"sqlite:///{database}")
    with migrated.connect() as connection:
        user = connection.execute(
            text("SELECT id, username, password_hash, timezone_name FROM users WHERE id = 7")
        ).one()
        assert tuple(user) == (7, "legacy-user", "argon-hash", None)
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0001_baseline"
        tables = set(inspect(connection).get_table_names())
        assert {"food_access", "recipe_access", "catalog_audit_events", "meal_entries"} <= tables
    migrated.dispose()
