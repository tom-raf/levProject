"""Multi-day simulated run: seeded day-1 narrative, real forecasts, formatted output.

Analyst/Reviewer here are heuristic stand-ins matching decision.py's interfaces
(see ticket #4) -- wiring real OpenRouter-backed models is ticket #5, a drop-in
replacement behind the same Analyst/Reviewer callables.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean

from decision import Analyst, DayForecast, Recommendation, Reviewer, decide_day
from rules import CHARGE_DURATION_HOURS, ProposedWindow, price_cap
from tools import get_carbon_forecast, get_price_forecast
from windows import SLOTS_PER_WINDOW, candidate_windows, window_start as _window_start


def _candidate_windows(forecast: DayForecast) -> list[tuple[int, float, float]]:
    return candidate_windows(forecast.prices, forecast.carbon)


def build_seed_day1(day: date) -> DayForecast:
    """Day 1's forecast is constructed, not fetched: cheapest and cleanest windows
    deliberately don't overlap, so a price-only first proposal gets a genuine,
    explainable soft rejection (see CONTEXT.md / PLAN.md's locked seed state)."""
    prices = [30.0] * 48
    carbon = [200.0] * 48
    for i in range(0, 8):  # 00:00-04:00: cheapest window, but high carbon
        prices[i] = 15.0
        carbon[i] = 320.0
    for i in range(20, 28):  # 10:00-14:00: within price cap, much cleaner
        prices[i] = 26.0
        carbon[i] = 70.0
    return DayForecast(day=day, prices=prices, carbon=carbon)


def heuristic_analyst(forecast: DayForecast, reason: str | None) -> tuple[ProposedWindow, str]:
    candidates = _candidate_windows(forecast)

    if reason is None:
        i, price, carbon = min(candidates, key=lambda c: c[1])
        explanation = (
            f"Cheapest available window: avg {price:.1f}p/kWh starting "
            f"{_window_start(forecast.day, i):%H:%M} ({carbon:.0f}gCO2/kWh)."
        )
    else:
        cap = price_cap(forecast.prices)
        within_cap = [c for c in candidates if c[1] <= cap] or candidates
        pmin, pmax = min(c[1] for c in within_cap), max(c[1] for c in within_cap)
        cmin, cmax = min(c[2] for c in within_cap), max(c[2] for c in within_cap)

        def score(c: tuple[int, float, float]) -> float:
            pn = (c[1] - pmin) / (pmax - pmin) if pmax > pmin else 0.0
            cn = (c[2] - cmin) / (cmax - cmin) if cmax > cmin else 0.0
            return pn + cn

        # tie-break on carbon: a rejection was raised specifically about carbon,
        # so an equal-scoring tie should resolve toward the cleaner window
        i, price, carbon = min(within_cap, key=lambda c: (score(c), c[2]))
        explanation = (
            f'Reconsidered after: "{reason}" Picked a within-cap window balancing price and carbon: '
            f"avg {price:.1f}p/kWh, {carbon:.0f}gCO2/kWh starting {_window_start(forecast.day, i):%H:%M}."
        )

    window = ProposedWindow(start=_window_start(forecast.day, i), avg_price=price)
    return window, explanation


def heuristic_reviewer(window: ProposedWindow, forecast: DayForecast, violations: list[str]) -> tuple[bool, str]:
    candidates = _candidate_windows(forecast)
    cap = price_cap(forecast.prices)
    slot_index = round((window.start - _window_start(forecast.day, 0)).total_seconds() / 1800)
    window_carbon = mean(forecast.carbon[slot_index : slot_index + SLOTS_PER_WINDOW])

    if violations:
        return False, (
            f"{'; '.join(violations)}. This window averages {window_carbon:.0f}gCO2/kWh, "
            f"but that's moot -- a hard rule already disqualifies it."
        )

    within_cap = [c for c in candidates if c[1] <= cap]
    if not within_cap:
        return True, "No within-cap alternative available - approved."

    cleanest = min(within_cap, key=lambda c: c[2])
    if cleanest[0] != slot_index and cleanest[2] < window_carbon * 0.6:
        return False, (
            f"This window's carbon intensity (~{window_carbon:.0f}gCO2/kWh) is high - a within-cap "
            f"window at {_window_start(forecast.day, cleanest[0]):%H:%M} averages only "
            f"{cleanest[2]:.0f}gCO2/kWh. Reconsider."
        )
    return True, f"Trade-off looks reasonable: ~{window_carbon:.0f}gCO2/kWh, within the price cap."


@dataclass
class DayResult:
    day: date
    forecast: DayForecast
    recommendation: Recommendation
    actual_carbon: float
    baseline_price: float
    baseline_carbon: float


def run_simulation(
    num_days: int = 2,
    start_day: date | None = None,
    analyst: Analyst = heuristic_analyst,
    reviewer: Reviewer = heuristic_reviewer,
) -> list[DayResult]:
    """Defaults to 2 days: day 1 is the seeded narrative day, day 2 is tomorrow's
    real (partial) forecast. Octopus Agile only publishes ~1 day ahead, so this is
    the actual forecast horizon -- see PLAN.md's "Data horizon" note.

    Analyst/Reviewer default to the heuristic stand-ins; pass llm_agents' versions
    to use the real OpenRouter-backed models instead (see ticket #5)."""
    start_day = start_day or date.today()
    results: list[DayResult] = []
    last_window_end: datetime | None = None

    for offset in range(num_days):
        day = start_day + timedelta(days=offset)
        if offset == 0:
            forecast = build_seed_day1(day)
        else:
            forecast = DayForecast(day=day, prices=get_price_forecast(day), carbon=get_carbon_forecast(day))

        _, baseline_price, baseline_carbon = min(_candidate_windows(forecast), key=lambda c: c[1])

        rec = decide_day(forecast, analyst, reviewer, last_window_end)
        slot_index = round((rec.window.start - _window_start(day, 0)).total_seconds() / 1800)
        actual_carbon = mean(forecast.carbon[slot_index : slot_index + SLOTS_PER_WINDOW])
        results.append(DayResult(day, forecast, rec, actual_carbon, baseline_price, baseline_carbon))

        if rec.status == "approved":
            last_window_end = rec.window.start + timedelta(hours=CHARGE_DURATION_HOURS)

    return results


def format_brief(result: DayResult) -> str:
    rec = result.recommendation
    return "\n".join(
        [
            f"# Recommendation - {result.day.isoformat()}",
            "",
            f"**Status:** {rec.status}{' (sent back once)' if rec.replanned else ''}",
            f"**Window:** {rec.window.start:%Y-%m-%d %H:%M} for {CHARGE_DURATION_HOURS}h, "
            f"avg {rec.window.avg_price:.2f}p/kWh",
            "",
            f"**Analyst:** {rec.explanation}",
            f"**Reviewer:** {rec.reviewer_reasoning}",
        ]
    )


def format_rollup(results: list[DayResult]) -> str:
    days = len(results)
    sent_back = sum(1 for r in results if r.recommendation.replanned)
    avg_price_premium = mean(r.recommendation.window.avg_price - r.baseline_price for r in results)
    avg_carbon_saved = mean(r.baseline_carbon - r.actual_carbon for r in results)
    return "\n".join(
        [
            "# End-of-run rollup",
            "",
            f"- Days simulated: {days}",
            f"- Sent back for reconsideration: {sent_back}",
            f"- Avg price premium vs. a price-only baseline: {avg_price_premium:+.2f}p/kWh",
            f"- Avg carbon saved vs. a price-only baseline: {avg_carbon_saved:+.0f}gCO2/kWh",
        ]
    )


def main(num_days: int = 2, output_dir: str = "output", use_llm: bool = False) -> None:
    if use_llm:
        from llm_agents import llm_analyst, llm_reviewer

        results = run_simulation(num_days=num_days, analyst=llm_analyst, reviewer=llm_reviewer)
    else:
        results = run_simulation(num_days=num_days)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    for result in results:
        brief = format_brief(result)
        print(brief, "\n")
        (out / f"brief-{result.day.isoformat()}.md").write_text(brief)

    rollup = format_rollup(results)
    print(rollup)
    (out / "rollup.md").write_text(rollup)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true", help="use the real OpenRouter-backed Analyst/Reviewer")
    args = parser.parse_args()
    main(use_llm=args.llm)
