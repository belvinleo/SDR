"""
SDRState — single source of truth for one lead flowing through the pipeline.
All agent nodes read from and write to this TypedDict.
"""
from __future__ import annotations
from typing import TypedDict, Literal, Optional
from datetime import datetime


class SDRState(TypedDict):
    # ── Lead identity ──────────────────────────────────────────────
    lead_id: str                        # UUID, generated at prospect node
    email: str
    name: str
    first_name: str
    last_name: str
    company: str
    domain: str                         # e.g. "acme.com"
    title: str
    linkedin_url: Optional[str]

    # ── Enrichment ─────────────────────────────────────────────────
    signals: dict                       # {"funding": str, "hiring": list, "tech_stack": list}
    firmographics: dict                 # {"employees": int, "industry": str, "hq": str}
    email_verified: bool

    # ── Qualification ──────────────────────────────────────────────
    fit_score: float                    # 0.0–1.0  (ICP match)
    intent_score: float                 # 0.0–1.0  (buying signals)
    final_score: float                  # weighted composite
    qualified: bool
    disqualification_reason: Optional[str]

    # ── Outreach ───────────────────────────────────────────────────
    channel: Literal["email", "linkedin"]
    draft_subject: Optional[str]        # email only
    draft_body: str
    confidence: float                   # LLM self-assessed 0.0–1.0
    approved: bool
    touch_number: int                   # 0-indexed, max 7 (8 touches total)
    thread_id: Optional[str]            # email thread or LinkedIn convo ID
    scheduled_at: Optional[datetime]

    # ── Reply tracking ─────────────────────────────────────────────
    reply_raw: Optional[str]            # raw reply text
    reply_status: Optional[Literal[
        "interested",
        "not_interested",
        "ooo",              # out of office
        "bounce",
        "follow_up",        # neutral, keep sequence going
    ]]
    meeting_booked: bool

    # ── Control ────────────────────────────────────────────────────
    hitl_required: bool                 # True when confidence < AUTO_APPROVE_THRESHOLD
    error: Optional[str]                # last error message if a node failed
    retry_count: int                    # incremented on node failure
