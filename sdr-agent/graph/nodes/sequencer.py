"""
Sequencer node — executes the current outreach touch.
Routes to Instantly (email) or Unipile (LinkedIn) based on channel.
Logs touch to Redis and HubSpot. Updates touch_number for next iteration.
"""
from __future__ import annotations
import os, asyncio, structlog
from datetime import datetime, timedelta, timezone
from graph.state import SDRState
from memory.redis_store import record_touch
from tools.instantly import send_email
from tools.unipile import send_linkedin_message
from tools.hubspot import log_activity

log = structlog.get_logger()

MAX_TOUCHES = int(os.getenv("MAX_TOUCHES", "8"))

# Days to wait between each touch (0-indexed)
TOUCH_DELAYS_DAYS = [0, 3, 5, 7, 10, 14, 21, 28]


async def run(state: SDRState) -> dict:
    """Execute the current outreach touch and schedule the next one."""
    touch = state.get("touch_number", 0)
    channel = state.get("channel", "email")
    lead_id = state.get("lead_id")

    log.info("node.sequence.start", lead_id=lead_id, touch=touch, channel=channel)

    # Guard: stop if max touches reached
    if touch >= MAX_TOUCHES:
        log.info("node.sequence.max_touches_reached", lead_id=lead_id)
        return {"reply_status": "stop"}

    thread_id = None
    error = None

    try:
        if channel == "email":
            thread_id = await send_email(
                to_email=state["email"],
                to_name=state["name"],
                subject=state.get("draft_subject", f"Quick question — {state.get('company')}"),
                body=state["draft_body"],
                lead_id=lead_id,
            )
        elif channel == "linkedin":
            if not state.get("linkedin_url"):
                log.warning("node.sequence.no_linkedin_url", lead_id=lead_id)
                # Fall back to email
                thread_id = await send_email(
                    to_email=state["email"],
                    to_name=state["name"],
                    subject=state.get("draft_subject", ""),
                    body=state["draft_body"],
                    lead_id=lead_id,
                )
            else:
                thread_id = await send_linkedin_message(
                    linkedin_url=state["linkedin_url"],
                    message=state["draft_body"],
                    lead_id=lead_id,
                )

    except Exception as e:
        error = str(e)
        log.error("node.sequence.send_failed", lead_id=lead_id, touch=touch, error=error)
        # Don't crash the pipeline — mark error and continue
        return {"error": error, "retry_count": state.get("retry_count", 0) + 1}

    # Record touch in Redis (for sequence state tracking)
    await record_touch(
        lead_id=lead_id,
        touch_number=touch,
        channel=channel,
        thread_id=thread_id,
        sent_at=datetime.now(timezone.utc),
    )

    # Log activity in HubSpot
    await log_activity(
        lead_id=lead_id,
        action=f"touch_{touch + 1}_sent",
        metadata={
            "channel": channel,
            "touch_number": touch + 1,
            "thread_id": thread_id,
            "subject": state.get("draft_subject", "N/A"),
        }
    )

    # Schedule next touch date
    next_touch_index = touch + 1
    days_delay = TOUCH_DELAYS_DAYS[next_touch_index] if next_touch_index < len(TOUCH_DELAYS_DAYS) else 30
    scheduled_at = datetime.now(timezone.utc) + timedelta(days=days_delay)

    log.info(
        "node.sequence.touch_sent",
        lead_id=lead_id,
        touch=touch + 1,
        channel=channel,
        thread_id=thread_id,
        next_touch_in_days=days_delay,
    )

    return {
        "touch_number": next_touch_index,
        "thread_id": thread_id,
        "scheduled_at": scheduled_at,
        "error": None,
    }
