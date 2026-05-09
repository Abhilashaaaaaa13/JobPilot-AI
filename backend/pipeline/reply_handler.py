# backend/pipeline/reply_handler.py - CORRECTED
from datetime import datetime, timezone
from loguru import logger
from typing import List, Dict
import json

from backend.database import SessionLocal
from backend.models.user import User
from backend.models.sent_email import SentEmail
from backend.models.notification import Notification
from backend.models.draft_action import DraftAction
from backend.config import GROQ_API_KEY, LLM_MODEL

try:
    from groq import Groq
    client = Groq(api_key=GROQ_API_KEY)
except ImportError:
    client = None
    logger.warning("Groq client not available")


class NotificationManager:
    @staticmethod
    def get_pending_notifications(user_id: int) -> List[Dict]:
        """Get all pending notifications for a user"""
        db = SessionLocal()
        try:
            notifications = db.query(Notification).filter(
                Notification.user_id == user_id,
                Notification.is_read == False
            ).all()
            
            return [
                {
                    "id": n.id,
                    "type": n.notification_type,
                    "data": json.loads(n.data) if n.data else {},
                    "created_at": n.created_at
                }
                for n in notifications
            ]
        except Exception as e:
            logger.error(f"Error getting notifications: {e}")
            return []
        finally:
            db.close()

    @staticmethod
    def create_notification(user_id: int, notif_type: str, data: Dict) -> bool:
        """Create a new notification"""
        db = SessionLocal()
        try:
            notif = Notification(
                user_id=user_id,
                notification_type=notif_type,
                title=data.get("title", ""),
                message=data.get("message", ""),
                data=json.dumps(data),
                is_read=False
            )
            db.add(notif)
            db.commit()
            logger.debug(f"Created notification: {notif_type} for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error creating notification: {e}")
            db.rollback()
            return False
        finally:
            db.close()


class DraftApprovalManager:
    @staticmethod
    def get_pending_drafts(user_id: int) -> List[Dict]:
        """Get all drafts awaiting approval"""
        db = SessionLocal()
        try:
            drafts = db.query(DraftAction).filter(
                DraftAction.user_id == user_id,
                DraftAction.status == "pending"
            ).all()
            
            return [
                {
                    "id": d.id,
                    "subject": d.subject,
                    "body": d.body,
                    "to_email": d.to_email,
                    "type": d.action_type,
                    "created_at": d.created_at
                }
                for d in drafts
            ]
        except Exception as e:
            logger.error(f"Error getting drafts: {e}")
            return []
        finally:
            db.close()


def _auto_generate_reply_draft(
    company: str,
    sender_email: str,
    original_subject: str,
    reply_text: str
) -> str:
    """Use Groq to generate a professional reply draft."""
    if not client:
        return f"Reply to {original_subject}"

    prompt = f"""
    You are helping draft a professional email reply.
    
    From: {sender_email}
    Company: {company}
    Original Subject: {original_subject}
    
    Their message:
    {reply_text[:500]}
    
    Generate a brief, professional reply (2-3 sentences max) that:
    1. Thanks them for their interest
    2. Shows you understood their message
    3. Suggests next steps (meeting, call, etc)
    
    Return ONLY the email body, no subject line.
    """
    
    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"Draft generation error: {e}")
        return f"Thank you for your reply. Let's discuss further."


def check_and_handle_all_replies() -> Dict:
    """
    Check all users' inboxes for replies.
    Auto-create drafts for responses.
    Create notifications.
    
    Called by: scheduler every 6 hours
    """
    logger.info("🔄 Checking for replies across all users...")
    
    db = SessionLocal()
    try:
        users = db.query(User).filter(User.is_active == True).all()
        total_replies = 0
        
        for user in users:
            try:
                sent = db.query(SentEmail).filter(
                    SentEmail.user_id == user.id,
                    SentEmail.replied == False
                ).all()
                
                for email in sent:
                    if email.reply_count > 0:
                        total_replies += 1
                        
                        draft = DraftAction(
                            user_id=user.id,
                            action_type="reply",
                            subject=f"Re: {email.subject}",
                            body=_auto_generate_reply_draft(
                                email.company,
                                email.to_email,
                                email.subject,
                                "Mock reply received"
                            ),
                            to_email=email.from_email,
                            status="pending"
                        )
                        db.add(draft)
                        
                        NotificationManager.create_notification(
                            user.id,
                            "reply_received",
                            {
                                "title": f"📩 Reply from {email.company}",
                                "message": email.subject[:60],
                                "company": email.company,
                                "from": email.from_email,
                                "subject": email.subject
                            }
                        )
                
                db.commit()
            
            except Exception as e:
                logger.error(f"Error processing user {user.id}: {e}")
                db.rollback()
                continue
        
        logger.info(f"✅ Reply check complete: {total_replies} replies found")
        return {"total_replies": total_replies, "success": True}
    
    finally:
        db.close()