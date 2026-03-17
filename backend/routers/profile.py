import os
import json
import shutil
from fastapi import (
    APIRouter, Depends, HTTPException, UploadFile,File
)
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.user import User, UserProfile
from backend.schemas.profile import ProfileUpdateRequest, ProfileResponse
from backend.dependencies import get_current_user
from backend.utils.pdf_parser import parse_resume
from backend.config import UPLOAD_DIR

router = APIRouter(prefix="/profile",tags=["profile"])

def get_or_create_profile(user: User, db: Session)->UserProfile:
    """
    if profile exists? return.
    if not? then create
    why?
    on registration only build user
    profile is created on onboarding"""
    profile = db.query(UserProfile).filter(
        UserProfile.user_id == user.id
    ).first()

    if not profile:
        profile = UserProfile(user_ud=user.id)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile

@router.post("/upload-resume")
async def upload_resume(
    file          : UploadFile      = File(...),
    db            : Session         = Depends(get_db),
    current_user  : User            = Depends(get_current_user)
):
    """Upload resume PDF.
    -> save file uploads/{user_id}/resume_base.pdf
    -> save in profile
    -> return extracted data-Form would be prefilled"""
    #only allow pdf
    if not file.filename.endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail = "Only PDFS are allowed"
        )
    
    #create upload folder
    user_upload_dir = os.path.join(UPLOAD_DIR, str(current_user.id))
    os.makedirs(user_upload_dir, exist_ok=True)
    os.makedirs(os.path.join(user_upload_dir, "resumes"),exist_ok=True)

    #save file
    resume_path = os.path.join(user_upload_dir,"resume_base.pdf")
    with open(resume_path,"wb")as f:
        shutil.copyfileobj(file.file,f)

    #parse kro
    parsed = parse_resume(resume_path)

    #profile update kro with extracted data
    profile = get_or_create_profile(current_user,db)
    profile.resume_path = resume_path

    if parsed.get("name") and not profile.name:
        profile.name = parsed["name"]

    if parsed.get("phone") and not profile.phone:
        profile.phone = parsed["phone"]
    
    if parsed.get("linkedin") and not profile.linkedin:
        profile.linkedin = parsed["linkedin"]

    if parsed.get("github") and not profile.github:
        profile.github = parsed["github"]
    if parsed.get("skills"):
        profile.skills = json.dumps(parsed["skills"])

    if parsed.get("experience_years"):
        profile.experience_years = parsed["experience_years"]

    if parsed.get("education"):
        profile_education = json.dumps(parsed["education"])
    
    db.commit()
    return {
        "message" : "Resume uploaded and parsed successfully.",
        "resume_path" : resume_path,
        "extracted" : parsed

    }
@router.put("/complete", response_model=ProfileResponse)
def complete_profile(
    req : ProfileUpdateRequest,
    db  : Session  = Depends(get_db),
    current_user : User = Depends(get_current_user)
):
    """Fill all the details from form.
    whats not in resume will be here"""
    profile = get_or_create_profile(current_user, db)
     # Sirf wo fields update karo jo bheje gaye hain
    # None bheja matlab update mat karo
    if req.name                                        : profile.name = req.name
    if req.phone                                       : profile.phone = req.phone
    if req.linkedin                                    : profile.linkedin = req.linkedin
    if req.github                                      : profile.github = req.github
    if req.skills                                      : profile.skills = json.dumps(req.skills)
    if req.experience_years is not None                : profile.experience_years = req.experience_years
    if req.target_roles                                : profile.target_roles = json.dumps(req.target_roles)
    if req.target_industries                           : profile.target_industries = json.dumps(req.target_industries)
    if req.preferred_locations                         : profile.preferred_locations = json.dumps(req.preferred_locations)
    if req.preferred_type                              : profile.preferred_type = req.preferred_type
    if req.preferred_company_size                      : profile.preferred_company_size = req.preferred_company_size
    if req.gmail_address                               : profile.gmail_address = req.gmail_address
    if req.gmail_app_password                          : profile.gmail_app_password = req.gmail_app_password
    if req.sheets_id                                   : profile.sheets_id = req.sheets_id
    if req.followup_after_days                         : profile.followup_after_days = req.followup_after_days
    if req.min_fit_score                               : profile.min_fit_score = req.target_roles
        
    db.commit()
    db.refresh(profile)
    return _format_profile(profile)

@router.get("/me", response_model=ProfileResponse)
def get_profile(
    db           : Session = Depends(get_db),
    current_user : User = Depends(get_current_user)
):
    """take profile of current user"""
    profile = get_or_create_profile(current_user,db)
    return _format_profile(profile)

def _format_profile(profile: UserProfile)->dict:
    """convert JSON strings into list.
    JSON string is in DB, want list in API """
    def parse(val):
        if val is None:
            return []
        try:
            return json.loads(val)
        except:
            return []
        
    onboarding_complete = bool(
        profile.name and
        profile.skills and
        profile.target_roles and
        profile.gmail_address
    )
    return {
          "id"                    : profile.id,
        "name"                  : profile.name,
        "phone"                 : profile.phone,
        "linkedin"              : profile.linkedin,
        "github"                : profile.github,
        "skills"                : parse(profile.skills),
        "experience_years"      : profile.experience_years,
        "target_roles"          : parse(profile.target_roles),
        "target_industries"     : parse(profile.target_industries),
        "preferred_locations"   : parse(profile.preferred_locations),
        "preferred_type"        : profile.preferred_type,
        "preferred_company_size": profile.preferred_company_size,
        "gmail_address"         : profile.gmail_address,
        "resume_path"           : profile.resume_path,
        "onboarding_complete"   : onboarding_complete
    }

