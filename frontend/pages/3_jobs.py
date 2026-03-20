import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import streamlit as st
import threading
import uuid
from backend.database import SessionLocal
from backend.models.job import Job
from backend.models.company import Company
from backend.models.contact import Contact
from backend.agents.scraper_agent import run as scrape_run
from backend.pipeline.state import TrackAState, TrackBState
from backend.pipeline.graph import (
    build_track_a_graph,
    build_track_b_graph,
)
from loguru import logger

if "user_id" not in st.session_state:
    st.warning("Pehle login karo")
    st.stop()

user_id = st.session_state["user_id"]

st.title("🔍 Jobs & Startups")

# ── Top Actions ───────────────────────────────
col1, col2 = st.columns([3, 1])
with col1:
    st.caption("Jobs aur startups dhundho — select karo — apply karo")
with col2:
    if st.button("🔄 Scrape Now", type="primary"):
        with st.spinner("Scraping + contacts dhundh rahe hain..."):
            db = SessionLocal()
            try:
                result = scrape_run(db, user_id)
                st.success(
                    f"✅ {result['total_jobs']} jobs, "
                    f"{result['total_companies']} companies found"
                )
            except Exception as e:
                st.error(str(e))
            finally:
                db.close()

st.divider()

tab1, tab2 = st.tabs(["💼 Job Listings", "🚀 Startups"])


# ═════════════════════════════════════════════
# TAB 1 — JOB LISTINGS
# ═════════════════════════════════════════════

with tab1:
    st.caption("Internshala, YC, Unstop, Remotive se scraped jobs")

    db = SessionLocal()
    try:
        jobs = db.query(Job).order_by(
            Job.fit_score.desc(),
            Job.scraped_date.desc()
        ).limit(50).all()
        jobs_data = [
            {
                "id"         : j.id,
                "title"      : j.title,
                "company"    : j.company_name,
                "location"   : j.location,
                "stipend"    : j.stipend,
                "fit_score"  : j.fit_score or 0,
                "job_type"   : j.job_type,
                "source"     : j.source,
                "apply_url"  : j.apply_url,
                "description": j.description,
                "status"     : j.status,
            }
            for j in jobs
        ]
    finally:
        db.close()

    if not jobs_data:
        st.info("Koi jobs nahi — Scrape Now dabao")
        st.stop()

    # ── Filters ───────────────────────────────
    col1, col2, col3 = st.columns(3)
    with col1:
        source_f = st.selectbox(
            "Source",
            ["all", "internshala", "yc_jobs",
             "unstop", "remotive", "the_muse"],
            key="job_src"
        )
    with col2:
        type_f = st.selectbox(
            "Type", ["all", "internship", "job"],
            key="job_typ"
        )
    with col3:
        score_f = st.slider(
            "Min Score", 0, 100, 0,
            key="job_scr"
        )

    filtered = jobs_data
    if source_f != "all":
        filtered = [j for j in filtered if j["source"] == source_f]
    if type_f != "all":
        filtered = [j for j in filtered if j["job_type"] == type_f]
    if score_f > 0:
        filtered = [j for j in filtered if j["fit_score"] >= score_f]

    st.metric("Jobs Found", len(filtered))

    if not filtered:
        st.info("Filter change karo")
        st.stop()

    # ── Job Selection ─────────────────────────
    if "selected_jobs" not in st.session_state:
        st.session_state["selected_jobs"] = set()

    for job in filtered:
        score = job["fit_score"]
        badge = "🟢" if score >= 75 else "🟡" if score >= 50 else "🔴"

        col1, col2 = st.columns([1, 12])

        with col1:
            checked = st.checkbox(
                "",
                key   = f"jc_{job['id']}",
                value = job["id"] in st.session_state["selected_jobs"]
            )
            if checked:
                st.session_state["selected_jobs"].add(job["id"])
            else:
                st.session_state["selected_jobs"].discard(job["id"])

        with col2:
            with st.expander(
                f"{badge} **{job['title']}** @ {job['company']} "
                f"— {score}% match"
            ):
                c1, c2, c3 = st.columns(3)
                c1.metric("Fit Score", f"{score}%")
                c2.metric("Location",  job["location"] or "N/A")
                c3.metric("Stipend",   job["stipend"]  or "N/A")

                c4, c5 = st.columns(2)
                c4.caption(f"📌 {job['source']}")
                c5.caption(f"💼 {job['job_type']}")

                if job["description"]:
                    st.caption(job["description"][:200])

                st.markdown(f"🔗 [View Job]({job['apply_url']})")

    st.divider()

    selected = st.session_state["selected_jobs"]
    st.metric("Selected", len(selected))

    if selected:
        if st.button(
            f"🚀 Apply to {len(selected)} Jobs",
            type="primary"
        ):
            thread_id = str(uuid.uuid4())

            initial_state: TrackAState = {
                "user_id"              : user_id,
                "thread_id"            : thread_id,
                "current_step"         : "scoring",
                "errors"               : [],
                "scored_jobs"          : [],
                "selected_job_ids"     : list(selected),
                "pending_resume_reviews": [],
                "approved_resume_ids"  : [],
                "rejected_resume_ids"  : [],
                "applications_sent"    : [],
            }

            def run_a():
                db    = SessionLocal()
                graph = build_track_a_graph(db)
                config = {"configurable": {"thread_id": thread_id}}
                try:
                    graph.invoke(initial_state, config=config)
                except Exception as e:
                    logger.error(f"Track A: {e}")
                finally:
                    db.close()

            threading.Thread(target=run_a, daemon=True).start()
            st.session_state["track_a_thread"] = thread_id
            st.success("✅ Pipeline started!")
            st.switch_page("pages/4_review.py")
    else:
        st.info("Koi job select karo")


