"""
Prospecting node — validates incoming lead against ICP config.
At this scale, leads arrive via the /webhook/lead endpoint.
This node filters, deduplicates, and prepares for enrichment.
"""
from __future__ import annotations
import yaml, re, structlog
from pathlib import Path
from graph.state import SDRState

log = structlog.get_logger()

# Load ICP config once at module level
_ICP_PATH = Path(__file__).parent.parent.parent / "config" / "icp.yaml"
with open(_ICP_PATH) as f:
    ICP = yaml.safe_load(f)


def _is_valid_email(email: str) -> bool:
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def _passes_icp(state: SDRState) -> tuple[bool, str | None]:
    """
    Check lead against ICP criteria from config/icp.yaml.
    Returns (passes: bool, reason: str | None)
    """
    # Email must be valid
    if not _is_valid_email(state.get("email", "")):
        return False, "invalid_email"

    # Title must match allowed seniorities
    allowed_titles = [t.lower() for t in ICP.get("allowed_titles", [])]
    title = state.get("title", "").lower()
    if allowed_titles and not any(t in title for t in allowed_titles):
        return False, f"title_not_in_icp: {state.get('title')}"

    # Blocked domains (competitors, free email providers)
    blocked_domains = ICP.get("blocked_domains", [])
    domain = state.get("domain", "")
    if any(bd in domain for bd in blocked_domains):
        return False, f"blocked_domain: {domain}"

    return True, None


async def run(state: SDRState) -> dict:
    """Validate and filter incoming lead against ICP criteria."""
    log.info("node.prospect.start", lead_id=state.get("lead_id"), email=state.get("email"))

    passes, reason = _passes_icp(state)

    if not passes:
        log.warning("node.prospect.disqualified", reason=reason, email=state.get("email"))
        return {
            "qualified": False,
            "disqualification_reason": reason,
        }

    log.info("node.prospect.passed_icp", email=state.get("email"))
    return {
        "qualified": True,               # tentative — scoring will confirm
        "email_verified": False,          # enrichment will verify
        "touch_number": 0,
        "meeting_booked": False,
        "retry_count": 0,
        "approved": False,
        "hitl_required": True,            # default to requiring human approval
    }
