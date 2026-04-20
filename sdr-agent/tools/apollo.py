"""Apollo.io wrapper — prospect search and ICP filtering."""
import os, uuid, httpx, structlog
from .base import retry_policy, ToolError

log = structlog.get_logger()
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY")
BASE_URL = "https://api.apollo.io/v1"


@retry_policy
async def search_leads(icp: dict, per_page: int = 25) -> list[dict]:
    """
    Search Apollo for leads matching ICP criteria.
    
    icp dict keys (all optional):
      - titles: list[str]       e.g. ["VP of Sales", "Head of Marketing"]
      - seniorities: list[str]  e.g. ["vp", "director", "manager"]
      - industries: list[str]   e.g. ["Software", "SaaS"]
      - employee_ranges: list   e.g. ["11,50", "51,200"]
      - locations: list[str]    e.g. ["United States", "Canada"]
    
    Returns list of lead dicts with keys:
      lead_id, email, name, first_name, last_name, company, domain,
      title, linkedin_url
    """
    async with httpx.AsyncClient(timeout=30) as client:
        payload = {
            "api_key": APOLLO_API_KEY,
            "per_page": per_page,
            "person_titles": icp.get("titles", []),
            "person_seniorities": icp.get("seniorities", []),
            "organization_industry_tag_ids": [],
            "organization_num_employees_ranges": icp.get("employee_ranges", []),
            "person_locations": icp.get("locations", []),
            "contact_email_status": ["verified"],
        }
        resp = await client.post(f"{BASE_URL}/mixed_people/search", json=payload)
        resp.raise_for_status()
        
        people = resp.json().get("people", [])
        leads = []
        for p in people:
            org = p.get("organization", {}) or {}
            leads.append({
                "lead_id": str(uuid.uuid4()),
                "email": p.get("email", ""),
                "name": p.get("name", ""),
                "first_name": p.get("first_name", ""),
                "last_name": p.get("last_name", ""),
                "company": org.get("name", ""),
                "domain": org.get("primary_domain", ""),
                "title": p.get("title", ""),
                "linkedin_url": p.get("linkedin_url"),
            })
        
        log.info("apollo.search_leads", count=len(leads))
        return leads
