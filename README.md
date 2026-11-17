# FitTrack
Privates Fitness- und Ernährungstracking für zwei Personen im Haushalt.

## Stack
FastAPI, SQLAlchemy, SQLite, React, TypeScript, Vite. Anmeldung mit Argon2-Passworthashes und signierten Session-Cookies.

## Windows-Entwicklung
Backend (PowerShell):
```powershell
cd backend
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:SESSION_SECRET = "hier-einen-langen-zufaelligen-wert-einsetzen"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
Frontend (zweites Terminal):
```powershell
cd frontend
npm install
npm run dev
```
Öffnen: http://localhost:5173 · API-Dokumentation: http://127.0.0.1:8000/docs

Über „Erstes Konto einrichten“ können maximal zwei Konten angelegt werden. Datenbankdatei: data/fittrack.db. Datensätze werden serverseitig dem angemeldeten Benutzer zugeordnet.

## LAN / Betrieb
Für LAN-Tests Backend und Vite auf 0.0.0.0 binden und Windows-Firewall auf das private Netzwerk beschränken. Keine Router-Portweiterleitung. Vor dauerhaftem Betrieb SESSION_SECRET ersetzen, HTTPS aktivieren (COOKIE_SECURE=true), Produktionsserver/Reverse-Proxy und Alembic-Migrationen einrichten.

## MVP-Status
Enthalten: Anmeldung, Benutzertrennung, Dashboard, manuelle Messwert- und Ernährungserfassung sowie Tages-Makros. Nächste Schritte: Alembic, Profil, vollständige Messwert-/Mahlzeitenlisten, Bearbeiten/Löschen, Statistiken und Tests.
