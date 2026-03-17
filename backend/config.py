# backend/config.py
# Sirf environment variables — koi hardcoding nahi
# Har user ka data DB mein hoga, yahan nahi

import os
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# Database
# ─────────────────────────────────────────────

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///data/jobs.db"
)
# Locally SQLite — zero setup
# Production pe sirf ye line .env mein change karo:
# DATABASE_URL=postgresql://user:pass@host:5432/dbname
# Baaki koi code nahi badlega — SQLAlchemy handle karta hai

# ─────────────────────────────────────────────
# LLM — Groq (Free Tier)
# console.groq.com pe signup karo
# 14,400 requests/day free
# ─────────────────────────────────────────────

GROQ_API_KEY  = os.getenv("GROQ_API_KEY")
LLM_MODEL     = "llama3-8b-8192"
# llama3-8b-8192 kyun?
# → Fast hai
# → Free quota zyada milti hai vs 70b
# → Email generation ke liye kaafi smart hai
# → 70b tab use karo jab quality bahut
#   important ho aur quota concern na ho

LLM_MAX_TOKENS  = 1024
LLM_TEMPERATURE = 0.7
# Temperature 0.7 kyun?
# 0.0 = deterministic, boring, repetitive
# 1.0 = creative but inconsistent
# 0.7 = balance — emails varied but sensible
# Research/scoring ke liye 0.1 use karte hain
# (wahan consistency chahiye)

# ─────────────────────────────────────────────
# Auth — JWT
# ─────────────────────────────────────────────

SECRET_KEY       = os.getenv("SECRET_KEY", "change-this-in-production")
ALGORITHM        = "HS256"
TOKEN_EXPIRE_MIN = 60 * 24   # 24 hours
# SECRET_KEY strong hona chahiye production mein
# Generate karo: python -c "import secrets; print(secrets.token_hex(32))"

# ─────────────────────────────────────────────
# Search — Company Research Ke Liye
# ─────────────────────────────────────────────

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
# tavily.com — 1000 free searches/month
# DuckDuckGo fallback hai agar ye nahi hai
# duckduckgo-search library — completely free, no key

# ─────────────────────────────────────────────
# Email Finding
# Priority: Website → Pattern+SMTP → Hunter
# ─────────────────────────────────────────────

HUNTER_API_KEY = os.getenv("HUNTER_API_KEY")
# hunter.io — 25 free/month
# Last resort only — pehle website aur SMTP try karo

# ─────────────────────────────────────────────
# Google Sheets — Applications Tracker
# ─────────────────────────────────────────────

GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_JSON",
    "credentials.json"
)
# console.cloud.google.com pe:
# → New Project banao
# → Sheets API + Drive API enable karo
# → Service Account banao
# → JSON key download karo
# → credentials.json naam do
# → .gitignore mein add karo

# ─────────────────────────────────────────────
# File Upload Paths
# ─────────────────────────────────────────────

UPLOAD_DIR = "uploads"
# Structure:
# uploads/{user_id}/resume_base.pdf     ← original
# uploads/{user_id}/resumes/            ← per company
#   └── finflow_ai_resume.pdf

# ─────────────────────────────────────────────
# Scraper Settings
# ─────────────────────────────────────────────

SCRAPER_DELAY_MIN = 2   # seconds
SCRAPER_DELAY_MAX = 5   # seconds
# Random delay between requests
# Fixed delay = bot pattern detect hota hai
# Random = human-like behaviour

SCRAPER_SOURCES = {
    "internshala" : True,
    "yc_jobs"     : True,
    "wellfound"   : True,
    "unstop"      : True,
    "yc_companies": True,
}

# ─────────────────────────────────────────────
# Scoring Thresholds
# ─────────────────────────────────────────────

MIN_FIT_SCORE    = 50
# Jobs below this score filtered out
# User apni profile settings mein override kar sakta hai

TARGET_ATS_SCORE = 70
# Resume rewrite ka goal
# Agar ATS score 70% se kam hai toh rewrite karo

# ─────────────────────────────────────────────
# Contact Priority
# Kis role ko pehle email karein
# Lower = higher priority
# ─────────────────────────────────────────────

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
# Founder first kyun?
# Early stage startups mein founder hi
# hiring decision leta hai.
# HR exist hi nahi karta mostly.
# Direct founder email = highest response rate.

# ─────────────────────────────────────────────
# Email + Follow-up Settings
# Default values — user profile mein override hoga
# ─────────────────────────────────────────────

FOLLOWUP_AFTER_DAYS  = 4
MAX_FOLLOWUPS        = 2
REPLY_CHECK_INTERVAL = 6   # hours

# ─────────────────────────────────────────────
# Sanity Check
# python backend/config.py se run karo
# Setup verify karne ke liye
# ─────────────────────────────────────────────

def verify_config():
    issues   = []
    warnings = []

    # Critical — bina inke kaam nahi chalega
    if not GROQ_API_KEY:
        issues.append(
            "❌ GROQ_API_KEY missing "
            "— console.groq.com se lo (free)"
        )
    if not os.path.exists("data"):
        issues.append(
            "❌ data/ folder missing "
            "— mkdir data karo"
        )
    if SECRET_KEY == "change-this-in-production":
        warnings.append(
            "⚠️  SECRET_KEY default hai "
            "— production mein zaroor change karo"
        )

    # Optional — warnings only
    if not TAVILY_API_KEY:
        warnings.append(
            "⚠️  TAVILY_API_KEY missing "
            "— DuckDuckGo fallback use hoga"
        )
    if not HUNTER_API_KEY:
        warnings.append(
            "⚠️  HUNTER_API_KEY missing "
            "— email finding limited hogi"
        )
    if not os.path.exists(GOOGLE_SERVICE_ACCOUNT_JSON):
        warnings.append(
            "⚠️  credentials.json missing "
            "— Google Sheets sync kaam nahi karega"
        )

    # Results print karo
    if issues:
        print("\n🚨 Critical Issues (fix karo pehle):")
        for i in issues:
            print(f"   {i}")

    if warnings:
        print("\n⚠️  Warnings (optional but recommended):")
        for w in warnings:
            print(f"   {w}")

    if not issues:
        print("\n✅ Config verified — sab critical settings theek hain")
        return True

    return False


if __name__ == "__main__":
    verify_config()