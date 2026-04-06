# backend/agents/scraper_agent.py
#
# Sources: YC API + Betalist + Product Hunt + Indie Hackers + GitHub Trending + HN Hiring
# Agent logic: fallback to cached feed if < 10 companies scraped
# All sources run in parallel via ThreadPoolExecutor

import asyncio
import sys
import time
import random
import re
import requests as req
from bs4                  import BeautifulSoup
from playwright.async_api import async_playwright
from loguru               import logger
from concurrent.futures   import ThreadPoolExecutor, as_completed
from typing               import Generator

import os
from dotenv import load_dotenv
load_dotenv()

APOLLO_API_KEY     = os.getenv("APOLLO_API_KEY",     "")
PRODUCT_HUNT_TOKEN = os.getenv("PRODUCT_HUNT_TOKEN", "")

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
    first = parts[0]  if parts          else ""
    last  = parts[-1] if len(parts) > 1 else ""

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


# ═════════════════════════════════════════════
# SOURCE 3 — PRODUCT HUNT (free tier)
# ═════════════════════════════════════════════

def _run_product_hunt(prefs: dict = None, limit: int = 20) -> list:
    """
    Product Hunt GraphQL API — token chahiye (free tier available).
    Token nahi? Skip silently.
    """
    if not PRODUCT_HUNT_TOKEN:
        logger.info("  Product Hunt token nahi hai — skipping")
        return []

    query = """
    query {
      posts(first: %d, order: NEWEST, topic: "developer-tools") {
        edges {
          node {
            name tagline description website votesCount
            makers { name twitterUsername }
          }
        }
      }
    }
    """ % limit

    try:
        res   = req.post(
            "https://api.producthunt.com/v2/api/graphql",
            json    = {"query": query},
            headers = {
                "Authorization": f"Bearer {PRODUCT_HUNT_TOKEN}",
                "Content-Type" : "application/json",
            },
            timeout=15,
        )
        edges = res.json().get("data", {}).get("posts", {}).get("edges", [])
    except Exception as e:
        logger.error(f"Product Hunt error: {e}")
        return []

    companies = []
    for edge in edges:
        node    = edge.get("node", {})
        name    = node.get("name",        "")
        tagline = node.get("tagline",     "")
        desc    = node.get("description", "") or tagline
        website = node.get("website",     "")
        makers  = node.get("makers",      [])

        if not name or not website:
            continue

        contacts = []
        for maker in makers[:2]:
            mname   = maker.get("name", "")
            twitter = maker.get("twitterUsername", "")
            if mname:
                contacts.append({
                    "name"    : mname,
                    "role"    : "Maker",
                    "email"   : None,
                    "twitter" : f"https://twitter.com/{twitter}" if twitter else "",
                    "verified": False,
                })

        companies.append({
            "name"       : name,
            "website"    : website,
            "one_liner"  : tagline,
            "description": desc[:500],
            "funding"    : "Product Hunt",
            "team_size"  : "Unknown",
            "location"   : "Remote",
            "source"     : "product_hunt",
            "contacts"   : contacts,
        })

    logger.info(f"  Product Hunt: {len(companies)} companies")
    return companies


# ═════════════════════════════════════════════
# SOURCE 4 — INDIE HACKERS (free, no auth)
# Bootstrapped founders — direct contact info milti hai
# ═════════════════════════════════════════════

