# backend/utils/sheets_tracker.py
# Google Sheets mein cold outreach track karo
# Job Applications tab removed — Track A dropped

import os
import json
from datetime import datetime
from loguru   import logger
from dotenv   import load_dotenv
load_dotenv()

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False
    logger.warning("gspread not installed — Sheets tracking disabled")

SHEETS_ID            = os.getenv("GOOGLE_SHEETS_ID",            "")
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "credentials.json")

TAB_COLD_OUTREACH = "Cold Outreach"
TAB_FOLLOWUPS     = "Follow Ups"


# ─────────────────────────────────────────────
# CLIENT
# ─────────────────────────────────────────────

def get_sheets_client():
    if not GSPREAD_AVAILABLE:
        logger.error("gspread library not available")
        return None

    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds  = Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE,
            scopes=scopes
        )
        return gspread.authorize(creds)

    except Exception as e:
        logger.error(f"Sheets client error: {e}", exc_info=True)
        return None


# ─────────────────────────────────────────────
# GET OR CREATE WORKSHEET
# ─────────────────────────────────────────────

def get_or_create_sheet(client, tab_name: str):
    try:
        spreadsheet = client.open_by_key(SHEETS_ID)

        try:
            return spreadsheet.worksheet(tab_name)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(
                title=tab_name,
                rows=1000,
                cols=20
            )
            headers = _get_headers(tab_name)
            if headers:
                worksheet.append_row(headers)
            logger.info(f"  📋 Created new sheet tab: {tab_name}")
            return worksheet

    except Exception as e:
        logger.error(f"Sheet get/create error: {e}", exc_info=True)
        return None


# ─────────────────────────────────────────────
# HEADERS
# ─────────────────────────────────────────────

def _get_headers(tab_name: str) -> list:
    if tab_name == TAB_COLD_OUTREACH:
        return [
            "Date Sent",
            "Company",
            "Website",
            "Contact Name",
            "Contact Role",
            "Email",
            "Subject",
            "Gap Identified",
            "Proposal",
            "Status",
            "Reply Date",
            "Reply Preview",
            "Follow Up 1",
            "Follow Up 2",
            "Notes"
        ]
    elif tab_name == TAB_FOLLOWUPS:
        return [
            "Date",
            "Company",
            "Contact Email",
            "Original Subject",
            "Followup Subject",
            "New Value Added",
            "Status"
        ]
    return []


# ─────────────────────────────────────────────
# LOG COLD OUTREACH EMAIL
# ─────────────────────────────────────────────

def log_cold_email(
    user_id      : int,
    company      : str,
    website      : str,
    contact_name : str,
    contact_role : str,
    contact_email: str,
    subject      : str,
    gap          : str,
    proposal     : str
) -> bool:
    if not SHEETS_ID:
        logger.warning("GOOGLE_SHEETS_ID missing — skip")
        return False

    client = get_sheets_client()
    if not client:
        return False

    try:
        ws = get_or_create_sheet(client, TAB_COLD_OUTREACH)
        if not ws:
            return False

        ws.append_row([
            datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
            company,
            website,
            contact_name,
            contact_role,
            contact_email,
            subject,
            gap[:100]      if gap      else "",
            proposal[:100] if proposal else "",
            "Sent",
            "",  # Reply Date
            "",  # Reply Preview
            "",  # Follow Up 1
            "",  # Follow Up 2
            ""   # Notes
        ])

        logger.info(f"  📊 Sheet updated: {company} cold email")
        return True

    except Exception as e:
        logger.error(f"Sheet log cold email error: {e}", exc_info=True)
        return False


# ─────────────────────────────────────────────
# UPDATE REPLY STATUS
# ─────────────────────────────────────────────

def update_reply_status(
    user_id      : int,
    contact_email: str,
    reply_body   : str,
    tab_name     : str = TAB_COLD_OUTREACH
) -> bool:
    if not SHEETS_ID:
        return False

    client = get_sheets_client()
    if not client:
        return False

    try:
        ws = get_or_create_sheet(client, tab_name)
        if not ws:
            return False

        rows = ws.get_all_values()
        if not rows:
            return False

        headers        = rows[0]
        email_col      = None
        status_col     = None
        reply_date_col = None
        reply_prev_col = None

        for i, h in enumerate(headers):
            if h in ("Email", "Contact Email"):
                email_col      = i
            if h == "Status":
                status_col     = i
            if h == "Reply Date":
                reply_date_col = i
            if h == "Reply Preview":
                reply_prev_col = i

        if email_col is None:
            return False

        for row_idx, row in enumerate(rows[1:], start=2):
            if len(row) > email_col:
                if row[email_col].lower() == contact_email.lower():
                    if status_col is not None:
                        ws.update_cell(row_idx, status_col + 1, "Replied")
                    if reply_date_col is not None:
                        ws.update_cell(
                            row_idx,
                            reply_date_col + 1,
                            datetime.utcnow().strftime("%Y-%m-%d")
                        )
                    if reply_prev_col is not None:
                        ws.update_cell(
                            row_idx,
                            reply_prev_col + 1,
                            reply_body[:100] if reply_body else ""
                        )
                    logger.info(
                        f"  📊 Sheet updated: reply from {contact_email}"
                    )
                    return True

        return False

    except Exception as e:
        logger.error(f"Sheet update reply error: {e}", exc_info=True)
        return False


