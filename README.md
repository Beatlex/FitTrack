# FitTrack

Privates Fitness- und Ernährungstracking für zwei Personen im Haushalt. Jeder Benutzer sieht ausschließlich die eigenen Einträge. Die Datenstruktur bleibt für eine spätere, explizite Freigabefunktion erweiterbar; aktuell gibt es keinerlei Sharing.

## Technologie
- Backend: Python 3.14, FastAPI, SQLAlchemy, SQLite
- Frontend: React, TypeScript, Vite
- Authentifizierung: Argon2-Passworthashes und signierte HttpOnly-Session-Cookies

## Windows-Entwicklung

### Backend – Eingabeaufforderung (CMD)
```cmd
cd backend
py -3.14 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt
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
$env:SESSION_SECRET = (python -c "import secrets; print(secrets.token_urlsafe(48))")
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend – zweites Terminal
```cmd
cd frontend
npm install
npm run dev
```
Öffne http://localhost:5173. Die API-Dokumentation findest du unter http://127.0.0.1:8000/docs.

Beim ersten Start können maximal zwei Konten angelegt werden. Die SQLite-Datei wird lokal unter `data/fittrack.db` erzeugt und ist absichtlich von Git ausgeschlossen.

## Linux (späterer Betrieb)
Die Anwendung verwendet plattformunabhängige Python-/Node-Werkzeuge. Unter Debian/Ubuntu werden die virtuelle Umgebung mit `python3 -m venv .venv`, die Abhängigkeiten mit `pip install -r requirements.txt` und das Frontend mit `npm install` installiert. Für den Produktivbetrieb sind ein starker `SESSION_SECRET`, `APP_ENV=production`, `COOKIE_SECURE=true`, HTTPS über einen Reverse-Proxy, ein nicht privilegierter Systembenutzer und regelmäßige Backups erforderlich.

## Sicherheit und Datenmodell
- Die API leitet die Benutzer-ID ausschließlich aus der serverseitigen Session ab. Eine vom Browser gelieferte Benutzer-ID wird nicht akzeptiert.
- Lese-, Änderungs- und Löschabfragen für Körperwerte sind immer auf den angemeldeten Benutzer eingeschränkt.
- Passwörter werden mit Argon2 gehasht; Session-Cookies sind HttpOnly und SameSite=Lax.
- Der lokale Entwicklungsschlüssel ist ausschließlich für lokale Tests gedacht. Produktionsstarts ohne einen mindestens 32 Zeichen langen `SESSION_SECRET` und ohne `COOKIE_SECURE=true` werden abgebrochen.
- Spätere Freigaben sollen über separate, widerrufbare Berechtigungsdatensätze umgesetzt werden. Die Eigentümerschaft der vorhandenen Mess- und Ernährungseinträge bleibt dabei unverändert.

## Aktueller Funktionsumfang
- Anmeldung für zwei getrennte Benutzer
- Dark-Dashboard mit Tagesmakros
- Körperwerte: Gewicht, Bauch, Brust, Hüfte, Arm und Oberschenkel
- Messdatum/-uhrzeit, Verlauf, Zeitraumfilter, Gewichtsdiagramm, Bearbeiten und Löschen
- Manuelle Lebensmitteleinträge

## Geplante Ausbaustufen
Alembic-Migrationen, Profilverwaltung, vollständige Ernährungshistorie mit Bearbeiten/Löschen, Statistiken und automatische Backups.
