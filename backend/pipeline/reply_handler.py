# backend/pipeline/reply_handler.py
# ═══════════════════════════════════════════════════════════════════════════════
# REPLY DETECTION & AUTO-DRAFT SYSTEM (LangGraph + Groq)
# ═══════════════════════════════════════════════════════════════════════════════
# Features:
# - Detects replies every 6 hours (scheduler runs automatically)
# - Auto-generates draft replies using Groq
# - Stores in DB with user approval flow
# - Integrates with existing LangGraph architecture
# ═══════════════════════════════════════════════════════════════════════════════

import os
import json
import imaplib
import email
import re
from email.header import decode_header
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

from backend.agents.email_generator import call_groq, _clean_email_address


# ─────────────────────────────────────────────
# REPLY DETECTION
# ─────────────────────────────────────────────

class ReplyDetector:
    """
    Gmail IMAP detector for cold outreach replies.
    NO Claude API — uses Groq instead.
    """
    
    def __init__(self, user_id: int):
        self.user_id = user_id
    
    def get_gmail_creds(self) -> Dict:
        """Fetch Gmail credentials from DB"""
        try:
            from backend.database import SessionLocal
            from backend.models.user import UserProfile
            
            db = SessionLocal()
            profile = db.query(UserProfile).filter(
                UserProfile.user_id == self.user_id
            ).first()
            db.close()
            
            if not profile or not profile.gmail_address or not profile.gmail_app_password:
                return {"error": "Gmail credentials not configured"}
            
            return {
                "email": profile.gmail_address,
                "password": profile.gmail_app_password
            }
        except Exception as e:
            logger.error(f"Error fetching Gmail creds: {e}")
            return {"error": str(e)}
    
    def decode_subject(self, raw: str) -> str:
        """Decode email subject with proper charset handling"""
        if not raw:
            return ""
        try:
            decoded = decode_header(raw)
            parts = []
            for part, charset in decoded:
                if isinstance(part, bytes):
                    parts.append(part.decode(charset or "utf-8", errors="ignore"))
                else:
                    parts.append(str(part))
            return "".join(parts)
        except Exception:
            return raw or ""
    
    def decode_body(self, msg) -> str:
        """Extract plain text from email"""
        body = ""
        try:
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        try:
                            body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                            break
                        except Exception:
                            continue
            else:
                try:
                    body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
                except Exception:
                    body = msg.get_payload()
        except Exception as e:
            logger.warning(f"Body decode error: {e}")
        
        return body[:2000]  # Truncate to 2000 chars
    
    def check_inbox(self) -> Dict:
        """
        Check Gmail for replies to sent emails.
        Returns: {replies: [{from, subject, body, original_subject, ...}]}
        """
        creds = self.get_gmail_creds()
        if "error" in creds:
            return {"error": creds["error"], "replies": []}
        
        try:
            # Get sent emails from DB
            from backend.database import SessionLocal
            from backend.models.sent_email import SentEmail
            
            db = SessionLocal()
            sent_emails = db.query(SentEmail).filter(
                SentEmail.user_id == self.user_id,
                SentEmail.replied == False  # Only unreplied
            ).all()
            db.close()
            
            if not sent_emails:
                logger.info(f"[{self.user_id}] No unreplied emails to check")
                return {"replies": []}
            
            awaiting_emails = {e.to_email.lower() for e in sent_emails}
            awaiting_subjects = {e.subject for e in sent_emails if e.subject}
            
            # Connect to Gmail
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(creds["email"], creds["password"])
            mail.select("inbox")
            
            # Search last 30 days
            since = (datetime.now() - timedelta(days=30)).strftime("%d-%b-%Y")
            _, ids = mail.search(None, f"SINCE {since}")
            
            if not ids or not ids[0]:
                mail.logout()
                return {"replies": []}
            
            id_list = ids[0].split()
            replies = []
            
            for mid in id_list[-100:]:
                try:
                    _, data = mail.fetch(mid, "(RFC822)")
                    msg = email.message_from_bytes(data[0][1])
                    
                    sender = msg.get("From", "").lower()
                    subject = self.decode_subject(msg.get("Subject", ""))
                    body = self.decode_body(msg)
                    
                    is_reply = False
                    original_email = None
                    
                    # Check 1: Sender matches
                    for ae in awaiting_emails:
                        if ae in sender:
                            is_reply = True
                            original_email = ae
                            break
                    
                    # Check 2: Re: subject matches
                    if not is_reply and subject.lower().startswith("re:"):
                        orig_subject = subject[3:].strip().lower()
                        for as_ in awaiting_subjects:
                            if orig_subject in as_.lower() or as_.lower() in orig_subject:
                                is_reply = True
                                for e in sent_emails:
                                    if e.subject and e.subject.lower() in orig_subject:
                                        original_email = e.to_email
                                        break
                                break
                    
                    if not is_reply:
                        continue
                    
                    # Found a reply!
                    original = next((e for e in sent_emails if e.to_email.lower() in sender), None)
                    if original:
                        replies.append({
                            "id": original.id,
                            "from": sender,
                            "subject": subject,
                            "body": body,
                            "original_email": original,
                        })
                        logger.info(f"[{self.user_id}] Found reply from {sender}")
                
                except Exception as e:
                    logger.warning(f"Email parse error: {e}")
                    continue
            
            mail.logout()
            
            return {"replies": replies}
        
        except Exception as e:
            logger.error(f"Reply detection error: {e}")
            return {"error": str(e), "replies": []}


