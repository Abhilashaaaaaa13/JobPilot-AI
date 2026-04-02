# frontend/pages/3_replies.py
# ═══════════════════════════════════════════════════════════════════════════════
# REPLY NOTIFICATIONS & DRAFT APPROVALS PAGE
# ═══════════════════════════════════════════════════════════════════════════════

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
import json
from datetime import datetime
from backend.pipeline.reply_handler import (
    NotificationManager,
    DraftApprovalManager,
    ReplyDetector,
    AutoDraftGenerator,
    ReplyStorage,
)

# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────

st.set_page_config(
    page_title="📬 Replies",
    page_icon="📬",
    layout="wide"
)

# ─────────────────────────────────────────────
# AUTH CHECK
# ─────────────────────────────────────────────

if "user_id" not in st.session_state:
    st.warning("🔐 Login first!")
    st.stop()

user_id = st.session_state["user_id"]

# ─────────────────────────────────────────────
# STYLING
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
[data-testid="stSidebarNav"]{display:none!important}
.stTabs [data-baseweb="tab-list"]{background:transparent!important;border-bottom:1px solid #2a2a2a!important}
.stTabs [data-baseweb="tab"]{background:transparent!important;color:#666!important;font-family:'Space Mono',monospace!important;font-size:12px!important;border-bottom:2px solid transparent!important;padding:10px 20px!important}
.stTabs [aria-selected="true"]{color:#e8ff47!important;border-bottom-color:#e8ff47!important}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────

with st.sidebar:
    st.markdown('<p style="font-family:\'Space Mono\',monospace;font-size:18px;color:#e8ff47;font-weight:700">⚡ OutreachAI</p>', unsafe_allow_html=True)
    st.markdown(f'<p style="color:#666;font-size:12px;font-family:\'Space Mono\',monospace">{st.session_state.get("email","")}</p>', unsafe_allow_html=True)
    st.divider()
    st.page_link("app.py",                label="⚡  Home",            use_container_width=True)
    st.page_link("pages/2_onboarding.py", label="👤  Profile Setup",   use_container_width=True)
    st.page_link("pages/4_outreach.py",   label="🚀  Cold Outreach",   use_container_width=True)
    st.page_link("pages/5_tracker.py",    label="📊  Tracker",         use_container_width=True)
    st.page_link("pages/3_replies.py",    label="📬  Replies & Drafts", use_container_width=True)

# ─────────────────────────────────────────────
# PAGE TITLE + CHECK NOW BUTTON
# ─────────────────────────────────────────────

col_title, col_actions = st.columns([3, 1])

with col_title:
    st.markdown("# 📬 Replies & Drafts")
    st.caption("Auto-detected replies from cold outreach emails")

with col_actions:
    if st.button("🔄 Check Now", key="check_now", use_container_width=True, type="primary"):
        with st.spinner("Checking Gmail inbox..."):
            try:
                detector = ReplyDetector(user_id)
                result   = detector.check_inbox()

                if result.get("error"):
                    st.error(f"❌ {result['error']}")
                else:
                    replies   = result.get("replies", [])
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
                            # Create notification so it shows in Tab 1
                            NotificationManager.create_notification(
                                user_id    = user_id,
                                notif_type = "reply_received",
                                title      = f"📩 Reply from {original.company or reply['from']}",
                                message    = f"Subject: {reply['subject'][:60]}",
                                data       = {
                                    "sent_email_id": original.id,
                                    "from"         : reply["from"],
                                    "company"      : original.company,
                                    "subject"      : reply["subject"],
                                    "body_preview" : reply["body"][:200],
                                }
                            )
                            new_count += 1

                    if new_count > 0:
                        st.success(f"✅ {new_count} new reply(ies) found & saved")
                        st.rerun()
                    else:
                        st.info("No new replies")

            except Exception as e:
                st.error(f"Error: {e}")

st.divider()

# ─────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────

tab1, tab2, tab3 = st.tabs([
    "🔔 New Replies",
    "✏️ Draft Approvals",
    "📋 History"
])

# ═════════════════════════════════════════════════════════════════════════════
# TAB 1: NEW REPLY NOTIFICATIONS
# ═════════════════════════════════════════════════════════════════════════════

with tab1:
    st.markdown("### 📩 New Replies Received")

    try:
        notifications = NotificationManager.get_pending_notifications(user_id)
        reply_notifs  = [n for n in notifications if n["type"] == "reply_received"]

        if not reply_notifs:
            st.info("✨ No new replies yet. Keep outreaching!")
        else:
            for notif in reply_notifs:
                with st.container(border=True):
                    col_icon, col_info = st.columns([0.5, 4])
                    with col_icon:
                        st.markdown("📩")
                    with col_info:
                        st.markdown(f"**{notif['title']}**")

                    data = notif["data"]
                    st.markdown(f"**From:** `{data.get('from', '?')}`")
                    st.markdown(f"**Company:** {data.get('company', 'N/A')}")
                    st.markdown(f"**Subject:** {data.get('subject', '(no subject)')}")

                    st.markdown("**Their message:**")
                    st.text_area(
                        "Preview",
                        value            = data.get("body_preview", "")[:500],
                        height           = 100,
                        disabled         = True,
                        label_visibility = "collapsed",
                        key              = f"reply_prev_{notif['id']}",
                    )

                    st.caption(f"Received: {notif['created_at'][:19]}")

                    col_read, col_drafts = st.columns(2)
                    with col_read:
                        if st.button(
                            "✅ Mark as read",
                            key              = f"mark_read_{notif['id']}",
                            use_container_width = True,
                        ):
                            NotificationManager.mark_as_read(notif["id"])
                            st.rerun()
                    with col_drafts:
                        if st.button(
                            "✏️ Go to Draft",
                            key              = f"go_draft_{notif['id']}",
                            use_container_width = True,
                        ):
                            # Switch to Tab 2 by rerunning with query param hint
                            st.session_state["active_tab"] = "drafts"
                            st.rerun()

    except Exception as e:
        st.error(f"Error loading notifications: {e}")


# ═════════════════════════════════════════════════════════════════════════════
# TAB 2: DRAFT APPROVALS
# ═════════════════════════════════════════════════════════════════════════════

with tab2:
    st.markdown("### ✏️ Review & Approve Replies")
    st.caption("Auto-generated replies using Groq AI — review, edit if needed, then send.")

    try:
        drafts = DraftApprovalManager.get_pending_drafts(user_id)

        if not drafts:
            st.info("✨ No drafts pending review")
        else:
            for idx, draft in enumerate(drafts):
                with st.container(border=True):
                    company_display = draft["company"] or draft["from"]
                    st.markdown(f"#### 📧 {company_display}")
                    st.caption(f"Reply from: **{draft['from']}**  ·  Received: {(draft.get('reply_at') or '')[:10]}")

                    col_preview, col_draft = st.columns([1, 2])

                    with col_preview:
                        st.markdown("**📥 Their Reply**")
                        with st.expander("View original context", expanded=False):
                            st.markdown("**Original subject we sent:**")
                            st.code(draft["original_subject"], language="text")
                            st.markdown("**Their reply preview:**")
                            st.text(draft["reply_body_preview"])

                    with col_draft:
                        st.markdown("**🤖 Auto-Draft Reply**")

                        auto_draft = draft.get("auto_draft", {})

                        edited_subject = st.text_input(
                            "Subject",
                            value            = auto_draft.get("subject", f"Re: {draft['original_subject']}"),
                            key              = f"subject_{idx}",
                            label_visibility = "visible",
                        )

                        edited_body = st.text_area(
                            "Body",
                            value            = auto_draft.get("body", "Thank you for your reply. I'd love to discuss this further."),
                            height           = 200,
                            key              = f"body_{idx}",
                            label_visibility = "visible",
                        )

                        st.caption("Generated by Groq · Edit freely before sending")

                    col_approve, col_reject, _ = st.columns(3)

                    with col_approve:
                        if st.button(
                            "✅ Send Reply",
                            key              = f"approve_{idx}",
                            use_container_width = True,
                            type             = "primary",
                        ):
                            result = DraftApprovalManager.approve_and_send(
                                sent_email_id = draft["id"],
                                final_subject = edited_subject,
                                final_body    = edited_body,
                                user_id       = user_id,
                            )
                            if result.get("success"):
                                st.success(f"✅ Reply sent to {draft['from']}")
                                st.rerun()
                            else:
                                st.error(f"Error: {result.get('error')}")

                    with col_reject:
                        if st.button(
                            "❌ Reject Draft",
                            key              = f"reject_{idx}",
                            use_container_width = True,
                        ):
                            if DraftApprovalManager.reject_draft(draft["id"]):
                                st.warning("Draft marked for manual reply")
                                st.rerun()

    except Exception as e:
        st.error(f"Error loading drafts: {e}")


# ═════════════════════════════════════════════════════════════════════════════
# TAB 3: HISTORY
# ═════════════════════════════════════════════════════════════════════════════

with tab3:
    st.markdown("### 📋 Draft Actions History")

    try:
        from backend.database import SessionLocal
        from backend.models.draft_action import DraftAction

        db      = SessionLocal()
        actions = db.query(DraftAction).filter(
            DraftAction.user_id == user_id
        ).order_by(DraftAction.user_action_at.desc()).limit(50).all()
        db.close()

        if not actions:
            st.info("No action history yet")
        else:
            for action in actions:
                icon = {
                    "approved"       : "✅",
                    "edited_and_sent": "✏️",
                    "rejected"       : "❌",
                    "manual_reply"   : "📝",
                }.get(action.action, "📋")

                col_action, col_time = st.columns([3, 1])
                with col_action:
                    action_name = action.action.replace("_", " ").title()
                    st.markdown(f"{icon} **{action_name}** · Email ID: `{action.sent_email_id}`")
                with col_time:
                    st.caption(action.user_action_at.strftime("%d %b %Y %H:%M"))

    except Exception as e:
        st.error(f"Error loading history: {e}")


# ─────────────────────────────────────────────
# DEBUG EXPANDER
# ─────────────────────────────────────────────

with st.expander("🔧 Debug Info", expanded=False):
    st.markdown("### Scheduler Status")

    sched = st.session_state.get("scheduler")
    if sched and sched.running:
        st.success("🟢 Scheduler is running")
        for job in sched.get_jobs():
            next_run = job.next_run_time.strftime("%H:%M") if job.next_run_time else "?"
            st.caption(f"⏰ {job.id}: Next run at {next_run}")
    else:
        err = st.session_state.get("scheduler_error", "")
        st.warning(f"🔴 Scheduler not running. {err[:80] if err else ''}")

    st.divider()
    st.markdown("### Manual Triggers (Testing)")

    col_reply, col_fu = st.columns(2)

    with col_reply:
        if st.button("🔄 Raw Check Replies", key="manual_reply"):
            with st.spinner("Checking..."):
                try:
                    detector = ReplyDetector(user_id)
                    result   = detector.check_inbox()
                    # Show raw result but strip ORM objects for JSON display
                    display  = {
                        "error"  : result.get("error"),
                        "replies": [
                            {
                                "from"   : r["from"],
                                "subject": r["subject"],
                                "body"   : r["body"][:100],
                            }
                            for r in result.get("replies", [])
                        ],
                    }
                    st.json(display)
                except Exception as e:
                    st.error(f"Error: {e}")

    with col_fu:
        if st.button("📤 Raw Force Follow Ups", key="manual_fu"):
            with st.spinner("Sending..."):
                try:
                    from backend.agents.followup_agent import check_and_send_followups
                    result = check_and_send_followups(user_id)
                    st.json(result)
                except Exception as e:
                    st.error(f"Error: {e}")

# ─────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────

st.divider()
st.markdown("""
### How It Works
1. **Background Scheduler** checks your Gmail inbox **every 6 hours** automatically
2. **Groq AI** detects replies and auto-generates contextual draft responses
3. **You see notifications** with preview of the incoming email
4. **You approve, edit, or reject** the auto-draft
5. **Approved replies** are sent back automatically
6. **Everything tracked** in your database

No manual triggers needed — everything runs in the background! ⚡
""")