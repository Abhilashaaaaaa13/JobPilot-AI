# backend/agents/contact_finder_enhanced.py
# ═══════════════════════════════════════════════════════════════════════════════
# ENHANCED CONTACT FINDER
# Better email detection, verification, and fallback strategies
# ═══════════════════════════════════════════════════════════════════════════════

import json
import re
import requests as req
from bs4 import BeautifulSoup
from groq import Groq
from duckduckgo_search import DDGS
from loguru import logger
from typing import List, Dict, Tuple

from backend.config import GROQ_API_KEY, LLM_MODEL

client = Groq(api_key=GROQ_API_KEY)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    )
}

EMAIL_REGEX = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
SKIP_EMAILS = {
    "noreply", "no-reply", "support", "example", "test", "spam",
    "info", "privacy", "legal", "abuse", "feedback", "hello",
    "contact", "general", "sales", "admin"
}


# ═════════════════════════════════════════════════════════════════════════════
# STEP 1: COMPREHENSIVE WEBSITE SCRAPING
# ═════════════════════════════════════════════════════════════════════════════

def scrape_all_pages(website: str, max_pages: int = 8) -> str:
    """
    Scrape multiple pages from website.
    Priority: /about → /team → /contact → /blog → /press → /investors
    """
    if not website or not website.startswith("http"):
        return ""
    
    base_url = website.rstrip("/")
    pages_to_scrape = [
        "",  # root
        "/about",
        "/about-us",
        "/team",
        "/contact",
        "/contact-us",
        "/leadership",
        "/founders",
        "/investors",
        "/press",
        "/news",
        "/blog",
    ]
    
    all_text = ""
    success_count = 0
    
    for page_path in pages_to_scrape[:max_pages]:
        if success_count >= 3:  # Got enough content
            break
        
        url = base_url + page_path
        try:
            res = req.get(url, headers=HEADERS, timeout=8)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                
                # Remove script/style tags
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                
                text = soup.get_text(separator=" ", strip=True)
                all_text += text[:2000] + "\n"
                success_count += 1
                logger.debug(f"  ✓ Scraped {page_path} ({len(text)} chars)")
        
        except Exception as e:
            logger.debug(f"  ✗ Failed {page_path}: {e}")
            continue
    
    return all_text[:5000]


# ═════════════════════════════════════════════════════════════════════════════
# STEP 2: EMAIL EXTRACTION FROM PAGES
# ═════════════════════════════════════════════════════════════════════════════

def extract_emails_from_text(text: str, domain: str) -> List[Dict]:
    """
    Extract and validate emails from scraped text.
    Returns list of {email, context, verified}
    """
    if not text:
        return []
    
    emails_found = re.findall(EMAIL_REGEX, text)
    domain_clean = domain.lower().replace("www.", "")
    
    validated = []
    seen = set()
    
    for email in emails_found:
        email_lower = email.lower()
        
        # Skip already seen
        if email_lower in seen:
            continue
        seen.add(email_lower)
        
        # Skip generic/spam emails
        local_part = email.split("@")[0].lower()
        if any(skip in local_part for skip in SKIP_EMAILS):
            continue
        
        # Check if email domain matches company domain
        email_domain = email.split("@")[1].lower()
        is_company_email = domain_clean in email_domain
        
        validated.append({
            "email": email,
            "is_company_email": is_company_email,
            "verified": True,  # Found on website
            "source": "website"
        })
    
    return validated[:10]


# ═════════════════════════════════════════════════════════════════════════════
# STEP 3: EXTRACT PEOPLE WITH ROLES (Groq)
# ═════════════════════════════════════════════════════════════════════════════

