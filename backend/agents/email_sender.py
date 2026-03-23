# backend/agents/email_sender.py

import os
import re
import json
import smtplib
from email.mime.text        import MIMEText
from email.mime.multipart   import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime               import datetime
from loguru                 import logger
from dotenv                 import load_dotenv
load_dotenv()


# ─────────────────────────────────────────────
# HELPER — angle-bracket email cleaner
# ─────────────────────────────────────────────

def _clean_email(raw: str) -> str:
    """
    "Name <email@domain.com>"  →  "email@domain.com"
    "u003esecurity@domain.com" →  "security@domain.com"

    When an email header like <security@playabl.ai> is naively str()-ed,
    '<' gets dropped and '>' becomes the unicode escape u003e.
    This extracts just the bare RFC-5321 address.
    """
    if not raw:
        return raw
    # First: strip any unicode escapes for angle brackets
    raw = raw.replace("u003e", "").replace("u003c", "").strip()
    # Then: extract bare email from "Name <email>" format
    match = re.search(r'[\w\.\+\-]+@[\w\.\-]+\.\w+', raw)
    return match.group(0) if match else raw.strip()


# ─────────────────────────────────────────────
# GMAIL CREDS
# ─────────────────────────────────────────────

def get_gmail_creds(user_id: int) -> dict:
    try:
        from backend.database    import SessionLocal
        from backend.models.user import UserProfile

        db      = SessionLocal()
        profile = db.query(UserProfile).filter(
            UserProfile.user_id == user_id
        ).first()
        db.close()

        if not profile:
            return {"error": "Profile nahi mila"}
        if not profile.gmail_address or not profile.gmail_app_password:
            return {"error": "Gmail credentials nahi hain — onboarding complete karo"}

        return {
            "email"   : profile.gmail_address.strip(),
            "password": profile.gmail_app_password.replace(" ", "").strip()
        }
    except Exception as e:
        return {"error": str(e)}


# ─────────────────────────────────────────────
# SENT LOG
# ─────────────────────────────────────────────

def get_sent_log(user_id: int) -> list:
    log_file = f"uploads/{user_id}/sent_emails/log.json"
    if not os.path.exists(log_file):
        return []
    try:
        with open(log_file, "r") as f:
            return json.load(f)
    except:
        return []


def save_sent_log(user_id: int, log: list):
    log_dir  = f"uploads/{user_id}/sent_emails"
    log_file = f"{log_dir}/log.json"
    os.makedirs(log_dir, exist_ok=True)
    with open(log_file, "w") as f:
        json.dump(log, f, indent=2)


# ─────────────────────────────────────────────
# SEND EMAIL
# ─────────────────────────────────────────────

def send_email(
    user_id    : int,
    to_email   : str,
    subject    : str,
    body       : str,
    resume_path: str = None,
    cc         : str = None,
    company    : str = "",
    contact    : str = ""
) -> dict:
    """Gmail SMTP se email bhejo."""

    # FIX — clean the address before doing anything with it
    to_email = _clean_email(to_email)
    if cc:
        cc = _clean_email(cc)

    creds = get_gmail_creds(user_id)
    if "error" in creds:
        return {"success": False, "error": creds["error"]}

    gmail_address  = creds["email"]
    gmail_password = creds["password"]

    try:
        msg            = MIMEMultipart()
        msg["From"]    = gmail_address
        msg["To"]      = to_email
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = cc

        msg.attach(MIMEText(body, "plain"))

        # Resume attach
        if resume_path and os.path.exists(resume_path):
            with open(resume_path, "rb") as f:
                part = MIMEApplication(
                    f.read(),
                    Name=os.path.basename(resume_path)
                )
            part["Content-Disposition"] = (
                f'attachment; filename="{os.path.basename(resume_path)}"'
            )
            msg.attach(part)
            logger.info("  📎 Resume attached")

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_address, gmail_password)
            recipients = [to_email]
            if cc:
                recipients.append(cc)
            server.sendmail(gmail_address, recipients, msg.as_string())

        sent_at = datetime.utcnow().isoformat()
        logger.info(f"  ✅ Sent to {to_email}")

        _log_sent(
            user_id = user_id,
            to      = to_email,
            subject = subject,
            body    = body,
            sent_at = sent_at,
            company = company,
            contact = contact
        )

        return {
            "success": True,
            "sent_at": sent_at,
            "from"   : gmail_address,
            "to"     : to_email
        }

    except smtplib.SMTPAuthenticationError:
        error = "Gmail auth failed — App Password check karo"
        logger.error(error)
        return {"success": False, "error": error}

    except smtplib.SMTPRecipientsRefused:
        error = f"Invalid email: {to_email}"
        logger.error(error)
        return {"success": False, "error": error}

    except Exception as e:
        logger.error(f"Send error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# ─────────────────────────────────────────────
# LOG
# ─────────────────────────────────────────────

def _log_sent(
    user_id: int,
    to     : str,
    subject: str,
    body   : str,
    sent_at: str,
    company: str = "",
    contact: str = ""
):
    """JSON log mein save karo + Google Sheets sync."""
    log = get_sent_log(user_id)

    log.append({
        "to"            : to,
        "subject"       : subject,
        "body"          : body[:500],
        "sent_at"       : sent_at,
        "company"       : company,
        "contact"       : contact,
        "replied"       : False,
        "reply_at"      : None,
        "reply_body"    : None,
        "followup_sent" : False,
        "followup_at"   : None,
        "followup_count": 0,
        "status"        : "awaiting"
    })

    save_sent_log(user_id, log)
    logger.info(f"  📝 Logged: {to}")

    # Google Sheets sync
    try:
        from backend.utils.sheets_tracker import log_cold_email
        log_cold_email(
            user_id       = user_id,
            company       = company,
            website       = "",
            contact_name  = contact,
            contact_role  = "",
            contact_email = to,
            subject       = subject,
            gap           = "",
            proposal      = ""
        )
    except Exception as e:
        logger.warning(f"Sheets sync error: {e}")


# ─────────────────────────────────────────────
# PIPELINE ENTRY POINT
# ─────────────────────────────────────────────

def send_and_log(
    user_id    : int,
    to_email   : str,
    subject    : str,
    body       : str,
    resume_path: str = None,
    company    : str = "",
    contact    : str = ""
) -> dict:
    """Pipeline nodes se call hota hai."""
    return send_email(
        user_id     = user_id,
        to_email    = to_email,
        subject     = subject,
        body        = body,
        resume_path = resume_path,
        company     = company,
        contact     = contact
    )