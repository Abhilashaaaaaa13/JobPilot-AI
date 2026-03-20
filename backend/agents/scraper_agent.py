# backend/agents/scraper_agent.py

import time
import random
import json
import re
import feedparser
from datetime import date
from bs4 import BeautifulSoup
import requests as req
from sqlalchemy.orm import Session
from groq import Groq
from backend.models.job import Job
from backend.models.company import Company
from backend.models.contact import Contact
from backend.models.user import UserProfile
from backend.config import (
    SCRAPER_SOURCES, SCRAPER_DELAY_MIN,
    SCRAPER_DELAY_MAX, PRODUCT_HUNT_TOKEN,
    GITHUB_TOKEN, GROQ_API_KEY, LLM_MODEL
)
from loguru import logger

TODAY   = str(date.today())
client  = Groq(api_key=GROQ_API_KEY)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    )
}

EMAIL_PATTERN = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def random_delay():
    time.sleep(random.uniform(SCRAPER_DELAY_MIN, SCRAPER_DELAY_MAX))


def is_relevant(title: str, description: str, target_roles: list) -> bool:
    text = (title + " " + description).lower()
    return any(role.lower() in text for role in target_roles)


def get_user_preferences(db: Session, user_id: int) -> dict:
    profile = db.query(UserProfile).filter(
        UserProfile.user_id == user_id
    ).first()

    def parse(val, default=[]):
        try:
            return json.loads(val) if val else default
        except:
            return default

    if not profile:
        return {
            "target_roles"       : ["software engineer", "developer", "intern"],
            "preferred_type"     : "both",
            "preferred_locations": ["remote"],
            "min_fit_score"      : 50
        }

    return {
        "target_roles"       : parse(profile.target_roles, ["software engineer"]),
        "preferred_type"     : profile.preferred_type or "both",
        "preferred_locations": parse(profile.preferred_locations, ["remote"]),
        "min_fit_score"      : profile.min_fit_score or 50
    }


def job_exists(db: Session, apply_url: str) -> bool:
    return db.query(Job).filter(
        Job.apply_url == apply_url
    ).first() is not None


def company_exists(db: Session, website: str) -> bool:
    return db.query(Company).filter(
        Company.website == website
    ).first() is not None


def save_job(db: Session, data: dict) -> bool:
    if not data.get("apply_url"):
        return False
    if job_exists(db, data["apply_url"]):
        return False
    try:
        job = Job(**data)
        db.add(job)
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Job save error: {e}")
        return False


def save_company_with_contacts(
    db         : Session,
    name       : str,
    website    : str,
    description: str,
    funding    : str,
    team_size  : str,
    location   : str,
    source     : str,
    ai_related : bool = False
) -> bool:
    """
    Save company + immediately find contacts.
    
    Pehle: Company save karo, contacts baad mein
    Ab: Ek saath — company save + contacts find
    
    Kyun?
    User ko already enriched data dikhana hai.
    Scraping ke time contacts bhi dhundh lo.
    Alag research step ki zaroorat nahi.
    """
    if not website or company_exists(db, website):
        return False

    try:
        company = Company(
            name         = name,
            website      = website,
            description  = description,
            funding      = funding,
            team_size    = team_size,
            location     = location,
            source       = source,
            ai_related   = ai_related,
            research_done= False
        )
        db.add(company)
        db.commit()
        db.refresh(company)

        # Immediately enrich with contacts
        enrich_company(db, company)
        return True

    except Exception as e:
        db.rollback()
        logger.error(f"Company save error: {e}")
        return False


# ─────────────────────────────────────────────
# ENRICHMENT — Company + Contacts
# ─────────────────────────────────────────────

def get_domain(website: str) -> str:
    return website.replace("https://", "")\
                  .replace("http://", "")\
                  .rstrip("/").split("/")[0]


def scrape_team_page(website: str) -> str:
    """Scrape /team /about /contact pages."""
    pages = [
        website.rstrip("/"),
        website.rstrip("/") + "/about",
        website.rstrip("/") + "/team",
        website.rstrip("/") + "/contact",
        website.rstrip("/") + "/about-us",
    ]
    text = ""
    for url in pages:
        try:
            res  = req.get(url, headers=HEADERS, timeout=8)
            if res.status_code != 200:
                continue
            soup = BeautifulSoup(res.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer"]):
                tag.decompose()

            # Emails from mailto links
            for link in soup.select('a[href^="mailto:"]'):
                email = link["href"].replace("mailto:", "").strip()
                text += f" EMAIL:{email} "

            text += soup.get_text(separator=" ", strip=True)[:1500]

        except Exception:
            continue
    return text[:4000]


def extract_people_groq(
    company_name: str,
    team_text   : str,
    description : str
) -> list:
    """
    Groq se founders/CTO extract karo.
    
    Pehle: Sirf naam extract karte the
    Ab: Naam + role + email (agar text mein hai)
    """
    prompt = f"""
Extract founders and key people from this company page.
Company: {company_name}
Description: {description}

Page Content:
{team_text[:2000]}

Return ONLY a JSON array, nothing else:
[
  {{
    "name" : "Full Name",
    "role" : "Founder/CEO/CTO/etc",
    "email": "email@domain.com or null"
  }}
]

Rules:
- Only include: Founder, Co-founder, CEO, CTO,
  VP Engineering, Engineering Manager
- Maximum 4 people
- If email found in text, include it
- If no people found, return []
"""
    try:
        res = client.chat.completions.create(
            model      = LLM_MODEL,
            messages   = [{"role": "user", "content": prompt}],
            max_tokens = 300,
            temperature= 0.1
        )
        raw = res.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)
        return result if isinstance(result, list) else []
    except Exception as e:
        logger.warning(f"Groq people extract error: {e}")
        return []


