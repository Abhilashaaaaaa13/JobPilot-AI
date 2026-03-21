# backend/pipeline/nodes.py

from functools import partial
from loguru import logger

from backend.pipeline.state import (
    TrackAState, TrackBState,
    ResumeReview, EmailReview
)
from backend.agents import (
    scraper_agent,
    resume_agent,
    email_generator,
)
from backend.agents.email_sender import send_and_log


# ═════════════════════════════════════════════
# TRACK A NODES
# ═════════════════════════════════════════════

def scrape_jobs_node(state: TrackAState) -> dict:
    """
    Fresh scrape karo — no DB.
    User prefs se domain + type lo.
    """
    logger.info(f"[Scrape Jobs] user {state['user_id']}")

    try:
        result = scraper_agent.run(
            user_id = state["user_id"],
            prefs   = state["prefs"]
        )

        jobs = result.get("track_a", [])
        logger.info(f"[Scrape Jobs] {len(jobs)} jobs found")

        return {
            "current_step": "awaiting_job_selection",
            "scraped_jobs": jobs,
            "errors"      : []
        }

    except Exception as e:
        logger.error(f"[Scrape Jobs] Error: {e}")
        return {
            "current_step": "awaiting_job_selection",
            "scraped_jobs": [],
            "errors"      : [str(e)]
        }


def optimize_resumes_a_node(state: TrackAState) -> dict:
    """
    Selected jobs ke liye resume optimize karo.
    """
    logger.info(f"[Resume A] Starting")

    selected = state.get("selected_jobs", [])
    if not selected:
        return {
            "current_step" : "awaiting_resume_review",
            "resume_reviews": [],
            "errors"        : ["No jobs selected"]
        }

    reviews = []

    for job in selected:
        try:
            result = resume_agent.optimize_for_job(
                user_id  = state["user_id"],
                job_title= job["title"],
                company  = job["company"],
                job_desc = job["description"]
            )

            if result.get("error"):
                continue

            review: ResumeReview = {
                "id"            : f"job_{job['url'][-20:]}",
                "job_title"     : job["title"],
                "company"       : job["company"],
                "original_path" : result["original_path"],
                "optimized_path": result["optimized_path"],
                "ats_before"    : result["ats_before"],
                "ats_after"     : result["ats_after"],
                "changes"       : result["changes"],
                "decision"      : None
            }
            reviews.append(review)
            logger.info(
                f"  ✅ {job['title']} @ {job['company']} "
                f"ATS: {result['ats_before']}→{result['ats_after']}"
            )

        except Exception as e:
            logger.error(f"Resume opt error: {e}")
            continue

    return {
        "current_step" : "awaiting_resume_review",
        "resume_reviews": reviews
    }


def apply_node(state: TrackAState) -> dict:
    """
    Approved resumes ke liye apply karo.
    Email send karo ya link save karo.
    """
    logger.info("[Apply] Starting")

    approved_ids  = set(state.get("approved_resume_ids", []))
    reviews       = state.get("resume_reviews", [])
    selected_jobs = state.get("selected_jobs", [])
    applications  = []

    for job in selected_jobs:
        job_id = f"job_{job['url'][-20:]}"

        # Resume path decide karo
        review = next(
            (r for r in reviews if r["id"] == job_id), None
        )
        if review:
            resume_path = (
                review["optimized_path"]
                if job_id in approved_ids
                else review["original_path"]
            )
        else:
            resume_path = None

        try:
            email_data = email_generator.generate_job_email(
                user_id  = state["user_id"],
                job_title= job["title"],
                company  = job["company"],
                job_desc = job["description"]
            )

            if not email_data.get("contact_email"):
                # No email — save link for manual apply
                applications.append({
                    "company"   : job["company"],
                    "title"     : job["title"],
                    "apply_url" : job["url"],
                    "type"      : "manual",
                    "status"    : "link_saved"
                })
                logger.info(
                    f"  🔗 Manual: {job['title']} @ {job['company']}"
                )
                continue

            result = send_and_log(
                user_id     = state["user_id"],
                to_email    = email_data["contact_email"],
                subject     = email_data["subject"],
                body        = email_data["body"],
                resume_path = resume_path
            )

            if result.get("success"):
                applications.append({
                    "company": job["company"],
                    "title"  : job["title"],
                    "email"  : email_data["contact_email"],
                    "type"   : "email_sent",
                    "status" : "sent"
                })
                logger.info(
                    f"  ✅ Sent: {job['title']} @ {job['company']}"
                )

        except Exception as e:
            logger.error(f"Apply error: {e}")
            continue

    return {
        "current_step"    : "done",
        "applications_sent": applications
    }


# ═════════════════════════════════════════════
# TRACK B NODES
# ═════════════════════════════════════════════

