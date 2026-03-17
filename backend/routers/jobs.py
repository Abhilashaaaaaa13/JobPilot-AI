# backend/routers/jobs.py

from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.user import User
from backend.models.job import Job
from backend.models.company import Company
from backend.dependencies import get_current_user
from backend.agents import scraper_agent,scoring_agent,research_agent,contact_finder,resume_agent
from backend.models.contact import Contact
router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/scrape")
def trigger_scrape(
    background_tasks: BackgroundTasks,
    db              : Session = Depends(get_db),
    current_user    : User    = Depends(get_current_user)
):
    background_tasks.add_task(
        scraper_agent.run,
        db      = db,
        user_id = current_user.id
    )
    return {
        "message": "Scraping background mein chal rahi hai",
        "status" : "running"
    }


@router.get("/list")
def get_jobs(
    source      : str = None,
    job_type    : str = None,
    skip        : int = 0,
    limit       : int = 20,
    db          : Session = Depends(get_db),
    current_user: User    = Depends(get_current_user)
):
    """Job listings — Internshala, Wellfound etc."""
    query = db.query(Job)

    if source:
        query = query.filter(Job.source == source)
    if job_type:
        query = query.filter(Job.job_type == job_type)

    total = query.count()
    jobs  = query.order_by(Job.scraped_date.desc())\
                 .offset(skip).limit(limit).all()

    return {
        "total": total,
        "jobs" : [
            {
                "id"          : j.id,
                "title"       : j.title,
                "company_name": j.company_name,
                "location"    : j.location,
                "job_type"    : j.job_type,
                "stipend"     : j.stipend,
                "source"      : j.source,
                "fit_score"   : j.fit_score,
                "status"      : j.status,
                "apply_url"   : j.apply_url,
            }
            for j in jobs
        ]
    }


@router.get("/companies")
def get_companies(
    skip        : int = 0,
    limit       : int = 20,
    db          : Session = Depends(get_db),
    current_user: User    = Depends(get_current_user)
):
    """Cold email targets — YC Companies etc."""
    query = db.query(Company)
    total = query.count()
    companies = query.order_by(Company.scraped_date.desc())\
                     .offset(skip).limit(limit).all()

    return {
        "total"    : total,
        "companies": [
            {
                "id"             : c.id,
                "name"           : c.name,
                "website"        : c.website,
                "description"    : c.description,
                "funding"        : c.funding,
                "team_size"      : c.team_size,
                "location"       : c.location,
                "source"         : c.source,
                "ai_related"     : c.ai_related,
                "research_done"  : c.research_done,
            }
            for c in companies
        ]
    }

@router.post("/score")
def trigger_scoring(
    background_tasks: BackgroundTasks,
    db              : Session = Depends(get_db),
    current_user    : User    = Depends(get_current_user)
):
    """
    Sab unscored jobs score karo.
    Background mein — time lag sakta hai.
    """
    background_tasks.add_task(
        scoring_agent.score_all_jobs,
        db      = db,
        user_id = current_user.id
    )
    return {"message": "Scoring shuru ho gayi", "status": "running"}


@router.get("/score/{job_id}")
def get_job_score(
    job_id      : int,
    db          : Session = Depends(get_db),
    current_user: User    = Depends(get_current_user)
):
    """Single job ka detailed score breakdown."""
    return scoring_agent.score_single_job(
        db      = db,
        user_id = current_user.id,
        job_id  = job_id
    )


@router.get("/recommended")
def get_recommended_jobs(
    skip        : int = 0,
    limit       : int = 20,
    db          : Session = Depends(get_db),
    current_user: User    = Depends(get_current_user)
):
    """
    Sirf relevant jobs — fit_score >= threshold.
    Score ke hisaab se sort karo — best first.
    """
    jobs = db.query(Job)\
             .filter(Job.is_relevant == True)\
             .order_by(Job.fit_score.desc())\
             .offset(skip).limit(limit).all()

    return {
        "total": len(jobs),
        "jobs" : [
            {
                "id"          : j.id,
                "title"       : j.title,
                "company_name": j.company_name,
                "location"    : j.location,
                "stipend"     : j.stipend,
                "fit_score"   : j.fit_score,
                "source"      : j.source,
                "apply_url"   : j.apply_url,
            }
            for j in jobs
        ]
    }

@router.post("/research/{company_id}")
def trigger_research(
    company_id      : int,
    db              : Session = Depends(get_db),
    current_user    : User    = Depends(get_current_user)
):
    """Ek company research karo."""
    return research_agent.research_company(db, company_id)


@router.post("/research/all/pending")
def research_all(
    background_tasks: BackgroundTasks,
    db              : Session = Depends(get_db),
    current_user    : User    = Depends(get_current_user)
):
    """Sab pending companies research karo."""
    background_tasks.add_task(
        research_agent.research_all_pending,
        db=db
    )
    return {"message": "Research shuru ho gayi"}


@router.post("/contacts/{company_id}")
def find_contacts(
    company_id      : int,
    db              : Session = Depends(get_db),
    current_user    : User    = Depends(get_current_user)
):
    """Ek company ke contacts dhundho."""
    return contact_finder.find_contacts(db, company_id)


@router.post("/contacts/all/pending")
def find_all_contacts(
    background_tasks: BackgroundTasks,
    db              : Session = Depends(get_db),
    current_user    : User    = Depends(get_current_user)
):
    """Sab companies ke contacts dhundho."""
    background_tasks.add_task(
        contact_finder.find_all_pending_contacts,
        db=db
    )
    return {"message": "Contact finding shuru ho gayi"}


@router.get("/contacts/{company_id}")
def get_contacts(
    company_id  : int,
    db          : Session = Depends(get_db),
    current_user: User    = Depends(get_current_user)
):
    """Company ke saved contacts lo."""
    contacts = db.query(Contact).filter(
        Contact.company_id == company_id
    ).order_by(Contact.priority).all()

    return {
        "contacts": [
            {
                "id"              : c.id,
                "name"            : c.name,
                "role"            : c.role,
                "email"           : c.email,
                "linkedin_url"    : c.linkedin_url,
                "confidence_score": c.confidence_score,
                "source"          : c.source,
                "priority"        : c.priority
            }
            for c in contacts
        ]
    }
@router.post("/resume/job/{job_id}")
def optimize_for_job(
    job_id      : int,
    db          : Session = Depends(get_db),
    current_user: User    = Depends(get_current_user)
):
    """Job ke liye resume optimize karo."""
    return resume_agent.optimize_resume_for_job(
        db      = db,
        user_id = current_user.id,
        job_id  = job_id
    )


@router.post("/resume/company/{company_id}")
def optimize_for_company(
    company_id  : int,
    db          : Session = Depends(get_db),
    current_user: User    = Depends(get_current_user)
):
    """Cold email company ke liye resume optimize karo."""
    return resume_agent.optimize_resume_for_company(
        db         = db,
        user_id    = current_user.id,
        company_id = company_id
    )