from pydantic import BaseModel, EmailStr
from typing import Optional, List

class ProfileUpdateRequest(BaseModel):
    name                           : Optional[str]
    phone                          : Optional[str]
    linkedin                       : Optional[str]
    github                         : Optional[str]
    skills                         : Optional[List[str]]
    experience_years               : Optional[int]
    target_roles                   : Optional[List[int]]
    target_industries              : Optional[List[int]]
    preferred_locations            : Optional[List[str]]
    preferred_type                 : Optional[str]    #internship/job/both
    preferred_company_size         : Optional[str]
    gmail_address                  : Optional[EmailStr]
    gmail_app_password             : Optional[str]
    sheets_id                      : Optional[str]
    followup_after_days            : Optional[int]
    max_followups                  : Optional[int]
    min_fit_score                  : Optional[int]

class ProfileResponse(BaseModel):
    id                     : int
    name                   : Optional[str]
    phone                  : Optional[str]
    linkedin               : Optional[str]
    github                 : Optional[str]
    skills                 : Optional[List[str]]
    experience_years       : Optional[int]
    target_roles           : Optional[List[str]]
    target_industries      : Optional[List[str]]
    preferred_locations    : Optional[List[str]]
    preferred_type         : Optional[str]
    preferred_company_size : Optional[str]
    gmail_address          : Optional[str]
    resume_path            : Optional[str]
    onboarding_complete    : bool = False

    class Config:
        from_attributes = True