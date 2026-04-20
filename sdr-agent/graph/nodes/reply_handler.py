"""
Reply handler node — polls for inbound replies, classifies intent with Claude Haiku.
Classification: interested | not_interested | ooo | bounce | follow_up
"""
from __future__ import annotations
import json, structlog
from langchain_anthropic import ChatAnthropic
from graph.state import SDRState
from tools.instantly import check_reply as check_email_reply
from tools.unipile import check_reply as check_linkedin_reply
from tools.hubspot import log_activity

log = structlog.get_logger()

_model = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0)

CLASSIFY_SYSTEM = """Classify this reply to a cold sales outreach message.

Output ONLY valid JSON:
{
  "status": "interested" | "not_interested" | "ooo" | "bounce" | "follow_up",
  "meeting_booked": true | false,
  "summary": "one sentence"
}

Definitions:
- interested: prospect wants to learn more, asks questions, or agrees to a call
- not_interested: clear rejection, asks to stop, unsubscribes
- ooo: out-of-office auto-reply
- bounce: email bounced (delivery failure notice)
- follow_up: neutral reply — not a yes or no (e.g. "send me more info", "maybe later")
- meeting_booked: true only if a specific time/calendar link was confirmed
"""


async def _get_reply(state: SDRState) -> dict | None:
    """Poll the appropriate channel for an inbound reply."""
    thread_id = state.get("thread_id")
    if not thread_id:
        return None

    channel = state.get("channel", "email")
    try:
        if channel == "email":
            return await check_email_reply(thread_id)
        elif channel == "linkedin":
            return await check_linkedin_reply(thread_id)
    except Exception as e:
        log.warning("node.reply_handler.poll_failed", channel=channel, error=str(e))
    return None


async def run(state: SDRState) -> dict:
    """Check for reply and classify it. If no reply, return follow_up to continue sequence."""
    lead_id = state.get("lead_id")
    touch = state.get("touch_number", 0)
    log.info("node.reply_handler.start", lead_id=lead_id, touch=touch)

    reply = await _get_reply(state)

    # No reply yet — continue the sequence
    if not reply:
        log.info("node.reply_handler.no_reply", lead_id=lead_id)
        return {"reply_status": "follow_up", "reply_raw": None}

    reply_text = reply.get("text", "")
    log.info("node.reply_handler.reply_received", lead_id=lead_id, length=len(reply_text))

    # Classify with Claude Haiku
    response = await _model.ainvoke([{
        "role": "user",
        "content": CLASSIFY_SYSTEM + f"\n\nReply text:\n{reply_text[:1000]}"
    }])

    try:
        classification = json.loads(response.content)
    except json.JSONDecodeError:
        log.error("node.reply_handler.parse_error", content=response.content[:200])
        classification = {"status": "follow_up", "meeting_booked": False, "summary": "parse_error"}

    status = classification.get("status", "follow_up")
    meeting_booked = bool(classification.get("meeting_booked", False))

    # Log to HubSpot
    await log_activity(
        lead_id=lead_id,
        action=f"reply_received_touch_{touch}",
        metadata={
            "reply_status": status,
            "meeting_booked": meeting_booked,
            "summary": classification.get("summary", ""),
            "reply_preview": reply_text[:200],
        }
    )

    # Update HubSpot lead status if interested
    if status == "interested":
        from tools.hubspot import upsert_contact
        await upsert_contact({**state, "hs_lead_status": "OPEN_DEAL"})

    log.info(
        "node.reply_handler.classified",
        lead_id=lead_id,
        status=status,
        meeting_booked=meeting_booked,
    )

    return {
        "reply_raw": reply_text,
        "reply_status": status,
        "meeting_booked": meeting_booked,
    }
