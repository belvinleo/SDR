"""
Redis working memory — sequence state for active leads.
Stores: touch history, last sent date, sequence position, thread IDs.
TTL: 90 days per lead key (auto-expire cold leads).
"""
from __future__ import annotations
import json, os, structlog
from datetime import datetime, timezone
from redis.asyncio import Redis, from_url

log = structlog.get_logger()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
KEY_TTL_SECONDS = 90 * 24 * 3600   # 90 days

_redis: Redis | None = None


async def get_client() -> Redis:
    """Lazily initialize and return the Redis client."""
    global _redis
    if _redis is None:
        _redis = await from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    return _redis


def _lead_key(lead_id: str) -> str:
    return f"sdr:lead:{lead_id}"


async def record_touch(
    lead_id: str,
    touch_number: int,
    channel: str,
    thread_id: str | None,
    sent_at: datetime,
) -> None:
    """Record a sent touch in Redis. Appends to the lead's touch history list."""
    r = await get_client()
    key = _lead_key(lead_id)

    touch_record = json.dumps({
        "touch_number": touch_number,
        "channel": channel,
        "thread_id": thread_id,
        "sent_at": sent_at.isoformat(),
    })

    pipe = r.pipeline()
    pipe.rpush(f"{key}:touches", touch_record)
    pipe.set(f"{key}:last_touch", touch_number)
    pipe.set(f"{key}:last_sent_at", sent_at.isoformat())
    if thread_id:
        pipe.set(f"{key}:thread_id", thread_id)
    pipe.expire(f"{key}:touches", KEY_TTL_SECONDS)
    pipe.expire(f"{key}:last_touch", KEY_TTL_SECONDS)
    pipe.expire(f"{key}:last_sent_at", KEY_TTL_SECONDS)
    await pipe.execute()

    log.info("redis.record_touch", lead_id=lead_id, touch=touch_number)


async def get_touch_history(lead_id: str) -> list[dict]:
    """Return all touch records for a lead."""
    r = await get_client()
    raw_touches = await r.lrange(f"{_lead_key(lead_id)}:touches", 0, -1)
    return [json.loads(t) for t in raw_touches]


async def get_last_touch(lead_id: str) -> int:
    """Return the index of the last sent touch, or -1 if none."""
    r = await get_client()
    val = await r.get(f"{_lead_key(lead_id)}:last_touch")
    return int(val) if val is not None else -1


async def mark_lead_complete(lead_id: str, status: str) -> None:
    """Mark a lead as complete (interested / stop). Sets final status key."""
    r = await get_client()
    key = _lead_key(lead_id)
    await r.set(f"{key}:status", status, ex=KEY_TTL_SECONDS)
    log.info("redis.lead_complete", lead_id=lead_id, status=status)


async def is_lead_active(lead_id: str) -> bool:
    """Return True if this lead has an active (non-complete) sequence."""
    r = await get_client()
    status = await r.get(f"{_lead_key(lead_id)}:status")
    return status is None or status == "active"


async def get_thread_id(lead_id: str) -> str | None:
    """Return the latest thread_id for this lead."""
    r = await get_client()
    return await r.get(f"{_lead_key(lead_id)}:thread_id")
