# frontend/pages/4_outreach.py

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import json
import streamlit as st
from datetime import datetime
from loguru import logger

if "user_id" not in st.session_state:
    st.warning("Pehle login karo")
    st.stop()

user_id = st.session_state["user_id"]


# ═════════════════════════════════════════════
# SENT STATUS — persistent across reruns
# ═════════════════════════════════════════════

def _mark_sent(co_id: int):
    """
    FIX — sent status do jagah save karo:
    1. email_previews["decision"] — card ke andar use hota hai
    2. sent_ids set — rerun ke baad bhi survive karta hai
    """
    if "sent_ids" not in st.session_state:
        st.session_state["sent_ids"] = set()
    st.session_state["sent_ids"].add(co_id)

    if "email_previews" in st.session_state and co_id in st.session_state["email_previews"]:
        st.session_state["email_previews"][co_id]["decision"] = "sent"


def _is_sent(co_id: int) -> bool:
    sent_ids = st.session_state.get("sent_ids", set())
    if co_id in sent_ids:
        return True
    ep = st.session_state.get("email_previews", {}).get(co_id, {})
    return ep.get("decision") == "sent"


# ═════════════════════════════════════════════
# TRACKER UPDATE
# ═════════════════════════════════════════════

def _update_tracker(user_id: int, company: dict, ep: dict):
    """Send ke baad log.json mein entry daalo."""
    log_dir  = f"uploads/{user_id}/sent_emails"
    log_file = f"{log_dir}/log.json"
    os.makedirs(log_dir, exist_ok=True)

    entry = {
        "to"            : ep["contact_email"],
        "company"       : company["name"],
        "website"       : company.get("website", ""),
        "contact_name"  : ep["contact_name"],
        "contact_role"  : ep["contact_role"],
        "subject"       : ep["subject"],
        "gap"           : ep.get("gap",      ""),
        "proposal"      : ep.get("proposal", ""),
        "status"        : "awaiting",
        "replied"       : False,
        "followup_sent" : False,
        "followup_count": 0,
        "sent_at"       : datetime.utcnow().isoformat(),
        "reply_at"      : None,
        "reply_body"    : None,
        "followup_at"   : None,
    }

    try:
        if os.path.exists(log_file):
            with open(log_file, "r") as f:
                log = json.load(f)
        else:
            log = []
        log.append(entry)
        with open(log_file, "w") as f:
            json.dump(log, f, indent=2)
        logger.info(f"✅ Tracker updated: {company['name']}")
    except Exception as e:
        logger.warning(f"Tracker log error: {e}")


# ═════════════════════════════════════════════
# GENERATE EMAIL (on demand)
# ═════════════════════════════════════════════

def _generate_email(user_id: int, co_id: int, company: dict):
    """Card pehli baar khule tab email generate karo."""
    from backend.agents.email_generator import generate_cold_email

    if "email_previews" not in st.session_state:
        st.session_state["email_previews"] = {}

    if co_id in st.session_state["email_previews"]:
        return

    contacts = company.get("contacts", [])
    contact  = next((c for c in contacts if c.get("email")), None)

    if not contact:
        st.session_state["email_previews"][co_id] = {"error": "No contact email found"}
        return

    with st.spinner(f"✍️ {company['name']} ke liye email ban raha hai..."):
        try:
            result = generate_cold_email(
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
                "subject"      : result.get("subject",  ""),
                "body"         : result.get("body",     ""),
                "gap"          : result.get("gap",      ""),
                "proposal"     : result.get("proposal", ""),
                "why_fits"     : result.get("why_fits", ""),
                "decision"     : None,
            }
        except Exception as e:
            logger.error(f"Email generate error {company['name']}: {e}")
            st.session_state["email_previews"][co_id] = {"error": str(e)}


# ═════════════════════════════════════════════
# SEND EMAIL
# ═════════════════════════════════════════════