def scrape_companies_node(state: TrackBState) -> dict:
    """
    Fresh scrape — sari companies.
    No DB — directly return.
    """
    logger.info(f"[Scrape Companies] user {state['user_id']}")

    try:
        result    = scraper_agent.run(
            user_id = state["user_id"],
            prefs   = state["prefs"]
        )
        companies = result.get("track_b", [])
        logger.info(
            f"[Scrape Companies] {len(companies)} found"
        )

        return {
            "current_step"    : "awaiting_company_selection",
            "scraped_companies": companies,
            "errors"          : []
        }

    except Exception as e:
        logger.error(f"[Scrape Companies] Error: {e}")
        return {
            "current_step"    : "awaiting_company_selection",
            "scraped_companies": [],
            "errors"          : [str(e)]
        }


def optimize_resumes_b_node(state: TrackBState) -> dict:
    """
    Selected companies ke liye resume optimize karo.
    Company description use karo JD ki jagah.
    """
    logger.info("[Resume B] Starting")

    selected = state.get("selected_companies", [])
    if not selected:
        return {
            "current_step" : "awaiting_resume_review",
            "resume_reviews": [],
            "errors"        : ["No companies selected"]
        }

    reviews = []

    for company in selected:
        try:
            result = resume_agent.optimize_for_company(
                user_id    = state["user_id"],
                company    = company["name"],
                description= company["description"]
            )

            if result.get("error"):
                continue

            review: ResumeReview = {
                "id"            : f"co_{company['name'][:20]}",
                "job_title"     : "Cold Outreach",
                "company"       : company["name"],
                "original_path" : result["original_path"],
                "optimized_path": result["optimized_path"],
                "ats_before"    : result["ats_before"],
                "ats_after"     : result["ats_after"],
                "changes"       : result["changes"],
                "decision"      : None
            }
            reviews.append(review)
            logger.info(f"  ✅ Resume ready: {company['name']}")

        except Exception as e:
            logger.error(f"Resume B error: {e}")
            continue

    return {
        "current_step" : "awaiting_resume_review",
        "resume_reviews": reviews
    }


def generate_emails_node(state: TrackBState) -> dict:
    """
    Approved resumes ke liye cold emails generate karo.
    Gap + proposal angle.
    """
    logger.info("[Email Gen] Starting")

    approved_ids = set(state.get("approved_resume_ids", []))
    reviews      = state.get("resume_reviews", [])
    selected     = state.get("selected_companies", [])
    email_reviews= []

    for company in selected:
        review_id = f"co_{company['name'][:20]}"
        review    = next(
            (r for r in reviews if r["id"] == review_id), None
        )

        resume_path = None
        if review:
            resume_path = (
                review["optimized_path"]
                if review_id in approved_ids
                else review["original_path"]
            )

        # Best contact dhundho
        contacts = company.get("contacts", [])
        contact  = next(
            (c for c in contacts if c.get("email")), None
        )

        if not contact:
            logger.warning(
                f"  ⚠️ No contact for {company['name']}"
            )
            continue

        try:
            result = email_generator.generate_cold_email(
                user_id    = state["user_id"],
                company    = company["name"],
                description= company["description"],
                one_liner  = company["one_liner"],
                contact    = contact
            )

            if result.get("error"):
                continue

            email_review: EmailReview = {
                "id"            : f"email_{review_id}",
                "company"       : company["name"],
                "contact_name"  : contact["name"],
                "contact_role"  : contact["role"],
                "contact_email" : contact["email"],
                "subject"       : result["subject"],
                "body"          : result["body"],
                "gap_identified": result["gap"],
                "proposal"      : result["proposal"],
                "why_user_fits" : result["why_fits"],
                "resume_path"   : resume_path,
                "decision"      : None,
                "edited_subject": None,
                "edited_body"   : None,
            }
            email_reviews.append(email_review)
            logger.info(
                f"  ✅ Email ready: {company['name']} "
                f"→ {contact['name']}"
            )

        except Exception as e:
            logger.error(f"Email gen error: {e}")
            continue

    return {
        "current_step": "awaiting_email_review",
        "email_reviews": email_reviews
    }


def send_emails_node(state: TrackBState) -> dict:
    """
    Approved emails bhejo.
    """
    logger.info("[Send Emails] Starting")

    approved_ids  = set(state.get("approved_email_ids", []))
    email_reviews = state.get("email_reviews", [])
    sent          = []

    for review in email_reviews:
        if review["id"] not in approved_ids:
            continue

        subject = review.get("edited_subject") or review["subject"]
        body    = review.get("edited_body")    or review["body"]

        if not review.get("contact_email"):
            continue

        try:
            result = send_and_log(
                user_id     = state["user_id"],
                to_email    = review["contact_email"],
                subject     = subject,
                body        = body,
                resume_path = review.get("resume_path")
            )

            if result.get("success"):
                sent.append({
                    "company"     : review["company"],
                    "contact"     : review["contact_name"],
                    "contact_role": review["contact_role"],
                    "email"       : review["contact_email"],
                })
                logger.info(
                    f"  ✅ Sent: {review['company']} "
                    f"→ {review['contact_name']}"
                )

        except Exception as e:
            logger.error(f"Send error: {e}")
            continue

    return {
        "current_step": "done",
        "emails_sent" : sent
    }