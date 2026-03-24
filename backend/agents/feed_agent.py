# backend/agents/feed_agent.py
#
# Global "New Startups" feed.
# Scheduler se har 24 ghante call hota hai.
# User-specific nahi — sab users ke liye ek global feed.
# Frontend data/company_feed.json read karta hai.

import json
import os
from datetime import datetime, timezone
from loguru   import logger

FEED_PATH     = os.path.join("data", "company_feed.json")
MAX_COMPANIES = 200   # feed mein max entries rakho

# Default prefs for feed — broad net
_FEED_PREFS = {
    "domains"     : ["ai_ml", "data_science", "software", "full_stack", "backend"],
    "target_roles": [
        "engineer", "developer", "data scientist",
        "ml engineer", "ai engineer", "backend", "full stack"
    ],
    "location": "remote"
}


# ─────────────────────────────────────────────
# READ / WRITE
# ─────────────────────────────────────────────

def _load_feed() -> dict:
    """Existing feed load karo."""
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
        logger.info(f"  💾 Feed saved → {FEED_PATH}")
    except Exception as e:
        logger.error(f"Feed save error: {e}")


def _deduplicate(existing: list, fresh: list) -> list:
    """
    Existing + fresh merge karo.
    Website ya naam se duplicate hatao.
    Naye entries pehle rakho (newest first).
    Max MAX_COMPANIES entries.
    """
    seen_websites = {c.get("website", "").lower() for c in existing if c.get("website")}
    seen_names    = {c.get("name",    "").lower() for c in existing if c.get("name")}

    new_entries = []
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

    # Naye pehle, phir existing — trim to MAX_COMPANIES
    merged = new_entries + existing
    return merged[:MAX_COMPANIES]


# ─────────────────────────────────────────────
# ENRICH — optional research pass
# ─────────────────────────────────────────────

def _enrich_company(company: dict) -> dict:
    """
    Light research pass — ai_hook aur recent_highlight add karo.
    Agar research fail ho to original return karo.
    """
    try:
        from backend.agents.research_agent import research_company
        research = research_company(
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
        }
    except Exception as e:
        logger.warning(f"Enrich error {company.get('name')}: {e}")
        return company


# ─────────────────────────────────────────────
# MAIN — Refresh Feed
# ─────────────────────────────────────────────

def refresh_feed(enrich: bool = False) -> dict:
    """
    Fresh companies scrape karo.
    Existing feed se merge karo (deduplicated).
    data/company_feed.json mein save karo.

    Args:
        enrich: True karo to har naye company ko research karo.
                False (default) — fast scrape only, no research.
                Pipeline mein research tab hoti hai jab user select kare.
    """
    logger.info("🔄 Refreshing global company feed...")

    from backend.agents.scraper_agent import scrape_track_b

    try:
        fresh = scrape_track_b(_FEED_PREFS)
        logger.info(f"  📡 Scraped: {len(fresh)} companies")
    except Exception as e:
        logger.error(f"Scrape error: {e}")
        return {"total": 0, "new": 0, "error": str(e)}

    if enrich and fresh:
        logger.info("  🔬 Enriching fresh companies...")
        enriched = []
        for company in fresh:
            enriched.append(_enrich_company(company))
        fresh = enriched

    # Tag each with scraped_at timestamp
    now = datetime.now(timezone.utc).isoformat()
    for company in fresh:
        company["scraped_at"] = now

    # Load existing, merge, save
    existing_data = _load_feed()
    existing      = existing_data.get("companies", [])
    merged        = _deduplicate(existing, fresh)

    new_count = len(merged) - len(existing)
    if new_count < 0:
        new_count = 0

    _save_feed({
        "companies"   : merged,
        "last_updated": now,
        "total"       : len(merged),
    })

    logger.info(
        f"  ✅ Feed updated — {len(merged)} total, {new_count} new"
    )

    return {
        "total"       : len(merged),
        "new"         : new_count,
        "last_updated": now,
    }


def get_feed(limit: int = 50, offset: int = 0) -> dict:
    """
    Frontend ke liye feed return karo.
    Pagination support — limit + offset.
    """
    data      = _load_feed()
    companies = data.get("companies", [])

    return {
        "companies"   : companies[offset: offset + limit],
        "total"       : len(companies),
        "last_updated": data.get("last_updated"),
        "has_more"    : (offset + limit) < len(companies),
    }


def get_feed_stats() -> dict:
    """Quick stats — no heavy load."""
    data = _load_feed()
    return {
        "total"       : len(data.get("companies", [])),
        "last_updated": data.get("last_updated"),
    }