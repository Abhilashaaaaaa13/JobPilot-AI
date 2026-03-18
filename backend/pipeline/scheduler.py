from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from backend.database import SessionLocal
from backend.agents import reply_detector,followup_agent
from backend.config import REPLY_CHECK_INTERVAL
from loguru import logger

def check_all_replies():
    """
    Checks Gmail inbox for all active users.
    Runs every 6 hours.
    
    Why session per job?
    APScheduler runs jobs in separate threads.
    SQLAlchemy sessions are not thread-safe.
    Create new session per job = safe.
    Close session after = no leaks.
    """
    from backend.models.user import User

    db = SessionLocal()
    try:
        users = db.query(User).filter(
            User.is_active == True
        ).all()

        for user in users:
            try:
                result = reply_detector.check_inbox(
                    db      = db,
                    user_id = user.id
                )
                logger.info(
                    f"Reply check user {user.id}: "
                    f"{result.get('replies_found', 0)} found"
                )
            except Exception as e:
                logger.error(
                    f"Reply check failed user {user.id}: {e}"
                )
                continue
    finally:
        db.close()


def send_all_followups():
    """
    Sends follow-up emails for all active users.
    Runs every 12 hours.
    """
    from backend.models.user import User

    db = SessionLocal()
    try:
        users = db.query(User).filter(
            User.is_active == True
        ).all()

        for user in users:
            try:
                result = followup_agent.check_and_send_followups(
                    db      = db,
                    user_id = user.id
                )
                logger.info(
                    f"Followup user {user.id}: "
                    f"{result.get('followups_sent', 0)} sent"
                )
            except Exception as e:
                logger.error(
                    f"Followup failed user {user.id}: {e}"
                )
                continue
    finally:
        db.close()


def daily_scrape_all_users():
    """
    Triggers scraping for all users daily at 2 AM.
    Does not run full pipeline — just scraping.
    User manually triggers full pipeline when ready.
    
    Why only scraping and not full pipeline?
    Full pipeline requires human approval.
    Cannot auto-run something that needs user input.
    Fresh data daily = user always has latest jobs.
    """
    from backend.models.user import User
    from backend.agents import scraper_agent

    db = SessionLocal()
    try:
        users = db.query(User).filter(
            User.is_active == True
        ).all()

        for user in users:
            try:
                scraper_agent.run(
                    db      = db,
                    user_id = user.id
                )
                logger.info(f"Daily scrape done for user {user.id}")
            except Exception as e:
                logger.error(
                    f"Daily scrape failed user {user.id}: {e}"
                )
                continue
    finally:
        db.close()


def create_scheduler() -> BackgroundScheduler:
    """
    Creates and configures the scheduler.
    Called once on app startup.
    """
    scheduler = BackgroundScheduler(
        timezone="Asia/Kolkata"
    )

    # Reply check — every 6 hours
    scheduler.add_job(
        func    = check_all_replies,
        trigger = IntervalTrigger(hours=REPLY_CHECK_INTERVAL),
        id      = "reply_checker",
        name    = "Check Gmail for replies",
        replace_existing = True
    )

    # Follow-up sender — every 12 hours
    scheduler.add_job(
        func    = send_all_followups,
        trigger = IntervalTrigger(hours=12),
        id      = "followup_sender",
        name    = "Send follow-up emails",
        replace_existing = True
    )

    # Daily scrape — 2 AM IST
    scheduler.add_job(
        func    = daily_scrape_all_users,
        trigger = CronTrigger(hour=2, minute=0),
        id      = "daily_scraper",
        name    = "Daily job scraping",
        replace_existing = True
    )

    return scheduler