# backend/pipeline/graph.py

from langgraph.graph           import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from backend.pipeline.state    import TrackBState
from backend.pipeline.nodes    import (
    scrape_companies_node,
    research_companies_node,
    optimize_resumes_b_node,
    generate_emails_node,
    send_emails_node,
)
from loguru import logger


# ─────────────────────────────────────────────
# CONDITIONAL EDGE
# ─────────────────────────────────────────────

def track_b_after_scrape(state: TrackBState) -> str:
    companies = state.get("scraped_companies", [])
    if not companies:
        logger.warning("No companies found — ending Track B")
        return "end"
    return "continue"


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
    research_companies          ← NEW: research before email/resume
        ↓
    optimize_resumes
        ↓
    [INTERRUPT — resume review (optional, can skip)]
    generate_emails
        ↓
    [INTERRUPT — email review before send]
    send_emails
        ↓
    END
    """
    graph = StateGraph(TrackBState)

    graph.add_node("scrape_companies",   scrape_companies_node)
    graph.add_node("research_companies", research_companies_node)
   
    graph.add_node("generate_emails",    generate_emails_node)
    graph.add_node("send_emails",        send_emails_node)

    graph.set_entry_point("scrape_companies")

    graph.add_conditional_edges(
        "scrape_companies",
        track_b_after_scrape,
        {
            "end"     : END,
            "continue": "research_companies"   # INTERRUPT fires here first
        }
    )

    # After user selects companies → research them automatically
    
    graph.add_edge("research_companies", "generate_emails")
    graph.add_edge("generate_emails",    "send_emails")
    graph.add_edge("send_emails",        END)

    checkpointer = SqliteSaver.from_conn_string("data/track_b_state.db")

    compiled = graph.compile(
        checkpointer     = checkpointer,
        interrupt_before = [
            
            "send_emails",       # INTERRUPT 2 — email review before send
            # NOTE: resume review interrupt removed — auto-approve optimized resume
            # NOTE: generate_emails runs automatically after research
        ]
    )

    return compiled


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def get_track_b_state(thread_id: str) -> dict:
    try:
        graph  = build_track_b_graph()
        config = {"configurable": {"thread_id": thread_id}}
        state  = graph.get_state(config)
        return state.values if state else {}
    except Exception as e:
        logger.error(f"Get Track B state error: {e}")
        return {}


def update_track_b_state(thread_id: str, updates: dict) -> bool:
    try:
        graph  = build_track_b_graph()
        config = {"configurable": {"thread_id": thread_id}}
        graph.update_state(config, updates)
        return True
    except Exception as e:
        logger.error(f"Update Track B state error: {e}")
        return False


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