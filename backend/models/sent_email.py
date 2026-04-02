# backend/models/sent_email.py
# Track cold outreach emails with full lifecycle

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.database import Base


class SentEmail(Base):
    __tablename__ = "sent_emails"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # ─────────────────────────────────────────────
    # EMAIL DETAILS
    # ─────────────────────────────────────────────
    to_email = Column(String(200), nullable=False, index=True)
    company = Column(String(200))
    contact_name = Column(String(200))
    subject = Column(String(500))
    body = Column(Text)
    
    # ─────────────────────────────────────────────
    # GMAIL INTEGRATION
    # ─────────────────────────────────────────────
    gmail_message_id = Column(String(500))
    "Gmail's unique message ID for tracking"
    
    # ─────────────────────────────────────────────
    # TIMELINE
    # ─────────────────────────────────────────────
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # ─────────────────────────────────────────────
    # REPLY TRACKING
    # ─────────────────────────────────────────────
    replied = Column(Boolean, default=False, index=True)
    reply_at = Column(DateTime)
    reply_body = Column(Text)
    reply_gmail_message_id = Column(String(500))
    reply_subject = Column(String(500))
    
    # ─────────────────────────────────────────────
    # AUTO-DRAFT SYSTEM
    # ─────────────────────────────────────────────
    auto_draft_json = Column(Text)
    "JSON: {subject, body, generated_at, model}"
    
    reply_notified = Column(Boolean, default=False)
    "Did we send user a notification about this reply?"
    
    auto_draft_approved = Column(Boolean, default=False)
    "User approved & sent the auto-generated reply?"
    
    # ─────────────────────────────────────────────
    # FOLLOW-UP TRACKING
    # ─────────────────────────────────────────────
    followup_count = Column(Integer, default=0)
    last_followup_at = Column(DateTime)
    
    # ─────────────────────────────────────────────
    # STATUS & METADATA
    # ─────────────────────────────────────────────
    status = Column(String(50), index=True)
    """
    Possible values:
    - 'sent'                  → Initial send
    - 'replied'               → Reply received
    - 'reply_sent'            → We replied back
    - 'followup_sent'         → Follow-up email sent
    - 'manual_reply_needed'   → User rejected auto-draft
    - 'ghosted'               → 7+ days no response
    """
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    user = relationship("User", backref="sent_emails")
    
    def __repr__(self):
        return f"<SentEmail {self.to_email} - {self.status}>"