# frontend/pages/5_tracker.py

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import streamlit as st
from datetime import datetime

if "user_id" not in st.session_state:
    st.warning("Please log in first")
    st.stop()

user_id = st.session_state["user_id"]

# ─────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────
from components.theme import apply_theme
apply_theme()

# ── Sidebar ───────────────────────────────────
from components.sidebar import render_sidebar
render_sidebar()


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

st.markdown("# 📊 Tracker")
st.caption("Sent emails, replies, follow ups — everything tracked in one place")

# ── Scheduler Status Banner ───────────────────
from components.scheduler_control import get_scheduler, is_running, start_scheduler

sched = get_scheduler()
if is_running():
    jobs         = {j.id: j for j in sched.get_jobs()}
    reply_job    = jobs.get("reply_check")
    followup_job = jobs.get("followup_check")
    sheets_job   = jobs.get("sheets_sync")

    parts = []
    if reply_job and reply_job.next_run_time:
        parts.append(f"Reply check: **{reply_job.next_run_time.strftime('%H:%M')}**")
    if followup_job and followup_job.next_run_time:
        parts.append(f"Follow up: **{followup_job.next_run_time.strftime('%H:%M')}**")
    if sheets_job and sheets_job.next_run_time:
        parts.append(f"Sheets sync: **{sheets_job.next_run_time.strftime('%H:%M')}**")

    status_line = "  ·  ".join(parts) if parts else "Jobs are running"
    st.markdown(
        f'<div style="background:rgba(74,222,128,.07);border:1px solid rgba(74,222,128,.2);'
        f'border-radius:6px;padding:8px 14px;font-size:12px;font-family:\'Space Mono\',monospace;'
        f'color:#4ade80;margin-bottom:12px">'
        f'🟢 Scheduler ON  ·  Next auto-run →  {status_line}'
        f'</div>',
        unsafe_allow_html=True
    )
else:
    col_msg, col_btn = st.columns([4, 1])
    with col_msg:
        st.markdown(
            '<div style="background:rgba(248,113,113,.07);border:1px solid rgba(248,113,113,.2);'
            'border-radius:6px;padding:8px 14px;font-size:12px;font-family:\'Space Mono\',monospace;'
            'color:#f87171;margin-bottom:12px">'
            '🔴 Scheduler OFF — auto reply-check, follow-ups & Sheets sync will not run.'
            '</div>',
            unsafe_allow_html=True
        )
    with col_btn:
        if st.button("▶ Start", key="tracker_sched_start", use_container_width=True, type="primary"):
            with st.spinner("Starting scheduler..."):
                start_scheduler()
            st.rerun()

log_file = f"uploads/{user_id}/sent_emails/log.json"

if not os.path.exists(log_file):
    st.markdown("""
    <div style="border:1px dashed #2a2a2a;border-radius:8px;padding:40px;text-align:center;color:#555">
        No emails sent yet.<br>
        <span style="font-size:13px">Go to the Cold Outreach page and email some startups.</span>
    </div>
    """, unsafe_allow_html=True)
    if st.button("→ Cold Outreach", type="primary"):
        st.switch_page("pages/4_outreach.py")
    st.stop()

try:
    with open(log_file) as f:
        sent_log = json.load(f)
except Exception:
    sent_log = []

if not sent_log:
    st.info("No emails yet — send some first")
    st.stop()

# ── Stats ─────────────────────────────────────
total     = len(sent_log)
replied   = sum(1 for e in sent_log if e.get("replied"))
awaiting  = sum(1 for e in sent_log if not e.get("replied"))
followups = sum(1 for e in sent_log if e.get("followup_sent"))
reply_pct = f"{int(replied/total*100)}%" if total else "0%"

c1,c2,c3,c4,c5 = st.columns(5)
c1.metric("Total Sent",  total)
c2.metric("Replied",     replied,  delta=reply_pct)
c3.metric("Awaiting",    awaiting)
c4.metric("Follow Ups",  followups)
c5.metric("Reply Rate",  reply_pct)

st.markdown("<br>", unsafe_allow_html=True)

# ── Manual Action Buttons ─────────────────────
st.caption("⬇️ Manual triggers — scheduler runs automatically but if you want to check inbox/send followups immediately, use these buttons")
a1, a2 = st.columns(2)
with a1:
    if st.button(
        "🔄 Check Replies Now",
        use_container_width=True,
        type="primary",
        help="Scheduler runs every 6 hours — this triggers an immediate inbox check"
    ):
        with st.spinner("Checking inbox..."):
            try:
                from backend.pipeline.reply_handler import ReplyDetector, ReplyStorage, AutoDraftGenerator

                detector = ReplyDetector(user_id)
                result   = detector.check_inbox()

                if result.get("error"):
                    st.error(result["error"])
                else:
                    replies = result.get("replies", [])
                    new_count = 0

                    for reply in replies:
                        original = reply["original_email"]

                        draft = AutoDraftGenerator.generate_reply_draft(
                            user_id          = user_id,
                            incoming_from    = reply["from"],
                            incoming_subject = reply["subject"],
                            incoming_body    = reply["body"],
                            original_subject = original.subject,
                            original_body    = getattr(original, "body", ""),
                            company          = original.company,
                        )

                        saved = ReplyStorage.save_reply_with_draft(
                            sent_email_id = original.id,
                            reply_from    = reply["from"],
                            reply_subject = reply["subject"],
                            reply_body    = reply["body"],
                            auto_draft    = draft,
                        )
                        if saved:
                            new_count += 1

                    st.success(
                        f"✅ {len(replies)} replies checked · "
                        f"{new_count} new replies saved"
                    )
                    if new_count > 0:
                        st.rerun()

            except Exception as e:
                st.error(f"Error: {e}")

