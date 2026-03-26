# backend/agents/scraper_agent.py
#
# Sources: YC API + Betalist
# HN "Who is Hiring" removed — job postings thread hai, company directory nahi.
# Parsed data unreliable tha (role names as company names, no proper descriptions).

import asyncio
import sys
import time
import random
import re
import requests as req
from bs4                      import BeautifulSoup
from playwright.async_api     import async_playwright
from loguru                   import logger
from concurrent.futures       import ThreadPoolExecutor, as_completed
from typing                   import Generator

import os
from dotenv import load_dotenv
load_dotenv()

APOLLO_API_KEY = os.getenv("APOLLO_API_KEY", "")

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


# ═════════════════════════════════════════════
# HELPERS
# ═════════════════════════════════════════════

def random_delay():
    time.sleep(random.uniform(1, 2))


def get_domain(website: str) -> str:
    return (
        website.replace("https://", "")
                .replace("http://", "")
                .rstrip("/")
                .split("/")[0]
    )


def is_relevant(title: str, desc: str, roles: list) -> bool:
    text = (title + " " + desc).lower()
    return any(r.lower() in text for r in roles)


# ═════════════════════════════════════════════
# EMAIL FINDING
# ═════════════════════════════════════════════

def find_emails_on_website(website: str) -> list:
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
            res = req.get(page, headers=HEADERS, timeout=5)
            if res.status_code != 200:
                continue
            soup = BeautifulSoup(res.text, "html.parser")

            for a in soup.find_all("a", href=True):
                if "mailto:" in a["href"]:
                    email = (
                        a["href"].replace("mailto:", "")
                                 .strip()
                                 .split("?")[0]
                    )
                    if "@" in email and not any(s in email.lower() for s in SKIP):
                        found.append({"email": email, "verified": True})

            for email in re.findall(EMAIL_RE, res.text):
                if domain in email and not any(s in email.lower() for s in SKIP):
                    found.append({"email": email, "verified": True})

        except Exception:
            continue

    seen, unique = set(), []
    for f in found:
        if f["email"] not in seen:
            seen.add(f["email"])
            unique.append(f)
    return unique


def _apollo_lookup(first: str, last: str, domain: str) -> dict | None:
    if not APOLLO_API_KEY:
        return None
    try:
        res = req.post(
            "https://api.apollo.io/v1/people/match",
            json={"first_name": first, "last_name": last, "domain": domain},
            headers={
                "Content-Type" : "application/json",
                "Cache-Control": "no-cache",
                "X-Api-Key"    : APOLLO_API_KEY,
            },
            timeout=8,
        )
        email = res.json().get("person", {}).get("email")
        if email:
            return {"email": email, "verified": True, "source": "apollo"}
    except Exception as e:
        logger.warning(f"Apollo lookup error: {e}")
    return None


def find_best_email(name: str, domain: str) -> dict:
    """Priority: website scrape → Apollo API → pattern fallback"""
    site = find_emails_on_website(f"https://{domain}")
    if site:
        return {**site[0], "source": "website"}

    if not name:
        return {"email": None, "verified": False, "source": "none"}

    parts = name.lower().strip().split()
    first = parts[0]           if parts          else ""
    last  = parts[-1]          if len(parts) > 1 else ""

    if not first:
        return {"email": None, "verified": False, "source": "none"}

    apollo = _apollo_lookup(first, last, domain)
    if apollo:
        return apollo

    email = f"{first}.{last}@{domain}" if (last and last != first) else f"{first}@{domain}"
    return {"email": email, "verified": False, "source": "pattern"}


# ═════════════════════════════════════════════
# SOURCE 1 — YC API
# ═════════════════════════════════════════════

def get_yc_founders(slug: str) -> list:
    try:
        url = f"https://www.ycombinator.com/companies/{slug}"
        res = req.get(url, headers=HEADERS, timeout=10)
        if res.status_code != 200:
            return []
        text = BeautifulSoup(res.text, "html.parser").get_text()
        if "Active Founders" not in text:
            return []
        section = text.split("Active Founders")[1]
        names   = list(dict.fromkeys(
            re.findall(r'([A-Z][a-z]+ [A-Z][a-z]+)\s+Founder', section)
        ))
        return [{"name": n, "role": "Founder"} for n in names[:4]]
    except Exception:
        return []


