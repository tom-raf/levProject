"""Dashboard shell + Live/Simulated run routes. GET / serves the
blueprint-styled page recreating design/design_handoff_dashboard/'s mockup.

SSE note: design/PLAN.md and design/SPEC.md describe these as POST routes
consumed via `EventSource` -- but the browser's native EventSource only ever
sends GET, it can't POST. The frontend uses fetch() + a streamed response
reader instead, which is the standard workaround; the wire format is still
plain SSE (`data: {...}\\n\\n`) and the routes are still POST, matching the
locked design's intent."""

import json
import queue
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, Response, render_template

from decision import decide_day
from live import build_rolling_forecast
from llm_agents import llm_analyst, llm_reviewer
from rules import CHARGE_DURATION_HOURS
from tools import get_carbon_forecast, get_price_forecast

app = Flask(__name__)

SIMULATED_FIXTURE_PATH = Path("fixtures/simulated_transcript.json")
STEP_DELAY_SECONDS = 0.6

# In-memory session history (SPEC.md: "lost on process restart -- acceptable
# for a local demo tool"). Ticket #12 reads this for Live's min-gap lookup;
# Simulated appends to it but never reads from it (PLAN.md decision 7).
RUN_HISTORY: list[dict] = []


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _last_approved_live_window_end() -> datetime | None:
    """The end of the most recently *approved* Live-type run this session, per
    PLAN.md decision 7. Unresolved Live runs don't count (never validated as
    safe), and Simulated runs are invisible to this lookup regardless of where
    they fall in RUN_HISTORY's order -- filtering on type=="live" already
    achieves that without any extra bookkeeping."""
    for entry in reversed(RUN_HISTORY):
        if entry["type"] == "live" and entry["status"] == "approved":
            return datetime.fromisoformat(entry["window_start"]) + timedelta(hours=CHARGE_DURATION_HOURS)
    return None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/run/simulated", methods=["POST"])
def run_simulated():
    fixture = json.loads(SIMULATED_FIXTURE_PATH.read_text())
    forecast = fixture["forecast"]
    events = fixture["events"]

    def stream():
        yield _sse({"step": "forecast", **forecast})
        for event in events:
            time.sleep(STEP_DELAY_SECONDS)
            yield _sse(event)

        final = next(e for e in events if e["step"] == "final")
        RUN_HISTORY.append({
            "type": "simulated",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": final["status"],
            "window_start": final["window"]["start"],
        })

    return Response(stream(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.route("/run/live", methods=["POST"])
def run_live():
    now = datetime.now(timezone.utc)
    today, tomorrow = now.date(), now.date() + timedelta(days=1)

    today_prices, today_carbon = get_price_forecast(today), get_carbon_forecast(today)
    try:
        tomorrow_prices, tomorrow_carbon = get_price_forecast(tomorrow), get_carbon_forecast(tomorrow)
    except Exception:
        # Not yet published (Octopus publishes ~1 day ahead, roughly 4pm-8pm UK
        # time) or a live/cache fetch failure -- an empty/thin horizon is an
        # accepted outcome here (design/PLAN.md), not an error.
        tomorrow_prices, tomorrow_carbon = None, None

    forecast = build_rolling_forecast(now, today_prices, today_carbon, tomorrow_prices, tomorrow_carbon)
    last_window_end = _last_approved_live_window_end()

    def stream():
        yield _sse({
            "step": "forecast", "start": forecast.start.isoformat(),
            "prices": forecast.prices, "carbon": forecast.carbon,
            "last_window_end": last_window_end.isoformat() if last_window_end else None,
        })

        events: queue.Queue = queue.Queue()

        def worker():
            try:
                decide_day(forecast, llm_analyst, llm_reviewer, last_window_end, on_step=events.put)
            except Exception as exc:
                # Without this, a crash here (e.g. a malformed LLM response) would leave the
                # sentinel below unqueued -- the generator's events.get() would block forever
                # and the browser would hang on RUNNING... with no way to recover but a reload.
                events.put({"step": "error", "message": str(exc)})
            finally:
                events.put(None)  # sentinel: worker has finished, one way or another

        threading.Thread(target=worker, daemon=True).start()

        final = None
        while (event := events.get()) is not None:
            if event["step"] == "final":
                final = event
            yield _sse(event)

        if final is not None:
            RUN_HISTORY.append({
                "type": "live",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": final["status"],
                "window_start": final["window"]["start"],
            })

    return Response(stream(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache"})


if __name__ == "__main__":
    app.run(debug=True, port=5050)
