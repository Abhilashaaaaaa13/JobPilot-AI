# backend/pipeline/scheduler.py (UPDATED for your setup)
# ═══════════════════════════════════════════════════════════════════════════════
# BACKGROUND JOB SCHEDULER (Groq + LangGraph integrated)
# ═══════════════════════════════════════════════════════════════════════════════
# Features:
# - Runs automatically in background (no manual trigger needed)
# - Check replies every 6 hours + auto-draft
# - Send follow-ups every 12 hours
# - Refresh company feed daily
# ═══════════════════════════════════════════════════════════════════════════════

from apscheduler.schedulers.background import BackgroundScheduler
from loguru import logger


def create_scheduler():
    """
    Create and return scheduler.
    Automatically starts when called.
    """
    scheduler = BackgroundScheduler()
    
    # ─────────────────────────────────────────────
    # JOB 1: CHECK REPLIES + AUTO-DRAFT (every 6h)
    # ─────────────────────────────────────────────
    scheduler.add_job(
        func             = _check_and_handle_replies,
        trigger          = "interval",
        hours            = 12,
        id               = "check_replies_with_draft",
        replace_existing = True
    )
    
    # ─────────────────────────────────────────────
    # JOB 2: SEND FOLLOW-UPS (every 12h)
    # ─────────────────────────────────────────────
    scheduler.add_job(
        func             = _send_followups,
        trigger          = "interval",
        days            = 4,
        id               = "send_followups",
        replace_existing = True
    )
    
    # ─────────────────────────────────────────────
    # JOB 3: REFRESH COMPANY FEED (daily)
    # ─────────────────────────────────────────────
    scheduler.add_job(
        func             = _refresh_company_feed,
        trigger          = "interval",
        hours            = 24,
        id               = "company_feed_refresh",
        replace_existing = True
    )
    
    logger.info(f"✅ Scheduler created with {len(scheduler.get_jobs())} jobs")
    return scheduler


# ═════════════════════════════════════════════════════════════════════════════
# JOB IMPLEMENTATIONS
# ═════════════════════════════════════════════════════════════════════════════

def _check_and_handle_replies():
    """
    Check all users' Gmail inboxes for replies.
    Auto-generate drafts using Groq.
    Store in DB + create notifications.
    
    Runs: Every 6 hours automatically
    No manual trigger needed.
    """
    try:
        from backend.pipeline.reply_handler import check_and_handle_all_replies
        
        result = check_and_handle_all_replies()
        total = result.get("total_replies", 0)
        
        if total > 0:
            logger.info(f"✅ [Scheduler] Found {total} new replies")
        else:
            logger.debug("[Scheduler] No new replies")
        
        return result
    
    except Exception as e:
        logger.error(f"❌ [Scheduler] Reply check error: {e}", exc_info=True)
        return {"error": str(e)}


def _send_followups():
    """
    Check which emails need follow-ups.
    Criteria:
    - 1st followup: 4 days after send
    - 2nd followup: 7 days after 1st followup
    
    Auto-send intelligent follow-ups using Groq.
    
    Runs: Every 12 hours automatically
    """
    try:
        from backend.agents.followup_agent import get_all_users_with_sent_emails
        from backend.agents.followup_agent import check_and_send_followups
        
        users = get_all_users_with_sent_emails()
        total_followups = 0
        
        for user_id in users:
            try:
                result = check_and_send_followups(user_id)
                followups_sent = result.get("followups_sent", 0)
                
                if followups_sent > 0:
                    logger.info(f"✅ [Scheduler] User {user_id}: {followups_sent} FU sent")
                    total_followups += followups_sent
            
            except Exception as e:
                logger.error(f"❌ [Scheduler] User {user_id} FU error: {e}")
                continue
        
        if total_followups > 0:
            logger.info(f"✅ [Scheduler] Total followups sent: {total_followups}")
        
        return {"total_followups": total_followups}
    
    except Exception as e:
        logger.error(f"❌ [Scheduler] Followup job error: {e}", exc_info=True)
        return {"error": str(e)}


def _refresh_company_feed():
    """
    Refresh global company feed.
    Scrape YC, Product Hunt, Betalist, etc.
    Save to data/company_feed.json for frontend.
    
    Runs: Daily automatically
    """
    try:
        from backend.agents.feed_agent import refresh_feed
        
        result = refresh_feed()
        total = result.get("total", 0)
        new = result.get("new", 0)
        
        logger.info(f"✅ [Scheduler] Feed refreshed: {total} total, {new} new")
        return result
    
    except Exception as e:
        logger.error(f"❌ [Scheduler] Feed refresh error: {e}", exc_info=True)
        return {"error": str(e)}


# ═════════════════════════════════════════════════════════════════════════════
# HELPER: Start scheduler in background (called from frontend/app.py)
# ═════════════════════════════════════════════════════════════════════════════

def start_scheduler_if_needed():
    """
    Called once when app starts.
    Checks if scheduler is running, starts if not.
    """
    try:
        scheduler = create_scheduler()
        if not scheduler.running:
            scheduler.start()
            logger.info("🚀 Scheduler started in background")
        return scheduler
    except Exception as e:
        logger.error(f"❌ Failed to start scheduler: {e}")
        return None


# ═════════════════════════════════════════════════════════════════════════════
# DEBUG: Manual job triggers (for testing)
# ═════════════════════════════════════════════════════════════════════════════

def trigger_reply_check_now() -> dict:
    """
    Manually trigger reply check (for testing).
    Usually runs automatically every 6h.
    """
    logger.info("🔄 Manual trigger: reply check")
    return _check_and_handle_replies()


def trigger_followup_check_now() -> dict:
    """
    Manually trigger followup check (for testing).
    Usually runs automatically every 12h.
    """
    logger.info("🔄 Manual trigger: followup check")
    return _send_followups()


def trigger_feed_refresh_now() -> dict:
    """
    Manually trigger feed refresh (for testing).
    Usually runs automatically daily.
    """
    logger.info("🔄 Manual trigger: feed refresh")
    return _refresh_company_feed()


if __name__ == "__main__":
    # Test scheduler creation
    scheduler = create_scheduler()
    print(f"✅ Scheduler created with {len(scheduler.get_jobs())} jobs:")
    for job in scheduler.get_jobs():
        print(f"  ⏰ {job.id}: {job.trigger}")