# ─────────────────────────────────────────────
# AUTO-DRAFT GENERATION (Groq-based)
# ─────────────────────────────────────────────

class AutoDraftGenerator:
    """
    Generate contextual replies using Groq.
    No Claude API — pure Groq.
    """
    
    @staticmethod
    def generate_reply_draft(
        user_id: int,
        incoming_from: str,
        incoming_subject: str,
        incoming_body: str,
        original_subject: str,
        original_body: str,
        company: Optional[str] = None
    ) -> Dict:
        """
        Generate draft reply using Groq.
        Returns: {subject, body} or {error: ...}
        """
        
        # Get user info for context
        try:
            from backend.database import SessionLocal
            from backend.models.user import UserProfile
            from backend.agents.email_generator import get_user_info
            
            db = SessionLocal()
            profile = db.query(UserProfile).filter(
                UserProfile.user_id == user_id
            ).first()
            db.close()
            
            user_info = get_user_info(user_id)
            user_context = f"""
Your profile:
- Name: {user_info.get('name', 'you')}
- Skills: {', '.join(user_info.get('skills', [])[:5])}
- Key project: {user_info.get('key_project', 'N/A')}
"""
        except Exception as e:
            logger.warning(f"Could not fetch user profile: {e}")
            user_context = ""
        
        prompt = f"""You are an expert email writer helping draft a reply to an incoming email.

{user_context}

=== ORIGINAL EMAIL WE SENT ===
Subject: {original_subject}
Body:
{original_body[:500]}

=== THEIR REPLY ===
From: {incoming_from}
Subject: {incoming_subject}
Body:
{incoming_body[:500]}

=== YOUR TASK ===
Generate a professional, warm reply that:
1. Thanks them for their response
2. Addresses their key points
3. Proposes next steps (call, info, etc.)
4. Keeps it concise (3-4 sentences)

Rules:
- NO markdown, NO asterisks
- All strings on ONE line (escape newlines as \\n)
- Return ONLY valid JSON: {{"subject": "...", "body": "..."}}
- Start with {{ and end with }}
- Subject max 10 words
- Body max 200 words"""
        
        result = call_groq(prompt, max_tokens=600)
        
        if "error" in result or not result.get("subject"):
            logger.error(f"Draft generation failed: {result.get('error', 'empty result')}")
            return {
                "subject": f"Re: {incoming_subject}",
                "body": (
                    f"Thank you for your message. I appreciate your response and would love "
                    f"to discuss this further. Let me know your availability.\n\nBest regards"
                ),
                "error": "Generation failed, using template"
            }
        
        logger.info(f"Generated reply draft for {incoming_from}")
        return result


# ─────────────────────────────────────────────
# DATABASE OPERATIONS
# ─────────────────────────────────────────────

