"""Database connection and session management module.

Role: Manages SQLAlchemy database engine, session lifecycle, and dependency injection.
Data flow: Settings.DATABASE_URL -> SQLAlchemy Engine -> SessionLocal -> FastAPI route dependencies.
"""

from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from backend.app.config import get_settings

settings = get_settings()

# Configure SQLite connection arguments
connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
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
