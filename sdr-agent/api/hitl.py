"""
HITL router — human approval/rejection of email drafts.

Flow:
1. Pipeline runs → hits hitl_gate node → pauses (interrupt_before)
2. Frontend polls GET /hitl/pending → shows drafts in Approval Queue
3. Human approves/rejects → POST /hitl/approve → pipeline resumes
4. Rejection with feedback loops back to draft node for revision
"""
from __future__ import annotations
import structlog
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from api.deps import get_graph
from db.leads import list_leads, upsert_lead

log = structlog.get_logger()
router = APIRouter()


class ApprovalPayload(BaseModel):
    lead_id: str
    approved: bool
    feedback: str | None = None     # Optional human notes for revision


def _format_lead(row: dict) -> dict:
    """Convert a DB row to the camelCase shape the frontend expects."""
    import json
    signals_raw = row.get("signals") or "{}"
    firm_raw = row.get("firmographics") or "{}"
    signals = json.loads(signals_raw) if isinstance(signals_raw, str) else signals_raw
    firm = json.loads(firm_raw) if isinstance(firm_raw, str) else firm_raw

    return {
        "id":           row["lead_id"],
        "name":         row.get("name", ""),
        "firstName":    row.get("first_name", ""),
        "lastName":     row.get("last_name", ""),
        "email":        row.get("email", ""),
        "company":      row.get("company", ""),
        "domain":       row.get("domain", ""),
        "title":        row.get("title", ""),
        "linkedinUrl":  row.get("linkedin_url"),
        "status":       row.get("status", "prospecting"),
        "fitScore":     round((row.get("fit_score") or 0) * 100),
        "intentScore":  round((row.get("intent_score") or 0) * 100),
        "finalScore":   round((row.get("final_score") or 0) * 100),
        "channel":      row.get("channel", "email"),
        "touchNumber":  row.get("touch_number", 0),
        "confidence":   row.get("confidence", 0),
        "draftSubject": row.get("draft_subject"),
        "draftBody":    row.get("draft_body"),
        "replyStatus":  row.get("reply_status"),
        "meetingBooked": row.get("meeting_booked", False),
        "signals": {
            "recentFunding":    signals.get("recent_funding"),
            "leadershipHiring": signals.get("leadership_hiring", []),
            "techStack":        signals.get("tech_stack", []),
            "employeeCount":    signals.get("employee_count") or firm.get("employees"),
            "industry":         signals.get("industry") or firm.get("industry"),
        },
        "createdAt":        row["created_at"].isoformat() if row.get("created_at") else None,
        "lastContactedAt":  row["last_contacted_at"].isoformat() if row.get("last_contacted_at") else None,
    }


@router.post("/approve")
async def handle_approval(
    payload: ApprovalPayload,
    graph=Depends(get_graph),
):
    """
    Resume a paused pipeline after human reviews the email draft.
    - approved=True  → graph continues to sequence node
    - approved=False → graph loops back to draft node for revision
    """
    config = {"configurable": {"thread_id": payload.lead_id}}

    try:
        state_snapshot = await graph.aget_state(config)
        if not state_snapshot or not state_snapshot.values:
            raise HTTPException(status_code=404, detail=f"Lead {payload.lead_id} not found in pipeline")

        update = {
            "approved":     payload.approved,
            "hitl_required": False,
        }
        if not payload.approved and payload.feedback:
            update["error"] = f"REVISION_REQUESTED: {payload.feedback}"

        await graph.aupdate_state(config, update, as_node="hitl_gate")

        # Sync new status to leads table immediately so the queue refreshes
        current = {**state_snapshot.values, **update}
        try:
            await upsert_lead({**current, "lead_id": payload.lead_id}, "hitl_gate")
        except Exception as db_err:
            log.warning("hitl.db_sync_failed", error=str(db_err))

        # Resume the pipeline (runs rest of graph in background via astream)
        async for event in graph.astream(None, config=config):
            node_name = list(event.keys())[0] if event else "unknown"
            log.info("hitl.pipeline_resumed", lead_id=payload.lead_id, node=node_name)
            break

        action = "approved" if payload.approved else "rejected_for_revision"
        log.info("hitl.decision", lead_id=payload.lead_id, action=action)

        return {
            "lead_id": payload.lead_id,
            "action":  action,
            "status":  "pipeline_resumed",
        }

    except HTTPException:
        raise
    except Exception as e:
        log.error("hitl.error", lead_id=payload.lead_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pending")
async def list_pending_approvals():
    """
    Return all leads currently paused at the HITL gate (status = pending_approval).
    The leads table is kept in sync by the pipeline runner, so this is a simple DB query.
    """
    rows = await list_leads(status="pending_approval", limit=50)
    return {"pending": [_format_lead(r) for r in rows]}
