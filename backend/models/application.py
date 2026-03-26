# backend/models/application.py
# Cold outreach application tracker
# job_id removed — Track A dropped
# contact fields inline — no FK to contacts table
# (stateless pipeline, contacts not persisted in DB)

from sqlalchemy import (
    Column, Integer, String, Text,
    DateTime, Float, ForeignKey
)
from sqlalchemy.orm import relationship
from datetime       import datetime
from backend.database import Base


class Application(Base):
    __tablename__ = "applications"

    id       = Column(Integer, primary_key=True, autoincrement=True)
    user_id  = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Company (optional FK — company may not be in DB for stateless flow)
    company_id   = Column(Integer, ForeignKey("companies.id"), nullable=True)
    company_name = Column(String(200))   # always store name directly too

    # Contact — inline strings, no FK
    # Stateless pipeline mein contacts DB mein nahi hote
    contact_name  = Column(String(200))
    contact_role  = Column(String(100))
    contact_email = Column(String(200))

    # Resume
    resume_version   = Column(String(500))
    ats_score_before = Column(Float)
    ats_score_after  = Column(Float)

    # Email
    email_subject = Column(String(300))
    email_body    = Column(Text)
    sent_date     = Column(DateTime)

    # Status
    status = Column(String(100), default="pending")
    # pending
    # email_sent
    # follow_up_1_sent
    # follow_up_2_sent
    # replied_positive
    # replied_negative
    # interview_scheduled
    # ghosted

    follow_up_count    = Column(Integer,  default=0)
    last_followup_date = Column(DateTime, nullable=True)
    created_at         = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user    = relationship("User",    back_populates="applications")
    company = relationship("Company", back_populates="applications")
    replies = relationship("Reply",   back_populates="application")