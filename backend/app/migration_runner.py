"""Run Alembic migrations only after a verified pre-migration SQLite backup."""
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory

from .backup_service import create_backup, ensure_scheduled_backups, sqlite_path
from .database import DATA, URL, engine


BACKUP_DIR = Path(__import__("os").environ.get("FITTRACK_BACKUP_DIR", DATA / "backups")).resolve()
ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def _config() -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_INI.parent / "alembic"))
    config.set_main_option("sqlalchemy.url", URL.replace("%", "%%"))
    return config


def run_database_migrations() -> None:
    if not URL.startswith("sqlite"):
        raise RuntimeError("Alembic-Backup-Automatik unterstützt derzeit ausschließlich SQLite.")
    config = _config()
    scripts = ScriptDirectory.from_config(config)
    head = scripts.get_current_head()
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
        has_user_tables = connection.exec_driver_sql(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' LIMIT 1"
        ).first() is not None

    if has_user_tables and current != head:
        create_backup(
            URL,
            BACKUP_DIR,
            kind="pre-migration",
            schema_revision=current,
        )

    command.upgrade(config, "head")
    with engine.connect() as connection:
        revision = MigrationContext.configure(connection).get_current_revision()
    ensure_scheduled_backups(URL, BACKUP_DIR, revision)
