# frontend/components/sidebar.py
"""
Single shared sidebar, used identically by every page.

Before this existed, every page in frontend/pages/ re-implemented its own
sidebar block by hand. They drifted apart (some pages had a logout button,
some didn't; some showed the scheduler status, some didn't) which made the
sidebar look like it was randomly changing/reappearing as you navigated.
Routing every page through render_sidebar() keeps it identical everywhere.
"""

import os
import json

import streamlit as st

from components.scheduler_control import render_scheduler_controls


def _get_reply_badge(user_id: int) -> str:
    try:
        from backend.pipeline.reply_handler import NotificationManager
        pending = NotificationManager.get_pending_notifications(user_id)
        count = len([n for n in pending if n["type"] == "reply_received"])
        return f"Replies & Drafts  🔴 {count}" if count else "Replies & Drafts"
    except Exception:
        return "Replies & Drafts"


def _remember_me_clear():
    if os.path.exists(".session_token"):
        os.remove(".session_token")


def render_sidebar():
    """Render the app-wide sidebar. Call this once near the top of every page."""
    user_id = st.session_state.get("user_id")
    email = st.session_state.get("email", "")

    with st.sidebar:
        st.markdown(
            '<p style="font-family:\'Space Mono\',monospace;font-size:18px;'
            'color:#e8ff47;font-weight:700;margin-bottom:0">⚡ OutreachAI</p>',
            unsafe_allow_html=True,
        )
        st.caption(email)
        st.divider()

        st.page_link("app.py", label="⚡  Home", use_container_width=True)
        st.page_link("pages/2_onboarding.py", label="👤  Profile Setup", use_container_width=True)
        st.page_link("pages/4_outreach.py", label="🚀  Cold Outreach", use_container_width=True)
        st.page_link("pages/5_tracker.py", label="📊  Tracker", use_container_width=True)
        st.page_link("pages/3_replies.py", label=f"📬  {_get_reply_badge(user_id)}", use_container_width=True)

        log_file = f"uploads/{user_id}/sent_emails/log.json"
        if user_id and os.path.exists(log_file):
            try:
                with open(log_file, encoding="utf-8") as f:
                    log = json.load(f)
                sent, replied = len(log), sum(1 for e in log if e.get("replied"))
                st.caption(f"📤 {sent} sent · 📩 {replied} replied")
            except Exception:
                pass

        st.divider()
        render_scheduler_controls(compact=True)
        st.divider()

        if st.button("Logout", key="sidebar_logout_btn", use_container_width=True):
            _remember_me_clear()
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()
