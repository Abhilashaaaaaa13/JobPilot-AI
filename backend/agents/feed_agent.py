# backend/agents/feed_agent.py
#
# Global "New Startups" feed.
# Sources: YC + Betalist + Product Hunt + Indie Hackers + GitHub Trending + HN Hiring
# Scheduler se har 24 ghante call hota hai.
# Frontend data/company_feed.json read karta hai.

import re
import json
import os
import requests as req
from datetime import datetime, timezone
from loguru   import logger

FEED_PATH     = os.path.join("data", "company_feed.json")
MAX_COMPANIES = 200

_FEED_PREFS = {
    "domains"     : ["ai_ml", "data_science", "software", "full_stack", "backend"],
    "target_roles": [
        "engineer", "developer", "data scientist",
        "ml engineer", "ai engineer", "backend", "full stack"
    ],
    "location": "remote"
}


# ─────────────────────────────────────────────
# TEXT CLEANER
# ─────────────────────────────────────────────

def _fix_encoding(s: str) -> str:
    if not s or not isinstance(s, str):
        return s
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def _clean_str(s: str) -> str:
    if not s or not isinstance(s, str):
        return s
    s = _fix_encoding(s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def _clean_company(company: dict) -> dict:
    text_fields = [
        "name", "one_liner", "description", "company_summary",
        "recent_highlight", "ai_hook", "location", "funding", "team_size"
    ]
    cleaned = dict(company)
    for field in text_fields:
        if field in cleaned:
            cleaned[field] = _clean_str(cleaned[field])
    if cleaned.get("contacts"):
        clean_contacts = []
        for c in cleaned["contacts"]:
            cc = dict(c)
            for f in ["name", "role", "email"]:
                if f in cc:
                    cc[f] = _clean_str(cc[f])
            clean_contacts.append(cc)
        cleaned["contacts"] = clean_contacts
    return cleaned


# ─────────────────────────────────────────────
# READ / WRITE
# ─────────────────────────────────────────────

def _load_feed() -> dict:
    os.makedirs("data", exist_ok=True)
    if not os.path.exists(FEED_PATH):
        return {"companies": [], "last_updated": None}
    try:
        with open(FEED_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Feed load error: {e}")
        return {"companies": [], "last_updated": None}


def _save_feed(data: dict):
    os.makedirs("data", exist_ok=True)
    try:
        with open(FEED_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"  Feed saved -> {FEED_PATH}")
    except Exception as e:
        logger.error(f"Feed save error: {e}")


def _deduplicate(existing: list, fresh: list) -> list:
    seen_websites = {c.get("website", "").lower() for c in existing if c.get("website")}
    seen_names    = {c.get("name",    "").lower() for c in existing if c.get("name")}
    new_entries   = []
    for company in fresh:
        website = company.get("website", "").lower()
        name    = company.get("name",    "").lower()
        if website and website in seen_websites:
            continue
        if name and name in seen_names:
            continue
        new_entries.append(company)
        seen_websites.add(website)
        seen_names.add(name)
    merged = new_entries + existing
    return merged[:MAX_COMPANIES]


# ─────────────────────────────────────────────
# ENRICH (tab karo jab user select kare — not in bulk)
# ─────────────────────────────────────────────

def _enrich_company(company: dict) -> dict:
    try:
        from backend.agents.research_agent import research_agent
        research = research_agent(
            company_name = company["name"],
            website      = company.get("website", ""),
            description  = company.get("description", "")
        )
        return {
            **company,
            "company_summary" : research.get("company_summary",  company.get("description", "")),
            "recent_highlight": research.get("recent_highlight", ""),
            "ai_hook"         : research.get("ai_hook",          ""),
            "tech_stack"      : research.get("tech_stack",       []),
            "ai_related"      : research.get("ai_related",       False),
            # website update karo agar research agent ne dhundha
            "website"         : research.get("website",          company.get("website", "")),
        }
    except Exception as e:
        logger.warning(f"Enrich error {company.get('name')}: {e}")
        return company


# ─────────────────────────────────────────────
# MAIN — Feed Refresh
# ─────────────────────────────────────────────

def refresh_feed(enrich: bool = False) -> dict:
    """
    Sab sources se fresh companies fetch karo.
    scraper_agent already sab sources handle karta hai parallel mein.
    enrich=True sirf background scheduler use kare — user flow mein nahi.
    """
    logger.info("Refreshing global company feed...")

    from backend.agents.scraper_agent import scraper_agent

    try:
        fresh = scraper_agent(_FEED_PREFS)
        logger.info(f"  Scraped (all sources): {len(fresh)} companies")
    except Exception as e:
        logger.error(f"Scrape error: {e}")
        fresh = []

    logger.info(f"  Total fresh: {len(fresh)} companies")

    # Enrich — sirf background mein, user flow mein nahi (latency avoid)
    if enrich and fresh:
        logger.info("  Enriching companies (background)...")
        fresh = [_enrich_company(c) for c in fresh]

    # Clean all text fields
    fresh = [_clean_company(c) for c in fresh]

    now = datetime.now(timezone.utc).isoformat()
    for company in fresh:
        company["scraped_at"] = now

    existing_data = _load_feed()
    existing      = existing_data.get("companies", [])
    merged        = _deduplicate(existing, fresh)
    new_count     = max(0, len(merged) - len(existing))

    _save_feed({
        "companies"   : merged,
        "last_updated": now,
        "total"       : len(merged),
    })

    logger.info(f"  Feed updated — {len(merged)} total, {new_count} new")

    return {
        "total"       : len(merged),
        "new"         : new_count,
        "last_updated": now,
    }


def get_feed(limit: int = 50, offset: int = 0) -> dict:
    data      = _load_feed()
    companies = data.get("companies", [])
    return {
        "companies"   : companies[offset: offset + limit],
        "total"       : len(companies),
        "last_updated": data.get("last_updated"),
        "has_more"    : (offset + limit) < len(companies),
    }


def get_feed_stats() -> dict:
    data = _load_feed()
    return {
        "total"       : len(data.get("companies", [])),
        "last_updated": data.get("last_updated"),
    }


if __name__ == "__main__":
    result = refresh_feed()
    logger.info(f"Done: {result}")