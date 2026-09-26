import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import streamlit as st
from datetime import datetime
from backend.database import init_db

init_db()

st.set_page_config(
    page_title="OutreachAI",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

from components.theme import apply_theme
apply_theme()


# ── Auth helpers ──────────────────────────────────────────────────────────────

def register_user(email, password):
    from backend.database import SessionLocal
    from backend.models.user import User
    from backend.utils.auth_utils import hash_password
    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == email).first():
            return False, "Email already registered"
        user = User(email=email, hashed_password=hash_password(password))
        db.add(user); db.commit(); db.refresh(user)
        return True, user
    except Exception as e:
        db.rollback(); return False, str(e)
    finally:
        db.close()


def login_user(email, password):
    from backend.database import SessionLocal
    from backend.models.user import User
    from backend.utils.auth_utils import verify_password
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user or not verify_password(password, user.hashed_password):
            return False, "Invalid email or password"
        if not user.is_active:
            return False, "Account inactive"
        return True, user
    except Exception as e:
        return False, str(e)
    finally:
        db.close()


# ── Remember-me helpers ───────────────────────────────────────────────────────

def _remember_me_load():
    if os.path.exists(".session_token"):
        try:
            with open(".session_token") as f:
                data = json.load(f)
            if data.get("user_id") and data.get("email"):
                return data
        except Exception:
            pass
    return None

def _remember_me_save(uid, email):
    try:
        with open(".session_token", "w") as f:
            json.dump({"user_id": uid, "email": email}, f)
    except Exception:
        pass

def _remember_me_clear():
    if os.path.exists(".session_token"):
        os.remove(".session_token")


# ── Session restore ───────────────────────────────────────────────────────────

if "user_id" not in st.session_state:
    saved = _remember_me_load()
    if saved:
        from backend.database import SessionLocal
        from backend.models.user import User
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == saved["user_id"]).first()
            if user and user.is_active:
                st.session_state["user_id"] = saved["user_id"]
                st.session_state["email"]   = saved["email"]
            else:
                _remember_me_clear()
        finally:
            db.close()


# ── Login / Register page ─────────────────────────────────────────────────────

if "user_id" not in st.session_state:
    _, col_m, _ = st.columns([1, 1.2, 1])
    with col_m:
        st.markdown("## ⚡ OutreachAI")
        st.caption("Cold outreach, automated.")
        tab_login, tab_reg = st.tabs(["Login", "Register"])

        with tab_login:
            st.markdown("<br>", unsafe_allow_html=True)
            login_email = st.text_input("Email",    key="login_email", placeholder="you@gmail.com")
            login_pass  = st.text_input("Password", key="login_pass",  type="password")
            remember_me = st.checkbox("Remember me", value=True)
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Login", key="btn_login", use_container_width=True):
                if not login_email or not login_pass:
                    st.error("Please enter your email and password.")
                else:
                    ok, result = login_user(login_email, login_pass)
                    if ok:
                        st.session_state["user_id"] = result.id
                        st.session_state["email"]   = result.email
                        if remember_me:
                            _remember_me_save(result.id, result.email)
                        st.rerun()
                    else:
                        st.error(result)

        with tab_reg:
            st.markdown("<br>", unsafe_allow_html=True)
            reg_email = st.text_input("Email",            key="reg_email",  placeholder="you@gmail.com")
            reg_pass  = st.text_input("Password",         key="reg_pass",   type="password")
            reg_pass2 = st.text_input("Confirm Password", key="reg_pass2",  type="password")
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Create Account", key="btn_reg", use_container_width=True):
                if not reg_email or not reg_pass:
                    st.error("Please fill in all fields.")
                elif reg_pass != reg_pass2:
                    st.error("Passwords do not match.")
                elif len(reg_pass) < 6:
                    st.error("Password must be at least 6 characters.")
                else:
                    ok, result = register_user(reg_email, reg_pass)
                    if ok:
                        st.session_state["user_id"] = result.id
                        st.session_state["email"]   = result.email
                        _remember_me_save(result.id, result.email)
                        st.success("Account created successfully!")
                        st.switch_page("pages/2_onboarding.py")
                    else:
                        st.error(result)
    st.stop()


# ── Sidebar ───────────────────────────────────────────────────────────────────

from components.sidebar import render_sidebar
from components.formatting import short_url
from components.email_actions import render_email_panel
render_sidebar()


# ── Dashboard ─────────────────────────────────────────────────────────────────

user_id = st.session_state["user_id"]

# Auto-start the background scheduler once logged in, so reply-checks, follow-ups,
# and Sheets sync run without needing a manual click every time the app boots.
from components.scheduler_control import start_scheduler
start_scheduler()

st.markdown("# ⚡ Dashboard")

from backend.database import SessionLocal
from backend.models.user import UserProfile
db      = SessionLocal()
profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
db.close()

