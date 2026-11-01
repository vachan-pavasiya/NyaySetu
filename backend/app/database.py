"""Database connection and session management module.

Role: Manages SQLAlchemy database engine, session lifecycle, and dependency injection.
Data flow: Settings.DATABASE_URL -> SQLAlchemy Engine -> SessionLocal -> FastAPI route dependencies.
Supports:
  - SQLite on local or persistent disk paths (e.g. Render mount /data/compliance_radar.db)
  - PostgreSQL / Supabase / Neon / Railway connection strings
"""

from typing import Generator
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from backend.app.config import get_settings

settings = get_settings()

db_url = settings.DATABASE_URL.strip()

# PostgreSQL URL normalization: render / heroku use postgres:// which SQLAlchemy 2.0 rejects
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

# Configure SQLite vs PostgreSQL parameters
if db_url.startswith("sqlite"):
    # Ensure parent directory exists for persistent disk mount (e.g. /data/compliance_radar.db)
    raw_path = db_url.replace("sqlite:///", "")
    if raw_path and not raw_path.startswith(":memory:"):
        db_file = Path(raw_path)
        if db_file.parent and not db_file.parent.exists():
            db_file.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        echo=False,
    )
else:
    # PostgreSQL / other relational engines
    engine = create_engine(
        db_url,
        pool_pre_ping=True,
        pool_recycle=300,
        echo=False,
    )

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Yield a database session and safely close it after request completion."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
