import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import streamlit as st
import time
from backend.database import SessionLocal
from backend.pipeline.graph import (
    get_track_a_state, get_track_b_state,
    update_track_a_state, update_track_b_state,
    resume_track_a, resume_track_b
)

if "user_id" not in st.session_state:
    st.warning("Pehle login karo")
    st.stop()

user_id       = st.session_state["user_id"]
track_a_thread = st.session_state.get("track_a_thread")
track_b_thread = st.session_state.get("track_b_thread")

st.title("✅ Review & Approve")

if not track_a_thread and not track_b_thread:
    st.info("Koi active pipeline nahi — Jobs page pe jao")
    if st.button("Go to Jobs"):
        st.switch_page("pages/3_jobs.py")
    st.stop()

tab1, tab2 = st.tabs(["💼 Track A — Job Apply", "🚀 Track B — Cold Outreach"])


# ═════════════════════════════════════════════
# TRACK A REVIEW
# ═════════════════════════════════════════════

with tab1:
    if not track_a_thread:
        st.info("Track A pipeline nahi chali")
        st.stop()

    db      = SessionLocal()
    state_a = get_track_a_state(db, track_a_thread)
    db.close()

    if not state_a:
        st.info("Track A state nahi mila")
        st.stop()

    current_step = state_a.get("current_step", "")

    # ── Progress ──────────────────────────────
    STEPS_A = {
        "scoring"              : (1, "Scoring jobs"),
        "awaiting_job_selection": (2, "Waiting for job selection"),
        "optimizing_resumes"   : (3, "Optimizing resumes"),
        "awaiting_resume_review": (4, "Waiting for resume review"),
        "sending"              : (5, "Applying"),
        "done"                 : (6, "Done"),
    }
    step_num, step_label = STEPS_A.get(current_step, (0, current_step))
    st.progress(step_num / 6)
    st.caption(f"Step {step_num}/6 — {step_label}")

    # ── Still Running ─────────────────────────
    if current_step not in [
        "awaiting_job_selection",
        "awaiting_resume_review",
        "done"
    ]:
        st.info(f"⏳ Running — {step_label}")
        st.caption("5 sec mein refresh...")
        time.sleep(5)
        st.rerun()

    # ── Done ──────────────────────────────────
    elif current_step == "done":
        apps = state_a.get("applications_sent", [])
        st.success(f"✅ Done — {len(apps)} applications sent")

        for app in apps:
            if app.get("type") == "email_sent":
                st.write(f"📧 Email sent: {app['title']} @ {app['company']}")
            else:
                st.write(f"🔗 Apply manually: {app['title']} @ {app['company']}")
                st.markdown(f"[Apply Here]({app.get('apply_url', '')})")

    # ── Resume Review ─────────────────────────
    elif current_step == "awaiting_resume_review":
        reviews = state_a.get("pending_resume_reviews", [])

        if not reviews:
            st.info("Koi resume reviews nahi")
            st.stop()

        st.subheader("📄 Resume Changes Review")
        st.caption(f"{len(reviews)} resumes — accept ya reject karo")

        if "resume_dec_a" not in st.session_state:
            st.session_state["resume_dec_a"] = {}

        for review in reviews:
            rid = review["id"]
            with st.expander(
                f"**{review['role']}** @ {review['company_name']} "
                f"— ATS: {review['ats_before']}% → "
                f"{review['ats_after']}% "
                f"(+{review['improvement']}%)"
            ):
                c1, c2, c3 = st.columns(3)
                c1.metric("Before", f"{review['ats_before']}%")
                c2.metric("After",  f"{review['ats_after']}%",
                          delta=f"+{review['improvement']}%")
                c3.metric("Type",   review["type"].title())

                if review.get("changes_summary"):
                    st.write("**Keywords added:**")
                    st.write(", ".join(review["changes_summary"]))

                st.divider()
                current = st.session_state["resume_dec_a"].get(rid)
                col1, col2 = st.columns(2)

                with col1:
                    if st.button(
                        "✅ Accept",
                        key  = f"a_acc_{rid}",
                        type = "primary" if current == "accept" else "secondary"
                    ):
                        st.session_state["resume_dec_a"][rid] = "accept"
                        st.rerun()

                with col2:
                    if st.button(
                        "❌ Keep Original",
                        key  = f"a_rej_{rid}",
                        type = "primary" if current == "reject" else "secondary"
                    ):
                        st.session_state["resume_dec_a"][rid] = "reject"
                        st.rerun()

                if current:
                    if current == "accept":
                        st.success("✅ Optimized resume will be used")
                    else:
                        st.info("Original resume will be used")

        decisions = st.session_state["resume_dec_a"]
        decided   = len(decisions)
        total     = len(reviews)

        st.progress(decided / total if total > 0 else 0)
        st.caption(f"{decided}/{total} reviewed")

        if decided == total:
            if st.button("🚀 Apply Now", type="primary"):
                db       = SessionLocal()
                approved = [r for r, d in decisions.items() if d == "accept"]
                rejected = [r for r, d in decisions.items() if d == "reject"]

                update_track_a_state(db, track_a_thread, {
                    "approved_resume_ids": approved,
                    "rejected_resume_ids": rejected,
                })
                resume_track_a(db, track_a_thread)
                db.close()

                del st.session_state["resume_dec_a"]
                st.success("✅ Applying now!")
                st.rerun()
        else:
            st.warning(f"{total - decided} resumes still pending")


