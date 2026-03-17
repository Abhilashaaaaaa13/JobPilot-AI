# backend/agents/email_sender.py
# Gmail SMTP se email bhejo
# Resume attach karo
# DB mein log karo

import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from sqlalchemy.orm import Session
from backend.models.application import Application
from backend.models.contact import Contact
from backend.models.user import UserProfile
from backend.config import FOLLOWUP_AFTER_DAYS
from loguru import logger


def get_gmail_credentials(
    db      : Session,
    user_id : int
) -> tuple:
    """
    User ka Gmail credentials lo DB se.

    Why per-user credentials?
    Har user apne Gmail se email bhejega.
    System ka ek shared Gmail nahi hai.
    Zyada authentic lagta hai — better delivery.
    """
    profile = db.query(UserProfile).filter(
        UserProfile.user_id == user_id
    ).first()

    if not profile:
        return None, None

    return profile.gmail_address, profile.gmail_app_password


def send_email(
    gmail_address  : str,
    app_password   : str,
    to_email       : str,
    subject        : str,
    body           : str,
    resume_path    : str = None
) -> bool:
    """
    Gmail SMTP se email bhejo.

    Why App Password?
    Google 2FA ke baad main password se
    third party apps kaam nahi karte.
    App Password = specific 16-char password
    sirf ek app ke liye.

    Why TLS port 587?
    Port 465 = SSL (older)
    Port 587 = TLS (modern, recommended)
    Gmail dono support karta hai but
    587 more reliable hai.
    """
    try:
        # Email object banao
        msg = MIMEMultipart()
        msg["From"]    = gmail_address
        msg["To"]      = to_email
        msg["Subject"] = subject

        # Body attach karo
        msg.attach(MIMEText(body, "plain"))

        # Resume attach karo agar hai
        if resume_path and os.path.exists(resume_path):
            with open(resume_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
                encoders.encode_base64(part)

                filename = os.path.basename(resume_path)
                part.add_header(
                    "Content-Disposition",
                    f"attachment; filename={filename}"
                )
                msg.attach(part)
            logger.info(f"  📎 Resume attached: {filename}")

        # Gmail SMTP se bhejo
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(gmail_address, app_password)
            server.send_message(msg)

        logger.info(f"  ✅ Email sent to {to_email}")
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error(
            "❌ Gmail auth failed — "
            "App Password check karo"
        )
        return False
    except smtplib.SMTPException as e:
        logger.error(f"❌ SMTP error: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Send error: {e}")
        return False


def log_application(
    db          : Session,
    user_id     : int,
    job_id      : int  = None,
    company_id  : int  = None,
    contact_id  : int  = None,
    subject     : str  = "",
    body        : str  = "",
    resume_path : str  = None,
    ats_before  : float = None,
    ats_after   : float = None
) -> Application:
    """
    Email bhejne ke baad application DB mein log karo.

    Why log karna zaroori hai?
    → Follow-up ke liye track karna hai
    → Reply detect karne ke liye reference chahiye
    → User ko dashboard pe dikhana hai
    → Google Sheets sync ke liye
    """
    from datetime import datetime, timedelta

    app = Application(
        user_id           = user_id,
        job_id            = job_id,
        company_id        = company_id,
        contact_id        = contact_id,
        email_subject     = subject,
        email_body        = body,
        resume_version    = resume_path,
        sent_date         = datetime.utcnow(),
        status            = "email_sent",
        follow_up_count   = 0,
        ats_score_before  = ats_before,
        ats_score_after   = ats_after,
    )

    db.add(app)
    db.commit()
    db.refresh(app)

    logger.info(f"  📝 Application logged — ID: {app.id}")
    return app


def send_and_log(
    db          : Session,
    user_id     : int,
    to_email    : str,
    subject     : str,
    body        : str,
    resume_path : str  = None,
    job_id      : int  = None,
    company_id  : int  = None,
    contact_id  : int  = None,
    ats_before  : float = None,
    ats_after   : float = None
) -> dict:
    """
    Main function:
    1. Gmail credentials lo
    2. Email bhejo
    3. Application log karo
    4. Result return karo
    """
    gmail, password = get_gmail_credentials(db, user_id)

    if not gmail or not password:
        return {
            "success": False,
            "error"  : "Gmail credentials nahi hain — profile mein daalo"
        }

    if not to_email:
        return {
            "success": False,
            "error"  : "Recipient email missing"
        }

    # Email bhejo
    sent = send_email(
        gmail_address = gmail,
        app_password  = password,
        to_email      = to_email,
        subject       = subject,
        body          = body,
        resume_path   = resume_path
    )

    if not sent:
        return {
            "success": False,
            "error"  : "Email send nahi hua — Gmail settings check karo"
        }

    # Log karo
    app = log_application(
        db          = db,
        user_id     = user_id,
        job_id      = job_id,
        company_id  = company_id,
        contact_id  = contact_id,
        subject     = subject,
        body        = body,
        resume_path = resume_path,
        ats_before  = ats_before,
        ats_after   = ats_after
    )

    return {
        "success"       : True,
        "application_id": app.id,
        "message"       : f"Email sent to {to_email}"
    }