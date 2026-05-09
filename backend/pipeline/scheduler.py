import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
from loguru import logger


def create_scheduler():
    """
    Create background scheduler for automated tasks:
    - Reply detection (every 6 hours)
    - Follow-up sending (every 12 hours)
    - Sheets sync (every 2 hours)
    """
    scheduler = BackgroundScheduler()

    # ─────────────────────────────────────────────
    # REPLY CHECK — every 6 hours
    # ─────────────────────────────────────────────
    def _check_replies_job():
        try:
            from backend.database import SessionLocal
            from backend.models.user import User
            from backend.pipeline.reply_handler import ReplyDetector, ReplyStorage, AutoDraftGenerator

            db = SessionLocal()
            users = db.query(User).filter(User.is_active == True).all()
            db.close()

            for user in users:
                try:
                    detector = ReplyDetector(user.id)
                    result = detector.check_inbox()

                    if result.get("error"):
                        logger.warning(f"User {user.id} reply check error: {result['error']}")
                        continue

                    replies = result.get("replies", [])
                    for reply in replies:
                        original = reply["original_email"]

                        draft = AutoDraftGenerator.generate_reply_draft(
                            user_id=user.id,
                            incoming_from=reply["from"],
                            incoming_subject=reply["subject"],
                            incoming_body=reply["body"],
                            original_subject=original.subject,
                            original_body=getattr(original, "body", ""),
                            company=original.company,
                        )

                        saved = ReplyStorage.save_reply_with_draft(
                            sent_email_id=original.id,
                            reply_from=reply["from"],
                            reply_subject=reply["subject"],
                            reply_body=reply["body"],
                            auto_draft=draft,
                        )

                        if saved:
                            # ✅ SYNC TO SHEETS AFTER REPLY SAVED
                            try:
                                from backend.utils.sheets_tracker import update_reply_status
                                update_reply_status(
                                    user_id=user.id,
                                    contact_email=reply["from"],
                                    reply_body=reply["body"],
                                )
                            except Exception as e:
                                logger.warning(f"Sheets sync failed for reply: {e}")

                    logger.info(f"✅ User {user.id}: {len(replies)} replies processed")

                except Exception as e:
                    logger.error(f"Reply check error for user {user.id}: {e}")

        except Exception as e:
            logger.error(f"Reply job error: {e}")

    scheduler.add_job(
        _check_replies_job,
        trigger=IntervalTrigger(hours=6),
        id="reply_check",
        name="Check Replies",
        replace_existing=True,
    )

    # ─────────────────────────────────────────────
    # FOLLOW-UP SENDING — every 12 hours
    # ─────────────────────────────────────────────
    def _check_followups_job():
        try:
            from backend.database import SessionLocal
            from backend.models.user import User
            from backend.agents.followup_agent import check_and_send_followups

            db = SessionLocal()
            users = db.query(User).filter(User.is_active == True).all()
            db.close()

            for user in users:
                try:
                    result = check_and_send_followups(user.id)
                    followups_sent = result.get("followups_sent", 0)

                    if followups_sent > 0:
                        # ✅ SYNC TO SHEETS AFTER FOLLOWUPS SENT
                        try:
                            from backend.utils.sheets_tracker import sync_sent_log_to_sheet
                            sync_result = sync_sent_log_to_sheet(user.id)
                            logger.info(
                                f"User {user.id}: {followups_sent} followups sent, "
                                f"{sync_result.get('synced', 0)} rows synced to sheets"
                            )
                        except Exception as e:
                            logger.warning(f"Sheets sync failed for followups: {e}")

                except Exception as e:
                    logger.error(f"Followup check error for user {user.id}: {e}")

        except Exception as e:
            logger.error(f"Followup job error: {e}")

    scheduler.add_job(
        _check_followups_job,
        trigger=IntervalTrigger(hours=12),
        id="followup_check",
        name="Check & Send Follow Ups",
        replace_existing=True,
    )

    # ─────────────────────────────────────────────
    # SHEETS SYNC — every 2 hours
    # ─────────────────────────────────────────────
    def _sheets_sync_job():
        try:
            from backend.database import SessionLocal
            from backend.models.user import User
            from backend.utils.sheets_tracker import sync_sent_log_to_sheet

            db = SessionLocal()
            users = db.query(User).filter(User.is_active == True).all()
            db.close()

            for user in users:
                try:
                    result = sync_sent_log_to_sheet(user.id)
                    synced = result.get("synced", 0)
                    if synced > 0:
                        logger.info(f"✅ User {user.id}: {synced} rows synced to sheets")
                except Exception as e:
                    logger.warning(f"Sheets sync error for user {user.id}: {e}")

        except Exception as e:
            logger.error(f"Sheets sync job error: {e}")

    scheduler.add_job(
        _sheets_sync_job,
        trigger=IntervalTrigger(hours=2),
        id="sheets_sync",
        name="Sync to Google Sheets",
        replace_existing=True,
    )

    return scheduler


if __name__ == "__main__":
    from backend.database import init_db
    init_db()

    scheduler = create_scheduler()
    scheduler.start()

    logger.info("=" * 60)
    logger.info("🚀 SCHEDULER STARTED")
    logger.info("=" * 60)
    logger.info("⏰ Jobs:")
    for job in scheduler.get_jobs():
        logger.info(f"   • {job.id}: {job.name} @ {job.trigger}")
    logger.info("=" * 60)
    logger.info("Ctrl+C to stop")
    logger.info("=" * 60)

    import signal
    import time

    def _shutdown(sig, frame):
        logger.info("🛑 Shutting down...")
        scheduler.shutdown(wait=False)
        import sys
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    while True:
        time.sleep(60)