def stream_yc_companies(prefs: dict) -> Generator:
    try:
        res  = req.get(
            "https://api.ycombinator.com/v0.1/companies?page=1&per_page=100",
            timeout=15,
        )
        data = res.json().get("companies", [])

        ai_tags = [
            "artificial intelligence", "machine learning",
            "developer tools", "saas", "nlp", "llm", "b2b",
        ]

        for c in data:
            name      = c.get("name",            "")
            website   = c.get("website",         "")
            one_liner = c.get("oneLiner",        "") or ""
            long_desc = c.get("longDescription", "") or ""
            desc      = long_desc if long_desc else one_liner
            batch     = c.get("batch",           "")
            slug      = c.get("slug",            "")
            tags      = " ".join(c.get("tags", [])).lower()
            loc       = ", ".join(c.get("locations", []))
            team_size = c.get("teamSize",        "")

            if not website or not name:
                continue

            ai_related = any(t in tags for t in ai_tags)
            relevant   = is_relevant(one_liner, tags, prefs.get("target_roles", []))

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
                "contacts"   : contacts,
            }

    except Exception as e:
        logger.error(f"YC Companies error: {e}")


# ═════════════════════════════════════════════
# SOURCE 2 — BETALIST
# ═════════════════════════════════════════════

async def _scrape_betalist_async(prefs: dict) -> list:
    results      = []
    skip_domains = [
        "betalist", "startup.jobs", "aijobs",
        "web3.career", "vision.directory",
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
                    await sp.goto(f"https://betalist.com{href}", timeout=15000)
                    await sp.wait_for_timeout(1000)

                    full_desc = desc
                    try:
                        desc_el2 = await sp.query_selector(
                            "div.prose, [class*='description'], [class*='pitch']"
                        )
                        if desc_el2:
                            full_desc = (await desc_el2.inner_text()).strip()[:500]
                    except Exception:
                        pass

                    all_links = await sp.query_selector_all("a[href]")
                    website   = None
                    for a in all_links:
                        h = await a.get_attribute("href")
                        if h and h.startswith("http") and not any(d in h for d in skip_domains):
                            website = h
                            break

                    await sp.close()

                    if not website:
                        clean   = name.lower().replace(" ", "").strip()
                        website = f"https://{clean}" if "." in clean else f"https://{clean}.com"

                    site_emails = find_emails_on_website(website)
                    contacts    = [
                        {
                            "name"    : name,
                            "role"    : "Contact",
                            "email"   : e["email"],
                            "verified": e["verified"],
                        }
                        for e in site_emails[:2]
                    ]

                    results.append({
                        "name"       : name,
                        "website"    : website,
                        "one_liner"  : desc,
                        "description": full_desc,
                        "funding"    : "Pre-launch",
                        "team_size"  : "Unknown",
                        "location"   : "Remote",
                        "source"     : "betalist",
                        "contacts"   : contacts,
                    })

                except Exception:
                    continue

        except Exception as e:
            logger.error(f"Betalist async error: {e}")
        finally:
            try:
                await browser.close()
            except Exception:
                pass

    return results


def _run_betalist(prefs: dict) -> list:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_scrape_betalist_async(prefs))
    except Exception as e:
        logger.error(f"Betalist run error: {e}")
        return []
    finally:
        loop.close()


def stream_betalist(prefs: dict) -> Generator:
    yield from _run_betalist(prefs)


# ═════════════════════════════════════════════
# RUNNER WRAPPERS
# ═════════════════════════════════════════════

def _run_yc(prefs: dict) -> list:
    return list(stream_yc_companies(prefs))


# ═════════════════════════════════════════════
# PARALLEL SCRAPING
# ═════════════════════════════════════════════

def scrape_track_b(prefs: dict) -> list:
    """
    YC + Betalist parallel chalao.
    HN removed — "Who is Hiring" thread job postings hai, company directory nahi.
    Parsed data unreliable tha (role names as company names, no descriptions).
    """
    companies = []
    scrapers  = [
        ("yc",       _run_yc,       prefs),
        ("betalist", _run_betalist, prefs),
    ]
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(fn, p): name for name, fn, p in scrapers}
        for future in as_completed(futures):
            source = futures[future]
            try:
                result = future.result()
                companies.extend(result)
                logger.info(f"  ✅ {source}: {len(result)} companies")
            except Exception as e:
                logger.error(f"  ❌ {source} failed: {e}")
    return companies


def run(user_id: int, prefs: dict) -> dict:
    logger.info(f"🚀 Scraper starting — user {user_id}")
    logger.info(f"   Domains: {prefs.get('domains')}")
    logger.info(f"   Roles  : {prefs.get('target_roles')}")
    track_b = scrape_track_b(prefs)
    logger.info(f"   Total  : {len(track_b)} companies")
    return {"track_b": track_b, "total_companies": len(track_b)}


# ─────────────────────────────────────────────
# LOCAL TEST
# ─────────────────────────────────────────────
if __name__ == "__main__":
    prefs = {
        "domains"     : ["ai_ml", "data_science"],
        "target_roles": ["ai engineer", "ml engineer", "data scientist"],
        "location"    : "remote",
    }
    result = run(user_id=1, prefs=prefs)
    logger.info(f"Companies: {result['total_companies']}")