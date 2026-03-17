# backend/routers/emails.py

from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from backend.database import get_db
from backend.models.user import User
from backend.dependencies import get_current_user
from backend.agents import (
    email_generator,
    email_sender,
    reply_detector,
    followup_agent
)

router = APIRouter(prefix="/emails", tags=["emails"])


# ── Request Schema ────────────────────────────
class SendEmailRequest(BaseModel):
    type          : str              # "job_email" / "cold_email"
    contact_email : str
    subject       : str
    body          : str
    resume_path   : Optional[str]    = None
    job_id        : Optional[int]    = None
    company_id    : Optional[int]    = None
    contact_id    : Optional[int]    = None
    ats_before    : Optional[float]  = None
    ats_after     : Optional[float]  = None


# ── Generate ──────────────────────────────────

@router.get("/generate/job/{job_id}")
def generate_job_email(
    job_id      : int,
    db          : Session = Depends(get_db),
    current_user: User    = Depends(get_current_user)
):
    return email_generator.generate_job_email(
        db      = db,
        user_id = current_user.id,
        job_id  = job_id
    )


@router.get("/generate/cold/{company_id}")
def generate_cold_email(
    company_id  : int,
    db          : Session = Depends(get_db),
    current_user: User    = Depends(get_current_user)
):
    return email_generator.generate_cold_email(
        db         = db,
        user_id    = current_user.id,
        company_id = company_id
    )


@router.get("/generate/followup/{application_id}")
def generate_followup(
    application_id: int,
    db            : Session = Depends(get_db),
    current_user  : User    = Depends(get_current_user)
):
    return email_generator.generate_followup_email(
        db             = db,
        application_id = application_id
    )


# ── Send ──────────────────────────────────────

@router.post("/send")
def send_email(
    req         : SendEmailRequest,
    db          : Session = Depends(get_db),
    current_user: User    = Depends(get_current_user)
):
    """
    Email bhejo + application log karo.
    User ne preview dekha + approve kiya
    tabhi ye endpoint call hota hai.
    """
    return email_sender.send_and_log(
        db          = db,
        user_id     = current_user.id,
        to_email    = req.contact_email,
        subject     = req.subject,
        body        = req.body,
        resume_path = req.resume_path,
        job_id      = req.job_id,
        company_id  = req.company_id,
        contact_id  = req.contact_id,
        ats_before  = req.ats_before,
        ats_after   = req.ats_after
    )


# ── Reply Detection ───────────────────────────

@router.post("/check-replies")
def check_replies(
    background_tasks: BackgroundTasks,
    db              : Session = Depends(get_db),
    current_user    : User    = Depends(get_current_user)
):
    """
    Inbox check karo — background mein.
    IMAP slow ho sakta hai.
    """
    background_tasks.add_task(
        reply_detector.check_inbox,
        db      = db,
        user_id = current_user.id
    )
    return {"message": "Inbox check shuru ho gaya"}


# ── Follow-up ─────────────────────────────────

@router.post("/followup/send")
def send_followups(
    background_tasks: BackgroundTasks,
    db              : Session = Depends(get_db),
    current_user    : User    = Depends(get_current_user)
):
    """
    Pending follow-ups bhejo.
    Background mein — multiple emails ho sakti hain.
    """
    background_tasks.add_task(
        followup_agent.check_and_send_followups,
        db      = db,
        user_id = current_user.id
    )
    return {"message": "Follow-ups check shuru ho gaye"}