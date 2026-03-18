import uuid
from sqlalchemy.orm import Session
from backend.pipeline.state import PipelineState,ResumeReview,EmailReview
from backend.agents import (
    scraper_agent,scoring_agent,research_agent,contact_finder
    ,resume_agent,email_generator
)
from backend.models.job import Job
from backend.models.company import Company
from loguru import logger

#node 1 -scraper 
#runs both jo scraping and Company scraping

def scraper_node(state:PipelineState,db:Session)->dict:
    """Triggers scraper agent for all sources.
    
    Design decision — why one node for all sources?
    Scraper agent internally handles all sources.
    Splitting into multiple nodes would add complexity
    without benefit at this scale.
    
    Returns scraped job ids and company ids
    so next nodes know what to process."""
    logger.info(f"[Scraper Node] Starting for user {state['user_id']}")
    try:
        result = scraper_agent.run(
            db=db,
            user_id=state["user_id"]
        )
        #get ids of what was scraped
        jobs = db.query(Job).filter(
            Job.status == "new"
        ).all()
        companies = db.query(Company).filter(
            Company.research_done == False
        ).all()
        logger.info(
            f"[Scraper Node] Done — "
            f"{len(jobs)} jobs, {len(companies)} companies"
        )
        return {
             "current_step"    : "scoring",
            "jobs_scraped"    : [j.id for j in jobs],
            "companies_scraped": [c.id for c in companies],
        }
    except Exception as e:
        logger.error(f"[Scraper Node] Error:{e}")
        return {
            "current_step": "scoring",
            "errors"      : [f"Scraper failed: {str(e)}"]
        }
    
#node 2 scorer
#scorer all unscored job
def scorer_node(state:PipelineState,db:Session)->dict:
    """Runs scoring agent on all scraped jobs.
    
    Design decision — why after scraper and not parallel?
    Scorer needs jobs to exist in DB first.
    Sequential dependency — cannot parallelize.
    
    However, scoring itself uses local sentence-transformers
    so it's fast — no API calls needed here."""
    logger.info(f"[Scorer Node] Starting")
    try:
        result = scoring_agent.score_all_jobs(
            db      = db,
            user_id = state["user_id"]
        )
        #get relevant job ids
        relevant = db.query(Job).filter(
            Job.is_relevant == True
        ).all()
        logger.info(
            f"[Scorer Node] Done — "
            f"{len(relevant)} relevant jobs found"
        )
        return {
            "current_step": "researching",
            "relevant_jobs": [j.id for j in relevant],
        }
    except Exception as e:
        logger.error(f"[Scorer Node] Error: {e}")
        return {
            "current_step": "researching",
            "errors"      : [f"Scorer failed: {str(e)}"]
        }
    
#node 3A - research node(company track)
#node 3b - contact finder node(company track)
#these run parallel with each other after scraping is done

def research_node(state:PipelineState, db:Session)->dict:
    """Researches all unresearched companies.
    
    Concept: This node runs in parallel with scorer_node
    because they operate on different data.
    Scorer works on Jobs table.
    Research works on Companies table.
    No conflict — safe to parallelize.
    
    Uses DuckDuckGo + Tavily + Groq.
    Most expensive node in terms of API calls."""
    logger.info(f"[Research Node] Starting")
    try:
        result = research_agent.research_all_pending(db)

        researched = db.query(Company).filter(
            Company.research_done == True
        ).all()

        logger.info(
            f"[Research Node] Done — "
            f"{len(researched)} companies researched"
        )

        return {
            "researched_companies": [c.id for c in researched],
        }
    except Exception as e:
        logger.error(f"[Research Node] Error: {e}")
        return {
            "errors": [f"Research failed: {str(e)}"]
        }
    
