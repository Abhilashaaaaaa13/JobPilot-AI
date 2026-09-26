# frontend/components/scheduler_control.py
"""
On-screen start/stop for the background scheduler (reply checks, follow-ups,
Sheets sync) — previously this required running `python run_scheduler.py` in
a separate terminal window.

st.cache_resource makes the scheduler a true singleton for the life of the
Streamlit server process — shared across every browser tab/session, and
surviving page reruns, so clicking Start once keeps it running in the
background for as long as the app itself is running.
"""

import streamlit as st
from loguru import logger


@st.cache_resource
def _holder():
    return {"scheduler": None}


def get_scheduler():
    return _holder()["scheduler"]


def is_running() -> bool:
    sched = get_scheduler()
    return sched is not None and sched.running


def start_scheduler():
    holder = _holder()
    if holder["scheduler"] is not None and holder["scheduler"].running:
        return holder["scheduler"]

    from backend.pipeline.scheduler import create_scheduler
    sched = create_scheduler()
    sched.start()
    holder["scheduler"] = sched
    logger.info("Scheduler started from UI")
    return sched


def stop_scheduler():
    holder = _holder()
    if holder["scheduler"] is not None and holder["scheduler"].running:
        holder["scheduler"].shutdown(wait=False)
        logger.info("Scheduler stopped from UI")
    holder["scheduler"] = None


def render_scheduler_controls(compact: bool = False):
    """Status + Start/Stop control. `compact=True` renders one slim row (for
    the sidebar); the full version (with an explanatory line) is used
    elsewhere, e.g. the Replies debug panel."""
    running = is_running()

    if compact:
        col_dot, col_btn = st.columns([2, 1])
        with col_dot:
            if running:
                st.markdown(
                    '<p style="color:#4ade80;font-size:11px;font-family:\'Space Mono\',monospace;margin:6px 0 0 0">🟢 Scheduler on</p>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<p style="color:#666;font-size:11px;font-family:\'Space Mono\',monospace;margin:6px 0 0 0">⚪ Scheduler off</p>',
                    unsafe_allow_html=True,
                )
        with col_btn:
            if running:
                if st.button("Stop", key="sched_stop_btn", use_container_width=True):
                    stop_scheduler()
                    st.rerun()
            else:
                if st.button("Start", key="sched_start_btn", use_container_width=True, type="primary"):
                    with st.spinner("Starting..."):
                        start_scheduler()
                    st.rerun()
        return

    if running:
        st.markdown(
            '<p style="color:#4ade80;font-size:11px;font-family:\'Space Mono\',monospace;margin:0">🟢 SCHEDULER ON</p>'
            '<p style="color:#555;font-size:10px;margin:2px 0">Auto reply-check, follow-ups & Sheets sync running</p>',
            unsafe_allow_html=True,
        )
        if st.button("⏹ Stop Scheduler", key="sched_stop_btn_full", use_container_width=True):
            stop_scheduler()
            st.rerun()
    else:
        st.markdown(
            '<p style="color:#f87171;font-size:11px;font-family:\'Space Mono\',monospace;margin:0">🔴 SCHEDULER OFF</p>'
            '<p style="color:#555;font-size:10px;margin:2px 0">No auto reply-check / follow-ups / Sheets sync</p>',
            unsafe_allow_html=True,
        )
        if st.button("▶ Start Scheduler", key="sched_start_btn_full", use_container_width=True, type="primary"):
            with st.spinner("Starting scheduler..."):
                start_scheduler()
            st.rerun()