def generate_email_patterns(name: str, domain: str) -> list:
    """Generate possible email patterns for a person."""
    parts = name.lower().strip().split()
    if not parts:
        return []

    first = parts[0]
    last  = parts[-1] if len(parts) > 1 else ""

    patterns = [f"{first}@{domain}"]
    if last:
        patterns += [
            f"{first}.{last}@{domain}",
            f"{first}{last}@{domain}",
            f"{first[0]}.{last}@{domain}",
            f"{first[0]}{last}@{domain}",
        ]
    return patterns


def smtp_verify(email: str) -> bool:
    """Verify email via SMTP."""
    import smtplib
    import dns.resolver
    try:
        domain     = email.split("@")[1]
        mx_records = dns.resolver.resolve(domain, "MX")
        mx_host    = str(mx_records[0].exchange).rstrip(".")

        with smtplib.SMTP(timeout=8) as smtp:
            smtp.connect(mx_host, 25)
            smtp.helo("verify.com")
            smtp.mail("verify@verify.com")
            code, _ = smtp.rcpt(email)
            return code == 250
    except Exception:
        return False


def find_email_for_person(name: str, domain: str) -> dict:
    """
    Find best email for a person.
    Priority: Pattern+SMTP → Best guess
    """
    patterns = generate_email_patterns(name, domain)

    for email in patterns:
        if smtp_verify(email):
            return {
                "email"     : email,
                "verified"  : True,
                "confidence": 0.95
            }

    # Best guess — most common pattern
    if patterns:
        return {
            "email"     : patterns[0],
            "verified"  : False,
            "confidence": 0.5
        }

    return {"email": None, "verified": False, "confidence": 0}


def enrich_company(db: Session, company: Company):
    """
    Main enrichment function.
    Called immediately after company is saved.
    
    What it does:
    1. Website scrape karo
    2. Groq se people extract karo
    3. Har person ke liye email dhundho
    4. Contacts save karo
    
    Pehle ye alag step tha — research agent
    alag, contact finder alag.
    Ab ek saath hota hai scraping ke time.
    """
    if not company.website:
        return

    logger.info(f"  🔍 Enriching: {company.name}")

    domain    = get_domain(company.website)
    team_text = scrape_team_page(company.website)

    # Emails directly in page
    direct_emails = re.findall(EMAIL_PATTERN, team_text)
    company_emails = [
        e for e in direct_emails
        if domain in e
        and "noreply" not in e
        and "support" not in e
        and "info" not in e
    ]

    # Extract people via Groq
    people = extract_people_groq(
        company.name,
        team_text,
        company.description or ""
    )

    from backend.config import CONTACT_PRIORITY

    contacts_saved = 0

    for person in people:
        name  = person.get("name", "")
        role  = person.get("role", "")
        email = person.get("email")  # from page directly

        if not name:
            continue

        # Priority assign karo
        priority = 8
        for key, p in CONTACT_PRIORITY.items():
            if key in role.lower():
                priority = p
                break

        # Email find karo
        if not email:
            # Check direct emails first
            if company_emails:
                email      = company_emails[0]
                verified   = True
                confidence = 0.8
            else:
                result     = find_email_for_person(name, domain)
                email      = result["email"]
                verified   = result["verified"]
                confidence = result["confidence"]
        else:
            verified   = True
            confidence = 0.9

        if not email:
            continue

        try:
            contact = Contact(
                company_id       = company.id,
                name             = name,
                role             = role,
                email            = email,
                linkedin_url     = None,
                confidence_score = confidence,
                source           = "website_scrape",
                priority         = priority
            )
            db.add(contact)
            contacts_saved += 1

        except Exception as e:
            logger.warning(f"Contact save error: {e}")
            continue

    db.commit()

    # Mark research done
    company.research_done = True
    db.commit()

    logger.info(
        f"  ✅ {company.name} — "
        f"{contacts_saved} contacts found"
    )


# ═════════════════════════════════════════════
# TRACK A — JOB LISTINGS
# ═════════════════════════════════════════════

