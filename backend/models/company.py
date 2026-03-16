# backend/models/company.py
# Company table — shared across all users
# Why shared?
# Agar 100 users hain aur sab YC companies scrape karein
# toh same data 100 baar store kyun karein?
# Ek baar scrape, sab use karein.

from sqlalchemy import Column, Integer, String,Text,DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.database import Base

class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    website = Column(String(300), unique=True)
    description =  Column(Text)
    tech_stack = Column(Text)
    funding = Column(String(100))
    team_size = Column(String(50))
    location = Column(String(200))
    source = Column(String(100))

    #research agent ka output
    ai_related = Column(Boolean, default=False)
    recent_news = Column(Text)
    company_summary = Column(Text)

    scraped_date = Column(DateTime, default=datetime.utcnow)

    #relationships
    contacts = relationship("Contact", back_populates="company")
    applications = relationship("Application", back_populates="company")
