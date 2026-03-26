# backend/models/company.py
# Sirf cold email targets
# Job openings yahan nahi hain

from sqlalchemy import (
    Column, Integer, String,
    Text, DateTime, Boolean, ForeignKey
)
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.database import Base


class Company(Base):
    __tablename__ = "companies"

    id            = Column(Integer, primary_key=True, autoincrement=True)

    # User ownership (feed_to_db ke liye zaroori)
    user_id       = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # Basic Info
    name          = Column(String(200), nullable=False)
    website       = Column(String(300), unique=True)
    one_liner     = Column(String(300))  # Short tagline
    description   = Column(Text)         # What they build
    tech_stack    = Column(Text)         # JSON string
    funding       = Column(String(100))  # "YC S23", "Series A"
    team_size     = Column(String(50))   # "1-10", "11-50"
    location      = Column(String(200))
    source        = Column(String(100))  # "yc_api", "producthunt", "feed"

    # Research Agent bharega
    ai_related       = Column(Boolean, default=False)
    recent_news      = Column(Text)
    recent_highlight = Column(String(500))  # feed_to_db ke liye
    ai_hook          = Column(String(500))  # feed_to_db ke liye
    company_summary  = Column(Text)         # Groq se generated
    research_done    = Column(Boolean, default=False)

    scraped_date  = Column(DateTime, default=datetime.utcnow)

    # Relationships
    contacts      = relationship("Contact",     back_populates="company")
    applications  = relationship("Application", back_populates="company")