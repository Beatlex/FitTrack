# FitTrack

Privates Fitness- und Ernährungstracking mit Haushaltsverwaltung. Mitglieder eines Haushalts teilen standardmäßig Lebensmittel und gespeicherte Gerichte; Körpermessungen, Tagesziele und protokollierte Mahlzeiten bleiben persönlich. Rezeptfavoriten sind pro Benutzer privat.

## Technologie
- Backend: Python 3.14, FastAPI, SQLAlchemy, SQLite
- Frontend: React, TypeScript, Vite
- Authentifizierung: Argon2-Passworthashes und signierte HttpOnly-Session-Cookies

## Windows-Entwicklung

### Backend – Eingabeaufforderung (CMD)
Vor einer Migration den laufenden Backend-Server stoppen und `data/fittrack.db` sichern. Die Migrationen werden einmalig nach einem Update in der angegebenen Reihenfolge ausgeführt.
```cmd
cd backend
py -3.14 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt
python -c "from app.main import app"  # erstellt das Grundschema
python -m app.migrate_nutrition
python -m app.migrate_household
python -c "import secrets; print(secrets.token_urlsafe(48))"
```
Kopiere den ausgegebenen Schlüssel und setze ihn in demselben Terminal:
```cmd
set SESSION_SECRET=HIER_DEN_GENERIERTEN_SCHLUESSEL_EINSETZEN
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Backend – PowerShell (Alternative)
```powershell
cd backend
py -3.14 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -c "from app.main import app"  # erstellt das Grundschema
python -m app.migrate_nutrition
python -m app.migrate_household
$env:SESSION_SECRET = (python -c "import secrets; print(secrets.token_urlsafe(48))")
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend – zweites Terminal
```cmd
cd frontend
npm install
npm run dev
```
Öffne http://localhost:5173. Die API-Dokumentation findest du unter http://127.0.0.1:8000/docs. Der Vite-Entwicklungsserver bindet standardmäßig nur an localhost. Für einen vorübergehenden Test in einem vertrauenswürdigen Heimnetz kannst du ihn mit `npm run dev -- --host 0.0.0.0` freigeben; wegen bekannter Schwachstellen in einem transitiven Entwicklungswerkzeug (picomatch) nicht in öffentlichen oder nicht vertrauenswürdigen Netzen verwenden.

Es können beliebig viele Benutzerkonten angelegt werden. Jeder Benutzer kann genau einem Haushalt angehören oder zunächst ohne Haushalt bleiben. Die SQLite-Datei wird lokal unter `data/fittrack.db` erzeugt und ist absichtlich von Git ausgeschlossen.

## Linux (späterer Betrieb)
Die Anwendung verwendet plattformunabhängige Python-/Node-Werkzeuge. Unter Debian/Ubuntu werden die virtuelle Umgebung mit `python3 -m venv .venv`, die Abhängigkeiten mit `pip install -r requirements.txt` und das Frontend mit `npm install` installiert. Für den Produktivbetrieb sind ein starker `SESSION_SECRET`, `APP_ENV=production`, `COOKIE_SECURE=true`, HTTPS über einen Reverse-Proxy, ein nicht privilegierter Systembenutzer und regelmäßige Backups erforderlich.

## Sicherheit und Datenmodell
- Die API leitet die Benutzer-ID ausschließlich aus der serverseitigen Session ab. Eine vom Browser gelieferte Benutzer-ID wird nicht akzeptiert.
- Lese-, Änderungs- und Löschabfragen für Körperwerte sind immer auf den angemeldeten Benutzer eingeschränkt.
- Passwörter werden mit Argon2 gehasht; Session-Cookies sind HttpOnly und SameSite=Lax.
- Der lokale Entwicklungsschlüssel ist ausschließlich für lokale Tests gedacht. Produktionsstarts ohne einen mindestens 32 Zeichen langen `SESSION_SECRET` und ohne `COOKIE_SECURE=true` werden abgebrochen.
- Haushaltsmitgliedschaften und Einladungen werden serverseitig geprüft. Lebensmittel und Gerichte gehören zu einer konkreten Haushalt-ID; Einladungen werden erst nach ausdrücklicher Annahme wirksam.
- Der Ersteller bleibt dauerhaft Admin. Er kann offene Einladungen zurückziehen und Mitglieder entfernen. Mitglieder können den Haushalt verlassen; der Admin kann den Haushalt auflösen, sobald er alleiniger Teilnehmer ist. Bei der Auflösung bleiben Lebensmittel und Gerichte als private Einträge ihrer Ersteller erhalten.
- Der Household-Migrationsschritt legt das Schema an, erstellt aber keinen Haushalt automatisch. Bestehende Benutzer bleiben unabhängig, bis sie selbst einen Haushalt erstellen oder eine Einladung annehmen. Migrationen vor dem ersten App-Start ausführen (siehe Befehle oben).
- Tagesziele, Körpermessungen und protokollierte Mahlzeiten bleiben strikt benutzerbezogen. Nährwert-Snapshots bereits protokollierter Mahlzeiten werden durch spätere Änderungen am Lebensmittel oder Rezept nicht verändert.

## Aktueller Funktionsumfang
- Anmeldung für beliebig viele getrennte Benutzer
- Dark-Dashboard mit Tagesmakros
- Körperwerte: Gewicht, Bauch, Brust, Hüfte, Arm und Oberschenkel
- Messdatum/-uhrzeit, Verlauf, Zeitraumfilter, Gewichtsdiagramm, Bearbeiten und Löschen
- Gemeinsamer Lebensmittelkatalog mit Suche, Anlegen, Bearbeiten und sicherem Archivieren
- Gemeinsame Rezeptbibliothek mit Zutaten, Mengen, Bearbeiten und Löschen
- Haushalts-Tab mit selbstständiger Erstellung, Mitgliederübersicht, Einladungen per bestehendem Benutzernamen, Annahme/Ablehnung und Entfernen/Verlassen
- Persönliche Rezeptfavoriten sowie individuelle Tagesziele und private Mahlzeitenprotokolle

## Geplante Ausbaustufen
Alembic als versioniertes Migrationssystem, Eigentümerübergabe und Haushaltsrollen, vollständige Ernährungshistorie mit Bearbeiten/Löschen, externe Lebensmitteldatenbank, Statistiken, Wochenplan, Einkaufsplan und automatische Backups.

- Beim Erstellen eines Haushalts werden bereits vorhandene eigene Lebensmittel und Gerichte des Erstellers in den Haushalt übernommen. Bei Annahme einer Einladung werden auch die bisherigen eigenen Katalogeinträge des beitretenden Benutzers geteilt. Beim Verlassen oder Entfernen werden eigene Einträge wieder privat; Lebensmittel, die von Rezepten verbleibender Mitglieder benötigt werden, bleiben für den Haushalt verfügbar.
- Die Dashboard-Übersicht zeigt die letzten 30 Gewichtsmessungen aus dem persönlichen Körperwerte-Verlauf.
