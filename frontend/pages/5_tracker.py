# frontend/pages/5_tracker.py

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import json
import streamlit as st
from datetime import datetime

if "user_id" not in st.session_state:
    st.warning("Pehle login karo")
    st.stop()

user_id = st.session_state["user_id"]

# ─────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap');
html,body,[data-testid="stAppViewContainer"]{background:#0d0d0d!important;color:#f0f0f0!important;font-family:'DM Sans',sans-serif!important}
[data-testid="stSidebar"]{background:#161616!important;border-right:1px solid #2a2a2a!important}
h1,h2,h3{font-family:'Space Mono',monospace!important}
.stButton>button{background:#e8ff47!important;color:#000!important;border:none!important;border-radius:4px!important;font-family:'Space Mono',monospace!important;font-weight:700!important;font-size:12px!important}
.stButton>button[kind="secondary"]{background:transparent!important;color:#f0f0f0!important;border:1px solid #2a2a2a!important}
.stExpander{border:1px solid #2a2a2a!important;border-radius:6px!important;background:#161616!important}
.stMetric{background:#161616!important;border:1px solid #2a2a2a!important;border-radius:6px!important;padding:16px!important}
.stMetric label{color:#666!important;font-size:11px!important;text-transform:uppercase;letter-spacing:.1em}
[data-testid="stSidebarNav"]{display:none!important}
.status-pill{display:inline-block;border-radius:3px;padding:2px 8px;font-size:11px;font-family:'Space Mono',monospace}
.status-replied{background:rgba(74,222,128,.12);color:#4ade80;border:1px solid rgba(74,222,128,.3)}
.status-followup{background:rgba(251,191,36,.12);color:#fbbf24;border:1px solid rgba(251,191,36,.3)}
.status-awaiting{background:rgba(255,255,255,.06);color:#888;border:1px solid #2a2a2a}
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────
with st.sidebar:
    st.markdown('<p style="font-family:\'Space Mono\',monospace;font-size:18px;color:#e8ff47;font-weight:700">⚡ OutreachAI</p>', unsafe_allow_html=True)
    st.markdown(f'<p style="color:#666;font-size:12px;font-family:\'Space Mono\',monospace">{st.session_state.get("email","")}</p>', unsafe_allow_html=True)
    st.divider()
    st.page_link("app.py",                label="⚡  Home",          use_container_width=True)
    st.page_link("pages/2_onboarding.py", label="👤  Profile Setup", use_container_width=True)
    st.page_link("pages/4_outreach.py",   label="🚀  Cold Outreach", use_container_width=True)
    st.page_link("pages/5_tracker.py",    label="📊  Tracker",       use_container_width=True)


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

st.markdown("# 📊 Tracker")
st.caption("Sent emails, replies, follow ups — sab ek jagah")

log_file = f"uploads/{user_id}/sent_emails/log.json"

if not os.path.exists(log_file):
    st.markdown("""
    <div style="border:1px dashed #2a2a2a;border-radius:8px;padding:40px;text-align:center;color:#555">
        Abhi tak koi email nahi bheji.<br>
        <span style="font-size:13px">Cold Outreach page pe jao aur startups ko email karo.</span>
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
    st.info("Koi emails nahi — pehle bhejo")
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
a1, a2 = st.columns(2)
with a1:
    if st.button("🔄 Check Replies Now", use_container_width=True, type="primary"):
        with st.spinner("Inbox check kar rahe hain..."):
            try:
                from backend.agents.reply_detector import check_inbox
                result = check_inbox(user_id)
                if result.get("error"):
                    st.error(result["error"])
                else:
                    st.success(
                        f"✅ {result['checked']} emails checked · "
                        f"{result['replies']} new replies"
                    )
                    if result["replies"] > 0:
                        st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

with a2:
    if st.button("📤 Send Follow Ups Now", use_container_width=True):
        with st.spinner("Follow ups bhej rahe hain..."):
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

# Sort — latest first
sorted_log = sorted(sent_log, key=lambda x: x.get("sent_at",""), reverse=True)

if filter_status != "all":
    sorted_log = [e for e in sorted_log if e.get("status","awaiting") == filter_status]

if not sorted_log:
    st.info("Koi entries nahi is filter mein")
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
                    st.warning(f"⏳ {days_ago} din — no reply. Follow up due?")
                else:
                    st.markdown(
                        f'<span style="color:#666;font-size:13px">'
                        f'{days_ago} din ho gaye</span>',
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
    st.caption("GOOGLE_SHEETS_ID .env mein add karo for Sheets tracking")