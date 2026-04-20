"""
Webhook router — triggers the SDR pipeline for a new lead.
Accepts lead data as JSON, validates required fields, kicks off LangGraph run.
"""
from __future__ import annotations
import uuid, structlog
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel, EmailStr
from api.deps import get_graph
from db.leads import get_lead_by_email, insert_lead_initial, upsert_lead
from memory.redis_store import get_last_touch, get_touch_history

log = structlog.get_logger()
router = APIRouter()


class LeadPayload(BaseModel):
    email: EmailStr
    name: str
    first_name: str = ""
    last_name: str = ""
    company: str
    domain: str
    title: str
    linkedin_url: str | None = None


async def _run_pipeline(graph, state: dict) -> None:
    """
    Run the LangGraph pipeline in the background.
    After each node completes, upserts the current state into the leads table
    so the frontend always has fresh data to display.
    """
    config = {"configurable": {"thread_id": state["lead_id"]}}
    try:
        async for event in graph.astream(state, config=config):
            if not event:
                continue
            node_name = list(event.keys())[0]
            node_output = event[node_name]

            # Merge node output into running state so downstream upserts are complete
            if isinstance(node_output, dict):
                state = {**state, **node_output}

            log.info("pipeline.event", lead_id=state["lead_id"], node=node_name)

            try:
                await upsert_lead(state, node_name)
            except Exception as db_err:
                # Never let a DB write crash the pipeline
                log.warning("pipeline.db_sync_failed", node=node_name, error=str(db_err))

    except Exception as e:
        log.error("pipeline.error", lead_id=state["lead_id"], error=str(e))


@router.post("/lead")
async def ingest_lead(
    payload: LeadPayload,
    background_tasks: BackgroundTasks,
    graph=Depends(get_graph),
):
    """
    Trigger the SDR pipeline for a new lead.
    Deduplicates by email — if the lead is already in an active sequence, returns
    the existing lead_id instead of starting a new run.
    """
    # Deduplicate by email address
    existing = await get_lead_by_email(str(payload.email))
    if existing and existing["status"] not in ("complete", "disqualified", "replied_not_interested"):
        log.info("webhook.duplicate_lead", email=payload.email, lead_id=existing["lead_id"])
        return {"lead_id": existing["lead_id"], "status": "already_active"}

    lead_id = str(uuid.uuid4())
    first_name = payload.first_name or payload.name.split()[0]
    last_name = payload.last_name or " ".join(payload.name.split()[1:])

    initial_state = {
        "lead_id":      lead_id,
        "email":        str(payload.email),
        "name":         payload.name,
        "first_name":   first_name,
        "last_name":    last_name,
        "company":      payload.company,
        "domain":       payload.domain,
        "title":        payload.title,
        "linkedin_url": payload.linkedin_url,
        # Defaults
        "signals": {},
        "firmographics": {},
        "email_verified": False,
        "fit_score": 0.0,
        "intent_score": 0.0,
        "final_score": 0.0,
        "qualified": False,
        "disqualification_reason": None,
        "channel": "email",
        "draft_subject": None,
        "draft_body": "",
        "confidence": 0.0,
        "approved": False,
        "touch_number": 0,
        "thread_id": None,
        "scheduled_at": None,
        "reply_raw": None,
        "reply_status": None,
        "meeting_booked": False,
        "hitl_required": True,
        "error": None,
        "retry_count": 0,
    }

    # Write the row immediately so GET /leads shows it right away
    await insert_lead_initial(initial_state)

    log.info("webhook.lead_received", lead_id=lead_id, email=payload.email)
    background_tasks.add_task(_run_pipeline, graph, initial_state)

    return {"lead_id": lead_id, "status": "pipeline_started"}


@router.get("/lead/{lead_id}/status")
async def lead_status(lead_id: str):
    """Check the current pipeline status for a lead via Redis."""
    touch = await get_last_touch(lead_id)
    history = await get_touch_history(lead_id)
    return {
        "lead_id":      lead_id,
        "last_touch":   touch,
        "touch_history": history,
    }
