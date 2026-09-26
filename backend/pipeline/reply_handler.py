# backend/pipeline/reply_handler.py
import imaplib
import email
import json
import re
from email.header import decode_header
from datetime import datetime
from typing import List, Dict

from loguru import logger

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


def _clean_addr(raw: str) -> str:
    if not raw:
        return ""
    match = re.search(r'[\w.+-]+@[\w.-]+\.\w+', raw)
    return (match.group(0) if match else raw).strip().lower()


def _decode(value: str) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    out = ""
    for text, enc in parts:
        if isinstance(text, bytes):
            out += text.decode(enc or "utf-8", errors="ignore")
        else:
            out += text
    return out


def _get_body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if ctype == "text/plain" and "attachment" not in disp:
                try:
                    return part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="ignore"
                    )
                except Exception:
                    continue
        return ""
    try:
        return msg.get_payload(decode=True).decode(
            msg.get_content_charset() or "utf-8", errors="ignore"
        )
    except Exception:
        return ""


# ─────────────────────────────────────────────
# NOTIFICATIONS
# ─────────────────────────────────────────────

class NotificationManager:
    @staticmethod
    def get_pending_notifications(user_id: int) -> List[Dict]:
        """Get all unread notifications for a user."""
        db = SessionLocal()
        try:
            notifications = db.query(Notification).filter(
                Notification.user_id == user_id,
                Notification.is_read == False
            ).order_by(Notification.created_at.desc()).all()

            return [
                {
                    "id"        : n.id,
                    "type"      : n.notification_type,
                    "title"     : n.title,
                    "message"   : n.message,
                    "data"      : json.loads(n.data) if n.data else {},
                    "created_at": n.created_at.isoformat() if n.created_at else "",
                }
                for n in notifications
            ]
        except Exception as e:
            logger.error(f"Error getting notifications: {e}")
            return []
        finally:
            db.close()

    @staticmethod
    def create_notification(user_id: int, notif_type: str, title: str = "", message: str = "", data: Dict = None) -> bool:
        db = SessionLocal()
        try:
            notif = Notification(
                user_id           = user_id,
                notification_type = notif_type,
                title              = title,
                message            = message,
                data               = json.dumps(data or {}),
                is_read            = False,
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

    @staticmethod
    def mark_as_read(notif_id: int) -> bool:
        db = SessionLocal()
        try:
            notif = db.query(Notification).filter(Notification.id == notif_id).first()
            if not notif:
                return False
            notif.is_read = True
            notif.read_at = datetime.utcnow()
            db.commit()
            return True
        except Exception as e:
            logger.error(f"Error marking notification read: {e}")
            db.rollback()
            return False
        finally:
            db.close()


# ─────────────────────────────────────────────
# REPLY DETECTION  (Gmail IMAP)
# ─────────────────────────────────────────────

class ReplyDetector:
    """Checks the user's Gmail inbox for replies to previously sent cold emails."""

    def __init__(self, user_id: int):
        self.user_id = user_id

    def check_inbox(self) -> Dict:
        from backend.agents.email_sender import get_gmail_creds

        creds = get_gmail_creds(self.user_id)
        if "error" in creds:
            return {"error": creds["error"]}

        db = SessionLocal()
        try:
            pending = db.query(SentEmail).filter(
                SentEmail.user_id == self.user_id,
                SentEmail.replied == False,
            ).all()

            if not pending:
                return {"replies": []}

            by_sender: Dict[str, list] = {}
            for row in pending:
                addr = _clean_addr(row.to_email)
                if addr:
                    by_sender.setdefault(addr, []).append(row)

            replies = []
            imap = None
            try:
                imap = imaplib.IMAP4_SSL("imap.gmail.com")
                imap.login(creds["email"], creds["password"])
                imap.select("INBOX")

                status, msg_ids = imap.search(None, "UNSEEN")
                if status != "OK":
                    return {"error": "Could not search inbox"}

                for msg_id in msg_ids[0].split():
                    try:
                        status, data = imap.fetch(msg_id, "(RFC822)")
                        if status != "OK" or not data or not data[0]:
                            continue
                        msg = email.message_from_bytes(data[0][1])

                        from_addr = _clean_addr(msg.get("From", ""))
                        matches = by_sender.get(from_addr)
                        if not matches:
                            continue

                        original = matches[0]
                        replies.append({
                            "from"          : from_addr,
                            "subject"       : _decode(msg.get("Subject", "")),
                            "body"          : _get_body(msg)[:5000],
                            "original_email": original,
                        })
                    except Exception as e:
                        logger.warning(f"Reply parse error (msg {msg_id}): {e}")
                        continue

            except imaplib.IMAP4.error as e:
                return {"error": f"Gmail login failed — check your App Password: {e}"}
            except Exception as e:
                return {"error": f"IMAP error: {e}"}
            finally:
                if imap:
                    try:
                        imap.logout()
                    except Exception:
                        pass

            return {"replies": replies}
        finally:
            db.close()


# ─────────────────────────────────────────────
# AUTO-DRAFT GENERATION  (Groq)
# ─────────────────────────────────────────────

class AutoDraftGenerator:
    @staticmethod
    def generate_reply_draft(
        user_id         : int,
        incoming_from   : str,
        incoming_subject: str,
        incoming_body   : str,
        original_subject: str,
        original_body   : str,
        company         : str,
    ) -> Dict:
        subject = incoming_subject if incoming_subject.lower().startswith("re:") else f"Re: {original_subject}"

        if not client:
            return {"subject": subject, "body": "Thank you for your reply. I'd love to discuss this further."}

        prompt = f"""
You are helping draft a professional reply to a cold outreach response.

Company: {company}
Their reply subject: {incoming_subject}
Their message:
{incoming_body[:800]}

Our original pitch:
{original_body[:400]}

Write a brief, professional reply (2-4 sentences) that:
1. Thanks them for responding
2. Directly addresses what they said
3. Proposes a concrete next step (a quick call, more details, etc.)

Return ONLY the email body text, no subject line, no markdown.
"""
        try:
            response = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=350,
                temperature=0.7,
                reasoning_effort="low",
            )
            body = response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"Draft generation error: {e}")
            body = "Thank you for your reply. I'd love to discuss this further — happy to jump on a quick call whenever works for you."

        return {"subject": subject, "body": body}