def scrape_internshala(db: Session, prefs: dict) -> int:
    logger.info("🕷️ Internshala...")
    saved = 0
    urls  = []

    if prefs["preferred_type"] in ["internship", "both"]:
        urls += [
            "https://internshala.com/internships/computer-science-internship/",
            "https://internshala.com/internships/python-django-internship/",
            "https://internshala.com/internships/machine-learning-internship/",
            "https://internshala.com/internships/web-development-internship/",
            "https://internshala.com/internships/artificial-intelligence-internship/",
            "https://internshala.com/internships/data-science-internship/",
        ]
    if prefs["preferred_type"] in ["job", "both"]:
        urls += [
            "https://internshala.com/jobs/software-development-job/",
            "https://internshala.com/jobs/python-job/",
            "https://internshala.com/jobs/data-science-job/",
        ]

    for url in urls:
        try:
            res   = req.get(url, headers=HEADERS, timeout=10)
            soup  = BeautifulSoup(res.text, "html.parser")
            cards = soup.select(".individual_internship")

            for card in cards:
                try:
                    title_el   = card.select_one(".job-internship-name")
                    company_el = card.select_one(".company-name")
                    loc_el     = card.select_one(".locations span")
                    stipend_el = card.select_one(".stipend")
                    link_el    = card.select_one("a.job-title-href")

                    if not title_el or not company_el:
                        continue

                    title     = title_el.text.strip()
                    company   = company_el.text.strip()
                    location  = loc_el.text.strip()     if loc_el     else "Remote"
                    stipend   = stipend_el.text.strip() if stipend_el else "Not mentioned"
                    apply_url = (
                        "https://internshala.com" + link_el["href"]
                        if link_el else url
                    )

                    if not is_relevant(title, "", prefs["target_roles"]):
                        continue

                    if save_job(db, {
                        "title"       : title,
                        "company_name": company,
                        "location"    : location,
                        "job_type"    : "internship" if "internship" in url else "job",
                        "stipend"     : stipend,
                        "description" : title,
                        "apply_url"   : apply_url,
                        "source"      : "internshala",
                        "status"      : "new"
                    }):
                        saved += 1
                        logger.info(f"  ✅ {title} @ {company}")

                except Exception:
                    continue

            random_delay()

        except Exception as e:
            logger.error(f"Internshala error: {e}")

    logger.info(f"[Internshala] {saved} saved")
    return saved


def scrape_yc_jobs(db: Session, prefs: dict) -> int:
    logger.info("🕷️ YC Jobs...")
    saved = 0

    try:
        res   = req.get(
            "https://www.workatastartup.com/jobs",
            headers=HEADERS, timeout=15
        )
        soup  = BeautifulSoup(res.text, "html.parser")
        cards = soup.select(".posting-title, .job-name")

        for card in cards:
            try:
                title     = card.text.strip()
                parent    = card.find_parent("a")
                apply_url = (
                    "https://www.workatastartup.com" + parent["href"]
                    if parent and parent.get("href") else ""
                )
                if not apply_url:
                    continue

                company_tag = card.find_previous(
                    ["div", "span"],
                    class_=lambda c: c and "company" in c.lower()
                )
                company = company_tag.text.strip() if company_tag else "YC Startup"

                if not is_relevant(title, "", prefs["target_roles"]):
                    continue

                if save_job(db, {
                    "title"       : title,
                    "company_name": company,
                    "location"    : "Remote / SF",
                    "job_type"    : "job",
                    "stipend"     : "Not mentioned",
                    "description" : title,
                    "apply_url"   : apply_url,
                    "source"      : "yc_jobs",
                    "status"      : "new"
                }):
                    saved += 1
                    logger.info(f"  ✅ {title} @ {company}")

            except Exception:
                continue

    except Exception as e:
        logger.error(f"YC Jobs error: {e}")

    logger.info(f"[YC Jobs] {saved} saved")
    return saved


def scrape_unstop(db: Session, prefs: dict) -> int:
    logger.info("🕷️ Unstop...")
    saved = 0

    try:
        res   = req.get(
            "https://unstop.com/api/public/opportunity/search-result"
            "?opportunity=jobs&per_page=20&page=1",
            headers=HEADERS, timeout=10
        )
        items = res.json().get("data", {}).get("data", [])

        for item in items:
            try:
                title     = item.get("title", "")
                company   = item.get("organisation", {}).get("name", "")
                location  = item.get("city", "Remote")
                slug      = item.get("public_url", "")
                apply_url = f"https://unstop.com/{slug}"

                if not is_relevant(title, "", prefs["target_roles"]):
                    continue

                if save_job(db, {
                    "title"       : title,
                    "company_name": company,
                    "location"    : location,
                    "job_type"    : "job",
                    "stipend"     : "Not mentioned",
                    "description" : title,
                    "apply_url"   : apply_url,
                    "source"      : "unstop",
                    "status"      : "new"
                }):
                    saved += 1
                    logger.info(f"  ✅ {title} @ {company}")

            except Exception:
                continue

    except Exception as e:
        logger.error(f"Unstop error: {e}")

    logger.info(f"[Unstop] {saved} saved")
    return saved


def scrape_remotive(db: Session, prefs: dict) -> int:
    logger.info("🕷️ Remotive...")
    saved = 0

    try:
        res  = req.get(
            "https://remotive.com/api/remote-jobs?limit=50",
            headers=HEADERS, timeout=10
        )
        jobs = res.json().get("jobs", [])

        for job in jobs:
            try:
                title       = job.get("title", "")
                company     = job.get("company_name", "")
                description = job.get("description", "")
                apply_url   = job.get("url", "")
                location    = job.get("candidate_required_location", "Remote")

                if not is_relevant(title, description, prefs["target_roles"]):
                    continue

                if save_job(db, {
                    "title"       : title,
                    "company_name": company,
                    "location"    : location,
                    "job_type"    : "job",
                    "stipend"     : "Not mentioned",
                    "description" : description[:500],
                    "apply_url"   : apply_url,
                    "source"      : "remotive",
                    "status"      : "new"
                }):
                    saved += 1
                    logger.info(f"  ✅ {title} @ {company}")

            except Exception:
                continue

    except Exception as e:
        logger.error(f"Remotive error: {e}")

    logger.info(f"[Remotive] {saved} saved")
    return saved


