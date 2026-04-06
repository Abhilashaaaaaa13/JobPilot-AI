# backend/agents/contact_finder.py
#
# Company ke CEO/CTO/Founder/HR dhundho
# Phir unka email find karo
#
# AGENT VERSION:
# - Team page scrape → Groq extract (already tha)
# - Na mile → LinkedIn DuckDuckGo search
# - Abhi bhi na mile → domain se founder guess karo
#
# DB-free — stateless, sirf company_name + website lega

import json
import requests as req
from bs4               import BeautifulSoup
from groq              import Groq
from duckduckgo_search import DDGS
from loguru            import logger

from backend.config import GROQ_API_KEY, LLM_MODEL, CONTACT_PRIORITY

client = Groq(api_key=GROQ_API_KEY)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    )
}


# ─────────────────────────────────────────────
# STEP 1 — Website Se People Dhundho
# ─────────────────────────────────────────────

def scrape_team_page(website: str) -> str:
    """
    /team aur /about page scrape karo.
    Names aur roles dhundho.
    """
    pages = [
        website.rstrip("/") + "/team",
        website.rstrip("/") + "/about",
        website.rstrip("/") + "/about-us",
        website.rstrip("/") + "/leadership",
    ]

    text = ""
    for url in pages:
        try:
            res = req.get(url, headers=HEADERS, timeout=8)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                for tag in soup(["script", "style"]):
                    tag.decompose()
                text += soup.get_text(separator=" ", strip=True)[:1500]
        except Exception:
            continue

    return text[:3000]


# ─────────────────────────────────────────────
# STEP 2 — Groq Se People Extract Karo
# ─────────────────────────────────────────────

def extract_people_with_groq(
    company_name : str,
    team_text    : str,
    company_desc : str
) -> list:
    """
    Team page text se structured people list nikalo.
    LLM text samajhta hai — koi bhi HTML format ho.
    """
    prompt = f"""
Extract people from this company team page.
Company: {company_name}
Description: {company_desc}

Team Page Content:
{team_text[:2000]}

Return ONLY a JSON array, no explanation:
[
  {{
    "name": "Full Name",
    "role": "CEO/CTO/Founder/HR/Engineer",
    "linkedin": "linkedin url or null"
  }}
]

Only include: CEO, CTO, Founder, Co-founder,
VP Engineering, Engineering Manager, HR, Recruiter.
Maximum 5 people. Most senior first.
If no people found, return empty array: []
"""
    try:
        response = client.chat.completions.create(
            model       = LLM_MODEL,
            messages    = [{"role": "user", "content": prompt}],
            max_tokens  = 400,
            temperature = 0.1
        )
        raw    = response.choices[0].message.content.strip()
        raw    = raw.replace("```json", "").replace("```", "").strip()
        people = json.loads(raw)
        return people if isinstance(people, list) else []

    except Exception as e:
        logger.error(f"Groq people extract error: {e}")
        return []


# ─────────────────────────────────────────────
# AGENT FALLBACK 1 — LinkedIn Search
# Team page pe koi nahi mila → LinkedIn try karo
# ─────────────────────────────────────────────

def _search_linkedin_people(company_name: str) -> list:
    """
    DuckDuckGo se LinkedIn profiles dhundho.
    CEO → Founder → CTO order mein try karo.
    """
    people = []
    seen   = set()

    queries = [
        (f"{company_name} CEO site:linkedin.com/in",      "CEO"),
        (f"{company_name} founder site:linkedin.com/in",  "Founder"),
        (f"{company_name} CTO site:linkedin.com/in",      "CTO"),
        (f"{company_name} HR recruiter site:linkedin.com/in", "HR"),
    ]

    for query, role in queries:
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=2))

            for r in results:
                title = r.get("title", "")
                url   = r.get("href",  "")

                # LinkedIn URL se naam nikalo
                # Format: "John Doe - CEO at CompanyName | LinkedIn"
                name = _extract_name_from_linkedin_title(title, company_name)

                if not name or name.lower() in seen:
                    continue
                seen.add(name.lower())

                people.append({
                    "name"    : name,
                    "role"    : role,
                    "linkedin": url,
                })

                if len(people) >= 3:
                    return people

        except Exception as e:
            logger.warning(f"  LinkedIn search error ({role}): {e}")
            continue

    return people


def _extract_name_from_linkedin_title(title: str, company_name: str) -> str:
    """
    LinkedIn title se naam nikalo.
    Formats:
    - "John Doe - CEO at Acme Corp | LinkedIn"
    - "John Doe | LinkedIn"
    - "John Doe - Founder"
    """
    if not title:
        return ""

    # " - " se pehle wala part naam hota hai usually
    parts = title.split(" - ")
    if parts:
        name_part = parts[0].strip()
        # "| LinkedIn" hata do
        name_part = name_part.replace("| LinkedIn", "").strip()
        name_part = name_part.replace("LinkedIn", "").strip()

        # Sirf agar 2+ words hain (first + last name)
        words = name_part.split()
        if 2 <= len(words) <= 4:
            # Company name nahi hai naam mein
            if company_name.lower() not in name_part.lower():
                return name_part

    return ""


