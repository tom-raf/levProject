"""Dashboard shell + Simulated run route. GET / serves the blueprint-styled
page recreating design/design_handoff_dashboard/'s mockup. POST /run/live
(ticket #11) still to come.

SSE note: design/PLAN.md and design/SPEC.md describe these as POST routes
consumed via `EventSource` -- but the browser's native EventSource only ever
sends GET, it can't POST. The frontend uses fetch() + a streamed response
reader instead, which is the standard workaround; the wire format is still
plain SSE (`data: {...}\\n\\n`) and the routes are still POST, matching the
locked design's intent."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, Response, render_template

app = Flask(__name__)

SIMULATED_FIXTURE_PATH = Path("fixtures/simulated_transcript.json")
STEP_DELAY_SECONDS = 0.6

# In-memory session history (SPEC.md: "lost on process restart -- acceptable
# for a local demo tool"). Ticket #12 reads this for Live's min-gap lookup;
# Simulated appends to it but never reads from it (PLAN.md decision 7).
RUN_HISTORY: list[dict] = []


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


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


if __name__ == "__main__":
    app.run(debug=True, port=5050)
