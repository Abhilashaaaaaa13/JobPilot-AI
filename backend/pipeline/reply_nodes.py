# backend/pipeline/reply_nodes.py
# ═══════════════════════════════════════════════════════════════════════════════
# LangGraph NODES for Reply Handling
# ═══════════════════════════════════════════════════════════════════════════════
# These nodes handle:
# 1. Check replies (runs in background via scheduler)
# 2. Draft approval (user interaction)
# 3. Send approved replies
# ═══════════════════════════════════════════════════════════════════════════════

from loguru import logger
from backend.pipeline.state import TrackBState
from backend.pipeline.reply_handler import (
    ReplyDetector,
    AutoDraftGenerator,
    ReplyStorage,
    NotificationManager,
    DraftApprovalManager
)


# ═════════════════════════════════════════════════════════════════════════════
# NODE 1: CHECK INBOX FOR REPLIES (Scheduler calls this)
# ═════════════════════════════════════════════════════════════════════════════

def check_inbox_for_replies_node(state: TrackBState) -> dict:
    """
    Check Gmail inbox for replies to sent cold emails.
    Auto-generate drafts.
    Create notifications.
    
    Called by: Scheduler every 6 hours (automatic)
    No manual trigger needed.
    
    Returns state update with:
    - new_replies: List of detected replies with drafts
    - notifications_created: Count
    """
    user_id = state.get("user_id")
    
    if not user_id:
        logger.warning("No user_id in state")
        return {
            "new_replies": [],
            "notifications_created": 0
        }
    
    logger.info(f"[ReplyCheck] Checking inbox for user {user_id}")
    
    try:
        detector = ReplyDetector(user_id)
        result = detector.check_inbox()
        
        if "error" in result:
            logger.error(f"[ReplyCheck] Error: {result['error']}")
            return {
                "new_replies": [],
                "notifications_created": 0,
                "errors": [result['error']]
            }
        
        replies = result.get("replies", [])
        new_replies = []
        notifs_created = 0
        
        for reply in replies:
            original = reply["original_email"]
            
            logger.info(f"  📩 Processing reply from {reply['from']}")
            
            # Generate auto-draft
            draft = AutoDraftGenerator.generate_reply_draft(
                user_id=user_id,
                incoming_from=reply["from"],
                incoming_subject=reply["subject"],
                incoming_body=reply["body"],
                original_subject=original.subject,
                original_body=original.body,
                company=original.company
            )
            
            # Save to DB
            if ReplyStorage.save_reply_with_draft(
                sent_email_id=original.id,
                reply_from=reply["from"],
                reply_subject=reply["subject"],
                reply_body=reply["body"],
                auto_draft=draft
            ):
                # Create notification
                if NotificationManager.create_notification(
                    user_id=user_id,
                    notif_type="reply_received",
                    title=f"📩 {original.company or reply['from']}",
                    message=f"Subject: {reply['subject'][:60]}",
                    data={
                        "sent_email_id": original.id,
                        "from": reply["from"],
                        "company": original.company,
                        "subject": reply["subject"]
                    }
                ):
                    notifs_created += 1
                
                new_replies.append({
                    "id": original.id,
                    "from": reply["from"],
                    "company": original.company,
                    "draft": draft
                })
                
                logger.info(f"    ✅ Reply saved + notified")
        
        logger.info(f"[ReplyCheck] Found {len(new_replies)} new replies")
        
        return {
            "new_replies": new_replies,
            "notifications_created": notifs_created
        }
    
    except Exception as e:
        logger.error(f"[ReplyCheck] Error: {e}", exc_info=True)
        return {
            "new_replies": [],
            "notifications_created": 0,
            "errors": [str(e)]
        }


# ═════════════════════════════════════════════════════════════════════════════
# NODE 2: DRAFT APPROVAL (User interaction)
# ═════════════════════════════════════════════════════════════════════════════

