"""Shared candidate-window arithmetic used by both the heuristic stand-in
(simulate.py) and the real OpenRouter-backed Analyst/Reviewer (llm_agents.py)."""

from datetime import date, datetime, time, timedelta, timezone
from statistics import mean

from rules import CHARGE_DURATION_HOURS

SLOTS_PER_WINDOW = CHARGE_DURATION_HOURS * 2  # 30-minute slots


def window_start(day: date, index: int) -> datetime:
    return datetime.combine(day, time.min, tzinfo=timezone.utc) + timedelta(minutes=30 * index)


def candidate_windows(prices: list[float], carbon: list[float]) -> list[tuple[int, float, float]]:
    """All valid (start_index, avg_price, avg_carbon) windows for a day's forecast."""
    n = len(prices)
    return [
        (i, mean(prices[i : i + SLOTS_PER_WINDOW]), mean(carbon[i : i + SLOTS_PER_WINDOW]))
        for i in range(0, n - SLOTS_PER_WINDOW + 1)
    ]
