"""One-off script: capture a real llm_agents run against real fetched
price/carbon data as a step-event fixture for the dashboard's Simulated button
to replay (ticket #7). Real OpenRouter calls plus real API fetches -- run
deliberately, not on every test run.

    .venv/bin/python capture_transcript.py

Snapshots tomorrow's forecast (Octopus Agile publishes it roughly 4-8pm UK
time) via the same tools.py fetch used by a real Live run, so the Simulated
button replays an actual real-world day rather than a hand-crafted seed.
Earlier attempts at a hand-crafted "genuine dilemma" seed are gone -- see git
history if that's ever needed again.
"""

import json
from datetime import date, timedelta
from pathlib import Path

from decision import DayForecast, decide_day
from llm_agents import llm_analyst, llm_reviewer
from tools import get_carbon_forecast, get_price_forecast

FIXTURE_PATH = Path("fixtures/simulated_transcript.json")


def main() -> None:
    day = date.today() + timedelta(days=1)
    forecast = DayForecast(day=day, prices=get_price_forecast(day), carbon=get_carbon_forecast(day))
    events: list[dict] = []

    rec = decide_day(forecast, llm_analyst, llm_reviewer, last_window_end=None, on_step=events.append)

    fixture = {
        "forecast": {"day": forecast.day.isoformat(), "prices": forecast.prices, "carbon": forecast.carbon},
        "events": events,
    }
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(json.dumps(fixture, indent=2))
    print(f"Captured {len(events)} step events to {FIXTURE_PATH}")
    print(f"Final status: {rec.status} (replanned={rec.replanned})")


if __name__ == "__main__":
    main()