def contact_finder_node(state: PipelineState, db:Session)->dict:
    """Finds contacts for all researched companies.
    
    Design decision — why after research and not parallel?
    Contact finder uses company summary for context
    when extracting names via Groq.
    Needs research to be done first.
    
    Within this node — contacts for multiple companies
    can be found sequentially without blocking the
    rest of the pipeline."""
    logger.info(f"[Contact Finder Node] Starting")
    try:
        result = contact_finder.find_all_pending_contacts(db)

        logger.info(
            f"[Contact Finder Node] Done — "
            f"{result.get('total_contacts_found', 0)} contacts found"
        )

        return {
            "contacts_found": [result.get("total_contacts_found", 0)],
        }
    except Exception as e:
        logger.error(f"[Contact Finder Node] Error: {e}")
        return {
            "errors": [f"Contact finder failed: {str(e)}"]
        }
    
#node 4-resume optimizer
#creates optimized resume for all releavnt  jobs n researched companies

def resume_optimizer_node(
        state: PipelineState,
        db : Session
)->dict:
    """Optimizes resume for every relevant job and company.
    
    Concept: Batch processing
    Instead of processing one at a time,
    we collect all results first, then
    present them to user at once in INTERRUPT 1.
    
    This is better UX — user reviews everything
    in one sitting instead of being interrupted
    for each individual resume.
    
    Why track changes_summary?
    User needs to understand what changed
    to make an informed accept/reject decision.
    Blind changes = user loses trust in system."""
    logger.info(f"[Resume Optimizer Node] Starting")

    pending_reviews = []
    #process relevant jobs
    for job_id in state.get("relevant_jobs",[]):
        try:
            result = resume_agent.optimize_resume_for_job(
                db      = db,
                user_id = state["user_id"],
                job_id  = job_id
            )
            if result.get("error"):
                continue
            job = db.query(Job).filter(Job.id == job_id).first()
            review: ResumeReview = {
                "id"                   : f"job_{job_id}",
                "type"                 : "job",
                "job_id"               : job_id,
                "company_id"           : None,
                "company_name"         : job.company_name if job else "",
                "role"                 : job.title if job else "",
                "original_resume_path" : result.get("original_path", ""),
                "rewritten_resume_path": result.get("resume_path", ""),
                "ats_before"           : result.get("ats_before", 0),
                "ats_after"            : result.get("ats_after", 0),
                "improvement"          : result.get("improvement", 0),
                "changes_summary"      : result.get("missing_keywords", []),
                "decision"             : None
            }
            pending_reviews.append(review)

        except Exception as e:
            logger.error(f"Resume opt failed job {job_id}: {e}")
            continue
    
    #process cold email companies
    for company_id in state.get("researched_companies", []):
        try:
            result = resume_agent.optimize_resume_for_company(
                db         = db,
                user_id    = state["user_id"],
                company_id = company_id
            )
            if result.get("error"):
                continue
            company = db.query(Company).filter(
                Company.id == company_id
            ).first()
            review: ResumeReview = {
                "id"                   : f"company_{company_id}",
                "type"                 : "company",
                "job_id"               : None,
                "company_id"           : company_id,
                "company_name"         : company.name if company else "",
                "role"                 : "Cold Email",
                "original_resume_path" : result.get("original_path", ""),
                "rewritten_resume_path": result.get("resume_path", ""),
                "ats_before"           : result.get("ats_before", 0),
                "ats_after"            : result.get("ats_after", 0),
                "improvement"          : result.get("improvement", 0),
                "changes_summary"      : result.get("missing_keywords", []),
                "decision"             : None
            }
            pending_reviews.append(review)
        except Exception as e:
            logger.error(f"Resume opt failed company {company_id}: {e}")
            continue
    
    logger.info(
        f"[Resume Optimizer Node] Done — "
        f"{len(pending_reviews)} resumes ready for review"
    )
    return {
        "current_step"         : "awaiting_resume_review",
        "pending_resume_reviews": pending_reviews,
    }

#node 5-email generator
#runs after interrupt 1(resume approval)
#generates email using approved resumes

