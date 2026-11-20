"""Verified SQLite online backups and explicit, non-destructive restores."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import unquote, urlparse

BackupKind = Literal["daily", "weekly", "pre-migration"]
MANIFEST_VERSION = 1


class BackupError(RuntimeError):
    """Raised when a backup or restore cannot be verified safely."""


def sqlite_path(database_url: str) -> Path:
    parsed = urlparse(database_url)
    if parsed.scheme not in {"sqlite", "sqlite+pysqlite"}:
        raise BackupError("FitTrack-Backups unterstützen derzeit ausschließlich SQLite.")
    raw_path = unquote(parsed.path)
    if raw_path in {"", "/:memory:"} or database_url.endswith(":memory:"):
        raise BackupError("In-Memory-Datenbanken können nicht gesichert werden.")
    if raw_path.startswith("/") and len(raw_path) > 2 and raw_path[2] == ":":
        raw_path = raw_path[1:]
    return Path(raw_path).resolve()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def integrity_check(path: Path) -> None:
    try:
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as connection:
            result = connection.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise BackupError(f"SQLite-Integritätsprüfung fehlgeschlagen: {result[0] if result else 'keine Antwort'}")
            foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
            if foreign_key_errors:
                raise BackupError(f"SQLite-Fremdschlüsselprüfung fehlgeschlagen ({len(foreign_key_errors)} Fehler).")
    except sqlite3.Error as exc:
        raise BackupError(f"SQLite-Datei kann nicht geprüft werden: {exc}") from exc


def create_backup(
    database_url: str,
    backup_dir: Path,
    *,
    kind: BackupKind,
    schema_revision: str | None = None,
    now: datetime | None = None,
) -> Path:
    source = sqlite_path(database_url)
    if not source.is_file():
        raise BackupError(f"Quelldatenbank nicht gefunden: {source}")
    backup_dir = backup_dir.resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    stamp = timestamp.strftime("%Y%m%dT%H%M%SZ")
    if kind == "weekly":
        iso_year, iso_week, _ = timestamp.isocalendar()
        stamp = f"{iso_year}W{iso_week:02d}-{stamp}"
    destination = backup_dir / f"fittrack-{kind}-{stamp}.db"
    temporary = destination.with_suffix(".db.tmp")
    if destination.exists() or temporary.exists():
        raise BackupError(f"Backup-Ziel existiert bereits: {destination.name}")

    try:
        with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as source_db:
            with sqlite3.connect(temporary) as target_db:
                source_db.backup(target_db)
                target_db.execute("PRAGMA journal_mode=DELETE")
                target_db.commit()
        integrity_check(temporary)
        checksum = _sha256(temporary)
        os.replace(temporary, destination)
        try:
            os.chmod(destination, 0o600)
        except OSError:
            pass
        manifest = {
            "manifest_version": MANIFEST_VERSION,
            "created_at": timestamp.isoformat(),
            "kind": kind,
            "database_file": destination.name,
            "sha256": checksum,
            "schema_revision": schema_revision,
            "sqlite_integrity": "ok",
            "foreign_key_check": "ok",
        }
        manifest_path = destination.with_suffix(".json")
        manifest_tmp = manifest_path.with_suffix(".json.tmp")
        manifest_tmp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        try:
            os.chmod(manifest_tmp, 0o600)
        except OSError:
            pass
        os.replace(manifest_tmp, manifest_path)
        return destination
    except Exception:
        temporary.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        destination.with_suffix(".json").unlink(missing_ok=True)
        raise


def verify_backup(backup_path: Path) -> dict:
    backup_path = backup_path.resolve()
    manifest_path = backup_path.with_suffix(".json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BackupError("Backup-Manifest fehlt oder ist ungültig.") from exc
    if manifest.get("manifest_version") != MANIFEST_VERSION:
        raise BackupError("Nicht unterstützte Backup-Manifest-Version.")
    if manifest.get("database_file") != backup_path.name:
        raise BackupError("Manifest und Backup-Dateiname stimmen nicht überein.")
    if not backup_path.is_file() or _sha256(backup_path) != manifest.get("sha256"):
        raise BackupError("SHA-256-Prüfsumme des Backups stimmt nicht.")
    integrity_check(backup_path)
    return manifest


def restore_backup(backup_path: Path, target_path: Path, *, active_database_path: Path | None = None) -> dict:
    """Restore to a new path only; never overwrite a database or the live DB."""
    backup_path = backup_path.resolve()
    target_path = target_path.resolve()
    if active_database_path and target_path == active_database_path.resolve():
        raise BackupError("Wiederherstellung in die aktive FitTrack-Datenbank ist gesperrt.")
    if target_path == backup_path or target_path.exists():
        raise BackupError("Restore-Ziel muss ein noch nicht existierender separater Dateipfad sein.")
    manifest = verify_backup(backup_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = target_path.with_suffix(target_path.suffix + ".restore-tmp")
    try:
        with sqlite3.connect(backup_path.as_uri() + "?mode=ro", uri=True) as source_db:
            with sqlite3.connect(temporary) as target_db:
                source_db.backup(target_db)
                target_db.commit()
        integrity_check(temporary)
        os.replace(temporary, target_path)
        try:
            os.chmod(target_path, 0o600)
        except OSError:
            pass
        return manifest
    except Exception:
        temporary.unlink(missing_ok=True)
        target_path.unlink(missing_ok=True)
        raise


def prune_scheduled_backups(backup_dir: Path, *, daily_keep: int = 7, weekly_keep: int = 4) -> None:
    """Prune only scheduled snapshots; pre-migration backups are immutable."""
    daily = sorted(backup_dir.glob("fittrack-daily-*.db"), reverse=True)
    weekly = sorted(backup_dir.glob("fittrack-weekly-*.db"), reverse=True)
    for path in daily[daily_keep:] + weekly[weekly_keep:]:
        path.unlink(missing_ok=True)
        path.with_suffix(".json").unlink(missing_ok=True)


def ensure_scheduled_backups(database_url: str, backup_dir: Path, schema_revision: str | None) -> list[Path]:
    now = datetime.now(timezone.utc)
    day = now.strftime("%Y%m%d")
    iso_year, iso_week, _ = now.isocalendar()
    week = f"{iso_year}W{iso_week:02d}"
    existing = list(backup_dir.glob("fittrack-*.db")) if backup_dir.exists() else []
    created: list[Path] = []
    if not any(path.name.startswith(f"fittrack-daily-{day}") for path in existing):
        created.append(create_backup(database_url, backup_dir, kind="daily", schema_revision=schema_revision, now=now))
    if not any(path.name.startswith(f"fittrack-weekly-{week}-") for path in existing):
        created.append(create_backup(database_url, backup_dir, kind="weekly", schema_revision=schema_revision, now=now))
    prune_scheduled_backups(backup_dir)
    return created
