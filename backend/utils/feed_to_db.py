# backend/utils/feed_to_db.py
# Feed company dict ko DB mein save karo (Company + Contacts)
# Agar already exist kare (by website/name) to skip — no duplicates

import json
from loguru import logger
from backend.database import SessionLocal
from backend.models.company import Company
from backend.models.contact import Contact


def _clean_domain(website: str) -> str:
    return (
        website.lower()
        .replace("https://", "")
        .replace("http://", "")
        .rstrip("/")
        .split("/")[0]
    )


def save_feed_company_to_db(user_id: int, company_dict: dict) -> tuple[bool, int]:
    """
    Feed dict se Company + Contacts DB mein save karo.
    Returns: (already_existed: bool, company_id: int)
    """
    db = SessionLocal()
    try:
        name    = (company_dict.get("name")    or "").strip()
        website = (company_dict.get("website") or "").strip()

        if not name:
            return False, -1

        # ── Duplicate check ──────────────────────
        existing = None
        if website:
            domain   = _clean_domain(website)
            existing = db.query(Company).filter(
                Company.website.ilike(f"%{domain}%")
            ).first()
        if not existing:
            existing = db.query(Company).filter(
                Company.name.ilike(name)
            ).first()

        if existing:
            logger.info(f"Company already in DB: {name} (id={existing.id})")
            return True, existing.id

        # ── Save Company ─────────────────────────
        co = Company(
            user_id          = user_id,
            name             = name,
            website          = website,
            one_liner        = company_dict.get("one_liner",        "")[:300],
            description      = company_dict.get("description",      "")[:1000],
            funding          = company_dict.get("funding",          ""),
            team_size        = str(company_dict.get("team_size",    "")),
            location         = company_dict.get("location",         ""),
            source           = company_dict.get("source",           "feed"),
            ai_related       = company_dict.get("ai_related",       False),
            tech_stack       = json.dumps(company_dict.get("tech_stack", [])),
            company_summary  = company_dict.get("company_summary",  ""),
            recent_highlight = company_dict.get("recent_highlight", ""),
            ai_hook          = company_dict.get("ai_hook",          ""),
        )
        db.add(co)
        db.flush()  # get co.id before commit

        # ── Save Contacts ─────────────────────────
        for ct in company_dict.get("contacts", []):
            email = (ct.get("email") or "").strip()
            cname = (ct.get("name")  or "").strip()
            if not email and not cname:
                continue

            # Fix www. in email domain
            if "@www." in email:
                email = email.replace("@www.", "@")

            contact = Contact(
                company_id       = co.id,
                name             = cname,
                role             = ct.get("role",   ""),
                email            = email,
                linkdin_url      = ct.get("linkedin_url", "") or ct.get("twitter", ""),
                confidence_score = 1.0 if ct.get("verified") else 0.5,
                source           = ct.get("source", "feed"),
                priority         = ct.get("priority", 5),
            )
            db.add(contact)

        db.commit()
        logger.info(f"Saved to DB: {name} (id={co.id})")
        return False, co.id

    except Exception as e:
        db.rollback()
        logger.error(f"save_feed_company_to_db error: {e}")
        return False, -1
    finally:
        db.close()


def get_company_with_contacts(company_id: int) -> dict | None:
    """DB se company dict banao (feed format mein) taaki outreach card use kar sake."""
    db = SessionLocal()
    try:
        co = db.query(Company).filter(Company.id == company_id).first()
        if not co:
            return None

        contacts = []
        for ct in co.contacts:
            contacts.append({
                "name"    : ct.name     or "",
                "role"    : ct.role     or "",
                "email"   : ct.email    or "",
                "verified": ct.confidence_score >= 1.0,
                "source"  : ct.source   or "",
                "priority": ct.priority or 5,
            })

        tech_stack = []
        try:
            tech_stack = json.loads(co.tech_stack or "[]")
        except Exception:
            pass

        return {
            "id"              : co.id,
            "name"            : co.name            or "",
            "website"         : co.website         or "",
            "one_liner"       : co.one_liner        or "",
            "description"     : co.description     or "",
            "company_summary" : co.company_summary  or "",
            "recent_highlight": co.recent_highlight or "",
            "ai_hook"         : co.ai_hook          or "",
            "tech_stack"      : tech_stack,
            "funding"         : co.funding          or "",
            "team_size"       : co.team_size        or "",
            "location"        : co.location         or "",
            "source"          : co.source           or "",
            "ai_related"      : co.ai_related       or False,
            "contacts"        : contacts,
        }
    except Exception as e:
        logger.error(f"get_company_with_contacts error: {e}")
        return None
    finally:
        db.close()