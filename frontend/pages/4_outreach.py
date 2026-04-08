# frontend/pages/4_outreach.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
import json
import streamlit as st
from loguru import logger

if "user_id" not in st.session_state:
    st.warning("Pehle login karo"); st.stop()

user_id = st.session_state["user_id"]

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
[data-testid="stSidebarNav"]{display:none!important}
.gap-box{background:rgba(255,107,53,.05);border-left:3px solid #ff6b35;padding:10px 14px;border-radius:0 6px 6px 0;font-size:13px}
.proposal-box{background:rgba(74,222,128,.05);border-left:3px solid #4ade80;padding:10px 14px;border-radius:0 6px 6px 0;font-size:13px}
.hook-box{background:rgba(232,255,71,.04);border:1px solid rgba(232,255,71,.15);border-radius:6px;padding:10px 14px}
.research-box{background:#1a1a1a;border:1px solid #2a2a2a;border-radius:6px;padding:12px 16px;margin:8px 0;font-size:13px}
</style>
""", unsafe_allow_html=True)


def _check_scheduler_process():
    try:
        import psutil
        for p in psutil.process_iter(["cmdline"]):
            if "run_scheduler.py" in " ".join(p.info["cmdline"] or []):
                return True
    except Exception: pass
    return False

with st.sidebar:
    st.markdown("### ⚡ OutreachAI")
    st.caption(st.session_state.get("email", ""))
    st.divider()
    st.page_link("app.py",                label="⚡  Home",          use_container_width=True)
    st.page_link("pages/2_onboarding.py", label="👤  Profile Setup", use_container_width=True)
    st.page_link("pages/4_outreach.py",   label="🚀  Cold Outreach", use_container_width=True)
    st.page_link("pages/5_tracker.py",    label="📊  Tracker",       use_container_width=True)
    try:
        from backend.pipeline.reply_handler import NotificationManager
        _p = NotificationManager.get_pending_notifications(user_id)
        _rc = len([n for n in _p if n["type"] == "reply_received"])
        _lbl = f"📬  Replies & Drafts  🔴 {_rc}" if _rc else "📬  Replies & Drafts"
    except Exception:
        _lbl = "📬  Replies & Drafts"
    st.page_link("pages/3_replies.py", label=_lbl, use_container_width=True)
    st.divider()
    sc = len(st.session_state.get("sent_ids", set()))
    if sc: st.success(f"✅ {sc} sent this session")
    st.divider()
    if _check_scheduler_process():
        st.markdown('<p style="color:#4ade80;font-size:11px;font-family:\'Space Mono\',monospace;margin:0">🟢 SCHEDULER ON</p>', unsafe_allow_html=True)
        st.markdown('<p style="color:#555;font-size:10px;margin:2px 0">· Auto follow-ups active</p>', unsafe_allow_html=True)
    else:
        st.markdown('<p style="color:#f87171;font-size:11px;font-family:\'Space Mono\',monospace;margin:0">🔴 SCHEDULER OFF</p>', unsafe_allow_html=True)
        st.markdown('<p style="color:#555;font-size:10px;margin:2px 0">· python run_scheduler.py chalao</p>', unsafe_allow_html=True)


SOURCE_ICONS = {"yc_api":"🟠 YC","betalist":"🟣 BL","product_hunt":"🔴 PH",
                "indie_hackers":"🟢 IH","github_trending":"⚫ GH","hn_hiring":"🟡 HN"}


# ═════════════════════════════════════════
# HELPERS
# ═════════════════════════════════════════

def _make_key(co_id, company):
    """Generate a stable unique key for a company to avoid duplicate widget IDs."""
    name_hash = abs(hash(company.get("name", "") + str(co_id))) % 10_000_000
    return f"{co_id}_{name_hash}"

def _mark_sent(co_id):
    if "sent_ids" not in st.session_state:
        st.session_state["sent_ids"] = set()
    st.session_state["sent_ids"].add(co_id)
    if co_id in st.session_state.get("email_previews", {}):
        st.session_state["email_previews"][co_id]["decision"] = "sent"
    try:
        from backend.utils.feed_to_db import mark_company_contacted
        mark_company_contacted(user_id, co_id)
    except Exception as e:
        logger.warning(f"mark_company_contacted failed: {e}")

def _is_sent(co_id):
    if co_id in st.session_state.get("sent_ids", set()): return True
    return st.session_state.get("email_previews", {}).get(co_id, {}).get("decision") == "sent"

def _db_save(company: dict) -> int:
    try:
        from backend.utils.feed_to_db import save_feed_company_to_db
        _, co_id = save_feed_company_to_db(user_id, company)
        return co_id if (co_id and co_id > 0) else id(company)
    except Exception as e:
        logger.warning(f"_db_save failed: {e}")
        return id(company)

def _send_email(co_id, company, ep):
    from backend.agents.email_sender import send_email, get_gmail_creds
    from backend.database import SessionLocal
    from backend.models.user import UserProfile
    creds = get_gmail_creds(user_id)
    if "error" in creds:
        st.error(f"❌ Gmail credentials missing: {creds['error']}"); return
    resume_path = ""
    db = SessionLocal()
    try:
        prof = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        if prof and prof.resume_path and os.path.exists(prof.resume_path):
            resume_path = prof.resume_path
    finally: db.close()
    to_email = ep.get("contact_email","").strip()
    subject  = ep.get("subject","").strip()
    body     = ep.get("body","").strip()
    if not to_email: st.error("❌ Contact email missing"); return
    if not subject:  st.error("❌ Subject empty"); return
    if not body:     st.error("❌ Body empty"); return
    with st.spinner(f"📤 Bhej rahe hain → {to_email}..."):
        result = send_email(
            user_id=user_id, to_email=to_email, subject=subject, body=body,
            resume_path=resume_path, company=company["name"],
            contact=ep.get("contact_name",""), contact_role=ep.get("contact_role",""),
            gap=ep.get("gap",""), proposal=ep.get("proposal",""),
            website=company.get("website",""),
        )
    if result.get("success"):
        _mark_sent(co_id)
        st.success(f"✅ Sent → `{to_email}` at {result.get('sent_at','')[:19]}")
        st.toast(f"✅ Sent to {ep.get('contact_name','')} @ {company['name']}!", icon="🚀")
    else:
        err = result.get("error","Unknown")
        st.error(f"❌ Send failed: {err}")
        if "auth" in err.lower() or "password" in err.lower():
            st.warning("🔧 Fix: App Password banao → Profile Setup mein daalo")

def _generate_email(co_id, company):
    from backend.agents.email_generator import generate_cold_email
    if "email_previews" not in st.session_state:
        st.session_state["email_previews"] = {}
    if co_id in st.session_state["email_previews"]: return
    contacts = company.get("contacts", [])
    contact  = next((c for c in contacts if c.get("email")), None)
    if not contact:
        st.session_state["email_previews"][co_id] = {"error": "No contact email found"}; return
    with st.spinner(f"✍️ Drafting for {company['name']}..."):
        try:
            result = generate_cold_email(
                user_id=user_id, company=company["name"],
                description=company.get("company_summary") or company.get("description",""),
                one_liner=company.get("one_liner",""), contact=contact,
                ai_hook=company.get("ai_hook",""),
                recent_highlight=company.get("recent_highlight",""),
                tech_stack=company.get("tech_stack",[]),
            )
            if result.get("error"):
                st.session_state["email_previews"][co_id] = {"error": result["error"]}; return
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


# ═════════════════════════════════════════
# COMPANY CARD
# ═════════════════════════════════════════

def _render_company_card(company, co_id, expanded=False, idx=0):
    # FIX: Use render-time idx as the widget key — guaranteed unique across all cards
    uid = f"card_{idx}"

    contacts     = company.get("contacts", [])
    already_sent = _is_sent(co_id)
    src       = SOURCE_ICONS.get(company.get("source",""), "⚪")
    ct_str    = f"✉️ {len(contacts)}" if contacts else "⚠️ no contacts"
    sfx       = " · ✅ Sent" if already_sent else ""
    stars_str = f" · ⭐ {company['github_stars']}" if company.get("github_stars") else ""
    header    = f"{src}  **{company['name']}** · {company.get('funding','?')} · {ct_str}{stars_str}{sfx}"

    with st.expander(header, expanded=expanded):
        r1, r2 = st.columns(2)
        r1.metric("Team",     company.get("team_size","?"))
        r2.metric("Location", (company.get("location") or "?")[:20])
        if company.get("one_liner"): st.info(company["one_liner"])
        if company.get("website"):   st.markdown(f"[🔗 {company['website']}]({company['website']})")
        if company.get("github_url"):st.markdown(f"[🐙 GitHub]({company['github_url']})")

        # Research — inline div, no nested expander
        if any([company.get("ai_hook") and company["ai_hook"] != "N/A",
                company.get("recent_highlight") and company["recent_highlight"] != "N/A",
                company.get("tech_stack")]):
            html = ["<div class='research-box'><strong>🔬 Research Insights</strong><br><br>"]
            if company.get("recent_highlight") and company["recent_highlight"] != "N/A":
                html.append(f"<small style='color:#666;text-transform:uppercase'>Recent</small><br>{company['recent_highlight']}<br><br>")
            if company.get("ai_hook") and company["ai_hook"] != "N/A":
                html.append(f"<small style='color:#666;text-transform:uppercase'>AI Angle</small><br>{company['ai_hook']}<br><br>")
            if company.get("tech_stack"):
                html.append(f"<small style='color:#666;text-transform:uppercase'>Stack</small><br>{', '.join(company['tech_stack'][:6])}")
            html.append("</div>")
            st.markdown("".join(html), unsafe_allow_html=True)

        if contacts:
            st.write("**Contacts:**")
            for ct in contacts:
                v = "✅" if ct.get("verified") else "⚠️"
                c1, c2, c3 = st.columns([3,5,1])
                c1.write(f"**{ct.get('name','')}** · {ct.get('role','')}")
                c2.code(ct.get("email","") or "(no email)")
                c3.write(v)
                if ct.get("twitter"): st.caption(f"🐦 [{ct['twitter']}]({ct['twitter']})")
                if ct.get("github"):  st.caption(f"🐙 [{ct['github']}]({ct['github']})")
        else:
            st.warning("No contacts — email nahi bhej sakte"); return

        st.divider()

        if already_sent:
            ep = st.session_state.get("email_previews",{}).get(co_id,{})
            st.success("✅ Email Sent — Tracker mein dekho")
            if ep.get("subject"):       st.write(f"**Subject:** {ep['subject']}")
            if ep.get("contact_email"): st.write(f"**To:** `{ep['contact_email']}`")
            c1,c2 = st.columns(2)
            with c1:
                if ep.get("gap"):      st.markdown(f'<div class="gap-box"><b>Gap</b><br>{ep["gap"][:120]}</div>', unsafe_allow_html=True)
            with c2:
                if ep.get("proposal"): st.markdown(f'<div class="proposal-box"><b>Proposal</b><br>{ep["proposal"][:120]}</div>', unsafe_allow_html=True)
            return

        _generate_email(co_id, company)
        ep = st.session_state.get("email_previews",{}).get(co_id)
        if not ep: return
        if ep.get("error"):              st.error(f"❌ {ep['error']}"); return
        if ep.get("decision") == "skip": st.caption("⏭ Skipped"); return

        st.markdown("### 📧 Draft Email")
        ec1,ec2 = st.columns(2)
        ec1.write(f"**To:** {ep.get('contact_name','')} ({ep.get('contact_role','')})")
        ec2.write(f"**Email:** `{ep.get('contact_email','')}`")
        g1,g2,g3 = st.columns(3)
        with g1:
            if ep.get("gap"):      st.markdown(f'<div class="gap-box"><b style="font-size:11px;color:#ff6b35">GAP</b><br>{ep["gap"][:100]}</div>', unsafe_allow_html=True)
        with g2:
            if ep.get("proposal"): st.markdown(f'<div class="proposal-box"><b style="font-size:11px;color:#4ade80">PROPOSAL</b><br>{ep["proposal"][:100]}</div>', unsafe_allow_html=True)
        with g3:
            if ep.get("why_fits"): st.markdown(f'<div class="hook-box"><b style="font-size:11px;color:#e8ff47">WHY YOU</b><br>{ep["why_fits"][:100]}</div>', unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        edit_key = f"editing_{uid}"
        editing  = st.session_state.get(edit_key, False)
        if editing:
            ns = st.text_input("Subject", value=ep.get("subject",""), key=f"subj_{uid}")
            nb = st.text_area("Body",     value=ep.get("body",""),    height=220, key=f"body_{uid}")
            st.session_state["email_previews"][co_id]["subject"] = ns
            st.session_state["email_previews"][co_id]["body"]    = nb
        else:
            st.text_input("Subject", value=ep.get("subject",""), disabled=True, key=f"subj_d_{uid}")
            st.text_area("Body",     value=ep.get("body",""),    disabled=True, height=200, key=f"body_d_{uid}")
        st.markdown("<br>", unsafe_allow_html=True)

        a1,a2,a3 = st.columns([2,1,1])
        with a1:
            if st.button("🚀 Send Email", key=f"send_{uid}", type="primary", use_container_width=True):
                _send_email(co_id, company, ep)
        with a2:
            lbl = "💾 Save" if editing else "✏️ Edit"
            if st.button(lbl, key=f"edit_{uid}", use_container_width=True):
                st.session_state[edit_key] = not editing; st.rerun()
        with a3:
            if st.button("❌ Skip", key=f"skip_{uid}", use_container_width=True):
                st.session_state["email_previews"][co_id]["decision"] = "skip"; st.rerun()


# ═════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════

st.markdown("# 🚀 Cold Outreach")
st.caption("DB se fresh companies load hongi — scrape karo to naye add honge, dobara nahi aayenge")
st.markdown("**Sources:** 🟠 YC &nbsp;·&nbsp; 🟣 Betalist &nbsp;·&nbsp; 🔴 PH &nbsp;·&nbsp; 🟢 IH &nbsp;·&nbsp; ⚫ GH &nbsp;·&nbsp; 🟡 HN", unsafe_allow_html=True)

from backend.agents.email_sender import get_gmail_creds
_creds = get_gmail_creds(user_id)
if "error" in _creds:
    st.error(f"⚠️ Gmail setup incomplete: {_creds['error']}")
    if st.button("👤 Go to Profile Setup", type="primary"): st.switch_page("pages/2_onboarding.py")
    st.stop()
else:
    st.success(f"✅ Gmail ready: `{_creds['email']}`")

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
    except Exception: pass
    finally: db.close()

prefs = st.session_state.get("prefs", {"preferred_type":"job","domains":["ai_ml"],"target_roles":["AI Engineer"],"location":"remote"})

# ── Home se feed company aaya? ──
feed_company = st.session_state.get("feed_outreach_company")
feed_co_id   = st.session_state.get("feed_outreach_co_id")
if feed_company:
    co_id = feed_co_id if (feed_co_id and feed_co_id > 0) else _db_save(feed_company)
    if _is_sent(co_id):
        st.session_state.pop("feed_outreach_company", None)
        st.session_state.pop("feed_outreach_co_id",   None)
        st.success("✅ Email sent! Tracker mein dekho.")
    else:
        st.info(f"📬 **{feed_company.get('name')}** — email draft ho raha hai...")
        st.divider()
        _render_company_card(feed_company, co_id, expanded=True, idx=0)
        st.divider()

# ── Find More button ──
col_find, col_info = st.columns([1,3])
with col_find:
    find_clicked = st.button("🔍 Find More Startups", type="primary", use_container_width=True)
with col_info:
    from backend.utils.feed_to_db import load_feed_companies as _lfc
    _db_total = len(_lfc(user_id, limit=200))
    st.caption(f"{_db_total} companies in DB waiting for outreach  ·  {len(st.session_state.get('sent_ids', set()))} sent this session")

if find_clicked:
    st.session_state["is_scraping"]   = True
    st.session_state["scraping_done"] = False
    st.rerun()


# ═════════════════════════════════════════
# SCRAPE — save each to DB immediately
# ═════════════════════════════════════════

if st.session_state.get("is_scraping"):
    from backend.agents.scraper_agent import (
        stream_yc_companies, stream_betalist,
        _run_product_hunt, _run_indie_hackers,
        _run_github_trending, _run_hn_hiring,
    )
    from backend.utils.feed_to_db import save_feed_company_to_db, sync_feed_json

    status_ph  = st.empty()
    cards_area = st.container()
    counts     = {"yc":0,"bl":0,"ph":0,"ih":0,"gh":0,"hn":0}
    new_cards  = []  # track newly added this run

    def _process(co, src_key):
        co["source"] = co.get("source") or src_key
        obj, co_id = save_feed_company_to_db(user_id, co)
        is_new = (obj is not None and not obj.contacted_at)
        if is_new:
            counts[src_key] += 1
            new_cards.append((co, co_id))
            with cards_area:
                _render_company_card(co, co_id, idx=counts[src_key])
        # If duplicate, silently skip — don't show card

    status_ph.info("🟠 YC scraping...")
    try:
        for co in stream_yc_companies(prefs):
            _process(co, "yc"); status_ph.info(f"🟠 YC: {counts['yc']} new...")
    except Exception as e: status_ph.warning(f"⚠️ YC: {e}")

    status_ph.info("🟣 Betalist scraping...")
    try:
        for co in stream_betalist(prefs):
            _process(co, "bl"); status_ph.info(f"🟣 Betalist: {counts['bl']} new...")
    except Exception as e: status_ph.warning(f"⚠️ Betalist: {e}")

    status_ph.info("🔴 Product Hunt scraping...")
    try:
        for co in _run_product_hunt(prefs): _process(co, "ph")
        status_ph.info(f"🔴 PH: {counts['ph']} new")
    except Exception as e: status_ph.warning(f"⚠️ PH: {e}")

    status_ph.info("🟢 Indie Hackers scraping...")
    try:
        for co in _run_indie_hackers(prefs): _process(co, "ih")
        status_ph.info(f"🟢 IH: {counts['ih']} new")
    except Exception as e: status_ph.warning(f"⚠️ IH: {e}")

    status_ph.info("⚫ GitHub Trending scraping...")
    try:
        for co in _run_github_trending(prefs): _process(co, "gh")
        status_ph.info(f"⚫ GH: {counts['gh']} new")
    except Exception as e: status_ph.warning(f"⚠️ GH: {e}")

    status_ph.info("🟡 HN Hiring scraping...")
    try:
        for co in _run_hn_hiring(prefs): _process(co, "hn")
        status_ph.info(f"🟡 HN: {counts['hn']} new")
    except Exception as e: status_ph.warning(f"⚠️ HN: {e}")

    total_new = sum(counts.values())

    # Sync DB → company_feed.json (home page reads this)
    try: sync_feed_json(user_id)
    except Exception as e: logger.warning(f"sync_feed_json: {e}")

    status_ph.success(
        f"✅ {total_new} new companies added to DB  "
        f"(🟠{counts['yc']} 🟣{counts['bl']} 🔴{counts['ph']} 🟢{counts['ih']} ⚫{counts['gh']} 🟡{counts['hn']})"
        + (f"  · Duplicates automatically skipped" if total_new == 0 else "")
    )
    st.session_state["is_scraping"]   = False
    st.session_state["scraping_done"] = True
    st.rerun()


# ═════════════════════════════════════════
# RESULTS — always from DB
# ═════════════════════════════════════════

else:
    from backend.utils.feed_to_db import load_feed_companies

    companies = load_feed_companies(user_id, limit=60)

    if not companies:
        st.divider()
        st.info("🎉 Saari companies outreach ho chuki hain ya abhi koi nahi hai. **'Find More Startups'** dabao.")
    else:
        all_sources = sorted({c.get("source","?") for c in companies})
        f1,f2,f3,f4,f5 = st.columns(5)
        with f1: src_f = st.selectbox("Source", ["all"] + all_sources, key="out_src")
        with f2: ct_f  = st.checkbox("Has Contacts",   key="out_ct")
        with f3: vr_f  = st.checkbox("Verified Email", key="out_vr")
        with f4: ai_f  = st.checkbox("AI related",     key="out_ai")
        with f5: gh_f  = st.checkbox("Has GitHub ⭐",   key="out_gh")

        filtered = companies
        if src_f != "all": filtered = [c for c in filtered if c.get("source") == src_f]
        if ct_f:           filtered = [c for c in filtered if c.get("contacts")]
        if vr_f:           filtered = [c for c in filtered if any(ct.get("verified") for ct in c.get("contacts",[]))]
        if ai_f:           filtered = [c for c in filtered if c.get("ai_related")]
        if gh_f:           filtered = [c for c in filtered if c.get("github_stars")]

        m1,m2,m3,m4,m5 = st.columns(5)
        m1.metric("In DB",         len(companies))
        m2.metric("Filtered",      len(filtered))
        m3.metric("With Contacts", sum(1 for c in filtered if c.get("contacts")))
        m4.metric("✅ Sent",        len(st.session_state.get("sent_ids",set())))
        m5.metric("Sources",       len(all_sources))

        with st.expander("📊 Source Breakdown", expanded=False):
            sc = {}
            for c in companies: sc[c.get("source","?")] = sc.get(c.get("source","?"),0)+1
            cols = st.columns(len(sc) or 1)
            for i,(s,cnt) in enumerate(sorted(sc.items())):
                cols[i].metric(SOURCE_ICONS.get(s,"⚪"), cnt)

        if not filtered:
            st.info("Filter change karo — koi results nahi"); st.stop()

        st.markdown("<br>", unsafe_allow_html=True)
        # FIX: Use enumerate so each card gets a guaranteed-unique fallback key
        for i, company in enumerate(filtered):
            co_id = company.get("id") or abs(hash(company.get("name", "") + str(i))) % 10_000_000
            _render_company_card(company, co_id, idx=i)