def _send_cold_email(user_id: int, co_id: int, company: dict, ep: dict):
    from backend.agents.email_sender import send_email

    resume_path = f"uploads/{user_id}/resume_base.pdf"
    if not os.path.exists(resume_path):
        resume_path = ""

    with st.spinner(f"📤 {company['name']} ko email bhej raha hai..."):
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
        # ── FIX: persistent sent status ──────────────────────────────────
        _mark_sent(co_id)

        if "company_statuses" not in st.session_state:
            st.session_state["company_statuses"] = {}
        st.session_state["company_statuses"][co_id] = "awaiting"

        _update_tracker(user_id, company, ep)

        # Google Sheets update
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

        # Show success toast — visible even after rerun
        st.toast(f"✅ Email sent to {ep['contact_name']} @ {company['name']}!", icon="🚀")

    else:
        st.error(f"❌ Failed: {result.get('error')}")


# ═════════════════════════════════════════════
# COMPANY CARD
# ═════════════════════════════════════════════

def _render_company_card(company: dict, co_id: int):
    contacts = company.get("contacts", [])
    status   = st.session_state.get("company_statuses", {}).get(co_id, "")
    already_sent = _is_sent(co_id)

    status_badge = {
        "awaiting"     : "⏳ Awaiting",
        "replied"      : "📩 Replied",
        "followup_sent": "🔄 Follow Up Sent",
        ""             : "",
    }.get(status, "")

    source_badges = {
        "yc_api"   : "🟠 YC",
        "hn_hiring": "🟤 HN",
        "betalist" : "🟣 Betalist",
    }
    src_badge = source_badges.get(company["source"], "⚪")
    ct_badge  = f"👥 {len(contacts)}" if contacts else "⚠️ No contacts"

    # FIX — show ✅ Sent badge in header if already sent
    sent_badge = " — ✅ **Sent**" if already_sent else ""
    header = f"{src_badge} **{company['name']}** — {company.get('funding', '?')} — {ct_badge}"
    if status_badge and not already_sent:
        header += f" — {status_badge}"
    header += sent_badge

    with st.expander(header):

        # ── Company Info ──────────────────────
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

        # ── Contacts ──────────────────────────
        if contacts:
            st.divider()
            st.caption("**Contacts:**")
            for ct in contacts:
                v = "✅" if ct.get("verified") else "⚠️"
                cc1, cc2, cc3 = st.columns([3, 5, 2])
                cc1.write(f"👤 **{ct['name']}** ({ct['role']})")
                cc2.code(ct.get("email", ""))
                cc3.caption(v)
        else:
            st.warning("⚠️ No contacts — email nahi bhej sakte")
            return

        # ── Already Sent — show summary, no buttons ───────────────────────
        if already_sent:
            ep = st.session_state.get("email_previews", {}).get(co_id, {})
            st.divider()
            st.success("✅ Email bhej di gayi! Tracker mein track ho rahi hai.")

            if ep.get("subject"):
                st.markdown(f"**📌 Subject:** {ep['subject']}")
            if ep.get("contact_email"):
                st.markdown(f"**📧 Sent to:** `{ep['contact_email']}`")

            col1, col2 = st.columns(2)
            with col1:
                if ep.get("gap"):
                    st.error(f"**🔍 Gap identified**\n\n{ep['gap'][:120]}")
            with col2:
                if ep.get("proposal"):
                    st.info(f"**💡 Proposal**\n\n{ep['proposal'][:120]}")
            return
        # ─────────────────────────────────────────────────────────────────

        # ── Email Generate (on first open) ────
        _generate_email(user_id, co_id, company)

        ep = st.session_state.get("email_previews", {}).get(co_id)
        if not ep:
            return

        if ep.get("error"):
            st.error(f"❌ Email generate nahi hua: {ep['error']}")
            return

        # ── Email Preview ─────────────────────
        st.divider()
        st.markdown("### 📧 Email")

        ec1, ec2 = st.columns(2)
        ec1.info(f"**To:** {ep.get('contact_name')} ({ep.get('contact_role')})")
        ec2.success(f"**Email:** {ep.get('contact_email')}")

        if ep.get("gap"):
            g1, g2, g3 = st.columns(3)
            g1.error(f"**🔍 Gap**\n\n{ep['gap'][:100]}")
            g2.info(f"**💡 Proposal**\n\n{ep['proposal'][:100]}")
            g3.success(f"**🎯 Why You**\n\n{ep['why_fits'][:100]}")

        st.divider()

        if ep.get("decision") == "skip":
            st.info("⏭️ Skipped")
            return

        # Edit mode toggle
        edit_key = f"editing_{co_id}"
        editing  = st.session_state.get(edit_key, False)

        if editing:
            new_subj = st.text_input(
                "✏️ Subject",
                value = ep.get("subject", ""),
                key   = f"subj_{co_id}"
            )
            new_body = st.text_area(
                "✏️ Body",
                value  = ep.get("body", ""),
                height = 250,
                key    = f"body_{co_id}"
            )
            st.session_state["email_previews"][co_id]["subject"] = new_subj
            st.session_state["email_previews"][co_id]["body"]    = new_body
        else:
            st.text_input(
                "📌 Subject",
                value    = ep.get("subject", ""),
                disabled = True,
                key      = f"subj_d_{co_id}"
            )
            st.text_area(
                "📝 Body",
                value    = ep.get("body", ""),
                height   = 200,
                disabled = True,
                key      = f"body_d_{co_id}"
            )

        # Action buttons
        ea1, ea2, ea3 = st.columns(3)
        with ea1:
            if st.button("🚀 Send Email", key=f"send_{co_id}", type="primary"):
                _send_cold_email(user_id, co_id, company, ep)
                st.rerun()
        with ea2:
            btn_label = "💾 Save & Close" if editing else "✏️ Edit Email"
            if st.button(btn_label, key=f"edit_{co_id}"):
                st.session_state[edit_key] = not editing
                st.rerun()
        with ea3:
            if st.button("❌ Skip", key=f"skip_{co_id}"):
                st.session_state["email_previews"][co_id]["decision"] = "skip"
                st.rerun()


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

