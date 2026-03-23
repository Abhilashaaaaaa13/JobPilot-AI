# backend/agents/resume_agent.py

import os
import json
from groq   import Groq
from loguru import logger
from dotenv import load_dotenv
load_dotenv()

client         = Groq(api_key=os.getenv("GROQ_API_KEY"))
LLM_MODEL      = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
TARGET_ATS     = int(os.getenv("TARGET_ATS_SCORE", 70))
UPLOAD_DIR     = "uploads"


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def load_prompt(filename: str) -> str:
    path = os.path.join("backend", "prompts", filename)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except:
        return ""


def get_resume_text(user_id: int) -> str:
    """User ka resume PDF se text nikalo."""
    resume_path = f"{UPLOAD_DIR}/{user_id}/resume_base.pdf"
    if not os.path.exists(resume_path):
        return ""
    try:
        import pdfplumber
        text = ""
        with pdfplumber.open(resume_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text += t + "\n"
        return text
    except Exception as e:
        logger.error(f"PDF read error: {e}")
        return ""


def get_resume_path(user_id: int) -> str:
    return f"{UPLOAD_DIR}/{user_id}/resume_base.pdf"


def get_output_path(user_id: int, name: str) -> str:
    safe = name.lower()\
               .replace(" ","_")\
               .replace("/","_")\
               .replace(".","_")[:30]
    path = os.path.join(
        UPLOAD_DIR, str(user_id), "resumes", f"{safe}_resume.pdf"
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def calculate_ats_score(resume_text: str, jd_text: str) -> dict:
    """
    Simple keyword-based ATS score.
    """
    try:
        from backend.utils.ats_scorer import calculate_ats_score as _calc
        return _calc(resume_text, jd_text)
    except:
        # Fallback — simple keyword match
        resume_lower = resume_text.lower()
        jd_words     = set(
            w for w in jd_text.lower().split()
            if len(w) > 3
        )
        matched = [w for w in jd_words if w in resume_lower]
        score   = int(len(matched) / max(len(jd_words), 1) * 100)
        missing = [w for w in jd_words if w not in resume_lower]

        return {
            "ats_score"       : min(score, 100),
            "matched_keywords": matched[:10],
            "missing_keywords": missing[:10]
        }


def rewrite_resume(
    resume_text     : str,
    jd_text         : str,
    company_name    : str,
    missing_keywords: list
) -> str:
    """Groq se resume rewrite karo — keywords inject karo."""
    prompt_template = load_prompt("resume_rewrite_prompt.txt")

    if prompt_template:
        prompt = prompt_template.format(
            resume_text      = resume_text[:3000],
            job_description  = jd_text[:1500],
            company_name     = company_name,
            missing_keywords = ", ".join(missing_keywords)
        )
    else:
        prompt = f"""
Rewrite this resume to naturally include these keywords: {', '.join(missing_keywords)}
Keep all facts true. Do not add fake experience.
Return ONLY the rewritten resume text.

Company: {company_name}
Job Context: {jd_text[:500]}

Resume:
{resume_text[:3000]}
"""

    try:
        res = client.chat.completions.create(
            model      = LLM_MODEL,
            messages   = [{"role": "user", "content": prompt}],
            max_tokens = 2000,
            temperature= 0.3
        )
        return res.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Resume rewrite error: {e}")
        return resume_text


def create_pdf(text: str, output_path: str, user_id: int):
    """Resume text se PDF banao."""
    try:
        from backend.utils.pdf_writer import create_resume_pdf
        create_resume_pdf(
            resume_text = text,
            output_path = output_path
        )
    except Exception as e:
        logger.error(f"PDF create error: {e}")
        # Fallback — original copy karo
        import shutil
        orig = get_resume_path(user_id)
        if os.path.exists(orig):
            shutil.copy(orig, output_path)


# ─────────────────────────────────────────────
# MAIN FUNCTIONS — NO DB
# ─────────────────────────────────────────────

def optimize_for_job(
    user_id  : int,
    job_title: str,
    company  : str,
    job_desc : str
) -> dict:
    """
    Job ke liye resume optimize karo.
    No DB — direct args.

    Args:
        user_id  : int
        job_title: "AI Engineer"
        company  : "Anthropic"
        job_desc : job description text
    """
    resume_text = get_resume_text(user_id)
    if not resume_text:
        return {
            "error"        : "Resume nahi mila — onboarding mein upload karo",
            "original_path": get_resume_path(user_id),
            "ats_before"   : 0,
            "ats_after"    : 0,
            "changes"      : []
        }

    jd_text = f"{job_title} {job_desc}"

    # ATS Before
    before    = calculate_ats_score(resume_text, jd_text)
    ats_before= before["ats_score"]
    missing   = before["missing_keywords"]

    logger.info(
        f"📊 ATS Before: {ats_before}% — {job_title} @ {company}"
    )

    orig_path = get_resume_path(user_id)
    opt_path  = get_output_path(user_id, company)

    rewritten_text = resume_text
    ats_after      = ats_before
    changes        = missing[:5]

    # Rewrite agar score kam hai
    if ats_before < TARGET_ATS and missing:
        rewritten_text = rewrite_resume(
            resume_text      = resume_text,
            jd_text          = jd_text,
            company_name     = company,
            missing_keywords = missing
        )
        after     = calculate_ats_score(rewritten_text, jd_text)
        ats_after = after["ats_score"]
        logger.info(f"📊 ATS After: {ats_after}%")

        create_pdf(rewritten_text, opt_path, user_id)
    else:
        # Score theek hai — original copy karo
        import shutil
        if os.path.exists(orig_path):
            shutil.copy(orig_path, opt_path)

    return {
        "job_title"      : job_title,
        "company"        : company,
        "original_path"  : orig_path,
        "optimized_path" : opt_path,
        "ats_before"     : ats_before,
        "ats_after"      : ats_after,
        "improvement"    : ats_after - ats_before,
        "changes"        : changes,
        "rewritten"      : ats_before < TARGET_ATS
    }


def optimize_for_company(
    user_id    : int,
    company    : str,
    description: str
) -> dict:
    """
    Cold outreach company ke liye resume optimize karo.
    No DB — direct args.

    Args:
        user_id    : int
        company    : "Playabl.ai"
        description: company description
    """
    resume_text = get_resume_text(user_id)
    if not resume_text:
        return {
            "error"         : "Resume nahi mila — onboarding mein upload karo",
            "original_path" : get_resume_path(user_id),
            "optimized_path": get_resume_path(user_id),
            "ats_before"    : 0,
            "ats_after"     : 0,
            "changes"       : []
        }

    jd_text = description

    # ATS Before
    before    = calculate_ats_score(resume_text, jd_text)
    ats_before= before["ats_score"]
    missing   = before["missing_keywords"]

    logger.info(f"📊 ATS Before: {ats_before}% — {company}")

    orig_path = get_resume_path(user_id)
    opt_path  = get_output_path(user_id, company)

    rewritten_text = resume_text
    ats_after      = ats_before
    changes        = missing[:5]

    if ats_before < TARGET_ATS and missing:
        rewritten_text = rewrite_resume(
            resume_text      = resume_text,
            jd_text          = jd_text,
            company_name     = company,
            missing_keywords = missing
        )
        after     = calculate_ats_score(rewritten_text, jd_text)
        ats_after = after["ats_score"]
        logger.info(f"📊 ATS After: {ats_after}%")

        create_pdf(rewritten_text, opt_path, user_id)
    else:
        import shutil
        if os.path.exists(orig_path):
            shutil.copy(orig_path, opt_path)

    return {
        "company"       : company,
        "original_path" : orig_path,
        "optimized_path": opt_path,
        "ats_before"    : ats_before,
        "ats_after"     : ats_after,
        "improvement"   : ats_after - ats_before,
        "changes"       : changes,
        "rewritten"     : ats_before < TARGET_ATS
    }


# DB wale functions — pipeline ke liye
# Backward compatibility

def optimize_resume_for_job(db, user_id, job_id):
    """DB version — pipeline mein use hota hai."""
    try:
        from backend.models.job import Job
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return {"error": "Job nahi mili"}
        return optimize_for_job(
            user_id   = user_id,
            job_title = job.title,
            company   = job.company_name or "",
            job_desc  = job.description  or ""
        )
    except Exception as e:
        return {"error": str(e)}


def optimize_resume_for_company(db, user_id, company_id):
    """DB version — pipeline mein use hota hai."""
    try:
        from backend.models.company import Company
        company = db.query(Company).filter(
            Company.id == company_id
        ).first()
        if not company:
            return {"error": "Company nahi mili"}
        return optimize_for_company(
            user_id     = user_id,
            company     = company.name,
            description = company.description or ""
        )
    except Exception as e:
        return {"error": str(e)}