# ─────────────────────────────────────────────
# AGENT FALLBACK 2 — Founder Guess
# LinkedIn pe bhi nahi mila → domain se guess karo
# ─────────────────────────────────────────────

def _guess_founder(company_name: str, domain: str) -> list:
    """
    Last resort — domain se common founder email patterns guess karo.
    Confidence low hogi — user ko dikhao.
    """
    logger.warning(f"  ⚠️ Guessing founder for {company_name} @ {domain}")

    common_emails = [
        f"founder@{domain}",
        f"hello@{domain}",
        f"hi@{domain}",
        f"contact@{domain}",
    ]

    return [{
        "name"      : f"{company_name} Team",
        "role"      : "Founder",
        "email"     : common_emails[0],
        "linkedin"  : None,
        "guessed"   : True,        # flag — low confidence
        "confidence": 0.2,
    }]


# ─────────────────────────────────────────────
# STEP 3 — Priority Assign Karo
# ─────────────────────────────────────────────

def get_priority(role: str) -> int:
    role_lower = role.lower()
    for key, priority in CONTACT_PRIORITY.items():
        if key in role_lower:
            return priority
    return 8


# ─────────────────────────────────────────────
# MAIN — Contact Finder Agent
# ─────────────────────────────────────────────

def contact_finder_agent(
    company_name: str,
    website     : str,
    description : str = ""
) -> dict:
    """
    AGENT VERSION — khud decide karta hai:
    1. Team page scrape → Groq extract
    2. Nahi mile → LinkedIn DuckDuckGo search
    3. Abhi bhi nahi mile → domain se guess

    Called by:
    - research_companies_node (pipeline)
    - feed_agent (scheduler)
    - API endpoints directly
    """
    logger.info(f"👤 Contact Finder Agent: {company_name}")

    # Website nahi hai toh bhi try karo — research_agent ne diya hoga
    if not website:
        logger.warning(f"  ⚠️ No website — skipping contact finder for {company_name}")
        return {"company": company_name, "contacts": []}

    domain = (
        website.replace("https://", "")
               .replace("http://", "")
               .rstrip("/")
               .split("/")[0]
    )

    # ── DECISION 1 — Team page scrape ────────
    team_text = scrape_team_page(website)
    people    = extract_people_with_groq(company_name, team_text, description)

    if people:
        logger.info(f"  ✅ Found {len(people)} people from team page")
    else:
        # ── DECISION 2 — LinkedIn fallback ───
        logger.info(f"  Team page khali — LinkedIn search try kar raha hoon")
        people = _search_linkedin_people(company_name)

        if people:
            logger.info(f"  ✅ Found {len(people)} people from LinkedIn")
        else:
            # ── DECISION 3 — Guess ───────────
            logger.warning(f"  LinkedIn bhi khali — guessing founder")
            people = _guess_founder(company_name, domain)

    # ── Email find karo har person ke liye ───
    from backend.agents.scraper_agent import find_best_email

    contacts = []

    for person in people:
        name     = person.get("name",     "")
        role     = person.get("role",     "")
        linkedin = person.get("linkedin")
        guessed  = person.get("guessed",  False)

        if not name:
            continue

        # Agar already email hai (LinkedIn se ya guess se)
        existing_email = person.get("email", "")

        try:
            if existing_email and guessed:
                # Guessed email — directly use karo
                email_result = {
                    "email"   : existing_email,
                    "verified": False,
                    "source"  : "guess",
                }
            else:
                # find_best_email se dhundho
                email_result = find_best_email(name, domain)

            contacts.append({
                "name"            : name,
                "role"            : role,
                "email"           : email_result.get("email"),
                "linkedin_url"    : linkedin,
                "confidence_score": 1.0 if email_result.get("verified") else (0.2 if guessed else 0.5),
                "source"          : email_result.get("source", "pattern"),
                "priority"        : get_priority(role),
                "guessed"         : guessed,
            })

            logger.info(
                f"  ✅ {name} ({role}) "
                f"→ {email_result.get('email')} "
                f"[{email_result.get('source')}]"
                f"{' ⚠️ guessed' if guessed else ''}"
            )

        except Exception as e:
            logger.error(f"  ❌ Contact error {name}: {e}")
            continue

    return {
        "company" : company_name,
        "contacts": contacts,
    }


# Backward compatibility
def find_contacts(
    company_name: str,
    website     : str,
    description : str = ""
) -> dict:
    return contact_finder_agent(company_name, website, description)