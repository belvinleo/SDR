"""
Lead CRUD operations against the leads table.
All functions are async-native (asyncpg).
"""
from __future__ import annotations
import json, structlog
from datetime import datetime, timezone
from db.connection import get_pool

log = structlog.get_logger()

# Maps the last-completed graph node → lead status string
_NODE_STATUS: dict[str, str | None] = {
    "prospect":     None,          # resolved dynamically below
    "enrich":       "enriching",
    "score":        None,          # resolved dynamically below
    "draft":        "drafting",
    "hitl_gate":    "pending_approval",
    "sequence":     "sequencing",
    "handle_reply": None,          # resolved dynamically below
    "log_crm":      "complete",
}


def derive_status(state: dict, last_node: str) -> str:
    """Derive the UI-facing status string from graph state + the node that just ran."""
    if last_node == "log_crm":
        return "complete"
    if last_node in ("draft", "hitl_gate"):
        return "pending_approval"
    if last_node == "sequence":
        return "sequencing"
    if last_node == "handle_reply":
        rs = state.get("reply_status")
        if rs == "interested":
            return "replied_interested"
        if rs in ("not_interested", "bounce"):
            return "replied_not_interested"
        return "sequencing"
    if last_node == "score":
        return "disqualified" if not state.get("qualified") else "qualified"
    if last_node == "prospect":
        return "disqualified" if not state.get("qualified") else "prospecting"
    if last_node == "enrich":
        return "enriching"
    return "prospecting"


async def upsert_lead(state: dict, last_node: str) -> None:
    """
    Insert or update the lead row from the current SDRState.
    Called after each graph node completes.
    """
    pool = await get_pool()
    status = derive_status(state, last_node)
    last_contacted = (
        datetime.now(timezone.utc) if last_node == "sequence" else None
    )

    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO leads (
                lead_id, email, name, first_name, last_name,
                company, domain, title, linkedin_url,
                status, fit_score, intent_score, final_score,
                channel, touch_number, confidence,
                draft_subject, draft_body,
                reply_status, meeting_booked, hitl_required,
                signals, firmographics, disqualification_reason,
                last_contacted_at, updated_at
            ) VALUES (
                $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,
                $14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25,NOW()
            )
            ON CONFLICT (lead_id) DO UPDATE SET
                status                  = EXCLUDED.status,
                fit_score               = EXCLUDED.fit_score,
                intent_score            = EXCLUDED.intent_score,
                final_score             = EXCLUDED.final_score,
                channel                 = EXCLUDED.channel,
                touch_number            = EXCLUDED.touch_number,
                confidence              = EXCLUDED.confidence,
                draft_subject           = EXCLUDED.draft_subject,
                draft_body              = EXCLUDED.draft_body,
                reply_status            = EXCLUDED.reply_status,
                meeting_booked          = EXCLUDED.meeting_booked,
                hitl_required           = EXCLUDED.hitl_required,
                signals                 = EXCLUDED.signals,
                firmographics           = EXCLUDED.firmographics,
                disqualification_reason = EXCLUDED.disqualification_reason,
                last_contacted_at       = COALESCE(EXCLUDED.last_contacted_at, leads.last_contacted_at),
                updated_at              = NOW()
        """,
            state["lead_id"],
            state.get("email", ""),
            state.get("name", ""),
            state.get("first_name", ""),
            state.get("last_name", ""),
            state.get("company", ""),
            state.get("domain", ""),
            state.get("title", ""),
            state.get("linkedin_url"),
            status,
            state.get("fit_score", 0.0),
            state.get("intent_score", 0.0),
            state.get("final_score", 0.0),
            state.get("channel", "email"),
            state.get("touch_number", 0),
            state.get("confidence", 0.0),
            state.get("draft_subject"),
            state.get("draft_body"),
            state.get("reply_status"),
            bool(state.get("meeting_booked", False)),
            bool(state.get("hitl_required", True)),
            json.dumps(state.get("signals", {})),
            json.dumps(state.get("firmographics", {})),
            state.get("disqualification_reason"),
            last_contacted,
        )

    log.debug("db.lead_upserted", lead_id=state["lead_id"], status=status, node=last_node)


async def insert_lead_initial(state: dict) -> None:
    """
    Insert a brand-new lead row when the pipeline first starts.
    Uses INSERT ... ON CONFLICT DO NOTHING so duplicate webhook calls are safe.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO leads (
                lead_id, email, name, first_name, last_name,
                company, domain, title, linkedin_url, status, created_at, updated_at
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,'prospecting',NOW(),NOW())
            ON CONFLICT (email) DO NOTHING
        """,
            state["lead_id"],
            state["email"],
            state.get("name", ""),
            state.get("first_name", ""),
            state.get("last_name", ""),
            state.get("company", ""),
            state.get("domain", ""),
            state.get("title", ""),
            state.get("linkedin_url"),
        )


async def get_lead_by_id(lead_id: str) -> dict | None:
    """Fetch a single lead row by lead_id."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM leads WHERE lead_id = $1", lead_id
        )
    return dict(row) if row else None


