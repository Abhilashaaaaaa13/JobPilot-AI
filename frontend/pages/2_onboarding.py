import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import streamlit as st
import json
from backend.database import SessionLocal
from backend.models.user import UserProfile
from backend.utils.pdf_parser import parse_resume

if "user_id" not in st.session_state:
    st.warning("Pehle login karo")
    st.stop()

user_id = st.session_state["user_id"]

st.title("👤 Setup Your Profile")

# ── Step 1 — Resume Upload ─────────────────────
st.subheader("Step 1 — Resume Upload karo")

uploaded = st.file_uploader("Resume PDF", type=["pdf"])

if uploaded:
    # Save file
    upload_dir = os.path.join("uploads", str(user_id))
    os.makedirs(upload_dir, exist_ok=True)
    resume_path = os.path.join(upload_dir, "resume_base.pdf")

    with open(resume_path, "wb") as f:
        f.write(uploaded.getbuffer())

    with st.spinner("Resume parse ho raha hai..."):
        parsed = parse_resume(resume_path)

    if parsed.get("error"):
        st.error(parsed["error"])
    else:
        st.success("✅ Resume parsed!")
        col1, col2 = st.columns(2)
        col1.metric("Skills Found", len(parsed.get("skills", [])))
        col2.metric("Experience",   f"{parsed.get('experience_years', 0)} years")
        st.session_state["parsed_resume"] = parsed
        st.session_state["resume_path"]   = resume_path

# ── Step 2 — Details Form ──────────────────────
st.divider()
st.subheader("Step 2 — Details Fill karo")

parsed = st.session_state.get("parsed_resume", {})

with st.form("profile_form"):
    col1, col2 = st.columns(2)

    with col1:
        name     = st.text_input("Full Name",  value=parsed.get("name", "") or "")
        phone    = st.text_input("Phone",      value=parsed.get("phone", "") or "")
        linkedin = st.text_input("LinkedIn URL", value=parsed.get("linkedin", "") or "")
        github   = st.text_input("GitHub URL",   value=parsed.get("github", "") or "")
        exp      = st.number_input(
            "Experience (years)",
            min_value = 0,
            max_value = 20,
            value     = parsed.get("experience_years", 0) or 0
        )

    with col2:
        skills = st.text_area(
            "Skills (comma separated)",
            value = ", ".join(parsed.get("skills", []))
        )
        target_roles = st.text_area(
            "Target Roles (comma separated)",
            placeholder = "AI Engineer, ML Intern, Backend Developer"
        )
        target_industries = st.text_area(
            "Target Industries",
            placeholder = "AI, SaaS, Fintech, EdTech"
        )

    st.divider()
    st.subheader("📍 Preferences")

    col3, col4 = st.columns(2)
    with col3:
        locations    = st.text_input(
            "Preferred Locations",
            placeholder = "Remote, Bangalore, Delhi"
        )
        job_type     = st.selectbox("Job Type", ["both", "internship", "job"])
    with col4:
        company_size = st.selectbox("Company Size", ["1-50", "51-200", "201-500", "any"])
        min_score    = st.slider("Minimum Fit Score (%)", 30, 80, 50)

    st.divider()
    st.subheader("📧 Gmail Setup")
    st.caption("Emails bhejne ke liye — App Password use karo, main password nahi")

    gmail   = st.text_input("Gmail Address")
    app_pwd = st.text_input("Gmail App Password", type="password")

    submitted = st.form_submit_button("💾 Save Profile", type="primary")

    if submitted:
        db = SessionLocal()
        try:
            profile = db.query(UserProfile).filter(
                UserProfile.user_id == user_id
            ).first()

            if not profile:
                profile = UserProfile(user_id=user_id)
                db.add(profile)

            profile.name                   = name
            profile.phone                  = phone
            profile.linkedin               = linkedin
            profile.github                 = github
            profile.experience_years       = exp
            profile.skills                 = json.dumps([s.strip() for s in skills.split(",") if s.strip()])
            profile.target_roles           = json.dumps([r.strip() for r in target_roles.split(",") if r.strip()])
            profile.target_industries      = json.dumps([i.strip() for i in target_industries.split(",") if i.strip()])
            profile.preferred_locations    = json.dumps([l.strip() for l in locations.split(",") if l.strip()])
            profile.preferred_type         = job_type
            profile.preferred_company_size = company_size
            profile.min_fit_score          = min_score
            profile.gmail_address          = gmail
            profile.gmail_app_password     = app_pwd
            profile.resume_path            = st.session_state.get("resume_path", "")

            db.commit()
            st.success("✅ Profile saved!")
            st.balloons()
            st.switch_page("pages/3_jobs.py")

        except Exception as e:
            db.rollback()
            st.error(str(e))
        finally:
            db.close()