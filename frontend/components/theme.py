# frontend/components/theme.py
"""
Single shared stylesheet for the whole app.

Every page used to carry its own near-identical <style> block, and small
drifts between copies (different colors, missing rules) made the app feel
inconsistent from page to page. apply_theme() is the one place that owns
the look, so every page renders identically.
"""

import streamlit as st

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap');

:root {
    --bg: #0d0d0d;
    --surface: #161616;
    --border: #2a2a2a;
    --accent: #e8ff47;
    --text: #f0f0f0;
    --muted: #666;
    --success: #4ade80;
    --warning: #fbbf24;
    --danger: #f87171;
}

html, body, [data-testid="stAppViewContainer"] {
    background: var(--bg) !important;
    color: var(--text) !important;
    font-family: 'DM Sans', sans-serif !important;
}
[data-testid="stSidebar"] {
    background: var(--surface) !important;
    border-right: 1px solid var(--border) !important;
}
[data-testid="stSidebarNav"] { display: none !important; }

h1, h2, h3 { font-family: 'Space Mono', monospace !important; letter-spacing: -.03em !important; }

.stButton>button {
    background: var(--accent) !important;
    color: #000 !important;
    border: none !important;
    border-radius: 4px !important;
    font-family: 'Space Mono', monospace !important;
    font-weight: 700 !important;
    font-size: 13px !important;
    padding: 10px 20px !important;
    transition: all .15s !important;
}
.stButton>button:hover { background: #fff !important; transform: translateY(-1px) !important; }
.stButton>button[kind="secondary"] {
    background: transparent !important;
    color: var(--text) !important;
    border: 1px solid var(--border) !important;
}
.stButton>button[kind="secondary"]:hover { border-color: var(--accent) !important; color: var(--accent) !important; }

.stTextInput>div>div>input, .stTextArea>div>div>textarea, .stSelectbox>div>div {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    color: var(--text) !important;
    border-radius: 4px !important;
}
.stTextInput>div>div>input:focus, .stTextArea>div>div>textarea:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 2px rgba(232, 255, 71, .1) !important;
}

.stTabs [data-baseweb="tab-list"] { background: transparent !important; border-bottom: 1px solid var(--border) !important; gap: 0 !important; }
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    color: var(--muted) !important;
    font-family: 'Space Mono', monospace !important;
    font-size: 12px !important;
    border-bottom: 2px solid transparent !important;
    padding: 10px 20px !important;
}
.stTabs [aria-selected="true"] { color: var(--accent) !important; border-bottom-color: var(--accent) !important; }

.stMetric {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: 6px !important;
    padding: 16px !important;
}
.stMetric label { color: var(--muted) !important; font-size: 11px !important; text-transform: uppercase; letter-spacing: .1em; }
.stMetric [data-testid="metric-container"]>div:nth-child(2) {
    color: var(--accent) !important;
    font-family: 'Space Mono', monospace !important;
    font-size: 28px !important;
}

.stExpander { border: 1px solid var(--border) !important; border-radius: 6px !important; background: var(--surface) !important; }

.desc-box {
    background: rgba(232, 255, 71, .04);
    border-left: 2px solid rgba(232, 255, 71, .25);
    padding: 8px 12px;
    border-radius: 0 4px 4px 0;
    font-size: 12px;
    color: #ccc;
    margin: 4px 0 6px 0;
    line-height: 1.5;
}
.gap-box {
    background: rgba(255, 107, 53, .05);
    border-left: 3px solid #ff6b35;
    padding: 10px 14px;
    border-radius: 0 6px 6px 0;
    font-size: 13px;
}
.proposal-box {
    background: rgba(74, 222, 128, .05);
    border-left: 3px solid var(--success);
    padding: 10px 14px;
    border-radius: 0 6px 6px 0;
    font-size: 13px;
}
.hook-box {
    background: rgba(232, 255, 71, .04);
    border: 1px solid rgba(232, 255, 71, .15);
    border-radius: 6px;
    padding: 10px 14px;
}
.research-box { background: #1a1a1a; border: 1px solid var(--border); border-radius: 6px; padding: 12px 16px; margin: 8px 0; font-size: 13px; }

.step-header { font-family: 'Space Mono', monospace; font-size: 11px; text-transform: uppercase; letter-spacing: 0.15em; color: var(--muted); margin-bottom: 8px; }
.filled-badge {
    background: rgba(74, 222, 128, 0.1);
    color: var(--success);
    border: 1px solid rgba(74, 222, 128, 0.3);
    border-radius: 3px;
    padding: 2px 8px;
    font-size: 11px;
    font-family: 'Space Mono', monospace;
}

.status-pill { display: inline-block; border-radius: 3px; padding: 2px 8px; font-size: 11px; font-family: 'Space Mono', monospace; }
.status-replied { background: rgba(74, 222, 128, .12); color: var(--success); border: 1px solid rgba(74, 222, 128, .3); }
.status-followup { background: rgba(251, 191, 36, .12); color: var(--warning); border: 1px solid rgba(251, 191, 36, .3); }
.status-awaiting { background: rgba(255, 255, 255, .06); color: #888; border: 1px solid var(--border); }

.status-banner-on {
    background: rgba(74, 222, 128, .07);
    border: 1px solid rgba(74, 222, 128, .2);
    border-radius: 6px;
    padding: 8px 14px;
    font-size: 12px;
    font-family: 'Space Mono', monospace;
    color: var(--success);
    margin-bottom: 12px;
}
.status-banner-off {
    background: rgba(248, 113, 113, .07);
    border: 1px solid rgba(248, 113, 113, .2);
    border-radius: 6px;
    padding: 8px 14px;
    font-size: 12px;
    font-family: 'Space Mono', monospace;
    color: var(--danger);
    margin-bottom: 12px;
}
</style>
"""


def apply_theme():
    """Inject the shared stylesheet. Call once near the top of every page."""
    st.markdown(_CSS, unsafe_allow_html=True)
