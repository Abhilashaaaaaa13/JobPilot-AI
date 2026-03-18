from typing import TypedDict, Annotated
import operator

class ResumeReview(TypedDict):
    """One resume review item.
    created by resume node.
    consumed by INTERRUPT 1."""

    id                  : str       # unique id — job_id or company_id
    type                : str       # "job" or "company"
    job_id              : int | None
    company_id          : int | None
    company_name        : str
    role                : str
    original_resume_path: str
    rewritten_resume_path: str
    ats_before          : float
    ats_after           : float
    improvement         : float
    changes_summary     : list[str]  # what changed
    decision            : str | None # "accept" / "reject" / None

class EmailReview(TypedDict):
    """One email review item.
    Created by email generator mode.
    consumed by INTERRUPT 2"""
    id              : str
    type            : str       # "job_email" or "cold_email"
    job_id          : int | None
    company_id      : int | None
    company_name    : str
    contact_name    : str
    contact_role    : str
    contact_email   : str | None
    subject         : str
    body            : str
    gap_identified  : str
    proposal        : str
    why_user_fits   : str
    resume_path     : str | None
    decision        : str | None  # "approve" / "edit" / "reject"
    edited_subject  : str | None  # if user edited
    edited_body     : str | None  # if user edited

class PipelineState(TypedDict):
    """Master state for the entire pipeline.
    
    Concept: Single Source of Truth
    Every node reads from here, writes to here.
    No node has its own hidden state.
    
    Annotated[list, operator.add] means:
    When multiple nodes write to same list,
    LangGraph merges them (add) instead of
    replacing. This enables parallel nodes
    to both write results without conflict."""

    #identity
    user_id     : int
    thread_id   : str

    #step tracking
    current_step: str
    # values: "scraping", "scoring", "researching",
    #         "finding_contacts", "optimizing_resumes",
    #         "generating_emails", "awaiting_resume_review",
    #         "awaiting_email_review", "sending", "done"
    errors : Annotated[list,operator.add]

    #scraping results
    jobs_scraped :Annotated[list,operator.add]
    companies_scraped :Annotated[list,operator.add]

    #after scroinf
    relevant_jobs : Annotated[list,operator.add]

    #after research+contacts
    researched_companies : Annotated[list, operator.add]
    contacts_found : Annotated[list,operator.add]

    #interrupt 1-resume review
    pending_resume_reviews : list[ResumeReview]
    approved_resume_ids : list[str]
    rejected_resume_ids :list[str]
    #rejected = original resume use hoga

    #interrupt 2-email review
    pending_email_reviews  : list[EmailReview]
    approved_email_ids     : list[str]
    rejected_email_ids     : list[str]

    #final result
    emails_sent : Annotated[list, operator.add]

    

