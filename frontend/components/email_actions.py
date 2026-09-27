# frontend/components/email_actions.py
"""
Shared draft/edit/send/skip logic for a single company's outreach email.

Used by both the Home feed (inline, no page navigation) and the Cold Outreach
page, so the two stay behaviorally identical instead of drifting apart.
"""

import os
import streamlit as st


def generate_email(user_id: int, co_id, company: dict):
    if "email_previews" not in st.session_state:
        st.session_state["email_previews"] = {}
    if co_id in st.session_state["email_previews"]:
        return

    from backend.agents.email_generator import generate_cold_email

    contacts = company.get("contacts", [])
    contact = next((c for c in contacts if c.get("email")), None)
    if not contact:
        st.session_state["email_previews"][co_id] = {"error": "No contact email found"}
        return

    with st.spinner(f"Drafting email for {company['name']}..."):
        try:
            result = generate_cold_email(
                user_id=user_id, company=company["name"],
                description=company.get("company_summary") or company.get("description", ""),
                one_liner=company.get("one_liner", ""), contact=contact,
                ai_hook=company.get("ai_hook", ""),
                recent_highlight=company.get("recent_highlight", ""),
                tech_stack=company.get("tech_stack", []),
            )
            if result.get("error"):
                st.session_state["email_previews"][co_id] = {"error": result["error"]}
                return
            st.session_state["email_previews"][co_id] = {
                "contact_name" : contact.get("name", ""),
                "contact_role" : contact.get("role", ""),
                "contact_email": contact.get("email", ""),
                "subject"      : result.get("subject", ""),
                "body"         : result.get("body", ""),
                "gap"          : result.get("gap", ""),
                "proposal"     : result.get("proposal", ""),
                "why_fits"     : result.get("why_fits", ""),
                "decision"     : None,
            }
        except Exception as e:
            st.session_state["email_previews"][co_id] = {"error": str(e)}


def is_sent(co_id) -> bool:
    if co_id in st.session_state.get("sent_ids", set()):
        return True
    return st.session_state.get("email_previews", {}).get(co_id, {}).get("decision") == "sent"


def mark_sent(user_id: int, co_id):
    if "sent_ids" not in st.session_state:
        st.session_state["sent_ids"] = set()
    st.session_state["sent_ids"].add(co_id)
    if co_id in st.session_state.get("email_previews", {}):
        st.session_state["email_previews"][co_id]["decision"] = "sent"
    try:
        from backend.utils.feed_to_db import mark_company_contacted
        mark_company_contacted(user_id, co_id)
    except Exception:
        pass


def send_email_action(user_id: int, co_id, company: dict, ep: dict):
    from backend.agents.email_sender import send_email, get_gmail_creds
    from backend.database import SessionLocal
    from backend.models.user import UserProfile

    creds = get_gmail_creds(user_id)
    if "error" in creds:
        st.error(f"❌ Gmail credentials missing: {creds['error']}")
        return

    resume_path = ""
    db = SessionLocal()
    try:
        prof = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        if prof and prof.resume_path and os.path.exists(prof.resume_path):
            resume_path = prof.resume_path
    finally:
        db.close()

    to_email = ep.get("contact_email", "").strip()
    subject  = ep.get("subject", "").strip()
    body     = ep.get("body", "").strip()
    if not to_email:
        st.error("❌ Contact email is missing."); return
    if not subject:
        st.error("❌ Subject is empty."); return
    if not body:
        st.error("❌ Email body is empty."); return

    with st.spinner(f"Sending to {to_email}..."):
        result = send_email(
            user_id=user_id, to_email=to_email, subject=subject, body=body,
            resume_path=resume_path, company=company["name"],
            contact=ep.get("contact_name", ""), contact_role=ep.get("contact_role", ""),
            gap=ep.get("gap", ""), proposal=ep.get("proposal", ""),
            website=company.get("website", ""),
        )

    if result.get("success"):
        mark_sent(user_id, co_id)
        st.success(f"✅ Sent to `{to_email}` at {result.get('sent_at', '')[:19]}")
        st.toast(f"✅ Sent to {ep.get('contact_name', '')} @ {company['name']}!", icon="🚀")
    else:
        err = result.get("error", "Unknown")
        st.error(f"❌ Send failed: {err}")
        if "auth" in err.lower() or "password" in err.lower():
            st.warning("🔧 Fix: Create an App Password and add it in Profile Setup.")