class ReplyStorage:
    """
    Store replies and drafts in database.
    """
    
    @staticmethod
    def save_reply_with_draft(
        sent_email_id: int,
        reply_from: str,
        reply_subject: str,
        reply_body: str,
        auto_draft: Dict
    ) -> bool:
        """
        Save detected reply + auto-draft to SentEmail table.
        """
        try:
            from backend.database import SessionLocal
            from backend.models.sent_email import SentEmail
            
            db = SessionLocal()
            email_record = db.query(SentEmail).filter(
                SentEmail.id == sent_email_id
            ).first()
            
            if email_record:
                email_record.replied = True
                email_record.reply_at = datetime.utcnow()
                email_record.reply_subject = reply_subject
                email_record.reply_body = reply_body
                email_record.auto_draft_json = json.dumps(auto_draft)
                email_record.reply_notified = False  # Notify user
                email_record.status = "replied"
                
                db.commit()
                db.close()
                
                logger.info(f"Saved reply to DB: {email_record.to_email}")
                return True
            
            db.close()
            return False
        
        except Exception as e:
            logger.error(f"Error saving reply to DB: {e}")
            return False


# ─────────────────────────────────────────────
# NOTIFICATION SYSTEM
# ─────────────────────────────────────────────

class NotificationManager:
    """
    Manage notifications for replies.
    Uses database for persistence.
    """
    
    @staticmethod
    def create_notification(
        user_id: int,
        notif_type: str,
        title: str,
        message: str,
        data: Dict
    ) -> bool:
        """
        Create notification in DB.
        Frontend polls for unread notifications.
        """
        try:
            from backend.database import SessionLocal
            from backend.models.notification import Notification
            
            db = SessionLocal()
            notif = Notification(
                user_id=user_id,
                type=notif_type,
                title=title,
                message=message,
                data_json=json.dumps(data),
                read=False,
                created_at=datetime.utcnow()
            )
            
            db.add(notif)
            db.commit()
            db.close()
            
            logger.info(f"Notification created: {user_id} - {title[:40]}")
            return True
        
        except Exception as e:
            logger.error(f"Notification creation error: {e}")
            return False
    
    @staticmethod
    def get_pending_notifications(user_id: int) -> List[Dict]:
        """
        Get all unread notifications for a user.
        """
        try:
            from backend.database import SessionLocal
            from backend.models.notification import Notification
            
            db = SessionLocal()
            notifications = db.query(Notification).filter(
                Notification.user_id == user_id,
                Notification.read == False
            ).order_by(Notification.created_at.desc()).all()
            
            result = [
                {
                    "id": n.id,
                    "type": n.type,
                    "title": n.title,
                    "message": n.message,
                    "data": json.loads(n.data_json) if n.data_json else {},
                    "created_at": n.created_at.isoformat() if n.created_at else ""
                }
                for n in notifications
            ]
            
            db.close()
            return result
        
        except Exception as e:
            logger.error(f"Notification fetch error: {e}")
            return []

    @staticmethod
    def mark_as_read(notification_id: int) -> bool:
        """Mark notification as read"""
        try:
            from backend.database import SessionLocal
            from backend.models.notification import Notification
        
            db = SessionLocal()
            notif = db.query(Notification).filter(
                Notification.id == notification_id
            ).first()
        
            if notif:
                notif.read = True
                notif.read_at = datetime.utcnow()
                db.commit()
                db.close()
                return True
        
            db.close()
            return False
        except Exception as e:
            logger.error(f"Error marking notification as read: {e}")
            return False
# ─────────────────────────────────────────────
# DRAFT APPROVAL FLOW
# ─────────────────────────────────────────────

