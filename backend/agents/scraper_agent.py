# backend/agents/scraper_agent.py

import asyncio
import sys
import time
import random
import re
import smtplib
import dns.resolver
import requests as req
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from loguru import logger
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Generator

import os
from dotenv import load_dotenv
load_dotenv()

PRODUCT_HUNT_TOKEN = os.getenv("PRODUCT_HUNT_TOKEN", "")
APOLLO_API_KEY     = os.getenv("APOLLO_API_KEY", "")

EMAIL_RE = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
HEADERS  = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    )
}
SKIP = [
    "noreply", "no-reply", "support", "example",
    "test", "spam", "info", "privacy", "legal", "abuse"
]

DOMAIN_INTERNSHIP_URLS = {
    "ai_ml": [
        "machine-learning-internship",
        "artificial-intelligence-internship",
        "data-science-internship",
    ],
    "web_dev": [
        "web-development-internship",
        "frontend-development-internship",
        "react-internship",
    ],
    "backend": [
        "python-django-internship",
        "backend-development-internship",
        "nodejs-internship",
    ],
    "data_science": [
        "data-science-internship",
        "data-analytics-internship",
        "business-analytics-internship",
    ],
    "software": [
        "computer-science-internship",
        "software-development-internship",
    ],
    "full_stack": [
        "full-stack-internship",
        "mern-stack-internship",
    ],
    "product": [
        "product-management-internship",
    ],
}

DOMAIN_JOB_URLS = {
    "ai_ml": [
        "machine-learning-job",
        "artificial-intelligence-job",
        "data-science-job",
    ],
    "web_dev": [
        "web-development-job",
        "frontend-development-job",
    ],
    "backend": [
        "python-job",
        "backend-development-job",
    ],
    "data_science": [
        "data-science-job",
        "data-analytics-job",
    ],
    "software": [
        "software-development-job",
    ],
    "full_stack": [
        "full-stack-job",
    ],
    "product": [
        "product-management-job",
    ],
}


# ═════════════════════════════════════════════
# HELPERS
# ═════════════════════════════════════════════

def random_delay():
    time.sleep(random.uniform(1, 2))


def get_domain(website):
    return website.replace("https://", "")\
                  .replace("http://", "")\
                  .rstrip("/").split("/")[0]


def is_relevant(title, desc, roles):
    text = (title + " " + desc).lower()
    return any(r.lower() in text for r in roles)


# ═════════════════════════════════════════════
# EMAIL FINDING
# ═════════════════════════════════════════════

def find_emails_on_website(website):
    domain = get_domain(website)
    pages  = [
        website.rstrip("/"),
        website.rstrip("/") + "/contact",
        website.rstrip("/") + "/contact-us",
        website.rstrip("/") + "/about",
        website.rstrip("/") + "/about-us",
        website.rstrip("/") + "/team",
    ]
    found = []
    for page in pages:
        try:
            res  = req.get(page, headers=HEADERS, timeout=5)
            if res.status_code != 200:
                continue
            soup = BeautifulSoup(res.text, "html.parser")

            for a in soup.find_all("a", href=True):
                if "mailto:" in a["href"]:
                    email = a["href"].replace(
                        "mailto:", ""
                    ).strip().split("?")[0]
                    if "@" in email and not any(
                        s in email.lower() for s in SKIP
                    ):
                        found.append({
                            "email"   : email,
                            "verified": True
                        })

            for email in re.findall(EMAIL_RE, res.text):
                if domain in email and not any(
                    s in email.lower() for s in SKIP
                ):
                    found.append({
                        "email"   : email,
                        "verified": True
                    })

        except:
            continue

    seen   = set()
    unique = []
    for f in found:
        if f["email"] not in seen:
            seen.add(f["email"])
            unique.append(f)
    return unique


def smtp_verify(email):
    try:
        domain = email.split("@")[1]
        mx     = dns.resolver.resolve(domain, "MX")
        host   = str(mx[0].exchange).rstrip(".")
        with smtplib.SMTP(timeout=5) as s:
            s.connect(host, 25)
            s.helo("verify.com")
            s.mail("v@v.com")
            code, _ = s.rcpt(email)
            return code == 250
    except:
        return False


