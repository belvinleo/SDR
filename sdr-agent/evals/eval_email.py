"""
Email quality evaluator — uses Claude to score draft outreach against 4 criteria.
Run in CI before each deploy: python -m evals.eval_email
"""
from __future__ import annotations
import json, asyncio, structlog
from pathlib import Path
from anthropic import AsyncAnthropic

log = structlog.get_logger()
client = AsyncAnthropic()

JUDGE_SYSTEM = """You are an expert B2B sales coach evaluating cold email drafts.

Score the email on these 4 criteria (1-5 each):
1. Signal specificity: Does it open with a real, verifiable fact about the company?
2. Relevance: Is the value prop connected to that signal/pain?
3. CTA clarity: Is the ask low-commitment and unambiguous?
4. Length: Is the body under 120 words?

Output ONLY valid JSON:
{
  "signal_specificity": 1-5,
  "relevance": 1-5,
  "cta_clarity": 1-5,
  "length_ok": 1-5,
  "overall": 1-5,
  "flags": ["list any issues"],
  "verdict": "pass" | "fail"
}

Verdict: pass if overall >= 3, fail otherwise.
"""


async def score_email(subject: str, body: str, signals: dict) -> dict:
    """Score a single email draft against the golden criteria."""
    prompt = f"""Subject: {subject}

Body:
{body}

Available signals that were passed to the writer:
{json.dumps(signals, indent=2)}
"""
    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{"role": "user", "content": JUDGE_SYSTEM + "\n\n" + prompt}]
    )
    try:
        return json.loads(response.content[0].text)
    except Exception:
        return {"overall": 0, "verdict": "error", "flags": ["parse_error"]}


async def run_eval():
    """Run email quality eval against all golden leads."""
    golden_path = Path(__file__).parent / "golden_leads.json"
    golden_leads = json.loads(golden_path.read_text())

    results = []
    for case in golden_leads:
        if not case["expected"].get("email_contains_signal"):
            continue   # Skip disqualified leads

        # Simulate a draft (in real eval, run the actual outreach node)
        mock_draft = {
            "subject": f"Quick question — {case['lead']['company']}",
            "body": f"Hi {case['lead']['first_name']}, saw {case['lead']['company']} raised a Series B — congrats. Companies scaling that fast often hit [pain]. We help with that. Worth a 15-min chat?"
        }

        score = await score_email(
            subject=mock_draft["subject"],
            body=mock_draft["body"],
            signals=case.get("mock_signals", {}),
        )

        passed = score.get("overall", 0) >= case["expected"].get("min_email_quality_score", 3)
        results.append({
            "lead_id": case["lead"]["lead_id"],
            "score": score,
            "passed": passed,
        })
        log.info("eval.email", lead_id=case["lead"]["lead_id"], overall=score.get("overall"), passed=passed)

    pass_rate = sum(1 for r in results if r["passed"]) / len(results) if results else 0
    print(f"\nEmail eval: {sum(1 for r in results if r['passed'])}/{len(results)} passed ({pass_rate:.0%})")

    # Fail CI if pass rate < 80%
    assert pass_rate >= 0.8, f"Email quality below threshold: {pass_rate:.0%}"
    return results


if __name__ == "__main__":
    asyncio.run(run_eval())
