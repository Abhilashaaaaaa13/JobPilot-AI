# backend/agents/contact_finder.py
# Company ke CEO/CTO/Founder/HR dhundho
# Phir unka email find karo

import json
import requests as req
from bs4 import BeautifulSoup
from groq import Groq
from sqlalchemy.orm import Session
from backend.models.company import Company
from backend.models.contact import Contact
from backend.utils.email_verifier import find_best_email
from backend.config import GROQ_API_KEY, LLM_MODEL, CONTACT_PRIORITY
from loguru import logger

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
            res  = req.get(url, headers=HEADERS, timeout=8)
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
    
    Why Groq here?
    HTML structure har site pe alag hoti hai.
    Regex se reliable extract karna mushkil.
    LLM text samajhta hai — koi bhi format.
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
            model      = LLM_MODEL,
            messages   = [{"role": "user", "content": prompt}],
            max_tokens = 400,
            temperature= 0.1
        )
        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        people = json.loads(raw)
        return people if isinstance(people, list) else []

    except Exception as e:
        logger.error(f"Groq people extract error: {e}")
        return []


# ─────────────────────────────────────────────
# STEP 3 — Priority Assign Karo
# ─────────────────────────────────────────────

def get_priority(role: str) -> int:
    """
    Role ke basis pe priority assign karo.
    Lower number = higher priority.
    config.py ke CONTACT_PRIORITY se.
    """
    role_lower = role.lower()
    for key, priority in CONTACT_PRIORITY.items():
        if key in role_lower:
            return priority
    return 8  # Unknown role = lowest priority


# ─────────────────────────────────────────────
# MAIN — Find Contacts For Company
# ─────────────────────────────────────────────

def find_contacts(db: Session, company_id: int) -> dict:
    """
    Ek company ke contacts dhundho.
    Already contacts hain? Skip karo.
    """
    company = db.query(Company).filter(
        Company.id == company_id
    ).first()

    if not company:
        return {"error": "Company nahi mili"}

    # Already contacts hain?
    existing = db.query(Contact).filter(
        Contact.company_id == company_id
    ).count()

    if existing > 0:
        return {
            "message" : "Already found",
            "contacts": existing
        }

    logger.info(f"👤 Finding contacts: {company.name}")

    domain = company.website.replace("https://", "")\
                            .replace("http://", "")\
                            .rstrip("/").split("/")[0] \
             if company.website else ""

    # Step 1 — Team page scrape
    team_text = scrape_team_page(company.website or "")

    # Step 2 — Groq se people extract
    people = extract_people_with_groq(
        company.name,
        team_text,
        company.description or ""
    )

    if not people:
        logger.warning(f"  ⚠️ No people found for {company.name}")
        return {"contacts": 0}

    saved = 0

    for person in people:
        try:
            name     = person.get("name", "")
            role     = person.get("role", "")
            linkedin = person.get("linkedin")

            if not name:
                continue

            # Email dhundho
            email_result = find_best_email(name, domain)

            contact = Contact(
                company_id       = company_id,
                name             = name,
                role             = role,
                email            = email_result["email"],
                linkedin_url     = linkedin,
                confidence_score = email_result["confidence"],
                source           = email_result["source"],
                priority         = get_priority(role)
            )

            db.add(contact)
            saved += 1

            logger.info(
                f"  ✅ {name} ({role}) "
                f"→ {email_result['email']} "
                f"[{email_result['source']}]"
            )

        except Exception as e:
            logger.error(f"  ❌ Contact save error: {e}")
            continue

    db.commit()

    return {
        "company"  : company.name,
        "contacts" : saved
    }


def find_all_pending_contacts(db: Session) -> dict:
    """
    Sab companies jinke contacts nahi hain.
    """
    # Companies jinke koi contact nahi
    companies_with_contacts = db.query(Contact.company_id).distinct()
    companies = db.query(Company).filter(
        Company.id.notin_(companies_with_contacts),
        Company.research_done == True
    ).all()

    if not companies:
        return {"message": "Sab companies ke contacts hain", "done": 0}

    done = 0
    for company in companies:
        try:
            result = find_contacts(db, company.id)
            done  += result.get("contacts", 0)
        except Exception as e:
            logger.error(f"Contact finder failed {company.name}: {e}")
            continue

    return {"total_contacts_found": done}