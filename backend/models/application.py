# backend/models/application.py
# Application — per user, per company
# Ye track karta hai ki kisne kab email bheja
# aur status kya hai
from sqlalchemy import (Column, Integer, String, Text, DateTime, Float, ForeignKey)
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.database import Base

class Application(Base):
    __tablename__= "applications"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    company_id = Column(Integer, ForeignKey("companies.id"))
    contact_id = Column(Integer, ForeignKey("contacts.id"))

    #resume
    resume_version = Column(String(500))
    # uploads/{user_id}/resumes/finflow_ai_resume.pdf
    ats_score_before = Column(Float)
    ats_score_after = Column(Float)

    #email
    email_subject = Column(String(300))
    email_body = Column(Text)
    sent_date = Column(DateTime)

    #status
    status = Column(String(100), default="pending")
    # pending           → email ready, user ne approve nahi kiya
    # email_sent        → email bhej diya
    # follow_up_1_sent  → pehla follow-up bheja
    # follow_up_2_sent  → doosra follow-up bheja
    # replied_positive  → positive reply aaya
    # replied_negative  → rejection aaya
    # interview_scheduled
    # ghosted           → max follow-ups ke baad bhi reply nahi
    follow_up_count = Column(Integer, default=0)
    last_followup_date = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow)

    #realtionships
    user = relationship("User", back_populates="applications")
    company = relationship("Company", back_populates="applications")
    contact = relationship("Contact", back_populates="applications")
    replies = relationship("Reply",back_populates="application")