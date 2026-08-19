"""One-off script: capture a real llm_agents run producing a genuine reject-then-
approve narrative, as a step-event fixture for the dashboard's Simulated button
to replay (ticket #7). Real OpenRouter calls -- run deliberately, not on every
test run.

    .venv/bin/python capture_transcript.py

Neither a stark price/carbon dominance (the real Analyst picks the objectively
best option immediately -- confirmed via live capture) nor an invisible hard
rule (the real Analyst/Reviewer only see min-gap-compliant candidates now that
llm_agents.py filters correctly -- see design/SPEC.md) reliably forces a
rejection. This seed instead creates a genuine Pareto frontier -- two
within-cap options where neither dominates (one cheaper, one cleaner, with a
close-enough cost-per-tonne trade-off) -- so the Analyst's pick and the
Reviewer's independent judgment can genuinely disagree, same as CONTEXT.md's
own "cheaper option exists but is carbon-heavy" scenario.
"""

import json
from datetime import date
from pathlib import Path

from decision import DayForecast, decide_day
from llm_agents import llm_analyst, llm_reviewer

FIXTURE_PATH = Path("fixtures/simulated_transcript.json")


def _seed_forecast_with_genuine_dilemma(day: date) -> DayForecast:
    """Two within-cap options, neither dominating: 02:00-06:00 is cheaper but
    carbon-heavier; 10:00-14:00 costs a modest premium for meaningfully lower
    carbon, at a cost-per-tonne (~£571) that's a real, arguable call rather than
    an obvious win either way."""
    prices = [30.0] * 48
    carbon = [200.0] * 48
    for i in range(0, 8):  # 00:00-04:00: cheaper, higher carbon
        prices[i] = 22.0
        carbon[i] = 150.0
    for i in range(20, 28):  # 10:00-14:00: modest premium, meaningfully cleaner
        prices[i] = 26.0
        carbon[i] = 80.0
    return DayForecast(day=day, prices=prices, carbon=carbon)


def main() -> None:
    day = date.today()
    forecast = _seed_forecast_with_genuine_dilemma(day)
    events: list[dict] = []

    rec = decide_day(forecast, llm_analyst, llm_reviewer, last_window_end=None, on_step=events.append)

    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(json.dumps(events, indent=2))
    print(f"Captured {len(events)} step events to {FIXTURE_PATH}")
    print(f"Final status: {rec.status} (replanned={rec.replanned})")


if __name__ == "__main__":
    main()
