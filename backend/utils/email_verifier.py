# backend/utils/email_verifier.py
# Email dhundho aur verify karo
#
# Priority order:
# 1. Website scraping  → free, unlimited, fastest
# 2. Hunter.io         → 25 free/month, last resort
# 3. Pattern guess     → always works, verified=False
#
# SMTP deliberately removed:
# - Port 25 mostly blocked by ISPs / cloud hosts
# - Catch-all servers hamesha 250 return karte hain
#   even for non-existent addresses — false positives
# - 3-10s per check × 300 companies = pipeline hang
# - Net gain zero — pattern guess utna hi useful hai
#
# Caller: contact_finder.py (pipeline, on user selection)
# NOT called from scraper_agent — wahan sirf fast pattern.

import re
import requests as req
from bs4    import BeautifulSoup
from loguru import logger

from backend.config import HUNTER_API_KEY

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    )
}

EMAIL_PATTERN = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'

SKIP = [
    "noreply", "no-reply", "support", "example",
    "test", "spam", "info", "privacy", "legal", "abuse"
]


# ─────────────────────────────────────────────
# METHOD 1 — Website Scraping
# ─────────────────────────────────────────────

def find_emails_on_website(domain: str) -> list:
    """
    Company website pe directly emails dhundho.
    /contact aur /team pages best hain.
    mailto: links bhi check karo.
    Returns list of email strings, deduped.
    """
    pages = [
        f"https://{domain}",
        f"https://{domain}/contact",
        f"https://{domain}/about",
        f"https://{domain}/team",
        f"https://{domain}/contact-us",
    ]

    found = []

    for url in pages:
        try:
            res = req.get(url, headers=HEADERS, timeout=6)
            if res.status_code != 200:
                continue
            soup = BeautifulSoup(res.text, "html.parser")

            # Method A — regex on raw HTML
            for email in re.findall(EMAIL_PATTERN, res.text):
                if (
                    domain in email
                    and not any(s in email.lower() for s in SKIP)
                ):
                    found.append(email)

            # Method B — mailto links
            for link in soup.select('a[href^="mailto:"]'):
                email = (
                    link["href"]
                    .replace("mailto:", "")
                    .strip()
                    .split("?")[0]
                )
                if "@" in email and not any(
                    s in email.lower() for s in SKIP
                ):
                    found.append(email)

        except Exception:
            continue

    # Deduplicate, preserve order
    seen, unique = set(), []
    for e in found:
        if e not in seen:
            seen.add(e)
            unique.append(e)

    return unique


# ─────────────────────────────────────────────
# METHOD 2 — Hunter.io (25 free / month)
# ─────────────────────────────────────────────

def hunter_lookup(domain: str) -> list:
    """
    Hunter.io se domain ke emails lo.
    Returns list of dicts with email + metadata.
    Only called when website scrape fails.
    25 free searches/month — conserve karo.
    """
    if not HUNTER_API_KEY:
        return []

    try:
        res = req.get(
            "https://api.hunter.io/v2/domain-search",
            params={
                "domain" : domain,
                "api_key": HUNTER_API_KEY
            },
            timeout=10
        )
        data        = res.json()
        emails_data = data.get("data", {}).get("emails", [])

        return [
            {
                "email"     : e.get("value"),
                "first_name": e.get("first_name", ""),
                "last_name" : e.get("last_name",  ""),
                "role"      : e.get("position",   ""),
                "confidence": e.get("confidence", 0)
            }
            for e in emails_data
            if e.get("value")
        ]

    except Exception as e:
        logger.error(f"Hunter error: {e}")
        return []


# ─────────────────────────────────────────────
# METHOD 3 — Pattern Generation (Fallback)
# ─────────────────────────────────────────────

def generate_email_patterns(full_name: str, domain: str) -> list:
    """
    Naam aur domain se possible emails banao.
    Most common startup patterns pehle.
    No verification — caller decides what to do with these.
    """
    parts = full_name.lower().strip().split()
    if not parts:
        return []

    first = parts[0]
    last  = parts[-1] if len(parts) > 1 else ""

    patterns = [f"{first}@{domain}"]

    if last and last != first:
        patterns += [
            f"{first}.{last}@{domain}",
            f"{first}{last}@{domain}",
            f"{first[0]}.{last}@{domain}",
            f"{first[0]}{last}@{domain}",
            f"{first}_{last}@{domain}",
            f"{last}.{first}@{domain}",
            f"{last}@{domain}",
        ]

    return patterns


# ─────────────────────────────────────────────
# MAIN — Find Best Email
# ─────────────────────────────────────────────

def find_best_email(
    full_name: str,
    domain   : str
) -> dict:
    """
    Priority:
    1. Website scrape  → verified=True,  source="website"
    2. Hunter.io       → verified=True,  source="hunter"
    3. Pattern guess   → verified=False, source="pattern"

    Called by contact_finder.py AFTER user selects companies.
    NOT called during bulk scraping — too slow at scale.
    """
    domain = (
        domain.replace("https://", "")
               .replace("http://", "")
               .rstrip("/")
               .split("/")[0]
    )

    logger.info(f"  📧 Finding email: {full_name} @ {domain}")

    # ── 1. Website scraping ───────────────────
    site_emails = find_emails_on_website(domain)
    if site_emails:
        logger.info(f"    ✅ Found on website: {site_emails[0]}")
        return {
            "email"     : site_emails[0],
            "source"    : "website",
            "confidence": 0.9,
            "verified"  : True
        }

    # ── 2. Hunter (25 free/month — last resort) ──
    hunter_results = hunter_lookup(domain)
    if hunter_results:
        best = hunter_results[0]
        logger.info(f"    ✅ Hunter: {best['email']}")
        return {
            "email"     : best["email"],
            "source"    : "hunter",
            "confidence": best["confidence"] / 100,
            "verified"  : True
        }

    # ── 3. Pattern guess ─────────────────────
    if full_name:
        patterns = generate_email_patterns(full_name, domain)
        if patterns:
            logger.info(f"    ⚠️  Pattern guess: {patterns[0]}")
            return {
                "email"     : patterns[0],
                "source"    : "pattern",
                "confidence": 0.4,
                "verified"  : False
            }

    logger.warning(f"    ❌ No email found for {full_name} @ {domain}")
    return {
        "email"     : None,
        "source"    : "not_found",
        "confidence": 0.0,
        "verified"  : False
    }