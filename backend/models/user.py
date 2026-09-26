# backend/models/user.py
# User     → authentication (email, password)
# UserProfile → job hunting data (skills, prefs, resume)
# Separation of concerns:
# auth is separate, business logic is separate
# Benefit: if OAuth is added later, only the User table changes,
# UserProfile stays the same

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, ForeignKey
)
from sqlalchemy.orm import relationship
from datetime       import datetime
from backend.database import Base


class User(Base):
    __tablename__ = "users"

    id              = Column(Integer,     primary_key=True, autoincrement=True)
    email           = Column(String(200), unique=True, nullable=False, index=True)
    hashed_password = Column(String(300), nullable=False)
    is_active       = Column(Boolean,     default=True)
    created_at      = Column(DateTime,    default=datetime.utcnow)

    # Relationships
    profile      = relationship("UserProfile", back_populates="user", uselist=False)
    applications = relationship("Application", back_populates="user")

class UserProfile(Base):
    __tablename__ = "user_profile"

    id      = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)

    # Basic info
    name     = Column(String(200))
    phone    = Column(String(20))
    linkedin = Column(String(300))
    github   = Column(String(300))

    # One liner — collected from the user during onboarding
    # Used in the cold email for "who you are in one line"
    # Example: "Final year CS student | built 3 RAG systems"
    one_liner = Column(String(300))

    # Resume
    resume_path = Column(String(500))
    # uploads/{user_id}/resume_base.pdf

    # Auto-extracted from resume (via pdf_parser.py)
    skills           = Column(Text)     # JSON string — ["Python", "LangChain"]
    experience_years = Column(Integer,  default=0)
    education        = Column(Text)

    # Job preferences — filled in from the onboarding form
    target_roles           = Column(Text)        # JSON string
    target_industries      = Column(Text)        # JSON string
    preferred_locations    = Column(Text)        # JSON string
    preferred_type         = Column(String(50))  # "internship" / "job" / "both"
    preferred_company_size = Column(String(50))  # "1-10" / "11-50" / "any"

    # Gmail — user will send emails from their own account
    gmail_address      = Column(String(200))
    gmail_app_password = Column(String(300))
    # In production, store this encrypted (cryptography library)

    # Google Sheets (optional — user can connect it)
    sheets_id = Column(String(300))

    # Settings — user can override the defaults
    followup_after_days = Column(Integer, default=4)
    max_followups       = Column(Integer, default=2)
    min_fit_score       = Column(Integer, default=50)

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # Relationship
    user = relationship("User", back_populates="profile")
    