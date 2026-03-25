# frontend/pages/2_onboarding.py

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import json
import streamlit as st
import pdfplumber
from groq   import Groq
from dotenv import load_dotenv
load_dotenv()

from backend.database    import SessionLocal
from backend.models.user import UserProfile

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ── Auth check ────────────────────────────────
if "user_id" not in st.session_state:
    st.warning("Pehle login karo")
    st.stop()

user_id = st.session_state["user_id"]

# ── Check if already done — let them edit still ──
db      = SessionLocal()
profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
db.close()

already_setup = profile and profile.resume_path

# ─────────────────────────────────────────────
# CSS (inherits from app.py if multi-page)
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap');
html, body, [data-testid="stAppViewContainer"] { background:#0d0d0d!important; color:#f0f0f0!important; font-family:'DM Sans',sans-serif!important; }
[data-testid="stSidebar"] { background:#161616!important; border-right:1px solid #2a2a2a!important; }
h1,h2,h3 { font-family:'Space Mono',monospace!important; }
.stButton>button { background:#e8ff47!important; color:#000!important; border:none!important; border-radius:4px!important; font-family:'Space Mono',monospace!important; font-weight:700!important; }
.stButton>button[kind="secondary"] { background:transparent!important; color:#f0f0f0!important; border:1px solid #2a2a2a!important; }
.stTextInput>div>div>input, .stTextArea>div>div>textarea { background:#161616!important; border:1px solid #2a2a2a!important; color:#f0f0f0!important; }
.stSelectbox>div>div { background:#161616!important; border-color:#2a2a2a!important; color:#f0f0f0!important; }
[data-testid="stSidebarNav"] { display:none!important; }
.step-header { font-family:'Space Mono',monospace; font-size:11px; text-transform:uppercase; letter-spacing:0.15em; color:#666; margin-bottom:8px; }
.filled-badge { background:rgba(74,222,128,0.1); color:#4ade80; border:1px solid rgba(74,222,128,0.3); border-radius:3px; padding:2px 8px; font-size:11px; font-family:'Space Mono',monospace; }
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

# ── Header ────────────────────────────────────
st.markdown("# 👤 Profile Setup")
if already_setup:
    st.markdown(
        '<span class="filled-badge">✓ Profile saved — editing</span>',
        unsafe_allow_html=True
    )
else:
    st.caption("Ek baar setup karo — phir outreach start karo")

st.markdown("<br>", unsafe_allow_html=True)

# ═════════════════════════════════════════════
# STEP 1 — RESUME
# ═════════════════════════════════════════════

st.markdown('<p class="step-header">Step 1 — Resume</p>', unsafe_allow_html=True)

# Pre-fill from DB
existing_resume = profile.resume_path if profile else ""
if existing_resume and os.path.exists(existing_resume):
    st.markdown(
        f'<span class="filled-badge">✓ Resume already uploaded</span>&nbsp;'
        f'<span style="color:#666;font-size:12px">{os.path.basename(existing_resume)}</span>',
        unsafe_allow_html=True
    )
    st.markdown("<br>", unsafe_allow_html=True)

uploaded = st.file_uploader(
    "Resume upload karo (PDF)" if not existing_resume else "Replace resume (optional)",
    type=["pdf"]
)

extracted_skills = []
extracted_roles  = []
resume_text      = ""

if uploaded:
    upload_dir  = f"uploads/{user_id}"
    os.makedirs(upload_dir, exist_ok=True)
    resume_path = f"{upload_dir}/resume_base.pdf"

    with open(resume_path, "wb") as f:
        f.write(uploaded.read())

    with st.spinner("Resume parse kar rahe hain..."):
        try:
            with pdfplumber.open(resume_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        resume_text += text + "\n"
        except Exception as e:
            st.error(f"PDF read error: {e}")

    if resume_text:
        with st.spinner("Skills extract ho rahi hain..."):
            try:
                prompt = f"""
You are a resume parser. Extract information from this resume.

Return ONLY a JSON object, no markdown, no explanation:
{{
    "name": "full name",
    "skills": ["skill1", "skill2"],
    "target_roles": ["AI Engineer", "ML Engineer"],
    "experience_years": 0,
    "education": "degree and college",
    "current_role": "current or last role",
    "summary": "2-3 line professional summary",
    "key_project": "most impressive project in 1 line with impact"
}}

Resume:
{resume_text[:4000]}
"""
                res = client.chat.completions.create(
                    model       = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"),
                    messages    = [{"role": "user", "content": prompt}],
                    max_tokens  = 800,
                    temperature = 0.1
                )
                raw    = res.choices[0].message.content.strip()
                raw    = raw.replace("```json","").replace("```","").strip()
                parsed = json.loads(raw)

                extracted_skills = parsed.get("skills",       [])
                extracted_roles  = parsed.get("target_roles", [])

                st.session_state["resume_path"]      = resume_path
                st.session_state["resume_text"]      = resume_text
                st.session_state["extracted_skills"] = extracted_skills
                st.session_state["extracted_roles"]  = extracted_roles
                st.session_state["resume_parsed"]    = parsed

                st.success(
                    f"✅ {len(extracted_skills)} skills, "
                    f"{len(extracted_roles)} roles extracted"
                )
            except Exception as e:
                st.error(f"Parse error: {e}")

# Show extracted or existing data
parsed_data = st.session_state.get("resume_parsed", {})
if parsed_data:
    with st.expander("Parsed resume — verify karo", expanded=False):
        c1, c2, c3 = st.columns(3)
        c1.info(f"**Role:** {parsed_data.get('current_role','N/A')}")
        c2.info(f"**Exp:** {parsed_data.get('experience_years',0)} yrs")
        c3.info(f"**Education:** {parsed_data.get('education','N/A')[:30]}")
        if parsed_data.get("summary"):
            st.caption(f"**Summary:** {parsed_data['summary']}")
        if parsed_data.get("key_project"):
            st.caption(f"**Key Project:** {parsed_data['key_project']}")

elif profile and profile.skills:
    try:
        existing_sk = json.loads(profile.skills)
        if existing_sk:
            st.caption(f"Existing skills: {', '.join(existing_sk[:8])}...")
    except Exception:
        pass

st.divider()

# ═════════════════════════════════════════════
# STEP 2 — ONE LINER
# ═════════════════════════════════════════════

st.markdown('<p class="step-header">Step 2 — Your One Liner</p>', unsafe_allow_html=True)
st.caption("Cold email mein sender intro ke liye use hoga")

default_one_liner = ""
if profile and profile.one_liner:
    default_one_liner = profile.one_liner
elif parsed_data.get("summary"):
    # Auto-suggest from resume
    default_one_liner = parsed_data["summary"][:100]

one_liner = st.text_input(
    "Ek line mein apne aap ko describe karo",
    value       = default_one_liner,
    placeholder = "Final year CS student | built 3 RAG systems | LangChain expert",
    max_chars   = 150,
    help        = "Max 150 chars. Resume summary se auto-filled hua hai — edit karo."
)
st.caption(f"{len(one_liner)}/150 characters")

st.divider()

# ═════════════════════════════════════════════
# STEP 3 — PREFERENCES
# ═════════════════════════════════════════════

st.markdown('<p class="step-header">Step 3 — Preferences</p>', unsafe_allow_html=True)

col1, col2 = st.columns(2)
with col1:
    preferred_type = st.selectbox(
        "Kya dhundh rahe ho?",
        ["job", "internship", "both"],
        index = 0 if not profile else (
            ["job","internship","both"].index(profile.preferred_type or "job")
            if profile.preferred_type in ["job","internship","both"] else 0
        ),
        format_func=lambda x: {
            "both"      : "Internship + Job dono",
            "internship": "Sirf Internship",
            "job"       : "Sirf Job"
        }[x]
    )
with col2:
    location = st.selectbox(
        "Location",
        ["remote", "india", "anywhere"],
        format_func=lambda x: {
            "remote"  : "Remote Only",
            "india"   : "India / Hybrid",
            "anywhere": "Anywhere"
        }[x]
    )

# Domains
st.markdown("<br>", unsafe_allow_html=True)
st.write("**Domains** (select all that apply)")

domain_options = {
    "ai_ml"       : "🤖 AI / ML",
    "data_science": "📊 Data Science",
    "software"    : "💻 Software Eng",
    "backend"     : "⚙️ Backend",
    "web_dev"     : "🌐 Web Dev",
    "full_stack"  : "🔄 Full Stack",
    "product"     : "📱 Product",
}

# Auto-detect defaults from extracted roles
default_domains = []
if profile and profile.target_industries:
    try:
        default_domains = json.loads(profile.target_industries)
    except Exception:
        pass
elif st.session_state.get("extracted_roles"):
    roles_lower = " ".join(st.session_state["extracted_roles"]).lower()
    if any(k in roles_lower for k in ["ai","ml","machine learning","nlp","llm"]):
        default_domains.append("ai_ml")
    if any(k in roles_lower for k in ["data","analyst","science"]):
        default_domains.append("data_science")
    if any(k in roles_lower for k in ["software","engineer","swe"]):
        default_domains.append("software")
    if any(k in roles_lower for k in ["backend","python","django","api"]):
        default_domains.append("backend")
    if any(k in roles_lower for k in ["web","frontend","react","next"]):
        default_domains.append("web_dev")
    if any(k in roles_lower for k in ["full stack","fullstack","mern"]):
        default_domains.append("full_stack")

selected_domains = []
cols = st.columns(4)
for i, (key, label) in enumerate(domain_options.items()):
    with cols[i % 4]:
        if st.checkbox(label, value=(key in default_domains), key=f"dom_{key}"):
            selected_domains.append(key)

st.markdown("<br>", unsafe_allow_html=True)

# Target roles
existing_roles = ""
if profile and profile.target_roles:
    try:
        existing_roles = ", ".join(json.loads(profile.target_roles))
    except Exception:
        pass
if not existing_roles and st.session_state.get("extracted_roles"):
    existing_roles = ", ".join(st.session_state["extracted_roles"])

target_roles_text = st.text_area(
    "Target Roles (comma separated)",
    value  = existing_roles or "AI Engineer, ML Engineer, Backend Engineer",
    height = 80,
    help   = "Resume se auto-fill hua — edit kar sakte ho"
)

# Skills
existing_skills = ""
if profile and profile.skills:
    try:
        existing_skills = ", ".join(json.loads(profile.skills))
    except Exception:
        pass
if not existing_skills and st.session_state.get("extracted_skills"):
    existing_skills = ", ".join(st.session_state["extracted_skills"])

skills_text = st.text_area(
    "Skills (comma separated)",
    value  = existing_skills,
    height = 80,
    help   = "Resume se auto-fill hua — edit kar sakte ho"
)

st.divider()

# ═════════════════════════════════════════════
# STEP 4 — GMAIL
# ═════════════════════════════════════════════

st.markdown('<p class="step-header">Step 4 — Gmail (for sending emails)</p>', unsafe_allow_html=True)
st.caption(
    "Outreach emails tumhari Gmail se jaayengi. "
    "[App Password setup guide ↗](https://support.google.com/accounts/answer/185833)"
)

existing_gmail = profile.gmail_address if profile else ""
if existing_gmail:
    st.markdown(
        f'<span class="filled-badge">✓ Gmail connected: {existing_gmail}</span>',
        unsafe_allow_html=True
    )
    st.markdown("<br>", unsafe_allow_html=True)

col1, col2 = st.columns(2)
with col1:
    gmail_address = st.text_input(
        "Gmail Address",
        value       = existing_gmail or "",
        placeholder = "yourname@gmail.com"
    )
with col2:
    gmail_password = st.text_input(
        "App Password",
        type        = "password",
        placeholder = "xxxx xxxx xxxx xxxx (spaces ok)",
        help        = "Google Account → Security → App Passwords"
    )

st.divider()

# ═════════════════════════════════════════════
# SAVE BUTTON
# ═════════════════════════════════════════════

col_save, col_skip = st.columns([2, 1])

with col_save:
    save_clicked = st.button(
        "💾 Save Profile →",
        type             = "primary",
        use_container_width = True
    )

with col_skip:
    if already_setup:
        if st.button("Cancel", use_container_width=True):
            st.switch_page("app.py")

if save_clicked:
    # Validation
    if not selected_domains:
        st.error("Kam se kam ek domain select karo")
        st.stop()
    if not target_roles_text.strip():
        st.error("Target roles daalo")
        st.stop()

    resume_path_to_save = st.session_state.get(
        "resume_path",
        profile.resume_path if profile else ""
    )
    if not resume_path_to_save:
        st.error("Resume upload karo — required hai")
        st.stop()

    target_roles = [r.strip() for r in target_roles_text.split(",") if r.strip()]
    skills       = [s.strip() for s in skills_text.split(",")       if s.strip()]

    prefs = {
        "preferred_type": preferred_type,
        "domains"       : selected_domains,
        "target_roles"  : target_roles,
        "skills"        : skills,
        "location"      : location,
    }
    st.session_state["prefs"] = prefs

    db = SessionLocal()
    try:
        prof = db.query(UserProfile).filter(
            UserProfile.user_id == user_id
        ).first()

        if not prof:
            prof = UserProfile(user_id=user_id)
            db.add(prof)

        prof.one_liner            = one_liner.strip()
        prof.preferred_type       = preferred_type
        prof.preferred_locations  = json.dumps([location])
        prof.target_roles         = json.dumps(target_roles)
        prof.target_industries    = json.dumps(selected_domains)
        prof.skills               = json.dumps(skills)
        prof.resume_path          = resume_path_to_save

        parsed = st.session_state.get("resume_parsed", {})
        if parsed.get("experience_years") is not None:
            prof.experience_years = parsed["experience_years"]
        if parsed.get("education"):
            prof.education = parsed["education"]
        if parsed.get("name") and not prof.name:
            prof.name = parsed["name"]

        if gmail_address:
            prof.gmail_address = gmail_address
        if gmail_password:
            prof.gmail_app_password = gmail_password.replace(" ", "")

        db.commit()
        st.success("✅ Profile saved!")
        st.switch_page("pages/4_outreach.py")

    except Exception as e:
        st.error(f"Save error: {e}")
    finally:
        db.close()