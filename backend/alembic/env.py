from logging.config import fileConfig

import os
from pathlib import Path

from alembic import context
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import engine_from_config, pool

from app.backup_service import create_backup
from app.database import Base, DATA
from app import models, nutrition_models, household_models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"check_same_thread": False},
    )
    try:
        # Keep backup preflight on its own connection. Its metadata reads must
        # not leave an implicit SQLite transaction open for Alembic's DDL.
        with connectable.connect() as preflight:
            current = MigrationContext.configure(preflight).get_current_revision()
            head = ScriptDirectory.from_config(config).get_current_head()
            has_user_tables = preflight.exec_driver_sql(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' LIMIT 1"
            ).first() is not None
            if has_user_tables and current != head:
                database_url = config.get_main_option("sqlalchemy.url")
                backup_dir = Path(
                    os.environ.get("FITTRACK_BACKUP_DIR", str(DATA / "backups"))
                ).resolve()
                create_backup(
                    database_url,
                    backup_dir,
                    kind="pre-migration",
                    schema_revision=current,
                )

        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
                render_as_batch=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
