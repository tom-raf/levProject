"""Hard constraints the Reviewer checks a proposed Window against.

Checked in code, not by a model. See CONTEXT.md for Window/Reviewer/min-gap definitions.
"""

from dataclasses import dataclass
from datetime import datetime

CHARGE_DURATION_HOURS = 4
MIN_GAP_HOURS = 16
PRICE_CAP_PERCENTILE = 25


def price_cap(day_prices: list[float]) -> float:
    """25th percentile of a day's quoted prices — recomputed per day, not a fixed number."""
    ordered = sorted(day_prices)
    index = int(len(ordered) * PRICE_CAP_PERCENTILE / 100)
    return ordered[index]


@dataclass
class ProposedWindow:
    start: datetime
    avg_price: float


def check_rules(
    window: ProposedWindow,
    day_prices: list[float],
    last_window_end: datetime | None,
) -> list[str]:
    """Returns a list of violated rules; empty means the hard gate passes."""
    violations = []

    if window.avg_price > price_cap(day_prices):
        violations.append("avg_price exceeds price_cap for this day")

    if last_window_end is not None:
        gap_hours = (window.start - last_window_end).total_seconds() / 3600
        if gap_hours < MIN_GAP_HOURS:
            violations.append(f"only {gap_hours:.1f}h since last window, needs {MIN_GAP_HOURS}h")

    return violations