def scrape_the_muse(db: Session, prefs: dict) -> int:
    logger.info("🕷️ The Muse...")
    saved = 0

    try:
        res  = req.get(
            "https://www.themuse.com/api/public/jobs?page=1&per_page=20",
            headers=HEADERS, timeout=10
        )
        jobs = res.json().get("results", [])

        for job in jobs:
            try:
                title     = job.get("name", "")
                company   = job.get("company", {}).get("name", "")
                apply_url = job.get("refs", {}).get("landing_page", "")
                locations = job.get("locations", [])
                location  = locations[0].get("name", "Remote") if locations else "Remote"

                if not is_relevant(title, "", prefs["target_roles"]):
                    continue

                if save_job(db, {
                    "title"       : title,
                    "company_name": company,
                    "location"    : location,
                    "job_type"    : "job",
                    "stipend"     : "Not mentioned",
                    "description" : title,
                    "apply_url"   : apply_url,
                    "source"      : "the_muse",
                    "status"      : "new"
                }):
                    saved += 1
                    logger.info(f"  ✅ {title} @ {company}")

            except Exception:
                continue

    except Exception as e:
        logger.error(f"The Muse error: {e}")

    logger.info(f"[The Muse] {saved} saved")
    return saved


# ═════════════════════════════════════════════
# TRACK B — COLD OUTREACH
# ═════════════════════════════════════════════

def scrape_yc_companies(db: Session, prefs: dict) -> int:
    logger.info("🕷️ YC Companies...")
    saved = 0

    try:
        res       = req.get(
            "https://api.ycombinator.com/v0.1/companies"
            "?page=1&per_page=100",
            headers=HEADERS, timeout=15
        )
        companies = res.json().get("companies", [])

        for c in companies:
            try:
                name        = c.get("name", "")
                website     = c.get("website", "")
                description = c.get("one_liner", "")
                batch       = c.get("batch", "")
                team_size   = str(c.get("team_size", ""))
                tags        = " ".join(c.get("tags", []))
                location    = c.get("location", "")

                if not website or not name:
                    continue

                ai_tags = [
                    "ai", "ml", "machine learning", "nlp",
                    "llm", "artificial intelligence",
                    "generative", "developer tools", "saas"
                ]
                ai_related = any(t in tags.lower() for t in ai_tags)
                role_match = is_relevant(
                    description, tags, prefs["target_roles"]
                )

                if not ai_related and not role_match:
                    continue

                if save_company_with_contacts(
                    db          = db,
                    name        = name,
                    website     = website,
                    description = description,
                    funding     = f"YC {batch}",
                    team_size   = team_size,
                    location    = location,
                    source      = "yc_api",
                    ai_related  = ai_related
                ):
                    saved += 1
                    logger.info(f"  ✅ {name}")

            except Exception:
                continue

        random_delay()

    except Exception as e:
        logger.error(f"YC Companies error: {e}")

    logger.info(f"[YC Companies] {saved} saved")
    return saved


def scrape_hn_hiring(db: Session, prefs: dict) -> int:
    """
    HN Who's Hiring — Ab Groq se structured data extract karo.
    
    Pehle: Comment ka pehla line naam maan lete the
    Ab: Groq se company naam + email + role nikalo
    """
    logger.info("🕷️ HN Who's Hiring...")
    saved = 0

    try:
        search_res = req.get(
            "https://hn.algolia.com/api/v1/search?"
            "query=who+is+hiring&tags=story&hitsPerPage=1",
            timeout=10
        )
        hits = search_res.json().get("hits", [])
        if not hits:
            return 0

        thread_id    = hits[0]["objectID"]
        comments_res = req.get(
            f"https://hn.algolia.com/api/v1/search?"
            f"tags=comment,story_{thread_id}&hitsPerPage=100",
            timeout=10
        )
        comments = comments_res.json().get("hits", [])

        for comment in comments:
            try:
                text = comment.get("comment_text", "")
                if not text or len(text) < 50:
                    continue

                soup    = BeautifulSoup(text, "html.parser")
                content = soup.get_text()

                if not is_relevant(content, "", prefs["target_roles"]):
                    continue

                # Groq se extract karo
                prompt = f"""
Extract company info from this HN hiring post.
Return ONLY JSON, nothing else:
{{
    "company_name": "name or null",
    "website": "url or null",
    "email": "email or null",
    "location": "location or Remote",
    "description": "what they build in 1 line"
}}

Post: {content[:500]}
"""
                res_groq = client.chat.completions.create(
                    model      = LLM_MODEL,
                    messages   = [{"role": "user", "content": prompt}],
                    max_tokens = 150,
                    temperature= 0.1
                )
                raw  = res_groq.choices[0].message.content.strip()
                raw  = raw.replace("```json", "").replace("```", "").strip()
                data = json.loads(raw)

                company_name = data.get("company_name")
                website      = data.get("website")
                email        = data.get("email")

                if not company_name:
                    continue

                # Website nahi mila toh skip
                if not website:
                    object_id = comment.get("objectID", "")
                    website   = f"https://news.ycombinator.com/item?id={object_id}"

                if save_company_with_contacts(
                    db          = db,
                    name        = company_name,
                    website     = website,
                    description = data.get("description", ""),
                    funding     = "Unknown",
                    team_size   = "Unknown",
                    location    = data.get("location", "Remote"),
                    source      = "hn_hiring",
                    ai_related  = "ai" in content.lower()
                ):
                    saved += 1
                    logger.info(f"  ✅ HN: {company_name}")

                    # Agar email directly mila toh save karo
                    if email and "@" in email:
                        company = db.query(Company).filter(
                            Company.website == website
                        ).first()
                        if company:
                            contact = Contact(
                                company_id       = company.id,
                                name             = "Hiring Contact",
                                role             = "Founder/HR",
                                email            = email,
                                confidence_score = 0.9,
                                source           = "hn_post",
                                priority         = 1
                            )
                            db.add(contact)
                            db.commit()

            except Exception:
                continue

    except Exception as e:
        logger.error(f"HN Hiring error: {e}")

    logger.info(f"[HN Hiring] {saved} saved")
    return saved