# ═════════════════════════════════════════════
# TRACK B REVIEW
# ═════════════════════════════════════════════

with tab2:
    if not track_b_thread:
        st.info("Track B pipeline nahi chali")
        st.stop()

    db      = SessionLocal()
    state_b = get_track_b_state(db, track_b_thread)
    db.close()

    if not state_b:
        st.info("Track B state nahi mila")
        st.stop()

    current_step_b = state_b.get("current_step", "")

    # ── Progress ──────────────────────────────
    STEPS_B = {
        "researching"             : (1, "Researching companies"),
        "finding_contacts"        : (2, "Finding contacts"),
        "awaiting_company_selection": (3, "Waiting for company selection"),
        "optimizing_resumes"      : (4, "Optimizing resumes"),
        "awaiting_resume_review"  : (5, "Waiting for resume review"),
        "generating_emails"       : (6, "Generating emails"),
        "awaiting_email_review"   : (7, "Waiting for email review"),
        "sending"                 : (8, "Sending emails"),
        "done"                    : (9, "Done"),
    }
    step_num_b, step_label_b = STEPS_B.get(
        current_step_b, (0, current_step_b)
    )
    st.progress(step_num_b / 9)
    st.caption(f"Step {step_num_b}/9 — {step_label_b}")

    # ── Still Running ─────────────────────────
    if current_step_b not in [
        "awaiting_company_selection",
        "awaiting_resume_review",
        "awaiting_email_review",
        "done"
    ]:
        st.info(f"⏳ Running — {step_label_b}")
        st.caption("5 sec mein refresh...")
        time.sleep(5)
        st.rerun()

    # ── Done ──────────────────────────────────
    elif current_step_b == "done":
        sent = state_b.get("emails_sent", [])
        st.success(f"✅ Done — {len(sent)} cold emails sent")
        for email in sent:
            st.write(
                f"📧 {email['company']} → "
                f"{email['contact']} ({email['contact_role']})"
            )

    # ── Resume Review ─────────────────────────
    elif current_step_b == "awaiting_resume_review":
        reviews = state_b.get("pending_resume_reviews", [])

        if not reviews:
            st.info("Koi resume reviews nahi")
            st.stop()

        st.subheader("📄 Resume Changes Review")

        if "resume_dec_b" not in st.session_state:
            st.session_state["resume_dec_b"] = {}

        for review in reviews:
            rid = review["id"]
            with st.expander(
                f"**{review['company_name']}** "
                f"— ATS: {review['ats_before']}% → "
                f"{review['ats_after']}% "
                f"(+{review['improvement']}%)"
            ):
                c1, c2 = st.columns(2)
                c1.metric("ATS Before", f"{review['ats_before']}%")
                c2.metric("ATS After",  f"{review['ats_after']}%",
                          delta=f"+{review['improvement']}%")

                if review.get("changes_summary"):
                    st.write("**Keywords added:**")
                    st.write(", ".join(review["changes_summary"]))

                st.divider()
                current = st.session_state["resume_dec_b"].get(rid)
                col1, col2 = st.columns(2)

                with col1:
                    if st.button(
                        "✅ Accept",
                        key  = f"b_acc_{rid}",
                        type = "primary" if current == "accept" else "secondary"
                    ):
                        st.session_state["resume_dec_b"][rid] = "accept"
                        st.rerun()
                with col2:
                    if st.button(
                        "❌ Keep Original",
                        key  = f"b_rej_{rid}",
                        type = "primary" if current == "reject" else "secondary"
                    ):
                        st.session_state["resume_dec_b"][rid] = "reject"
                        st.rerun()

        decisions = st.session_state["resume_dec_b"]
        decided   = len(decisions)
        total     = len(reviews)

        st.progress(decided / total if total > 0 else 0)
        st.caption(f"{decided}/{total} reviewed")

        if decided == total:
            if st.button("✅ Generate Emails", type="primary"):
                db       = SessionLocal()
                approved = [r for r, d in decisions.items() if d == "accept"]
                rejected = [r for r, d in decisions.items() if d == "reject"]

                update_track_b_state(db, track_b_thread, {
                    "approved_resume_ids": approved,
                    "rejected_resume_ids": rejected,
                })
                resume_track_b(db, track_b_thread)
                db.close()

                del st.session_state["resume_dec_b"]
                st.success("✅ Generating emails!")
                st.rerun()
        else:
            st.warning(f"{total - decided} pending")

    # ── Email Review ──────────────────────────
    elif current_step_b == "awaiting_email_review":
        email_reviews = state_b.get("pending_email_reviews", [])

        if not email_reviews:
            st.info("Koi email reviews nahi")
            st.stop()

        st.subheader("📧 Email Review")

        if "email_dec_b" not in st.session_state:
            st.session_state["email_dec_b"] = {}
        if "email_edits_b" not in st.session_state:
            st.session_state["email_edits_b"] = {}

        for review in email_reviews:
            rid = review["id"]
            with st.expander(
                f"**{review['company_name']}** → "
                f"{review['contact_name']} ({review['contact_role']})"
            ):
                # Analysis
                if review.get("gap_identified"):
                    c1, c2, c3 = st.columns(3)
                    c1.error(f"**Gap**\n\n{review['gap_identified']}")
                    c2.info(f"**Proposal**\n\n{review['proposal']}")
                    c3.success(f"**Why You**\n\n{review['why_user_fits']}")
                    st.divider()

                # Contact
                col1, col2 = st.columns(2)
                col1.info(
                    f"**To:** {review['contact_name']} "
                    f"({review['contact_role']})"
                )
                if review.get("contact_email"):
                    col2.success(f"**Email:** {review['contact_email']}")
                else:
                    col2.warning("**Email:** Not found")

                # Edit toggle
                edit_key   = f"b_edit_{rid}"
                is_editing = st.session_state.get(edit_key, False)

                if is_editing:
                    subj = st.text_input(
                        "Subject",
                        value = st.session_state["email_edits_b"].get(
                            rid, {}
                        ).get("subject", review["subject"]),
                        key   = f"b_subj_{rid}"
                    )
                    body = st.text_area(
                        "Body",
                        value  = st.session_state["email_edits_b"].get(
                            rid, {}
                        ).get("body", review["body"]),
                        height = 250,
                        key    = f"b_body_{rid}"
                    )
                    st.session_state["email_edits_b"][rid] = {
                        "subject": subj,
                        "body"   : body
                    }
                else:
                    st.text_input(
                        "Subject", value=review["subject"],
                        disabled=True, key=f"b_subj_d_{rid}"
                    )
                    st.text_area(
                        "Body", value=review["body"],
                        height=200, disabled=True,
                        key=f"b_body_d_{rid}"
                    )

                st.caption(f"{len(review['body'].split())} words")

                if review.get("resume_path"):
                    st.success(f"📎 {review['resume_path']}")

                st.divider()
                current = st.session_state["email_dec_b"].get(rid)
                c1, c2, c3 = st.columns(3)

                with c1:
                    if st.button(
                        "✅ Approve", key=f"b_app_{rid}",
                        type="primary" if current == "approve" else "secondary"
                    ):
                        st.session_state["email_dec_b"][rid] = "approve"
                        st.session_state[edit_key] = False
                        st.rerun()
                with c2:
                    if st.button(
                        "✏️ Edit", key=f"b_edt_{rid}",
                        type="primary" if current == "edit" else "secondary"
                    ):
                        st.session_state[edit_key] = True
                        st.session_state["email_dec_b"][rid] = "edit"
                        st.rerun()
                with c3:
                    if st.button(
                        "❌ Reject", key=f"b_rej_e_{rid}",
                        type="primary" if current == "reject" else "secondary"
                    ):
                        st.session_state["email_dec_b"][rid] = "reject"
                        st.session_state[edit_key] = False
                        st.rerun()

        decisions      = st.session_state["email_dec_b"]
        decided        = len(decisions)
        total          = len(email_reviews)
        approved_count = sum(
            1 for d in decisions.values()
            if d in ["approve", "edit"]
        )

        st.progress(decided / total if total > 0 else 0)
        st.caption(
            f"{decided}/{total} reviewed — "
            f"{approved_count} will be sent"
        )

        if decided == total and approved_count > 0:
            if st.button(
                f"📤 Send {approved_count} Emails",
                type="primary"
            ):
                db       = SessionLocal()
                approved = [
                    r for r, d in decisions.items()
                    if d in ["approve", "edit"]
                ]
                rejected = [
                    r for r, d in decisions.items()
                    if d == "reject"
                ]

                # Apply edits to state
                reviews_updated = state_b.get("pending_email_reviews", [])
                edits           = st.session_state.get("email_edits_b", {})

                for r in reviews_updated:
                    if r["id"] in edits:
                        r["edited_subject"] = edits[r["id"]].get("subject")
                        r["edited_body"]    = edits[r["id"]].get("body")

                update_track_b_state(db, track_b_thread, {
                    "approved_email_ids"   : approved,
                    "rejected_email_ids"   : rejected,
                    "pending_email_reviews": reviews_updated,
                })
                resume_track_b(db, track_b_thread)
                db.close()

                del st.session_state["email_dec_b"]
                if "email_edits_b" in st.session_state:
                    del st.session_state["email_edits_b"]

                st.success(f"✅ Sending {approved_count} emails!")
                st.rerun()

        elif decided < total:
            st.warning(f"{total - decided} emails still pending")