def render_email_panel(user_id: int, co_id, company: dict, uid: str, auto_draft: bool = False):
    """Renders the draft / edit / send / skip UI for one company, inline —
    no page navigation. `uid` must be unique+stable per company (tie it to co_id)."""

    if is_sent(co_id):
        ep = st.session_state.get("email_previews", {}).get(co_id, {})
        st.success("✅ Email sent — check the Tracker for details.")
        if ep.get("subject"):
            st.write(f"**Subject:** {ep['subject']}")
        if ep.get("contact_email"):
            st.write(f"**To:** `{ep['contact_email']}`")
        return

    has_draft = co_id in st.session_state.get("email_previews", {})
    if not has_draft:
        if not auto_draft:
            if st.button("✉️ Draft Email", key=f"draft_btn_{uid}", type="primary", use_container_width=True):
                generate_email(user_id, co_id, company)
                st.rerun()
            return
        generate_email(user_id, co_id, company)

    ep = st.session_state.get("email_previews", {}).get(co_id)
    if not ep:
        return
    if ep.get("error"):
        st.error(f"❌ {ep['error']}")
        return
    if ep.get("decision") == "skip":
        st.caption("⏭ Skipped")
        return

    st.markdown("### 📧 Draft Email")
    ec1, ec2 = st.columns(2)
    ec1.write(f"**To:** {ep.get('contact_name', '')} ({ep.get('contact_role', '')})")
    ec2.write(f"**Email:** `{ep.get('contact_email', '')}`")

    g1, g2, g3 = st.columns(3)
    with g1:
        if ep.get("gap"):
            st.markdown(f'<div class="gap-box"><b style="font-size:11px;color:#ff6b35">GAP</b><br>{ep["gap"][:100]}</div>', unsafe_allow_html=True)
    with g2:
        if ep.get("proposal"):
            st.markdown(f'<div class="proposal-box"><b style="font-size:11px;color:#4ade80">PROPOSAL</b><br>{ep["proposal"][:100]}</div>', unsafe_allow_html=True)
    with g3:
        if ep.get("why_fits"):
            st.markdown(f'<div class="hook-box"><b style="font-size:11px;color:#8b5cf6">WHY YOU</b><br>{ep["why_fits"][:100]}</div>', unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    edit_key = f"editing_{uid}"
    editing = st.session_state.get(edit_key, False)
    if editing:
        ns = st.text_input("Subject", value=ep.get("subject", ""), key=f"subj_{uid}")
        nb = st.text_area("Body", value=ep.get("body", ""), height=220, key=f"body_{uid}")
        st.session_state["email_previews"][co_id]["subject"] = ns
        st.session_state["email_previews"][co_id]["body"] = nb
    else:
        st.text_input("Subject", value=ep.get("subject", ""), disabled=True, key=f"subj_d_{uid}")
        st.text_area("Body", value=ep.get("body", ""), disabled=True, height=200, key=f"body_d_{uid}")
    st.markdown("<br>", unsafe_allow_html=True)

    a1, a2, a3 = st.columns([2, 1, 1])
    with a1:
        if st.button("🚀 Send Email", key=f"send_{uid}", type="primary", use_container_width=True):
            send_email_action(user_id, co_id, company, ep)
    with a2:
        lbl = "💾 Save" if editing else "✏️ Edit"
        if st.button(lbl, key=f"edit_{uid}", use_container_width=True):
            st.session_state[edit_key] = not editing
            st.rerun()
    with a3:
        if st.button("❌ Skip", key=f"skip_{uid}", use_container_width=True):
            st.session_state["email_previews"][co_id]["decision"] = "skip"
            st.rerun()
