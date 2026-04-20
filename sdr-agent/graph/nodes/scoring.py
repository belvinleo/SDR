"""
Scoring node — qualify leads using a weighted 3-factor model.
Uses Claude Haiku for structured JSON scoring output.
Final score = (fit × 0.5) + (intent × 0.3) + (urgency × 0.2)
Threshold: final_score >= 0.6 → qualified
"""
from __future__ import annotations
import json, os, structlog
from langchain_anthropic import ChatAnthropic
from graph.state import SDRState

log = structlog.get_logger()

QUALIFY_THRESHOLD = float(os.getenv("QUALIFY_THRESHOLD", "0.6"))

# Haiku is cheap and fast — perfect for structured classification
_model = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0)

SCORING_SYSTEM = """You are a B2B lead scoring engine. Score leads for sales outreach.

Output ONLY valid JSON, no markdown, no explanation:
{
  "fit_score": 0.0-1.0,
  "intent_score": 0.0-1.0,
  "urgency_score": 0.0-1.0,
  "reasoning": "one sentence max"
}

Scoring guide:
- fit_score: How well does this lead match our ICP? (title seniority, company size, industry)
- intent_score: Are there buying signals? (recent funding = high spend capacity, hiring sales = scaling, using competitor tech = pain)
- urgency_score: How time-sensitive is their need? (just raised funding = buy now, stable company = lower urgency)
"""


async def run(state: SDRState) -> dict:
    """Score the lead and determine if they qualify for outreach."""
    log.info("node.score.start", lead_id=state.get("lead_id"))

    prompt = f"""Score this B2B lead:

Name: {state.get('name')}
Title: {state.get('title')}
Company: {state.get('company')}
Industry: {state.get('firmographics', {}).get('industry', 'unknown')}
Employees: {state.get('firmographics', {}).get('employee_count', 'unknown')}

Signals:
- Recent funding: {state.get('signals', {}).get('recent_funding') or 'none found'}
- Leadership hiring: {state.get('signals', {}).get('leadership_hiring') or 'none found'}
- Tech stack: {state.get('signals', {}).get('tech_stack', [])}
"""

    response = await _model.ainvoke([
        {"role": "user", "content": SCORING_SYSTEM + "\n\n" + prompt}
    ])

    try:
        scores = json.loads(response.content)
    except json.JSONDecodeError:
        log.error("node.score.parse_error", content=response.content[:200])
        scores = {"fit_score": 0.5, "intent_score": 0.5, "urgency_score": 0.5, "reasoning": "parse_error"}

    fit = float(scores.get("fit_score", 0.5))
    intent = float(scores.get("intent_score", 0.5))
    urgency = float(scores.get("urgency_score", 0.5))

    final_score = (fit * 0.5) + (intent * 0.3) + (urgency * 0.2)
    qualified = final_score >= QUALIFY_THRESHOLD

    log.info(
        "node.score.complete",
        lead_id=state.get("lead_id"),
        final_score=round(final_score, 3),
        qualified=qualified,
    )

    return {
        "fit_score": fit,
        "intent_score": intent,
        "final_score": round(final_score, 3),
        "qualified": qualified,
        "disqualification_reason": None if qualified else f"score_too_low:{final_score:.2f}",
    }
