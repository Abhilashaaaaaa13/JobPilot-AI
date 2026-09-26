# backend/api/routes_companies.py
import threading

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from loguru import logger

from backend.models.user import User
from backend.api.auth import get_current_user

router = APIRouter(prefix="/api/companies", tags=["companies"])

# In-memory scrape progress, keyed by user_id. Fine at this app's scale
# (single instance); would need a shared store (Redis etc.) if ever scaled out.
_SCRAPE_STATE: dict[int, dict] = {}


def _sorted_feed(user_id: int) -> list:
    from backend.utils.feed_to_db import load_feed_companies
    companies = load_feed_companies(user_id, limit=60)
    # Companies with a findable email first — those are ready for outreach right now.
    return sorted(companies, key=lambda c: not any(ct.get("email") for ct in c.get("contacts", [])))


@router.get("/feed")
def get_feed(user: User = Depends(get_current_user)):
    return {"companies": _sorted_feed(user.id)}


def _run_scrape(user_id: int, prefs: dict):
    state = _SCRAPE_STATE[user_id]
    try:
        from backend.agents.scraper_agent import scraper_agent
        from backend.utils.feed_to_db import save_companies_bulk, sync_feed_json

        companies = scraper_agent(prefs)
        added = save_companies_bulk(user_id, companies)
        sync_feed_json(user_id)
        state["new"] = added
        state["total"] = len(companies)
    except Exception as e:
        logger.error(f"Scrape error for user {user_id}: {e}")
        state["error"] = str(e)
    finally:
        state["running"] = False
        state["done"] = True


@router.post("/scrape")
def start_scrape(user: User = Depends(get_current_user)):
    existing = _SCRAPE_STATE.get(user.id)
    if existing and existing.get("running"):
        return {"already_running": True}

    prefs = {
        "domains": ["ai_ml", "saas", "developer_tools"],
        "target_roles": ["founder", "ceo", "engineer", "ai engineer"],
        "location": "remote",
    }
    _SCRAPE_STATE[user.id] = {"running": True, "done": False, "new": 0, "total": 0, "error": None}
    threading.Thread(target=_run_scrape, args=(user.id, prefs), daemon=True).start()
    return {"started": True}


@router.get("/scrape/status")
def scrape_status(user: User = Depends(get_current_user)):
    return _SCRAPE_STATE.get(user.id, {"running": False, "done": False, "new": 0, "total": 0, "error": None})


@router.post("/{company_id}/draft")
def draft_email(company_id: int, user: User = Depends(get_current_user)):
    from backend.utils.feed_to_db import load_feed_companies
    from backend.agents.email_generator import generate_cold_email

    company = next((c for c in load_feed_companies(user.id, limit=200) if c["id"] == company_id), None)
    if not company:
        raise HTTPException(404, "Company not found")

    contacts = company.get("contacts", [])
    contact = next((c for c in contacts if c.get("email")), None)
    if not contact:
        raise HTTPException(400, "No contact email found for this company")

    result = generate_cold_email(
        user_id=user.id, company=company["name"],
        description=company.get("description", ""), one_liner=company.get("one_liner", ""),
        contact=contact, ai_hook=company.get("ai_hook", ""),
        recent_highlight=company.get("recent_highlight", ""), tech_stack=company.get("tech_stack", []),
    )
    if result.get("error"):
        raise HTTPException(500, result["error"])

    return {
        "contact_name": contact.get("name", ""), "contact_role": contact.get("role", ""),
        "contact_email": contact.get("email", ""), "subject": result.get("subject", ""),
        "body": result.get("body", ""), "gap": result.get("gap", ""),
        "proposal": result.get("proposal", ""), "why_fits": result.get("why_fits", ""),
    }


class SendEmailBody(BaseModel):
    contact_email: str
    subject: str
    body: str
    contact_name: str = ""
    contact_role: str = ""
    gap: str = ""
    proposal: str = ""


@router.post("/{company_id}/send")
def send_company_email(company_id: int, body: SendEmailBody, user: User = Depends(get_current_user)):
    import os
    from backend.utils.feed_to_db import load_feed_companies, mark_company_contacted
    from backend.agents.email_sender import send_email
    from backend.database import SessionLocal
    from backend.models.user import UserProfile

    company = next((c for c in load_feed_companies(user.id, limit=200) if c["id"] == company_id), None)
    if not company:
        raise HTTPException(404, "Company not found")

    resume_path = ""
    db = SessionLocal()
    try:
        prof = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
        if prof and prof.resume_path and os.path.exists(prof.resume_path):
            resume_path = prof.resume_path
    finally:
        db.close()

    result = send_email(
        user_id=user.id, to_email=body.contact_email, subject=body.subject, body=body.body,
        resume_path=resume_path, company=company["name"], contact=body.contact_name,
        contact_role=body.contact_role, gap=body.gap, proposal=body.proposal,
        website=company.get("website", ""),
    )
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Send failed"))

    mark_company_contacted(user.id, company_id)
    return {"success": True, "sent_at": result.get("sent_at")}


@router.post("/{company_id}/skip")
def skip_company(company_id: int, user: User = Depends(get_current_user)):
    from backend.utils.feed_to_db import mark_company_contacted
    mark_company_contacted(user.id, company_id)
    return {"success": True}
