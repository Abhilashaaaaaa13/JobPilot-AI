# backend/database.py

import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from backend.config import DATABASE_URL
from loguru import logger

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
    if "sqlite" in DATABASE_URL
    else {}
)

SessionLocal = sessionmaker(
    bind       = engine,
    autocommit = False,
    autoflush  = False,
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _sqlite_add_missing_columns():
    """
    SQLite ALTER TABLE workaround — nayi columns add karo agar exist na karein.
    Har column ke liye ek baar silently try karta hai.
    """
    if "sqlite" not in DATABASE_URL:
        return  # Postgres/MySQL ke liye alembic use karo

    # (table, column, definition)
    migrations = [
        ("companies", "user_id",          "INTEGER REFERENCES users(id)"),
        ("companies", "one_liner",        "VARCHAR(300)"),
        ("companies", "ai_hook",          "VARCHAR(500)"),
        ("companies", "recent_highlight", "VARCHAR(500)"),
    ]

    with engine.connect() as conn:
        for table, col, definition in migrations:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {definition}"))
                conn.commit()
                logger.info(f"Migration: added {table}.{col}")
            except Exception:
                # Column already exists — ignore
                pass


def init_db():
    """Initialize database with all models"""
    # Import all models here to register them with Base
    from backend.models.user import User, UserProfile
    from backend.models.company import Company
    from backend.models.contact import Contact
    from backend.models.sent_email import SentEmail
    from backend.models.notification import Notification
    from backend.models.draft_action import DraftAction
    from backend.models.application import Application
    Base.metadata.create_all(bind=engine, checkfirst=True)
    _sqlite_add_missing_columns()
    logger.info("✅ Database initialised")