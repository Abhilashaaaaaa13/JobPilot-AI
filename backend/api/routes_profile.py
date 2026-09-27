# backend/api/routes_profile.py
import json
import os

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from pydantic import BaseModel

from backend.database import SessionLocal
from backend.models.user import User, UserProfile
from backend.api.auth import get_current_user

router = APIRouter(prefix="/api/profile", tags=["profile"])


def _profile_dict(profile: UserProfile | None) -> dict:
    if not profile:
        return {
            "one_liner": "", "preferred_type": "job", "target_roles": [],
            "target_industries": [], "skills": [], "gmail_address": "",
            "gmail_connected": False, "resume_uploaded": False, "resume_filename": "",
            "experience_years": 0, "education": "", "name": "",
        }
    return {
        "one_liner": profile.one_liner or "",
        "preferred_type": profile.preferred_type or "job",
        "target_roles": json.loads(profile.target_roles or "[]"),
        "target_industries": json.loads(profile.target_industries or "[]"),
        "skills": json.loads(profile.skills or "[]"),
        "gmail_address": profile.gmail_address or "",
        "gmail_connected": bool(profile.gmail_address and profile.gmail_app_password),
        "resume_uploaded": bool(profile.resume_path and os.path.exists(profile.resume_path)),
        "resume_filename": os.path.basename(profile.resume_path) if profile.resume_path else "",
        "experience_years": profile.experience_years or 0,
        "education": profile.education or "",
        "name": profile.name or "",
    }


@router.get("")
def get_profile(user: User = Depends(get_current_user)):
    db = SessionLocal()
    try:
        profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
        return _profile_dict(profile)
    finally:
        db.close()


class ProfileUpdate(BaseModel):
    one_liner: str | None = None
    preferred_type: str | None = None
    target_roles: list[str] | None = None
    target_industries: list[str] | None = None
    skills: list[str] | None = None
    location: str | None = None
    gmail_address: str | None = None
    gmail_app_password: str | None = None


@router.put("")
def update_profile(body: ProfileUpdate, user: User = Depends(get_current_user)):
    db = SessionLocal()
    try:
        profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
        if not profile:
            profile = UserProfile(user_id=user.id)
            db.add(profile)

        if body.one_liner is not None:
            profile.one_liner = body.one_liner.strip()
        if body.preferred_type is not None:
            profile.preferred_type = body.preferred_type
        if body.target_roles is not None:
            profile.target_roles = json.dumps(body.target_roles)
        if body.target_industries is not None:
            profile.target_industries = json.dumps(body.target_industries)
        if body.skills is not None:
            profile.skills = json.dumps(body.skills)
        if body.location is not None:
            profile.preferred_locations = json.dumps([body.location])
        if body.gmail_address:
            profile.gmail_address = body.gmail_address.strip()
        if body.gmail_app_password:
            profile.gmail_app_password = body.gmail_app_password.replace(" ", "")

        db.commit()
        db.refresh(profile)
        return _profile_dict(profile)
    finally:
        db.close()


@router.post("/resume")
async def upload_resume(file: UploadFile = File(...), user: User = Depends(get_current_user)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported")

    upload_dir = f"uploads/{user.id}"
    os.makedirs(upload_dir, exist_ok=True)
    resume_path = f"{upload_dir}/resume_base.pdf"
    with open(resume_path, "wb") as f:
        f.write(await file.read())

    parsed = {}
    try:
        import pdfplumber
        resume_text = ""
        with pdfplumber.open(resume_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    resume_text += text + "\n"

        if resume_text:
            import os as _os
            from groq import Groq
            client = Groq(api_key=_os.getenv("GROQ_API_KEY"))
            prompt = f"""You are a resume parser. Extract information from this resume.

Return ONLY a JSON object, no markdown, no explanation:
{{
    "name": "full name",
    "skills": ["skill1", "skill2"],
    "target_roles": ["AI Engineer", "ML Engineer"],
    "experience_years": 0,
    "education": "degree and college",
    "current_role": "current or last role",
    "summary": "2-3 line professional summary",
    "key_project": "most impressive project in 1 line with impact"
}}

Resume:
{resume_text[:4000]}
"""
            res = client.chat.completions.create(
                model=_os.getenv("LLM_MODEL", "openai/gpt-oss-20b"),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=900,
                temperature=0.1,
                reasoning_effort="low",
            )
            raw = res.choices[0].message.content.strip()
            raw = raw.replace("```json", "").replace("```", "").strip()
            parsed = json.loads(raw)
    except Exception:
        parsed = {}

    db = SessionLocal()
    try:
        profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
        if not profile:
            profile = UserProfile(user_id=user.id)
            db.add(profile)

        profile.resume_path = resume_path
        if parsed.get("skills"):
            profile.skills = json.dumps(parsed["skills"])
        if parsed.get("target_roles"):
            profile.target_roles = json.dumps(parsed["target_roles"])
        if parsed.get("experience_years") is not None:
            profile.experience_years = parsed["experience_years"]
        if parsed.get("education"):
            profile.education = parsed["education"]
        if parsed.get("name") and not profile.name:
            profile.name = parsed["name"]
        if parsed.get("summary") and not profile.one_liner:
            profile.one_liner = parsed["summary"][:150]

        db.commit()
        db.refresh(profile)
        result = _profile_dict(profile)
        result["parsed"] = parsed
        return result
    finally:
        db.close()


@router.delete("/resume")
def remove_resume(user: User = Depends(get_current_user)):
    db = SessionLocal()
    try:
        profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
        if profile and profile.resume_path:
            try:
                if os.path.exists(profile.resume_path):
                    os.remove(profile.resume_path)
            except Exception:
                pass
            # The rest of the profile (one-liner, roles, skills) was derived
            # from this resume — removing it resets those too rather than
            # leaving stale data that no longer matches anything uploaded.
            profile.resume_path       = ""
            profile.one_liner         = ""
            profile.skills            = "[]"
            profile.target_roles      = "[]"
            profile.experience_years  = 0
            profile.education         = ""
            db.commit()
        return {"success": True}
    finally:
        db.close()
