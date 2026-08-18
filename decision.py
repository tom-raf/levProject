"""Single-day decision core: propose -> check -> replan once -> approve/unresolved.

See CONTEXT.md for Analyst/Reviewer/Recommendation definitions and rules.py for
the hard constraints. Analyst and Reviewer are swappable callables so a real
model provider can be wired in without touching this logic.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable, Literal

from rules import ProposedWindow, check_rules


@dataclass
class DayForecast:
    day: date
    prices: list[float]
    carbon: list[float]


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


def _evaluate(
    window: ProposedWindow,
    forecast: DayForecast,
    last_window_end: datetime | None,
    reviewer: Reviewer,
) -> tuple[bool, str]:
    violations = check_rules(window, forecast.prices, last_window_end)
    if violations:
        return False, "; ".join(violations)
    return reviewer(window, forecast)


def decide_day(
    forecast: DayForecast,
    analyst: Analyst,
    reviewer: Reviewer,
    last_window_end: datetime | None,
) -> Recommendation:
    window, explanation = analyst(forecast, None)
    approved, reasoning = _evaluate(window, forecast, last_window_end, reviewer)
    if approved:
        return Recommendation(window, explanation, "approved", reasoning, replanned=False)

    window, explanation = analyst(forecast, reasoning)
    approved, reasoning = _evaluate(window, forecast, last_window_end, reviewer)
    status: Literal["approved", "unresolved"] = "approved" if approved else "unresolved"
    return Recommendation(window, explanation, status, reasoning, replanned=True)
