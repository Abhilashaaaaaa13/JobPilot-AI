# backend/agents/scraper_agent.py

import time
import random
import json
from datetime import date
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import requests as req
from sqlalchemy.orm import Session
from backend.models.job import Job
from backend.models.company import Company
from backend.models.user import UserProfile
from loguru import logger

TODAY = str(date.today())

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def random_delay():
    time.sleep(random.uniform(2, 5))


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
        "target_roles"       : parse(profile.target_roles,
                                     ["software engineer", "intern"]),
        "preferred_type"     : profile.preferred_type or "both",
        "preferred_locations": parse(profile.preferred_locations, ["remote"]),
        "min_fit_score"      : profile.min_fit_score or 50
    }


def job_exists(db: Session, apply_url: str) -> bool:
    """Duplicate job check — apply_url unique hai"""
    return db.query(Job).filter(
        Job.apply_url == apply_url
    ).first() is not None


def company_exists(db: Session, website: str) -> bool:
    """Duplicate company check — website unique hai"""
    return db.query(Company).filter(
        Company.website == website
    ).first() is not None


def save_job(db: Session, data: dict) -> bool:
    """
    Job table mein save karo.
    Already exists? Skip karo.
    Returns True agar naya save hua.
    """
    if job_exists(db, data["apply_url"]):
        return False

    job = Job(**data)
    db.add(job)
    try:
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Job save error: {e}")
        return False


def save_company(db: Session, data: dict) -> bool:
    """
    Company table mein save karo.
    Already exists? Skip karo.
    Returns True agar naya save hua.
    """
    if company_exists(db, data["website"]):
        return False

    company = Company(**data)
    db.add(company)
    try:
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Company save error: {e}")
        return False


# ─────────────────────────────────────────────
# SOURCE 1 — Internshala → Job Table
# ─────────────────────────────────────────────

def scrape_internshala(db: Session, prefs: dict) -> int:
    logger.info("🕷️ Internshala scraping shuru...")
    saved = 0

    urls = []

    if prefs["preferred_type"] in ["internship", "both"]:
        urls += [
            "https://internshala.com/internships/computer-science-internship/",
            "https://internshala.com/internships/python-django-internship/",
            "https://internshala.com/internships/machine-learning-internship/",
            "https://internshala.com/internships/web-development-internship/",
            "https://internshala.com/internships/artificial-intelligence-internship/",
        ]

    if prefs["preferred_type"] in ["job", "both"]:
        urls += [
            "https://internshala.com/jobs/software-development-job/",
            "https://internshala.com/jobs/python-job/",
        ]

    for url in urls:
        try:
            res  = req.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(res.text, "html.parser")
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
                    location  = loc_el.text.strip() if loc_el else "Remote"
                    stipend   = stipend_el.text.strip() if stipend_el else "Not mentioned"
                    apply_url = (
                        "https://internshala.com" + link_el["href"]
                        if link_el else url
                    )

                    if not is_relevant(title, "", prefs["target_roles"]):
                        continue

                    # Job table mein save karo
                    data = {
                        "title"       : title,
                        "company_name": company,
                        "location"    : location,
                        "job_type"    : "internship" if "internship" in url else "job",
                        "stipend"     : stipend,
                        "description" : title,
                        "apply_url"   : apply_url,
                        "source"      : "internshala",
                        "status"      : "new"
                    }

                    if save_job(db, data):
                        saved += 1
                        logger.info(f"  ✅ {title} @ {company}")

                except Exception as e:
                    logger.warning(f"  ⚠️ Card error: {e}")
                    continue

            random_delay()

        except Exception as e:
            logger.error(f"  ❌ Internshala error: {e}")

    logger.info(f"[Internshala] {saved} jobs saved")
    return saved


# ─────────────────────────────────────────────
# SOURCE 2 — YC Job Board → Job Table
# ─────────────────────────────────────────────

def scrape_yc_jobs(db: Session, prefs: dict) -> int:
    logger.info("🕷️ YC Jobs scraping shuru...")
    saved = 0

    try:
        res  = req.get(
            "https://www.workatastartup.com/jobs",
            headers=HEADERS,
            timeout=15
        )
        soup = BeautifulSoup(res.text, "html.parser")
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

                data = {
                    "title"       : title,
                    "company_name": company,
                    "location"    : "Remote / SF",
                    "job_type"    : "job",
                    "stipend"     : "Not mentioned",
                    "description" : title,
                    "apply_url"   : apply_url,
                    "source"      : "yc_jobs",
                    "status"      : "new"
                }

                if save_job(db, data):
                    saved += 1
                    logger.info(f"  ✅ {title} @ {company}")

            except Exception as e:
                logger.warning(f"  ⚠️ YC job error: {e}")
                continue

    except Exception as e:
        logger.error(f"  ❌ YC jobs error: {e}")

    logger.info(f"[YC Jobs] {saved} jobs saved")
    return saved


# ─────────────────────────────────────────────
# SOURCE 3 — Wellfound → Job Table
# Playwright — JS heavy
# ─────────────────────────────────────────────

