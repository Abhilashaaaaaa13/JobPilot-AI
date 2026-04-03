# backend/pipeline/nodes.py

from loguru import logger

from backend.pipeline.state import (
    TrackBState,
    EmailReview
)
from backend.agents import (
    scraper_agent,
    email_generator,
)
from backend.agents.email_sender   import send_and_log
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
    """
    logger.info("[Research] Starting")

    selected = state.get("selected_companies", [])
    if not selected:
        return {
            "current_step": "awaiting_email_review",
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
            enriched.append(company)
            continue

    return {
        "current_step"      : "awaiting_email_review",
        "selected_companies": enriched
    }


def generate_emails_node(state: TrackBState) -> dict:
    """
    Cold emails generate karo.
    Resume path DB se seedha liya jata hai — no optimization step.
    """
    logger.info("[Email Gen] Starting")

    # Resume path — DB se original resume lo
    from backend.database import SessionLocal
    from backend.models.user import UserProfile

    db      = SessionLocal()
    prof    = db.query(UserProfile).filter(
        UserProfile.user_id == state["user_id"]
    ).first()
    resume_path = prof.resume_path if prof else None
    db.close()

    selected      = state.get("selected_companies", [])
    email_reviews = []

    for company in selected:
        contacts = company.get("contacts", [])
        contact  = next(
            (c for c in contacts if c.get("email")), None
        )

        if not contact:
            logger.warning(f"  ⚠️ No contact for {company['name']}")
            continue

        try:
            result = email_generator.generate_cold_email(
                user_id          = state["user_id"],
                company          = company["name"],
                description      = company.get("company_summary") or company.get("description", ""),
                one_liner        = company.get("one_liner", ""),
                contact          = contact,
                ai_hook          = company.get("ai_hook",          ""),
                recent_highlight = company.get("recent_highlight", ""),
                tech_stack       = company.get("tech_stack",       []),
            )

            if result.get("error"):
                logger.warning(f"  ⚠️ Email gen error for {company['name']}: {result['error']}")
                continue

            review_id = f"co_{company['name'][:20]}"

            email_review: EmailReview = {
                "id"            : f"email_{review_id}",
                "company"       : company["name"],
                "contact_name"  : contact.get("name",  ""),
                "contact_role"  : contact.get("role",  ""),
                "contact_email" : contact.get("email", ""),
                "subject"       : result["subject"],
                "body"          : result["body"],
                "gap_identified": result.get("gap",      ""),
                "proposal"      : result.get("proposal", ""),
                "why_user_fits" : result.get("why_fits", ""),
                "resume_path"   : resume_path,
                "decision"      : None,
                "edited_subject": None,
                "edited_body"   : None,
            }
            email_reviews.append(email_review)
            logger.info(
                f"  ✅ Email ready: {company['name']} "
                f"→ {contact.get('name', '')}"
            )

        except Exception as e:
            logger.error(f"Email gen error {company['name']}: {e}")
            continue

    return {
        "current_step" : "awaiting_email_review",
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