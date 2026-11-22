"""SQLAlchemy 2 database engine, session factory, and declarative base."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Shared SQLAlchemy 2 declarative base for all Harbor tables."""


def build_engine(database_url: str):
    """Create a SQLAlchemy engine for PostgreSQL."""
    return create_engine(
        database_url,
        pool_pre_ping=True,
        future=True,
    )


settings = get_settings()
engine = build_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=Session)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
