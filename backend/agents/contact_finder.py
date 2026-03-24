# backend/agents/contact_finder.py
# Company ke CEO/CTO/Founder/HR dhundho
# Phir unka email find karo
# DB-free — stateless, sirf company_name + website lega

import json
import requests as req
from bs4    import BeautifulSoup
from groq   import Groq
from loguru import logger

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
# STEP 3 — Priority Assign Karo
# ─────────────────────────────────────────────

def get_priority(role: str) -> int:
    role_lower = role.lower()
    for key, priority in CONTACT_PRIORITY.items():
        if key in role_lower:
            return priority
    return 8


# ─────────────────────────────────────────────
# MAIN — Stateless Contact Finder
# ─────────────────────────────────────────────

def find_contacts(
    company_name: str,
    website     : str,
    description : str = ""
) -> dict:
    """
    Ek company ke contacts dhundho — DB-free.
    Sirf company_name + website chahiye.
    Returns dict with 'contacts' list.

    Called by:
    - research_companies_node (pipeline)
    - feed_agent (scheduler)
    - API endpoints directly
    """
    if not website:
        return {"company": company_name, "contacts": []}

    logger.info(f"👤 Finding contacts: {company_name}")

    domain = (
        website.replace("https://", "")
                .replace("http://", "")
                .rstrip("/")
                .split("/")[0]
    )

    # Step 1 — Team page scrape
    team_text = scrape_team_page(website)

    # Step 2 — Groq se people extract
    people = extract_people_with_groq(company_name, team_text, description)

    if not people:
        logger.warning(f"  ⚠️ No people found for {company_name}")
        return {"company": company_name, "contacts": []}

    # Import here to avoid circular — scraper_agent also used in pipeline
    from backend.agents.scraper_agent import find_best_email

    contacts = []

    for person in people:
        name     = person.get("name",     "")
        role     = person.get("role",     "")
        linkedin = person.get("linkedin")

        if not name:
            continue

        try:
            email_result = find_best_email(name, domain)

            contacts.append({
                "name"            : name,
                "role"            : role,
                "email"           : email_result.get("email"),
                "linkedin_url"    : linkedin,
                "confidence_score": 1.0 if email_result.get("verified") else 0.5,
                "source"          : email_result.get("source", "pattern"),
                "priority"        : get_priority(role),
            })

            logger.info(
                f"  ✅ {name} ({role}) "
                f"→ {email_result.get('email')} "
                f"[{email_result.get('source')}]"
            )

        except Exception as e:
            logger.error(f"  ❌ Contact error {name}: {e}")
            continue

    return {
        "company" : company_name,
        "contacts": contacts
    }