# frontend/pages/5_tracker.py

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import json
import streamlit as st
from datetime import datetime
from loguru   import logger

if "user_id" not in st.session_state:
    st.warning("Pehle login karo")
    st.stop()

user_id = st.session_state["user_id"]

st.title("📊 Tracker")
st.caption("Sent emails, replies aur follow ups track karo")

# ── Load sent log ─────────────────────────────
log_file = f"uploads/{user_id}/sent_emails/log.json"

if not os.path.exists(log_file):
    st.info("Abhi tak koi email nahi bheji — Jobs ya Cold Outreach page pe jao")
    st.stop()

try:
    with open(log_file, "r") as f:
        sent_log = json.load(f)
except:
    sent_log = []

if not sent_log:
    st.info("Koi emails nahi — pehle bhejo")
    st.stop()

# ── Stats ─────────────────────────────────────
total      = len(sent_log)
replied    = sum(1 for e in sent_log if e.get("replied"))
awaiting   = sum(1 for e in sent_log if e.get("status") == "awaiting")
followups  = sum(1 for e in sent_log if e.get("followup_sent"))

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Sent",    total)
col2.metric("Replied",       replied,   delta=f"{int(replied/total*100)}%" if total else "0%")
col3.metric("Awaiting",      awaiting)
col4.metric("Follow Ups",    followups)

st.divider()

# ── Manual Actions ────────────────────────────
col1, col2 = st.columns(2)

with col1:
    if st.button("🔄 Check Replies Now"):
        with st.spinner("Inbox check kar rahe hain..."):
            try:
                from backend.agents.reply_detector import check_inbox
                result = check_inbox(user_id)
                if result.get("error"):
                    st.error(result["error"])
                else:
                    st.success(
                        f"✅ {result['checked']} emails checked — "
                        f"{result['replies']} new replies"
                    )
                    st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

with col2:
    if st.button("📤 Send Follow Ups Now"):
        with st.spinner("Follow ups bhej rahe hain..."):
            try:
                from backend.agents.followup_agent import check_and_send_followups
                result = check_and_send_followups(user_id)
                st.success(
                    f"✅ {result['followups_sent']} follow ups sent"
                )
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

st.divider()

# ── Email List ────────────────────────────────
st.subheader("📧 All Sent Emails")

# Sort by date — latest first
sent_log_sorted = sorted(
    sent_log,
    key    = lambda x: x.get("sent_at", ""),
    reverse= True
)

status_colors = {
    "replied"      : "🟢",
    "followup_sent": "🟡",
    "awaiting"     : "⏳",
}

for entry in sent_log_sorted:
    status      = entry.get("status", "awaiting")
    status_icon = status_colors.get(status, "⏳")
    company     = entry.get("company", entry["to"])

    try:
        sent_dt  = datetime.fromisoformat(entry["sent_at"])
        sent_str = sent_dt.strftime("%d %b %Y")
    except:
        sent_str = entry.get("sent_at", "")[:10]

    with st.expander(
        f"{status_icon} **{company}** → {entry['to']} — {sent_str}"
    ):
        col1, col2, col3 = st.columns(3)
        col1.metric("Status",    status.replace("_", " ").title())
        col2.metric("Sent",      sent_str)
        col3.metric(
            "Follow Ups",
            entry.get("followup_count", 0)
        )

        st.write(f"**Subject:** {entry.get('subject', '')}")

        if entry.get("replied"):
            st.success(
                f"📩 Replied on: "
                f"{entry.get('reply_at', '')[:10]}"
            )
            if entry.get("reply_body"):
                st.caption(
                    f"Reply preview: {entry['reply_body'][:200]}"
                )

        elif entry.get("followup_sent"):
            st.info(
                f"🔄 Follow up sent: "
                f"{entry.get('followup_at', '')[:10]}"
            )

        else:
            try:
                sent_dt  = datetime.fromisoformat(entry["sent_at"])
                days_ago = (datetime.utcnow() - sent_dt).days
                st.warning(f"⏳ {days_ago} din ho gaye — reply nahi aaya")
            except:
                pass

st.divider()

# ── Google Sheets Link ────────────────────────
sheets_id = os.getenv("GOOGLE_SHEETS_ID", "")
if sheets_id:
    sheets_url = f"https://docs.google.com/spreadsheets/d/{sheets_id}"
    st.markdown(
        f"📊 **[Google Sheet mein dekho]({sheets_url})**"
    )
else:
    st.caption("Google Sheets ID .env mein add karo")