def find_best_email(name, domain):
    site = find_emails_on_website(f"https://{domain}")
    if site:
        return site[0]

    if not name:
        return {"email": None, "verified": False}

    parts = name.lower().strip().split()
    first = parts[0] if parts else ""
    last  = parts[-1] if len(parts) > 1 else ""

    if not first:
        return {"email": None, "verified": False}

    patterns = [f"{first}@{domain}"]
    if last and last != first:
        patterns += [
            f"{first}.{last}@{domain}",
            f"{first}{last}@{domain}",
        ]

    for email in patterns:
        if smtp_verify(email):
            return {"email": email, "verified": True}

    if APOLLO_API_KEY:
        try:
            res = req.post(
                "https://api.apollo.io/v1/people/match",
                json={
                    "first_name": first,
                    "last_name" : last,
                    "domain"    : domain
                },
                headers={
                    "Content-Type" : "application/json",
                    "Cache-Control": "no-cache",
                    "X-Api-Key"    : APOLLO_API_KEY
                },
                timeout=8
            )
            email = res.json().get("person", {}).get("email")
            if email:
                return {"email": email, "verified": True}
        except:
            pass

    return {
        "email"   : f"{first}@{domain}",
        "verified": False
    }


# ═════════════════════════════════════════════
# TRACK A — STREAMING GENERATORS
# ═════════════════════════════════════════════

def stream_internshala(prefs: dict) -> Generator:
    """Yields jobs one by one as scraped."""
    domains   = prefs.get("domains", ["ai_ml"])
    pref_type = prefs.get("preferred_type", "both")
    seen_urls = set()
    urls      = []

    if pref_type in ["internship", "both"]:
        for domain in domains:
            for slug in DOMAIN_INTERNSHIP_URLS.get(domain, []):
                urls.append((
                    f"https://internshala.com/internships/{slug}/",
                    "internship"
                ))

    if pref_type in ["job", "both"]:
        for domain in domains:
            for slug in DOMAIN_JOB_URLS.get(domain, []):
                urls.append((
                    f"https://internshala.com/jobs/{slug}/",
                    "job"
                ))

    for url, job_type in urls:
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
                    desc_el    = card.select_one(".job-internship-details")

                    if not title_el or not company_el:
                        continue

                    title     = title_el.text.strip()
                    company   = company_el.text.strip()
                    apply_url = (
                        "https://internshala.com" + link_el["href"]
                        if link_el else url
                    )

                    if apply_url in seen_urls:
                        continue
                    seen_urls.add(apply_url)

                    if not is_relevant(title, "", prefs.get("target_roles", [])):
                        continue

                    yield {
                        "title"      : title,
                        "company"    : company,
                        "location"   : loc_el.text.strip() if loc_el else "Remote",
                        "stipend"    : stipend_el.text.strip() if stipend_el else "Not mentioned",
                        "description": desc_el.text.strip()[:300] if desc_el else title,
                        "url"        : apply_url,
                        "type"       : job_type,
                        "source"     : "internshala"
                    }

                except:
                    continue

            random_delay()

        except Exception as e:
            logger.error(f"Internshala error: {e}")


def stream_remotive(prefs: dict) -> Generator:
    if prefs.get("preferred_type") == "internship":
        return

    try:
        res      = req.get(
            "https://remotive.com/api/remote-jobs?limit=50",
            timeout=10
        )
        all_jobs = res.json().get("jobs", [])

        for j in all_jobs:
            title   = j.get("title", "")
            company = j.get("company_name", "")
            desc    = BeautifulSoup(
                j.get("description", ""), "html.parser"
            ).get_text()[:300]
            url     = j.get("url", "")
            loc     = j.get("candidate_required_location", "Remote")

            if not is_relevant(title, desc, prefs.get("target_roles", [])):
                continue

            yield {
                "title"      : title,
                "company"    : company,
                "location"   : loc,
                "stipend"    : "Not mentioned",
                "description": desc,
                "url"        : url,
                "type"       : "job",
                "source"     : "remotive"
            }

    except Exception as e:
        logger.error(f"Remotive error: {e}")


