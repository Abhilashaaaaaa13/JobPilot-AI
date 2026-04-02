# backend/models/draft_action.py
# Track user actions on auto-generated drafts

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.database import Base


class DraftAction(Base):
    __tablename__ = "draft_actions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    sent_email_id = Column(Integer, ForeignKey("sent_emails.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # ─────────────────────────────────────────────
    # ACTION TYPE
    # ─────────────────────────────────────────────
    action = Column(String(50), index=True)
    """
    Types:
    - 'approved'          → User clicked "Send"
    - 'edited_and_sent'   → User edited then sent
    - 'rejected'          → User clicked "Reject"
    - 'manual_reply'      → User opted to write manually
    """
    
    # ─────────────────────────────────────────────
    # ORIGINAL VS FINAL
    # ─────────────────────────────────────────────
    original_draft_json = Column(Text)
    "Original auto-generated draft"
    
    final_draft_json = Column(Text)
    "What user actually sent (may be edited)"
    
    user_edits = Column(Text)
    "What user changed"
    
    # ─────────────────────────────────────────────
    # TIMELINE
    # ─────────────────────────────────────────────
    draft_generated_at = Column(DateTime)
    user_action_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    sent_email = relationship("SentEmail", backref="draft_actions")
    user = relationship("User", backref="draft_actions")
    
    def __repr__(self):
        return f"<DraftAction {self.action} - {self.sent_email_id}>"