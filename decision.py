"""Single-day decision core: propose -> check -> replan once -> approve/unresolved.

See CONTEXT.md for Analyst/Reviewer/Recommendation definitions and rules.py for
the hard constraints. Analyst and Reviewer are swappable callables so a real
model provider can be wired in without touching this logic.
"""

from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Callable, Literal

from rules import ProposedWindow, check_rules


@dataclass
class DayForecast:
    day: date
    prices: list[float]
    carbon: list[float]
    # Populated by decide_day() before calling analyst/reviewer, from its own
    # last_window_end parameter -- a single source of truth, not duplicated by
    # callers. Lets an Analyst/Reviewer implementation filter out candidates
    # that are known ineligible, rather than discovering it via rejection.
    last_window_end: datetime | None = None


@dataclass
class Recommendation:
    window: ProposedWindow
    explanation: str
    status: Literal["approved", "unresolved"]
    reviewer_reasoning: str
    replanned: bool


# Analyst: (forecast, prior_rejection_reason) -> (proposed window, plain-language explanation)
Analyst = Callable[[DayForecast, str | None], tuple[ProposedWindow, str]]

# Reviewer: (proposed window, forecast) -> (approved, plain-language reasoning)
# Only called when the hard rules already pass -- it exercises soft judgment only.
Reviewer = Callable[[ProposedWindow, DayForecast], tuple[bool, str]]


# A step event is a plain dict with a "step" key
# ("proposal" | "rule_check" | "reviewer_verdict" | "replan" | "final") plus
# step-specific, JSON-serializable fields. See CONTEXT.md for what each step
# represents; used to stream a Live run and to capture the Simulated fixture.
OnStep = Callable[[dict], None]


def _window_dict(window: ProposedWindow) -> dict:
    return {"start": window.start.isoformat(), "avg_price": window.avg_price}


def decide_day(
    forecast: DayForecast,
    analyst: Analyst,
    reviewer: Reviewer,
    last_window_end: datetime | None,
    on_step: OnStep | None = None,
) -> Recommendation:
    forecast = replace(forecast, last_window_end=last_window_end)

    def emit(event: dict) -> None:
        if on_step is not None:
            on_step(event)

    def attempt(attempt_num: int, prior_reason: str | None) -> tuple[ProposedWindow, str, bool, str]:
        window, explanation = analyst(forecast, prior_reason)
        emit({"step": "proposal", "attempt": attempt_num, "window": _window_dict(window), "explanation": explanation})

        violations = check_rules(window, forecast.prices, last_window_end)
        emit({"step": "rule_check", "attempt": attempt_num, "violations": violations})
        if violations:
            return window, explanation, False, "; ".join(violations)

        approved, reasoning = reviewer(window, forecast)
        emit({"step": "reviewer_verdict", "attempt": attempt_num, "approved": approved, "reasoning": reasoning})
        return window, explanation, approved, reasoning

    window, explanation, approved, reasoning = attempt(1, None)
    if approved:
        emit({
            "step": "final", "status": "approved", "window": _window_dict(window),
            "explanation": explanation, "reviewer_reasoning": reasoning, "replanned": False,
        })
        return Recommendation(window, explanation, "approved", reasoning, replanned=False)

    emit({"step": "replan", "attempt": 2, "reason": reasoning})
    # Each analyst() call is a fresh, stateless call (no memory of its own prior
    # answer) -- restate the rejected window itself, not just the rejection
    # reason, so a replanning analyst can reason about it correctly instead of
    # guessing what it previously proposed.
    prior_reason = f"{reasoning} (previously proposed: start {window.start.isoformat()}, avg_price {window.avg_price:.2f})"
    window, explanation, approved, reasoning = attempt(2, prior_reason)
    status: Literal["approved", "unresolved"] = "approved" if approved else "unresolved"
    emit({
        "step": "final", "status": status, "window": _window_dict(window),
        "explanation": explanation, "reviewer_reasoning": reasoning, "replanned": True,
    })
    return Recommendation(window, explanation, status, reasoning, replanned=True)
