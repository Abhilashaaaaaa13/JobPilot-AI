# backend/utils/feed_to_db.py
"""
Single source of truth for company storage.

  save_feed_company_to_db(user_id, dict)  → (obj, id)
  save_companies_bulk(user_id, list)       → new_count
  load_feed_companies(user_id, limit)      → list[dict]  (uncontacted only)
  mark_company_contacted(user_id, co_id)  → None
  sync_feed_json(user_id)                 → None
"""

import json, os
from datetime import datetime, timezone
from loguru import logger
from backend.database import SessionLocal


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────
# UPSERT ONE
# ─────────────────────────────────────────────

def save_feed_company_to_db(user_id: int, company: dict) -> tuple:
    from backend.models.company import Company
    db = SessionLocal()
    try:
        name = (company.get("name") or "").strip()
        if not name:
            return None, -1

        existing = db.query(Company).filter(
            Company.user_id == user_id, Company.name == name
        ).first()
        if existing:
            return existing, existing.id

        obj = Company(
            user_id          = user_id,
            name             = name,
            website          = (company.get("website") or "").strip(),
            description      = company.get("description") or company.get("one_liner") or "",
            one_liner        = company.get("one_liner", ""),
            funding          = company.get("funding", ""),
            team_size        = str(company.get("team_size", "")),
            location         = company.get("location", ""),
            source           = company.get("source", ""),
            ai_hook          = company.get("ai_hook", ""),
            recent_highlight = company.get("recent_highlight", ""),
            tech_stack       = json.dumps(company.get("tech_stack", [])),
            github_url       = company.get("github_url", ""),
            github_stars     = company.get("github_stars") or 0,
            contacts_json    = json.dumps(company.get("contacts", [])),
            feed_added_at    = _utcnow(),
            contacted_at     = None,
        )
        db.add(obj)
        db.commit()
        db.refresh(obj)
        logger.debug(f"DB saved: '{name}' id={obj.id}")
        return obj, obj.id
    except Exception as e:
        db.rollback()
        logger.error(f"save_feed_company_to_db error '{company.get('name')}': {e}")
        return None, -1
    finally:
        db.close()


# ─────────────────────────────────────────────
# LOAD UNCONTACTED (for UI)
# ─────────────────────────────────────────────

def load_feed_companies(user_id: int, limit: int = 60) -> list:
    from backend.models.company import Company
    db = SessionLocal()
    try:
        rows = (
            db.query(Company)
            .filter(Company.user_id == user_id, Company.contacted_at == None)  # noqa
            .order_by(Company.feed_added_at.desc())
            .limit(limit)
            .all()
        )
        return [_row_to_dict(r) for r in rows]
    except Exception as e:
        logger.error(f"load_feed_companies error: {e}")
        return []
    finally:
        db.close()


def _row_to_dict(row) -> dict:
    try:    contacts   = json.loads(row.contacts_json or "[]")
    except: contacts   = []
    try:    tech_stack = json.loads(row.tech_stack or "[]")
    except: tech_stack = []
    return {
        "id"              : row.id,
        "name"            : row.name or "",
        "website"         : row.website or "",
        "description"     : row.description or "",
        "one_liner"       : row.one_liner or "",
        "funding"         : row.funding or "",
        "team_size"       : row.team_size or "",
        "location"        : row.location or "",
        "source"          : row.source or "",
        "ai_hook"         : row.ai_hook or "",
        "recent_highlight": row.recent_highlight or "",
        "tech_stack"      : tech_stack,
        "github_url"      : row.github_url or "",
        "github_stars"    : row.github_stars or 0,
        "contacts"        : contacts,
        "feed_added_at"   : row.feed_added_at or "",
    }


# ─────────────────────────────────────────────
# MARK CONTACTED
# ─────────────────────────────────────────────

def mark_company_contacted(user_id: int, co_id: int):
    from backend.models.company import Company
    db = SessionLocal()
    try:
        row = db.query(Company).filter(
            Company.id == co_id, Company.user_id == user_id
        ).first()
        if row and not row.contacted_at:
            row.contacted_at = _utcnow()
            db.commit()
            logger.debug(f"DB contacted: id={co_id}")
    except Exception as e:
        db.rollback()
        logger.error(f"mark_company_contacted error: {e}")
    finally:
        db.close()


# ─────────────────────────────────────────────
# SYNC → company_feed.json
# ─────────────────────────────────────────────

def sync_feed_json(user_id: int):
    companies = load_feed_companies(user_id, limit=200)
    os.makedirs("data", exist_ok=True)
    with open("data/company_feed.json", "w", encoding="utf-8") as f:
        json.dump({"last_updated": _utcnow(), "companies": companies}, f, ensure_ascii=False, indent=2)
    logger.info(f"sync_feed_json: {len(companies)} companies written")