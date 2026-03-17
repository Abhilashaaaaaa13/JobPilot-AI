# backend/routers/dashboard.py

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from backend.database import get_db
from backend.models.user import User
from backend.models.application import Application
from backend.models.reply import Reply
from backend.models.job import Job
from backend.models.company import Company
from backend.models.contact import Contact
from backend.dependencies import get_current_user

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
def get_stats(
    db          : Session = Depends(get_db),
    current_user: User    = Depends(get_current_user)
):
    """
    User ka complete stats overview.
    Dashboard pe dikhega.
    """
    user_id = current_user.id

    # Total applications
    total = db.query(Application).filter(
        Application.user_id == user_id
    ).count()

    # Status wise count
    statuses = [
        "email_sent",
        "follow_up_1_sent",
        "follow_up_2_sent",
        "replied_positive",
        "replied_negative",
        "interview_scheduled",
        "ghosted",
        "pending"
    ]

    status_counts = {}
    for status in statuses:
        count = db.query(Application).filter(
            Application.user_id == user_id,
            Application.status  == status
        ).count()
        status_counts[status] = count

    # Reply rate calculate karo
    replied = (
        status_counts.get("replied_positive", 0) +
        status_counts.get("replied_negative", 0) +
        status_counts.get("interview_scheduled", 0)
    )
    reply_rate = round(
        (replied / total * 100), 1
    ) if total > 0 else 0

    # Interview rate
    interviews = status_counts.get("interview_scheduled", 0)
    interview_rate = round(
        (interviews / total * 100), 1
    ) if total > 0 else 0

    # Source wise breakdown
    # Job applications
    job_apps = db.query(
        Job.source,
        func.count(Application.id).label("count")
    ).join(
        Application,
        Application.job_id == Job.id
    ).filter(
        Application.user_id == user_id
    ).group_by(Job.source).all()

    # Cold email applications
    company_apps = db.query(
        Company.source,
        func.count(Application.id).label("count")
    ).join(
        Application,
        Application.company_id == Company.id
    ).filter(
        Application.user_id == user_id
    ).group_by(Company.source).all()

    source_breakdown = {}
    for source, count in job_apps:
        source_breakdown[source] = count
    for source, count in company_apps:
        key = f"{source} (cold)"
        source_breakdown[key] = count

    # ATS improvement average
    ats_apps = db.query(Application).filter(
        Application.user_id     == user_id,
        Application.ats_score_before != None,
        Application.ats_score_after  != None
    ).all()

    avg_ats_improvement = 0
    if ats_apps:
        improvements = [
            a.ats_score_after - a.ats_score_before
            for a in ats_apps
        ]
        avg_ats_improvement = round(
            sum(improvements) / len(improvements), 1
        )

    # Recent 5 applications
    recent = db.query(Application).filter(
        Application.user_id == user_id
    ).order_by(
        Application.created_at.desc()
    ).limit(5).all()

    recent_list = []
    for app in recent:
        name = ""
        if app.job_id:
            job  = db.query(Job).filter(Job.id == app.job_id).first()
            name = f"{job.title} @ {job.company_name}" if job else ""
        elif app.company_id:
            co   = db.query(Company).filter(Company.id == app.company_id).first()
            name = f"Cold Email → {co.name}" if co else ""

        recent_list.append({
            "id"        : app.id,
            "name"      : name,
            "status"    : app.status,
            "sent_date" : str(app.sent_date)[:10] if app.sent_date else "",
        })

    return {
        "total_applications"   : total,
        "status_counts"        : status_counts,
        "reply_rate"           : reply_rate,
        "interview_rate"       : interview_rate,
        "source_breakdown"     : source_breakdown,
        "avg_ats_improvement"  : avg_ats_improvement,
        "recent_applications"  : recent_list,
    }


@router.get("/applications")
def get_applications(
    status      : str = None,
    skip        : int = 0,
    limit       : int = 20,
    db          : Session = Depends(get_db),
    current_user: User    = Depends(get_current_user)
):
    """Sab applications list karo — filter optional."""
    query = db.query(Application).filter(
        Application.user_id == current_user.id
    )

    if status:
        query = query.filter(Application.status == status)

    total = query.count()
    apps  = query.order_by(
        Application.created_at.desc()
    ).offset(skip).limit(limit).all()

    result = []
    for app in apps:
        # Company/Job name nikalo
        name    = ""
        website = ""

        if app.job_id:
            job     = db.query(Job).filter(Job.id == app.job_id).first()
            name    = f"{job.title} @ {job.company_name}" if job else ""
            website = job.apply_url if job else ""
        elif app.company_id:
            co      = db.query(Company).filter(
                Company.id == app.company_id
            ).first()
            name    = co.name    if co else ""
            website = co.website if co else ""

        # Contact info
        contact_name  = ""
        contact_email = ""
        if app.contact_id:
            contact       = db.query(Contact).filter(
                Contact.id == app.contact_id
            ).first()
            contact_name  = contact.name  if contact else ""
            contact_email = contact.email if contact else ""

        # Reply info
        reply = db.query(Reply).filter(
            Reply.application_id == app.id
        ).first()

        result.append({
            "id"              : app.id,
            "name"            : name,
            "website"         : website,
            "contact_name"    : contact_name,
            "contact_email"   : contact_email,
            "subject"         : app.email_subject,
            "status"          : app.status,
            "sent_date"       : str(app.sent_date)[:10] if app.sent_date else "",
            "follow_up_count" : app.follow_up_count,
            "ats_before"      : app.ats_score_before,
            "ats_after"       : app.ats_score_after,
            "reply"           : {
                "classification": reply.classification,
                "next_action"   : reply.next_action,
                "received_date" : str(reply.received_date)[:10]
            } if reply else None
        })

    return {"total": total, "applications": result}


@router.patch("/applications/{app_id}/status")
def update_status(
    app_id      : int,
    status      : str,
    db          : Session = Depends(get_db),
    current_user: User    = Depends(get_current_user)
):
    """User manually status update kare."""
    app = db.query(Application).filter(
        Application.id      == app_id,
        Application.user_id == current_user.id
    ).first()

    if not app:
        from fastapi import HTTPException
        raise HTTPException(404, "Application nahi mili")

    app.status = status
    db.commit()

    return {"message": "Status updated", "status": status}