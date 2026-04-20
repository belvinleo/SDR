"""
Postgres checkpointer — LangGraph PostgresSaver setup.
Enables pipeline persistence across restarts and supports the HITL pause/resume pattern.
"""
from __future__ import annotations
import os, structlog
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

log = structlog.get_logger()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://sdr:sdrpass@localhost:5432/sdrdb")

_checkpointer: PostgresSaver | None = None
_pool: ConnectionPool | None = None


def get_checkpointer() -> PostgresSaver:
    """
    Return a singleton PostgresSaver instance.
    Creates the connection pool and schema tables on first call.
    """
    global _checkpointer, _pool

    if _checkpointer is not None:
        return _checkpointer

    log.info("pg_checkpointer.initializing", db=DATABASE_URL.split("@")[-1])

    # ConnectionPool (psycopg 3): 2–10 connections
    # NOTE: PostgresSaver REQUIRES autocommit=True and row_factory=dict_row
    _pool = ConnectionPool(
        conninfo=DATABASE_URL,
        min_size=2,
        max_size=10,
        kwargs={
            "autocommit": True, 
            "row_factory": dict_row,
        },
    )

    _checkpointer = PostgresSaver(_pool)

    # Create checkpointing tables if they don't exist
    _checkpointer.setup()

    log.info("pg_checkpointer.ready")
    return _checkpointer


async def get_lead_state(lead_id: str, graph) -> dict | None:
    """
    Retrieve the latest saved state for a lead from the checkpointer.
    Returns None if lead has never been processed.
    """
    checkpointer = get_checkpointer()
    config = {"configurable": {"thread_id": lead_id}}
    snapshot = await graph.aget_state(config)
    if snapshot and snapshot.values:
        return snapshot.values
    return None