with a2:
    if st.button(
        "📤 Force Send Follow Ups",
        use_container_width=True,
        help="Scheduler runs every 12 hours — this triggers an immediate follow-up sending"
    ):
        with st.spinner("Sending follow ups..."):
            try:
                from backend.agents.followup_agent import check_and_send_followups
                result = check_and_send_followups(user_id)
                st.success(f"✅ {result['followups_sent']} follow ups sent")
                if result["followups_sent"] > 0:
                    st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

st.divider()

# ── Filters ───────────────────────────────────
st.markdown("### 📧 Sent Emails")

f1, f2 = st.columns([1,3])
with f1:
    filter_status = st.selectbox(
        "Filter",
        ["all", "awaiting", "replied", "followup_sent"],
        format_func=lambda x: {
            "all"          : "All",
            "awaiting"     : "⏳ Awaiting",
            "replied"      : "📩 Replied",
            "followup_sent": "🔄 Follow Up Sent",
        }[x],
        key="tracker_filter"
    )

sorted_log = sorted(sent_log, key=lambda x: x.get("sent_at",""), reverse=True)

if filter_status != "all":
    sorted_log = [e for e in sorted_log if e.get("status","awaiting") == filter_status]

if not sorted_log:
    st.info("No entries in this filter-try changing it")
    st.stop()

status_class = {
    "replied"      : "status-replied",
    "followup_sent": "status-followup",
    "awaiting"     : "status-awaiting",
}
status_label = {
    "replied"      : "📩 Replied",
    "followup_sent": "🔄 Follow Up",
    "awaiting"     : "⏳ Awaiting",
}

# ── Entry cards ───────────────────────────────
for entry in sorted_log:
    status   = entry.get("status", "awaiting")
    company  = entry.get("company", entry["to"])
    s_class  = status_class.get(status, "status-awaiting")
    s_label  = status_label.get(status, "⏳ Awaiting")

    try:
        sent_str = datetime.fromisoformat(entry["sent_at"]).strftime("%d %b %Y")
    except Exception:
        sent_str = entry.get("sent_at","")[:10]

    with st.expander(
        f"**{company}** · {entry['to']} · {sent_str}",
        expanded=False
    ):
        col1, col2, col3 = st.columns(3)
        col1.markdown(
            f'<span class="status-pill {s_class}">{s_label}</span>',
            unsafe_allow_html=True
        )
        col2.markdown(f"**Sent:** {sent_str}")
        col3.markdown(f"**Follow Ups:** {entry.get('followup_count',0)}")

        st.markdown(f"**Subject:** {entry.get('subject','—')}")

        if entry.get("replied"):
            reply_date = entry.get("reply_at","")[:10]
            st.success(f"📩 Reply received on {reply_date}")
            if entry.get("reply_body"):
                st.caption(f"Preview: {entry['reply_body'][:200]}")

        elif entry.get("followup_sent"):
            fu_date = entry.get("followup_at","")[:10]
            st.info(f"🔄 Follow up sent on {fu_date}")

        else:
            try:
                days_ago = (
                    datetime.utcnow()
                    - datetime.fromisoformat(entry["sent_at"])
                ).days
                if days_ago >= 4:
                    st.warning(f"⏳ {days_ago} days — no reply. Follow up due?")
                else:
                    st.markdown(
                        f'<span style="color:#666;font-size:13px">'
                        f'{days_ago} days ago</span>',
                        unsafe_allow_html=True
                    )
            except Exception:
                pass

        if entry.get("gap"):
            st.caption(f"**Gap:** {entry['gap'][:120]}")
        if entry.get("proposal"):
            st.caption(f"**Proposal:** {entry['proposal'][:120]}")

st.divider()

# ── Google Sheets link ────────────────────────
sheets_id = os.getenv("GOOGLE_SHEETS_ID","")
if sheets_id:
    st.markdown(
        f'📊 **[Full tracker in Google Sheets ↗](https://docs.google.com/spreadsheets/d/{sheets_id})**'
    )
else:
    st.caption("Add GOOGLE_SHEETS_ID .env for sheets tracking")