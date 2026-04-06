# backend/agents/research_agent.py
#
# Company ke baare mein research karo
# Taaki cold email personalized ho sake
#
# AGENT VERSION:
# - Website nahi mili → khud dhundho (Google → LinkedIn → guess)
# - Scrape data kam → multiple pages try karo
# - Search fail → Tavily → DuckDuckGo → description fallback
#
# DB-free — stateless.
# Input : company_name, website, description
# Output: research dict (summary, ai_hook, tech_stack, etc.)

import json
import requests as req
from bs4               import BeautifulSoup
from groq              import Groq
from duckduckgo_search import DDGS
from loguru            import logger

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
# AGENT STEP 0 — Website Finder
# Website nahi mili toh khud dhundho
# ─────────────────────────────────────────────

def _find_website_agent(company_name: str) -> str:
    """
    Company ka website dhundho — 3 strategies:
    1. DuckDuckGo — naam match karo URL mein
    2. LinkedIn company page
    3. Guess karo domain se
    """
    logger.info(f"  🔎 Website finder: {company_name}")

    clean_name = company_name.lower().replace(" ", "")

    # Strategy 1 — DuckDuckGo official website
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(
                f"{company_name} official website",
                max_results=5
            ))
            for r in results:
                url = r.get("href", "")
                # URL mein company name ka koi part ho
                name_part = clean_name[:6]  # pehle 6 chars
                if (
                    url.startswith("http")
                    and name_part in url.lower()
                    and not any(skip in url for skip in [
                        "linkedin", "facebook", "twitter",
                        "crunchbase", "wikipedia", "glassdoor"
                    ])
                ):
                    logger.info(f"  ✅ Website found via DDG: {url}")
                    return url
    except Exception as e:
        logger.warning(f"  DDG website search error: {e}")

    # Strategy 2 — LinkedIn company page (se website extract karein)
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(
                f"{company_name} site:linkedin.com/company",
                max_results=2
            ))
            if results:
                li_url = results[0].get("href", "")
                if "linkedin.com/company" in li_url:
                    # LinkedIn se actual website fetch karo
                    website = _extract_website_from_linkedin(li_url)
                    if website:
                        logger.info(f"  ✅ Website found via LinkedIn: {website}")
                        return website
    except Exception as e:
        logger.warning(f"  LinkedIn website search error: {e}")

    # Strategy 3 — Guess karo
    guessed = f"https://{clean_name}.com"
    logger.info(f"  ⚠️ Guessing website: {guessed}")
    return guessed


def _extract_website_from_linkedin(linkedin_url: str) -> str:
    """LinkedIn company page se website link nikalo."""
    try:
        res = req.get(linkedin_url, headers=HEADERS, timeout=8)
        if res.status_code != 200:
            return ""
        soup = BeautifulSoup(res.text, "html.parser")

        # LinkedIn pe website link hoti hai
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if (
                href.startswith("http")
                and "linkedin.com" not in href
                and "facebook.com" not in href
                and "twitter.com" not in href
            ):
                return href
    except Exception:
        pass
    return ""


# ─────────────────────────────────────────────
# AGENT STEP 1 — Website Scrape (with retry)
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


def _scrape_with_fallback(url: str, company_name: str) -> str:
    """
    AGENT — scrape karo, kam data mila toh aur try karo.
    """
    text = scrape_website(url)

    # Data kaafi hai
    if len(text) >= 300:
        return text

    logger.info(f"  ⚠️ Scrape data kam ({len(text)} chars) — extra pages try kar raha hoon")

    # Extra pages try karo
    extra_pages = [
        url.rstrip("/") + "/product",
        url.rstrip("/") + "/features",
        url.rstrip("/") + "/company",
        url.rstrip("/") + "/blog",
    ]

    for page_url in extra_pages:
        try:
            res = req.get(page_url, headers=HEADERS, timeout=8)
            if res.status_code != 200:
                continue
            soup = BeautifulSoup(res.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            extra = soup.get_text(separator=" ", strip=True)[:1000]
            text += "\n" + extra
            if len(text) >= 300:
                break
        except Exception:
            continue

    return text[:3000]


# ─────────────────────────────────────────────
# AGENT STEP 2 — News Search (with fallback)
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
                "api_key"       : TAVILY_API_KEY,
                "query"         : f"{company_name} company product AI",
                "search_depth"  : "basic",
                "max_results"   : 3,
                "include_answer": True
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


def _search_with_fallback(company_name: str) -> str:
    """
    AGENT — Tavily try karo, fail toh DDG, fail toh empty string.
    """
    # Try 1 — Tavily (better quality)
    result = search_tavily(company_name)
    if result and len(result) > 100:
        logger.info(f"  ✅ Search: Tavily")
        return result

    # Try 2 — DuckDuckGo
    result = search_duckduckgo(company_name)
    if result and len(result) > 50:
        logger.info(f"  ✅ Search: DuckDuckGo fallback")
        return result

    logger.warning(f"  ⚠️ Search: both failed for {company_name}")
    return ""


# ─────────────────────────────────────────────
# AGENT STEP 3 — Groq Se Summarize
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
# MAIN — Research Agent (stateless + autonomous)
# ─────────────────────────────────────────────

def research_agent(
    company_name: str,
    website     : str,
    description : str = ""
) -> dict:
    """
    AGENT VERSION — khud decide karta hai:
    1. Website nahi mili? → _find_website_agent() call karo
    2. Scrape data kam? → extra pages try karo
    3. Search fail? → fallback sources try karo
    4. Sab fail? → description use karo as fallback

    Called by:
    - research_companies_node (pipeline, after user selects company)
    - feed_agent (scheduler, for global feed enrichment)
    """
    logger.info(f"🔍 Research Agent: {company_name}")

    # ── DECISION 1 — Website hai? ─────────────
    if not website:
        logger.info(f"  Website missing — finding autonomously")
        website = _find_website_agent(company_name)

    # ── DECISION 2 — Scrape karo ──────────────
    website_text = _scrape_with_fallback(website, company_name)

    # ── DECISION 3 — Search karo ──────────────
    search_text = _search_with_fallback(company_name)

    # ── DECISION 4 — Sab fail? description use karo
    if not website_text and not search_text and description:
        logger.warning(f"  ⚠️ No data found — using base description as fallback")
        website_text = description

    # ── Summarize ─────────────────────────────
    summary = summarize_with_groq(
        company_name,
        website_text,
        search_text,
        base_desc=description
    )

    logger.info(f"  ✅ {company_name} — research done")

    return {
        "company_name"    : company_name,
        "website"         : website,
        "company_summary" : summary.get("company_summary"),
        "ai_related"      : summary.get("ai_related",       False),
        "tech_stack"      : summary.get("tech_stack",       []),
        "recent_highlight": summary.get("recent_highlight", ""),
        "ai_hook"         : summary.get("ai_hook",          ""),
        "company_stage"   : summary.get("company_stage",    "unknown"),
        "target_customer" : summary.get("target_customer",  "unknown"),
    }


# Backward compatibility
def research_company(
    company_name: str,
    website     : str,
    description : str = ""
) -> dict:
    return research_agent(company_name, website, description)