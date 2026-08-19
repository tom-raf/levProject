"""Rolling forecast horizon for the dashboard's Live run: today's remaining
published slots concatenated with tomorrow's published slots (if published
yet), with slot-start times computed relative to `now` rather than midnight.
See design/PLAN.md and design/SPEC.md for the decision behind this."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import ceil


@dataclass
class RollingForecast:
    start: datetime  # slot-start time of index 0: the next slot boundary at/after `now`
    prices: list[float]
    carbon: list[float]


def _next_slot_boundary(now: datetime) -> datetime:
    """The next 30-minute slot boundary at or after `now` -- never a slot already in progress."""
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    slots_since_midnight = (now - midnight).total_seconds() / 1800
    return midnight + timedelta(minutes=30 * ceil(slots_since_midnight))


def build_rolling_forecast(
    now: datetime,
    today_prices: list[float],
    today_carbon: list[float],
    tomorrow_prices: list[float] | None = None,
    tomorrow_carbon: list[float] | None = None,
) -> RollingForecast:
    """Concatenates today's remaining published slots (from the next slot boundary
    at/after `now`) with tomorrow's published slots, if published yet (Octopus
    publishes next-day prices roughly 4pm-8pm UK time -- tomorrow_prices/carbon
    are None until then). No minimum-horizon floor: a press landing in the
    window before tomorrow publishes can see a thin horizon -- accepted, not
    handled (see design/PLAN.md)."""
    boundary = _next_slot_boundary(now)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_index = round((boundary - midnight).total_seconds() / 1800)

    prices = today_prices[start_index:] + (tomorrow_prices or [])
    carbon = today_carbon[start_index:] + (tomorrow_carbon or [])
    return RollingForecast(start=boundary, prices=prices, carbon=carbon)


def rolling_window_start(forecast: RollingForecast, index: int) -> datetime:
    return forecast.start + timedelta(minutes=30 * index)
