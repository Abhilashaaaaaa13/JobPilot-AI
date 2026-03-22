# frontend/pages/4_outreach.py

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import streamlit as st
from loguru import logger

if "user_id" not in st.session_state:
    st.warning("Pehle login karo")
    st.stop()

user_id = st.session_state["user_id"]


# ═════════════════════════════════════════════
# HELPER FUNCTIONS
# ═════════════════════════════════════════════

def _render_company_card(company: dict, co_id: int):
    """Single company card."""
    contacts = company.get("contacts", [])
    status   = st.session_state.get(
        "company_statuses", {}
    ).get(co_id, "")

    status_badge = {
        "awaiting"     : "⏳ Awaiting",
        "replied"      : "📩 Replied",
        "followup_sent": "🔄 Follow Up Sent",
        ""             : ""
    }.get(status, "")

    source_badges = {
        "yc_api"   : "🟠 YC",
        "hn_hiring": "🟤 HN",
        "betalist" : "🟣 Betalist",
    }
    src_badge = source_badges.get(company["source"], "⚪")
    ct_badge  = (
        f"👥 {len(contacts)}"
        if contacts else "⚠️ No contacts"
    )

    col1, col2 = st.columns([1, 16])

    with col1:
        can_select = bool(contacts) and status not in ["replied"]
        if "selected_companies" not in st.session_state:
            st.session_state["selected_companies"] = {}

        checked = st.checkbox(
            "select",
            key              = f"csel_{co_id}",
            value            = co_id in st.session_state["selected_companies"],
            disabled         = not can_select,
            label_visibility = "hidden"
        )
        if checked and can_select:
            st.session_state["selected_companies"][co_id] = company
        elif not checked:
            st.session_state["selected_companies"].pop(co_id, None)

    with col2:
        header = (
            f"{src_badge} **{company['name']}** "
            f"— {company.get('funding', '?')} "
            f"— {ct_badge}"
        )
        if status_badge:
            header += f" — {status_badge}"

        with st.expander(header):
            c1, c2, c3 = st.columns(3)
            c1.metric("Team",     company.get("team_size", "?"))
            c2.metric("Location", company.get("location",  "?")[:20])
            c3.metric("Source",   company["source"])

            if company.get("one_liner"):
                st.info(f"💡 {company['one_liner']}")

            if company.get("description"):
                st.caption(company["description"][:400])

            if company.get("website"):
                st.markdown(f"[🔗 Website]({company['website']})")

            if contacts:
                st.divider()
                st.caption("**Contacts:**")
                for ct in contacts:
                    v = "✅" if ct.get("verified") else "⚠️"
                    c1, c2, c3 = st.columns([3, 5, 2])
                    c1.write(f"👤 **{ct['name']}** ({ct['role']})")
                    c2.code(ct.get("email", ""))
                    c3.caption(v)
            else:
                st.warning("⚠️ No contacts")

            # Resume preview
            rv = st.session_state.get("resume_previews", {}).get(co_id)
            if rv:
                st.divider()
                st.write("**📄 Resume:**")
                rc1, rc2 = st.columns(2)
                rc1.metric("Before", f"{rv['ats_before']}%")
                rc2.metric(
                    "After",
                    f"{rv['ats_after']}%",
                    delta=f"+{rv['ats_after'] - rv['ats_before']}%"
                )
                if rv.get("changes"):
                    st.caption("Keywords: " + ", ".join(rv["changes"][:5]))
                if rv.get("decision") is None:
                    rb1, rb2 = st.columns(2)
                    with rb1:
                        if st.button("✅ Use Optimized", key=f"racc_{co_id}"):
                            st.session_state["resume_previews"][co_id]["decision"] = "accept"
                            st.rerun()
                    with rb2:
                        if st.button("📄 Keep Original", key=f"rrej_{co_id}"):
                            st.session_state["resume_previews"][co_id]["decision"] = "reject"
                            st.rerun()
                else:
                    d = rv["decision"]
                    st.success("✅ Optimized" if d == "accept" else "📄 Original")

            # Email preview
            ep = st.session_state.get("email_previews", {}).get(co_id)
            if ep:
                st.divider()
                st.write("**📧 Email:**")
                ec1, ec2 = st.columns(2)
                ec1.info(f"**To:** {ep.get('contact_name')} ({ep.get('contact_role')})")
                ec2.success(f"**Email:** {ep.get('contact_email')}")

                if ep.get("gap"):
                    g1, g2, g3 = st.columns(3)
                    g1.error(f"**Gap**\n\n{ep['gap'][:80]}")
                    g2.info(f"**Proposal**\n\n{ep['proposal'][:80]}")
                    g3.success(f"**Why You**\n\n{ep['why_fits'][:80]}")

                edit_key = f"editing_{co_id}"
                editing  = st.session_state.get(edit_key, False)

                if editing:
                    new_subj = st.text_input(
                        "Subject", value=ep.get("subject",""), key=f"subj_{co_id}"
                    )
                    new_body = st.text_area(
                        "Body", value=ep.get("body",""), height=200, key=f"body_{co_id}"
                    )
                    st.session_state["email_previews"][co_id]["subject"] = new_subj
                    st.session_state["email_previews"][co_id]["body"]    = new_body
                else:
                    st.text_input(
                        "Subject", value=ep.get("subject",""), disabled=True, key=f"subj_d_{co_id}"
                    )
                    st.text_area(
                        "Body", value=ep.get("body",""), height=150, disabled=True, key=f"body_d_{co_id}"
                    )

                if ep.get("decision") is None:
                    ea1, ea2, ea3 = st.columns(3)
                    with ea1:
                        if st.button("✅ Send", key=f"send_{co_id}", type="primary"):
                            _send_cold_email(user_id, co_id, company, ep)
                            st.rerun()
                    with ea2:
                        if st.button("✏️ Edit", key=f"edit_{co_id}"):
                            st.session_state[edit_key] = not editing
                            st.rerun()
                    with ea3:
                        if st.button("❌ Skip", key=f"skip_{co_id}"):
                            st.session_state["email_previews"][co_id]["decision"] = "skip"
                            st.rerun()
                elif ep.get("decision") == "sent":
                    st.success("✅ Email sent!")
                elif ep.get("decision") == "skip":
                    st.info("⏭️ Skipped")


