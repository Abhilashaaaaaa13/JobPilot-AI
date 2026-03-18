from functools import partial
from langgraph.graph import StateGraph,END
from langgraph.checkpoint.sqlite import SqliteSaver
from sqlalchemy.orm import Session
from backend.pipeline.state import PipelineState
from backend.pipeline.nodes import (
    scraper_node,
    scorer_node,
    research_node,
    contact_finder_node,
    resume_optimizer_node,
    email_generator_node,
    email_sender_node,
)

def should_continue_after_scraping(state:PipelineState)->str:
    """Conditional edge after scraping.
    
    Concept: Routing function
    Returns the name of next node to go to.
    If nothing was scraped — end early.
    No point running scorer on empty data."""

    jobs      = state.get("jobs_scraped", [])
    companies = state.get("companies_scraped", [])

    if not jobs and not companies:
        return "end"
    return "score_and_research"

def should_continue_after_scoring(state:PipelineState)->str:
    """Conditional edge after scoring.
    If no relevant jobs found and no companies
    to research — end early."""
    relevant  = state.get("relevant_jobs", [])
    companies = state.get("companies_scraped", [])

    if not relevant and not companies:
        return "end"
    return "optimize_resumes"

def build_graph(db:Session):
    """Builds and compiles the pipeline graph.
    
    Concept: Graph compilation
    compile() validates the graph structure,
    sets up checkpointing, and prepares
    interrupt points.
    
    Why pass db to nodes via partial()?
    LangGraph node functions only receive state.
    We need db session too.
    partial() pre-fills the db argument so
    LangGraph can call node(state) cleanly.
    
    Why SqliteSaver?
    Persists state across app restarts.
    User can close browser, come back tomorrow,
    and still resume their pipeline.
    Free, no extra infrastructure needed."""

    # Wrap nodes with db session
    # partial() = pre-fill db argument
    scraper_with_db          = partial(scraper_node,          db=db)
    scorer_with_db           = partial(scorer_node,           db=db)
    research_with_db         = partial(research_node,         db=db)
    contact_finder_with_db   = partial(contact_finder_node,   db=db)
    resume_optimizer_with_db = partial(resume_optimizer_node, db=db)
    email_generator_with_db  = partial(email_generator_node,  db=db)
    email_sender_with_db     = partial(email_sender_node,     db=db)

    # Build graph
    graph = StateGraph(PipelineState)

    # Add all nodes
    graph.add_node("scraper",          scraper_with_db)
    graph.add_node("scorer",           scorer_with_db)
    graph.add_node("researcher",       research_with_db)
    graph.add_node("contact_finder",   contact_finder_with_db)
    graph.add_node("resume_optimizer", resume_optimizer_with_db)
    graph.add_node("email_generator",  email_generator_with_db)
    graph.add_node("email_sender",     email_sender_with_db)

    # Entry point
    graph.set_entry_point("scraper")

    # Conditional edge after scraping
    graph.add_conditional_edges(
        "scraper",
        should_continue_after_scraping,
        {
            "end"               : END,
            "score_and_research": "scorer"
        }
    )

    # Scorer and researcher run after scraper
    # Scorer → resume_optimizer (after scoring)
    graph.add_conditional_edges(
        "scorer",
        should_continue_after_scoring,
        {
            "end"             : END,
            "optimize_resumes": "resume_optimizer"
        }
    )

    # Researcher → contact_finder → resume_optimizer
    # Note: researcher runs parallel with scorer
    # Both feed into resume_optimizer
    graph.add_edge("scraper",          "researcher")
    graph.add_edge("researcher",       "contact_finder")
    graph.add_edge("contact_finder",   "resume_optimizer")

    # After both scorer and contact_finder
    # feed into resume_optimizer
    # resume_optimizer → INTERRUPT 1 → email_generator
    graph.add_edge("resume_optimizer", "email_generator")

    # email_generator → INTERRUPT 2 → email_sender
    graph.add_edge("email_generator",  "email_sender")

    # email_sender → END
    graph.add_edge("email_sender", END)

    # Checkpointer — saves state to SQLite
    checkpointer = SqliteSaver.from_conn_string(
        "data/pipeline_state.db"
    )

    # Compile with interrupt points
    # interrupt_before = pause BEFORE entering these nodes
    # State is saved, user can review, then resume
    compiled = graph.compile(
        checkpointer     = checkpointer,
        interrupt_before = [
            "email_generator",  # INTERRUPT 1 — resume review
            "email_sender",     # INTERRUPT 2 — email review
        ]
    )

    return compiled