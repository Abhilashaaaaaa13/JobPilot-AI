# backend/models/company.py
from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from backend.database import Base


class Company(Base):
    __tablename__ = "companies"

    id               = Column(Integer, primary_key=True, index=True)
    user_id          = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    name             = Column(String(200), nullable=False, index=True)
    website          = Column(String(500), default="")
    description      = Column(Text,        default="")
    one_liner        = Column(String(300), default="")
    funding          = Column(String(100), default="")
    team_size        = Column(String(50),  default="")
    location         = Column(String(150), default="")
    source           = Column(String(80),  default="")

    ai_hook          = Column(String(500), default="")
    recent_highlight = Column(String(500), default="")
    tech_stack       = Column(Text,        default="[]")

    github_url       = Column(String(300), default="")
    github_stars     = Column(Integer,     default=0)

    contacts_json    = Column(Text,        default="[]")

    feed_added_at    = Column(String(50),  default="")
    contacted_at     = Column(String(50),  nullable=True)

    # Relationships
    contacts     = relationship("Contact",     back_populates="company", cascade="all, delete-orphan")
    applications = relationship("Application", back_populates="company")  # ← add this