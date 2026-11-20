# FitTrack: Datenbankmigrationen, Backups und Restore

## Automatischer Startablauf

Das Backend führt beim Start `alembic upgrade head` über den zentralen Migration-Runner aus:

1. Aktuelle Alembic-Revision und erwarteten Head lesen.
2. Wenn eine vorhandene Datenbank Migrationen benötigt, vor jeder Änderung ein SQLite-Online-Backup vom Live-Datenbank-Handle erstellen.
3. Backup-Datei mit SQLite `integrity_check` und `foreign_key_check` prüfen und SHA-256-Manifest atomar schreiben.
4. Alembic-Migration ausführen.
5. Nach erfolgreicher Migration die aktuelle Schema-Revision lesen und tägliche/wöchentliche Sicherungen bei Bedarf erzeugen.

Kann das Vorab-Backup nicht erstellt oder verifiziert werden, wird die Migration nicht gestartet. Eine fehlgeschlagene Migration lässt das Vorab-Backup unangetastet.

## Bestehende Installationen / Baseline

Die Revision `0001_baseline` ist bewusst eine einmalige Kompatibilitäts-Baseline:
- `Base.metadata.create_all` ergänzt fehlende Tabellen, verändert aber keine bestehenden Tabellen destruktiv.
- Die bestehenden idempotenten Katalogzugriffs-, Audit- und Zeitzonen-Upgrades ergänzen fehlende Spalten/Tabellen.
- Vorhandene Benutzer- und Tracking-Datensätze bleiben erhalten.
- Die Revision ist nicht rückwärts ausführbar. Für eine Rückkehr wird ein geprüftes Backup in einen separaten Pfad wiederhergestellt.

Neue Schemaänderungen gehören in eigene Alembic-Revisionen. Keine bestehenden Revisionen nachträglich umschreiben, sobald sie in einer Installation verwendet wurden.

## Backup-Layout und Aufbewahrung

Standardpfad: `data/backups/`; konfigurierbar über `FITTRACK_BACKUP_DIR`.

Jede Sicherung besteht aus:
- SQLite-Datenbankdatei, erstellt über `sqlite3.Connection.backup()`
- gleichnamigem JSON-Manifest mit Manifestversion, UTC-Erstellungszeit, Typ, Datenbankdateiname, SHA-256, Alembic-Revision und Prüfstatus.

Der Scheduler legt täglich um 02:00 UTC eine Sicherung an, solange FitTrack läuft. Beim nächsten App-Start werden ausgefallene Sicherungstage nachgeholt. Automatische Rotation:
- maximal 7 tägliche Sicherungen
- maximal 4 wöchentliche Sicherungen
- `pre-migration`-Sicherungen werden niemals durch die Rotation gelöscht.

Backup-Dateien und Manifeste werden mit restriktiven Dateirechten angelegt und sind vom Git-Tracking ausgeschlossen. Sie sind derzeit nicht separat verschlüsselt. Für produktive/persönliche Daten daher ein verschlüsseltes Dateisystem und ein Backup-Ziel auf einem separaten Datenträger verwenden. Ein Backup auf derselben physischen Festplatte schützt nicht vor deren Ausfall.

## Manuelle Prüfung und Wiederherstellung

Im Backend-Verzeichnis:
```cmd
python -m alembic current
python -m alembic history
python -m app.restore_backup "..\\data\\backups\\fittrack-daily-YYYYMMDDTHHMMSSZ.db" "..\\data\\restore-test\\restored.db"
```

Der Restore:
- validiert Manifestversion und Dateinamen,
- berechnet und vergleicht SHA-256,
- prüft das Backup mit SQLite `integrity_check` und `foreign_key_check`,
- stellt über SQLite Online Backup in eine neue, nicht existierende Datei wieder her,
- prüft die wiederhergestellte Datei erneut,
- verweigert die aktive Datenbank und jedes bereits existierende Ziel.

Für eine Abnahme muss FitTrack mit einer separaten Testdatenbank gestartet werden; dort sind Tabellen, Zeilenzahlen und fachlich relevante Datensätze gegen die Quelle zu vergleichen. Der automatisierte Test `test_online_backup_restore_roundtrip_to_separate_database` führt bereits einen vollständigen SQLite-Restore aus und vergleicht alle Tabelleninhalte des Testdatensatzes.

## Tests

```cmd
cd backend
.venv\\Scripts\\activate.bat
python -m pytest -q
```

Die Tests decken Online-Backup/Restore, Datenvergleich, Integritätsprüfung, SHA-256-Manipulation, Verweigerung eines Restore in die aktive oder vorhandene Datenbank, Schutz von Pre-Migration-Backups und die wiederholbare Übernahme einer bestehenden Legacy-Datenbank in Alembic ab.