def scrape_product_hunt(db: Session, prefs: dict) -> int:
    if not PRODUCT_HUNT_TOKEN:
        logger.warning("Product Hunt token missing")
        return 0

    logger.info("🕷️ Product Hunt...")
    saved = 0

    query = """
    {
      posts(first: 20, order: VOTES) {
        edges {
          node {
            name
            tagline
            website
            makers { name username }
            topics { edges { node { name } } }
          }
        }
      }
    }
    """

    try:
        res = req.post(
            "https://api.producthunt.com/v2/api/graphql",
            json    = {"query": query},
            headers = {
                "Authorization": f"Bearer {PRODUCT_HUNT_TOKEN}",
                "Content-Type" : "application/json"
            },
            timeout = 10
        )
        posts = res.json().get("data", {}).get("posts", {}).get("edges", [])

        for edge in posts:
            try:
                node    = edge["node"]
                name    = node.get("name", "")
                tagline = node.get("tagline", "")
                website = node.get("website", "")
                makers  = node.get("makers", [])
                topics  = [
                    t["node"]["name"]
                    for t in node.get("topics", {}).get("edges", [])
                ]

                if not website or not name:
                    continue

                topics_str = " ".join(topics)
                ai_related = any(
                    t in topics_str.lower()
                    for t in ["artificial intelligence", "developer tools",
                              "productivity", "saas", "machine learning"]
                )

                if not is_relevant(name, tagline, prefs["target_roles"]) \
                        and not ai_related:
                    continue

                if save_company_with_contacts(
                    db          = db,
                    name        = name,
                    website     = website,
                    description = tagline,
                    funding     = "Unknown",
                    team_size   = "1-10",
                    location    = "Remote",
                    source      = "product_hunt",
                    ai_related  = ai_related
                ):
                    saved += 1
                    logger.info(f"  ✅ {name}")

                    # Product Hunt makers directly milte hain
                    # Unka username se GitHub/email dhundho
                    company = db.query(Company).filter(
                        Company.website == website
                    ).first()

                    if company and makers:
                        domain = get_domain(website)
                        for maker in makers[:2]:
                            maker_name = maker.get("name", "")
                            if not maker_name:
                                continue

                            result = find_email_for_person(
                                maker_name, domain
                            )
                            if result["email"]:
                                contact = Contact(
                                    company_id       = company.id,
                                    name             = maker_name,
                                    role             = "Founder/Maker",
                                    email            = result["email"],
                                    confidence_score = result["confidence"],
                                    source           = "product_hunt",
                                    priority         = 1
                                )
                                db.add(contact)

                        db.commit()

            except Exception:
                continue

    except Exception as e:
        logger.error(f"Product Hunt error: {e}")

    logger.info(f"[Product Hunt] {saved} saved")
    return saved