# ═════════════════════════════════════════════
# TAB 2 — STARTUPS
# ═════════════════════════════════════════════

with tab2:
    st.caption(
        "YC, Product Hunt, HN, GitHub se startups — "
        "contacts ke saath"
    )

    # Load companies with contacts
    db = SessionLocal()
    try:
        companies = db.query(Company).order_by(
            Company.scraped_date.desc()
        ).limit(100).all()

        companies_data = []
        for c in companies:
            contacts = db.query(Contact).filter(
                Contact.company_id == c.id
            ).order_by(Contact.priority).all()

            companies_data.append({
                "id"          : c.id,
                "name"        : c.name,
                "website"     : c.website,
                "description" : c.description,
                "summary"     : c.company_summary,
                "funding"     : c.funding,
                "team_size"   : c.team_size,
                "location"    : c.location,
                "source"      : c.source,
                "ai_related"  : c.ai_related,
                "research_done": c.research_done,
                "contacts"    : [
                    {
                        "name"      : ct.name,
                        "role"      : ct.role,
                        "email"     : ct.email,
                        "verified"  : ct.confidence_score >= 0.9,
                        "confidence": ct.confidence_score,
                        "source"    : ct.source,
                    }
                    for ct in contacts
                ]
            })
    finally:
        db.close()

    if not companies_data:
        st.info("Koi startups nahi — Scrape Now dabao")
        st.stop()

    # ── Filters ───────────────────────────────
    col1, col2, col3 = st.columns(3)
    with col1:
        src_f = st.selectbox(
            "Source",
            ["all", "yc_api", "product_hunt", "hn_hiring",
             "github_trending", "betalist", "devto",
             "google_news", "reddit", "f6s"],
            key="co_src"
        )
    with col2:
        ai_f = st.checkbox("AI Related Only", key="ai_f")
    with col3:
        contacts_f = st.checkbox(
            "Has Contacts Only", key="ct_f"
        )

    filtered_co = companies_data
    if src_f != "all":
        filtered_co = [c for c in filtered_co if c["source"] == src_f]
    if ai_f:
        filtered_co = [c for c in filtered_co if c["ai_related"]]
    if contacts_f:
        filtered_co = [c for c in filtered_co if c["contacts"]]

    col1, col2, col3 = st.columns(3)
    col1.metric("Companies",       len(filtered_co))
    col2.metric("With Contacts",   sum(1 for c in filtered_co if c["contacts"]))
    col3.metric("AI Related",      sum(1 for c in filtered_co if c["ai_related"]))

    if not filtered_co:
        st.info("Filter change karo")
        st.stop()

    # ── Company Selection ─────────────────────
    if "selected_companies" not in st.session_state:
        st.session_state["selected_companies"] = set()

    for company in filtered_co:
        col1, col2 = st.columns([1, 12])

        with col1:
            checked = st.checkbox(
                "",
                key   = f"cc_{company['id']}",
                value = company["id"] in st.session_state["selected_companies"]
            )
            if checked:
                st.session_state["selected_companies"].add(company["id"])
            else:
                st.session_state["selected_companies"].discard(company["id"])

        with col2:
            # Badges
            ai_badge      = "🤖 " if company["ai_related"] else ""
            contact_badge = (
                f"👥 {len(company['contacts'])} contacts"
                if company["contacts"]
                else "⚠️ No contacts"
            )

            with st.expander(
                f"{ai_badge}**{company['name']}** "
                f"— {company['source']} — {contact_badge}"
            ):
                # Company info
                c1, c2, c3 = st.columns(3)
                c1.metric("Funding",   company["funding"]   or "Unknown")
                c2.metric("Team",      company["team_size"] or "Unknown")
                c3.metric("Location",  company["location"]  or "Unknown")

                if company["description"]:
                    st.info(f"📌 {company['description'][:200]}")

                if company["summary"]:
                    st.caption(f"🔍 {company['summary'][:200]}")

                if company["website"]:
                    st.markdown(f"🔗 [Website]({company['website']})")

                # ── Contacts ──────────────────
                if company["contacts"]:
                    st.divider()
                    st.caption("**Contacts:**")

                    for contact in company["contacts"]:
                        verified_badge = (
                            "✅ verified"
                            if contact["verified"]
                            else "⚠️ unverified"
                        )
                        confidence = int(
                            contact["confidence"] * 100
                        )

                        c1, c2, c3 = st.columns([3, 4, 3])
                        c1.write(
                            f"👤 **{contact['name']}** "
                            f"({contact['role']})"
                        )
                        if contact["email"]:
                            c2.code(contact["email"])
                            c3.caption(
                                f"{verified_badge} "
                                f"({confidence}%)"
                            )
                        else:
                            c2.caption("Email not found")
                else:
                    st.divider()
                    st.warning(
                        "⚠️ No contacts found. "
                        "Cold email nahi bhej sakte."
                    )

    st.divider()

    selected_co = st.session_state["selected_companies"]

    # Only companies with contacts select ho sakte hain
    valid_selected = {
        cid for cid in selected_co
        if any(
            c["id"] == cid and c["contacts"]
            for c in filtered_co
        )
    }

    col1, col2 = st.columns(2)
    col1.metric("Selected",         len(selected_co))
    col2.metric("With Contacts",    len(valid_selected))

    if len(selected_co) > len(valid_selected):
        st.warning(
            f"{len(selected_co) - len(valid_selected)} selected companies "
            f"mein contacts nahi hain — unhe skip kiya jaayega"
        )

    if valid_selected:
        if st.button(
            f"📧 Reach Out to {len(valid_selected)} Companies",
            type="primary"
        ):
            thread_id = str(uuid.uuid4())

            initial_state: TrackBState = {
                "user_id"              : user_id,
                "thread_id"            : thread_id,
                "current_step"         : "researching",
                "errors"               : [],
                "researched_companies" : [],
                "selected_company_ids" : list(valid_selected),
                "pending_resume_reviews": [],
                "approved_resume_ids"  : [],
                "rejected_resume_ids"  : [],
                "pending_email_reviews": [],
                "approved_email_ids"   : [],
                "rejected_email_ids"   : [],
                "emails_sent"          : [],
            }

            def run_b():
                db     = SessionLocal()
                graph  = build_track_b_graph(db)
                config = {"configurable": {"thread_id": thread_id}}
                try:
                    graph.invoke(initial_state, config=config)
                except Exception as e:
                    logger.error(f"Track B: {e}")
                finally:
                    db.close()

            threading.Thread(target=run_b, daemon=True).start()
            st.session_state["track_b_thread"] = thread_id
            st.success("✅ Cold outreach pipeline started!")
            st.switch_page("pages/4_review.py")
    else:
        st.info(
            "Contacts wali companies select karo. "
            "Bina email ke cold email nahi bhej sakte."
        )