async def get_lead_by_email(email: str) -> dict | None:
    """Fetch a single lead row by email address."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM leads WHERE email = $1", email
        )
    return dict(row) if row else None


async def list_leads(
    status: str | None = None,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """List leads with optional status filter and text search."""
    pool = await get_pool()
    conditions: list[str] = []
    params: list = []
    idx = 1

    if status:
        conditions.append(f"status = ${idx}")
        params.append(status)
        idx += 1
    if search:
        conditions.append(
            f"(name ILIKE ${idx} OR email ILIKE ${idx} OR company ILIKE ${idx})"
        )
        params.append(f"%{search}%")
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params += [limit, offset]

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT * FROM leads
            {where}
            ORDER BY updated_at DESC
            LIMIT ${idx} OFFSET ${idx + 1}
            """,
            *params,
        )
    return [dict(r) for r in rows]


async def get_stats() -> dict:
    """Aggregate stats for the dashboard KPI cards."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
                COUNT(*)                                                 AS total_leads,
                COUNT(*) FILTER (WHERE status NOT IN ('disqualified','complete'))
                                                                         AS in_pipeline,
                COUNT(*) FILTER (WHERE status = 'pending_approval')      AS pending_approval,
                COUNT(*) FILTER (WHERE meeting_booked = TRUE)            AS meetings_booked,
                COUNT(*) FILTER (WHERE reply_status = 'interested')      AS interested,
                COUNT(*) FILTER (WHERE reply_status IS NOT NULL
                                   AND reply_status != 'follow_up')      AS total_replied,
                COUNT(*) FILTER (WHERE touch_number > 0)                 AS emails_sent
            FROM leads
        """)
    r = dict(row)
    total_sent = r["emails_sent"] or 0
    total_replied = r["total_replied"] or 0
    reply_rate = round((total_replied / total_sent * 100), 1) if total_sent > 0 else 0.0
    return {
        "totalLeads":      r["total_leads"],
        "inPipeline":      r["in_pipeline"],
        "pendingApproval": r["pending_approval"],
        "meetingsBooked":  r["meetings_booked"],
        "replyRate":       reply_rate,
        "emailsSent":      total_sent,
    }


async def get_funnel_stats() -> list[dict]:
    """Pipeline funnel counts for the Dashboard funnel chart."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT
                COUNT(*)                                                AS prospected,
                COUNT(*) FILTER (WHERE status != 'prospecting')        AS enriched,
                COUNT(*) FILTER (WHERE final_score >= 0.6)             AS qualified,
                COUNT(*) FILTER (WHERE draft_body IS NOT NULL)         AS drafted,
                COUNT(*) FILTER (WHERE touch_number >= 1)              AS sent,
                COUNT(*) FILTER (WHERE reply_status IS NOT NULL
                                   AND reply_status != 'follow_up')    AS replied,
                COUNT(*) FILTER (WHERE reply_status = 'interested')    AS interested,
                COUNT(*) FILTER (WHERE meeting_booked = TRUE)          AS meeting_booked
            FROM leads
        """)
    r = dict(row)
    return [
        {"stage": "Prospected",      "count": r["prospected"]},
        {"stage": "Enriched",        "count": r["enriched"]},
        {"stage": "Qualified",       "count": r["qualified"]},
        {"stage": "Drafted",         "count": r["drafted"]},
        {"stage": "Sent (Touch 1)",  "count": r["sent"]},
        {"stage": "Replied",         "count": r["replied"]},
        {"stage": "Interested",      "count": r["interested"]},
        {"stage": "Meeting Booked",  "count": r["meeting_booked"]},
    ]