def scrape_github_trending(db: Session, prefs: dict) -> int:
    """
    GitHub Trending — Ab sirf organizations, individuals nahi.
    
    Pehle: Har repo owner save karte the
    Ab: Sirf orgs filter karo + GitHub API se website nikalo
    """
    logger.info("🕷️ GitHub Trending...")
    saved = 0

    languages = ["python", "javascript", "typescript"]

    for lang in languages:
        try:
            res  = req.get(
                f"https://github.com/trending/{lang}?since=weekly",
                headers=HEADERS, timeout=10
            )
            soup  = BeautifulSoup(res.text, "html.parser")
            repos = soup.select("article.Box-row")

            for repo in repos:
                try:
                    name_el = repo.select_one("h2 a")
                    desc_el = repo.select_one("p")

                    if not name_el:
                        continue

                    full_name = name_el.get_text(
                        strip=True
                    ).replace("\n", "").replace(" ", "")

                    description = desc_el.get_text(strip=True) if desc_el else ""

                    # Only orgs — "org/repo" format
                    parts = full_name.split("/")
                    if len(parts) < 2:
                        continue

                    org      = parts[0]
                    repo_url = f"https://github.com/{org}"

                    if company_exists(db, repo_url):
                        continue

                    # GitHub API se org info lo
                    gh_headers = {"User-Agent": "job-hunter"}
                    if GITHUB_TOKEN:
                        gh_headers["Authorization"] = f"token {GITHUB_TOKEN}"

                    org_res  = req.get(
                        f"https://api.github.com/orgs/{org}",
                        headers=gh_headers, timeout=8
                    )

                    if org_res.status_code != 200:
                        # Individual user ho sakta hai — skip
                        continue

                    org_data = org_res.json()
                    org_type = org_data.get("type", "")

                    # Sirf organizations
                    if org_type != "Organization":
                        continue

                    website     = org_data.get("blog", "") or repo_url
                    org_name    = org_data.get("name", org) or org
                    org_desc    = org_data.get("description", description) or description
                    org_email   = org_data.get("email")
                    location    = org_data.get("location", "Remote") or "Remote"

                    if not website.startswith("http"):
                        website = f"https://{website}" if website else repo_url

                    if save_company_with_contacts(
                        db          = db,
                        name        = org_name,
                        website     = website,
                        description = org_desc[:300],
                        funding     = "Unknown",
                        team_size   = "Unknown",
                        location    = location,
                        source      = "github_trending",
                        ai_related  = any(
                            kw in org_desc.lower()
                            for kw in ["ai", "ml", "llm", "model"]
                        )
                    ):
                        saved += 1
                        logger.info(f"  ✅ {org_name} (org)")

                        # GitHub email directly save karo
                        if org_email:
                            company = db.query(Company).filter(
                                Company.website == website
                            ).first()
                            if company:
                                contact = Contact(
                                    company_id       = company.id,
                                    name             = org_name,
                                    role             = "Organization",
                                    email            = org_email,
                                    confidence_score = 0.9,
                                    source           = "github_api",
                                    priority         = 2
                                )
                                db.add(contact)
                                db.commit()

                except Exception:
                    continue

            random_delay()

        except Exception as e:
            logger.error(f"GitHub error {lang}: {e}")

    logger.info(f"[GitHub Trending] {saved} saved")
    return saved


def scrape_reddit(db: Session, prefs: dict) -> int:
    """
    Reddit — Ab Groq se company info extract karo.
    
    Pehle: Post title ko company naam maan lete the
    Ab: Sirf "we built/launched" posts filter karo
        Groq se actual company info nikalo
    """
    logger.info("🕷️ Reddit...")
    saved = 0

    subreddits = [
        ("startups",    "we built|we launched|our startup|we're building"),
        ("forhire",     "hiring|looking for|we need"),
    ]

    for subreddit, keywords in subreddits:
        try:
            res   = req.get(
                f"https://www.reddit.com/r/{subreddit}/new.json?limit=25",
                headers={"User-Agent": "job-hunter-bot/1.0"},
                timeout=10
            )
            posts = res.json().get("data", {}).get("children", [])

            for post in posts:
                try:
                    data     = post["data"]
                    title    = data.get("title", "")
                    selftext = data.get("selftext", "")
                    content  = title + " " + selftext

                    # Filter: sirf relevant posts
                    keyword_match = any(
                        kw in content.lower()
                        for kw in keywords.split("|")
                    )
                    if not keyword_match:
                        continue

                    if not is_relevant(content, "", prefs["target_roles"]):
                        continue

                    # Groq se extract karo
                    prompt = f"""
Extract startup info from this Reddit post.
Return ONLY JSON:
{{
    "company_name": "name or null",
    "website": "url or null",
    "email": "email or null",
    "description": "what they build in 1 line or null"
}}

Post: {content[:400]}
"""
                    res_g = client.chat.completions.create(
                        model      = LLM_MODEL,
                        messages   = [{"role": "user", "content": prompt}],
                        max_tokens = 100,
                        temperature= 0.1
                    )
                    raw  = res_g.choices[0].message.content.strip()
                    raw  = raw.replace("```json", "").replace("```", "").strip()
                    info = json.loads(raw)

                    company_name = info.get("company_name")
                    website      = info.get("website")

                    if not company_name:
                        continue

                    if not website:
                        post_url = f"https://reddit.com{data.get('permalink', '')}"
                        website  = post_url

                    if save_company_with_contacts(
                        db          = db,
                        name        = company_name,
                        website     = website,
                        description = info.get("description", "")[:300],
                        funding     = "Unknown",
                        team_size   = "Unknown",
                        location    = "Remote",
                        source      = "reddit",
                        ai_related  = "ai" in content.lower()
                    ):
                        saved += 1
                        logger.info(f"  ✅ Reddit: {company_name}")

                except Exception:
                    continue

            random_delay()

        except Exception as e:
            logger.error(f"Reddit error {subreddit}: {e}")

    logger.info(f"[Reddit] {saved} saved")
    return saved


