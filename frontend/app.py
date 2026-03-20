import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import streamlit as st
from backend.database import init_db

init_db()

if "scheduler_started" not in st.session_state:
    try:
        from backend.pipeline.scheduler import create_scheduler
        scheduler = create_scheduler()
        scheduler.start()
    except Exception:
        pass
    st.session_state["scheduler_started"] = True

st.set_page_config(
    page_title = "Job Hunter Agent",
    page_icon  = "🤖",
    layout     = "wide"
)

if "user_id" not in st.session_state:
    from backend.database import SessionLocal
    from backend.models.user import User
    from backend.utils.auth_utils import hash_password, verify_password

    st.title("🤖 Job Hunter Agent")
    st.caption("Agentic AI job hunting system")

    tab1, tab2 = st.tabs(["Login", "Register"])

    with tab2:
        reg_email = st.text_input("Email",    key="reg_email")
        reg_pass  = st.text_input("Password", key="reg_pass", type="password")

        if st.button("Register"):
            if not reg_email or not reg_pass:
                st.error("Email aur password daalo")
            else:
                db = SessionLocal()
                try:
                    existing = db.query(User).filter(
                        User.email == reg_email
                    ).first()
                    if existing:
                        st.error("Email already registered")
                    else:
                        user = User(
                            email           = reg_email,
                            hashed_password = hash_password(reg_pass)
                        )
                        db.add(user)
                        db.commit()
                        st.success("✅ Account created — Login karo")
                except Exception as e:
                    st.error(str(e))
                finally:
                    db.close()

    with tab1:
        login_email = st.text_input("Email",    key="login_email")
        login_pass  = st.text_input("Password", key="login_pass", type="password")

        if st.button("Login"):
            if not login_email or not login_pass:
                st.error("Email aur password daalo")
            else:
                db = SessionLocal()
                try:
                    user = db.query(User).filter(
                        User.email == login_email
                    ).first()
                    if not user:
                        st.error("Email nahi mila — register karo")
                    elif not verify_password(login_pass, user.hashed_password):
                        st.error("Wrong password")
                    elif not user.is_active:
                        st.error("Account inactive")
                    else:
                        st.session_state["user_id"] = user.id
                        st.session_state["email"]   = user.email
                        st.rerun()
                except Exception as e:
                    st.error(str(e))
                finally:
                    db.close()

    st.stop()

# ── Logged In ─────────────────────────────────
with st.sidebar:
    st.title("🤖 Job Hunter")
    st.caption(f"👤 {st.session_state.get('email', '')}")
    st.divider()

    st.page_link("pages/5_dashboard.py", label="📊 Dashboard")
    st.page_link("pages/3_jobs.py",      label="🔍 Jobs & Startups")
    st.page_link("pages/4_review.py",    label="✅ Review")
    st.page_link("pages/2_onboarding.py",label="👤 Profile")

    # Active pipeline indicator
    if st.session_state.get("track_a_thread"):
        st.info("⚡ Track A active")
    if st.session_state.get("track_b_thread"):
        st.info("⚡ Track B active")

    st.divider()
    if st.button("🚪 Logout"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

st.switch_page("pages/5_dashboard.py")