def scrape_wellfound(db: Session, prefs: dict) -> int:
    logger.info("🕷️ Wellfound scraping shuru...")
    saved = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page    = browser.new_page()

        try:
            role_query = prefs["target_roles"][0].replace(" ", "%20")
            page.goto(
                f"https://wellfound.com/jobs?q={role_query}",
                timeout=30000
            )
            page.wait_for_timeout(4000)

            cards = page.query_selector_all(
                "[data-test='JobListingCard']"
            )

            for card in cards:
                try:
                    title_el   = card.query_selector("h2")
                    company_el = card.query_selector(
                        "[data-test='startup-name']"
                    )
                    loc_el     = card.query_selector(
                        "[data-test='job-location']"
                    )
                    link_el    = card.query_selector("a")

                    if not title_el:
                        continue

                    title     = title_el.inner_text().strip()
                    company   = (company_el.inner_text().strip()
                                 if company_el else "Startup")
                    location  = (loc_el.inner_text().strip()
                                 if loc_el else "Remote")
                    href      = (link_el.get_attribute("href")
                                 if link_el else "")
                    apply_url = (
                        "https://wellfound.com" + href
                        if href.startswith("/") else href
                    )

                    if not apply_url:
                        continue

                    if not is_relevant(title, "", prefs["target_roles"]):
                        continue

                    data = {
                        "title"       : title,
                        "company_name": company,
                        "location"    : location,
                        "job_type"    : "job",
                        "stipend"     : "Not mentioned",
                        "description" : title,
                        "apply_url"   : apply_url,
                        "source"      : "wellfound",
                        "status"      : "new"
                    }

                    if save_job(db, data):
                        saved += 1
                        logger.info(f"  ✅ {title} @ {company}")

                except Exception as e:
                    logger.warning(f"  ⚠️ Wellfound card error: {e}")
                    continue

        except Exception as e:
            logger.error(f"  ❌ Wellfound error: {e}")

        browser.close()

    logger.info(f"[Wellfound] {saved} jobs saved")
    return saved


# ─────────────────────────────────────────────
# SOURCE 4 — Unstop → Job Table
# Public JSON API
# ─────────────────────────────────────────────

def scrape_unstop(db: Session, prefs: dict) -> int:
    logger.info("🕷️ Unstop scraping shuru...")
    saved = 0

    try:
        res = req.get(
            "https://unstop.com/api/public/opportunity/search-result"
            "?opportunity=jobs&per_page=20&page=1",
            headers=HEADERS,
            timeout=10
        )
        items = res.json().get("data", {}).get("data", [])

        for item in items:
            try:
                title     = item.get("title", "")
                company   = item.get("organisation", {}).get("name", "Unknown")
                location  = item.get("city", "Remote")
                slug      = item.get("public_url", "")
                apply_url = f"https://unstop.com/{slug}"

                if not is_relevant(title, "", prefs["target_roles"]):
                    continue

                data = {
                    "title"       : title,
                    "company_name": company,
                    "location"    : location,
                    "job_type"    : "job",
                    "stipend"     : "Not mentioned",
                    "description" : title,
                    "apply_url"   : apply_url,
                    "source"      : "unstop",
                    "status"      : "new"
                }

                if save_job(db, data):
                    saved += 1
                    logger.info(f"  ✅ {title} @ {company}")

            except Exception as e:
                logger.warning(f"  ⚠️ Unstop item error: {e}")
                continue

    except Exception as e:
        logger.error(f"  ❌ Unstop error: {e}")

    logger.info(f"[Unstop] {saved} jobs saved")
    return saved


# ─────────────────────────────────────────────
# SOURCE 5 — YC Companies API → Company Table
# Cold email targets
# Opening nahi bhi hai toh bhi email bhejenge
# ─────────────────────────────────────────────

def scrape_yc_companies(db: Session, prefs: dict) -> int:
    logger.info("🕷️ YC Companies API scraping shuru...")
    saved = 0

    try:
        res       = req.get(
            "https://api.ycombinator.com/v0.1/companies"
            "?page=1&per_page=50",
            headers=HEADERS,
            timeout=15
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

                # Relevance check —
                # AI/ML companies always include
                # chahe role match na kare
                ai_tags = [
                    "ai", "ml", "machine learning",
                    "nlp", "llm", "artificial intelligence",
                    "generative", "developer tools"
                ]
                ai_related = any(t in tags.lower() for t in ai_tags)
                role_match = is_relevant(
                    description, tags, prefs["target_roles"]
                )

                if not ai_related and not role_match:
                    continue

                # Company table mein save karo
                data = {
                    "name"        : name,
                    "website"     : website,
                    "description" : description,
                    "tech_stack"  : None,
                    "funding"     : f"YC {batch}",
                    "team_size"   : team_size,
                    "location"    : location,
                    "source"      : "yc_api",
                    "ai_related"  : ai_related,
                    "research_done": False
                }

                if save_company(db, data):
                    saved += 1
                    logger.info(f"  ✅ {name} — {description[:50]}")

            except Exception as e:
                logger.warning(f"  ⚠️ YC company error: {e}")
                continue

        random_delay()

    except Exception as e:
        logger.error(f"  ❌ YC API error: {e}")

    logger.info(f"[YC Companies] {saved} companies saved")
    return saved


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def run(db: Session, user_id: int) -> dict:
    logger.info(f"🚀 Scraper Agent — user {user_id}")

    prefs = get_user_preferences(db, user_id)
    logger.info(f"   Roles: {prefs['target_roles']}")
    logger.info(f"   Type : {prefs['preferred_type']}")

    results = {
        "internshala"  : scrape_internshala(db, prefs),
        "yc_jobs"      : scrape_yc_jobs(db, prefs),
        "wellfound"    : scrape_wellfound(db, prefs),
        "unstop"       : scrape_unstop(db, prefs),
        "yc_companies" : scrape_yc_companies(db, prefs),
    }

    total_jobs      = (results["internshala"] + results["yc_jobs"] +
                       results["wellfound"]   + results["unstop"])
    total_companies = results["yc_companies"]

    logger.info(f"✅ Done — {total_jobs} jobs, {total_companies} companies")

    return {
        "total_jobs"      : total_jobs,
        "total_companies" : total_companies,
        "breakdown"       : results
    }