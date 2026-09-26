# frontend/pages/4_outreach.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import json
import streamlit as st
from loguru import logger

if "user_id" not in st.session_state:
    st.warning("Please log in first."); st.stop()

user_id = st.session_state["user_id"]

from components.theme import apply_theme
from components.formatting import short_url
apply_theme()


from components.sidebar import render_sidebar
render_sidebar()


SOURCE_ICONS = {"yc_api":"🟠 YC","betalist":"🟣 BL","product_hunt":"🔴 PH",
                "indie_hackers":"🟢 IH","github_trending":"⚫ GH","hn_hiring":"🟡 HN"}


# ═════════════════════════════════════════
# HELPERS
# ═════════════════════════════════════════

from components.email_actions import (
    is_sent as _is_sent,
    mark_sent as _mark_sent_base,
    render_email_panel,
)

def _mark_sent(co_id):
    _mark_sent_base(user_id, co_id)

def _db_save(company: dict) -> int:
    try:
        from backend.utils.feed_to_db import save_feed_company_to_db
        _, co_id = save_feed_company_to_db(user_id, company)
        return co_id if (co_id and co_id > 0) else id(company)
    except Exception as e:
        logger.warning(f"_db_save failed: {e}")
        return id(company)


# ═════════════════════════════════════════
# COMPANY CARD
# ═════════════════════════════════════════

def _render_company_card(company, co_id, expanded=False, idx=0, auto_draft=False):
    uid = f"card_{co_id}"  # tied to the company, not list position, so state survives reruns/reordering

    contacts     = company.get("contacts", [])
    already_sent = _is_sent(co_id)
    has_draft    = co_id in st.session_state.get("email_previews", {})
    src       = SOURCE_ICONS.get(company.get("source",""), "⚪")
    ct_str    = f"✉️ {len(contacts)}" if contacts else "⚠️ no contacts"
    sfx       = " · ✅ Sent" if already_sent else (" · 📧 Drafted" if has_draft else "")
    stars_str = f" · ⭐ {company['github_stars']}" if company.get("github_stars") else ""
    header    = f"{src}  **{company['name']}** · {company.get('funding','?')} · {ct_str}{stars_str}{sfx}"

    # Once a card has a draft (or is sent), keep it open across reruns — otherwise
    # clicking Edit/Save/Send inside a closed-by-default expander looks like it
    # silently does nothing, because the expander collapses back on every rerun.
    with st.expander(header, expanded=(expanded or has_draft or already_sent)):
        r1, r2 = st.columns(2)
        r1.metric("Team",     company.get("team_size","?"))
        r2.metric("Location", (company.get("location") or "?")[:20])

        # ── Company Description ──────────────────────────────────────────────
        full_desc = (
            company.get("company_summary")
            or company.get("one_liner")
            or company.get("description")
            or ""
        ).strip()

        one_liner = (company.get("one_liner") or "").strip()

        if one_liner:
            st.info(one_liner)

        if full_desc and full_desc != one_liner and len(full_desc) > len(one_liner) + 10:
            st.markdown(
                f'<div class="desc-box">📋 {full_desc[:300]}{"…" if len(full_desc) > 300 else ""}</div>',
                unsafe_allow_html=True
            )

        if company.get("website"):
            st.markdown(f"[🔗 {short_url(company['website'])}]({company['website']})")
        if company.get("github_url"): st.markdown(f"[🐙 GitHub]({company['github_url']})")

        # Research insights
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
            st.warning("No contacts found — cannot send email."); return

        st.divider()

        render_email_panel(user_id, co_id, company, uid=uid, auto_draft=auto_draft)


# ═════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════

st.markdown("# 🚀 Cold Outreach")
st.caption("Find startups, generate personalized emails, and reach out — all in one place.")
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

