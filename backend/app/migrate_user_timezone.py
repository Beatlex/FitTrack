"""Add nullable per-user IANA timezone preference.

Existing accounts remain unset and are initialized from the browser on their
next authenticated session. UTC remains the fallback until then.
"""
from contextlib import nullcontext

from sqlalchemy import Connection, Engine, inspect, text

from .database import engine as default_engine


def upgrade(bind: Engine | Connection = default_engine) -> None:
    inspector = inspect(bind)
    if "users" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "timezone_name" not in columns:
        transaction = bind.begin() if isinstance(bind, Engine) else nullcontext(bind)
        with transaction as connection:
            connection.execute(text(
                "ALTER TABLE users ADD COLUMN timezone_name VARCHAR(64)"
            ))


if __name__ == "__main__":
    upgrade()
    print("User timezone schema is up to date.")
