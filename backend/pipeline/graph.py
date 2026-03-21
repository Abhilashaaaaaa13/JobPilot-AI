# backend/pipeline/graph.py

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from backend.pipeline.state import TrackAState, TrackBState
from backend.pipeline.nodes import (
    scrape_jobs_node,
    optimize_resumes_a_node,
    apply_node,
    scrape_companies_node,
    optimize_resumes_b_node,
    generate_emails_node,
    send_emails_node,
)
from loguru import logger


# ─────────────────────────────────────────────
# CONDITIONAL EDGES
# ─────────────────────────────────────────────

def track_a_after_scrape(state: TrackAState) -> str:
    jobs = state.get("scraped_jobs", [])
    if not jobs:
        logger.warning("No jobs found — ending Track A")
        return "end"
    return "continue"


def track_b_after_scrape(state: TrackBState) -> str:
    companies = state.get("scraped_companies", [])
    if not companies:
        logger.warning("No companies found — ending Track B")
        return "end"
    return "continue"


# ─────────────────────────────────────────────
# TRACK A GRAPH
# ─────────────────────────────────────────────

def build_track_a_graph():
    """
    Flow:
    scrape_jobs
        ↓ no jobs → END
        ↓ jobs found → continue
    [INTERRUPT — user selects jobs]
    optimize_resumes
        ↓
    [INTERRUPT — resume review]
    apply
        ↓
    END
    """
    graph = StateGraph(TrackAState)

    graph.add_node("scrape_jobs",       scrape_jobs_node)
    graph.add_node("optimize_resumes",  optimize_resumes_a_node)
    graph.add_node("apply",             apply_node)

    graph.set_entry_point("scrape_jobs")

    graph.add_conditional_edges(
        "scrape_jobs",
        track_a_after_scrape,
        {
            "end"     : END,
            "continue": "optimize_resumes"
        }
    )

    graph.add_edge("optimize_resumes", "apply")
    graph.add_edge("apply",            END)

    checkpointer = SqliteSaver.from_conn_string(
        "data/track_a_state.db"
    )

    compiled = graph.compile(
        checkpointer     = checkpointer,
        interrupt_before = [
            "optimize_resumes",  # INTERRUPT 1 — job selection
            "apply",             # INTERRUPT 2 — resume review
        ]
    )

    return compiled


# ─────────────────────────────────────────────
# TRACK B GRAPH
# ─────────────────────────────────────────────

def build_track_b_graph():
    """
    Flow:
    scrape_companies
        ↓ no companies → END
        ↓ found → continue
    [INTERRUPT — user selects companies]
    optimize_resumes
        ↓
    [INTERRUPT — resume review]
    generate_emails
        ↓
    [INTERRUPT — email review]
    send_emails
        ↓
    END
    """
    graph = StateGraph(TrackBState)

    graph.add_node("scrape_companies",  scrape_companies_node)
    graph.add_node("optimize_resumes",  optimize_resumes_b_node)
    graph.add_node("generate_emails",   generate_emails_node)
    graph.add_node("send_emails",       send_emails_node)

    graph.set_entry_point("scrape_companies")

    graph.add_conditional_edges(
        "scrape_companies",
        track_b_after_scrape,
        {
            "end"     : END,
            "continue": "optimize_resumes"
        }
    )

    graph.add_edge("optimize_resumes", "generate_emails")
    graph.add_edge("generate_emails",  "send_emails")
    graph.add_edge("send_emails",      END)

    checkpointer = SqliteSaver.from_conn_string(
        "data/track_b_state.db"
    )

    compiled = graph.compile(
        checkpointer     = checkpointer,
        interrupt_before = [
            "optimize_resumes",  # INTERRUPT 1 — company selection
            "generate_emails",   # INTERRUPT 2 — resume review
            "send_emails",       # INTERRUPT 3 — email review
        ]
    )

    return compiled


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def get_track_a_state(thread_id: str) -> dict:
    try:
        graph  = build_track_a_graph()
        config = {"configurable": {"thread_id": thread_id}}
        state  = graph.get_state(config)
        return state.values if state else {}
    except Exception as e:
        logger.error(f"Get Track A state error: {e}")
        return {}


def get_track_b_state(thread_id: str) -> dict:
    try:
        graph  = build_track_b_graph()
        config = {"configurable": {"thread_id": thread_id}}
        state  = graph.get_state(config)
        return state.values if state else {}
    except Exception as e:
        logger.error(f"Get Track B state error: {e}")
        return {}


def update_track_a_state(thread_id: str, updates: dict) -> bool:
    try:
        graph  = build_track_a_graph()
        config = {"configurable": {"thread_id": thread_id}}
        graph.update_state(config, updates)
        return True
    except Exception as e:
        logger.error(f"Update Track A state error: {e}")
        return False


def update_track_b_state(thread_id: str, updates: dict) -> bool:
    try:
        graph  = build_track_b_graph()
        config = {"configurable": {"thread_id": thread_id}}
        graph.update_state(config, updates)
        return True
    except Exception as e:
        logger.error(f"Update Track B state error: {e}")
        return False


def resume_track_a(thread_id: str) -> None:
    import threading
    def _run():
        try:
            graph  = build_track_a_graph()
            config = {"configurable": {"thread_id": thread_id}}
            graph.invoke(None, config=config)
        except Exception as e:
            logger.error(f"Track A resume error: {e}")
    threading.Thread(target=_run, daemon=True).start()


def resume_track_b(thread_id: str) -> None:
    import threading
    def _run():
        try:
            graph  = build_track_b_graph()
            config = {"configurable": {"thread_id": thread_id}}
            graph.invoke(None, config=config)
        except Exception as e:
            logger.error(f"Track B resume error: {e}")
    threading.Thread(target=_run, daemon=True).start()