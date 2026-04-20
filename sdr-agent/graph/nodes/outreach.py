"""
Outreach node — Claude Sonnet writes signal-grounded cold outreach.
Generates: draft_subject, draft_body, channel, confidence.
Confidence >= AUTO_APPROVE_THRESHOLD → auto-send (no HITL).
"""
from __future__ import annotations
import json, os, yaml, structlog
from pathlib import Path
from langchain_anthropic import ChatAnthropic
from graph.state import SDRState

log = structlog.get_logger()

AUTO_APPROVE_THRESHOLD = float(os.getenv("AUTO_APPROVE_THRESHOLD", "0.85"))

# Sonnet for drafting — quality is the competitive edge
_model = ChatAnthropic(model="claude-sonnet-4-5", temperature=0.7)

# Load sequence templates
_SEQ_PATH = Path(__file__).parent.parent.parent / "config" / "sequences.yaml"
with open(_SEQ_PATH) as f:
    SEQUENCES = yaml.safe_load(f)

EMAIL_SYSTEM = """You are an elite SDR known for writing cold emails that get replies.

Your emails:
1. Open with ONE specific, verifiable signal about the prospect (funding round, a leadership hire, news item)
2. Connect that signal to a pain it creates OR a goal it implies
3. Present our value prop in ONE sentence tied to that pain/goal
4. End with a low-commitment CTA: a yes/no question OR offer of a 15-min call

Hard rules:
- Subject line: max 8 words, no clickbait, no emoji
- Body: max 120 words
- Never say: "I hope this finds you well", "reaching out because", "I wanted to"
- Never mention you used AI to write this
- Write in first person as if from a human SDR

Output ONLY valid JSON:
{
  "subject": "...",
  "body": "...",
  "confidence": 0.0-1.0,
  "confidence_reason": "why this score"
}

Confidence guide:
- 0.9+: Strong signal found, high personalization, clear pain/CTA match
- 0.7-0.9: Moderate signal, good personalization
- <0.7: Weak signal, generic draft — needs human review
"""

LINKEDIN_SYSTEM = """You are an elite SDR writing LinkedIn connection request messages.

Rules:
- Max 200 characters (LinkedIn connection note limit)
- Reference ONE specific thing about them (role, company news, shared connection)
- No pitch in the connection request — just a genuine reason to connect
- Sound human, not automated

Output ONLY valid JSON:
{
  "body": "...",
  "confidence": 0.0-1.0,
  "confidence_reason": "why this score"
}
"""


def _select_channel(state: SDRState) -> str:
    """Select outreach channel based on touch number and available data."""
    touch = state.get("touch_number", 0)
    has_linkedin = bool(state.get("linkedin_url"))
    has_email = bool(state.get("email"))

    # Touch pattern: email → linkedin → email → linkedin...
    if touch % 2 == 0 and has_email:
        return "email"
    if has_linkedin:
        return "linkedin"
    return "email"


def _build_prompt(state: SDRState, touch: int) -> str:
    signals = state.get("signals", {})
    firmographics = state.get("firmographics", {})
    
    # Pick tone template from sequences config based on touch number
    tone = SEQUENCES.get("touch_tones", {}).get(str(touch), "consultative")

    return f"""Write cold outreach for this lead. Touch #{touch + 1} of 8.

LEAD:
Name: {state.get('name')} ({state.get('first_name')})
Title: {state.get('title')}
Company: {state.get('company')}
Industry: {firmographics.get('industry', 'unknown')}
Employees: {firmographics.get('employee_count', 'unknown')}
LinkedIn: {state.get('linkedin_url', 'N/A')}

SIGNALS (use the strongest one as your opener):
- Recent funding: {signals.get('recent_funding') or 'none found'}
- Leadership hiring: {signals.get('leadership_hiring') or 'none found'}
- Tech stack: {signals.get('tech_stack', [])}

TONE: {tone}
ICP fit score: {state.get('fit_score', 0):.2f}
Intent score: {state.get('intent_score', 0):.2f}

If no strong signal exists, use their title + company growth stage as the hook.
"""


async def run(state: SDRState) -> dict:
    """Generate personalized outreach draft using Claude Sonnet."""
    touch = state.get("touch_number", 0)
    channel = _select_channel(state)
    log.info("node.outreach.start", lead_id=state.get("lead_id"), touch=touch, channel=channel)

    system = EMAIL_SYSTEM if channel == "email" else LINKEDIN_SYSTEM
    prompt = _build_prompt(state, touch)

    response = await _model.ainvoke([
        {"role": "user", "content": system + "\n\n" + prompt}
    ])

    try:
        result = json.loads(response.content)
    except json.JSONDecodeError:
        log.error("node.outreach.parse_error", content=response.content[:300])
        result = {
            "body": response.content[:500],
            "confidence": 0.3,
            "confidence_reason": "parse_error_fallback"
        }

    confidence = float(result.get("confidence", 0.5))
    hitl_required = confidence < AUTO_APPROVE_THRESHOLD

    log.info(
        "node.outreach.complete",
        lead_id=state.get("lead_id"),
        channel=channel,
        confidence=confidence,
        hitl_required=hitl_required,
    )

    return {
        "channel": channel,
        "draft_subject": result.get("subject"),      # None for LinkedIn
        "draft_body": result.get("body", ""),
        "confidence": confidence,
        "hitl_required": hitl_required,
        "approved": False,                            # always start unapproved
    }
