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
    --bg: #faf9f5;
    --surface: #ffffff;
    --surface-2: #f2f1e9;
    --border: #e2e0d5;
    --accent: #588112;
    --accent-bright: #84cc16;
    --text: #26251f;
    --muted: #7c7a6d;
    --success: #16a34a;
    --warning: #d97706;
    --danger: #dc2626;
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

h1, h2, h3 { font-family: 'Space Mono', monospace !important; letter-spacing: -.03em !important; color: var(--text) !important; }

.stButton>button {
    background: var(--accent-bright) !important;
    color: #26251f !important;
    border: none !important;
    border-radius: 4px !important;
    font-family: 'Space Mono', monospace !important;
    font-weight: 700 !important;
    font-size: 13px !important;
    padding: 10px 20px !important;
    transition: all .15s !important;
}
.stButton>button:hover { background: #a3e635 !important; transform: translateY(-1px) !important; }
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
    box-shadow: 0 0 0 2px rgba(88, 129, 18, .15) !important;
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
    background: rgba(88, 129, 18, .06);
    border-left: 2px solid rgba(88, 129, 18, .3);
    padding: 8px 12px;
    border-radius: 0 4px 4px 0;
    font-size: 12px;
    color: var(--text);
    margin: 4px 0 6px 0;
    line-height: 1.5;
}
.gap-box {
    background: rgba(234, 88, 12, .06);
    border-left: 3px solid #ea580c;
    padding: 10px 14px;
    border-radius: 0 6px 6px 0;
    font-size: 13px;
}
.proposal-box {
    background: rgba(22, 163, 74, .06);
    border-left: 3px solid var(--success);
    padding: 10px 14px;
    border-radius: 0 6px 6px 0;
    font-size: 13px;
}
.hook-box {
    background: rgba(88, 129, 18, .06);
    border: 1px solid rgba(88, 129, 18, .25);
    border-radius: 6px;
    padding: 10px 14px;
}
.research-box { background: var(--surface-2); border: 1px solid var(--border); border-radius: 6px; padding: 12px 16px; margin: 8px 0; font-size: 13px; }

.step-header { font-family: 'Space Mono', monospace; font-size: 11px; text-transform: uppercase; letter-spacing: 0.15em; color: var(--muted); margin-bottom: 8px; }
.filled-badge {
    background: rgba(22, 163, 74, 0.1);
    color: var(--success);
    border: 1px solid rgba(22, 163, 74, 0.3);
    border-radius: 3px;
    padding: 2px 8px;
    font-size: 11px;
    font-family: 'Space Mono', monospace;
}

.status-pill { display: inline-block; border-radius: 3px; padding: 2px 8px; font-size: 11px; font-family: 'Space Mono', monospace; }
.status-replied { background: rgba(22, 163, 74, .12); color: var(--success); border: 1px solid rgba(22, 163, 74, .3); }
.status-followup { background: rgba(217, 119, 6, .12); color: var(--warning); border: 1px solid rgba(217, 119, 6, .3); }
.status-awaiting { background: rgba(0, 0, 0, .04); color: var(--muted); border: 1px solid var(--border); }

.status-banner-on {
    background: rgba(22, 163, 74, .08);
    border: 1px solid rgba(22, 163, 74, .25);
    border-radius: 6px;
    padding: 8px 14px;
    font-size: 12px;
    font-family: 'Space Mono', monospace;
    color: var(--success);
    margin-bottom: 12px;
}
.status-banner-off {
    background: rgba(220, 38, 38, .08);
    border: 1px solid rgba(220, 38, 38, .25);
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
