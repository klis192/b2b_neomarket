"""
Подключение к PostgreSQL и управление сессиями.
"""

import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.dialects.postgresql import UUID

from src.config import settings

engine = create_engine(settings.database_url, echo=settings.debug)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency — сессия на запрос."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
