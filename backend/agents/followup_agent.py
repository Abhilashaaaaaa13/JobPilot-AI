# backend/agents/followup_agent.py

import os
import json
from datetime import datetime, timedelta
from loguru   import logger
from dotenv   import load_dotenv
load_dotenv()

FOLLOWUP_AFTER_DAYS = int(os.getenv("FOLLOWUP_AFTER_DAYS", 4))
MAX_FOLLOWUPS       = int(os.getenv("MAX_FOLLOWUPS",        2))


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


def check_and_send_followups(user_id: int) -> dict:
    """
    4 din baad reply nahi aaya → follow up bhejo.
    Max 2 follow ups per email.
    Sheets mein log karo.
    """
    from backend.agents.email_sender    import send_email
    from backend.agents.email_generator import generate_followup_email

    sent_log = get_sent_log(user_id)
    if not sent_log:
        return {"followups_sent": 0, "emails": []}

    now            = datetime.utcnow()
    followups_sent = 0
    sent_emails    = []

    for entry in sent_log:
        # Skip agar reply aa gaya
        if entry.get("replied"):
            continue

        # Skip agar max followups ho gaye
        followup_count = entry.get("followup_count", 0)
        if followup_count >= MAX_FOLLOWUPS:
            continue

        # Kitne din ho gaye
        try:
            sent_at  = datetime.fromisoformat(entry["sent_at"])
            days_ago = (now - sent_at).days
        except:
            continue

        # Last followup ke baad kitne din
        last_followup = entry.get("followup_at")
        if last_followup:
            try:
                last_dt         = datetime.fromisoformat(last_followup)
                days_since_last = (now - last_dt).days
                if days_since_last < FOLLOWUP_AFTER_DAYS:
                    continue
            except:
                pass
        else:
            if days_ago < FOLLOWUP_AFTER_DAYS:
                continue

        logger.info(
            f"  🔄 Follow up for {entry['to']} "
            f"({days_ago} days ago)"
        )

        contact = {
            "name" : entry.get("contact", "Founder"),
            "role" : "",
            "email": entry["to"]
        }

        # Follow up email generate karo
        followup = generate_followup_email(
            user_id         = user_id,
            company         = entry.get("company", ""),
            contact         = contact,
            original_subject= entry.get("subject", ""),
            original_body   = entry.get("body",    ""),
            days_ago        = days_ago
        )

        if followup.get("error"):
            logger.error(f"Generate error: {followup['error']}")
            continue

        # Send karo
        result = send_email(
            user_id = user_id,
            to_email= entry["to"],
            subject = followup["subject"],
            body    = followup["body"],
            company = entry.get("company", ""),
            contact = entry.get("contact", "")
        )

        if result.get("success"):
            entry["followup_sent"]   = True
            entry["followup_at"]     = datetime.utcnow().isoformat()
            entry["followup_count"]  = followup_count + 1
            entry["status"]          = "followup_sent"

            followups_sent += 1
            sent_emails.append({
                "to"     : entry["to"],
                "company": entry.get("company", ""),
                "subject": followup["subject"]
            })

            logger.info(f"  ✅ Follow up sent to {entry['to']}")

            # ── Google Sheets update ──────────────
            try:
                from backend.utils.sheets_tracker import log_followup
                log_followup(
                    user_id         = user_id,
                    company         = entry.get("company", ""),
                    contact_email   = entry["to"],
                    original_subject= entry.get("subject", ""),
                    followup_subject= followup["subject"],
                    new_value       = followup.get("new_value_added", "")
                )
            except Exception as e:
                logger.warning(f"Sheets followup log error: {e}")

        else:
            logger.error(f"  ❌ Failed: {result.get('error')}")

    if followups_sent > 0:
        save_sent_log(user_id, sent_log)

    logger.info(f"[Followup] {followups_sent} sent")

    return {
        "followups_sent": followups_sent,
        "emails"        : sent_emails
    }


def run_for_all_users() -> dict:
    """Sab users ke liye — scheduler se call hota hai."""
    from backend.agents.reply_detector import get_all_users_with_sent_emails

    users   = get_all_users_with_sent_emails()
    total   = 0
    results = {}

    for user_id in users:
        try:
            result           = check_and_send_followups(user_id)
            results[user_id] = result
            total           += result.get("followups_sent", 0)
        except Exception as e:
            logger.error(f"User {user_id} error: {e}")
            results[user_id] = {"error": str(e)}

    logger.info(f"[Followup] Total: {total}")
    return {"total_followups": total, "by_user": results}