def scrape_betalist(db: Session, prefs: dict) -> int:
    """
    Betalist — Pre-launch startups.
    Ab actual website dhundho aur contacts nikalo.
    """
    logger.info("🕷️ Betalist...")
    saved = 0

    try:
        res  = req.get(
            "https://betalist.com/startups",
            headers=HEADERS, timeout=10
        )
        soup = BeautifulSoup(res.text, "html.parser")

        # Updated selectors
        startups = soup.select(
            "li.startup, div.startup, article, "
            "[class*='startup'], [class*='product']"
        )

        for startup in startups[:20]:
            try:
                name_el = startup.select_one(
                    "h2, h3, [class*='name'], [class*='title']"
                )
                desc_el = startup.select_one(
                    "p, [class*='pitch'], [class*='desc']"
                )
                link_el = startup.select_one("a[href]")

                if not name_el:
                    continue

                name = name_el.text.strip()
                desc = desc_el.text.strip() if desc_el else ""
                href = link_el["href"] if link_el else ""

                if not href:
                    continue

                # Betalist page URL → actual website dhundho
                betalist_url = (
                    f"https://betalist.com{href}"
                    if href.startswith("/") else href
                )

                # Visit startup page to get actual website
                startup_res  = req.get(
                    betalist_url, headers=HEADERS, timeout=8
                )
                startup_soup = BeautifulSoup(
                    startup_res.text, "html.parser"
                )

                website_el = startup_soup.select_one(
                    "a[href*='http']:not([href*='betalist'])"
                )
                website = website_el["href"] if website_el else betalist_url

                if save_company_with_contacts(
                    db          = db,
                    name        = name,
                    website     = website,
                    description = desc,
                    funding     = "Pre-launch",
                    team_size   = "1-5",
                    location    = "Remote",
                    source      = "betalist",
                    ai_related  = "ai" in desc.lower()
                ):
                    saved += 1
                    logger.info(f"  ✅ {name}")

            except Exception:
                continue

    except Exception as e:
        logger.error(f"Betalist error: {e}")

    logger.info(f"[Betalist] {saved} saved")
    return saved


def scrape_devto(db: Session, prefs: dict) -> int:
    """
    Dev.to — Sirf 'Show HN' / 'we built' type articles.
    
    Pehle: Har article save karte the
    Ab: Sirf relevant posts + author company dhundho
    """
    logger.info("🕷️ Dev.to...")
    saved = 0

    # Sirf ye tags — actual builders ke posts
    tags = ["showdev", "startup", "buildinpublic"]

    for tag in tags:
        try:
            res      = req.get(
                f"https://dev.to/api/articles?tag={tag}&per_page=10",
                headers=HEADERS, timeout=10
            )
            articles = res.json()

            for article in articles:
                try:
                    title       = article.get("title", "")
                    description = article.get("description", "")
                    url         = article.get("url", "")
                    user        = article.get("user", {})
                    author      = user.get("name", "")
                    username    = user.get("username", "")

                    if not is_relevant(title, description, prefs["target_roles"]):
                        continue

                    # Author ka website dhundho
                    author_res  = req.get(
                        f"https://dev.to/api/users/by_username?url={username}",
                        headers=HEADERS, timeout=8
                    )
                    author_data = author_res.json()
                    website     = (
                        author_data.get("website_url") or
                        author_data.get("github_username") and
                        f"https://github.com/{author_data['github_username']}" or
                        url
                    )

                    if not website:
                        continue

                    if save_company_with_contacts(
                        db          = db,
                        name        = author or title[:50],
                        website     = website,
                        description = description[:300],
                        funding     = "Unknown",
                        team_size   = "Unknown",
                        location    = "Remote",
                        source      = "devto",
                        ai_related  = "ai" in description.lower()
                    ):
                        saved += 1
                        logger.info(f"  ✅ {author}: {title[:40]}")

                except Exception:
                    continue

        except Exception as e:
            logger.error(f"Dev.to error {tag}: {e}")

    logger.info(f"[Dev.to] {saved} saved")
    return saved


def scrape_f6s(db: Session, prefs: dict) -> int:
    """
    F6S — Startup accelerator companies.
    Fixed selectors.
    """
    logger.info("🕷️ F6S...")
    saved = 0

    try:
        res  = req.get(
            "https://www.f6s.com/companies",
            headers=HEADERS, timeout=10
        )
        soup = BeautifulSoup(res.text, "html.parser")

        # Try multiple selector patterns
        companies = (
            soup.select(".company-listing") or
            soup.select("[class*='company']") or
            soup.select("li.item") or
            soup.select("article")
        )

        for company in companies[:20]:
            try:
                name_el = company.select_one(
                    "h2, h3, [class*='name'], strong"
                )
                desc_el = company.select_one(
                    "p, [class*='desc'], [class*='pitch']"
                )
                link_el = company.select_one("a[href]")

                if not name_el:
                    continue

                name    = name_el.text.strip()
                desc    = desc_el.text.strip() if desc_el else ""
                href    = link_el["href"] if link_el else ""
                website = (
                    f"https://www.f6s.com{href}"
                    if href.startswith("/") else href
                )

                if not name or not website:
                    continue

                if save_company_with_contacts(
                    db          = db,
                    name        = name,
                    website     = website,
                    description = desc,
                    funding     = "Unknown",
                    team_size   = "Unknown",
                    location    = "Remote",
                    source      = "f6s",
                    ai_related  = "ai" in desc.lower()
                ):
                    saved += 1
                    logger.info(f"  ✅ {name}")

            except Exception:
                continue

    except Exception as e:
        logger.error(f"F6S error: {e}")

    logger.info(f"[F6S] {saved} saved")
    return saved