def _prepare_cold_emails(user_id: int, selected_co: dict):
    from backend.agents import resume_agent
    from backend.agents.email_generator import generate_cold_email

    if "resume_previews" not in st.session_state:
        st.session_state["resume_previews"] = {}
    if "email_previews" not in st.session_state:
        st.session_state["email_previews"] = {}

    total    = len(selected_co)
    progress = st.progress(0)

    for i, (co_id, company) in enumerate(selected_co.items()):
        try:
            st.caption(f"⏳ {company['name']} process ho raha hai...")

            result = resume_agent.optimize_for_company(
                user_id     = user_id,
                company     = company["name"],
                description = company.get("description", "")
            )

            st.session_state["resume_previews"][co_id] = {
                "ats_before": result.get("ats_before", 0),
                "ats_after" : result.get("ats_after",  0),
                "changes"   : result.get("changes",    []),
                "orig_path" : result.get("original_path",  ""),
                "opt_path"  : result.get("optimized_path", ""),
                "decision"  : None
            }

            contact = next(
                (c for c in company.get("contacts", []) if c.get("email")),
                None
            )
            if not contact:
                continue

            email_result = generate_cold_email(
                user_id     = user_id,
                company     = company["name"],
                description = company.get("description", ""),
                one_liner   = company.get("one_liner",   ""),
                contact     = contact
            )

            st.session_state["email_previews"][co_id] = {
                "contact_name" : contact["name"],
                "contact_role" : contact["role"],
                "contact_email": contact["email"],
                "subject"      : email_result.get("subject",  ""),
                "body"         : email_result.get("body",     ""),
                "gap"          : email_result.get("gap",      ""),
                "proposal"     : email_result.get("proposal", ""),
                "why_fits"     : email_result.get("why_fits", ""),
                "decision"     : None
            }

            progress.progress((i + 1) / total)

        except Exception as e:
            logger.error(f"Prepare error {company['name']}: {e}")

    progress.empty()


def _send_cold_email(user_id, co_id, company, ep):
    from backend.agents.email_sender import send_email

    resume_info = st.session_state.get("resume_previews", {}).get(co_id, {})
    decision    = resume_info.get("decision", "reject")
    resume_path = (
        resume_info.get("opt_path")
        if decision == "accept"
        else resume_info.get("orig_path", "")
    )

    result = send_email(
        user_id     = user_id,
        to_email    = ep["contact_email"],
        subject     = ep["subject"],
        body        = ep["body"],
        resume_path = resume_path,
        company     = company["name"],
        contact     = ep["contact_name"]
    )

    if result.get("success"):
        if "company_statuses" not in st.session_state:
            st.session_state["company_statuses"] = {}
        st.session_state["company_statuses"][co_id]          = "awaiting"
        st.session_state["email_previews"][co_id]["decision"] = "sent"

        try:
            from backend.utils.sheets_tracker import log_cold_email
            log_cold_email(
                user_id       = user_id,
                company       = company["name"],
                website       = company.get("website", ""),
                contact_name  = ep["contact_name"],
                contact_role  = ep["contact_role"],
                contact_email = ep["contact_email"],
                subject       = ep["subject"],
                gap           = ep.get("gap",      ""),
                proposal      = ep.get("proposal", "")
            )
        except Exception as e:
            logger.warning(f"Sheets error: {e}")

        st.success(f"✅ Sent to {ep['contact_name']} @ {company['name']}!")
    else:
        st.error(f"❌ Failed: {result.get('error')}")


# ═════════════════════════════════════════════
# MAIN PAGE
# ═════════════════════════════════════════════

st.title("🚀 Cold Outreach")
st.caption("Startups dhundho — personalized cold emails bhejo")