def _run_indie_hackers(prefs: dict = None) -> list:
    """
    Indie Hackers products page scrape karo.
    Bootstrapped founders milte hain — great for cold outreach.
    No auth needed.
    """
    companies = []

    try:
        res = req.get(
            "https://www.indiehackers.com/products",
            headers=HEADERS,
            timeout=15,
        )
        if res.status_code != 200:
            logger.warning(f"  Indie Hackers status: {res.status_code}")
            return []

        soup  = BeautifulSoup(res.text, "html.parser")

        # Product cards dhundho
        cards = soup.find_all("a", href=re.compile(r"/product/"))

        seen = set()
        for card in cards[:20]:
            try:
                href = card.get("href", "")
                if not href or href in seen:
                    continue
                seen.add(href)

                # Product name
                name_el = card.find(
                    ["h2", "h3", "span"],
                    class_=re.compile(r"title|name|product", re.I)
                )
                name = name_el.get_text(strip=True) if name_el else ""

                # Tagline
                desc_el = card.find(
                    ["p", "span"],
                    class_=re.compile(r"tagline|desc|pitch", re.I)
                )
                desc = desc_el.get_text(strip=True) if desc_el else ""

                if not name:
                    continue

                # Product page fetch — website + founder
                product_url = f"https://www.indiehackers.com{href}"
                website, founder_name = _fetch_ih_product_page(product_url)

                if not website:
                    clean   = name.lower().replace(" ", "")
                    website = f"https://{clean}.com"

                contacts = []
                if founder_name and website:
                    domain = get_domain(website)
                    email  = find_best_email(founder_name, domain)
                    if email.get("email"):
                        contacts.append({
                            "name"    : founder_name,
                            "role"    : "Founder",
                            "email"   : email["email"],
                            "verified": email["verified"],
                        })

                companies.append({
                    "name"       : name,
                    "website"    : website,
                    "one_liner"  : desc,
                    "description": desc,
                    "funding"    : "Bootstrapped",
                    "team_size"  : "1-5",
                    "location"   : "Remote",
                    "source"     : "indie_hackers",
                    "contacts"   : contacts,
                })

            except Exception:
                continue

    except Exception as e:
        logger.error(f"  Indie Hackers error: {e}")

    logger.info(f"  Indie Hackers: {len(companies)} companies")
    return companies


def _fetch_ih_product_page(url: str) -> tuple:
    """Product page se website + founder name nikalo."""
    try:
        res = req.get(url, headers=HEADERS, timeout=8)
        if res.status_code != 200:
            return "", ""

        soup = BeautifulSoup(res.text, "html.parser")

        # Website link
        website = ""
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("http") and "indiehackers" not in href:
                website = href
                break

        # Founder name
        founder = ""
        founder_el = soup.find(
            ["a", "span"],
            class_=re.compile(r"founder|maker|author", re.I)
        )
        if founder_el:
            founder = founder_el.get_text(strip=True)

        return website, founder

    except Exception:
        return "", ""


# ═════════════════════════════════════════════
# SOURCE 5 — GITHUB TRENDING (free, no auth)
# Tech companies jo actively build kar rahe hain
# ═════════════════════════════════════════════

def _run_github_trending(prefs: dict = None) -> list:
    """
    GitHub trending repositories — tech stack automatically pata chalta hai.
    Company/org repos dhundho — founders ke profiles milte hain.
    No auth needed (public API).
    """
    companies = []

    # GitHub Search API — recently active, popular repos
    queries = [
        "topic:saas pushed:>2024-01-01",
        "topic:ai-tools pushed:>2024-01-01",
        "topic:developer-tools pushed:>2024-01-01",
    ]

    seen_orgs = set()

    for query in queries:
        try:
            res = req.get(
                "https://api.github.com/search/repositories",
                params={
                    "q"       : query,
                    "sort"    : "stars",
                    "order"   : "desc",
                    "per_page": 10,
                },
                headers={**HEADERS, "Accept": "application/vnd.github+json"},
                timeout=10,
            )

            if res.status_code == 403:
                logger.warning("  GitHub rate limit — skipping")
                break

            items = res.json().get("items", [])

            for item in items:
                owner = item.get("owner", {})
                org   = owner.get("login", "")
                otype = owner.get("type",  "")

                # Only organizations — individual repos skip
                if otype != "Organization" or org in seen_orgs:
                    continue
                seen_orgs.add(org)

                name        = item.get("name",            "")
                desc        = item.get("description",     "") or ""
                lang        = item.get("language",        "") or ""
                topics      = item.get("topics",          [])
                homepage    = item.get("homepage",        "") or ""
                stars       = item.get("stargazers_count", 0)
                html_url    = item.get("html_url",        "")

                # Company name = org name (cleaner)
                company_name = org.replace("-", " ").replace("_", " ").title()

                website = homepage if homepage.startswith("http") else f"https://github.com/{org}"

                tech_stack = [lang] if lang else []
                tech_stack += [t for t in topics[:4] if t not in tech_stack]

                # Org ke founders/members dhundho
                contacts = _get_github_org_contacts(org, website)

                companies.append({
                    "name"       : company_name,
                    "website"    : website,
                    "one_liner"  : desc[:150],
                    "description": desc[:500],
                    "funding"    : "Open Source / Startup",
                    "team_size"  : "Unknown",
                    "location"   : "Remote",
                    "source"     : "github_trending",
                    "tech_stack" : tech_stack,
                    "contacts"   : contacts,
                    "github_stars": stars,
                    "github_url" : html_url,
                })

            time.sleep(1)  # GitHub rate limit se bachao

        except Exception as e:
            logger.error(f"  GitHub trending error ({query}): {e}")
            continue

    logger.info(f"  GitHub Trending: {len(companies)} companies")
    return companies


