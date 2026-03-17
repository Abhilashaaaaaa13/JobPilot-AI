# backend/agents/email_generator.py

import os
import json
from groq import Groq
from sqlalchemy.orm import Session
from backend.models.job import Job
from backend.models.company import Company
from backend.models.contact import Contact
from backend.models.user import User, UserProfile
from backend.config import GROQ_API_KEY, LLM_MODEL
from loguru import logger

client = Groq(api_key=GROQ_API_KEY)


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def load_prompt(filename: str) -> str:
    path = os.path.join("backend", "prompts", filename)
    try:
        with open(path, "r") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Prompt load error {filename}: {e}")
        return ""


def get_user_data(db: Session, user_id: int) -> dict:
    """User ka profile data lo."""
    user    = db.query(User).filter(
        User.id == user_id
    ).first()
    profile = db.query(UserProfile).filter(
        UserProfile.user_id == user_id
    ).first()

    if not user or not profile:
        return {}

    def parse(val):
        try:
            return json.loads(val) if val else []
        except:
            return []

    return {
        "name"            : profile.name or user.email,
        "skills"          : parse(profile.skills),
        "experience_years": profile.experience_years or 0,
    }


def get_user_key_project(db: Session, user_id: int) -> str:
    """
    Resume se most impressive project
    ek line mein extract karo.

    Why Groq here?
    Resume mein projects paragraph mein hote hain.
    Groq se best one-liner nikalta hai.
    Ye email mein proof of work ke taur pe use hoga.
    """
    from backend.utils.pdf_parser import extract_text_from_pdf

    profile = db.query(UserProfile).filter(
        UserProfile.user_id == user_id
    ).first()

    if not profile or not profile.resume_path:
        return ""

    if not os.path.exists(profile.resume_path):
        return ""

    from backend.utils.pdf_parser import extract_text_from_pdf
    resume_text = extract_text_from_pdf(profile.resume_path)
    if not resume_text:
        return ""

    try:
        response = client.chat.completions.create(
            model    = LLM_MODEL,
            messages = [{
                "role"   : "user",
                "content": f"""
From this resume extract the single most impressive
technical project in ONE line under 20 words.
Focus on: what was built + technology used + result/impact.

Resume:
{resume_text[:2000]}

Return ONLY the one line. No explanation. No label.
Good example:
"Built RAG-based research assistant using LangChain
that reduced manual work by 70%"
"""
            }],
            max_tokens  = 60,
            temperature = 0.1
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Key project extract error: {e}")
        return ""


def call_groq(prompt: str) -> dict:
    """
    Groq API call karo.
    JSON response parse karo.

    Why fallback dict?
    LLM kabhi kabhi malformed JSON deta hai.
    App crash nahi honi chahiye email generation pe.
    User ko error dikhao, crash nahi.
    """
    try:
        response = client.chat.completions.create(
            model      = LLM_MODEL,
            messages   = [{"role": "user", "content": prompt}],
            max_tokens = 600,
            temperature= 0.7
        )
        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)

    except json.JSONDecodeError:
        logger.error("Groq JSON parse failed")
        return {
            "subject"                 : "Quick thought on your product",
            "body"                    : "Could not generate — please try again.",
            "gap_identified"          : "",
            "proposal"                : "",
            "why_user_fits"           : "",
            "core_problem_identified" : "",
            "idea_suggested"          : "",
            "new_value_added"         : ""
        }
    except Exception as e:
        logger.error(f"Groq call error: {e}")
        return {}


def get_resume_path(user_id: int, name: str) -> str:
    """Resume path banao."""
    safe_name = name.lower()\
                    .replace(" ", "_")\
                    .replace("/", "_")\
                    .replace(".", "_")[:30]
    return os.path.join(
        "uploads", str(user_id),
        "resumes", f"{safe_name}_resume.pdf"
    )


def get_fallback_resume(db: Session, user_id: int) -> str:
    """
    Optimized resume nahi mila toh
    base resume use karo.
    """
    profile = db.query(UserProfile).filter(
        UserProfile.user_id == user_id
    ).first()
    return profile.resume_path if profile else None


# ─────────────────────────────────────────────
# TYPE 1 — Job Application Email
# ─────────────────────────────────────────────

