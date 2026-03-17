# backend/agents/scoring_agent.py
# Sab unscored jobs ko score karo
# user ke profile ke basis pe

import json
from sqlalchemy.orm import Session
from backend.models.job import Job
from backend.models.user import UserProfile
from backend.utils.ats_scorer import calculate_fit_score
from loguru import logger


def get_user_profile(db: Session, user_id: int) -> dict:
    """User ke skills aur experience lo."""
    profile = db.query(UserProfile).filter(
        UserProfile.user_id == user_id
    ).first()

    if not profile:
        return {"skills": [], "experience_years": 0}

    try:
        skills = json.loads(profile.skills) if profile.skills else []
    except:
        skills = []

    return {
        "skills"          : skills,
        "experience_years": profile.experience_years or 0
    }


def score_all_jobs(db: Session, user_id: int) -> dict:
    """
    Sab unscored jobs ko score karo.
    
    Why sirf unscored?
    Already scored jobs dobara score karna
    wasteful hai — Groq API calls bachao.
    fit_score == 0 matlab score nahi hua abhi.
    """
    user_data = get_user_profile(db, user_id)

    if not user_data["skills"]:
        return {
            "error"  : "Profile mein skills nahi hain",
            "scored" : 0
        }

    # Sirf unscored jobs lo
    jobs = db.query(Job).filter(Job.fit_score == 0).all()

    if not jobs:
        return {"message": "Sab jobs already scored hain", "scored": 0}

    scored_count    = 0
    relevant_count  = 0

    for job in jobs:
        try:
            result = calculate_fit_score(
                user_skills      = user_data["skills"],
                experience_years = user_data["experience_years"],
                job_description  = job.description or "",
                job_title        = job.title or ""
            )

            # DB update karo
            job.fit_score   = result["fit_score"]
            job.is_relevant = result["is_relevant"]

            if result["is_relevant"]:
                relevant_count += 1
                job.status = "scored"
            else:
                job.status = "filtered_out"

            scored_count += 1

            logger.info(
                f"  📊 {job.title[:40]} @ {job.company_name} "
                f"→ {result['fit_score']}% "
                f"{'✅' if result['is_relevant'] else '❌'}"
            )

        except Exception as e:
            logger.error(f"  ❌ Score error {job.id}: {e}")
            continue

    db.commit()

    logger.info(
        f"✅ Scoring done — "
        f"{scored_count} scored, "
        f"{relevant_count} relevant"
    )

    return {
        "total_scored"   : scored_count,
        "relevant"       : relevant_count,
        "filtered_out"   : scored_count - relevant_count
    }


def score_single_job(
    db      : Session,
    user_id : int,
    job_id  : int
) -> dict:
    """
    Ek specific job score karo.
    User job detail page pe jaaye
    toh detailed breakdown dikhao.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return {"error": "Job nahi mili"}

    user_data = get_user_profile(db, user_id)

    result = calculate_fit_score(
        user_skills      = user_data["skills"],
        experience_years = user_data["experience_years"],
        job_description  = job.description or "",
        job_title        = job.title or ""
    )

    # Update karo
    job.fit_score   = result["fit_score"]
    job.is_relevant = result["is_relevant"]
    db.commit()

    return {
        "job_id"          : job_id,
        "title"           : job.title,
        "company"         : job.company_name,
        "fit_score"       : result["fit_score"],
        "keyword_score"   : result["keyword_score"],
        "semantic_score"  : result["semantic_score"],
        "matched_keywords": result["matched_keywords"],
        "missing_keywords": result["missing_keywords"],
        "is_relevant"     : result["is_relevant"]
    }