def extract_people_from_website(
    company_name: str,
    website_text: str,
    description: str
) -> List[Dict]:
    """
    Use Groq to intelligently extract people and their roles from website text.
    """
    if not website_text:
        return []
    
    prompt = f"""
Extract all people (names + roles) from this website content.

Company: {company_name}
Description: {description[:200]}

Website Content:
{website_text[:3000]}

Return ONLY valid JSON array, no markdown:
[
  {{
    "name": "First Last",
    "role": "CEO|CTO|Founder|HR Manager|Head of Engineering",
    "context": "where you found them (e.g., 'Team page')"
  }}
]

Rules:
- Include: Founders, CEO, CTO, VP roles, HR, Managers
- Exclude: Team members, junior engineers, marketing
- Only if name is clearly identifiable
- Max 8 people
- If no people found, return []
"""
    
    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.1
        )
        
        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        people = json.loads(raw)
        
        if isinstance(people, list):
            logger.info(f"  ✅ Extracted {len(people)} people from website")
            return people
        return []
    
    except Exception as e:
        logger.error(f"Groq extraction error: {e}")
        return []


# ═════════════════════════════════════════════════════════════════════════════
# STEP 4: EMAIL PATTERN GENERATION (Fallback)
# ═════════════════════════════════════════════════════════════════════════════

def generate_email_patterns(name: str, domain: str) -> List[str]:
    """
    Generate common email patterns for a name.
    Returns list of likely email addresses.
    """
    if not name or not domain:
        return []
    
    parts = name.lower().strip().split()
    first = parts[0] if parts else ""
    last = parts[-1] if len(parts) > 1 else ""
    
    if not first:
        return []
    
    patterns = []
    
    # Single name variants
    patterns.append(f"{first}@{domain}")
    
    # First.Last variants
    if last and last != first:
        patterns.append(f"{first}.{last}@{domain}")
        patterns.append(f"{first}{last}@{domain}")
        patterns.append(f"{last}.{first}@{domain}")
    
    # Initials
    if last:
        patterns.append(f"{first[0]}{last}@{domain}")
        patterns.append(f"{first[0]}.{last}@{domain}")
    
    # Admin/generic
    patterns.append(f"hello@{domain}")
    patterns.append(f"contact@{domain}")
    patterns.append(f"founders@{domain}")
    
    return patterns


# ═════════════════════════════════════════════════════════════════════════════
# STEP 5: VERIFY EMAIL (Optional - if Hunter API available)
# ═════════════════════════════════════════════════════════════════════════════

def verify_email_hunter(name: str, domain: str) -> Dict:
    """
    Try Hunter.io API for email verification (requires API key).
    """
    api_key = __import__("os").getenv("HUNTER_API_KEY", "")
    
    if not api_key:
        return None
    
    try:
        res = req.get(
            "https://api.hunter.io/v2/email-finder",
            params={
                "domain": domain,
                "first_name": name.split()[0] if name else "",
                "last_name": name.split()[-1] if name and len(name.split()) > 1 else "",
            },
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=8
        )
        
        if res.status_code == 200:
            data = res.json()
            email = data.get("data", {}).get("email")
            if email:
                return {
                    "email": email,
                    "verified": True,
                    "source": "hunter"
                }
    except Exception as e:
        logger.debug(f"Hunter API error: {e}")
    
    return None


# ═════════════════════════════════════════════════════════════════════════════
# STEP 6: LINKEDIN FALLBACK SEARCH
# ═════════════════════════════════════════════════════════════════════════════

def search_linkedin_profiles(name: str, company_name: str) -> List[Dict]:
    """
    Search for LinkedIn profiles using DuckDuckGo.
    Extract email if available in search results.
    """
    try:
        with DDGS() as ddgs:
            query = f"{name} {company_name} linkedin.com/in"
            results = list(ddgs.text(query, max_results=3))
            
            profiles = []
            for r in results:
                title = r.get("title", "")
                url = r.get("href", "")
                
                if "linkedin.com/in" in url:
                    profiles.append({
                        "name": name,
                        "linkedin_url": url,
                        "title": title,
                        "source": "linkedin"
                    })
            
            return profiles
    
    except Exception as e:
        logger.debug(f"LinkedIn search error: {e}")
        return []


# ═════════════════════════════════════════════════════════════════════════════
# MAIN: ENHANCED CONTACT FINDER
# ═════════════════════════════════════════════════════════════════════════════

