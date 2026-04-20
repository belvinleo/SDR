"""Conditional routing functions for the SDR StateGraph."""
import os
from .state import SDRState

AUTO_APPROVE_THRESHOLD = float(os.getenv("AUTO_APPROVE_THRESHOLD", "0.85"))
MAX_TOUCHES = int(os.getenv("MAX_TOUCHES", "8"))


def route_by_score(state: SDRState) -> str:
    """After scoring: send to draft or log as disqualified."""
    if state.get("qualified"):
        return "qualified"
    return "disqualified"


def route_approval(state: SDRState) -> str:
    """After HITL gate: auto-approve high-confidence, else wait for human."""
    if state.get("approved"):
        return "approved"
    if state.get("confidence", 0) >= AUTO_APPROVE_THRESHOLD:
        return "auto"
    # hitl_required=True means the interrupt already paused here
    # and the human has not yet approved — keep waiting (reject loop)
    return "rejected"


def route_reply(state: SDRState) -> str:
    """After reply handler: book, continue sequence, or stop."""
    status = state.get("reply_status")
    touch = state.get("touch_number", 0)

    if status == "interested":
        return "interested"
    if status in ("not_interested", "bounce"):
        return "stop"
    if touch >= MAX_TOUCHES:
        return "stop"
    # ooo, follow_up, or None (no reply yet) — continue sequence
    return "follow_up"
