"""
Shared dependencies and state for the SDR Agent API.
Helps avoid circular imports between main.py and routers.
"""
from __future__ import annotations
import structlog

log = structlog.get_logger()

_graph = None

def get_graph():
    """FastAPI dependency to get the initialised LangGraph instance."""
    global _graph
    if _graph is None:
        raise RuntimeError("Graph not initialised — startup not complete")
    return _graph

def set_graph(graph):
    """Initialise the global graph instance (called from main.py lifespan)."""
    global _graph
    _graph = graph
    log.info("deps.graph_set")

def is_graph_ready() -> bool:
    """Check if the graph is initialised."""
    return _graph is not None
