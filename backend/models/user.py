# backend/models/user.py
# User     → authentication (email, password)
# UserProfile → job hunting data (skills, prefs, resume)
# Separation of concerns:
# auth alag, business logic alag
# Fayda: kal OAuth add karo to sirf User table badle,
# UserProfile same rahe

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

    # One liner — onboarding mein user se lenge
    # Cold email mein "who you are in one line" ke liye use hoga
    # Example: "Final year CS student | built 3 RAG systems"
    one_liner = Column(String(300))

    # Resume
    resume_path = Column(String(500))
    # uploads/{user_id}/resume_base.pdf

    # Auto-extracted from resume (pdf_parser.py se)
    skills           = Column(Text)     # JSON string — ["Python", "LangChain"]
    experience_years = Column(Integer,  default=0)
    education        = Column(Text)

    # Job preferences — onboarding form se fill hoga
    target_roles           = Column(Text)        # JSON string
    target_industries      = Column(Text)        # JSON string
    preferred_locations    = Column(Text)        # JSON string
    preferred_type         = Column(String(50))  # "internship" / "job" / "both"
    preferred_company_size = Column(String(50))  # "1-10" / "11-50" / "any"

    # Gmail — user apne account se emails bhejega
    gmail_address      = Column(String(200))
    gmail_app_password = Column(String(300))
    # Production mein encrypt karke store karo (cryptography library)

    # Google Sheets (optional — user connect kar sakta hai)
    sheets_id = Column(String(300))

    # Settings — user override kar sakta hai defaults ko
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
    