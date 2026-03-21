# backend/agents/reply_detector.py

import os
import json
import imaplib
import email
from email.header import decode_header
from datetime     import datetime, timedelta
from loguru       import logger


def get_gmail_creds(user_id: int) -> dict:
    try:
        from backend.database    import SessionLocal
        from backend.models.user import UserProfile

        db      = SessionLocal()
        profile = db.query(UserProfile).filter(
            UserProfile.user_id == user_id
        ).first()
        db.close()

        if not profile:
            return {"error": "Profile nahi mila"}
        if not profile.gmail_address or not profile.gmail_app_password:
            return {"error": "Gmail credentials nahi hain"}

        return {
            "email"   : profile.gmail_address,
            "password": profile.gmail_app_password
        }
    except Exception as e:
        return {"error": str(e)}


def get_sent_log(user_id: int) -> list:
    log_file = f"uploads/{user_id}/sent_emails/log.json"
    if not os.path.exists(log_file):
        return []
    try:
        with open(log_file, "r") as f:
            return json.load(f)
    except:
        return []


def save_sent_log(user_id: int, log: list):
    log_dir  = f"uploads/{user_id}/sent_emails"
    log_file = f"{log_dir}/log.json"
    os.makedirs(log_dir, exist_ok=True)
    with open(log_file, "w") as f:
        json.dump(log, f, indent=2)


def decode_subject(raw) -> str:
    if not raw:
        return ""
    decoded = decode_header(raw)
    parts   = []
    for part, charset in decoded:
        if isinstance(part, bytes):
            parts.append(
                part.decode(charset or "utf-8", errors="ignore")
            )
        else:
            parts.append(str(part))
    return "".join(parts)


def decode_body(msg) -> str:
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    body = part.get_payload(
                        decode=True
                    ).decode("utf-8", errors="ignore")
                    break
                except:
                    continue
    else:
        try:
            body = msg.get_payload(
                decode=True
            ).decode("utf-8", errors="ignore")
        except:
            pass
    return body[:1000]


def check_inbox(user_id: int) -> dict:
    """
    Gmail IMAP se inbox check karo.
    Replies detect karo.
    Sheets mein update karo.
    """
    creds = get_gmail_creds(user_id)
    if "error" in creds:
        return {"error": creds["error"]}

    sent_log = get_sent_log(user_id)
    if not sent_log:
        return {"checked": 0, "replies": 0, "updated": []}

    awaiting = [
        e for e in sent_log
        if not e.get("replied")
        and e.get("status") == "awaiting"
    ]

    if not awaiting:
        return {"checked": 0, "replies": 0, "updated": []}

    awaiting_emails   = {e["to"].lower()  for e in awaiting}
    awaiting_subjects = {e["subject"]     for e in awaiting}

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(creds["email"], creds["password"])
        mail.select("inbox")

        since  = (
            datetime.now() - timedelta(days=30)
        ).strftime("%d-%b-%Y")
        _, ids = mail.search(None, f"SINCE {since}")

        if not ids or not ids[0]:
            mail.logout()
            return {"checked": 0, "replies": 0, "updated": []}

        id_list     = ids[0].split()
        updated     = []
        reply_count = 0

        for mid in id_list[-100:]:
            try:
                _, data = mail.fetch(mid, "(RFC822)")
                msg     = email.message_from_bytes(data[0][1])

                sender  = msg.get("From", "").lower()
                subject = decode_subject(msg.get("Subject", ""))
                body    = decode_body(msg)

                is_reply = False

                # Check 1 — sender matches
                for ae in awaiting_emails:
                    if ae in sender:
                        is_reply = True
                        break

                # Check 2 — Re: subject matches
                if not is_reply and subject.lower().startswith("re:"):
                    orig = subject[3:].strip().lower()
                    for as_ in awaiting_subjects:
                        if (orig in as_.lower()
                                or as_.lower() in orig):
                            is_reply = True
                            break

                if not is_reply:
                    continue

                # Log update karo
                for entry in sent_log:
                    if (entry["to"].lower() in sender
                            and not entry.get("replied")):

                        entry["replied"]    = True
                        entry["reply_at"]   = datetime.utcnow().isoformat()
                        entry["status"]     = "replied"
                        entry["reply_body"] = body
                        updated.append(entry["to"])
                        reply_count += 1

                        logger.info(
                            f"  📩 Reply from: {entry['to']}"
                        )

                        # ── Google Sheets update ──────────
                        try:
                            from backend.utils.sheets_tracker import (
                                update_reply_status
                            )
                            update_reply_status(
                                user_id       = user_id,
                                contact_email = entry["to"],
                                reply_body    = body
                            )
                        except Exception as e:
                            logger.warning(
                                f"Sheets reply update error: {e}"
                            )

                        break

            except Exception as e:
                logger.warning(f"Email parse error: {e}")
                continue

        mail.logout()

        if updated:
            save_sent_log(user_id, sent_log)
            logger.info(
                f"[Reply Detector] {reply_count} replies found"
            )

        return {
            "checked": len(id_list),
            "replies": reply_count,
            "updated": updated
        }

    except imaplib.IMAP4.error as e:
        return {"error": f"IMAP error: {e}"}
    except Exception as e:
        return {"error": str(e)}


def get_all_users_with_sent_emails() -> list:
    """Sab users jo emails bhej chuke hain."""
    upload_dir = "uploads"
    users      = []
    if not os.path.exists(upload_dir):
        return []
    for folder in os.listdir(upload_dir):
        log_file = f"{upload_dir}/{folder}/sent_emails/log.json"
        if os.path.exists(log_file):
            try:
                users.append(int(folder))
            except:
                continue
    return users