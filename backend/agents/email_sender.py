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
    """
    if not raw:
        return raw
    raw = raw.replace("u003e", "").replace("u003c", "").strip()
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
            return {"error": "Gmail credentials missing — onboarding mein Gmail App Password daalo"}

        return {
            "email"   : profile.gmail_address.strip(),
            "password": profile.gmail_app_password.replace(" ", "").strip()
        }
    except Exception as e:
        logger.error(f"get_gmail_creds error: {e}")
        return {"error": str(e)}


# ─────────────────────────────────────────────
# SENT LOG  (shared helpers — tracker bhi yahi use kare)
# ─────────────────────────────────────────────

def get_sent_log(user_id: int) -> list:
    log_file = f"uploads/{user_id}/sent_emails/log.json"
    if not os.path.exists(log_file):
        return []
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"get_sent_log read error: {e}")
        return []


def save_sent_log(user_id: int, log: list):
    log_dir  = f"uploads/{user_id}/sent_emails"
    log_file = f"{log_dir}/log.json"
    os.makedirs(log_dir, exist_ok=True)
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


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
    contact    : str = "",
    contact_role: str = "",
    gap        : str = "",
    proposal   : str = "",
    website    : str = "",
) -> dict:
    """Gmail SMTP se email bhejo aur log karo."""

    to_email = _clean_email(to_email)
    if not to_email:
        return {"success": False, "error": "to_email empty hai"}
    if cc:
        cc = _clean_email(cc)

    # ── Credential check ──────────────────────
    creds = get_gmail_creds(user_id)
    if "error" in creds:
        logger.error(f"Gmail creds error: {creds['error']}")
        return {"success": False, "error": creds["error"]}

    gmail_address  = creds["email"]
    gmail_password = creds["password"]

    logger.info(f"Sending → {to_email}  |  from: {gmail_address}  |  company: {company}")

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
        elif resume_path:
            logger.warning(f"  ⚠️ Resume path set but file not found: {resume_path}")

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_address, gmail_password)
            recipients = [to_email]
            if cc:
                recipients.append(cc)
            server.sendmail(gmail_address, recipients, msg.as_string())

        sent_at = datetime.utcnow().isoformat()
        logger.info(f"  ✅ SMTP success → {to_email}")

        # ── Log to JSON ───────────────────────
        _log_sent(
            user_id      = user_id,
            to           = to_email,
            subject      = subject,
            body         = body,
            sent_at      = sent_at,
            company      = company,
            contact      = contact,
            contact_role = contact_role,
            gap          = gap,
            proposal     = proposal,
            website      = website,
        )

        return {
            "success": True,
            "sent_at": sent_at,
            "from"   : gmail_address,
            "to"     : to_email,
        }

    except smtplib.SMTPAuthenticationError:
        error = "Gmail auth failed — Google Account mein 2FA on karo, phir App Password banao"
        logger.error(f"  ❌ {error}")
        return {"success": False, "error": error}

    except smtplib.SMTPRecipientsRefused as e:
        error = f"Recipient refused: {to_email} — {e}"
        logger.error(f"  ❌ {error}")
        return {"success": False, "error": error}

    except smtplib.SMTPException as e:
        error = f"SMTP error: {e}"
        logger.error(f"  ❌ {error}", exc_info=True)
        return {"success": False, "error": error}

    except Exception as e:
        logger.error(f"  ❌ Send error: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# ─────────────────────────────────────────────
# LOG  (single source of truth — outreach page
#       _update_tracker ko HATAO, yahi use karo)
# ─────────────────────────────────────────────

def _log_sent(
    user_id     : int,
    to          : str,
    subject     : str,
    body        : str,
    sent_at     : str,
    company     : str = "",
    contact     : str = "",
    contact_role: str = "",
    gap         : str = "",
    proposal    : str = "",
    website     : str = "",
):
    """JSON log mein ek entry append karo."""
    log = get_sent_log(user_id)

    entry = {
        "to"            : to,
        "subject"       : subject,
        "body"          : body[:500],
        "sent_at"       : sent_at,
        "company"       : company,
        "website"       : website,
        "contact"       : contact,
        "contact_name"  : contact,       # tracker dono key check karta hai
        "contact_role"  : contact_role,
        "gap"           : gap,
        "proposal"      : proposal,
        "replied"       : False,
        "reply_at"      : None,
        "reply_body"    : None,
        "followup_sent" : False,
        "followup_at"   : None,
        "followup_count": 0,
        "status"        : "awaiting",    # tracker filter yahi dekhta hai
    }
    log.append(entry)
    save_sent_log(user_id, log)
    logger.info(f"  📝 Logged to JSON: {to} ({company})")

    # Google Sheets sync (optional — failure se send block nahi hoga)
    try:
        from backend.utils.sheets_tracker import log_cold_email
        log_cold_email(
            user_id       = user_id,
            company       = company,
            website       = website,
            contact_name  = contact,
            contact_role  = contact_role,
            contact_email = to,
            subject       = subject,
            gap           = gap,
            proposal      = proposal,
        )
    except Exception as e:
        logger.warning(f"  Sheets sync skipped: {e}")


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
    contact    : str = "",
) -> dict:
    return send_email(
        user_id     = user_id,
        to_email    = to_email,
        subject     = subject,
        body        = body,
        resume_path = resume_path,
        company     = company,
        contact     = contact,
    )