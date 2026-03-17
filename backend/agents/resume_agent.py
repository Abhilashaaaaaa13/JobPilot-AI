# backend/agents/resume_agent.py
# Har job/company ke liye resume customize karo
# ATS score improve karo
# New PDF generate karo

import os
import json
from groq import Groq
from sqlalchemy.orm import Session
from backend.models.job import Job
from backend.models.company import Company
from backend.models.application import Application
from backend.models.user import User, UserProfile
from backend.utils.pdf_parser import extract_text_from_pdf
from backend.utils.ats_scorer import calculate_ats_score
from backend.utils.pdf_writer import create_resume_pdf
from backend.config import (
    GROQ_API_KEY, LLM_MODEL,
    UPLOAD_DIR, TARGET_ATS_SCORE
)
from loguru import logger

client = Groq(api_key=GROQ_API_KEY)


def load_prompt(filename: str) -> str:
    """Prompt file load karo."""
    path = os.path.join("backend", "prompts", filename)
    try:
        with open(path, "r") as f:
            return f.read()
    except:
        return ""


def get_user_resume_text(
    db      : Session,
    user_id : int
) -> str:
    """
    User ka base resume text lo.
    PDF parse karke text extract karo.
    """
    profile = db.query(UserProfile).filter(
        UserProfile.user_id == user_id
    ).first()

    if not profile or not profile.resume_path:
        return ""

    if not os.path.exists(profile.resume_path):
        return ""

    return extract_text_from_pdf(profile.resume_path)