def enhanced_contact_finder(
    company_name: str,
    website: str,
    description: str = ""
) -> Dict:
    """
    ENHANCED CONTACT FINDER with multiple strategies:
    
    1. Scrape website (team, about, contact pages)
    2. Extract emails directly from HTML
    3. Use Groq to find people + roles
    4. Generate email patterns for each person
    5. Verify with Hunter API (if available)
    6. LinkedIn fallback for missing contacts
    
    Returns comprehensive contact list with confidence scores.
    """
    
    logger.info(f"👤 Enhanced Contact Finder: {company_name}")
    
    if not website:
        logger.warning(f"  ⚠️ No website provided")
        return {"company": company_name, "contacts": []}
    
    domain = (
        website.replace("https://", "")
               .replace("http://", "")
               .rstrip("/")
               .split("/")[0]
    )
    
    # ─── PHASE 1: Scrape website ─────────────────
    logger.info(f"  📄 Scraping website...")
    website_text = scrape_all_pages(website)
    
    if not website_text:
        logger.warning(f"  ⚠️ Could not scrape website")
        website_text = description
    
    # ─── PHASE 2: Extract emails directly ───────
    logger.info(f"  📧 Extracting emails...")
    website_emails = extract_emails_from_text(website_text, domain)
    
    # ─── PHASE 3: Extract people + roles ────────
    logger.info(f"  👥 Extracting people...")
    people = extract_people_from_website(company_name, website_text, description)
    
    if not people and website_emails:
        # If Groq couldn't find people but we have emails, use them
        logger.info(f"  ℹ️ Using extracted emails as contacts")
        people = [
            {
                "name": email["email"].split("@")[0].title(),
                "role": "Contact",
            }
            for email in website_emails[:3]
        ]
    
    # ─── PHASE 4: Build contact list ────────────
    contacts = []
    
    for person in people:
        name = person.get("name", "").strip()
        role = person.get("role", "Engineer").strip()
        
        if not name:
            continue
        
        # Try Hunter first
        hunter_email = verify_email_hunter(name, domain)
        if hunter_email:
            contacts.append({
                "name": name,
                "role": role,
                "email": hunter_email["email"],
                "verified": True,
                "source": "hunter",
                "confidence": 0.95,
                "linkedin_url": None,
            })
            logger.info(f"  ✅ {name} ({role}) → {hunter_email['email']} [Hunter]")
            continue
        
        # Generate patterns
        patterns = generate_email_patterns(name, domain)
        
        # Try company emails first
        company_emails = [e for e in website_emails if e.get("is_company_email")]
        
        # Pick best match
        best_email = None
        confidence = 0.5
        
        if company_emails:
            # Prefer emails found on website
            best_email = company_emails[0]["email"]
            confidence = 0.85
        else:
            # Use first pattern
            best_email = patterns[0] if patterns else f"{name.lower()}@{domain}"
            confidence = 0.5
        
        # Try LinkedIn
        linkedin_profiles = search_linkedin_profiles(name, company_name)
        linkedin_url = linkedin_profiles[0]["linkedin_url"] if linkedin_profiles else None
        
        contacts.append({
            "name": name,
            "role": role,
            "email": best_email,
            "verified": confidence >= 0.8,
            "source": "pattern" if confidence < 0.8 else "website",
            "confidence": confidence,
            "linkedin_url": linkedin_url,
        })
        
        logger.info(
            f"  ✅ {name} ({role}) → {best_email} "
            f"[confidence: {confidence:.0%}]"
        )
    
    # Sort by role priority (Founder > CEO > CTO > others)
    role_priority = {
        "founder": 1, "ceo": 2, "cto": 3, "cfo": 4,
        "vp": 5, "head": 5, "manager": 6, "engineer": 7
    }
    
    def get_priority(contact):
        role_lower = contact["role"].lower()
        for key, priority in role_priority.items():
            if key in role_lower:
                return priority
        return 8
    
    contacts.sort(key=lambda c: get_priority(c))
    
    logger.info(f"  ✅ Found {len(contacts)} contacts")
    
    return {
        "company": company_name,
        "website": website,
        "contacts": contacts[:8],  # Top 8 contacts
    }


# Backward compatibility
def find_contacts_enhanced(company_name: str, website: str, description: str = "") -> Dict:
    return enhanced_contact_finder(company_name, website, description)