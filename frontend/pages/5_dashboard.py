import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import streamlit as st
from backend.database import SessionLocal
from backend.models.application import Application
from backend.models.job import Job
from backend.models.company import Company

# Auth check
if "user_id" not in st.session_state:
    st.warning("Pehle login karo")
    st.stop()

user_id = st.session_state["user_id"]

st.title("📊 Dashboard")

# ── Stats ─────────────────────────────────────
db = SessionLocal()
try:
    total = db.query(Application).filter(
        Application.user_id == user_id
    ).count()

    statuses = [
        "email_sent", "follow_up_1_sent",
        "follow_up_2_sent", "replied_positive",
        "replied_negative", "interview_scheduled",
        "ghosted"
    ]

    status_counts = {}
    for s in statuses:
        status_counts[s] = db.query(Application).filter(
            Application.user_id == user_id,
            Application.status  == s
        ).count()

    replied = (
        status_counts.get("replied_positive", 0) +
        status_counts.get("replied_negative", 0) +
        status_counts.get("interview_scheduled", 0)
    )
    reply_rate = round(replied / total * 100, 1) if total > 0 else 0
    interviews = status_counts.get("interview_scheduled", 0)

    # ATS improvement
    ats_apps = db.query(Application).filter(
        Application.user_id          == user_id,
        Application.ats_score_before != None,
        Application.ats_score_after  != None
    ).all()

    avg_improvement = 0
    if ats_apps:
        improvements   = [a.ats_score_after - a.ats_score_before for a in ats_apps]
        avg_improvement = round(sum(improvements) / len(improvements), 1)

    # Recent applications
    recent_apps = db.query(Application).filter(
        Application.user_id == user_id
    ).order_by(Application.created_at.desc()).limit(5).all()

    recent = []
    for app in recent_apps:
        name = ""
        if app.job_id:
            job  = db.query(Job).filter(Job.id == app.job_id).first()
            name = f"{job.title} @ {job.company_name}" if job else ""
        elif app.company_id:
            co   = db.query(Company).filter(Company.id == app.company_id).first()
            name = f"Cold → {co.name}" if co else ""
        recent.append({
            "name"     : name,
            "status"   : app.status,
            "sent_date": str(app.sent_date)[:10] if app.sent_date else ""
        })

finally:
    db.close()

# ── Top Metrics ───────────────────────────────
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Sent",    total)
col2.metric("Reply Rate",    f"{reply_rate}%")
col3.metric("Interviews",    interviews)
col4.metric("Avg ATS Boost", f"+{avg_improvement}%")

st.divider()

# ── Status Breakdown ──────────────────────────
st.subheader("Application Status")

STATUS_MAP = {
    "email_sent"         : "📤 Sent",
    "follow_up_1_sent"   : "🔄 Follow Up 1",
    "follow_up_2_sent"   : "🔄 Follow Up 2",
    "replied_positive"   : "✅ Positive",
    "replied_negative"   : "❌ Rejected",
    "interview_scheduled": "🎯 Interview",
    "ghosted"            : "👻 Ghosted",
}

cols = st.columns(len(STATUS_MAP))
for col, (key, label) in zip(cols, STATUS_MAP.items()):
    col.metric(label, status_counts.get(key, 0))

st.divider()

# ── Recent Activity ───────────────────────────
st.subheader("Recent Activity")

STATUS_EMOJI = {
    "email_sent"         : "📤",
    "replied_positive"   : "✅",
    "replied_negative"   : "❌",
    "interview_scheduled": "🎯",
    "ghosted"            : "👻",
    "follow_up_1_sent"   : "🔄",
    "follow_up_2_sent"   : "🔄",
}

if recent:
    for app in recent:
        emoji = STATUS_EMOJI.get(app["status"], "📄")
        c1, c2, c3 = st.columns([4, 2, 2])
        c1.write(f"{emoji} {app['name']}")
        c2.caption(app["sent_date"])
        c3.caption(app["status"].replace("_", " ").title())
else:
    st.info("Koi activity nahi abhi")

st.divider()

# ── Quick Actions ─────────────────────────────
st.subheader("Quick Actions")

col1, col2 = st.columns(2)

with col1:
    if st.button("🚀 New Hunt", type="primary"):
        if "thread_id" in st.session_state:
            del st.session_state["thread_id"]
        st.switch_page("pages/3_pipeline.py")

with col2:
    if st.button("✅ Pending Approvals"):
        st.switch_page("pages/4_approvals.py")