def _get_github_org_contacts(org: str, website: str) -> list:
    """GitHub org ke public members se contacts nikalo."""
    contacts = []
    try:
        res = req.get(
            f"https://api.github.com/orgs/{org}/members",
            params  = {"per_page": 5},
            headers = {**HEADERS, "Accept": "application/vnd.github+json"},
            timeout = 8,
        )
        if res.status_code != 200:
            return []

        members = res.json()
        domain  = get_domain(website) if website else f"{org}.com"

        for member in members[:3]:
            username = member.get("login", "")
            if not username:
                continue

            # Public profile se name fetch karo
            profile_res = req.get(
                f"https://api.github.com/users/{username}",
                headers=HEADERS,
                timeout=5,
            )
            if profile_res.status_code != 200:
                continue

            profile = profile_res.json()
            name    = profile.get("name", "") or username
            email   = profile.get("email", "")

            if not email:
                result = find_best_email(name, domain)
                email  = result.get("email", "")

            if email:
                contacts.append({
                    "name"    : name,
                    "role"    : "Engineer / Founder",
                    "email"   : email,
                    "verified": bool(profile.get("email")),
                    "github"  : f"https://github.com/{username}",
                })

    except Exception as e:
        logger.warning(f"  GitHub org contacts error ({org}): {e}")

    return contacts


# ═════════════════════════════════════════════
# SOURCE 6 — HACKER NEWS "WHO IS HIRING" (free)
# Monthly thread — active companies hiring right now
# ═════════════════════════════════════════════

def _run_hn_hiring(prefs: dict = None) -> list:
    """
    HN 'Who is Hiring' monthly thread se companies nikalo.
    Direct hiring posts — company name + sometimes website.
    No auth needed.
    """
    companies = []

    try:
        # Latest "Ask HN: Who is hiring?" thread dhundho
        search_res = req.get(
            "https://hn.algolia.com/api/v1/search",
            params={
                "query"      : "Ask HN: Who is hiring?",
                "tags"       : "story",
                "hitsPerPage": 5,
            },
            timeout=10,
        )
        hits = search_res.json().get("hits", [])

        if not hits:
            logger.warning("  HN: No hiring thread found")
            return []

        # Sabse latest thread
        thread_id = hits[0].get("objectID", "")
        if not thread_id:
            return []

        logger.info(f"  HN Hiring thread: {thread_id}")

        # Thread ke comments fetch karo
        comments_res = req.get(
            "https://hn.algolia.com/api/v1/items/" + thread_id,
            timeout=10,
        )
        thread = comments_res.json()
        children = thread.get("children", [])

        seen_names = set()

        for comment in children[:50]:
            try:
                text = comment.get("text", "") or ""
                if not text or len(text) < 30:
                    continue

                # HTML tags hata do
                text_clean = BeautifulSoup(text, "html.parser").get_text()

                # Company name — pehli line mein hoti hai usually
                lines = [l.strip() for l in text_clean.split("\n") if l.strip()]
                if not lines:
                    continue

                first_line = lines[0]

                # "CompanyName | Role | Location" format common hai
                parts = re.split(r'\|', first_line)
                company_name = parts[0].strip() if parts else first_line[:60]

                # Skip agar name duplicate ya too generic
                if not company_name or company_name.lower() in seen_names:
                    continue
                if len(company_name) > 80 or len(company_name) < 2:
                    continue
                seen_names.add(company_name.lower())

                # Website dhundho text mein
                urls    = re.findall(r'https?://[^\s\)\]>\"]+', text_clean)
                website = ""
                for u in urls:
                    if not any(skip in u for skip in ["linkedin", "glassdoor", "lever", "greenhouse", "ycombinator"]):
                        website = u.rstrip(".,")
                        break

                if not website:
                    clean   = company_name.lower().replace(" ", "")
                    clean   = re.sub(r'[^a-z0-9]', '', clean)
                    website = f"https://{clean}.com" if clean else ""

                # Email dhundho text mein
                emails_found = re.findall(EMAIL_RE, text_clean)
                contacts     = []
                for em in emails_found[:2]:
                    if not any(s in em.lower() for s in SKIP):
                        contacts.append({
                            "name"    : "Hiring Contact",
                            "role"    : "HR / Recruiter",
                            "email"   : em,
                            "verified": True,
                        })

                # Short description — lines join karo
                desc = " ".join(lines[1:4])[:400] if len(lines) > 1 else first_line

                # Remote/location check
                location = "Remote"
                if "onsite" in text_clean.lower() or "on-site" in text_clean.lower():
                    location = "On-site"
                elif "hybrid" in text_clean.lower():
                    location = "Hybrid"

                companies.append({
                    "name"       : company_name,
                    "website"    : website,
                    "one_liner"  : desc[:150],
                    "description": desc,
                    "funding"    : "Unknown",
                    "team_size"  : "Unknown",
                    "location"   : location,
                    "source"     : "hn_hiring",
                    "contacts"   : contacts,
                })

            except Exception:
                continue

    except Exception as e:
        logger.error(f"  HN Hiring error: {e}")

    logger.info(f"  HN Hiring: {len(companies)} companies")
    return companies


