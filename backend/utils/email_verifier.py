# backend/utils/email_verifier.py
# Email dhundho aur verify karo
#
# Priority order:
# 1. Website scraping     → free, unlimited
# 2. Pattern generation   → free, unlimited
# 3. SMTP verification    → free, unlimited
# 4. Hunter.io            → 25/month, last resort

import re
import smtplib
import dns.resolver
import requests as req
from bs4 import BeautifulSoup
from backend.config import HUNTER_API_KEY
from loguru import logger

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    )
}

EMAIL_PATTERN = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'


# ─────────────────────────────────────────────
# METHOD 1 — Website Scraping
# ─────────────────────────────────────────────

def find_emails_on_website(domain: str) -> list:
    """
    Company website pe directly emails dhundho.
    /contact aur /team pages best hain.
    mailto: links bhi check karo.
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
            res  = req.get(url, headers=HEADERS, timeout=8)
            soup = BeautifulSoup(res.text, "html.parser")

            # Method A — regex on raw HTML
            raw_emails = re.findall(EMAIL_PATTERN, res.text)
            found.extend(raw_emails)

            # Method B — mailto links
            for link in soup.select('a[href^="mailto:"]'):
                email = link["href"].replace("mailto:", "").strip()
                if "@" in email:
                    found.append(email)

        except Exception:
            continue

    # Sirf company domain emails rakho
    company_emails = [
        e for e in set(found)
        if domain in e
        and "example" not in e
        and "noreply" not in e
        and "support" not in e
    ]

    return company_emails


# ─────────────────────────────────────────────
# METHOD 2 — Pattern Generation
# ─────────────────────────────────────────────

def generate_email_patterns(full_name: str, domain: str) -> list:
    """
    Naam aur domain se possible emails banao.
    
    Why itne patterns?
    Startups consistent nahi hote.
    Pattern check karna fast hai.
    SMTP se best match verify kar lete hain.
    """
    parts = full_name.lower().strip().split()
    if len(parts) == 0:
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
            f"{first}_{last}@{domain}",
            f"{last}.{first}@{domain}",
            f"{last}@{domain}",
        ]

    return patterns


# ─────────────────────────────────────────────
# METHOD 3 — SMTP Verification
# ─────────────────────────────────────────────

def smtp_verify(email: str) -> bool:
    """
    Mail server se puchho — email exist karta hai?
    
    How it works:
    1. Domain ka MX record dhundho
       (MX = mail server address)
    2. Us server se SMTP connect karo
    3. RCPT TO command bhejo
       (email deliver karne ki request)
    4. 250 = exists, 550 = not found
    
    Why safe hai?
    Email actually nahi bhejte —
    sirf "deliver kar sakte ho?" puchte hain.
    
    Limitation:
    Kuch servers catch-all hote hain —
    koi bhi email accept kar lete hain.
    Toh True return ho sakta hai
    even if email doesn't exist.
    """
    try:
        domain     = email.split("@")[1]
        mx_records = dns.resolver.resolve(domain, "MX")
        mx_host    = str(mx_records[0].exchange).rstrip(".")

        with smtplib.SMTP(timeout=10) as smtp:
            smtp.connect(mx_host, 25)
            smtp.helo("verify.com")
            smtp.mail("verify@verify.com")
            code, _ = smtp.rcpt(email)
            return code == 250

    except Exception:
        return False


# ─────────────────────────────────────────────
# METHOD 4 — Hunter.io (Last Resort)
# ─────────────────────────────────────────────

def hunter_lookup(domain: str) -> list:
    """
    Hunter.io se domain ke emails lo.
    25 free/month — sirf last resort.
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
        data    = res.json()
        emails_data = data.get("data", {}).get("emails", [])

        return [
            {
                "email"     : e.get("value"),
                "first_name": e.get("first_name", ""),
                "last_name" : e.get("last_name", ""),
                "role"      : e.get("position", ""),
                "confidence": e.get("confidence", 0)
            }
            for e in emails_data
            if e.get("value")
        ]

    except Exception as e:
        logger.error(f"Hunter error: {e}")
        return []


# ─────────────────────────────────────────────
# MAIN — Find Best Email
# ─────────────────────────────────────────────

def find_best_email(
    full_name : str,
    domain    : str
) -> dict:
    """
    Sab methods try karo priority order mein.
    Best verified email return karo.
    """
    domain = domain.replace("https://", "")\
                   .replace("http://", "")\
                   .rstrip("/").split("/")[0]

    logger.info(f"  📧 Finding email: {full_name} @ {domain}")

    # Method 1 — Website scraping
    site_emails = find_emails_on_website(domain)
    if site_emails:
        logger.info(f"    ✅ Found on website: {site_emails[0]}")
        return {
            "email"     : site_emails[0],
            "source"    : "website",
            "confidence": 0.9,
            "verified"  : True
        }

    # Method 2 + 3 — Pattern + SMTP verify
    if full_name:
        patterns = generate_email_patterns(full_name, domain)
        for email in patterns:
            if smtp_verify(email):
                logger.info(f"    ✅ SMTP verified: {email}")
                return {
                    "email"     : email,
                    "source"    : "smtp_verify",
                    "confidence": 0.95,
                    "verified"  : True
                }

        # SMTP fail hua — best guess do
        if patterns:
            logger.info(f"    ⚠️ Best guess: {patterns[0]}")
            return {
                "email"     : patterns[0],
                "source"    : "pattern_guess",
                "confidence": 0.5,
                "verified"  : False
            }

    # Method 4 — Hunter last resort
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

    return {
        "email"     : None,
        "source"    : "not_found",
        "confidence": 0,
        "verified"  : False
    }