# ─────────────────────────────────────────────
# REPLY STORAGE
# ─────────────────────────────────────────────

class ReplyStorage:
    @staticmethod
    def save_reply_with_draft(
        sent_email_id: int,
        reply_from   : str,
        reply_subject: str,
        reply_body   : str,
        auto_draft   : Dict,
    ) -> bool:
        db = SessionLocal()
        try:
            row = db.query(SentEmail).filter(SentEmail.id == sent_email_id).first()
            if not row or row.replied:
                return False

            row.replied         = True
            row.reply_at        = datetime.utcnow()
            row.reply_body      = (reply_body or "")[:5000]
            row.reply_subject   = reply_subject
            row.auto_draft_json = json.dumps(auto_draft or {})
            row.status          = "replied"
            db.commit()
            return True
        except Exception as e:
            logger.error(f"save_reply_with_draft error: {e}")
            db.rollback()
            return False
        finally:
            db.close()


# ─────────────────────────────────────────────
# DRAFT APPROVAL  (reply drafts awaiting the user's OK)
# ─────────────────────────────────────────────

class DraftApprovalManager:
    @staticmethod
    def get_pending_drafts(user_id: int) -> List[Dict]:
        """SentEmail rows that got a reply and are waiting on the user to approve the auto-draft."""
        db = SessionLocal()
        try:
            rows = db.query(SentEmail).filter(
                SentEmail.user_id == user_id,
                SentEmail.replied == True,
                SentEmail.auto_draft_approved == False,
            ).order_by(SentEmail.reply_at.desc()).all()

            out = []
            for r in rows:
                try:
                    auto_draft = json.loads(r.auto_draft_json) if r.auto_draft_json else {}
                except Exception:
                    auto_draft = {}
                out.append({
                    "id"                : r.id,
                    "company"           : r.company or "",
                    "from"              : r.to_email,
                    "original_subject"  : r.subject or "",
                    "reply_body_preview": (r.reply_body or "")[:500],
                    "reply_at"          : r.reply_at.isoformat() if r.reply_at else "",
                    "auto_draft"        : auto_draft,
                })
            return out
        except Exception as e:
            logger.error(f"get_pending_drafts error: {e}")
            return []
        finally:
            db.close()

    @staticmethod
    def approve_and_send(sent_email_id: int, final_subject: str, final_body: str, user_id: int) -> Dict:
        from backend.agents.email_sender import send_email

        db = SessionLocal()
        try:
            row = db.query(SentEmail).filter(
                SentEmail.id == sent_email_id, SentEmail.user_id == user_id
            ).first()
            if not row:
                return {"success": False, "error": "Original email not found"}

            result = send_email(
                user_id  = user_id,
                to_email = row.to_email,
                subject  = final_subject,
                body     = final_body,
                company  = row.company or "",
                contact  = row.contact_name or "",
            )
            if not result.get("success"):
                return {"success": False, "error": result.get("error", "Send failed")}

            row.auto_draft_approved = True
            row.status              = "reply_sent"
            db.commit()

            db.add(DraftAction(
                user_id       = user_id,
                sent_email_id = sent_email_id,
                action        = "edited_and_sent" if final_body != json.loads(row.auto_draft_json or "{}").get("body") else "approved",
                action_type   = "reply",
                subject       = final_subject,
                body          = final_body,
                to_email      = row.to_email,
                status        = "sent",
                user_action_at= datetime.utcnow(),
            ))
            db.commit()
            return {"success": True}
        except Exception as e:
            logger.error(f"approve_and_send error: {e}")
            db.rollback()
            return {"success": False, "error": str(e)}
        finally:
            db.close()

    @staticmethod
    def reject_draft(sent_email_id: int) -> bool:
        db = SessionLocal()
        try:
            row = db.query(SentEmail).filter(SentEmail.id == sent_email_id).first()
            if not row:
                return False

            row.status              = "manual_reply_needed"
            row.auto_draft_approved = True  # stop showing it as pending
            db.commit()

            db.add(DraftAction(
                user_id        = row.user_id,
                sent_email_id  = sent_email_id,
                action         = "rejected",
                action_type    = "reply",
                to_email       = row.to_email,
                status         = "rejected",
                user_action_at = datetime.utcnow(),
            ))
            db.commit()
            return True
        except Exception as e:
            logger.error(f"reject_draft error: {e}")
            db.rollback()
            return False
        finally:
            db.close()