def stream_unstop(prefs: dict) -> Generator:
    try:
        pref_type   = prefs.get("preferred_type", "both")
        opportunity = (
            "internships" if pref_type == "internship" else "jobs"
        )
        res   = req.get(
            f"https://unstop.com/api/public/opportunity/search-result"
            f"?opportunity={opportunity}&per_page=20&page=1",
            headers=HEADERS, timeout=10
        )
        items = res.json().get("data", {}).get("data", [])

        for item in items:
            title   = item.get("title", "")
            company = item.get("organisation", {}).get("name", "")
            loc     = item.get("city", "Remote") or "Remote"
            slug    = item.get("public_url", "")
            url     = f"https://unstop.com/{slug}"
            desc    = item.get("description", title)[:300]

            if not is_relevant(title, desc, prefs.get("target_roles", [])):
                continue

            yield {
                "title"      : title,
                "company"    : company,
                "location"   : loc,
                "stipend"    : "Not mentioned",
                "description": desc,
                "url"        : url,
                "type"       : opportunity[:-1],
                "source"     : "unstop"
            }

    except Exception as e:
        logger.error(f"Unstop error: {e}")


def stream_yc_jobs(prefs: dict) -> Generator:
    if prefs.get("preferred_type") == "internship":
        return

    try:
        res   = req.get(
            "https://www.workatastartup.com/jobs",
            headers=HEADERS, timeout=15
        )
        soup  = BeautifulSoup(res.text, "html.parser")
        cards = soup.select(".posting-title, .job-name")

        for card in cards:
            try:
                title  = card.text.strip()
                parent = card.find_parent("a")
                url    = (
                    "https://www.workatastartup.com" + parent["href"]
                    if parent and parent.get("href") else ""
                )
                if not url or not title:
                    continue

                if not is_relevant(title, "", prefs.get("target_roles", [])):
                    continue

                yield {
                    "title"      : title,
                    "company"    : "YC Startup",
                    "location"   : "Remote / SF",
                    "stipend"    : "Not mentioned",
                    "description": title,
                    "url"        : url,
                    "type"       : "job",
                    "source"     : "yc_jobs"
                }

            except:
                continue

    except Exception as e:
        logger.error(f"YC Jobs error: {e}")


# ═════════════════════════════════════════════
# TRACK B — STREAMING GENERATORS
# ═════════════════════════════════════════════

def get_yc_founders(slug):
    try:
        url  = f"https://www.ycombinator.com/companies/{slug}"
        res  = req.get(url, headers=HEADERS, timeout=10)
        if res.status_code != 200:
            return []
        text = BeautifulSoup(res.text, "html.parser").get_text()
        if "Active Founders" not in text:
            return []
        section = text.split("Active Founders")[1]
        names   = list(dict.fromkeys(
            re.findall(
                r'([A-Z][a-z]+ [A-Z][a-z]+)\s+Founder',
                section
            )
        ))
        return [{"name": n, "role": "Founder"} for n in names[:4]]
    except:
        return []


