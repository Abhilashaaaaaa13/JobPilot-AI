# backend/models/notification.py
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.database import Base


class Notification(Base):
    __tablename__ = "notifications"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    notification_type = Column(String(100), index=True)
    title = Column(String(300))
    message = Column(Text)
    data = Column(Text)
    
    is_read = Column(Boolean, default=False, index=True)
    dismissed = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    read_at = Column(DateTime, nullable=True)
    
    user = relationship("User", backref="notifications")
    
    def __repr__(self):
        return f"<Notification {self.notification_type} - {self.title[:30]}>"