def approve_reply_draft_node(state: TrackBState) -> dict:
    """
    User approves a reply draft (with optional edits).
    Send the approved reply.
    Update DB.
    
    Called by: Frontend when user clicks "Send"
    Receives: sent_email_id, final_subject, final_body
    
    Returns: {success: bool, email_id: int}
    """
    user_id = state.get("user_id")
    approved_drafts = state.get("approved_reply_drafts", [])
    
    if not approved_drafts:
        return {"approved_count": 0}
    
    logger.info(f"[DraftApproval] Processing {len(approved_drafts)} approved drafts")
    
    sent_count = 0
    
    for draft_info in approved_drafts:
        try:
            sent_email_id = draft_info.get("sent_email_id")
            final_subject = draft_info.get("subject")
            final_body = draft_info.get("body")
            
            if not all([sent_email_id, final_subject, final_body]):
                logger.warning(f"Incomplete draft approval data: {draft_info}")
                continue
            
            result = DraftApprovalManager.approve_and_send(
                sent_email_id=sent_email_id,
                final_subject=final_subject,
                final_body=final_body,
                user_id=user_id
            )
            
            if result.get("success"):
                logger.info(f"  ✅ Reply approved & sent (ID: {sent_email_id})")
                sent_count += 1
            else:
                logger.error(f"  ❌ Send failed: {result.get('error')}")
        
        except Exception as e:
            logger.error(f"Draft approval error: {e}")
            continue
    
    return {"approved_count": sent_count}


# ═════════════════════════════════════════════════════════════════════════════
# NODE 3: REJECT DRAFT (User rejects auto-draft)
# ═════════════════════════════════════════════════════════════════════════════

def reject_reply_draft_node(state: TrackBState) -> dict:
    """
    User rejected auto-draft.
    Mark for manual reply.
    
    Called by: Frontend when user clicks "Reject"
    """
    rejected_ids = state.get("rejected_reply_drafts", [])
    
    if not rejected_ids:
        return {"rejected_count": 0}
    
    logger.info(f"[DraftRejection] Rejecting {len(rejected_ids)} drafts")
    
    rejected_count = 0
    for sent_email_id in rejected_ids:
        if DraftApprovalManager.reject_draft(sent_email_id):
            logger.info(f"  ❌ Draft {sent_email_id} marked for manual reply")
            rejected_count += 1
    
    return {"rejected_count": rejected_count}


# ═════════════════════════════════════════════════════════════════════════════
# CONDITIONAL EDGES
# ═════════════════════════════════════════════════════════════════════════════

def check_if_drafts_pending(state: TrackBState) -> str:
    """
    Check if user has pending draft approvals.
    Routes to draft approval flow.
    """
    pending = DraftApprovalManager.get_pending_drafts(
        state.get("user_id")
    )
    
    if pending:
        return "draft_approval_pending"
    return "no_drafts"


def check_new_replies(state: TrackBState) -> str:
    """
    Check if new replies detected.
    Routes to notification display.
    """
    new_replies = state.get("new_replies", [])
    
    if new_replies:
        return "has_replies"
    return "no_replies"


# ═════════════════════════════════════════════════════════════════════════════
# INTEGRATION: Add to your graph.py
# ═════════════════════════════════════════════════════════════════════════════

"""
In your backend/pipeline/graph.py, add these nodes:

from backend.pipeline.reply_nodes import (
    check_inbox_for_replies_node,
    approve_reply_draft_node,
    reject_reply_draft_node
)

# Add nodes to graph
graph.add_node("check_inbox_replies",    check_inbox_for_replies_node)
graph.add_node("approve_reply_draft",    approve_reply_draft_node)
graph.add_node("reject_reply_draft",     reject_reply_draft_node)

# Add edges (example)
graph.add_edge("send_emails",            "check_inbox_replies")  # After sending emails
graph.add_conditional_edges(
    "check_inbox_replies",
    check_new_replies,
    {
        "has_replies": "notify_user",
        "no_replies": END
    }
)
"""