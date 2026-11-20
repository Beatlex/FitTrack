"""Daily UTC backup scheduler for the single-process local FitTrack server."""
import logging
from datetime import timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from alembic.migration import MigrationContext

from .backup_service import ensure_scheduled_backups
from .database import URL, engine
from .migration_runner import BACKUP_DIR

logger = logging.getLogger(__name__)
_scheduler = BackgroundScheduler(timezone=timezone.utc)


def _run_scheduled_backup() -> None:
    try:
        with engine.connect() as connection:
            revision = MigrationContext.configure(connection).get_current_revision()
        created = ensure_scheduled_backups(URL, BACKUP_DIR, revision)
        if created:
            logger.info("FitTrack-Backups erstellt: %s", ", ".join(path.name for path in created))
    except Exception:
        logger.exception("Geplante FitTrack-Datenbanksicherung fehlgeschlagen.")


def start_backup_scheduler() -> None:
    if _scheduler.running:
        return
    _scheduler.add_job(
        _run_scheduled_backup,
        CronTrigger(hour=2, minute=0, timezone=timezone.utc),
        id="fittrack-daily-backup",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    _scheduler.start()


def stop_backup_scheduler() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=True)
