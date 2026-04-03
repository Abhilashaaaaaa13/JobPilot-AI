# backend/pipeline/state.py

from typing import TypedDict, Annotated, Optional
import operator


# ─────────────────────────────────────────────
# SHARED TYPES
# ─────────────────────────────────────────────

class ContactInfo(TypedDict):
    name    : str
    role    : str
    email   : Optional[str]
    verified: bool


class CompanyResult(TypedDict):
    name             : str
    website          : str
    one_liner        : str
    description      : str
    funding          : str
    team_size        : str
    location         : str
    source           : str
    contacts         : list[ContactInfo]
    # Research-enriched fields (populated by research_companies_node)
    company_summary  : Optional[str]
    recent_highlight : Optional[str]
    ai_hook          : Optional[str]
    tech_stack       : Optional[list[str]]
    ai_related       : Optional[bool]





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

    # Step 2 — User selects (research enrichment happens after this)
    selected_companies: list[CompanyResult]

    

    # Step 4 — Email generation
    email_reviews      : list[EmailReview]
    approved_email_ids : list[str]
    rejected_email_ids : list[str]

    # Step 5 — Emails sent
    emails_sent: Annotated[list, operator.add]

    # Global feed — new startups (populated by scheduler, not pipeline)
    new_companies_feed : list[CompanyResult]