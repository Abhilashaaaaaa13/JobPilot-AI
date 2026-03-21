# backend/pipeline/scheduler.py

from apscheduler.schedulers.background import BackgroundScheduler
from loguru import logger


def create_scheduler():
    scheduler = BackgroundScheduler()

    # Har 6 ghante — reply check
    scheduler.add_job(
        func         = _check_all_replies,
        trigger      = "interval",
        hours        = 6,
        id           = "reply_check",
        replace_existing = True
    )

    # Har 12 ghante — followup check
    scheduler.add_job(
        func         = _check_all_followups,
        trigger      = "interval",
        hours        = 12,
        id           = "followup_check",
        replace_existing = True
    )

    return scheduler


def _check_all_replies():
    """Sab users ke inbox check karo."""
    try:
        from backend.agents.reply_detector import (
            get_all_users_with_sent_emails,
            check_inbox
        )
        users = get_all_users_with_sent_emails()
        for user_id in users:
            try:
                result = check_inbox(user_id)
                if result.get("replies", 0) > 0:
                    logger.info(
                        f"[Scheduler] User {user_id}: "
                        f"{result['replies']} new replies"
                    )
            except Exception as e:
                logger.error(
                    f"Reply check error user {user_id}: {e}"
                )
    except Exception as e:
        logger.error(f"Reply scheduler error: {e}")


def _check_all_followups():
    """Sab users ke followups check karo."""
    try:
        from backend.agents.followup_agent import run_for_all_users
        result = run_for_all_users()
        logger.info(
            f"[Scheduler] Followups: "
            f"{result.get('total_followups', 0)} sent"
        )
    except Exception as e:
        logger.error(f"Followup scheduler error: {e}")