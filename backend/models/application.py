# backend/models/application.py
# Ab application Job se bhi link ho sakti hai
# aur Company se bhi
# Job = specific opening pe apply kiya
# Company = cold email bheja bina opening ke

from sqlalchemy import (
    Column, Integer, String, Text,
    DateTime, Float, ForeignKey
)
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.database import Base


class Application(Base):
    __tablename__ = "applications"

    id                 = Column(Integer, primary_key=True, autoincrement=True)
    user_id            = Column(Integer, ForeignKey("users.id"))

    # Job ya Company — ek hoga dono nahi
    job_id             = Column(Integer, ForeignKey("jobs.id"),      nullable=True)
    company_id         = Column(Integer, ForeignKey("companies.id"), nullable=True)
    contact_id         = Column(Integer, ForeignKey("contacts.id"),  nullable=True)

    # Resume
    resume_version     = Column(String(500))
    ats_score_before   = Column(Float)
    ats_score_after    = Column(Float)

    # Email
    email_subject      = Column(String(300))
    email_body         = Column(Text)
    sent_date          = Column(DateTime)

    # Status
    status             = Column(String(100), default="pending")
    # pending
    # email_sent
    # follow_up_1_sent
    # follow_up_2_sent
    # replied_positive
    # replied_negative
    # interview_scheduled
    # ghosted

    follow_up_count    = Column(Integer, default=0)
    last_followup_date = Column(DateTime)
    created_at         = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user               = relationship("User",    back_populates="applications")
    job                = relationship("Job",     back_populates="applications")
    company            = relationship("Company", back_populates="applications")
    contact            = relationship("Contact", back_populates="applications")
    replies            = relationship("Reply",   back_populates="application")