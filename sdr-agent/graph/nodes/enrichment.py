"""
Enrichment node — parallel company enrichment + real-time signal grounding.
Populates: signals, firmographics, email_verified.
"""
from __future__ import annotations
import asyncio, structlog
from graph.state import SDRState
from tools.clearbit import get_firmographics
from tools.tavily_search import search

log = structlog.get_logger()


def _extract_funding_signal(results: list[dict]) -> str | None:
    """Pull the most relevant funding mention from search results."""
    funding_keywords = ["raised", "series", "funding", "million", "billion", "seed", "round"]
    for r in results:
        content = r.get("content", "").lower()
        title = r.get("title", "")
        if any(kw in content for kw in funding_keywords):
            # Return a clean 1-2 sentence summary
            sentences = r.get("content", "").split(". ")
            relevant = [s for s in sentences if any(kw in s.lower() for kw in funding_keywords)]
            if relevant:
                return relevant[0].strip()[:250]
    return None


def _extract_hiring_signals(results: list[dict]) -> list[str]:
    """Extract leadership/sales roles being hired for."""
    leadership_keywords = [
        "VP of Sales", "Head of Sales", "Director of Sales",
        "VP of Marketing", "Head of Marketing", "Chief Revenue",
        "VP of Growth", "Director of Revenue",
    ]
    found = set()
    for r in results:
        content = r.get("content", "")
        for kw in leadership_keywords:
            if kw.lower() in content.lower():
                found.add(kw)
    return list(found)[:3]


async def run(state: SDRState) -> dict:
    """Enrich lead with firmographics and real-time signals (parallel)."""
    company = state["company"]
    domain = state["domain"]
    log.info("node.enrich.start", company=company, domain=domain)

    # All three run simultaneously — don't pay 3× latency
    firmographics_task = get_firmographics(domain)
    funding_task = search(f"{company} funding raised investment round 2024 2025", max_results=4)
    hiring_task = search(f"{company} hiring VP director head of sales marketing growth", max_results=4)

    firmographics, funding_results, hiring_results = await asyncio.gather(
        firmographics_task,
        funding_task,
        hiring_task,
        return_exceptions=True,   # don't fail the whole pipeline if one errors
    )

    # Handle partial failures gracefully
    if isinstance(firmographics, Exception):
        log.warning("node.enrich.clearbit_failed", error=str(firmographics))
        firmographics = {}
    if isinstance(funding_results, Exception):
        funding_results = []
    if isinstance(hiring_results, Exception):
        hiring_results = []

    funding_signal = _extract_funding_signal(funding_results)
    hiring_signal = _extract_hiring_signals(hiring_results)

    signals = {
        "recent_funding": funding_signal,
        "leadership_hiring": hiring_signal,
        "tech_stack": firmographics.get("tech", []),
        "employee_count": firmographics.get("employees"),
        "industry": firmographics.get("industry"),
    }

    # Consider email verified if Clearbit returned data
    email_verified = bool(firmographics)

    log.info(
        "node.enrich.complete",
        company=company,
        has_funding_signal=bool(funding_signal),
        hiring_signals=len(hiring_signal),
    )

    return {
        "firmographics": firmographics,
        "signals": signals,
        "email_verified": email_verified,
    }