# ── Sent counter in sidebar ───────────────────
sent_count = len(st.session_state.get("sent_ids", set()))
if sent_count:
    st.sidebar.success(f"✅ {sent_count} email(s) sent this session")

# ── Find Button ───────────────────────────────
if st.button("🔍 Find Startups", type="primary"):
    st.session_state["scraped_companies"]  = []
    st.session_state["email_previews"]     = {}
    st.session_state["company_statuses"]   = {}
    st.session_state["sent_ids"]           = set()   # reset on new search
    st.session_state["is_scraping"]        = True
    st.session_state["scraping_done"]      = False
    st.rerun()

# ── STREAMING ─────────────────────────────────
if st.session_state.get("is_scraping"):
    from backend.agents.scraper_agent import (
        stream_yc_companies,
        stream_hn_hiring,
        stream_betalist,
    )

    status     = st.empty()
    cards_area = st.container()
    status.info("🟠 YC Companies scraping...")

    yc_count = 0
    for co in stream_yc_companies(prefs):
        co_id = len(st.session_state["scraped_companies"])
        st.session_state["scraped_companies"].append(co)
        yc_count += 1
        status.info(f"🟠 YC: {yc_count} found...")
        with cards_area:
            _render_company_card(co, co_id)

    status.info(f"🟤 HN Hiring scraping... ({yc_count} YC mile)")
    hn_count = 0
    for co in stream_hn_hiring(prefs):
        co_id = len(st.session_state["scraped_companies"])
        st.session_state["scraped_companies"].append(co)
        hn_count += 1
        status.info(f"🟤 HN: {hn_count} found, total: {yc_count + hn_count}...")
        with cards_area:
            _render_company_card(co, co_id)

    status.info(f"🟣 Betalist scraping... ({yc_count + hn_count} total)")
    bl_count = 0
    for co in stream_betalist(prefs):
        co_id = len(st.session_state["scraped_companies"])
        st.session_state["scraped_companies"].append(co)
        bl_count += 1
        status.info(
            f"🟣 Betalist: {bl_count} found, "
            f"total: {yc_count + hn_count + bl_count}..."
        )
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

# ── SAVED RESULTS ─────────────────────────────
else:
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

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total",         len(companies))
    col2.metric("Filtered",      len(filtered))
    col3.metric("With Contacts", sum(1 for c in filtered if c.get("contacts")))
    col4.metric("✅ Sent",        len(st.session_state.get("sent_ids", set())))

    if not filtered:
        st.info("Filter change karo")
        st.stop()

    # ── Cards ─────────────────────────────────
    filtered_ids = set(id(c) for c in filtered)
    for co_id, company in enumerate(companies):
        if id(company) in filtered_ids:
            _render_company_card(company, co_id)