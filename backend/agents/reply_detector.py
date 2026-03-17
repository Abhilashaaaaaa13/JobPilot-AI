# backend/agents/reply_detector.py
# Gmail IMAP se inbox monitor karo
# Replies detect karo + classify karo

import imaplib
import email
import json
from email.header import decode_header
from datetime import datetime, timedelta
from groq import Groq
from sqlalchemy.orm import Session
from backend.models.application import Application
from backend.models.reply import Reply
from backend.models.user import UserProfile
from backend.config import GROQ_API_KEY, LLM_MODEL
from loguru import logger

client = Groq(api_key=GROQ_API_KEY)


def get_gmail_credentials(
    db      : Session,
    user_id : int
) -> tuple:
    profile = db.query(UserProfile).filter(
        UserProfile.user_id == user_id
    ).first()
    if not profile:
        return None, None
    return profile.gmail_address, profile.gmail_app_password


def decode_subject(subject: str) -> str:
    """Email subject decode karo."""
    try:
        decoded, encoding = decode_header(subject)[0]
        if isinstance(decoded, bytes):
            return decoded.decode(encoding or "utf-8")
        return decoded
    except:
        return subject or ""


def get_email_body(msg) -> str:
    """Email body extract karo."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    body = part.get_payload(decode=True)\
                               .decode("utf-8", errors="ignore")
                    break
                except:
                    continue
    else:
        try:
            body = msg.get_payload(decode=True)\
                      .decode("utf-8", errors="ignore")
        except:
            pass
    return body[:2000]


def classify_reply(reply_text: str) -> dict:
    """
    Groq se reply classify karo.

    Why LLM for classification?
    Rule-based: "interview" keyword dhundho
    → Miss karta hai: "let's connect" = interview
    → Wrong hit: "no interview" = rejection

    LLM context samajhta hai —
    sarcasm, indirect language bhi.
    """
    prompt_template = open(
        "backend/prompts/reply_classify_prompt.txt"
    ).read()

    prompt = prompt_template.format(reply_text=reply_text)

    try:
        response = client.chat.completions.create(
            model      = LLM_MODEL,
            messages   = [{"role": "user", "content": prompt}],
            max_tokens = 200,
            temperature= 0.1
        )
        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        logger.error(f"Classify error: {e}")
        return {
            "classification": "general",
            "confidence"    : 0.5,
            "next_action"   : "Manually review this reply",
            "key_points"    : []
        }


def check_inbox(
    db      : Session,
    user_id : int
) -> dict:
    """
    Gmail inbox check karo.
    Sent emails ke replies dhundho.

    How IMAP works:
    → IMAP = Internet Message Access Protocol
    → Server pe emails read karta hai
    → Download nahi karta — sirf reads
    → Gmail IMAP enable karna padta hai:
      Gmail Settings → See all settings →
      Forwarding and POP/IMAP → Enable IMAP
    """
    gmail, password = get_gmail_credentials(db, user_id)

    if not gmail or not password:
        return {"error": "Gmail credentials missing"}

    # Sent applications lo — jinke replies check karne hain
    applications = db.query(Application).filter(
        Application.user_id == user_id,
        Application.status.in_([
            "email_sent",
            "follow_up_1_sent",
            "follow_up_2_sent"
        ])
    ).all()

    if not applications:
        return {"message": "Koi pending applications nahi", "found": 0}

    # Subject lines index karo — reply match karne ke liye
    sent_subjects = {
        app.email_subject: app
        for app in applications
        if app.email_subject
    }

    found_replies = 0

    try:
        # Gmail IMAP connect karo
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(gmail, password)
        mail.select("inbox")

        # Last 7 days ki emails search karo
        since_date = (
            datetime.now() - timedelta(days=7)
        ).strftime("%d-%b-%Y")

        _, message_ids = mail.search(
            None, f'SINCE {since_date}'
        )

        ids = message_ids[0].split()
        logger.info(
            f"📬 {len(ids)} emails found "
            f"in inbox (last 7 days)"
        )

        for msg_id in ids[-50:]:  # Last 50 emails check karo
            try:
                _, msg_data = mail.fetch(msg_id, "(RFC822)")
                raw_email   = msg_data[0][1]
                msg         = email.message_from_bytes(raw_email)

                subject = decode_subject(msg.get("Subject", ""))
                sender  = msg.get("From", "")

                # "Re:" wali emails dhundho
                if not subject.lower().startswith("re:"):
                    continue

                # Original subject se match karo
                original = subject[3:].strip()
                matched_app = sent_subjects.get(original)

                if not matched_app:
                    # Partial match try karo
                    for sent_sub, app in sent_subjects.items():
                        if (sent_sub.lower() in subject.lower() or
                            subject.lower() in sent_sub.lower()):
                            matched_app = app
                            break

                if not matched_app:
                    continue

                # Already processed?
                existing = db.query(Reply).filter(
                    Reply.application_id == matched_app.id
                ).first()
                if existing:
                    continue

                # Body extract karo
                body = get_email_body(msg)

                # Classify karo
                classification = classify_reply(body)

                # Reply save karo
                reply = Reply(
                    application_id = matched_app.id,
                    received_date  = datetime.utcnow(),
                    reply_body     = body,
                    classification = classification["classification"],
                    next_action    = classification["next_action"]
                )
                db.add(reply)

                # Application status update karo
                cls = classification["classification"]
                if cls == "interview_invite":
                    matched_app.status = "interview_scheduled"
                elif cls == "rejection":
                    matched_app.status = "replied_negative"
                elif cls in ["info_request", "general"]:
                    matched_app.status = "replied_positive"

                db.commit()
                found_replies += 1

                logger.info(
                    f"  📩 Reply from {sender[:30]} "
                    f"→ {cls} "
                    f"| Action: {classification['next_action'][:50]}"
                )

            except Exception as e:
                logger.warning(f"  ⚠️ Email parse error: {e}")
                continue

        mail.logout()

    except imaplib.IMAP4.error as e:
        logger.error(f"❌ IMAP error: {e}")
        return {
            "error": (
                "IMAP connection failed — "
                "Gmail mein IMAP enable karo"
            )
        }
    except Exception as e:
        logger.error(f"❌ Inbox check error: {e}")
        return {"error": str(e)}

    return {
        "emails_checked": len(ids),
        "replies_found" : found_replies
    }