if not profile or not profile.resume_path:
    st.warning("Profile setup incomplete — please upload your resume.")
    if st.button("Complete Profile Setup", type="primary"):
        st.switch_page("pages/2_onboarding.py")
    st.stop()

log_file = f"uploads/{user_id}/sent_emails/log.json"
sent_log = []
if os.path.exists(log_file):
    try:
        with open(log_file, encoding="utf-8") as f:
            sent_log = json.load(f)
    except Exception:
        pass

total_sent = len(sent_log)
replied    = sum(1 for e in sent_log if e.get("replied"))
awaiting   = sum(1 for e in sent_log if not e.get("replied"))
followups  = sum(1 for e in sent_log if e.get("followup_sent"))
reply_rate = f"{int(replied/total_sent*100)}%" if total_sent else "—"

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Emails Sent", total_sent)
c2.metric("Replied",     replied)
c3.metric("Awaiting",    awaiting)
c4.metric("Follow Ups",  followups)
c5.metric("Reply Rate",  reply_rate)

st.markdown("<br>", unsafe_allow_html=True)
left, right = st.columns([1, 1.4], gap="large")


# ── Notifications panel ───────────────────────────────────────────────────────

with left:
    st.markdown("### 🔔 Notifications")
    has_notifs = False
    now        = datetime.utcnow()

    try:
        from backend.pipeline.reply_handler import NotificationManager
        db_notifs    = NotificationManager.get_pending_notifications(user_id)
        reply_notifs = [n for n in db_notifs if n["type"] == "reply_received"]
        if reply_notifs:
            has_notifs = True
            for notif in reply_notifs[:3]:
                data    = notif["data"]
                company = data.get("company") or data.get("from", "")
                subj    = data.get("subject", "")[:60]
                col_msg, col_btn = st.columns([3, 1])
                with col_msg:
                    st.success(f"**📩 Reply received** — {company}  ·  {subj}")
                with col_btn:
                    if st.button("View", key=f"view_notif_{notif['id']}"):
                        st.switch_page("pages/3_replies.py")
            if len(reply_notifs) > 3:
                st.caption(f"+ {len(reply_notifs)-3} more replies — see Replies page")
    except Exception:
        new_replies = [e for e in sent_log if e.get("replied") and e.get("reply_at")]
        for entry in sorted(new_replies, key=lambda x: x.get("reply_at", ""), reverse=True)[:3]:
            company  = entry.get("company", entry.get("to", ""))
            reply_at = entry.get("reply_at", "")[:10]
            st.success(f"**Reply received** — {company}  ·  {reply_at}")
            has_notifs = True

    try:
        from backend.pipeline.reply_handler import DraftApprovalManager
        pending_drafts = DraftApprovalManager.get_pending_drafts(user_id)
        if pending_drafts:
            has_notifs = True
            st.warning(f"**✏️ {len(pending_drafts)} draft(s) awaiting your approval**")
            if st.button("Review Drafts", key="home_drafts"):
                st.switch_page("pages/3_replies.py")
    except Exception:
        pass

    due_followups = []
    for entry in sent_log:
        if entry.get("replied") or entry.get("followup_count", 0) >= 2:
            continue
        try:
            if (now - datetime.fromisoformat(entry["sent_at"])).days >= 4 and not entry.get("followup_sent"):
                due_followups.append(entry)
        except Exception:
            pass
    if due_followups:
        st.warning(f"**Follow-up due** — {len(due_followups)} email(s) with no reply in 4+ days")
        has_notifs = True
        if st.button("Send Follow Ups Now", key="home_fu"):
            st.switch_page("pages/5_tracker.py")

    long_awaiting = []
    for entry in sent_log:
        if not entry.get("replied") and not entry.get("followup_sent"):
            try:
                if (now - datetime.fromisoformat(entry["sent_at"])).days >= 7:
                    long_awaiting.append(entry)
            except Exception:
                pass
    if long_awaiting:
        st.info(f"**7+ days no reply** — {len(long_awaiting)} companies have not responded")
        has_notifs = True

    if not has_notifs:
        st.caption("No notifications yet. Start cold outreach to see activity here.")

    st.markdown("<br>", unsafe_allow_html=True)
    col_n1, col_n2 = st.columns(2)
    with col_n1:
        if st.button("📬 Replies & Drafts", key="home_replies", use_container_width=True):
            st.switch_page("pages/3_replies.py")
    with col_n2:
        if st.button("📊 Go to Tracker", key="home_tracker", use_container_width=True):
            st.switch_page("pages/5_tracker.py")


# ── Feed panel ────────────────────────────────────────────────────────────────

SOURCE_ICONS = {
    "yc_api"         : "🟠 YC",
    "betalist"       : "🟣 BL",
    "product_hunt"   : "🔴 PH",
    "indie_hackers"  : "🟢 IH",
    "github_trending": "⚫ GH",
    "hn_hiring"      : "🟡 HN",
}

