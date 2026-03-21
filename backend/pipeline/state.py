# backend/pipeline/state.py

from typing import TypedDict, Annotated, Optional
import operator


class ContactInfo(TypedDict):
    name    : str
    role    : str
    email   : Optional[str]
    verified: bool


class JobResult(TypedDict):
    title      : str
    company    : str
    location   : str
    stipend    : str
    description: str
    url        : str
    type       : str   # internship / job
    source     : str


class CompanyResult(TypedDict):
    name       : str
    website    : str
    one_liner  : str
    description: str
    funding    : str
    team_size  : str
    location   : str
    source     : str
    contacts   : list[ContactInfo]


class ResumeReview(TypedDict):
    id                   : str
    job_title            : str
    company              : str
    original_path        : str
    optimized_path       : str
    ats_before           : float
    ats_after            : float
    changes              : list[str]
    decision             : Optional[str]  # accept / reject


class EmailReview(TypedDict):
    id             : str
    company        : str
    contact_name   : str
    contact_role   : str
    contact_email  : Optional[str]
    subject        : str
    body           : str
    gap_identified : str
    proposal       : str
    why_user_fits  : str
    resume_path    : Optional[str]
    decision       : Optional[str]   # approve / edit / reject
    edited_subject : Optional[str]
    edited_body    : Optional[str]


# ─────────────────────────────────────────────
# TRACK A — Job Applications
# ─────────────────────────────────────────────

class TrackAState(TypedDict):
    user_id  : int
    thread_id: str
    prefs    : dict

    # Step 1 — Scraping
    current_step  : str
    errors        : Annotated[list, operator.add]

    # Step 2 — Scraped results
    scraped_jobs  : list[JobResult]

    # Step 3 — User selects
    selected_jobs : list[JobResult]

    # Step 4 — Resume optimization
    resume_reviews        : list[ResumeReview]
    approved_resume_ids   : list[str]
    rejected_resume_ids   : list[str]

    # Step 5 — Applications sent
    applications_sent: Annotated[list, operator.add]


# ─────────────────────────────────────────────
# TRACK B — Cold Outreach
# ─────────────────────────────────────────────

class TrackBState(TypedDict):
    user_id  : int
    thread_id: str
    prefs    : dict

    current_step: str
    errors      : Annotated[list, operator.add]

    # Step 1 — Scraped companies
    scraped_companies : list[CompanyResult]

    # Step 2 — User selects
    selected_companies: list[CompanyResult]

    # Step 3 — Resume optimization
    resume_reviews      : list[ResumeReview]
    approved_resume_ids : list[str]
    rejected_resume_ids : list[str]

    # Step 4 — Email generation
    email_reviews      : list[EmailReview]
    approved_email_ids : list[str]
    rejected_email_ids : list[str]

    # Step 5 — Emails sent
    emails_sent: Annotated[list, operator.add]