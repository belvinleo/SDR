"""HubSpot CRM wrapper — contact and activity management."""
import os, httpx, structlog
from .base import retry_policy, ToolError

log = structlog.get_logger()
HUBSPOT_API_KEY = os.getenv("HUBSPOT_API_KEY")
BASE_URL = "https://api.hubapi.com"
HEADERS = {
    "Authorization": f"Bearer {HUBSPOT_API_KEY}",
    "Content-Type": "application/json",
}


@retry_policy
async def upsert_contact(state: dict) -> str:
    """
    Create or update a HubSpot contact from SDRState.
    Returns the HubSpot contact ID.
    """
    async with httpx.AsyncClient(timeout=20, headers=HEADERS) as client:
        properties = {
            "email": state.get("email"),
            "firstname": state.get("first_name"),
            "lastname": state.get("last_name"),
            "company": state.get("company"),
            "jobtitle": state.get("title"),
            "linkedinbio": state.get("linkedin_url", ""),
            "hs_lead_status": "IN_PROGRESS",
            "sdr_fit_score": str(state.get("final_score", 0)),
            "sdr_touch_number": str(state.get("touch_number", 0)),
        }
        resp = await client.post(
            f"{BASE_URL}/crm/v3/objects/contacts/batch/upsert",
            json={"inputs": [{"idProperty": "email", "properties": properties}]},
        )
        resp.raise_for_status()
        contact_id = resp.json()["results"][0]["id"]
        log.info("hubspot.upsert_contact", email=state.get("email"), contact_id=contact_id)
        return contact_id


@retry_policy
async def log_activity(lead_id: str, action: str, metadata: dict) -> None:
    """Log a note/activity against the contact in HubSpot."""
    async with httpx.AsyncClient(timeout=15, headers=HEADERS) as client:
        body = f"SDR Agent — {action}\n\n" + "\n".join(
            f"{k}: {v}" for k, v in metadata.items()
        )
        resp = await client.post(
            f"{BASE_URL}/crm/v3/objects/notes",
            json={"properties": {"hs_note_body": body, "hs_timestamp": "now"}},
        )
        resp.raise_for_status()
        log.info("hubspot.log_activity", lead_id=lead_id, action=action)
