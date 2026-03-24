# backend/agents/research_agent.py
# Company ke baare mein research karo
# Taaki cold email personalized ho sake
#
# DB-free — stateless.
# Input : company_name, website, description
# Output: research dict (summary, ai_hook, tech_stack, etc.)

import json
import requests as req
from bs4              import BeautifulSoup
from groq             import Groq
from duckduckgo_search import DDGS
from loguru           import logger

from backend.config import (
    GROQ_API_KEY,
    LLM_MODEL,
    TAVILY_API_KEY,
)

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
    """
    if not url:
        return ""

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
            res = req.get(page_url, headers=HEADERS, timeout=8)
            if res.status_code != 200:
                continue

            soup = BeautifulSoup(res.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()

            text           = soup.get_text(separator=" ", strip=True)
            combined_text += text[:1000] + "\n"

        except Exception:
            continue

    return combined_text[:3000]


# ─────────────────────────────────────────────
# STEP 2 — News Search
# ─────────────────────────────────────────────

def search_duckduckgo(company_name: str) -> str:
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
        data    = res.json()
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
    search_text  : str,
    base_desc    : str = ""
) -> dict:
    prompt = f"""
You are researching a company for personalized cold email outreach.

Company: {company_name}
Known Description: {base_desc[:300]}

Website Content:
{website_text[:1500]}

Recent News/Search Results:
{search_text[:1000]}

Return ONLY a JSON object, no explanation, no markdown:
{{
    "company_summary"  : "2-3 line summary of what they build",
    "ai_related"       : true or false,
    "tech_stack"       : ["tech1", "tech2"],
    "recent_highlight" : "most interesting recent thing they did",
    "ai_hook"          : "specific angle to mention in cold email about their AI work",
    "company_stage"    : "early/growth/scale",
    "target_customer"  : "who they sell to"
}}
"""
    try:
        response = client.chat.completions.create(
            model       = LLM_MODEL,
            messages    = [{"role": "user", "content": prompt}],
            max_tokens  = 400,
            temperature = 0.1
        )
        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)

    except Exception as e:
        logger.error(f"Groq summarize error: {e}")
        return {
            "company_summary" : base_desc or "Could not research",
            "ai_related"      : False,
            "tech_stack"      : [],
            "recent_highlight": "",
            "ai_hook"         : "",
            "company_stage"   : "unknown",
            "target_customer" : "unknown",
        }


# ─────────────────────────────────────────────
# MAIN — Stateless Research
# ─────────────────────────────────────────────

def research_company(
    company_name: str,
    website     : str,
    description : str = ""
) -> dict:
    """
    Ek company research karo — DB-free.
    Returns research dict directly.

    Called by:
    - research_companies_node (pipeline, after company selection)
    - feed_agent (scheduler, for global feed enrichment)
    """
    logger.info(f"🔍 Researching: {company_name}")

    # Step 1 — Website
    website_text = scrape_website(website)

    # Step 2 — News (Tavily first, DDG fallback)
    search_text = search_tavily(company_name)
    if not search_text:
        search_text = search_duckduckgo(company_name)

    # Step 3 — Groq summary
    summary = summarize_with_groq(
        company_name,
        website_text,
        search_text,
        base_desc=description
    )

    logger.info(f"  ✅ {company_name} — research done")

    return {
        "company_name"    : company_name,
        "company_summary" : summary.get("company_summary"),
        "ai_related"      : summary.get("ai_related",       False),
        "tech_stack"      : summary.get("tech_stack",       []),
        "recent_highlight": summary.get("recent_highlight", ""),
        "ai_hook"         : summary.get("ai_hook",          ""),
        "company_stage"   : summary.get("company_stage",    "unknown"),
        "target_customer" : summary.get("target_customer",  "unknown"),
    }