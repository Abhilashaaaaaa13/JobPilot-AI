# backend/api/routes_tracker.py
from fastapi import APIRouter, Depends

from backend.models.user import User
from backend.api.auth import get_current_user

router = APIRouter(prefix="/api/tracker", tags=["tracker"])


@router.get("/sent-emails")
def sent_emails(user: User = Depends(get_current_user)):
    from backend.agents.email_sender import get_sent_log
    return {"emails": get_sent_log(user.id)}


@router.post("/check-replies")
def check_replies(user: User = Depends(get_current_user)):
    from backend.pipeline.reply_handler import ReplyDetector, ReplyStorage, AutoDraftGenerator, NotificationManager

    detector = ReplyDetector(user.id)
    result = detector.check_inbox()
    if result.get("error"):
        return {"error": result["error"]}

    new_count = 0
    for reply in result.get("replies", []):
        original = reply["original_email"]
        draft = AutoDraftGenerator.generate_reply_draft(
            user_id=user.id, incoming_from=reply["from"], incoming_subject=reply["subject"],
            incoming_body=reply["body"], original_subject=original.subject,
            original_body=getattr(original, "body", ""), company=original.company,
        )
        saved = ReplyStorage.save_reply_with_draft(
            sent_email_id=original.id, reply_from=reply["from"], reply_subject=reply["subject"],
            reply_body=reply["body"], auto_draft=draft,
        )
        if saved:
            new_count += 1
            NotificationManager.create_notification(
                user_id=user.id, notif_type="reply_received",
                title=f"📩 Reply from {original.company or reply['from']}",
                message=f"Subject: {reply['subject'][:60]}",
                data={"sent_email_id": original.id, "from": reply["from"], "company": original.company,
                      "subject": reply["subject"], "body_preview": reply["body"][:200]},
            )

    return {"checked": len(result.get("replies", [])), "new": new_count}


@router.post("/send-followups")
def send_followups(user: User = Depends(get_current_user)):
    from backend.agents.followup_agent import check_and_send_followups
    result = check_and_send_followups(user.id)
    return result
