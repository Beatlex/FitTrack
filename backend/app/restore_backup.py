"""CLI: verify and restore a backup into a separate, new SQLite database."""
import argparse
from pathlib import Path

from .backup_service import restore_backup, sqlite_path
from .database import URL


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup", type=Path, help="Backup-Datei (.db) mit zugehörigem Manifest (.json)")
    parser.add_argument("target", type=Path, help="Neuer, separater Pfad für die wiederhergestellte Datenbank")
    args = parser.parse_args()
    manifest = restore_backup(args.backup, args.target, active_database_path=sqlite_path(URL))
    print(f"Restore erfolgreich: {args.target}")
    print(f"Backup-Zeitpunkt: {manifest['created_at']}")
    print(f"Schema-Version: {manifest.get('schema_revision') or 'unversioniert'}")


if __name__ == "__main__":
    main()
