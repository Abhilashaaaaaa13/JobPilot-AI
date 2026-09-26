# backend/api/routes_replies.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.models.user import User
from backend.api.auth import get_current_user

router = APIRouter(prefix="/api/replies", tags=["replies"])


@router.get("/notifications")
def notifications(user: User = Depends(get_current_user)):
    from backend.pipeline.reply_handler import NotificationManager
    all_notifs = NotificationManager.get_pending_notifications(user.id)
    return {"notifications": [n for n in all_notifs if n["type"] == "reply_received"]}


@router.post("/notifications/{notif_id}/read")
def mark_read(notif_id: int, user: User = Depends(get_current_user)):
    from backend.pipeline.reply_handler import NotificationManager
    ok = NotificationManager.mark_as_read(notif_id)
    return {"success": ok}


@router.get("/drafts")
def drafts(user: User = Depends(get_current_user)):
    from backend.pipeline.reply_handler import DraftApprovalManager
    return {"drafts": DraftApprovalManager.get_pending_drafts(user.id)}


class ApproveBody(BaseModel):
    subject: str
    body: str


@router.post("/drafts/{sent_email_id}/approve")
def approve_draft(sent_email_id: int, body: ApproveBody, user: User = Depends(get_current_user)):
    from backend.pipeline.reply_handler import DraftApprovalManager
    result = DraftApprovalManager.approve_and_send(
        sent_email_id=sent_email_id, final_subject=body.subject, final_body=body.body, user_id=user.id,
    )
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Send failed"))
    return result


@router.post("/drafts/{sent_email_id}/reject")
def reject_draft(sent_email_id: int, user: User = Depends(get_current_user)):
    from backend.pipeline.reply_handler import DraftApprovalManager
    ok = DraftApprovalManager.reject_draft(sent_email_id)
    return {"success": ok}