def generate_job_email(
    db      : Session,
    user_id : int,
    job_id  : int
) -> dict:
    """
    Specific job opening ke liye email.

    Angle:
    → Core problem identify karo jo role solve karta hai
    → User ka project connect karo us problem se
    → Ek small idea suggest karo role ke liye
    → Value-first — begging nahi
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return {"error": "Job nahi mili"}

    user_data   = get_user_data(db, user_id)
    key_project = get_user_key_project(db, user_id)

    if not user_data:
        return {"error": "Profile incomplete hai"}

    # Best contact dhundho
    contact = db.query(Contact)\
                .join(Company)\
                .filter(Company.name == job.company_name)\
                .order_by(Contact.priority)\
                .first()

    contact_name = contact.name if contact else "Hiring Manager"
    contact_role = contact.role if contact else "Hiring Team"

    # Company info agar available hai
    company = db.query(Company)\
                .filter(Company.name == job.company_name)\
                .first()

    company_summary = ""
    tech_str        = ""

    if company:
        company_summary = company.company_summary or company.description or ""
        try:
            tech_list = json.loads(company.tech_stack or "[]")
            tech_str  = ", ".join(tech_list)
        except:
            tech_str = ""

    prompt_template = load_prompt("job_email_prompt.txt")
    prompt = prompt_template.format(
        user_name        = user_data["name"],
        contact_name     = contact_name,
        contact_role     = contact_role,
        company_name     = job.company_name or "Company",
        job_title        = job.title,
        job_description  = (job.description or "")[:600],
        user_skills      = ", ".join(user_data["skills"][:10]),
        key_project      = key_project,
        experience_years = user_data["experience_years"],
        company_summary  = company_summary,
        tech_stack       = tech_str
    )

    result = call_groq(prompt)

    # Resume path
    resume_path = get_resume_path(user_id, job.company_name or f"job_{job_id}")
    if not os.path.exists(resume_path):
        resume_path = get_fallback_resume(db, user_id)

    return {
        "type"                   : "job_email",
        "job_id"                 : job_id,
        "job_title"              : job.title,
        "company"                : job.company_name,
        "contact_name"           : contact_name,
        "contact_role"           : contact_role,
        "contact_email"          : contact.email if contact else None,
        "subject"                : result.get("subject",                 ""),
        "body"                   : result.get("body",                    ""),
        "core_problem_identified": result.get("core_problem_identified", ""),
        "idea_suggested"         : result.get("idea_suggested",          ""),
        "resume_path"            : resume_path,
    }


# ─────────────────────────────────────────────
# TYPE 2 — Cold Email (No Opening)
# ─────────────────────────────────────────────

def generate_cold_email(
    db         : Session,
    user_id    : int,
    company_id : int
) -> dict:
    """
    YC company ke liye cold email.

    Angle:
    → Product ka ek gap identify karo
    → Concrete proposal suggest karo
    → User ki exact skills se connect karo
    → Founder soche "ye kaam ka banda hai"
    """
    company = db.query(Company).filter(
        Company.id == company_id
    ).first()
    if not company:
        return {"error": "Company nahi mili"}

    if not company.research_done:
        return {
            "error": "Pehle research karo — /jobs/research/{id}"
        }

    user_data   = get_user_data(db, user_id)
    key_project = get_user_key_project(db, user_id)

    if not user_data:
        return {"error": "Profile incomplete hai"}

    contact = db.query(Contact)\
                .filter(Contact.company_id == company_id)\
                .order_by(Contact.priority)\
                .first()

    try:
        tech_list = json.loads(company.tech_stack or "[]")
        tech_str  = ", ".join(tech_list)
    except:
        tech_str  = ""

    prompt_template = load_prompt("cold_email_prompt.txt")
    prompt = prompt_template.format(
        user_name        = user_data.get("name", ""),
        contact_name     = contact.name  if contact else "Founder",
        contact_role     = contact.role  if contact else "Founder",
        company_name     = company.name,
        user_skills      = ", ".join(user_data.get("skills", [])[:10]),
        key_project      = key_project,
        experience_years = user_data.get("experience_years", 0),
        company_summary  = company.company_summary or company.description or "",
        tech_stack       = tech_str,
        recent_highlight = company.recent_news or "",
    )

    result = call_groq(prompt)

    resume_path = get_resume_path(user_id, company.name)
    if not os.path.exists(resume_path):
        resume_path = get_fallback_resume(db, user_id)

    return {
        "type"          : "cold_email",
        "company_id"    : company_id,
        "company"       : company.name,
        "contact_name"  : contact.name  if contact else "Founder",
        "contact_role"  : contact.role  if contact else "Founder",
        "contact_email" : contact.email if contact else None,
        "subject"       : result.get("subject",       ""),
        "body"          : result.get("body",           ""),
        "gap_identified": result.get("gap_identified", ""),
        "proposal"      : result.get("proposal",       ""),
        "why_user_fits" : result.get("why_user_fits",  ""),
        "resume_path"   : resume_path,
        "company_summary": company.company_summary,
    }


# ─────────────────────────────────────────────
# TYPE 3 — Follow-up Email
# ─────────────────────────────────────────────

def generate_followup_email(
    db             : Session,
    application_id : int
) -> dict:
    """
    Follow-up email — new value add karo.
    Sirf "just following up" nahi — boring hai ye.
    Kuch naya lao — prototype, insight, news hook.
    """
    from backend.models.application import Application
    from datetime import datetime

    app = db.query(Application).filter(
        Application.id == application_id
    ).first()
    if not app:
        return {"error": "Application nahi mili"}

    days_ago = 0
    if app.sent_date:
        days_ago = (datetime.utcnow() - app.sent_date).days

    contact = db.query(Contact).filter(
        Contact.id == app.contact_id
    ).first()

    # Company name nikalo
    company_name      = ""
    original_proposal = ""

    if app.company_id:
        company = db.query(Company).filter(
            Company.id == app.company_id
        ).first()
        if company:
            company_name = company.name

    elif app.job_id:
        job = db.query(Job).filter(
            Job.id == app.job_id
        ).first()
        if job:
            company_name = job.company_name or ""

    # Original email body se proposal context
    if app.email_body:
        original_proposal = app.email_body[:200]

    prompt_template = load_prompt("followup_prompt.txt")
    prompt = prompt_template.format(
        user_name         = "",
        days_ago          = days_ago,
        company_name      = company_name,
        contact_name      = contact.name if contact else "Hiring Manager",
        contact_role      = contact.role if contact else "",
        original_subject  = app.email_subject or "",
        original_proposal = original_proposal
    )

    result = call_groq(prompt)

    return {
        "application_id" : application_id,
        "contact_email"  : contact.email if contact else None,
        "subject"        : result.get("subject",         f"Re: {app.email_subject}"),
        "body"           : result.get("body",            ""),
        "new_value_added": result.get("new_value_added", ""),
        "days_ago"       : days_ago
    }