# backend/config.py

import os
from dotenv import load_dotenv

load_dotenv()

# ── Database ──────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/jobs.db")

# ── LLM ───────────────────────────────────────
GROQ_API_KEY    = os.getenv("GROQ_API_KEY")
LLM_MODEL       = "llama-3.1-8b-instant"  # ← fixed
LLM_MAX_TOKENS  = 1024
LLM_TEMPERATURE = 0.7

# ── Auth ──────────────────────────────────────
SECRET_KEY       = os.getenv("SECRET_KEY", "change-in-production")
ALGORITHM        = "HS256"
TOKEN_EXPIRE_MIN = 60 * 24

# ── Search ────────────────────────────────────
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

# ── Email Finding ─────────────────────────────
HUNTER_API_KEY = os.getenv("HUNTER_API_KEY")
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY")
SNOV_API_KEY   = os.getenv("SNOV_API_KEY")
SKRAPP_API_KEY = os.getenv("SKRAPP_API_KEY")
GITHUB_TOKEN   = os.getenv("GITHUB_TOKEN")

# ── Startup Sources ───────────────────────────
PRODUCT_HUNT_TOKEN = os.getenv("PRODUCT_HUNT_TOKEN")

# ── Upload Paths ──────────────────────────────
UPLOAD_DIR = "uploads"

# ── Scraper Settings ──────────────────────────
SCRAPER_DELAY_MIN = 2
SCRAPER_DELAY_MAX = 5

SCRAPER_SOURCES = {
    # Track A — Job Listings
    "internshala"    : True,
    "yc_jobs"        : True,
    "unstop"         : True,
    "remotive"       : True,
    "the_muse"       : True,
    "wellfound"      : False,   # threading issue

    # Track B — Cold Outreach
    "yc_companies"   : True,
    "hn_hiring"      : True,
    "product_hunt"   : True,
    "github_trending": True,
    "betalist"       : True,
    "indie_hackers"  : True,
    "google_news"    : True,
    "devto"          : True,
    "reddit"         : True,
    "f6s"            : True,
}

# ── Scoring ───────────────────────────────────
MIN_FIT_SCORE    = 50
TARGET_ATS_SCORE = 70

# ── Contact Priority ──────────────────────────
CONTACT_PRIORITY = {
    "founder"            : 1,
    "co-founder"         : 1,
    "ceo"                : 2,
    "cto"                : 3,
    "vp engineering"     : 4,
    "engineering manager": 5,
    "hr"                 : 6,
    "recruiter"          : 7
}

# ── Email Settings ────────────────────────────
FOLLOWUP_AFTER_DAYS  = 4
MAX_FOLLOWUPS        = 2
REPLY_CHECK_INTERVAL = 6

# ── Google Sheets ─────────────────────────────
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_JSON", "credentials.json"
)


def verify_config():
    issues   = []
    warnings = []

    if not GROQ_API_KEY:
        issues.append("❌ GROQ_API_KEY missing")
    if not os.path.exists("data"):
        issues.append("❌ data/ folder missing")
    if SECRET_KEY == "change-in-production":
        warnings.append("⚠️ SECRET_KEY default hai")
    if not TAVILY_API_KEY:
        warnings.append("⚠️ TAVILY_API_KEY missing — DDG fallback")
    if not HUNTER_API_KEY:
        warnings.append("⚠️ HUNTER_API_KEY missing")
    if not PRODUCT_HUNT_TOKEN:
        warnings.append("⚠️ PRODUCT_HUNT_TOKEN missing")

    if issues:
        print("\n🚨 Critical Issues:")
        for i in issues:
            print(f"   {i}")
    if warnings:
        print("\n⚠️  Warnings:")
        for w in warnings:
            print(f"   {w}")
    if not issues:
        print("\n✅ Config OK")
        return True
    return False


if __name__ == "__main__":
    verify_config()