with right:
    st.markdown("### 🆕 New Startups")
    st.caption("🟠 YC &nbsp;·&nbsp; 🟣 BL &nbsp;·&nbsp; 🔴 PH &nbsp;·&nbsp; 🟢 IH &nbsp;·&nbsp; ⚫ GH &nbsp;·&nbsp; 🟡 HN")

    feed_companies = []
    last_updated   = None
    try:
        from backend.utils.feed_to_db import load_feed_companies
        feed_companies = load_feed_companies(user_id, limit=200)
        last_updated   = "live"
    except Exception:
        feed_path = "data/company_feed.json"
        if os.path.exists(feed_path):
            try:
                with open(feed_path, encoding="utf-8") as f:
                    fd = json.load(f)
                feed_companies = fd.get("companies", [])
                last_updated   = fd.get("last_updated", "")
            except Exception:
                pass

    if last_updated and last_updated != "live":
        try:
            lu = datetime.fromisoformat(last_updated)
            st.caption(f"Updated {lu.strftime('%d %b %Y %H:%M')} UTC  ·  {len(feed_companies)} companies waiting")
        except Exception:
            pass
    elif feed_companies:
        st.caption(f"{len(feed_companies)} companies in DB — not yet contacted")

    if not feed_companies:
        st.info("Feed is empty. Click 'Find More Startups' or Refresh Feed.")
    else:
        # Companies with a findable email go first — those are ready for outreach right now.
        feed_companies = sorted(
            feed_companies,
            key=lambda c: not any(ct.get("email") for ct in c.get("contacts", [])),
        )
        for idx, company in enumerate(feed_companies[:12]):
            name     = (company.get("name")     or "").strip()
            website  = (company.get("website")   or "").strip()
            src      = SOURCE_ICONS.get(company.get("source", ""), "⚪")
            contacts = company.get("contacts", [])
            stars    = company.get("github_stars", 0)
            co_db_id = company.get("id")

            full_desc = (
                company.get("company_summary")
                or company.get("one_liner")
                or company.get("description")
                or ""
            ).strip()

            one_liner = (company.get("one_liner") or company.get("description") or "").strip()[:100]

            best_email = best_contact_name = None
            for c in contacts:
                if c.get("email") and c.get("verified"):
                    best_email = c["email"]; best_contact_name = c.get("name", ""); break
            if not best_email:
                for c in contacts:
                    if c.get("email"):
                        best_email = c["email"]; best_contact_name = c.get("name", ""); break
            if best_email and "@www." in best_email:
                best_email = best_email.replace("@www.", "@")

            with st.container(border=True):
                title_parts = [f"**{name}**", src]
                if stars:
                    title_parts.append(f"⭐{stars}")
                st.markdown("  —  ".join(title_parts))

                if one_liner:
                    st.caption(one_liner)

                if full_desc and full_desc != one_liner and len(full_desc) > len(one_liner):
                    st.markdown(
                        f'<div class="desc-box">📋 {full_desc[:220]}{"…" if len(full_desc) > 220 else ""}</div>',
                        unsafe_allow_html=True
                    )

                col_w, col_e = st.columns(2)
                with col_w:
                    if website:
                        st.markdown(f"🔗 [{short_url(website)}]({website})")
                    else:
                        st.caption("No website")
                with col_e:
                    if best_email:
                        verified = any(c.get("verified") and c.get("email") == best_email for c in contacts)
                        icon  = "✅" if verified else "📧"
                        label = f"{best_contact_name}  ·  " if best_contact_name else ""
                        st.caption(f"{icon}  {label}{best_email}")
                    else:
                        st.caption("No email found")

                if not co_db_id:
                    from backend.utils.feed_to_db import save_feed_company_to_db
                    _, co_db_id = save_feed_company_to_db(user_id, company)

                show_key = f"home_show_email_{co_db_id}"
                if not st.session_state.get(show_key):
                    if st.button("✉️ View Email", key=f"feed_outreach_{idx}",
                                 use_container_width=True, type="primary"):
                        st.session_state[show_key] = True
                        st.rerun()
                else:
                    render_email_panel(user_id, co_db_id, company, uid=f"home_{co_db_id}", auto_draft=True)

    st.markdown("<br>", unsafe_allow_html=True)
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if st.button("🚀 Start Outreach", key="home_outreach", use_container_width=True):
            st.switch_page("pages/4_outreach.py")
    with col_b2:
        if st.button("🔄 Refresh Feed", key="home_refresh", use_container_width=True):
            with st.spinner("Refreshing feed..."):
                try:
                    from backend.agents.feed_agent import refresh_feed
                    result = refresh_feed(user_id)
                    if result.get("error"):
                        st.error(f"Refresh failed: {result['error']}")
                    else:
                        st.success(f"{result.get('new', 0)} new companies added to DB")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")