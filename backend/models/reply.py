# backend/models/reply.py
# Reply — jab company ka response aata hai

from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.database import Base

class Reply(Base):
    __tablename__ = "replies"
    id = Column(Integer, primary_key=True, autoincrement=True)
    application_id = Column(Integer, ForeignKey("applications.id"))

    received_date = Column(DateTime, default=datetime.utcnow)
    reply_body = Column(Text)

    classification = Column(String(100))
    # "interview_invite"  → Schedule call karo
    # "rejection"         → Move on
    # "info_request"      → More details chahiye unhe
    # "general"           → Unclear, manually dekho
    next_action =Column(Text)
      # Groq se generated suggestion
    # "Reply with your availability for a call"
    # "Send portfolio link"

    # Relationship
    application = relationship("Application",back_populates="replies")