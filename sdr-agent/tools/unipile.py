"""Unipile wrapper — LinkedIn message execution."""
import os, httpx, structlog
from .base import retry_policy, ToolError

log = structlog.get_logger()
UNIPILE_API_KEY = os.getenv("UNIPILE_API_KEY")
UNIPILE_ACCOUNT_ID = os.getenv("UNIPILE_ACCOUNT_ID")
BASE_URL = "https://api.unipile.com:13465/api/v1"

HEADERS = {
    "X-API-KEY": UNIPILE_API_KEY,
    "Content-Type": "application/json",
}


@retry_policy
async def send_linkedin_message(
    linkedin_url: str,
    message: str,
    lead_id: str,
) -> str:
    """
    Send a LinkedIn connection request + message via Unipile.
    Returns the Unipile chat_id as thread_id.
    """
    async with httpx.AsyncClient(timeout=30, headers=HEADERS) as client:
        resp = await client.post(
            f"{BASE_URL}/chats",
            json={
                "account_id": UNIPILE_ACCOUNT_ID,
                "attendees_ids": [linkedin_url],
                "text": message,
            }
        )
        resp.raise_for_status()
        chat_id = resp.json().get("id", lead_id)
        log.info("unipile.send_message", linkedin_url=linkedin_url, chat_id=chat_id)
        return str(chat_id)


async def check_reply(thread_id: str) -> dict | None:
    """Check for a reply in a LinkedIn conversation."""
    async with httpx.AsyncClient(timeout=15, headers=HEADERS) as client:
        resp = await client.get(f"{BASE_URL}/chats/{thread_id}/messages")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        messages = resp.json().get("items", [])
        # Return the last message if it's from the prospect (not us)
        for msg in reversed(messages):
            if msg.get("sender_id") != UNIPILE_ACCOUNT_ID:
                return {"text": msg.get("text", ""), "from": msg.get("sender_id")}
        return None