# ─────────────────────────────────────────────
# SCHEDULER ENTRY POINT — checks every user's inbox
# ─────────────────────────────────────────────

def check_and_handle_all_replies() -> Dict:
    """Called by the background scheduler every few hours."""
    logger.info("🔄 Checking for replies across all users...")

    db = SessionLocal()
    try:
        users = db.query(User).filter(User.is_active == True).all()
    finally:
        db.close()

    total_replies = 0
    for user in users:
        try:
            detector = ReplyDetector(user.id)
            result   = detector.check_inbox()
            if result.get("error"):
                logger.warning(f"Reply check skipped for user {user.id}: {result['error']}")
                continue

            for reply in result.get("replies", []):
                original = reply["original_email"]
                draft = AutoDraftGenerator.generate_reply_draft(
                    user_id          = user.id,
                    incoming_from    = reply["from"],
                    incoming_subject = reply["subject"],
                    incoming_body    = reply["body"],
                    original_subject = original.subject,
                    original_body    = getattr(original, "body", ""),
                    company          = original.company,
                )
                saved = ReplyStorage.save_reply_with_draft(
                    sent_email_id = original.id,
                    reply_from    = reply["from"],
                    reply_subject = reply["subject"],
                    reply_body    = reply["body"],
                    auto_draft    = draft,
                )
                if saved:
                    total_replies += 1
                    NotificationManager.create_notification(
                        user_id    = user.id,
                        notif_type = "reply_received",
                        title      = f"📩 Reply from {original.company or reply['from']}",
                        message    = f"Subject: {reply['subject'][:60]}",
                        data       = {
                            "sent_email_id": original.id,
                            "from"         : reply["from"],
                            "company"      : original.company,
                            "subject"      : reply["subject"],
                            "body_preview" : reply["body"][:200],
                        },
                    )
        except Exception as e:
            logger.error(f"Error processing user {user.id}: {e}")
            continue

    logger.info(f"✅ Reply check complete: {total_replies} replies found")
    return {"total_replies": total_replies, "success": True}
