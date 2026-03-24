# backend/pipeline/nodes.py

from loguru import logger

from backend.pipeline.state import (
    TrackBState,
    ResumeReview, EmailReview
)
from backend.agents import (
    scraper_agent,
    resume_agent,
    email_generator,
)
from backend.agents.email_sender  import send_and_log
from backend.agents.research_agent import research_company


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
        logger.info(f"[Scrape Companies] {len(companies)} found")

        return {
            "current_step"     : "awaiting_company_selection",
            "scraped_companies": companies,
            "errors"           : []
        }

    except Exception as e:
        logger.error(f"[Scrape Companies] Error: {e}")
        return {
            "current_step"     : "awaiting_company_selection",
            "scraped_companies": [],
            "errors"           : [str(e)]
        }


def research_companies_node(state: TrackBState) -> dict:
    """
    Selected companies ko research karo — website scrape,
    news search, Groq summary — taaki email personalized ho.
    Runs BEFORE resume optimization & email generation.
    """
    logger.info("[Research] Starting")

    selected = state.get("selected_companies", [])
    if not selected:
        return {
            "current_step": "awaiting_resume_review",
            "errors"      : ["No companies selected"]
        }

    enriched = []

    for company in selected:
        try:
            research = research_company(
                company_name = company["name"],
                website      = company.get("website", ""),
                description  = company.get("description", "")
            )

            # Merge research data into company dict
            enriched_company = {
                **company,
                "company_summary" : research.get("company_summary",  company.get("description", "")),
                "recent_highlight": research.get("recent_highlight", ""),
                "ai_hook"         : research.get("ai_hook",          ""),
                "tech_stack"      : research.get("tech_stack",       []),
                "ai_related"      : research.get("ai_related",       False),
            }
            enriched.append(enriched_company)
            logger.info(f"  ✅ Researched: {company['name']}")

        except Exception as e:
            logger.error(f"Research error {company['name']}: {e}")
            enriched.append(company)   # push original if research fails
            continue

    return {
        "current_step"     : "awaiting_resume_review",
        "selected_companies": enriched
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
                user_id     = state["user_id"],
                company     = company["name"],
                description = company.get("company_summary") or company["description"]
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
            logger.info(
                f"  ✅ Resume ready: {company['name']} "
                f"ATS: {result['ats_before']}→{result['ats_after']}"
            )

        except Exception as e:
            logger.error(f"Resume B error: {e}")
            continue

    return {
        "current_step" : "awaiting_resume_review",
        "resume_reviews": reviews
    }


def generate_emails_node(state: TrackBState) -> dict:
    """
    Cold emails generate karo.
    BUG FIX: agar approved_resume_ids empty hai (interrupt skip hua)
    to optimized resume auto-use karo — default to best version.
    """
    logger.info("[Email Gen] Starting")

    approved_ids  = set(state.get("approved_resume_ids", []))
    reviews       = state.get("resume_reviews", [])
    selected      = state.get("selected_companies", [])
    email_reviews = []

    for company in selected:
        review_id = f"co_{company['name'][:20]}"
        review    = next(
            (r for r in reviews if r["id"] == review_id), None
        )

        resume_path = None
        if review:
            # FIX: agar approved_ids empty → auto-approve → use optimized
            use_optimized = (
                not approved_ids               # interrupt skip hua
                or review_id in approved_ids   # user ne explicitly approve kiya
            )
            resume_path = (
                review["optimized_path"]
                if use_optimized
                else review["original_path"]
            )

        # Best contact dhundho
        contacts = company.get("contacts", [])
        contact  = next(
            (c for c in contacts if c.get("email")), None
        )

        if not contact:
            logger.warning(f"  ⚠️ No contact for {company['name']}")
            continue

        try:
            result = email_generator.generate_cold_email(
                user_id     = state["user_id"],
                company     = company["name"],
                description = company.get("company_summary") or company["description"],
                one_liner   = company.get("one_liner", ""),
                contact     = contact,
                # Pass research extras for personalisation
                ai_hook          = company.get("ai_hook",          ""),
                recent_highlight = company.get("recent_highlight", ""),
                tech_stack       = company.get("tech_stack",       []),
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
                "gap_identified": result.get("gap",       ""),
                "proposal"      : result.get("proposal",  ""),
                "why_user_fits" : result.get("why_fits",  ""),
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
                resume_path = review.get("resume_path"),
                company     = review["company"],
                contact     = review["contact_name"],
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