def stream_yc_companies(prefs: dict) -> Generator:
    try:
        res  = req.get(
            "https://api.ycombinator.com/v0.1/companies"
            "?page=1&per_page=100",
            timeout=15
        )
        data = res.json().get("companies", [])

        ai_tags = [
            "artificial intelligence", "machine learning",
            "developer tools", "saas", "nlp", "llm", "b2b"
        ]

        for c in data:
            name      = c.get("name", "")
            website   = c.get("website", "")
            one_liner = c.get("oneLiner", "") or ""
            long_desc = c.get("longDescription", "") or ""
            desc      = long_desc if long_desc else one_liner
            batch     = c.get("batch", "")
            slug      = c.get("slug", "")
            tags      = " ".join(c.get("tags", [])).lower()
            loc       = ", ".join(c.get("locations", []))
            team_size = c.get("teamSize", "")

            if not website or not name:
                continue

            ai_related = any(t in tags for t in ai_tags)
            relevant   = is_relevant(
                one_liner, tags, prefs.get("target_roles", [])
            )

            if not ai_related and not relevant:
                continue

            domain   = get_domain(website)
            founders = get_yc_founders(slug)
            contacts = []

            for f in founders:
                result = find_best_email(f["name"], domain)
                if result["email"]:
                    contacts.append({
                        "name"    : f["name"],
                        "role"    : "Founder",
                        "email"   : result["email"],
                        "verified": result["verified"],
                    })

            yield {
                "name"       : name,
                "website"    : website,
                "one_liner"  : one_liner,
                "description": desc[:500] if desc else one_liner,
                "funding"    : f"YC {batch}",
                "team_size"  : str(team_size),
                "location"   : loc,
                "source"     : "yc_api",
                "contacts"   : contacts
            }

    except Exception as e:
        logger.error(f"YC Companies error: {e}")


def stream_hn_hiring(prefs: dict) -> Generator:
    try:
        hits = req.get(
            "https://hn.algolia.com/api/v1/search"
            "?query=who+is+hiring&tags=story&hitsPerPage=1",
            timeout=10
        ).json().get("hits", [])

        if not hits:
            return

        thread_id = hits[0]["objectID"]
        comments  = req.get(
            f"https://hn.algolia.com/api/v1/search"
            f"?tags=comment,story_{thread_id}&hitsPerPage=100",
            timeout=10
        ).json().get("hits", [])

        for comment in comments:
            text = BeautifulSoup(
                comment.get("comment_text", ""), "html.parser"
            ).get_text()

            if not text or len(text) < 30:
                continue

            if not is_relevant(text, "", prefs.get("target_roles", [])):
                continue

            emails = [
                e for e in re.findall(EMAIL_RE, text)
                if not any(s in e.lower() for s in SKIP)
            ]
            if not emails:
                continue

            lines  = [l.strip() for l in text.split("\n") if l.strip()]
            name   = lines[0][:80] if lines else "HN Company"
            obj_id = comment.get("objectID", "")
            desc   = " ".join(lines[:6])[:500]

            yield {
                "name"       : name,
                "website"    : f"https://news.ycombinator.com/item?id={obj_id}",
                "one_liner"  : lines[0][:100] if lines else "",
                "description": desc,
                "funding"    : "Unknown",
                "team_size"  : "Unknown",
                "location"   : "Remote",
                "source"     : "hn_hiring",
                "contacts"   : [
                    {
                        "name"    : "Hiring Contact",
                        "role"    : "Founder/HR",
                        "email"   : e,
                        "verified": True,
                    }
                    for e in emails[:2]
                ]
            }

    except Exception as e:
        logger.error(f"HN error: {e}")