def rewrite_resume_with_groq(
    resume_text      : str,
    job_description  : str,
    company_name     : str,
    missing_keywords : list
) -> str:
    """
    Groq se resume rewrite karo.
    Missing keywords naturally inject karo.

    Why low temperature (0.3)?
    Resume accurate hona chahiye —
    facts same rehne chahiye.
    Sirf wording improve hogi.
    High temperature = hallucination risk.
    """
    prompt_template = load_prompt("resume_rewrite_prompt.txt")

    if not prompt_template:
        # Fallback prompt agar file nahi mili
        prompt_template = """
Rewrite this resume to include these keywords naturally: {missing_keywords}
Keep all facts true. Return only the rewritten resume text.

Resume: {resume_text}
Job Description: {job_description}
Company: {company_name}
"""

    prompt = prompt_template.format(
        resume_text      = resume_text[:3000],
        job_description  = job_description[:1500],
        company_name     = company_name,
        missing_keywords = ", ".join(missing_keywords)
    )

    try:
        response = client.chat.completions.create(
            model      = LLM_MODEL,
            messages   = [{"role": "user", "content": prompt}],
            max_tokens = 2000,
            temperature= 0.3
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        logger.error(f"Groq resume rewrite error: {e}")
        return resume_text   # Original return karo agar fail ho


def get_output_path(
    user_id      : int,
    company_name : str
) -> str:
    """
    Resume save karne ka path banao.
    uploads/{user_id}/resumes/company_resume.pdf
    """
    safe_name = company_name.lower()\
                            .replace(" ", "_")\
                            .replace("/", "_")\
                            .replace(".", "_")[:30]

    return os.path.join(
        UPLOAD_DIR,
        str(user_id),
        "resumes",
        f"{safe_name}_resume.pdf"
    )


# ─────────────────────────────────────────────
# MAIN FUNCTIONS
# ─────────────────────────────────────────────

def optimize_resume_for_job(
    db      : Session,
    user_id : int,
    job_id  : int
) -> dict:
    """
    Job ke liye resume optimize karo.

    Flow:
    1. Resume text lo
    2. Job description lo
    3. ATS score calculate karo (before)
    4. Rewrite karo agar score < target
    5. ATS score calculate karo (after)
    6. PDF banao
    7. Result return karo
    """
    # Job lo
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return {"error": "Job nahi mili"}

    # Resume text lo
    resume_text = get_user_resume_text(db, user_id)
    if not resume_text:
        return {"error": "Resume nahi mila — pehle upload karo"}

    jd_text = f"{job.title} {job.description or ''}"

    # ATS Score — Before
    ats_before = calculate_ats_score(resume_text, jd_text)
    logger.info(
        f"📊 ATS Before: {ats_before['ats_score']}% "
        f"— {job.title} @ {job.company_name}"
    )

    rewritten_text = resume_text
    ats_after      = ats_before

    # Sirf rewrite karo agar score target se kam hai
    if ats_before["ats_score"] < TARGET_ATS_SCORE:
        logger.info(
            f"✍️  Rewriting resume — "
            f"missing: {ats_before['missing_keywords']}"
        )

        rewritten_text = rewrite_resume_with_groq(
            resume_text      = resume_text,
            job_description  = jd_text,
            company_name     = job.company_name or "",
            missing_keywords = ats_before["missing_keywords"]
        )

        # ATS Score — After
        ats_after = calculate_ats_score(rewritten_text, jd_text)
        logger.info(f"📊 ATS After: {ats_after['ats_score']}%")
    else:
        logger.info("✅ ATS score already good — no rewrite needed")

    # PDF banao
    user = db.query(User).filter(User.id == user_id).first()
    output_path = get_output_path(
        user_id,
        job.company_name or f"job_{job_id}"
    )

    create_resume_pdf(
        resume_text = rewritten_text,
        output_path = output_path,
        user_name   = user.email if user else ""
    )

    return {
        "job_id"          : job_id,
        "company"         : job.company_name,
        "resume_path"     : output_path,
        "ats_before"      : ats_before["ats_score"],
        "ats_after"       : ats_after["ats_score"],
        "improvement"     : ats_after["ats_score"] - ats_before["ats_score"],
        "matched_keywords": ats_after["matched_keywords"],
        "missing_keywords": ats_after["missing_keywords"],
        "rewritten"       : ats_before["ats_score"] < TARGET_ATS_SCORE
    }


def optimize_resume_for_company(
    db         : Session,
    user_id    : int,
    company_id : int
) -> dict:
    """
    Cold email company ke liye resume optimize karo.
    Job description nahi hai —
    company description use karo.
    """
    company = db.query(Company).filter(
        Company.id == company_id
    ).first()
    if not company:
        return {"error": "Company nahi mili"}

    resume_text = get_user_resume_text(db, user_id)
    if not resume_text:
        return {"error": "Resume nahi mila"}

    # Company description as JD
    jd_text = (
        f"{company.description or ''} "
        f"{company.company_summary or ''} "
        f"{company.tech_stack or ''}"
    )

    # ATS Before
    ats_before = calculate_ats_score(resume_text, jd_text)
    logger.info(
        f"📊 ATS Before: {ats_before['ats_score']}% "
        f"— {company.name}"
    )

    rewritten_text = resume_text
    ats_after      = ats_before

    if ats_before["ats_score"] < TARGET_ATS_SCORE:
        rewritten_text = rewrite_resume_with_groq(
            resume_text      = resume_text,
            job_description  = jd_text,
            company_name     = company.name,
            missing_keywords = ats_before["missing_keywords"]
        )
        ats_after = calculate_ats_score(rewritten_text, jd_text)
        logger.info(f"📊 ATS After: {ats_after['ats_score']}%")

    # PDF banao
    output_path = get_output_path(user_id, company.name)
    create_resume_pdf(
        resume_text = rewritten_text,
        output_path = output_path
    )

    return {
        "company_id"      : company_id,
        "company"         : company.name,
        "resume_path"     : output_path,
        "ats_before"      : ats_before["ats_score"],
        "ats_after"       : ats_after["ats_score"],
        "improvement"     : ats_after["ats_score"] - ats_before["ats_score"],
        "matched_keywords": ats_after["matched_keywords"],
        "missing_keywords": ats_after["missing_keywords"],
    }