# ═════════════════════════════════════════════
# RUNNER WRAPPERS
# ═════════════════════════════════════════════

def _run_yc(prefs: dict) -> list:
    return list(stream_yc_companies(prefs))

def stream_betalist(prefs: dict) -> Generator:
    yield from _run_betalist(prefs)


# ═════════════════════════════════════════════
# AGENT — PARALLEL SCRAPING + FALLBACK
# ═════════════════════════════════════════════

def scraper_agent(prefs: dict) -> list:
    """
    6 sources parallel chalao.
    Koi fail hua → skip, baaki chalte rahen.

    AGENT logic:
    - Sab sources parallel run karo
    - Agar < 10 companies mile → cached feed se fallback
    - Har source independently fail ho sakta hai

    Sources (all free):
    1. YC API          — structured, best quality
    2. Betalist        — pre-launch startups
    3. Product Hunt    — developer tools (token chahiye)
    4. Indie Hackers   — bootstrapped founders
    5. GitHub Trending — active tech orgs
    6. HN Hiring       — currently hiring companies
    """
    companies = []

    scrapers = [
        ("yc",            _run_yc,            prefs),
        ("betalist",      _run_betalist,      prefs),
        ("product_hunt",  _run_product_hunt,  prefs),
        ("indie_hackers", _run_indie_hackers, prefs),
        ("github",        _run_github_trending, prefs),
        ("hn_hiring",     _run_hn_hiring,     prefs),
    ]

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(fn, p): name for name, fn, p in scrapers}
        for future in as_completed(futures):
            source = futures[future]
            try:
                result = future.result()
                companies.extend(result)
                logger.info(f"  ✅ {source}: {len(result)} companies")
            except Exception as e:
                logger.error(f"  ❌ {source} failed: {e}")

    # AGENT fallback — kam companies mile toh cache use karo
    if len(companies) < 10:
        logger.warning(
            f"  ⚠️ Only {len(companies)} companies scraped — "
            f"falling back to cached feed"
        )
        try:
            from backend.agents.feed_agent import get_feed
            cached = get_feed(limit=50).get("companies", [])
            # Cached mein jo already hai woh add mat karo
            existing_names = {c.get("name", "").lower() for c in companies}
            for c in cached:
                if c.get("name", "").lower() not in existing_names:
                    companies.append(c)
            logger.info(f"  📦 After cache fallback: {len(companies)} companies")
        except Exception as e:
            logger.error(f"  Cache fallback error: {e}")

    return companies


# Backward compatibility — purana naam bhi kaam kare
def scrape_track_b(prefs: dict) -> list:
    return scraper_agent(prefs)


def run(user_id: int, prefs: dict) -> dict:
    logger.info(f"🚀 Scraper Agent starting — user {user_id}")
    logger.info(f"   Domains: {prefs.get('domains')}")
    logger.info(f"   Roles  : {prefs.get('target_roles')}")
    companies = scraper_agent(prefs)
    logger.info(f"   Total  : {len(companies)} companies")
    return {"track_b": companies, "total_companies": len(companies)}


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