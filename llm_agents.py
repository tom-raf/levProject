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

from dotenv import load_dotenv
from openai import OpenAI

from rules import ProposedWindow, price_cap
from windows import candidate_windows, window_start

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


def _format_candidates(day, prices: list[float], carbon: list[float]) -> str:
    lines = []
    for i, price, carb in candidate_windows(prices, carbon):
        lines.append(f"- start {window_start(day, i):%H:%M}, avg price {price:.2f}p/kWh, avg carbon {carb:.0f}gCO2/kWh")
    return "\n".join(lines)


def llm_analyst(forecast, reason: str | None) -> tuple[ProposedWindow, str]:
    candidates_text = _format_candidates(forecast.day, forecast.prices, forecast.carbon)
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

    system = (
        "You are the Analyst in a grid battery dispatch system. Given a list of candidate "
        f"4-hour charge windows for {forecast.day.isoformat()} (price cap for today: {cap:.2f}p/kWh), "
        "pick one and explain the trade-off. Respond with ONLY a JSON object: "
        '{"start": "HH:MM", "avg_price": <number>, "explanation": "<plain language>"}.'
    )
    user = f"{instruction}\n\nCandidate windows:\n{candidates_text}"

    content = _complete(ANALYST_MODEL, system, user)
    data = _extract_json(content)

    hour, minute = (int(x) for x in data["start"].split(":"))
    start = window_start(forecast.day, 0).replace(hour=hour, minute=minute)
    window = ProposedWindow(start=start, avg_price=float(data["avg_price"]))
    return window, str(data["explanation"])


def llm_reviewer(window: ProposedWindow, forecast) -> tuple[bool, str]:
    candidates_text = _format_candidates(forecast.day, forecast.prices, forecast.carbon)
    cap = price_cap(forecast.prices)

    system = (
        "You are the Reviewer in a grid battery dispatch system. The hard rules (price cap, "
        "min-gap) already passed -- your job is soft judgment only: is this a genuinely good "
        f"price/carbon trade-off, or does a clearly better within-cap alternative exist? "
        f"Price cap for {forecast.day.isoformat()}: {cap:.2f}p/kWh. "
        'Respond with ONLY a JSON object: {"approved": <true|false>, "reasoning": "<plain language>"}.'
    )
    user = (
        f"Proposed window: start {window.start:%H:%M}, avg price {window.avg_price:.2f}p/kWh.\n\n"
        f"All candidate windows for context:\n{candidates_text}"
    )

    content = _complete(REVIEWER_MODEL, system, user)
    data = _extract_json(content)
    return bool(data["approved"]), str(data["reasoning"])
