"""Instantly.ai wrapper — cold email send and tracking."""
import os, httpx, structlog
from .base import retry_policy, ToolError

log = structlog.get_logger()
INSTANTLY_API_KEY = os.getenv("INSTANTLY_API_KEY")
INSTANTLY_CAMPAIGN_ID = os.getenv("INSTANTLY_CAMPAIGN_ID")
BASE_URL = "https://api.instantly.ai/api/v1"


@retry_policy
async def send_email(
    to_email: str,
    to_name: str,
    subject: str,
    body: str,
    lead_id: str,
) -> str:
    """
    Add a lead to an Instantly campaign and trigger immediate send.
    Returns thread_id (Instantly lead ID string).
    """
    async with httpx.AsyncClient(timeout=20) as client:
        # Step 1: Add lead to campaign
        add_resp = await client.post(
            f"{BASE_URL}/lead/add",
            json={
                "api_key": INSTANTLY_API_KEY,
                "campaign_id": INSTANTLY_CAMPAIGN_ID,
                "skip_if_in_workspace": True,
                "leads": [{
                    "email": to_email,
                    "first_name": to_name.split()[0],
                    "last_name": " ".join(to_name.split()[1:]),
                    "custom_variables": {
                        "sdr_lead_id": lead_id,
                        "custom_subject": subject,
                        "custom_body": body,
                    }
                }]
            }
        )
        add_resp.raise_for_status()
        result = add_resp.json()
        thread_id = result.get("leads", [{}])[0].get("id", lead_id)
        log.info("instantly.send_email", to=to_email, thread_id=thread_id)
        return str(thread_id)


async def check_reply(thread_id: str) -> dict | None:
    """
    Poll for a reply to a given thread.
    Returns {"text": str, "from": str} or None if no reply yet.
    """
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{BASE_URL}/lead/get",
            params={"api_key": INSTANTLY_API_KEY, "id": thread_id},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        reply_text = data.get("reply_text")
        if reply_text:
            return {"text": reply_text, "from": data.get("email", "")}
        return None
