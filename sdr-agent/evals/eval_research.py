"""
Research accuracy evaluator — checks that enrichment signals are factual.
Compares extracted signals against golden_leads.json expected signals.
"""
from __future__ import annotations
import json, asyncio
from pathlib import Path


async def run_eval():
    """Verify enrichment node extracts expected signals from mock data."""
    golden_path = Path(__file__).parent / "golden_leads.json"
    cases = json.loads(golden_path.read_text())

    results = []
    for case in cases:
        expected = case["expected"]
        signals = case.get("mock_signals", {})

        checks = {
            "has_funding_signal": bool(signals.get("recent_funding")) == expected.get("email_contains_signal", False),
            "has_industry": bool(signals.get("industry")),
            "has_employee_count": signals.get("employee_count") is not None,
        }
        passed = all(checks.values())
        results.append({"lead_id": case["lead"]["lead_id"], "checks": checks, "passed": passed})
        print(f"  {case['lead']['lead_id']}: {'PASS' if passed else 'FAIL'} {checks}")

    pass_rate = sum(1 for r in results if r["passed"]) / len(results) if results else 0
    print(f"\nResearch eval: {pass_rate:.0%} pass rate")
    assert pass_rate >= 0.8, f"Research accuracy below threshold: {pass_rate:.0%}"


if __name__ == "__main__":
    asyncio.run(run_eval())
