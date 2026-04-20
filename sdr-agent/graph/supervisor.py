"""
LangGraph StateGraph — wires all SDR agent nodes together.
Run with PostgresSaver checkpointer so sequence state survives restarts.
"""
from __future__ import annotations
import os
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver

from .state import SDRState
from .edges import route_by_score, route_approval, route_reply
from .nodes.prospecting import run as prospect_run
from .nodes.enrichment import run as enrich_run
from .nodes.scoring import run as score_run
from .nodes.outreach import run as draft_run
from .nodes.sequencer import run as sequence_run
from .nodes.reply_handler import run as reply_run


async def log_to_crm(state: SDRState) -> dict:
    """Terminal node — write final lead status to HubSpot."""
    from tools.hubspot import upsert_contact, log_activity
    await upsert_contact(state)
    await log_activity(
        lead_id=state["lead_id"],
        action="pipeline_complete",
        metadata={
            "final_score": state.get("final_score"),
            "reply_status": state.get("reply_status"),
            "meeting_booked": state.get("meeting_booked"),
            "touches_sent": state.get("touch_number"),
        }
    )
    return {}


def build_graph(checkpointer: PostgresSaver):
    """Build and compile the SDR StateGraph."""
    g = StateGraph(SDRState)

    # ── Register nodes ──────────────────────────────────────────
    g.add_node("prospect",     prospect_run)
    g.add_node("enrich",       enrich_run)
    g.add_node("score",        score_run)
    g.add_node("draft",        draft_run)
    g.add_node("hitl_gate",    lambda s: s)   # passthrough; graph pauses here
    g.add_node("sequence",     sequence_run)
    g.add_node("handle_reply", reply_run)
    g.add_node("log_crm",      log_to_crm)

    # ── Linear pipeline ─────────────────────────────────────────
    g.set_entry_point("prospect")
    g.add_edge("prospect", "enrich")
    g.add_edge("enrich",   "score")

    # ── Conditional: qualified vs disqualified ───────────────────
    g.add_conditional_edges("score", route_by_score, {
        "qualified":    "draft",
        "disqualified": "log_crm",
    })

    g.add_edge("draft", "hitl_gate")

    # ── Conditional: approved / auto-send / revise ───────────────
    g.add_conditional_edges("hitl_gate", route_approval, {
        "approved":  "sequence",
        "auto":      "sequence",
        "rejected":  "draft",        # rewrite loop
    })

    # ── Sequence → reply handler ─────────────────────────────────
    g.add_edge("sequence", "handle_reply")

    # ── Conditional: route by reply ──────────────────────────────
    g.add_conditional_edges("handle_reply", route_reply, {
        "interested": "log_crm",
        "follow_up":  "sequence",
        "stop":       "log_crm",
    })

    g.add_edge("log_crm", END)

    return g.compile(
        checkpointer=checkpointer,
        interrupt_before=["hitl_gate"],  # pause for human approval
    )
