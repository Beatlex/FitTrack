import os
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA / 'fittrack.db'}")
engine = create_engine(URL, connect_args={"check_same_thread": False} if URL.startswith("sqlite") else {})

if URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
class Base(DeclarativeBase): pass
def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()
