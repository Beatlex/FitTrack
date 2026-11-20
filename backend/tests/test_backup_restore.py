import json
import sqlite3
from pathlib import Path

import pytest

from app.backup_service import BackupError, create_backup, restore_backup, verify_backup


def create_source(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE)")
        connection.execute("CREATE TABLE measurements (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), weight REAL)")
        connection.execute("INSERT INTO users VALUES (1, 'restore-test')")
        connection.execute("INSERT INTO measurements VALUES (10, 1, 82.4)")
        connection.commit()


def logical_snapshot(path: Path) -> dict:
    with sqlite3.connect(path) as connection:
        tables = [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )]
        return {
            table: connection.execute(f'SELECT * FROM "{table}" ORDER BY 1').fetchall()
            for table in tables
        }


def test_online_backup_restore_roundtrip_to_separate_database(tmp_path: Path):
    source = tmp_path / "live.db"
    backup_dir = tmp_path / "backups"
    restored = tmp_path / "restore-test" / "restored.db"
    create_source(source)

    backup = create_backup(f"sqlite:///{source}", backup_dir, kind="pre-migration", schema_revision="0001_baseline")
    manifest = verify_backup(backup)
    assert manifest["sqlite_integrity"] == "ok"
    assert manifest["foreign_key_check"] == "ok"

    restore_backup(backup, restored, active_database_path=source)
    assert logical_snapshot(restored) == logical_snapshot(source)
    assert restored != source


def test_backup_detects_checksum_tampering(tmp_path: Path):
    source = tmp_path / "source.db"
    create_source(source)
    backup = create_backup(f"sqlite:///{source}", tmp_path / "backups", kind="daily")
    with backup.open("ab") as stream:
        stream.write(b"tampered")
    with pytest.raises(BackupError, match="SHA-256"):
        verify_backup(backup)


def test_restore_refuses_existing_or_active_database(tmp_path: Path):
    source = tmp_path / "source.db"
    create_source(source)
    backup = create_backup(f"sqlite:///{source}", tmp_path / "backups", kind="daily")
    with pytest.raises(BackupError, match="aktive"):
        restore_backup(backup, source, active_database_path=source)
    existing = tmp_path / "existing.db"
    existing.touch()
    with pytest.raises(BackupError, match="separater"):
        restore_backup(backup, existing)


def test_pre_migration_backups_are_not_pruned(tmp_path: Path):
    from datetime import datetime, timezone
    from app.backup_service import prune_scheduled_backups

    source = tmp_path / "source.db"
    create_source(source)
    for day in range(1, 10):
        create_backup(
            f"sqlite:///{source}", tmp_path / "backups", kind="daily",
            now=datetime(2026, 1, day, tzinfo=timezone.utc),
        )
    protected = create_backup(f"sqlite:///{source}", tmp_path / "backups", kind="pre-migration")
    prune_scheduled_backups(tmp_path / "backups", daily_keep=2, weekly_keep=1)
    assert protected.exists()
    assert len(list((tmp_path / "backups").glob("fittrack-daily-*.db"))) == 2
