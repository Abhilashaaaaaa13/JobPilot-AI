# backend/models/job.py

from sqlalchemy import (
    Column, Integer, String,
    Text, DateTime, Boolean
)
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.database import Base


class Job(Base):
    __tablename__ = "jobs"

    id           = Column(Integer, primary_key=True, autoincrement=True)

    # Job Details
    title        = Column(String(300), nullable=False)
    company_name = Column(String(200))
    location     = Column(String(200))
    job_type     = Column(String(50))     # "internship" / "job"
    stipend      = Column(String(100))    # "15000/month" / "8 LPA"
    description  = Column(Text)
    apply_url    = Column(String(500), unique=True)

   

    # Scoring — scoring agent bharega
    fit_score    = Column(Integer, default=0)    # 0-100
    is_relevant  = Column(Boolean, default=False)

    # Status
    status       = Column(String(100), default="new")
    # new → scored → email_sent → replied → rejected

    scraped_date = Column(DateTime, default=datetime.utcnow)

   