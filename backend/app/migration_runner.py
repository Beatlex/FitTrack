"""Run Alembic and create scheduled snapshots after successful upgrades."""
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext

from .backup_service import ensure_scheduled_backups
from .database import DATA, URL, engine


BACKUP_DIR = Path(os.environ.get("FITTRACK_BACKUP_DIR", str(DATA / "backups"))).resolve()
ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def _config() -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_INI.parent / "alembic"))
    config.set_main_option("sqlalchemy.url", URL.replace("%", "%%"))
    return config


def run_database_migrations() -> None:
    if not URL.startswith("sqlite"):
        raise RuntimeError("Alembic-Backup-Automatik unterstützt derzeit ausschließlich SQLite.")
    command.upgrade(_config(), "head")
    with engine.connect() as connection:
        revision = MigrationContext.configure(connection).get_current_revision()
    ensure_scheduled_backups(URL, BACKUP_DIR, revision)
