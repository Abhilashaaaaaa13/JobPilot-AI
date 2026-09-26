# backend/models/draft_action.py
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.database import Base


class DraftAction(Base):
    __tablename__ = "draft_actions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    action_type = Column(String(50))
    subject = Column(String(300))
    body = Column(Text)
    to_email = Column(String(200))

    status = Column(String(50), default="pending", index=True)

    # Which sent email this action applies to, and what the user actually did
    # (approved / edited_and_sent / rejected / manual_reply) — used by the
    # Replies & Drafts history tab.
    sent_email_id = Column(Integer, ForeignKey("sent_emails.id"), nullable=True, index=True)
    action = Column(String(50), nullable=True)
    user_action_at = Column(DateTime, default=datetime.utcnow, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    approved_at = Column(DateTime, nullable=True)
    
    user = relationship("User", backref="draft_actions")
    
    def __repr__(self):
        return f"<DraftAction {self.action_type} - {self.status}>"