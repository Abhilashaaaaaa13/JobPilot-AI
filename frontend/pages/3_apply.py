# frontend/pages/3_apply.py

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import streamlit as st
from loguru import logger

if "user_id" not in st.session_state:
    st.warning("Pehle login karo")
    st.stop()

user_id = st.session_state["user_id"]

st.title("💼 Direct Apply")
st.caption("Jobs aur internships dhundho — directly apply karo")

# ── Preferences ───────────────────────────────
with st.expander("⚙️ Search Preferences", expanded=True):
    col1, col2 = st.columns(2)

    with col1:
        pref_type = st.selectbox(
            "Kya dhundh rahe ho?",
            ["both", "internship", "job"],
            index = ["both", "internship", "job"].index(
                st.session_state.get("pref_type", "both")
            ),
            format_func = lambda x: {
                "both"      : "Internship + Job dono",
                "internship": "Sirf Internship",
                "job"       : "Sirf Job"
            }[x]
        )
        st.session_state["pref_type"] = pref_type

    with col2:
        location = st.selectbox(
            "Location",
            ["remote", "india", "anywhere"],
            format_func = lambda x: {
                "remote"  : "Remote Only",
                "india"   : "India Only",
                "anywhere": "Anywhere"
            }[x]
        )

    domain_options = {
        "ai_ml"      : "🤖 AI / ML",
        "data_science": "📊 Data Science",
        "software"   : "💻 Software Engg",
        "backend"    : "⚙️ Backend",
        "web_dev"    : "🌐 Web Dev",
        "full_stack" : "🔄 Full Stack",
        "product"    : "📱 Product Mgmt",
    }

    st.write("**Domains:**")
    cols        = st.columns(4)
    sel_domains = []
    saved       = st.session_state.get("sel_domains", ["ai_ml"])

    for i, (key, label) in enumerate(domain_options.items()):
        with cols[i % 4]:
            if st.checkbox(
                label,
                value = key in saved,
                key   = f"dom_a_{key}"
            ):
                sel_domains.append(key)

    if not sel_domains:
        sel_domains = ["ai_ml"]
    st.session_state["sel_domains"] = sel_domains

    target_roles = st.text_input(
        "Target Roles (comma separated)",
        value = st.session_state.get(
            "target_roles_text",
            "AI Engineer, ML Engineer, Data Scientist"
        )
    )
    st.session_state["target_roles_text"] = target_roles

prefs = {
    "preferred_type": pref_type,
    "domains"       : sel_domains,
    "target_roles"  : [
        r.strip() for r in target_roles.split(",") if r.strip()
    ],
    "location"      : location,
}
st.session_state["prefs"] = prefs

type_label = {
    "both"      : "Jobs + Internships",
    "internship": "Internships",
    "job"       : "Jobs"
}[pref_type]

st.divider()

# ── Find Button ───────────────────────────────
if st.button(f"🔍 Find {type_label}", type="primary"):
    st.session_state["jobs_stage"]    = "internshala"
    st.session_state["scraped_jobs"]  = []
    st.session_state["selected_jobs"] = {}
    st.rerun()

# ── Streaming — Source by Source ──────────────
stage = st.session_state.get("jobs_stage", "idle")

if stage not in ["idle", "done"]:
    from backend.agents.scraper_agent import (
        stream_internshala,
        stream_remotive,
        stream_unstop,
        stream_yc_jobs,
    )

    if stage == "internshala":
        with st.spinner("🟢 Internshala scraping..."):
            try:
                for job in stream_internshala(prefs):
                    st.session_state["scraped_jobs"].append(job)
            except Exception as e:
                logger.error(f"Internshala error: {e}")
        st.session_state["jobs_stage"] = "remotive"
        st.rerun()

    elif stage == "remotive":
        with st.spinner("🔵 Remotive scraping..."):
            try:
                for job in stream_remotive(prefs):
                    st.session_state["scraped_jobs"].append(job)
            except Exception as e:
                logger.error(f"Remotive error: {e}")
        st.session_state["jobs_stage"] = "unstop"
        st.rerun()

    elif stage == "unstop":
        with st.spinner("🟡 Unstop scraping..."):
            try:
                for job in stream_unstop(prefs):
                    st.session_state["scraped_jobs"].append(job)
            except Exception as e:
                logger.error(f"Unstop error: {e}")
        st.session_state["jobs_stage"] = "yc_jobs"
        st.rerun()

    elif stage == "yc_jobs":
        with st.spinner("🟠 YC Jobs scraping..."):
            try:
                for job in stream_yc_jobs(prefs):
                    st.session_state["scraped_jobs"].append(job)
            except Exception as e:
                logger.error(f"YC Jobs error: {e}")
        st.session_state["jobs_stage"] = "done"
        st.rerun()

# ── Results ───────────────────────────────────
jobs = st.session_state.get("scraped_jobs", [])

if stage == "idle" and not jobs:
    st.info(f"'Find {type_label}' dabao")
    st.stop()

# Progress indicator
stage_labels = {
    "internshala": ("🟢 Internshala", 1),
    "remotive"   : ("🔵 Remotive",    2),
    "unstop"     : ("🟡 Unstop",      3),
    "yc_jobs"    : ("🟠 YC Jobs",     4),
    "done"       : ("✅ Done",         4),
}