class DraftApprovalManager:
    """
    User approves/rejects/edits drafts.
    Sends approved replies through Gmail.
    """
    
    @staticmethod
    def get_pending_drafts(user_id: int) -> List[Dict]:
        """
        Get all replies pending user approval.
        """
        try:
            from backend.database import SessionLocal
            from backend.models.sent_email import SentEmail
            
            db = SessionLocal()
            pending = db.query(SentEmail).filter(
                SentEmail.user_id == user_id,
                SentEmail.replied == True,
                SentEmail.auto_draft_approved == False
            ).order_by(SentEmail.reply_at.desc()).all()
            
            result = [
                {
                    "id": e.id,
                    "from": e.to_email,
                    "company": e.company,
                    "original_subject": e.subject,
                    "reply_subject": e.reply_subject,
                    "reply_body_preview": e.reply_body[:200],
                    "auto_draft": json.loads(e.auto_draft_json) if e.auto_draft_json else {},
                    "reply_at": e.reply_at.isoformat() if e.reply_at else None
                }
                for e in pending
            ]
            
            db.close()
            return result
        
        except Exception as e:
            logger.error(f"Get pending drafts error: {e}")
            return []
    
    @staticmethod
    def approve_and_send(
        sent_email_id: int,
        final_subject: str,
        final_body: str,
        user_id: int
    ) -> Dict:
        """
        User approved draft.
        Send reply through Gmail.
        Mark as approved in DB.
        """
        try:
            from backend.database import SessionLocal
            from backend.models.sent_email import SentEmail
            from backend.agents.email_sender import send_and_log
            
            db = SessionLocal()
            email_record = db.query(SentEmail).filter(
                SentEmail.id == sent_email_id
            ).first()
            
            if not email_record:
                return {"error": "Email record not found"}
            
            # Send via Gmail
            result = send_and_log(
                user_id=user_id,
                to_email=email_record.to_email,
                subject=final_subject,
                body=final_body,
                company=email_record.company,
                contact=email_record.contact_name,
                is_reply=True
            )
            
            if not result.get("success"):
                return {"error": f"Send failed: {result.get('error')}"}
            
            # Update DB
            email_record.auto_draft_approved = True
            email_record.status = "reply_sent"
            db.commit()
            db.close()
            
            logger.info(f"Reply sent to {email_record.to_email}")
            return {"success": True, "email_id": sent_email_id}
        
        except Exception as e:
            logger.error(f"Approve and send error: {e}")
            return {"error": str(e)}
    
    @staticmethod
    def reject_draft(sent_email_id: int) -> bool:
        """
        User rejected auto-draft.
        Mark for manual reply.
        """
        try:
            from backend.database import SessionLocal
            from backend.models.sent_email import SentEmail
            
            db = SessionLocal()
            email_record = db.query(SentEmail).filter(
                SentEmail.id == sent_email_id
            ).first()
            
            if email_record:
                email_record.status = "manual_reply_needed"
                db.commit()
                db.close()
                return True
            
            db.close()
            return False
        
        except Exception as e:
            logger.error(f"Reject draft error: {e}")
            return False


# ─────────────────────────────────────────────
# SCHEDULER JOB
# ─────────────────────────────────────────────

def check_and_handle_all_replies() -> Dict:
    """
    Background scheduler job.
    Runs every 6 hours automatically.
    NO manual trigger needed.
    
    Returns: {total_replies: N, processed: [...]}
    """
    from backend.agents.followup_agent import get_all_users_with_sent_emails
    
    users = get_all_users_with_sent_emails()
    total_replies = 0
    processed = []
    
    for user_id in users:
        try:
            detector = ReplyDetector(user_id)
            result = detector.check_inbox()
            
            if "error" in result:
                logger.warning(f"Reply check error user {user_id}: {result['error']}")
                continue
            
            replies = result.get("replies", [])
            
            for reply in replies:
                original = reply["original_email"]
                
                # Generate auto-draft
                draft = AutoDraftGenerator.generate_reply_draft(
                    user_id=user_id,
                    incoming_from=reply["from"],
                    incoming_subject=reply["subject"],
                    incoming_body=reply["body"],
                    original_subject=original.subject,
                    original_body=original.body,
                    company=original.company
                )
                
                # Save to DB
                if ReplyStorage.save_reply_with_draft(
                    sent_email_id=original.id,
                    reply_from=reply["from"],
                    reply_subject=reply["subject"],
                    reply_body=reply["body"],
                    auto_draft=draft
                ):
                    # Create notification
                    NotificationManager.create_notification(
                        user_id=user_id,
                        notif_type="reply_received",
                        title=f"📩 Reply from {original.company or reply['from']}",
                        message=f"Subject: {reply['subject'][:60]}...",
                        data={
                            "sent_email_id": original.id,
                            "from": reply["from"],
                            "company": original.company,
                            "subject": reply["subject"],
                            "body_preview": reply["body"][:200]
                        }
                    )
                    
                    total_replies += 1
                    processed.append({
                        "user": user_id,
                        "from": reply["from"],
                        "company": original.company
                    })
        
        except Exception as e:
            logger.error(f"User {user_id} reply check error: {e}")
            continue
    
    logger.info(f"[Scheduler] Reply check complete: {total_replies} new replies")
    return {"total_replies": total_replies, "processed": processed}


if __name__ == "__main__":
    # Test
    result = check_and_handle_all_replies()
    print(json.dumps(result, indent=2, default=str))