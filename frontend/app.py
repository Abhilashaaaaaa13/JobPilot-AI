# frontend/app.py
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import streamlit as st
from datetime import datetime
from backend.database import init_db

init_db()

# ── Scheduler startup ─────────────────────────
if "scheduler" not in st.session_state:
    try:
        from backend.pipeline.scheduler import create_scheduler
        _scheduler = create_scheduler()
        _scheduler.start()
        st.session_state["scheduler"] = _scheduler
    except Exception as e:
        st.session_state["scheduler"] = None
        st.session_state["scheduler_error"] = str(e)
# ─────────────────────────────────────────────

st.set_page_config(
    page_title="OutreachAI",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap');
:root{--bg:#0d0d0d;--surface:#161616;--border:#2a2a2a;--accent:#e8ff47;--text:#f0f0f0;--muted:#666;--success:#4ade80;--warning:#fbbf24}
html,body,[data-testid="stAppViewContainer"]{background:var(--bg)!important;color:var(--text)!important;font-family:'DM Sans',sans-serif!important}
[data-testid="stSidebar"]{background:var(--surface)!important;border-right:1px solid var(--border)!important}
h1,h2,h3{font-family:'Space Mono',monospace!important;letter-spacing:-.03em!important}
.stButton>button{background:var(--accent)!important;color:#000!important;border:none!important;border-radius:4px!important;font-family:'Space Mono',monospace!important;font-weight:700!important;font-size:13px!important;padding:10px 20px!important;transition:all .15s!important}
.stButton>button:hover{background:#fff!important;transform:translateY(-1px)!important}
.stButton>button[kind="secondary"]{background:transparent!important;color:var(--text)!important;border:1px solid var(--border)!important}
.stButton>button[kind="secondary"]:hover{border-color:var(--accent)!important;color:var(--accent)!important}
.stTextInput>div>div>input,.stTextArea>div>div>textarea{background:var(--surface)!important;border:1px solid var(--border)!important;color:var(--text)!important;border-radius:4px!important}
.stTextInput>div>div>input:focus,.stTextArea>div>div>textarea:focus{border-color:var(--accent)!important;box-shadow:0 0 0 2px rgba(232,255,71,.1)!important}
.stTabs [data-baseweb="tab-list"]{background:transparent!important;border-bottom:1px solid var(--border)!important;gap:0!important}
.stTabs [data-baseweb="tab"]{background:transparent!important;color:var(--muted)!important;font-family:'Space Mono',monospace!important;font-size:12px!important;border-bottom:2px solid transparent!important;padding:10px 20px!important}
.stTabs [aria-selected="true"]{color:var(--accent)!important;border-bottom-color:var(--accent)!important}
.stMetric{background:var(--surface)!important;border:1px solid var(--border)!important;border-radius:6px!important;padding:16px!important}
.stMetric label{color:var(--muted)!important;font-size:11px!important;text-transform:uppercase;letter-spacing:.1em}
.stMetric [data-testid="metric-container"]>div:nth-child(2){color:var(--accent)!important;font-family:'Space Mono',monospace!important;font-size:28px!important}
.stExpander{border:1px solid var(--border)!important;border-radius:6px!important;background:var(--surface)!important}
[data-testid="stSidebarNav"]{display:none!important}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# AUTH HELPERS
# ─────────────────────────────────────────────

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


# ─────────────────────────────────────────────
# AUTO LOGIN
# ─────────────────────────────────────────────

if "user_id" not in st.session_state:
    saved = _remember_me_load()
    if saved:
        st.session_state["user_id"] = saved["user_id"]
        st.session_state["email"]   = saved["email"]

# ─────────────────────────────────────────────
# AUTH GATE
# ─────────────────────────────────────────────

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
                    st.error("Email aur password daalo")
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
                    st.error("Sab fields fill karo")
                elif reg_pass != reg_pass2:
                    st.error("Passwords match nahi karte")
                elif len(reg_pass) < 6:
                    st.error("Password 6+ characters hona chahiye")
                else:
                    ok, result = register_user(reg_email, reg_pass)
                    if ok:
                        st.session_state["user_id"] = result.id
                        st.session_state["email"]   = result.email
                        _remember_me_save(result.id, result.email)
                        st.success("Account ready!")
                        st.switch_page("pages/2_onboarding.py")
                    else:
                        st.error(result)
    st.stop()


# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────

with st.sidebar:
    st.markdown("### ⚡ OutreachAI")
    st.caption(st.session_state.get("email", ""))
    st.divider()
    st.page_link("app.py",                label="⚡  Home",          use_container_width=True)
    st.page_link("pages/2_onboarding.py", label="👤  Profile Setup", use_container_width=True)
    st.page_link("pages/4_outreach.py",   label="🚀  Cold Outreach", use_container_width=True)
    st.page_link("pages/5_tracker.py",    label="📊  Tracker",       use_container_width=True)
    st.divider()

    user_id  = st.session_state["user_id"]
    log_file = f"uploads/{user_id}/sent_emails/log.json"
    if os.path.exists(log_file):
        try:
            with open(log_file, encoding="utf-8") as f:
                _log = json.load(f)
            st.metric("Emails Sent", len(_log))
            st.metric("Replies",     sum(1 for e in _log if e.get("replied")))
        except Exception:
            pass

    # ── Scheduler status — sidebar mein ──────
    st.divider()
    sched = st.session_state.get("scheduler")
    if sched and sched.running:
        st.markdown(
            '<p style="color:#4ade80;font-size:11px;font-family:\'Space Mono\',monospace;margin:0">'
            '🟢 AUTO-CHECK ON</p>',
            unsafe_allow_html=True
        )
        jobs = sched.get_jobs()
        for job in jobs:
            if job.next_run_time:
                label = {"reply_check": "Replies", "followup_check": "Follow ups", "company_feed_refresh": "Feed"}.get(job.id, job.id)
                next_t = job.next_run_time.strftime("%H:%M")
                st.markdown(
                    f'<p style="color:#555;font-size:10px;font-family:\'Space Mono\',monospace;margin:2px 0">'
                    f'· {label}: {next_t}</p>',
                    unsafe_allow_html=True
                )
    else:
        err = st.session_state.get("scheduler_error", "")
        st.markdown(
            '<p style="color:#f87171;font-size:11px;font-family:\'Space Mono\',monospace;margin:0">'
            '🔴 SCHEDULER OFF</p>',
            unsafe_allow_html=True
        )
        if err:
            st.caption(f"Error: {err[:60]}")

    st.divider()
    if st.button("Logout", key="logout_btn", use_container_width=True):
        _remember_me_clear()
        # Scheduler band karo logout pe
        sched = st.session_state.get("scheduler")
        if sched and sched.running:
            try:
                sched.shutdown(wait=False)
            except Exception:
                pass
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()


# ─────────────────────────────────────────────
# PROFILE CHECK
# ─────────────────────────────────────────────

user_id = st.session_state["user_id"]
st.markdown("# ⚡ Dashboard")

from backend.database import SessionLocal
from backend.models.user import UserProfile
db      = SessionLocal()
profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
db.close()

if not profile or not profile.resume_path:
    st.warning("Profile setup incomplete — resume upload karo taaki outreach start ho sake.")
    if st.button("Complete Profile Setup", type="primary"):
        st.switch_page("pages/2_onboarding.py")
    st.stop()


# ─────────────────────────────────────────────
# LOAD SENT LOG
# ─────────────────────────────────────────────

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


# ─────────────────────────────────────────────
# STATS ROW
# ─────────────────────────────────────────────

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Emails Sent", total_sent)
c2.metric("Replied",     replied)
c3.metric("Awaiting",    awaiting)
c4.metric("Follow Ups",  followups)
c5.metric("Reply Rate",  reply_rate)

st.markdown("<br>", unsafe_allow_html=True)
left, right = st.columns([1, 1.4], gap="large")


# ─────────────────────────────────────────────
# LEFT — NOTIFICATIONS
# ─────────────────────────────────────────────

with left:
    st.markdown("### 🔔 Notifications")
    has_notifs = False
    now = datetime.utcnow()

    new_replies = [e for e in sent_log if e.get("replied") and e.get("reply_at")]
    for entry in sorted(new_replies, key=lambda x: x.get("reply_at", ""), reverse=True)[:3]:
        company  = entry.get("company", entry.get("to", ""))
        reply_at = entry.get("reply_at", "")[:10]
        st.success(f"**Reply received** — {company}  ·  {reply_at}")
        has_notifs = True

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
        st.warning(f"**Follow-up due** — {len(due_followups)} email(s), 4+ din se reply nahi")
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
        st.info(f"**7+ days no reply** — {len(long_awaiting)} companies ghosting")
        has_notifs = True

    if not has_notifs:
        st.caption("No notifications yet. Start cold outreach to see activity here.")

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Go to Tracker", key="home_tracker", use_container_width=True):
        st.switch_page("pages/5_tracker.py")


# ─────────────────────────────────────────────
# RIGHT — NEW STARTUPS FEED
# ─────────────────────────────────────────────

with right:
    st.markdown("### 🆕 New Startups")

    feed_path      = "data/company_feed.json"
    feed_companies = []
    last_updated   = None

    if os.path.exists(feed_path):
        try:
            with open(feed_path, encoding="utf-8") as f:
                fd = json.load(f)
            feed_companies = fd.get("companies", [])
            last_updated   = fd.get("last_updated", "")
        except Exception:
            pass

    contacted_names   = set()
    contacted_domains = set()
    for entry in sent_log:
        n = (entry.get("company") or entry.get("to") or "").lower().strip()
        if n:
            contacted_names.add(n)
        w = (entry.get("website") or "").lower()
        if w:
            d = w.replace("https://","").replace("http://","").rstrip("/").split("/")[0]
            if d:
                contacted_domains.add(d)

    def _is_fresh(c):
        if (c.get("name") or "").lower().strip() in contacted_names:
            return False
        w = (c.get("website") or "").lower()
        if w:
            d = w.replace("https://","").replace("http://","").rstrip("/").split("/")[0]
            if d and d in contacted_domains:
                return False
        return True

    fresh  = [c for c in feed_companies if _is_fresh(c)]
    hidden = len(feed_companies) - len(fresh)

    if last_updated:
        try:
            lu   = datetime.fromisoformat(last_updated)
            note = f"Updated {lu.strftime('%d %b %Y %H:%M')} UTC"
            if hidden:
                note += f"  ·  {hidden} already contacted (hidden)"
            st.caption(note)
        except Exception:
            pass

    if not fresh:
        msg = "Saari companies outreach ho chuki hain! Refresh karo nayi laane ke liye." \
              if feed_companies else "Feed empty hai. Refresh Feed karo."
        st.info(msg)

    else:
        source_label = {"yc_api": "YC", "betalist": "Betalist", "product_hunt": "Product Hunt"}

        for idx, company in enumerate(fresh[:8]):
            name     = (company.get("name")     or "").strip()
            desc     = (company.get("one_liner") or company.get("description") or "").strip()[:120]
            website  = (company.get("website")   or "").strip()
            src      = source_label.get(company.get("source", ""), "")
            contacts = company.get("contacts", [])

            best_email        = None
            best_contact_name = None
            for c in contacts:
                if c.get("email") and c.get("verified"):
                    best_email        = c["email"]
                    best_contact_name = c.get("name", "")
                    break
            if not best_email:
                for c in contacts:
                    if c.get("email"):
                        best_email        = c["email"]
                        best_contact_name = c.get("name", "")
                        break
            if best_email and "@www." in best_email:
                best_email = best_email.replace("@www.", "@")

            with st.container(border=True):
                title = f"**{name}**"
                if src:
                    title += f"  —  {src}"
                st.markdown(title)

                if desc:
                    st.caption(desc)

                col_w, col_e = st.columns(2)
                with col_w:
                    if website:
                        display = website.replace("https://","").replace("http://","").rstrip("/").split("/")[0]
                        st.markdown(f"🔗 [{display}]({website})")
                    else:
                        st.caption("No website")
                with col_e:
                    if best_email:
                        verified = any(c.get("verified") and c.get("email") == best_email for c in contacts)
                        icon     = "✅" if verified else "📧"
                        label    = f"{best_contact_name}  ·  " if best_contact_name else ""
                        st.caption(f"{icon}  {label}{best_email}")
                    else:
                        st.caption("No email found")

                if st.button(
                    "✉️ Outreach Karo",
                    key  = f"feed_outreach_{idx}",
                    use_container_width = True,
                    type = "primary",
                ):
                    from backend.utils.feed_to_db import save_feed_company_to_db
                    _, co_id = save_feed_company_to_db(user_id, company)
                    st.session_state["feed_outreach_company"] = company
                    st.session_state["feed_outreach_co_id"]   = co_id
                    st.switch_page("pages/4_outreach.py")

    st.markdown("<br>", unsafe_allow_html=True)
    col_b1, col_b2 = st.columns(2)
    with col_b1:
        if st.button("🚀 Outreach Page", key="home_outreach", use_container_width=True):
            st.switch_page("pages/4_outreach.py")
    with col_b2:
        if st.button("🔄 Refresh Feed", key="home_refresh", use_container_width=True):
            with st.spinner("Feed refresh ho raha hai..."):
                try:
                    from backend.agents.feed_agent import refresh_feed
                    result = refresh_feed()
                    st.success(f"{result['new']} new companies added")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")