async def _scrape_betalist_async(prefs: dict) -> list:
    results      = []
    skip_domains = [
        "betalist", "startup.jobs", "aijobs",
        "web3.career", "vision.directory"
    ]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page    = await browser.new_page()

        try:
            await page.goto("https://betalist.com", timeout=30000)
            await page.wait_for_timeout(1500)

            rows = await page.query_selector_all(".startup-row")

            for row in rows[:10]:
                try:
                    name_el = await row.query_selector("span.font-medium")
                    desc_el = await row.query_selector("span.text-gray-500")
                    link_el = await row.query_selector("a")

                    name = await name_el.inner_text() if name_el else ""
                    desc = await desc_el.inner_text() if desc_el else ""
                    href = await link_el.get_attribute("href") if link_el else ""

                    if not name or not href:
                        continue

                    sp = await browser.new_page()
                    await sp.goto(
                        f"https://betalist.com{href}",
                        timeout=15000
                    )
                    await sp.wait_for_timeout(1000)

                    # Full description
                    full_desc = desc
                    try:
                        desc_el2 = await sp.query_selector(
                            "div.prose, [class*='description'], [class*='pitch']"
                        )
                        if desc_el2:
                            full_desc = (await desc_el2.inner_text()).strip()[:500]
                    except:
                        pass

                    # Website
                    all_links = await sp.query_selector_all("a[href]")
                    website   = None

                    for a in all_links:
                        h = await a.get_attribute("href")
                        if (h and h.startswith("http")
                                and not any(d in h for d in skip_domains)):
                            website = h
                            break

                    await sp.close()

                    if not website:
                        clean = name.lower().replace(" ", "").strip()
                        website = (
                            f"https://{clean}"
                            if "." in clean
                            else f"https://{clean}.com"
                        )

                    domain      = get_domain(website)
                    site_emails = find_emails_on_website(website)
                    contacts    = []

                    if site_emails:
                        for e in site_emails[:2]:
                            contacts.append({
                                "name"    : name,
                                "role"    : "Contact",
                                "email"   : e["email"],
                                "verified": e["verified"],
                            })

                    results.append({
                        "name"       : name,
                        "website"    : website,
                        "one_liner"  : desc,
                        "description": full_desc,
                        "funding"    : "Pre-launch",
                        "team_size"  : "Unknown",
                        "location"   : "Remote",
                        "source"     : "betalist",
                        "contacts"   : contacts
                    })

                except:
                    continue

        except Exception as e:
            logger.error(f"Betalist async error: {e}")
        finally:
            try:
                await browser.close()
            except:
                pass

    return results


def stream_betalist(prefs: dict) -> Generator:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(
            asyncio.WindowsProactorEventLoopPolicy()
        )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        results = loop.run_until_complete(
            _scrape_betalist_async(prefs)
        )
        for r in results:
            yield r
    except Exception as e:
        logger.error(f"Betalist stream error: {e}")
    finally:
        loop.close()


# ═════════════════════════════════════════════
# PARALLEL SCRAPING
# ═════════════════════════════════════════════

def scrape_track_a(prefs: dict) -> list:
    """All Track A sources — returns list."""
    jobs = []
    for job in stream_internshala(prefs):
        jobs.append(job)
    for job in stream_remotive(prefs):
        jobs.append(job)
    for job in stream_unstop(prefs):
        jobs.append(job)
    for job in stream_yc_jobs(prefs):
        jobs.append(job)
    return jobs


def scrape_track_b(prefs: dict) -> list:
    """All Track B sources — returns list."""
    companies = []
    for co in stream_yc_companies(prefs):
        companies.append(co)
    for co in stream_hn_hiring(prefs):
        companies.append(co)
    for co in stream_betalist(prefs):
        companies.append(co)
    return companies


def run(user_id: int, prefs: dict) -> dict:
    """
    Parallel scraping — Track A + Track B simultaneously.
    """
    logger.info(f"🚀 Scraper starting — user {user_id}")
    logger.info(f"   Type   : {prefs.get('preferred_type')}")
    logger.info(f"   Domains: {prefs.get('domains')}")
    logger.info(f"   Roles  : {prefs.get('target_roles')}")

    track_a = []
    track_b = []

    # Parallel execution
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_a = executor.submit(scrape_track_a, prefs)
        future_b = executor.submit(scrape_track_b, prefs)

        track_a = future_a.result()
        track_b = future_b.result()

    logger.info(
        f"✅ Done — {len(track_a)} jobs, "
        f"{len(track_b)} companies"
    )

    return {
        "total_jobs"      : len(track_a),
        "total_companies" : len(track_b),
        "track_a"         : track_a,
        "track_b"         : track_b
    }


if __name__ == "__main__":
    prefs = {
        "preferred_type": "both",
        "domains"       : ["ai_ml", "data_science"],
        "target_roles"  : ["ai engineer", "ml engineer", "data scientist"],
        "location"      : "remote"
    }
    result = run(user_id=1, prefs=prefs)
    logger.info(f"Jobs: {result['total_jobs']}")
    logger.info(f"Companies: {result['total_companies']}")