prefs = st.session_state.get("prefs", {
    "preferred_type": "both",
    "domains"       : ["ai_ml"],
    "target_roles"  : ["AI Engineer", "ML Engineer"],
    "location"      : "remote"
})

# ── Find Button ───────────────────────────────
if st.button("🔍 Find Startups", type="primary"):
    st.session_state["scraped_companies"]  = []
    st.session_state["selected_companies"] = {}
    st.session_state["email_previews"]     = {}
    st.session_state["resume_previews"]    = {}
    st.session_state["company_statuses"]   = {}
    st.session_state["is_scraping"]        = True
    st.session_state["scraping_done"]      = False
    st.rerun()

# ── REAL TIME STREAMING ───────────────────────
if st.session_state.get("is_scraping"):
    from backend.agents.scraper_agent import (
        stream_yc_companies,
        stream_hn_hiring,
        stream_betalist,
    )

    companies = st.session_state.get("scraped_companies", [])

    # Status bar
    status = st.empty()
    status.info("🟠 YC Companies scraping...")

    # Cards container — live update hoga
    cards_area = st.container()

    # ── YC Stream ────────────────────────────
    yc_count = 0
    for co in stream_yc_companies(prefs):
        st.session_state["scraped_companies"].append(co)
        yc_count += 1
        status.info(f"🟠 YC: {yc_count} companies found...")

        # Turant card dikhao
        co_id = hash(co["website"])
        with cards_area:
            _render_company_card(co, co_id)

    # ── HN Stream ────────────────────────────
    status.info(f"🟤 HN Hiring scraping... ({yc_count} YC companies mile)")
    hn_count = 0
    for co in stream_hn_hiring(prefs):
        st.session_state["scraped_companies"].append(co)
        hn_count += 1
        status.info(f"🟤 HN: {hn_count} found, total: {yc_count + hn_count}...")
        co_id = hash(co["website"])
        with cards_area:
            _render_company_card(co, co_id)

    # ── Betalist Stream ───────────────────────
    status.info(f"🟣 Betalist scraping... ({yc_count + hn_count} total)")
    bl_count = 0
    for co in stream_betalist(prefs):
        st.session_state["scraped_companies"].append(co)
        bl_count += 1
        status.info(
            f"🟣 Betalist: {bl_count} found, "
            f"total: {yc_count + hn_count + bl_count}..."
        )
        co_id = hash(co["website"])
        with cards_area:
            _render_company_card(co, co_id)

    total = yc_count + hn_count + bl_count
    status.success(
        f"✅ Done — {total} startups found! "
        f"(YC: {yc_count}, HN: {hn_count}, Betalist: {bl_count})"
    )

    st.session_state["is_scraping"]   = False
    st.session_state["scraping_done"] = True
    st.rerun()

# ── Show Saved Results ────────────────────────
elif not st.session_state.get("is_scraping"):
    companies = st.session_state.get("scraped_companies", [])

    if not companies:
        st.info("'Find Startups' dabao")
        st.stop()

    # ── Filters ──────────────────────────────
    col1, col2, col3 = st.columns(3)
    with col1:
        src_f = st.selectbox(
            "Source",
            ["all"] + list({c["source"] for c in companies}),
            key = "out_src"
        )
    with col2:
        ct_f = st.checkbox("Has Contacts Only", key="out_ct")
    with col3:
        vr_f = st.checkbox("Verified Email Only", key="out_vr")

    filtered = companies
    if src_f != "all":
        filtered = [c for c in filtered if c["source"] == src_f]
    if ct_f:
        filtered = [c for c in filtered if c.get("contacts")]
    if vr_f:
        filtered = [
            c for c in filtered
            if any(ct.get("verified") for ct in c.get("contacts", []))
        ]

    col1, col2, col3 = st.columns(3)
    col1.metric("Total",        len(companies))
    col2.metric("Filtered",     len(filtered))
    col3.metric(
        "With Contacts",
        sum(1 for c in filtered if c.get("contacts"))
    )

    if not filtered:
        st.info("Filter change karo")
        st.stop()

    # ── Company Cards ─────────────────────────
    for company in filtered:
        co_id = hash(company["website"])
        _render_company_card(company, co_id)

    st.divider()

    # ── Prepare Emails ────────────────────────
    selected_co = st.session_state.get("selected_companies", {})
    valid_co    = {
        k: v for k, v in selected_co.items()
        if v.get("contacts")
    }

    col1, col2 = st.columns(2)
    col1.metric("Selected",      len(selected_co))
    col2.metric("With Contacts", len(valid_co))

    if len(selected_co) > len(valid_co):
        st.warning(
            f"{len(selected_co) - len(valid_co)} mein "
            f"contacts nahi — skip honge"
        )

    if valid_co:
        if st.button(
            f"📧 Prepare Cold Emails for {len(valid_co)} Startups",
            type = "primary"
        ):
            with st.spinner("Resume + Emails prepare ho rahe hain..."):
                _prepare_cold_emails(user_id, valid_co)
            st.rerun()
    else:
        st.info("Contacts wale startups select karo")
