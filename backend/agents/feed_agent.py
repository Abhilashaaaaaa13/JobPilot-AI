# backend/agents/feed_agent.py
# ═══════════════════════════════════════════════════════════════════════════════
# Feed management — refresh, cache, and persist company data
# ═══════════════════════════════════════════════════════════════════════════════

import json
import os
from datetime import datetime, timezone
from loguru import logger
from typing import List, Dict

from backend.database import SessionLocal
from backend.models.company import Company
from backend.utils.feed_to_db import save_companies_bulk, sync_feed_json


def get_feed(limit: int = 100) -> Dict:
    """
    Get cached feed from data/company_feed.json.
    Falls back to empty if not available.
    """
    feed_path = "data/company_feed.json"
    
    if os.path.exists(feed_path):
        try:
            with open(feed_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                companies = data.get("companies", [])[:limit]
                return {
                    "companies": companies,
                    "last_updated": data.get("last_updated", ""),
                    "total": len(companies)
                }
        except Exception as e:
            logger.warning(f"Could not load feed cache: {e}")
    
    return {"companies": [], "last_updated": "", "total": 0}


def refresh_feed() -> Dict:
    """
    Refresh global company feed from all sources.
    
    Called by:
    - Scheduler daily
    - Frontend "Refresh Feed" button
    - Feed agent job
    
    Returns: {"total": int, "new": int, "companies": list}
    """
    logger.info("🔄 Starting feed refresh...")
    
    try:
        from backend.agents.scraper_agent import scraper_agent
        
        prefs = {
            "domains": ["ai_ml", "saas", "developer_tools"],
            "target_roles": ["founder", "ceo", "engineer", "ai engineer"],
            "location": "remote"
        }
        
        # Scrape all sources
        companies = scraper_agent(prefs)
        
        if not companies:
            logger.warning("⚠️ No companies scraped — using cached feed")
            return get_feed()
        
        logger.info(f"✅ Scraped {len(companies)} companies from sources")
        
        # Save to DB for ALL users (or default user)
        # Using user_id = 0 for global feed
        user_id = 0
        
        db = SessionLocal()
        try:
            # Get existing count before
            existing = db.query(Company).filter(Company.user_id == user_id).count()
            
            # Save bulk
            added = save_companies_bulk(user_id, companies)
            
            # Sync to JSON cache
            sync_feed_json(user_id)
            
            logger.info(f"✅ Feed refresh complete: {added} new companies added")
            
            return {
                "total": len(companies),
                "new": added,
                "companies": companies,
                "success": True
            }
        
        finally:
            db.close()
    
    except Exception as e:
        logger.error(f"❌ Feed refresh error: {e}", exc_info=True)
        
        # Return cached feed on error
        cached = get_feed()
        return {
            "total": cached["total"],
            "new": 0,
            "error": str(e),
            "companies": cached["companies"]
        }


def get_user_feed(user_id: int, limit: int = 60) -> List[Dict]:
    """Get uncontacted companies from user's feed"""
    from backend.utils.feed_to_db import load_feed_companies
    return load_feed_companies(user_id, limit)


def mark_contacted(user_id: int, company_id: int) -> bool:
    """Mark a company as contacted"""
    from backend.utils.feed_to_db import mark_company_contacted
    
    try:
        mark_company_contacted(user_id, company_id)
        return True
    except Exception as e:
        logger.error(f"Error marking company contacted: {e}")
        return False


if __name__ == "__main__":
    result = refresh_feed()
    print(f"Feed refreshed: {result['new']} new companies")