def email_generator_node(
    state: PipelineState,
    db   : Session
) -> dict:
    """
    Generates personalized emails for all approved resumes.
    
    Concept: State-driven processing
    This node reads approved_resume_ids from state
    to know which items to process.
    Items in rejected_resume_ids use original resume.
    
    Design decision — why generate emails in bulk?
    Same reason as resume optimizer — batch UX.
    User reviews all emails at once in INTERRUPT 2.
    """
    logger.info(f"[Email Generator Node] Starting")

    pending_email_reviews = []
    approved_ids  = set(state.get("approved_resume_ids", []))
    rejected_ids  = set(state.get("rejected_resume_ids", []))
    all_reviews   = state.get("pending_resume_reviews", [])

    for review in all_reviews:
        review_id = review["id"]

        # Determine which resume to use
        if review_id in rejected_ids:
            resume_path = review["original_resume_path"]
        else:
            resume_path = review["rewritten_resume_path"]

        try:
            if review["type"] == "job" and review.get("job_id"):
                result = email_generator.generate_job_email(
                    db      = db,
                    user_id = state["user_id"],
                    job_id  = review["job_id"]
                )
            else:
                result = email_generator.generate_cold_email(
                    db         = db,
                    user_id    = state["user_id"],
                    company_id = review["company_id"]
                )

            if result.get("error"):
                continue

            email_review: EmailReview = {
                "id"            : f"email_{review_id}",
                "type"          : result.get("type", ""),
                "job_id"        : review.get("job_id"),
                "company_id"    : review.get("company_id"),
                "company_name"  : review["company_name"],
                "contact_name"  : result.get("contact_name", ""),
                "contact_role"  : result.get("contact_role", ""),
                "contact_email" : result.get("contact_email"),
                "subject"       : result.get("subject", ""),
                "body"          : result.get("body", ""),
                "gap_identified": result.get("gap_identified", ""),
                "proposal"      : result.get("proposal", ""),
                "why_user_fits" : result.get("why_user_fits", ""),
                "resume_path"   : resume_path,
                "decision"      : None,
                "edited_subject": None,
                "edited_body"   : None,
            }
            pending_email_reviews.append(email_review)

        except Exception as e:
            logger.error(f"Email gen failed {review_id}: {e}")
            continue

    logger.info(
        f"[Email Generator Node] Done — "
        f"{len(pending_email_reviews)} emails ready for review"
    )

    return {
        "current_step"         : "awaiting_email_review",
        "pending_email_reviews": pending_email_reviews,
    }



# NODE 6 — Email Sender
# Runs after INTERRUPT 2 (email approval)
def email_sender_node(
    state: PipelineState,
    db   : Session
) -> dict:
    """
    Sends all approved emails.
    
    Concept: Final action node
    This is the only node with real-world side effects
    that cannot be undone (sending emails).
    All previous nodes are reversible/safe.
    This is why human approval before this is critical.
    
    Design decision — edited emails:
    If user edited subject/body, use edited version.
    edited_subject/body take priority over original.
    """
    from backend.agents.email_sender import send_and_log

    logger.info(f"[Email Sender Node] Starting")

    approved_ids   = set(state.get("approved_email_ids", []))
    email_reviews  = state.get("pending_email_reviews", [])
    sent_emails    = []

    for review in email_reviews:
        if review["id"] not in approved_ids:
            continue

        # Use edited version if user edited
        subject = review.get("edited_subject") or review["subject"]
        body    = review.get("edited_body")    or review["body"]

        try:
            result = send_and_log(
                db         = db,
                user_id    = state["user_id"],
                to_email   = review["contact_email"],
                subject    = subject,
                body       = body,
                resume_path= review.get("resume_path"),
                job_id     = review.get("job_id"),
                company_id = review.get("company_id"),
            )

            if result.get("success"):
                sent_emails.append({
                    "company"   : review["company_name"],
                    "contact"   : review["contact_name"],
                    "email"     : review["contact_email"],
                    "sent_at"   : str(__import__("datetime").datetime.utcnow()),
                })
                logger.info(
                    f"  Sent to {review['contact_name']} "
                    f"@ {review['company_name']}"
                )

        except Exception as e:
            logger.error(f"Send failed {review['id']}: {e}")
            continue

    logger.info(
        f"[Email Sender Node] Done — "
        f"{len(sent_emails)} emails sent"
    )

    return {
        "current_step": "done",
        "emails_sent" : sent_emails,
    }