# ─────────────────────────────────────────────
# LOG FOLLOW UP
# ─────────────────────────────────────────────

def log_followup(
    user_id         : int,
    company         : str,
    contact_email   : str,
    original_subject: str,
    followup_subject: str,
    new_value       : str,
    tab_name        : str = TAB_COLD_OUTREACH
) -> bool:
    if not SHEETS_ID:
        return False

    client = get_sheets_client()
    if not client:
        return False

    try:
        # 1 — Followups tab mein log karo
        fu_ws = get_or_create_sheet(client, TAB_FOLLOWUPS)
        if fu_ws:
            fu_ws.append_row([
                datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
                company,
                contact_email,
                original_subject,
                followup_subject,
                new_value[:100] if new_value else "",
                "Sent"
            ])

        # 2 — Original row update karo
        ws = get_or_create_sheet(client, tab_name)
        if not ws:
            logger.warning(
                f"Could not open tab '{tab_name}' — skipping row update"
            )
            return True

        rows = ws.get_all_values()
        if not rows:
            return True

        headers    = rows[0]
        email_col  = None
        fu1_col    = None
        fu2_col    = None
        status_col = None

        for i, h in enumerate(headers):
            if h in ("Email", "Contact Email"):
                email_col  = i
            if h == "Follow Up 1":
                fu1_col    = i
            if h == "Follow Up 2":
                fu2_col    = i
            if h == "Status":
                status_col = i

        if email_col is None:
            return True

        for row_idx, row in enumerate(rows[1:], start=2):
            if len(row) > email_col:
                if row[email_col].lower() == contact_email.lower():
                    now_str = datetime.utcnow().strftime("%Y-%m-%d")

                    if fu1_col is not None:
                        fu1_val = row[fu1_col] if len(row) > fu1_col else ""
                        if not fu1_val:
                            ws.update_cell(row_idx, fu1_col + 1, now_str)
                        elif fu2_col is not None:
                            fu2_val = row[fu2_col] if len(row) > fu2_col else ""
                            if not fu2_val:
                                ws.update_cell(row_idx, fu2_col + 1, now_str)

                    if status_col is not None:
                        ws.update_cell(
                            row_idx, status_col + 1, "Follow Up Sent"
                        )

                    logger.info(
                        f"  📊 Sheet updated: followup {contact_email}"
                    )
                    break

        return True

    except Exception as e:
        logger.error(f"Sheet log followup error: {e}", exc_info=True)
        return False


# ─────────────────────────────────────────────
# SYNC ALL — Sent log se Sheet sync karo
# ─────────────────────────────────────────────

def sync_sent_log_to_sheet(user_id: int) -> dict:
    """Pura sent log Sheet se sync karo."""

    log_file = f"uploads/{user_id}/sent_emails/log.json"

    if not os.path.exists(log_file):
        logger.warning(f"[Sheets] No sent log found for user {user_id}")
        return {"synced": 0}

    try:
        with open(log_file, encoding="utf-8") as f:
            log = json.load(f)
    except Exception as e:
        logger.error(f"[Sheets] Could not read sent log: {e}")
        return {"synced": 0}

    if not log:
        return {"synced": 0}

    synced = 0
    for entry in log:
        try:
            company = entry.get("company", "")
            if not company:
                continue

            log_cold_email(
                user_id       = user_id,
                company       = company,
                website       = entry.get("website", ""),
                contact_name  = entry.get("contact", ""),
                contact_role  = "",
                contact_email = entry["to"],
                subject       = entry.get("subject", ""),
                gap           = entry.get("gap", ""),
                proposal      = entry.get("proposal", ""),
            )
            synced += 1

        except Exception as e:
            logger.error(f"Sync error: {e}", exc_info=True)
            continue

    logger.info(f"[Sheets] Synced {synced} entries")
    return {"synced": synced}