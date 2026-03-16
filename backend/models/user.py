#y 2 tables?-> user+userprofile
#user-> authentication data (emails, password)
#userprofile -> job hunting data (skills ,preference)
#separation of concerns - auth alag, business logic alg
#fayda: kl agar oauth add kro to sirf tble change hogi user profile same rhegi

from sqlalchemy import (
    Column, Integer, String , Boolean, DateTime, Text, ForeignKey
)
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer,primary_key=True,autoincrement=True)
    email = Column(String(200), unique=True, nullable=False, index=True)
    hashed_password = Column(String(300), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    #relationship
    profile = relationship("UserProfile", back_populates="user",uselist=False)
    applications = relationship("Application", back_populates="user")

class UserProfile(Base):
    __tablename__ = "user_profile"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)

    #basic info
    name = Column(String(200))
    phone = Column(String(20))
    linkdin = Column(String(300))
    github = Column(String(300))
    #resume
    resume_path = Column(String(500))
    # uploads/{user_id}/resume_base.pdf

    # Auto extracted from resume
    skills = Column(Text)
    # JSON string — ["Python", "LangChain", "RAG"]
    # Why Text not Array?
    # SQLite mein Array type nahi hota
    # JSON string store karo, load karte waqt parse karo
    experience_years = Column(Integer, default=0)
    education = Column(Text)

    #job preferences-form s fill hoga
    target_roles = Column(Text)
    target_industries = Column(Text)
    preferred_locations = Column(Text)
    preferred_type = Column(String(50))
    preferred_company_size = Column(String(50))

    #user ko apna gmail-emails bhejn k liye
    gmail_address = Column(String(200))
    gmail_app_password = Column(String(300))
    # Why store password?
    # Har user apne Gmail se email bhejega
    # Production mein encrypt karke store karo
    # (cryptography library use karo)

    # Google Sheets
    sheets_id = Column(String(300))
    #settings-user override kr skta h defaults ko
    followup_after_days = Column(Integer, default=4)
    max_followups = Column(Integer, default=2)
    min_fit_score = Column(Integer, default=50)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    #relationshiop
    user = relationship("User", back_populates="profile")
