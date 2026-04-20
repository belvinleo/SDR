"""
Follow-up scheduler — runs every 15 minutes to resume leads
whose next touch is due.

Flow:
1. Query leads table for status='sequencing' AND scheduled_at <= NOW()
2. For each lead, resume its LangGraph thread via graph.astream(None, ...)
3. The graph picks up exactly where it left off (checkpointed in Postgres)
"""
from __future__ import annotations
import structlog
from db.connection import get_pool

log = structlog.get_logger()


async def resume_scheduled_leads(graph) -> None:
    """
    Find all leads with a past-due scheduled_at and resume their pipelines.
    Called every 15 minutes by APScheduler.
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT lead_id, email, company, touch_number, scheduled_at
            FROM leads
            WHERE status = 'sequencing'
              AND scheduled_at IS NOT NULL
              AND scheduled_at <= NOW()
            ORDER BY scheduled_at ASC
            LIMIT 50
        """)

    if not rows:
        log.debug("scheduler.no_leads_due")
        return

    log.info("scheduler.resuming_leads", count=len(rows))

    for row in rows:
        lead_id = row["lead_id"]
        try:
            config = {"configurable": {"thread_id": lead_id}}
            # Resume from checkpoint — graph knows exactly which node to run next
            async for event in graph.astream(None, config=config):
                node_name = list(event.keys())[0] if event else "unknown"
                log.info(
                    "scheduler.lead_resumed",
                    lead_id=lead_id,
                    node=node_name,
                    company=row["company"],
                    touch=row["touch_number"],
                )
                break  # Let it run in the background after first event
        except Exception as e:
            log.error("scheduler.resume_failed", lead_id=lead_id, error=str(e))
            # Never let one failure stop the rest of the batch
            continue