# ── Company passed from Home feed ──
feed_company = st.session_state.get("feed_outreach_company")
feed_co_id   = st.session_state.get("feed_outreach_co_id")
if feed_company:
    co_id = feed_co_id if (feed_co_id and feed_co_id > 0) else _db_save(feed_company)
    if _is_sent(co_id):
        st.session_state.pop("feed_outreach_company", None)
        st.session_state.pop("feed_outreach_co_id",   None)
        st.success("✅ Email sent! Check the Tracker for details.")
    else:
        st.info(f"📬 **{feed_company.get('name')}** — drafting your email...")
        st.divider()
        _render_company_card(feed_company, co_id, expanded=True, idx=0, auto_draft=True)
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
# SCRAPE
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
    new_cards  = []
    errors     = {}  # src_key -> error message, shown persistently at the end
    # (a per-source failure used to only flash in status_ph for a split second
    # before the next source's status line overwrote it — invisible in practice)

    def _process(co, src_key):
        co["source"] = co.get("source") or src_key
        obj, co_id = save_feed_company_to_db(user_id, co)
        is_new = (obj is not None and not obj.contacted_at)
        if is_new:
            counts[src_key] += 1
            new_cards.append((co, co_id))
            with cards_area:
                _render_company_card(co, co_id, idx=counts[src_key])

    status_ph.info("🟠 Scraping YC...")
    try:
        for co in stream_yc_companies(prefs):
            _process(co, "yc"); status_ph.info(f"🟠 YC: {counts['yc']} new...")
    except Exception as e: errors["yc"] = str(e)

    status_ph.info("🟣 Scraping Betalist...")
    try:
        for co in stream_betalist(prefs):
            _process(co, "bl"); status_ph.info(f"🟣 Betalist: {counts['bl']} new...")
    except Exception as e: errors["bl"] = str(e)

    status_ph.info("🔴 Scraping Product Hunt...")
    try:
        for co in _run_product_hunt(prefs): _process(co, "ph")
        status_ph.info(f"🔴 PH: {counts['ph']} new")
    except Exception as e: errors["ph"] = str(e)

    status_ph.info("🟢 Scraping Indie Hackers...")
    try:
        for co in _run_indie_hackers(prefs): _process(co, "ih")
        status_ph.info(f"🟢 IH: {counts['ih']} new")
    except Exception as e: errors["ih"] = str(e)

    status_ph.info("⚫ Scraping GitHub Trending...")
    try:
        for co in _run_github_trending(prefs): _process(co, "gh")
        status_ph.info(f"⚫ GH: {counts['gh']} new")
    except Exception as e: errors["gh"] = str(e)

    status_ph.info("🟡 Scraping HN Hiring...")
    try:
        for co in _run_hn_hiring(prefs): _process(co, "hn")
        status_ph.info(f"🟡 HN: {counts['hn']} new")
    except Exception as e: errors["hn"] = str(e)

    total_new = sum(counts.values())

    try: sync_feed_json(user_id)
    except Exception as e: logger.warning(f"sync_feed_json: {e}")

    status_ph.success(
        f"✅ {total_new} new companies added to DB  "
        f"(🟠{counts['yc']} 🟣{counts['bl']} 🔴{counts['ph']} 🟢{counts['ih']} ⚫{counts['gh']} 🟡{counts['hn']})"
        + ("  · Duplicates automatically skipped" if total_new == 0 else "")
    )
    # st.rerun() below wipes anything rendered on this run — stash errors in
    # session_state so they can be shown persistently on the results page.
    st.session_state["scrape_errors"] = errors

    st.session_state["is_scraping"]   = False
    st.session_state["scraping_done"] = True
    st.rerun()


# ═════════════════════════════════════════
# RESULTS — from DB
# ═════════════════════════════════════════

else:
    from backend.utils.feed_to_db import load_feed_companies

    _scrape_errors = st.session_state.pop("scrape_errors", None)
    if _scrape_errors:
        SOURCE_NAMES = {"yc":"YC","bl":"Betalist","ph":"Product Hunt","ih":"Indie Hackers","gh":"GitHub Trending","hn":"HN Hiring"}
        for src_key, msg in _scrape_errors.items():
            st.error(f"⚠️ {SOURCE_NAMES.get(src_key, src_key)} failed to scrape: {msg}")

    companies = load_feed_companies(user_id, limit=60)

    # Don't re-render the company already shown above (from Home's "Start Outreach") —
    # same co_id twice on one page produces duplicate widget keys and crashes.
    _shown_co_id = st.session_state.get("feed_outreach_co_id")
    if _shown_co_id and not _is_sent(_shown_co_id):
        companies = [c for c in companies if c.get("id") != _shown_co_id]

    if not companies:
        st.divider()
        st.info("🎉 All companies have been contacted. Click **'Find More Startups'** to get more.")
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
            st.info("No results match your current filters."); st.stop()

        st.markdown("<br>", unsafe_allow_html=True)
        for i, company in enumerate(filtered):
            co_id = company.get("id") or abs(hash(company.get("name", "") + str(i))) % 10_000_000
            _render_company_card(company, co_id, idx=i)