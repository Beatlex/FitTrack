"""Baseline current FitTrack schema and safely absorb legacy bootstrap upgrades.

Revision ID: 0001_baseline
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Import all model modules before create_all so every current table is known.
    from app.database import Base
    from app import models, nutrition_models, household_models  # noqa: F401
    from app.migrate_catalog_access import upgrade as migrate_catalog_access
    from app.migrate_catalog_audit import upgrade as migrate_catalog_audit
    from app.migrate_user_timezone import upgrade as migrate_user_timezone

    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    # Existing databases may predate these additive changes. Keep the original
    # idempotent migrations as the one-time baseline compatibility layer.
    migrate_catalog_access(bind)
    migrate_catalog_audit(bind)
    migrate_user_timezone(bind)
    # Ensure the legacy users table receives the preference column even when
    # an older SQLite schema is introspected through a cached Inspector.
    user_columns = {row[1] for row in bind.exec_driver_sql("PRAGMA table_info(users)")}
    if "timezone_name" not in user_columns:
        op.add_column("users", sa.Column("timezone_name", sa.String(length=64), nullable=True))


def downgrade() -> None:
    raise RuntimeError("Die FitTrack-Baseline ist absichtlich nicht rückwärts ausführbar. Nutze ein geprüftes Backup.")
