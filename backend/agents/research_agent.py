# backend/agents/research_agent.py
# Company ke baare mein research karo
# Taaki cold email personalized ho sake
#
# Why research zaroori hai?
# Generic email: "I want to work at your company"
# Personalized: "Maine dekha aap AI-powered
# retail analytics bana rahe hain — maine
# exactly aisa RAG system banaya hai"
#
# Second email open hoti hai, first nahi.

import json
import requests as req
from bs4 import BeautifulSoup
from groq import Groq
from duckduckgo_search import DDGS
from sqlalchemy.orm import Session
from backend.models.company import Company
from backend.config import (
    GROQ_API_KEY, LLM_MODEL,
    TAVILY_API_KEY
)
from loguru import logger

client = Groq(api_key=GROQ_API_KEY)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    )
}


# ─────────────────────────────────────────────
# STEP 1 — Website Scrape
# ─────────────────────────────────────────────

def scrape_website(url: str) -> str:
    """
    Company website se text nikalo.
    /about aur /team pages most useful hain.
    
    Why multiple pages?
    Homepage = marketing copy
    /about   = actual mission, team info
    /team    = founder names, emails
    """
    pages = [
        url,
        url.rstrip("/") + "/about",
        url.rstrip("/") + "/about-us",
        url.rstrip("/") + "/team",
        url.rstrip("/") + "/contact",
    ]

    combined_text = ""

    for page_url in pages:
        try:
            res  = req.get(page_url, headers=HEADERS, timeout=8)
            if res.status_code != 200:
                continue

            soup = BeautifulSoup(res.text, "html.parser")

            # Irrelevant tags hata do
            for tag in soup(["script", "style", "nav",
                              "footer", "header"]):
                tag.decompose()

            text = soup.get_text(separator=" ", strip=True)

            # Max 1000 chars per page — enough context
            combined_text += text[:1000] + "\n"

        except Exception:
            continue

    return combined_text[:3000]  # Total max 3000 chars


# ─────────────────────────────────────────────
# STEP 2 — News Search
# ─────────────────────────────────────────────

def search_duckduckgo(company_name: str) -> str:
    """
    DuckDuckGo se recent news dhundho.
    Free, no API key needed.
    """
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(
                f"{company_name} startup AI product launch",
                max_results=3
            ))
            return " ".join([r.get("body", "") for r in results])
    except Exception as e:
        logger.warning(f"DuckDuckGo error: {e}")
        return ""


def search_tavily(company_name: str) -> str:
    """
    Tavily se structured search results.
    Better than DuckDuckGo for recent news.
    Free: 1000 searches/month.
    
    Why Tavily aur DuckDuckGo dono?
    Tavily = recent, structured, accurate
    DuckDuckGo = fallback agar Tavily quota khatam
    """
    if not TAVILY_API_KEY:
        return ""

    try:
        res = req.post(
            "https://api.tavily.com/search",
            json={
                "api_key"        : TAVILY_API_KEY,
                "query"          : f"{company_name} company product AI",
                "search_depth"   : "basic",
                "max_results"    : 3,
                "include_answer" : True
            },
            timeout=10
        )
        data = res.json()

        # Answer + results combine karo
        answer  = data.get("answer", "")
        results = data.get("results", [])
        content = answer + " " + " ".join(
            [r.get("content", "") for r in results]
        )
        return content[:2000]

    except Exception as e:
        logger.warning(f"Tavily error: {e}")
        return ""


# ─────────────────────────────────────────────
# STEP 3 — Groq Se Summarize
# ─────────────────────────────────────────────

def summarize_with_groq(
    company_name : str,
    website_text : str,
    search_text  : str
) -> dict:
    """
    Sab context Groq ko do.
    Structured summary nikalo.
    
    Why JSON output?
    Structured data = easy to use in email template
    "company_summary" → email intro mein
    "ai_hook"         → personalization angle
    "tech_stack"      → resume match karne ke liye
    """
    prompt = f"""
You are researching a company for personalized cold email outreach.

Company: {company_name}

Website Content:
{website_text[:1500]}

Recent News/Search Results:
{search_text[:1000]}

Return ONLY a JSON object, no explanation, no markdown:
{{
    "company_summary": "2-3 line summary of what they build",
    "ai_related": true or false,
    "tech_stack": ["tech1", "tech2"],
    "recent_highlight": "most interesting recent thing they did",
    "ai_hook": "specific angle to mention in cold email about their AI work",
    "company_stage": "early/growth/scale",
    "target_customer": "who they sell to"
}}
"""
    try:
        response = client.chat.completions.create(
            model      = LLM_MODEL,
            messages   = [{"role": "user", "content": prompt}],
            max_tokens = 400,
            temperature= 0.1
        )
        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)

    except Exception as e:
        logger.error(f"Groq summarize error: {e}")
        return {
            "company_summary" : "Could not research",
            "ai_related"      : False,
            "tech_stack"      : [],
            "recent_highlight": "",
            "ai_hook"         : "",
            "company_stage"   : "unknown",
            "target_customer" : "unknown"
        }


# ─────────────────────────────────────────────
# MAIN — Research One Company
# ─────────────────────────────────────────────

def research_company(db: Session, company_id: int) -> dict:
    """
    Ek company research karo.
    DB mein update karo.
    """
    company = db.query(Company).filter(
        Company.id == company_id
    ).first()

    if not company:
        return {"error": "Company nahi mili"}

    if company.research_done:
        return {"message": "Already researched", "id": company_id}

    logger.info(f"🔍 Researching: {company.name}")

    # Step 1 — Website
    website_text = scrape_website(company.website or "")

    # Step 2 — News (Tavily first, DDG fallback)
    search_text = search_tavily(company.name)
    if not search_text:
        search_text = search_duckduckgo(company.name)

    # Step 3 — Groq summary
    summary = summarize_with_groq(
        company.name,
        website_text,
        search_text
    )

    # DB update karo
    company.company_summary = summary.get("company_summary")
    company.recent_news     = summary.get("recent_highlight")
    company.ai_related      = summary.get("ai_related", False)
    company.tech_stack      = json.dumps(summary.get("tech_stack", []))
    company.research_done   = True

    db.commit()

    logger.info(f"  ✅ {company.name} — research done")

    return {
        "company_id"      : company_id,
        "name"            : company.name,
        "summary"         : summary.get("company_summary"),
        "ai_related"      : summary.get("ai_related"),
        "recent_highlight": summary.get("recent_highlight"),
        "ai_hook"         : summary.get("ai_hook"),
        "tech_stack"      : summary.get("tech_stack"),
    }


def research_all_pending(db: Session) -> dict:
    """Sab unresearched companies research karo."""
    companies = db.query(Company).filter(
        Company.research_done == False
    ).all()

    if not companies:
        return {"message": "Sab companies researched hain", "done": 0}

    done = 0
    for company in companies:
        try:
            research_company(db, company.id)
            done += 1
        except Exception as e:
            logger.error(f"Research failed {company.name}: {e}")
            continue

    return {"researched": done}