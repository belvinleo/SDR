"""
Leads router — read-only API for the frontend to query lead data.
All writes flow through /webhook/lead (pipeline start) or /hitl/approve (HITL).
"""
from __future__ import annotations
import json, structlog
from fastapi import APIRouter, HTTPException, Query
from db.leads import list_leads, get_lead_by_id, get_stats, get_funnel_stats

log = structlog.get_logger()
router = APIRouter()


def _format_lead(row: dict) -> dict:
    """Convert a DB row to the camelCase shape the frontend expects."""
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
        # Backend stores 0.0–1.0; frontend expects 0–100
        "fitScore":     round((row.get("fit_score") or 0) * 100),
        "intentScore":  round((row.get("intent_score") or 0) * 100),
        "finalScore":   round((row.get("final_score") or 0) * 100),
        "channel":      row.get("channel", "email"),
        "touchNumber":  row.get("touch_number", 0),
        "confidence":   row.get("confidence", 0),        # kept 0–1 (frontend uses it raw)
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
        "createdAt":       row["created_at"].isoformat() if row.get("created_at") else None,
        "lastContactedAt": row["last_contacted_at"].isoformat() if row.get("last_contacted_at") else None,
    }


@router.get("")
async def get_leads(
    status: str | None = Query(default=None, description="Filter by status"),
    search: str | None = Query(default=None, description="Full-text search on name/email/company"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Return a paginated list of leads, optionally filtered."""
    rows = await list_leads(status=status, search=search, limit=limit, offset=offset)
    return {
        "leads":  [_format_lead(r) for r in rows],
        "count":  len(rows),
        "limit":  limit,
        "offset": offset,
    }


@router.get("/stats")
async def get_dashboard_stats():
    """Aggregate KPI stats for the Dashboard page."""
    stats = await get_stats()
    funnel = await get_funnel_stats()
    return {"kpis": stats, "funnel": funnel}


@router.get("/{lead_id}")
async def get_lead(lead_id: str):
    """Return a single lead by its UUID."""
    row = await get_lead_by_id(lead_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Lead {lead_id} not found")
    return _format_lead(row)
