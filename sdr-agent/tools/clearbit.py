"""Clearbit wrapper — company firmographics enrichment."""
import os, httpx, structlog
from .base import retry_policy, ToolError

log = structlog.get_logger()
CLEARBIT_API_KEY = os.getenv("CLEARBIT_API_KEY")


@retry_policy
async def get_firmographics(domain: str) -> dict:
    """
    Enrich a company domain with Clearbit.
    Returns dict with keys: employees, industry, hq, country, tech (list)
    Falls back to empty dict if domain not found (don't fail the pipeline).
    """
    async with httpx.AsyncClient(
        timeout=15,
        auth=(CLEARBIT_API_KEY, ""),
    ) as client:
        try:
            resp = await client.get(
                f"https://company.clearbit.com/v2/companies/find",
                params={"domain": domain},
            )
            if resp.status_code == 404:
                log.warning("clearbit.not_found", domain=domain)
                return {}
            resp.raise_for_status()
            data = resp.json()
            
            return {
                "employees": data.get("metrics", {}).get("employees"),
                "industry": data.get("category", {}).get("industry"),
                "hq": data.get("geo", {}).get("city"),
                "country": data.get("geo", {}).get("country"),
                "tech": [t["name"] for t in data.get("tech", [])[:10]],
            }
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 422:
                return {}
            raise
