"""Real Analyst/Reviewer, calling OpenRouter's OpenAI-compatible chat completions
endpoint. Each is a single structured completion, not a tool-calling loop -- the
orchestration (decision.py) already fetches data and runs check_rules() in plain
code, so these just receive pre-prepared data and return a parsed structured
response. Drop-in replacement for simulate.py's heuristic stand-ins, matching
decision.py's Analyst/Reviewer interfaces exactly (see #2, #5).
"""

import json
import os
import re
from datetime import datetime

from dotenv import load_dotenv
from openai import OpenAI

from live import RollingForecast, rolling_window_start
from rules import MIN_GAP_HOURS, ProposedWindow, price_cap
from windows import candidate_windows, window_start as day_window_start

load_dotenv()

ANALYST_MODEL = "anthropic/claude-opus-5"
REVIEWER_MODEL = "anthropic/claude-sonnet-5"

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.environ["OPENROUTER_API_KEY"]
        _client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
    return _client


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"no JSON object found in model response: {text!r}")
    return json.loads(match.group(0))


def _complete(model: str, system: str, user: str) -> str:
    response = _get_client().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return response.choices[0].message.content or ""


def _slot_start(forecast, i: int) -> datetime:
    """Works for either a single-day DayForecast (decision.py) or a
    now-anchored, possibly cross-midnight RollingForecast (live.py) -- the
    two seams sharing this Analyst/Reviewer via decide_day()'s generic
    interface."""
    if isinstance(forecast, RollingForecast):
        return rolling_window_start(forecast, i)
    return day_window_start(forecast.day, i)


def _forecast_label(forecast) -> str:
    if isinstance(forecast, RollingForecast):
        return f"the forecast horizon starting {forecast.start.isoformat()}"
    return forecast.day.isoformat()


def _format_candidates(forecast, last_window_end=None) -> str:
    lines = []
    for i, price, carb in candidate_windows(forecast.prices, forecast.carbon):
        start = _slot_start(forecast, i)
        if last_window_end is not None:
            gap_hours = (start - last_window_end).total_seconds() / 3600
            if gap_hours < MIN_GAP_HOURS:
                continue  # already ineligible on the min-gap rule -- don't offer it as a candidate
        # Full ISO datetime, not bare "HH:MM" -- a rolling horizon can span
        # midnight into tomorrow, and the Analyst echoes this exact string
        # back rather than us reconstructing a date from a truncated time.
        lines.append(f"- start {start.isoformat()}, avg price {price:.2f}p/kWh, avg carbon {carb:.0f}gCO2/kWh")
    return "\n".join(lines)


def llm_analyst(forecast, reason: str | None) -> tuple[ProposedWindow, str]:
    candidates_text = _format_candidates(forecast, forecast.last_window_end)
    cap = price_cap(forecast.prices)

    if reason is None:
        instruction = (
            "Propose the single best 4-hour charge window for tonight's grid-scale battery. "
            "Weigh price against carbon intensity and explain the trade-off in plain language."
        )
    else:
        instruction = (
            f'Your previous proposal was sent back with this reason: "{reason}". '
            "Propose a revised 4-hour charge window that addresses it, and explain your reasoning."
        )

    gap_note = (
        " Windows within the required minimum gap since the last approved charge window have "
        "already been excluded from the candidate list below."
        if forecast.last_window_end is not None else ""
    )
    system = (
        "You are the Analyst in a grid battery dispatch system. Given a list of candidate "
        f"4-hour charge windows for {_forecast_label(forecast)} (price cap: {cap:.2f}p/kWh), "
        f"pick one and explain the trade-off.{gap_note} Respond with ONLY a JSON object: "
        '{"start": "<the exact start value copied from the chosen candidate line>", '
        '"avg_price": <number>, "explanation": "<plain language>"}.'
    )
    user = f"{instruction}\n\nCandidate windows:\n{candidates_text}"

    content = _complete(ANALYST_MODEL, system, user)
    data = _extract_json(content)

    start = datetime.fromisoformat(data["start"])
    window = ProposedWindow(start=start, avg_price=float(data["avg_price"]))
    return window, str(data["explanation"])


def llm_reviewer(window: ProposedWindow, forecast) -> tuple[bool, str]:
    candidates_text = _format_candidates(forecast, forecast.last_window_end)
    cap = price_cap(forecast.prices)

    gap_note = (
        " Windows within the required minimum gap since the last approved charge window have "
        "already been excluded from the candidate list, so every listed alternative is a fair comparison."
        if forecast.last_window_end is not None else ""
    )
    system = (
        "You are the Reviewer in a grid battery dispatch system. The hard rules (price cap, "
        "min-gap) already passed -- your job is soft judgment only: is this a genuinely good "
        f"price/carbon trade-off, or does a clearly better within-cap alternative exist?{gap_note} "
        f"Price cap for {_forecast_label(forecast)}: {cap:.2f}p/kWh. "
        'Respond with ONLY a JSON object: {"approved": <true|false>, "reasoning": "<plain language>"}.'
    )
    user = (
        f"Proposed window: start {window.start.isoformat()}, avg price {window.avg_price:.2f}p/kWh.\n\n"
        f"All candidate windows for context:\n{candidates_text}"
    )

    content = _complete(REVIEWER_MODEL, system, user)
    data = _extract_json(content)
    return bool(data["approved"]), str(data["reasoning"])
