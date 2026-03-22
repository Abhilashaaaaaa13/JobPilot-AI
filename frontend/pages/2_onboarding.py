# frontend/pages/2_onboarding.py

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import json
import streamlit as st
import pdfplumber
from groq import Groq
from dotenv import load_dotenv
load_dotenv()

from backend.database import SessionLocal
from backend.models.user import UserProfile

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

if "user_id" not in st.session_state:
    st.warning("Pehle login karo")
    st.stop()

user_id = st.session_state["user_id"]

st.title("👤 Profile Setup")
st.caption("Apna resume upload karo aur preferences set karo")

# ─────────────────────────────────────────────
# RESUME UPLOAD + SKILL EXTRACTION
# ─────────────────────────────────────────────

st.subheader("📄 Resume Upload")

uploaded = st.file_uploader(
    "Resume upload karo (PDF)",
    type=["pdf"]
)

extracted_skills = []
extracted_roles  = []
resume_text      = ""

if uploaded:
    # Save resume
    upload_dir = f"uploads/{user_id}"
    os.makedirs(upload_dir, exist_ok=True)
    resume_path = f"{upload_dir}/resume_base.pdf"

    with open(resume_path, "wb") as f:
        f.write(uploaded.read())

    # Extract text from PDF
    with st.spinner("Resume read kar rahe hain..."):
        try:
            with pdfplumber.open(resume_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        resume_text += text + "\n"
        except Exception as e:
            st.error(f"PDF read error: {e}")

    if resume_text:
        # Groq se skills + roles extract karo
        with st.spinner("Skills extract kar rahe hain..."):
            try:
                prompt = f"""
You are a resume parser. Extract information from this resume.

Return ONLY a JSON object, no markdown, no explanation:
{{
    "skills": ["skill1", "skill2", ...],
    "target_roles": ["role1", "role2", ...],
    "experience_years": 0,
    "education": "degree and field",
    "current_role": "current or last role",
    "summary": "2-3 line professional summary"
}}

Rules:
- skills: ALL technical skills (languages, frameworks, tools, platforms)
- target_roles: roles this person is suitable for based on their background
- Be comprehensive — extract everything mentioned
- target_roles should be job titles like "AI Engineer", "ML Engineer" etc

Resume:
{resume_text[:4000]}
"""
                res = client.chat.completions.create(
                    model    = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"),
                    messages = [{"role": "user", "content": prompt}],
                    max_tokens  = 800,
                    temperature = 0.1
                )
                raw = res.choices[0].message.content.strip()
                raw = raw.replace("```json", "").replace("```", "").strip()

                parsed           = json.loads(raw)
                extracted_skills = parsed.get("skills", [])
                extracted_roles  = parsed.get("target_roles", [])

                st.session_state["resume_path"]    = resume_path
                st.session_state["resume_text"]    = resume_text
                st.session_state["extracted_skills"] = extracted_skills
                st.session_state["extracted_roles"]  = extracted_roles
                st.session_state["resume_parsed"]    = parsed

                st.success(
                    f"✅ Resume parsed — "
                    f"{len(extracted_skills)} skills, "
                    f"{len(extracted_roles)} roles found"
                )

            except Exception as e:
                st.error(f"Skill extraction error: {e}")
                st.text(f"Raw response: {raw[:300] if 'raw' in dir() else 'N/A'}")

# Show extracted info
if st.session_state.get("resume_parsed"):
    parsed = st.session_state["resume_parsed"]

    col1, col2 = st.columns(2)
    with col1:
        st.info(f"**Current Role:** {parsed.get('current_role', 'N/A')}")
        st.info(f"**Education:** {parsed.get('education', 'N/A')}")
        st.info(f"**Experience:** {parsed.get('experience_years', 0)} years")
    with col2:
        st.info(f"**Summary:** {parsed.get('summary', 'N/A')}")

    st.write("**Extracted Skills:**")
    skills = st.session_state.get("extracted_skills", [])
    st.write(", ".join(skills) if skills else "No skills found")

    st.write("**Suggested Roles:**")
    roles = st.session_state.get("extracted_roles", [])
    st.write(", ".join(roles) if roles else "No roles found")

st.divider()

# ─────────────────────────────────────────────
# JOB PREFERENCES
# ─────────────────────────────────────────────

st.subheader("🎯 Job Preferences")

col1, col2 = st.columns(2)

with col1:
    preferred_type = st.selectbox(
        "Kya dhundh rahe ho?",
        ["both", "internship", "job"],
        format_func=lambda x: {
            "both"      : "Internship + Job dono",
            "internship": "Sirf Internship",
            "job"       : "Sirf Job"
        }[x]
    )

with col2:
    location = st.selectbox(
        "Location Preference",
        ["remote", "india", "anywhere"],
        format_func=lambda x: {
            "remote"  : "Remote Only",
            "india"   : "India Only",
            "anywhere": "Anywhere"
        }[x]
    )

# Domain multi-select
st.write("**Domains** (jo relevant hain select karo)")
domain_options = {
    "ai_ml"      : "🤖 AI / Machine Learning",
    "data_science": "📊 Data Science",
    "software"   : "💻 Software Engineering",
    "backend"    : "⚙️ Backend Development",
    "web_dev"    : "🌐 Web Development",
    "full_stack" : "🔄 Full Stack",
    "product"    : "📱 Product Management",
}

# Default select karo based on extracted roles
default_domains = []
if st.session_state.get("extracted_roles"):
    roles_lower = " ".join(
        st.session_state["extracted_roles"]
    ).lower()
    if any(k in roles_lower for k in ["ai", "ml", "machine learning"]):
        default_domains.append("ai_ml")
    if any(k in roles_lower for k in ["data", "analyst"]):
        default_domains.append("data_science")
    if any(k in roles_lower for k in ["software", "engineer"]):
        default_domains.append("software")
    if any(k in roles_lower for k in ["backend", "python", "django"]):
        default_domains.append("backend")
    if any(k in roles_lower for k in ["web", "frontend", "react"]):
        default_domains.append("web_dev")
    if any(k in roles_lower for k in ["full stack", "fullstack"]):
        default_domains.append("full_stack")

selected_domains = []
cols = st.columns(3)
for i, (key, label) in enumerate(domain_options.items()):
    with cols[i % 3]:
        if st.checkbox(
            label,
            value = key in default_domains,
            key   = f"domain_{key}"
        ):
            selected_domains.append(key)

# Target roles — editable
st.write("**Target Roles** (edit kar sakte ho)")
default_roles_text = ", ".join(
    st.session_state.get("extracted_roles", [
        "Software Engineer", "AI Engineer"
    ])
)
target_roles_text = st.text_area(
    "Roles (comma separated)",
    value  = default_roles_text,
    height = 80,
    help   = "Resume se auto-fill hua hai — edit kar sakte ho"
)

# Additional skills — editable
st.write("**Skills** (edit kar sakte ho)")
default_skills_text = ", ".join(
    st.session_state.get("extracted_skills", [])
)
skills_text = st.text_area(
    "Skills (comma separated)",
    value  = default_skills_text,
    height = 80,
    help   = "Resume se auto-fill hua hai"
)

st.divider()

# ─────────────────────────────────────────────
# GMAIL SETTINGS
# ─────────────────────────────────────────────

st.subheader("📧 Gmail Settings")
st.caption(
    "Email bhejne ke liye Gmail App Password chahiye. "
    "[Setup guide](https://support.google.com/accounts/answer/185833)"
)

col1, col2 = st.columns(2)
with col1:
    gmail_address = st.text_input(
        "Gmail Address",
        placeholder="yourname@gmail.com"
    )
with col2:
    gmail_password = st.text_input(
        "App Password",
        type       = "password",
        placeholder= "xxxx xxxx xxxx xxxx"
    )

st.divider()

# ─────────────────────────────────────────────
# SAVE
# ─────────────────────────────────────────────

if st.button("💾 Save Profile", type="primary"):

    # Validation
    if not selected_domains:
        st.error("Kam se kam ek domain select karo")
        st.stop()

    if not target_roles_text.strip():
        st.error("Target roles likho")
        st.stop()

    target_roles = [
        r.strip()
        for r in target_roles_text.split(",")
        if r.strip()
    ]
    skills = [
        s.strip()
        for s in skills_text.split(",")
        if s.strip()
    ]

    # Prefs save karo session mein
    prefs = {
        "preferred_type" : preferred_type,
        "domains"        : selected_domains,
        "target_roles"   : target_roles,
        "skills"         : skills,
        "location"       : location,
    }
    st.session_state["prefs"]      = prefs
    st.session_state["gmail"]      = gmail_address
    st.session_state["gmail_pass"] = gmail_password

    # DB mein save karo
    db = SessionLocal()
    try:
        profile = db.query(UserProfile).filter(
            UserProfile.user_id == user_id
        ).first()

        if not profile:
            profile = UserProfile(user_id=user_id)
            db.add(profile)

        profile.preferred_type      = preferred_type
        profile.preferred_locations = json.dumps([location])
        profile.target_roles        = json.dumps(target_roles)
        profile.skills              = json.dumps(skills)
        profile.domains             = json.dumps(selected_domains)
        profile.resume_path         = st.session_state.get(
            "resume_path", ""
        )
        profile.gmail_address       = gmail_address
        profile.min_fit_score       = 50

        db.commit()
        st.success("✅ Profile saved!")
        st.switch_page("pages/3_apply.py")

    except Exception as e:
        st.error(f"Save error: {e}")
    finally:
        db.close()