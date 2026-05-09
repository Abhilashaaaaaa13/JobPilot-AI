# backend/utils/sheets_sync.py
# ═══════════════════════════════════════════════════════════════════════════════
# SYNC SENT EMAILS + REPLIES TO GOOGLE SHEETS
# ═══════════════════════════════════════════════════════════════════════════════
# Automatically updates user's tracker spreadsheet every 2 hours
# ═══════════════════════════════════════════════════════════════════════════════

import json
import os
from datetime import datetime
from loguru import logger

try:
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    HAS_GOOGLE = True
except ImportError:
    HAS_GOOGLE = False
    logger.warning("google-auth-oauthlib not installed — Sheets sync disabled")


SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def get_sheets_service(creds_json_path: str = None):
    """
    Get Google Sheets API service.
    Uses service account credentials from GOOGLE_CREDENTIALS environment variable.
    """
    if not HAS_GOOGLE:
        return None
    
    # Try environment variable first
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    
    if not creds_json and creds_json_path:
        try:
            with open(creds_json_path) as f:
                creds_json = f.read()
        except Exception:
            return None
    
    if not creds_json:
        logger.warning("GOOGLE_CREDENTIALS not set — Sheets sync unavailable")
        return None
    
    try:
        creds_dict = json.loads(creds_json)
        credentials = Credentials.from_service_account_info(
            creds_dict,
            scopes=SCOPES
        )
        service = build("sheets", "v4", credentials=credentials)
        return service
    except Exception as e:
        logger.error(f"Failed to create Sheets service: {e}")
        return None


def sync_user_tracker_to_sheets(user_id: int, sheets_id: str) -> dict:
    """
    Sync user's sent emails + replies to their Google Sheet.
    
    Sheet format:
    | Company | Contact | Email | Status | Sent Date | Reply Date | Follow-ups | Notes |
    
    Args:
        user_id: User ID
        sheets_id: Google Sheets ID
    
    Returns:
        {"success": bool, "rows_updated": int, "error": str}
    """
    try:
        from backend.database import SessionLocal
        from backend.models.sent_email import SentEmail
        
        service = get_sheets_service()
        if not service:
            return {
                "success": False,
                "error": "Google Sheets not configured"
            }
        
        db = SessionLocal()
        sent_emails = db.query(SentEmail).filter(
            SentEmail.user_id == user_id
        ).order_by(SentEmail.sent_at.desc()).all()
        db.close()
        
        if not sent_emails:
            return {
                "success": True,
                "rows_updated": 0,
                "note": "No emails to sync"
            }
        
        # Prepare sheet data
        headers = [
            "Company",
            "Contact",
            "Email",
            "Status",
            "Sent Date",
            "Reply Date",
            "Follow-ups",
            "Notes"
        ]
        
        rows = [headers]
        
        for email in sent_emails:
            sent_date = (
                email.sent_at.strftime("%Y-%m-%d")
                if email.sent_at else ""
            )
            reply_date = (
                email.reply_at.strftime("%Y-%m-%d")
                if email.reply_at else ""
            )
            
            # Determine status
            if email.replied:
                status = "📩 Replied"
            elif email.followup_count >= 1:
                status = "🔄 Follow-up Sent"
            else:
                status = "⏳ Awaiting"
            
            row = [
                email.company or "—",
                email.contact_name or "—",
                email.to_email,
                status,
                sent_date,
                reply_date,
                str(email.followup_count),
                email.subject[:50] if email.subject else "—"
            ]
            rows.append(row)
        
        # Clear and update sheet
        range_name = "A1"
        body = {
            "values": rows
        }
        
        # First clear the sheet
        service.spreadsheets().values().clear(
            spreadsheetId=sheets_id,
            range="A:Z",
            body={}
        ).execute()
        
        # Then update with new data
        result = service.spreadsheets().values().update(
            spreadsheetId=sheets_id,
            range=range_name,
            valueInputOption="RAW",
            body=body
        ).execute()
        
        updated_range = result.get("updatedRange", "")
        rows_updated = result.get("updatedRows", 0)
        
        logger.info(
            f"✅ Synced {rows_updated} rows for user {user_id} "
            f"to {sheets_id}"
        )
        
        return {
            "success": True,
            "rows_updated": rows_updated,
            "range": updated_range
        }
    
    except Exception as e:
        logger.error(f"Sheets sync error for user {user_id}: {e}")
        return {
            "success": False,
            "error": str(e)
        }


def create_tracker_sheet(user_id: int, sheets_id: str) -> dict:
    """
    Initialize Google Sheet with headers and formatting.
    
    Args:
        user_id: User ID
        sheets_id: Google Sheets ID
    
    Returns:
        {"success": bool, "error": str}
    """
    try:
        service = get_sheets_service()
        if not service:
            return {
                "success": False,
                "error": "Google Sheets not configured"
            }
        
        headers = [
            "Company",
            "Contact",
            "Email",
            "Status",
            "Sent Date",
            "Reply Date",
            "Follow-ups",
            "Notes"
        ]
        
        body = {
            "values": [headers]
        }
        
        service.spreadsheets().values().update(
            spreadsheetId=sheets_id,
            range="A1:H1",
            valueInputOption="RAW",
            body=body
        ).execute()
        
        # Format header row (bold)
        requests = [
            {
                "repeatCell": {
                    "range": {
                        "sheetId": 0,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": 8
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {
                                "bold": True
                            }
                        }
                    },
                    "fields": "userEnteredFormat.textFormat"
                }
            }
        ]
        
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheets_id,
            body={"requests": requests}
        ).execute()
        
        logger.info(f"✅ Tracker sheet initialized for user {user_id}")
        return {"success": True}
    
    except Exception as e:
        logger.error(f"Failed to create tracker sheet: {e}")
        return {
            "success": False,
            "error": str(e)
        }


def get_sheets_id_from_url(sheet_url: str) -> str:
    """
    Extract Sheets ID from URL.
    URL format: https://docs.google.com/spreadsheets/d/{SHEETS_ID}/...
    """
    try:
        parts = sheet_url.split("/d/")
        if len(parts) >= 2:
            sheets_id = parts[1].split("/")[0]
            return sheets_id
    except Exception:
        pass
    return ""


if __name__ == "__main__":
    # Test
    user_id = 1
    sheets_id = os.getenv("GOOGLE_SHEETS_ID", "")
    
    if sheets_id:
        result = sync_user_tracker_to_sheets(user_id, sheets_id)
        print(result)
    else:
        print("Set GOOGLE_SHEETS_ID environment variable")