if stage != "idle":
    label, step = stage_labels.get(stage, ("", 0))
    st.progress(step / 4)

    if stage != "done":
        st.info(f"⏳ {label} scraping... {len(jobs)} jobs mile abhi tak")
    else:
        st.success(f"✅ {len(jobs)} {type_label} mile!")

if not jobs:
    st.stop()

# Filters
st.divider()
col1, col2, col3 = st.columns(3)
with col1:
    src_f = st.selectbox(
        "Source",
        ["all"] + list({j["source"] for j in jobs}),
        key = "apply_src_f"
    )
with col2:
    type_f = st.selectbox(
        "Type",
        ["all", "internship", "job"],
        key = "apply_type_f"
    )
with col3:
    search_f = st.text_input(
        "Search",
        placeholder = "title ya company...",
        key         = "apply_search_f"
    )

filtered = jobs
if src_f != "all":
    filtered = [j for j in filtered if j["source"] == src_f]
if type_f != "all":
    filtered = [j for j in filtered if j["type"] == type_f]
if search_f:
    filtered = [
        j for j in filtered
        if search_f.lower() in j["title"].lower()
        or search_f.lower() in j["company"].lower()
    ]

col1, col2, col3 = st.columns(3)
col1.metric("Total",    len(jobs))
col2.metric("Filtered", len(filtered))
col3.metric(
    "Selected",
    len(st.session_state.get("selected_jobs", {}))
)

if not filtered:
    st.info("Filter change karo")
    st.stop()

# Job cards
if "selected_jobs" not in st.session_state:
    st.session_state["selected_jobs"] = {}

source_colors = {
    "internshala": "🟢",
    "remotive"   : "🔵",
    "unstop"     : "🟡",
    "yc_jobs"    : "🟠",
}

for job in filtered:
    job_id     = hash(job["url"])
    src_badge  = source_colors.get(job["source"], "⚪")
    type_badge = "🎓" if job["type"] == "internship" else "💼"

    col1, col2 = st.columns([1, 16])

    with col1:
        checked = st.checkbox(
            "select",
            key              = f"jsel_{job_id}",
            value            = job_id in st.session_state["selected_jobs"],
            label_visibility = "hidden"
        )
        if checked:
            st.session_state["selected_jobs"][job_id] = job
        elif job_id in st.session_state["selected_jobs"]:
            del st.session_state["selected_jobs"][job_id]

    with col2:
        with st.expander(
            f"{src_badge} {type_badge} **{job['title']}** "
            f"@ {job['company']} — {job['location']}"
        ):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Type",     job["type"].title())
            c2.metric("Location", job["location"][:20])
            c3.metric("Stipend",  job.get("stipend", "N/A")[:20])
            c4.metric("Source",   job["source"])

            if job.get("description"):
                st.caption(job["description"][:250])

            st.markdown(f"[🔗 View & Apply]({job['url']})")

st.divider()

# ── Apply Section ─────────────────────────────
selected = st.session_state.get("selected_jobs", {})

if not selected:
    st.info("Jobs select karo upar se")
    st.stop()

st.subheader(f"✅ {len(selected)} selected")

if st.button(
    f"🚀 Apply to {len(selected)} {type_label}",
    type = "primary"
):
    for job_id, job in selected.items():
        try:
            st.write(f"**{job['title']}** @ {job['company']}")

            from backend.agents import resume_agent
            result = resume_agent.optimize_for_job(
                user_id   = user_id,
                job_title = job["title"],
                company   = job["company"],
                job_desc  = job.get("description", "")
            )

            if not result.get("error"):
                rc1, rc2 = st.columns(2)
                rc1.metric("ATS Before", f"{result['ats_before']}%")
                rc2.metric(
                    "ATS After",
                    f"{result['ats_after']}%",
                    delta = f"+{result['ats_after'] - result['ats_before']}%"
                )

            from backend.agents.email_generator import generate_job_email
            from backend.agents.email_sender    import send_email

            email_data = generate_job_email(
                user_id   = user_id,
                job_title = job["title"],
                company   = job["company"],
                job_desc  = job.get("description", "")
            )

            if email_data.get("contact_email"):
                res = send_email(
                    user_id     = user_id,
                    to_email    = email_data["contact_email"],
                    subject     = email_data["subject"],
                    body        = email_data["body"],
                    resume_path = result.get("optimized_path", ""),
                    company     = job["company"]
                )
                if res.get("success"):
                    st.success(f"✅ Email sent!")
                    try:
                        from backend.utils.sheets_tracker import log_job_application
                        log_job_application(
                            user_id       = user_id,
                            company       = job["company"],
                            role          = job["title"],
                            platform      = job["source"],
                            apply_url     = job["url"],
                            contact_email = email_data["contact_email"],
                            subject       = email_data["subject"]
                        )
                    except:
                        pass
                else:
                    st.error(f"❌ {res.get('error')}")
            else:
                st.warning(
                    f"📎 Email nahi mili — "
                    f"[Manually Apply]({job['url']})"
                )

        except Exception as e:
            st.error(f"Error: {e}")