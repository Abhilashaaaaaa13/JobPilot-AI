# backend/agents/followup_agent.py
# Auto follow-up bhejo
# 4 din baad agar reply nahi aaya

from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from backend.models.application import Application
from backend.models.user import UserProfile, User
from backend.agents.email_generator import generate_followup_email
from backend.agents.email_sender import send_email, get_gmail_credentials
from backend.config import MAX_FOLLOWUPS
from loguru import logger


def check_and_send_followups(
    db      : Session,
    user_id : int
) -> dict:
    """
    Follow-up bhejne ki logic:

    1. Applications dhundho jo:
       → email_sent status hai
       → X din se purani hai (user setting)
       → Max followups nahi bheje

    2. Har ek ke liye:
       → Follow-up email generate karo
       → Gmail se bhejo
       → Status + count update karo

    Why max 2 followups?
    Zyada follow-up = annoying = spam mark.
    2 = enough to show interest,
    not enough to be desperate.
    """
    profile = db.query(UserProfile).filter(
        UserProfile.user_id == user_id
    ).first()

    followup_days = profile.followup_after_days \
                   if profile else 4
    max_followups = profile.max_followups \
                   if profile else MAX_FOLLOWUPS

    # Cutoff date calculate karo
    cutoff = datetime.utcnow() - timedelta(days=followup_days)

    # Eligible applications
    applications = db.query(Application).filter(
        Application.user_id == user_id,
        Application.status.in_([
            "email_sent",
            "follow_up_1_sent"
        ]),
        Application.follow_up_count < max_followups,
        Application.sent_date <= cutoff
    ).all()

    if not applications:
        logger.info("No applications need follow-up")
        return {"sent": 0}

    gmail, password = get_gmail_credentials(db, user_id)
    if not gmail or not password:
        return {"error": "Gmail credentials missing"}

    sent_count = 0

    for app in applications:
        try:
            # Follow-up email generate karo
            followup = generate_followup_email(
                db             = db,
                application_id = app.id
            )

            if followup.get("error"):
                logger.warning(
                    f"  ⚠️ Followup gen failed "
                    f"app {app.id}: {followup['error']}"
                )
                continue

            to_email = followup.get("contact_email")
            if not to_email:
                logger.warning(
                    f"  ⚠️ No email for app {app.id}"
                )
                continue

            # Send karo
            sent = send_email(
                gmail_address = gmail,
                app_password  = password,
                to_email      = to_email,
                subject       = followup["subject"],
                body          = followup["body"],
                resume_path   = app.resume_version
            )

            if sent:
                # Status update karo
                app.follow_up_count   += 1
                app.last_followup_date = datetime.utcnow()

                if app.follow_up_count == 1:
                    app.status = "follow_up_1_sent"
                elif app.follow_up_count >= 2:
                    app.status = "follow_up_2_sent"

                db.commit()
                sent_count += 1

                logger.info(
                    f"  ✅ Follow-up {app.follow_up_count} "
                    f"sent for app {app.id}"
                )

        except Exception as e:
            logger.error(
                f"  ❌ Followup failed app {app.id}: {e}"
            )
            continue

    # Max followups ke baad ghosted mark karo
    ghosted = db.query(Application).filter(
        Application.user_id == user_id,
        Application.status  == "follow_up_2_sent",
        Application.follow_up_count >= max_followups,
        Application.last_followup_date <= cutoff
    ).all()

    for app in ghosted:
        app.status = "ghosted"

    if ghosted:
        db.commit()
        logger.info(f"  👻 {len(ghosted)} applications marked ghosted")

    return {
        "followups_sent": sent_count,
        "ghosted"       : len(ghosted)
    }