def scrape_google_news(db: Session, prefs: dict) -> int:
    """
    Google News — Ab company naam extract karo, news nahi.
    
    Pehle: News article title save karte the
    Ab: Groq se company naam nikalo
        DuckDuckGo se website dhundho
        Contacts nikalo
    """
    logger.info("🕷️ Google News...")
    saved = 0

    queries = [
        "AI startup India funding 2025",
        "SaaS startup India launch 2025",
        "tech startup India hiring 2025",
    ]

    for query in queries:
        try:
            query_encoded = query.replace(" ", "+")
            feed          = feedparser.parse(
                f"https://news.google.com/rss/search"
                f"?q={query_encoded}&hl=en-IN"
            )

            for entry in feed.entries[:5]:
                try:
                    title   = entry.get("title", "")
                    summary = entry.get("summary", "")
                    content = title + " " + summary

                    # Groq se company naam extract karo
                    prompt = f"""
Extract the startup/company name from this news headline.
Return ONLY JSON:
{{
    "company_name": "exact company name or null",
    "description": "what they do in 1 line or null"
}}

Headline: {content[:300]}
"""
                    res_g = client.chat.completions.create(
                        model      = LLM_MODEL,
                        messages   = [{"role": "user", "content": prompt}],
                        max_tokens = 80,
                        temperature= 0.1
                    )
                    raw  = res_g.choices[0].message.content.strip()
                    raw  = raw.replace("```json", "").replace("```", "").strip()
                    info = json.loads(raw)

                    company_name = info.get("company_name")
                    if not company_name:
                        continue

                    # DuckDuckGo se website dhundho
                    from duckduckgo_search import DDGS
                    with DDGS() as ddgs:
                        results = list(ddgs.text(
                            f"{company_name} official website",
                            max_results=1
                        ))

                    website = None
                    if results:
                        website = results[0].get("href")

                    if not website:
                        continue

                    if save_company_with_contacts(
                        db          = db,
                        name        = company_name,
                        website     = website,
                        description = info.get("description", "")[:300],
                        funding     = "Unknown",
                        team_size   = "Unknown",
                        location    = "India",
                        source      = "google_news",
                        ai_related  = "ai" in content.lower()
                    ):
                        saved += 1
                        logger.info(f"  ✅ {company_name}")

                except Exception:
                    continue

        except Exception as e:
            logger.error(f"Google News error: {e}")

    logger.info(f"[Google News] {saved} saved")
    return saved


# ═════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════

def run(db: Session, user_id: int) -> dict:
    logger.info(f"🚀 Scraper — user {user_id}")

    prefs = get_user_preferences(db, user_id)
    logger.info(f"   Roles: {prefs['target_roles']}")

    track_a = {}
    track_b = {}

    # Track A
    if SCRAPER_SOURCES.get("internshala"):
        track_a["internshala"] = scrape_internshala(db, prefs)
    if SCRAPER_SOURCES.get("yc_jobs"):
        track_a["yc_jobs"]     = scrape_yc_jobs(db, prefs)
    if SCRAPER_SOURCES.get("unstop"):
        track_a["unstop"]      = scrape_unstop(db, prefs)
    if SCRAPER_SOURCES.get("remotive"):
        track_a["remotive"]    = scrape_remotive(db, prefs)
    if SCRAPER_SOURCES.get("the_muse"):
        track_a["the_muse"]    = scrape_the_muse(db, prefs)

    # Track B
    if SCRAPER_SOURCES.get("yc_companies"):
        track_b["yc_companies"]    = scrape_yc_companies(db, prefs)
    if SCRAPER_SOURCES.get("hn_hiring"):
        track_b["hn_hiring"]       = scrape_hn_hiring(db, prefs)
    if SCRAPER_SOURCES.get("product_hunt"):
        track_b["product_hunt"]    = scrape_product_hunt(db, prefs)
    if SCRAPER_SOURCES.get("github_trending"):
        track_b["github_trending"] = scrape_github_trending(db, prefs)
    if SCRAPER_SOURCES.get("reddit"):
        track_b["reddit"]          = scrape_reddit(db, prefs)
    if SCRAPER_SOURCES.get("betalist"):
        track_b["betalist"]        = scrape_betalist(db, prefs)
    if SCRAPER_SOURCES.get("devto"):
        track_b["devto"]           = scrape_devto(db, prefs)
    if SCRAPER_SOURCES.get("google_news"):
        track_b["google_news"]     = scrape_google_news(db, prefs)
    if SCRAPER_SOURCES.get("f6s"):
        track_b["f6s"]             = scrape_f6s(db, prefs)

    total_jobs      = sum(track_a.values())
    total_companies = sum(track_b.values())

    logger.info(
        f"✅ Done — {total_jobs} jobs, "
        f"{total_companies} companies"
    )

    return {
        "total_jobs"      : total_jobs,
        "total_companies" : total_companies,
        "track_a"         : track_a,
        "track_b"         : track_b
    }