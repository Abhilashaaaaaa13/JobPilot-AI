# frontend/pages/4_outreach.py

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import json
import streamlit as st
from loguru import logger

if "user_id" not in st.session_state:
    st.warning("Pehle login karo")
    st.stop()

user_id = st.session_state["user_id"]

# ─────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap');
html,body,[data-testid="stAppViewContainer"]{background:#0d0d0d!important;color:#f0f0f0!important;font-family:'DM Sans',sans-serif!important}
[data-testid="stSidebar"]{background:#161616!important;border-right:1px solid #2a2a2a!important}
h1,h2,h3{font-family:'Space Mono',monospace!important}
.stButton>button{background:#e8ff47!important;color:#000!important;border:none!important;border-radius:4px!important;font-family:'Space Mono',monospace!important;font-weight:700!important;font-size:12px!important;transition:all .15s!important}
.stButton>button:hover{background:#fff!important;transform:translateY(-1px)!important}
.stButton>button[kind="secondary"]{background:transparent!important;color:#f0f0f0!important;border:1px solid #2a2a2a!important}
.stButton>button[kind="secondary"]:hover{border-color:#e8ff47!important;color:#e8ff47!important}
.stTextInput>div>div>input,.stTextArea>div>div>textarea{background:#161616!important;border:1px solid #2a2a2a!important;color:#f0f0f0!important}
.stTextInput>div>div>input:focus,.stTextArea>div>div>textarea:focus{border-color:#e8ff47!important}
.stExpander{border:1px solid #2a2a2a!important;border-radius:6px!important;background:#161616!important}
.stExpander:hover{border-color:#3a3a3a!important}
[data-testid="stSidebarNav"]{display:none!important}
.gap-box{background:rgba(255,107,53,.05);border-left:3px solid #ff6b35;padding:10px 14px;border-radius:0 6px 6px 0;font-size:13px}
.proposal-box{background:rgba(74,222,128,.05);border-left:3px solid #4ade80;padding:10px 14px;border-radius:0 6px 6px 0;font-size:13px}
.hook-box{background:rgba(232,255,71,.04);border:1px solid rgba(232,255,71,.15);border-radius:6px;padding:10px 14px}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### ⚡ OutreachAI")
    st.caption(st.session_state.get("email", ""))
    st.divider()
    st.page_link("app.py",                label="⚡  Home",          use_container_width=True)
    st.page_link("pages/2_onboarding.py", label="👤  Profile Setup", use_container_width=True)
    st.page_link("pages/4_outreach.py",   label="🚀  Cold Outreach", use_container_width=True)
    st.page_link("pages/5_tracker.py",    label="📊  Tracker",       use_container_width=True)
    st.divider()
    sent_count = len(st.session_state.get("sent_ids", set()))
    if sent_count:
        st.success(f"✅ {sent_count} sent this session")


# ═════════════════════════════════════════════
# HELPERS
# ═════════════════════════════════════════════

def _load_sent_log():
    from backend.agents.email_sender import get_sent_log
    return get_sent_log(user_id)


def _mark_sent(co_id):
    if "sent_ids" not in st.session_state:
        st.session_state["sent_ids"] = set()
    st.session_state["sent_ids"].add(co_id)
    if "email_previews" in st.session_state and co_id in st.session_state["email_previews"]:
        st.session_state["email_previews"][co_id]["decision"] = "sent"


def _is_sent(co_id):
    if co_id in st.session_state.get("sent_ids", set()):
        return True
    return st.session_state.get("email_previews", {}).get(co_id, {}).get("decision") == "sent"


def _send_email(co_id, company, ep):
    """
    Gmail SMTP se bhejo.
    Saara debug UI mein dikhega — koi silent failure nahi.
    """
    from backend.agents.email_sender import send_email, get_gmail_creds
    from backend.database import SessionLocal
    from backend.models.user import UserProfile

    # ── Step 1: Gmail credentials check ──────
    creds = get_gmail_creds(user_id)
    if "error" in creds:
        st.error(f"❌ Gmail credentials missing: {creds['error']}")
        st.info("👉 Profile Setup mein jaao → Gmail Address aur App Password daalo")
        return

    st.info(f"📧 Gmail account: `{creds['email']}`")

    # ── Step 2: Resume path ───────────────────
    resume_path = ""
    db = SessionLocal()
    try:
        prof = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        if prof and prof.resume_path:
            resume_path = prof.resume_path
            if os.path.exists(resume_path):
                st.info(f"📎 Resume found: `{resume_path}`")
            else:
                st.warning(f"⚠️ Resume path set but file missing: `{resume_path}` — email bina resume ke jaayegi")
                resume_path = ""
    finally:
        db.close()

    # ── Step 3: Validate email fields ────────
    to_email = ep.get("contact_email", "").strip()
    subject  = ep.get("subject", "").strip()
    body     = ep.get("body", "").strip()

    if not to_email:
        st.error("❌ Contact email missing — email nahi bhej sakte")
        return
    if not subject:
        st.error("❌ Subject empty hai")
        return
    if not body:
        st.error("❌ Email body empty hai")
        return

    st.info(f"📤 Sending to: `{to_email}` | Subject: `{subject[:50]}`")

    # ── Step 4: Send ──────────────────────────
    with st.spinner(f"📤 SMTP se bhej rahe hain → {to_email}..."):
        result = send_email(
            user_id      = user_id,
            to_email     = to_email,
            subject      = subject,
            body         = body,
            resume_path  = resume_path,
            company      = company["name"],
            contact      = ep.get("contact_name",  ""),
            contact_role = ep.get("contact_role",  ""),
            gap          = ep.get("gap",           ""),
            proposal     = ep.get("proposal",      ""),
            website      = company.get("website",  ""),
        )

    # ── Step 5: Result ────────────────────────
    if result.get("success"):
        _mark_sent(co_id)
        st.success(f"✅ Email sent! → `{to_email}` at {result.get('sent_at','')[:19]}")
        st.toast(f"✅ Sent to {ep.get('contact_name','')} @ {company['name']}!", icon="🚀")
        logger.info(f"SENT: {to_email} ({company['name']})")
    else:
        err = result.get("error", "Unknown error")
        st.error(f"❌ Send failed: {err}")
        # Common fix hints
        if "auth" in err.lower() or "password" in err.lower():
            st.warning(
                "🔧 Fix: Google Account → Security → 2-Step Verification ON karo "
                "→ phir App Passwords mein 'Mail' app password banao → woh 16-char password "
                "Profile Setup mein daalo (spaces ke bina)"
            )
        elif "recipient" in err.lower():
            st.warning(f"🔧 Fix: Email address galat lag raha hai: `{to_email}`")
        logger.error(f"SEND FAILED: {to_email} | {err}")


def _generate_email(co_id, company):
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

    with st.spinner(f"✍️ Drafting email for {company['name']}..."):
        try:
            result = generate_cold_email(
                user_id          = user_id,
                company          = company["name"],
                description      = company.get("company_summary") or company.get("description", ""),
                one_liner        = company.get("one_liner", ""),
                contact          = contact,
                ai_hook          = company.get("ai_hook", ""),
                recent_highlight = company.get("recent_highlight", ""),
                tech_stack       = company.get("tech_stack", []),
            )
            if result.get("error"):
                st.session_state["email_previews"][co_id] = {"error": result["error"]}
                return
            st.session_state["email_previews"][co_id] = {
                "contact_name" : contact.get("name",  ""),
                "contact_role" : contact.get("role",  ""),
                "contact_email": contact.get("email", ""),
                "subject"      : result.get("subject",  ""),
                "body"         : result.get("body",     ""),
                "gap"          : result.get("gap",      ""),
                "proposal"     : result.get("proposal", ""),
                "why_fits"     : result.get("why_fits", ""),
                "decision"     : None,
            }
        except Exception as e:
            st.session_state["email_previews"][co_id] = {"error": str(e)}


# ═════════════════════════════════════════════
# COMPANY CARD
# ═════════════════════════════════════════════

def _render_company_card(company, co_id, expanded=False):
    contacts     = company.get("contacts", [])
    already_sent = _is_sent(co_id)

    source_icons = {"yc_api": "🟠 YC", "betalist": "🟣 BL", "product_hunt": "🔴 PH"}
    src    = source_icons.get(company.get("source", ""), "⚪")
    ct_str = f"✉️ {len(contacts)}" if contacts else "⚠️ no contacts"
    sfx    = " · ✅ Sent" if already_sent else ""
    header = f"{src}  **{company['name']}** · {company.get('funding','?')} · {ct_str}{sfx}"

    with st.expander(header, expanded=expanded):

        r1, r2 = st.columns(2)
        r1.metric("Team",     company.get("team_size", "?"))
        r2.metric("Location", (company.get("location") or "?")[:20])

        if company.get("one_liner"):
            st.info(company["one_liner"])
        if company.get("website"):
            st.markdown(f"[🔗 {company['website']}]({company['website']})")

        if any([company.get("ai_hook"), company.get("recent_highlight"), company.get("tech_stack")]):
            with st.expander("🔬 Research insights"):
                if company.get("recent_highlight") and company["recent_highlight"] != "N/A":
                    st.write(f"**Recent:** {company['recent_highlight']}")
                if company.get("ai_hook") and company["ai_hook"] != "N/A":
                    st.write(f"**AI angle:** {company['ai_hook']}")
                if company.get("tech_stack"):
                    st.write(f"**Stack:** {', '.join(company['tech_stack'][:6])}")

        if contacts:
            st.write("**Contacts:**")
            for ct in contacts:
                v = "✅" if ct.get("verified") else "⚠️"
                cc1, cc2, cc3 = st.columns([3, 5, 1])
                cc1.write(f"**{ct.get('name','')}** · {ct.get('role','')}")
                cc2.code(ct.get("email", ""))
                cc3.write(v)
        else:
            st.warning("No contacts — email nahi bhej sakte")
            return

        st.divider()

        if already_sent:
            ep = st.session_state.get("email_previews", {}).get(co_id, {})
            st.success("✅ Email Sent — Tracker mein dekho")
            if ep.get("subject"):
                st.write(f"**Subject:** {ep['subject']}")
            if ep.get("contact_email"):
                st.write(f"**To:** `{ep['contact_email']}`")
            c1, c2 = st.columns(2)
            with c1:
                if ep.get("gap"):
                    st.markdown(f'<div class="gap-box"><b>Gap</b><br>{ep["gap"][:120]}</div>', unsafe_allow_html=True)
            with c2:
                if ep.get("proposal"):
                    st.markdown(f'<div class="proposal-box"><b>Proposal</b><br>{ep["proposal"][:120]}</div>', unsafe_allow_html=True)
            return

        _generate_email(co_id, company)
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
        ec1.write(f"**To:** {ep.get('contact_name','')} ({ep.get('contact_role','')})")
        ec2.write(f"**Email:** `{ep.get('contact_email','')}`")

        g1, g2, g3 = st.columns(3)
        with g1:
            if ep.get("gap"):
                st.markdown(f'<div class="gap-box"><b style="font-size:11px;color:#ff6b35">GAP</b><br>{ep["gap"][:100]}</div>', unsafe_allow_html=True)
        with g2:
            if ep.get("proposal"):
                st.markdown(f'<div class="proposal-box"><b style="font-size:11px;color:#4ade80">PROPOSAL</b><br>{ep["proposal"][:100]}</div>', unsafe_allow_html=True)
        with g3:
            if ep.get("why_fits"):
                st.markdown(f'<div class="hook-box"><b style="font-size:11px;color:#e8ff47">WHY YOU</b><br>{ep["why_fits"][:100]}</div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        edit_key = f"editing_{co_id}"
        editing  = st.session_state.get(edit_key, False)

        if editing:
            new_subj = st.text_input("Subject", value=ep.get("subject", ""), key=f"subj_{co_id}")
            new_body = st.text_area("Body",     value=ep.get("body",    ""), height=220, key=f"body_{co_id}")
            st.session_state["email_previews"][co_id]["subject"] = new_subj
            st.session_state["email_previews"][co_id]["body"]    = new_body
        else:
            st.text_input("Subject", value=ep.get("subject", ""), disabled=True, key=f"subj_d_{co_id}")
            st.text_area("Body",     value=ep.get("body",    ""), disabled=True, height=200, key=f"body_d_{co_id}")

        st.markdown("<br>", unsafe_allow_html=True)

        a1, a2, a3 = st.columns([2, 1, 1])
        with a1:
            if st.button("🚀 Send Email", key=f"send_{co_id}", type="primary", use_container_width=True):
                _send_email(co_id, company, ep)
                # rerun nahi — result screen pe dikhne do, card stable rahe
        with a2:
            lbl = "💾 Save" if editing else "✏️ Edit"
            if st.button(lbl, key=f"edit_{co_id}", use_container_width=True):
                st.session_state[edit_key] = not editing
                st.rerun()
        with a3:
            if st.button("❌ Skip", key=f"skip_{co_id}", use_container_width=True):
                st.session_state["email_previews"][co_id]["decision"] = "skip"
                st.rerun()


# ═════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════

st.markdown("# 🚀 Cold Outreach")
st.caption("Feed se company chuno ya fresh scrape karo — email draft karo — bhejo")

# ── Gmail credential check — page load pe hi batao ──
from backend.agents.email_sender import get_gmail_creds
_creds_check = get_gmail_creds(user_id)
if "error" in _creds_check:
    st.error(f"⚠️ Gmail setup incomplete: {_creds_check['error']}")
    st.warning(
        "**Fix karo:** Profile Setup → Gmail Address + App Password daalo\n\n"
        "App Password banane ka tarika:\n"
        "1. myaccount.google.com → Security\n"
        "2. 2-Step Verification ON karo\n"
        "3. App Passwords → 'Mail' select karo → 16-char password copy karo\n"
        "4. Woh password Profile Setup mein daalo (bina spaces ke)"
    )
    if st.button("👤 Go to Profile Setup", type="primary"):
        st.switch_page("pages/2_onboarding.py")
    st.stop()
else:
    st.success(f"✅ Gmail ready: `{_creds_check['email']}`")

if "prefs" not in st.session_state:
    from backend.database import SessionLocal
    from backend.models.user import UserProfile
    db = SessionLocal()
    try:
        prof = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        if prof:
            st.session_state["prefs"] = {
                "preferred_type": prof.preferred_type or "job",
                "domains"       : json.loads(prof.target_industries or '["ai_ml"]'),
                "target_roles"  : json.loads(prof.target_roles or '["Software Engineer"]'),
                "skills"        : json.loads(prof.skills or "[]"),
                "location"      : "remote",
            }
    except Exception:
        pass
    finally:
        db.close()

prefs = st.session_state.get("prefs", {
    "preferred_type": "job",
    "domains"       : ["ai_ml"],
    "target_roles"  : ["AI Engineer"],
    "location"      : "remote",
})

# ─────────────────────────────────────────────
# FEED COMPANY — Home se aaya?
# ─────────────────────────────────────────────

feed_company = st.session_state.get("feed_outreach_company", None)
feed_co_id   = st.session_state.get("feed_outreach_co_id",   None)

if feed_company:
    co_id = feed_co_id if (feed_co_id and feed_co_id > 0) else 8000

    # Sent ho gaya? Tab clear karo
    if _is_sent(co_id):
        st.session_state.pop("feed_outreach_company", None)
        st.session_state.pop("feed_outreach_co_id",   None)
        st.success(f"✅ Email sent! Tracker mein dekho.")
    else:
        st.info(f"📬 **{feed_company.get('name')}** — email draft ho raha hai...")
        st.divider()
        _render_company_card(feed_company, co_id, expanded=True)
        st.divider()
        st.markdown("<br>", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# FIND STARTUPS
# ─────────────────────────────────────────────

col_find, col_info = st.columns([1, 3])
with col_find:
    find_clicked = st.button("🔍 Find More Startups", type="primary", use_container_width=True)
with col_info:
    if st.session_state.get("scraped_companies"):
        total = len(st.session_state["scraped_companies"])
        sent  = len(st.session_state.get("sent_ids", set()))
        st.caption(f"{total} companies loaded  ·  {sent} sent this session")

if find_clicked:
    st.session_state["scraped_companies"] = []
    st.session_state["email_previews"]    = {}
    st.session_state["sent_ids"]          = set()
    st.session_state["is_scraping"]       = True
    st.session_state["scraping_done"]     = False
    st.rerun()

# ─────────────────────────────────────────────
# STREAMING SCRAPE
# ─────────────────────────────────────────────

if st.session_state.get("is_scraping"):
    from backend.agents.scraper_agent import stream_yc_companies, stream_betalist

    status_ph  = st.empty()
    cards_area = st.container()
    counts     = {"yc": 0, "bl": 0}

    status_ph.info("🟠 YC Companies scraping...")
    try:
        for co in stream_yc_companies(prefs):
            co_id = len(st.session_state["scraped_companies"])
            st.session_state["scraped_companies"].append(co)
            counts["yc"] += 1
            status_ph.info(f"🟠 YC: {counts['yc']} found...")
            with cards_area:
                _render_company_card(co, co_id)
    except Exception as e:
        status_ph.warning(f"⚠️ YC error: {e}")

    status_ph.info(f"🟣 Betalist scraping... ({counts['yc']} YC done)")
    try:
        for co in stream_betalist(prefs):
            co_id = len(st.session_state["scraped_companies"])
            st.session_state["scraped_companies"].append(co)
            counts["bl"] += 1
            status_ph.info(f"🟣 Betalist: {counts['bl']} found...")
            with cards_area:
                _render_company_card(co, co_id)
    except Exception as e:
        status_ph.warning(f"⚠️ Betalist error: {e}")

    total = counts["yc"] + counts["bl"]
    status_ph.success(f"✅ Done — {total} startups")
    st.session_state["is_scraping"]   = False
    st.session_state["scraping_done"] = True
    st.rerun()

# ─────────────────────────────────────────────
# SCRAPED / FEED RESULTS
# ─────────────────────────────────────────────

else:
    companies = st.session_state.get("scraped_companies", [])

    if not companies:
        st.divider()
        st.caption("💡 Feed se fresh companies — ya 'Find More Startups' dabao")

        feed_path = "data/company_feed.json"
        if os.path.exists(feed_path):
            try:
                with open(feed_path) as f:
                    feed = json.load(f)

                sent_log  = _load_sent_log()
                c_names   = {(e.get("company") or e.get("to") or "").lower().strip() for e in sent_log}
                c_domains = set()
                for e in sent_log:
                    w = (e.get("website") or "").lower()
                    if w:
                        d = w.replace("https://","").replace("http://","").rstrip("/").split("/")[0]
                        if d:
                            c_domains.add(d)

                def _fresh(c):
                    if (c.get("name") or "").lower().strip() in c_names:
                        return False
                    w = (c.get("website") or "").lower()
                    if w:
                        d = w.replace("https://","").replace("http://","").rstrip("/").split("/")[0]
                        if d in c_domains:
                            return False
                    return True

                feed_cos = [c for c in feed.get("companies", []) if _fresh(c)][:20]

                if not feed_cos:
                    st.info("Saari companies outreach ho chuki hain. 'Find More Startups' dabao.")
                else:
                    st.caption(f"{len(feed_cos)} fresh companies")
                    for i, co in enumerate(feed_cos):
                        _render_company_card(co, 9000 + i)

            except Exception as e:
                st.warning(f"Feed load error: {e}")
        else:
            st.info("'Find More Startups' dabao")

    else:
        f1, f2, f3, f4 = st.columns(4)
        with f1:
            src_f = st.selectbox("Source", ["all"] + list({c.get("source","?") for c in companies}), key="out_src")
        with f2:
            ct_f = st.checkbox("Has Contacts",   key="out_ct")
        with f3:
            vr_f = st.checkbox("Verified Email", key="out_vr")
        with f4:
            ai_f = st.checkbox("AI related",     key="out_ai")

        filtered = companies
        if src_f != "all":
            filtered = [c for c in filtered if c.get("source") == src_f]
        if ct_f:
            filtered = [c for c in filtered if c.get("contacts")]
        if vr_f:
            filtered = [c for c in filtered if any(ct.get("verified") for ct in c.get("contacts", []))]
        if ai_f:
            filtered = [c for c in filtered if c.get("ai_related")]

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total",         len(companies))
        m2.metric("Filtered",      len(filtered))
        m3.metric("With Contacts", sum(1 for c in filtered if c.get("contacts")))
        m4.metric("✅ Sent",        len(st.session_state.get("sent_ids", set())))

        if not filtered:
            st.info("Filter change karo — koi results nahi")
            st.stop()

        st.markdown("<br>", unsafe_allow_html=True)
        filtered_ids = {id(c) for c in filtered}
        for co_id, company in enumerate(companies):
            if id(company) in filtered_ids:
                _render_company_card(company, co_id)