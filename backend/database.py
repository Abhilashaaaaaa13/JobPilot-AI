# backend/database.py

import os
from sqlalchemy import create_engine, text, inspect
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
    SQLite ALTER TABLE workaround — add new columns if they don't exist yet.
    Safe to call on every startup.
    """
    if "sqlite" not in DATABASE_URL:
        return

    migrations = [
        ("companies", "user_id",          "INTEGER REFERENCES users(id)"),
        ("companies", "one_liner",        "VARCHAR(300)"),
        ("companies", "ai_hook",          "VARCHAR(500)"),
        ("companies", "recent_highlight", "VARCHAR(500)"),
        ("companies", "github_url",       "VARCHAR(300) DEFAULT ''"),
        ("companies", "github_stars",     "INTEGER DEFAULT 0"),
        ("companies", "contacts_json",    "TEXT DEFAULT '[]'"),
        ("companies", "feed_added_at",    "VARCHAR(50) DEFAULT ''"),
        ("companies", "contacted_at",     "VARCHAR(50)"),
        ("companies", "tech_stack",       "TEXT DEFAULT '[]'"),
    ]

    inspector = inspect(engine)

    with engine.connect() as conn:
        for table, col, definition in migrations:
            try:
                existing_cols = [c["name"] for c in inspector.get_columns(table)]
                if col not in existing_cols:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {definition}"))
                    conn.commit()
                    logger.info(f"Migration: added {table}.{col}")
            except Exception as e:
                logger.warning(f"Migration skip ({table}.{col}): {e}")


def init_db():
    """Initialize database with all models"""
    from backend.models.user import User, UserProfile
    from backend.models.company import Company
    from backend.models.contact import Contact
    from backend.models.sent_email import SentEmail
    from backend.models.notification import Notification
    from backend.models.draft_action import DraftAction
    from backend.models.application import Application

    # create_all skips tables that already exist by default
    Base.metadata.create_all(bind=engine)
    _sqlite_add_missing_columns()
    logger.info("✅ Database initialised")