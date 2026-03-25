# frontend/pages/4_outreach.py

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import json
import streamlit as st
from datetime import datetime
from loguru   import logger

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
.tag{display:inline-block;background:rgba(232,255,71,.1);color:#e8ff47;border:1px solid rgba(232,255,71,.25);border-radius:3px;padding:1px 7px;font-size:11px;font-family:'Space Mono',monospace;margin:2px}
.tag-orange{background:rgba(255,107,53,.1);color:#ff6b35;border-color:rgba(255,107,53,.25)}
.tag-green{background:rgba(74,222,128,.1);color:#4ade80;border-color:rgba(74,222,128,.25)}
.tag-gray{background:rgba(255,255,255,.05);color:#888;border-color:#2a2a2a}
.co-name{font-family:'Space Mono',monospace;font-size:15px;font-weight:700}
.badge-sent{background:rgba(74,222,128,.12);color:#4ade80;border:1px solid rgba(74,222,128,.3);border-radius:3px;padding:2px 8px;font-size:11px;font-family:'Space Mono',monospace}
.hook-box{background:rgba(232,255,71,.04);border:1px solid rgba(232,255,71,.15);border-radius:6px;padding:10px 14px;margin-bottom:10px}
.gap-box{background:rgba(255,107,53,.05);border-left:3px solid #ff6b35;padding:10px 14px;border-radius:0 6px 6px 0;font-size:13px}
.proposal-box{background:rgba(74,222,128,.05);border-left:3px solid #4ade80;padding:10px 14px;border-radius:0 6px 6px 0;font-size:13px}
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
    st.divider()
    sent_count = len(st.session_state.get("sent_ids", set()))
    if sent_count:
        st.markdown(
            f'<p style="color:#4ade80;font-size:13px;font-family:\'Space Mono\',monospace">'
            f'✅ {sent_count} sent this session</p>',
            unsafe_allow_html=True
        )


# ═════════════════════════════════════════════
# HELPERS
# ═════════════════════════════════════════════

def _mark_sent(co_id: int):
    if "sent_ids" not in st.session_state:
        st.session_state["sent_ids"] = set()
    st.session_state["sent_ids"].add(co_id)
    if "email_previews" in st.session_state and co_id in st.session_state["email_previews"]:
        st.session_state["email_previews"][co_id]["decision"] = "sent"


def _is_sent(co_id: int) -> bool:
    if co_id in st.session_state.get("sent_ids", set()):
        return True
    return st.session_state.get("email_previews", {}).get(co_id, {}).get("decision") == "sent"


def _update_tracker(company: dict, ep: dict):
    log_dir  = f"uploads/{user_id}/sent_emails"
    log_file = f"{log_dir}/log.json"
    os.makedirs(log_dir, exist_ok=True)
    entry = {
        "to"            : ep["contact_email"],
        "company"       : company["name"],
        "website"       : company.get("website", ""),
        "contact_name"  : ep.get("contact_name",""),
        "contact_role"  : ep.get("contact_role",""),
        "subject"       : ep.get("subject",""),
        "gap"           : ep.get("gap",""),
        "proposal"      : ep.get("proposal",""),
        "status"        : "awaiting",
        "replied"       : False,
        "followup_sent" : False,
        "followup_count": 0,
        "sent_at"       : datetime.utcnow().isoformat(),
        "reply_at"      : None,
        "reply_body"    : None,
        "followup_at"   : None,
        "body"          : ep.get("body","")[:500],
    }
    try:
        existing = []
        if os.path.exists(log_file):
            with open(log_file) as f:
                existing = json.load(f)
        existing.append(entry)
        with open(log_file, "w") as f:
            json.dump(existing, f, indent=2)
    except Exception as e:
        logger.warning(f"Tracker log error: {e}")


def _generate_email(co_id: int, company: dict):
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
                description      = company.get("company_summary") or company.get("description",""),
                one_liner        = company.get("one_liner",""),
                contact          = contact,
                ai_hook          = company.get("ai_hook",""),
                recent_highlight = company.get("recent_highlight",""),
                tech_stack       = company.get("tech_stack",[]),
            )
            st.session_state["email_previews"][co_id] = {
                "contact_name" : contact.get("name",""),
                "contact_role" : contact.get("role",""),
                "contact_email": contact.get("email",""),
                "subject"      : result.get("subject",""),
                "body"         : result.get("body",""),
                "gap"          : result.get("gap",""),
                "proposal"     : result.get("proposal",""),
                "why_fits"     : result.get("why_fits",""),
                "decision"     : None,
            }
        except Exception as e:
            st.session_state["email_previews"][co_id] = {"error": str(e)}


def _send_email(co_id: int, company: dict, ep: dict):
    from backend.agents.email_sender import send_email

    resume_path = ""
    from backend.database import SessionLocal
    from backend.models.user import UserProfile
    db = SessionLocal()
    try:
        prof = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        if prof and prof.resume_path and os.path.exists(prof.resume_path):
            resume_path = prof.resume_path
    finally:
        db.close()

    with st.spinner(f"📤 Sending to {company['name']}..."):
        result = send_email(
            user_id     = user_id,
            to_email    = ep["contact_email"],
            subject     = ep["subject"],
            body        = ep["body"],
            resume_path = resume_path,
            company     = company["name"],
            contact     = ep.get("contact_name","")
        )

    if result.get("success"):
        _mark_sent(co_id)
        _update_tracker(company, ep)
        try:
            from backend.utils.sheets_tracker import log_cold_email
            log_cold_email(
                user_id       = user_id,
                company       = company["name"],
                website       = company.get("website",""),
                contact_name  = ep.get("contact_name",""),
                contact_role  = ep.get("contact_role",""),
                contact_email = ep["contact_email"],
                subject       = ep["subject"],
                gap           = ep.get("gap",""),
                proposal      = ep.get("proposal",""),
            )
        except Exception as e:
            logger.warning(f"Sheets error: {e}")
        st.toast(f"✅ Sent to {ep.get('contact_name','')} @ {company['name']}!", icon="🚀")
    else:
        st.error(f"❌ Failed: {result.get('error','unknown error')}")


# ═════════════════════════════════════════════
# COMPANY CARD
# ═════════════════════════════════════════════

def _render_company_card(company: dict, co_id: int):
    contacts     = company.get("contacts", [])
    already_sent = _is_sent(co_id)

    source_icons = {
        "yc_api"   : "🟠 YC",
        "hn_hiring": "🟤 HN",
        "betalist" : "🟣 BL",
    }
    src      = source_icons.get(company.get("source",""), "⚪")
    ct_str   = f"✉️ {len(contacts)}" if contacts else "⚠️ no contacts"
    sent_sfx = " · ✅ Sent" if already_sent else ""

    header = f"{src}  **{company['name']}** · {company.get('funding','?')} · {ct_str}{sent_sfx}"

    with st.expander(header, expanded=False):

        # Info row
        r1, r2, r3 = st.columns(3)
        r1.metric("Team",     company.get("team_size","?"))
        r2.metric("Location", company.get("location","?")[:18])
        r3.metric("Source",   company.get("source","?"))

        if company.get("one_liner"):
            st.markdown(
                f'<div class="hook-box">'
                f'<span style="color:#888;font-size:11px;font-family:\'Space Mono\',monospace">ONE LINER</span><br>'
                f'<span style="font-size:13px">{company["one_liner"]}</span>'
                f'</div>',
                unsafe_allow_html=True
            )

        # Research enrichment (if available)
        ai_hook   = company.get("ai_hook","")
        highlight = company.get("recent_highlight","")
        tech      = company.get("tech_stack",[])

        if any([ai_hook, highlight, tech]):
            with st.expander("🔬 Research insights", expanded=False):
                if highlight and highlight != "N/A":
                    st.markdown(f"**Recent:** {highlight}")
                if ai_hook and ai_hook != "N/A":
                    st.markdown(f"**AI angle:** {ai_hook}")
                if tech:
                    st.markdown(f"**Stack:** {', '.join(tech[:6])}")

        if company.get("website"):
            st.markdown(f"[🔗 Website]({company['website']})")

        # Contacts
        if contacts:
            st.markdown("**Contacts:**")
            for ct in contacts:
                v             = "✅ verified" if ct.get("verified") else "⚠️ unverified"
                cc1, cc2, cc3 = st.columns([3,5,2])
                cc1.write(f"**{ct.get('name','')}** · {ct.get('role','')}")
                cc2.code(ct.get("email",""))
                cc3.caption(v)
        else:
            st.warning("⚠️ No contacts — email nahi bhej sakte")
            return

        st.divider()

        # If already sent — show summary only
        if already_sent:
            ep = st.session_state.get("email_previews",{}).get(co_id,{})
            st.markdown('<span class="badge-sent">✅ Email Sent</span>', unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
            if ep.get("subject"):
                st.markdown(f"**Subject:** {ep['subject']}")
            if ep.get("contact_email"):
                st.markdown(f"**Sent to:** `{ep['contact_email']}`")
            c1, c2 = st.columns(2)
            with c1:
                if ep.get("gap"):
                    st.markdown(
                        f'<div class="gap-box"><b>Gap identified</b><br>{ep["gap"][:120]}</div>',
                        unsafe_allow_html=True
                    )
            with c2:
                if ep.get("proposal"):
                    st.markdown(
                        f'<div class="proposal-box"><b>Proposal</b><br>{ep["proposal"][:120]}</div>',
                        unsafe_allow_html=True
                    )
            return

        # Generate email on first open
        _generate_email(co_id, company)
        ep = st.session_state.get("email_previews",{}).get(co_id)
        if not ep:
            return

        if ep.get("error"):
            st.error(f"❌ {ep['error']}")
            return

        if ep.get("decision") == "skip":
            st.markdown('<span style="color:#555;font-size:13px">⏭ Skipped</span>', unsafe_allow_html=True)
            return

        # Email preview
        st.markdown("### 📧 Draft Email")

        ec1, ec2 = st.columns(2)
        ec1.markdown(f"**To:** {ep.get('contact_name','')} ({ep.get('contact_role','')})")
        ec2.markdown(f"**Email:** `{ep.get('contact_email','')}`")

        g1, g2, g3 = st.columns(3)
        with g1:
            if ep.get("gap"):
                st.markdown(
                    f'<div class="gap-box"><b style="font-size:11px;color:#ff6b35">GAP</b><br>{ep["gap"][:100]}</div>',
                    unsafe_allow_html=True
                )
        with g2:
            if ep.get("proposal"):
                st.markdown(
                    f'<div class="proposal-box"><b style="font-size:11px;color:#4ade80">PROPOSAL</b><br>{ep["proposal"][:100]}</div>',
                    unsafe_allow_html=True
                )
        with g3:
            if ep.get("why_fits"):
                st.markdown(
                    f'<div class="hook-box"><b style="font-size:11px;color:#e8ff47">WHY YOU</b><br>{ep["why_fits"][:100]}</div>',
                    unsafe_allow_html=True
                )

        st.markdown("<br>", unsafe_allow_html=True)

        edit_key = f"editing_{co_id}"
        editing  = st.session_state.get(edit_key, False)

        if editing:
            new_subj = st.text_input("Subject", value=ep.get("subject",""),  key=f"subj_{co_id}")
            new_body = st.text_area ("Body",    value=ep.get("body",""), height=220, key=f"body_{co_id}")
            st.session_state["email_previews"][co_id]["subject"] = new_subj
            st.session_state["email_previews"][co_id]["body"]    = new_body
        else:
            st.text_input("Subject", value=ep.get("subject",""), disabled=True, key=f"subj_d_{co_id}")
            st.text_area ("Body",    value=ep.get("body",""),    disabled=True, height=200, key=f"body_d_{co_id}")

        st.markdown("<br>", unsafe_allow_html=True)
        a1, a2, a3 = st.columns([2,1,1])
        with a1:
            if st.button("🚀 Send Email", key=f"send_{co_id}", type="primary", use_container_width=True):
                _send_email(co_id, company, ep)
                st.rerun()
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
st.caption("Startups dhundho — AI-personalized cold emails draft karo — bhejo")

# Load prefs from DB if not in session
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

# ── Find button row ───────────────────────────
col_find, col_info = st.columns([1,3])
with col_find:
    find_clicked = st.button(
        "🔍 Find Startups",
        type                = "primary",
        use_container_width = True
    )
with col_info:
    if st.session_state.get("scraped_companies"):
        total = len(st.session_state["scraped_companies"])
        sent  = len(st.session_state.get("sent_ids",set()))
        st.markdown(
            f'<p style="color:#888;font-size:13px;padding-top:10px">'
            f'{total} companies loaded · {sent} sent this session</p>',
            unsafe_allow_html=True
        )

if find_clicked:
    st.session_state["scraped_companies"] = []
    st.session_state["email_previews"]    = {}
    st.session_state["sent_ids"]          = set()
    st.session_state["is_scraping"]       = True
    st.session_state["scraping_done"]     = False
    st.rerun()

# ── Streaming scrape ──────────────────────────
if st.session_state.get("is_scraping"):
    from backend.agents.scraper_agent import (
        stream_yc_companies,
        stream_hn_hiring,
        stream_betalist,
    )

    status_ph  = st.empty()
    cards_area = st.container()
    counts     = {"yc": 0, "hn": 0, "bl": 0}

    # ── YC ──
    status_ph.info("🟠 YC Companies...")
    try:
        for co in stream_yc_companies(prefs):
            co_id = len(st.session_state["scraped_companies"])
            st.session_state["scraped_companies"].append(co)
            counts["yc"] += 1
            status_ph.info(f"🟠 YC: {counts['yc']}...")
            with cards_area:
                _render_company_card(co, co_id)
    except Exception as e:
        logger.error(f"YC stream error: {e}")
        status_ph.warning(f"⚠️ YC error: {e}")

    # ── HN ──
    status_ph.info(f"🟤 HN Hiring... ({counts['yc']} YC done)")
    try:
        for co in stream_hn_hiring(prefs):
            co_id = len(st.session_state["scraped_companies"])
            st.session_state["scraped_companies"].append(co)
            counts["hn"] += 1
            status_ph.info(f"🟤 HN: {counts['hn']}...")
            with cards_area:
                _render_company_card(co, co_id)
    except Exception as e:
        logger.error(f"HN stream error: {e}")
        status_ph.warning(f"⚠️ HN error: {e}")

    # ── Betalist ──
    status_ph.info(f"🟣 Betalist... ({counts['yc']+counts['hn']} done)")
    try:
        for co in stream_betalist(prefs):
            co_id = len(st.session_state["scraped_companies"])
            st.session_state["scraped_companies"].append(co)
            counts["bl"] += 1
            status_ph.info(f"🟣 BL: {counts['bl']}...")
            with cards_area:
                _render_company_card(co, co_id)
    except Exception as e:
        logger.error(f"Betalist stream error: {e}")
        status_ph.warning(f"⚠️ Betalist error: {e}")

    total = sum(counts.values())
    status_ph.success(
        f"✅ Done — {total} startups "
        f"(YC: {counts['yc']}, HN: {counts['hn']}, BL: {counts['bl']})"
    )
    st.session_state["is_scraping"]   = False
    st.session_state["scraping_done"] = True
    st.rerun()

# ── Saved results ─────────────────────────────
else:
    companies = st.session_state.get("scraped_companies", [])

    if not companies:
        st.markdown("---")
        st.markdown("**💡 From global feed** — ya 'Find Startups' dabao fresh scrape ke liye")

        feed_path = "data/company_feed.json"
        if os.path.exists(feed_path):
            try:
                with open(feed_path) as f:
                    feed = json.load(f)
                feed_cos = feed.get("companies",[])[:5]
                for i, co in enumerate(feed_cos):
                    _render_company_card(co, 9000+i)
            except Exception:
                pass

        if not os.path.exists(feed_path):
            st.info("'Find Startups' dabao")
        st.stop()

    # ── Filters ──────────────────────────────
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        src_f = st.selectbox(
            "Source",
            ["all"] + list({c.get("source","?") for c in companies}),
            key="out_src"
        )
    with f2:
        ct_f = st.checkbox("Has Contacts", key="out_ct")
    with f3:
        vr_f = st.checkbox("Verified Email", key="out_vr")
    with f4:
        ai_f = st.checkbox("AI related", key="out_ai")

    filtered = companies
    if src_f != "all":
        filtered = [c for c in filtered if c.get("source") == src_f]
    if ct_f:
        filtered = [c for c in filtered if c.get("contacts")]
    if vr_f:
        filtered = [c for c in filtered if any(ct.get("verified") for ct in c.get("contacts",[]))]
    if ai_f:
        filtered = [c for c in filtered if c.get("ai_related")]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total",         len(companies))
    m2.metric("Filtered",      len(filtered))
    m3.metric("With Contacts", sum(1 for c in filtered if c.get("contacts")))
    m4.metric("✅ Sent",        len(st.session_state.get("sent_ids",set())))

    if not filtered:
        st.info("Filter change karo — koi results nahi")
        st.stop()

    st.markdown("<br>", unsafe_allow_html=True)

    filtered_ids = {id(c) for c in filtered}
    for co_id, company in enumerate(companies):
        if id(company) in filtered_ids:
            _render_company_card(company, co_id)