"""Add catalog optimistic-version columns and the append-only audit table.

The migration is additive and idempotent so existing local SQLite databases can
continue to start without destructive rebuilds. Alembic will replace this
bootstrap migration once the versioned migration system is introduced.
"""
from sqlalchemy import Engine, inspect, text

from .database import engine as default_engine
from .nutrition_models import CatalogAuditEvent


def upgrade(bind: Engine = default_engine) -> None:
    inspector = inspect(bind)
    with bind.begin() as connection:
        for table_name in ("foods", "meal_templates"):
            if table_name not in inspector.get_table_names():
                continue
            existing_columns = {
                column["name"] for column in inspect(connection).get_columns(table_name)
            }
            if "version" not in existing_columns:
                connection.execute(text(
                    f"ALTER TABLE {table_name} "
                    "ADD COLUMN version INTEGER NOT NULL DEFAULT 1"
                ))

        CatalogAuditEvent.__table__.create(bind=connection, checkfirst=True)
