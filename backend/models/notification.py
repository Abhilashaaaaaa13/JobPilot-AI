# backend/models/notification.py
# User notifications for replies, follow-ups, etc.

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.database import Base


class Notification(Base):
    __tablename__ = "notifications"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    # ─────────────────────────────────────────────
    # NOTIFICATION TYPE & CONTENT
    # ─────────────────────────────────────────────
    type = Column(String(100), index=True)
    """
    Types:
    - 'reply_received'       → New email from contact
    - 'followup_due'         → Time to send follow-up
    - 'ghosting_warning'     → 7+ days no response
    - 'followup_sent'        → We sent a follow-up
    - 'reply_draft_ready'    → Auto-draft ready for approval
    """
    
    title = Column(String(300))
    message = Column(Text)
    
    # ─────────────────────────────────────────────
    # DATA & STATE
    # ─────────────────────────────────────────────
    data_json = Column(Text)
    "JSON with additional context (email IDs, etc.)"
    
    read = Column(Boolean, default=False, index=True)
    dismissed = Column(Boolean, default=False)
    
    # ─────────────────────────────────────────────
    # TIMELINE
    # ─────────────────────────────────────────────
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    read_at = Column(DateTime)
    
    # Relationship
    user = relationship("User", backref="notifications")
    
    def __repr__(self):
        return f"<Notification {self.type} - {self.title[:30]}>"