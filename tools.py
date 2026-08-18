"""Live/cached fetch tools for price and carbon forecasts.

Thin wrappers: fetch/parse/return only, no logic beyond that (see PLAN.md).
One switch controls both: GRID_DISPATCH_DATA_SOURCE=live (default) or cache.
Live falls back to cache automatically if the live call fails.
"""

import json
import os
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import requests

OCTOPUS_BASE = "https://api.octopus.energy/v1"
CARBON_BASE = "https://api.carbonintensity.org.uk"
OCTOPUS_REGION = os.environ.get("OCTOPUS_REGION", "C")
CACHE_DIR = Path(os.environ.get("GRID_DISPATCH_CACHE_DIR", ".cache"))


def _use_cache_only() -> bool:
    return os.environ.get("GRID_DISPATCH_DATA_SOURCE", "live").lower() == "cache"


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


def _current_agile_tariff_code() -> tuple[str, str]:
    """Look up the currently-live Agile import product rather than hardcoding one that will expire."""
    resp = requests.get(f"{OCTOPUS_BASE}/products/", params={"brand": "OCTOPUS_ENERGY"}, timeout=10)
    resp.raise_for_status()
    products = resp.json()["results"]
    agile = [
        p for p in products
        if p["code"].startswith("AGILE") and p.get("direction") == "IMPORT" and p.get("available_to") is None
    ]
    if not agile:
        raise RuntimeError("no live Agile import product found")
    product_code = agile[0]["code"]
    return product_code, f"E-1R-{product_code}-{OCTOPUS_REGION}"


def _fetch_price_forecast_live(day: date) -> list[float]:
    product_code, tariff_code = _current_agile_tariff_code()
    start, end = _day_bounds(day)
    url = f"{OCTOPUS_BASE}/products/{product_code}/electricity-tariffs/{tariff_code}/standard-unit-rates/"
    resp = requests.get(url, params={"period_from": start.isoformat(), "period_to": end.isoformat()}, timeout=10)
    resp.raise_for_status()
    results = sorted(resp.json()["results"], key=lambda r: r["valid_from"])
    return [r["value_inc_vat"] for r in results]


def _fetch_carbon_forecast_live(day: date) -> list[float]:
    start, end = _day_bounds(day)
    fmt = "%Y-%m-%dT%H:%MZ"
    url = f"{CARBON_BASE}/intensity/{start.strftime(fmt)}/{end.strftime(fmt)}"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    data = [d for d in resp.json()["data"] if d["from"] >= start.strftime(fmt)]
    data.sort(key=lambda d: d["from"])
    return [d["intensity"]["forecast"] for d in data]


def _cache_path(name: str, day: date) -> Path:
    return CACHE_DIR / f"{name}-{day.isoformat()}.json"


def _read_cache(name: str, day: date) -> list[float]:
    path = _cache_path(name, day)
    if not path.exists():
        raise FileNotFoundError(f"no cached {name} forecast for {day} at {path}")
    return json.loads(path.read_text())


def _write_cache(name: str, day: date, values: list[float]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(name, day).write_text(json.dumps(values))


def _get_forecast(name: str, day: date, fetch_live) -> list[float]:
    if _use_cache_only():
        return _read_cache(name, day)
    try:
        values = fetch_live(day)
    except requests.RequestException:
        return _read_cache(name, day)
    _write_cache(name, day, values)
    return values


def get_price_forecast(day: date) -> list[float]:
    return _get_forecast("price", day, _fetch_price_forecast_live)


def get_carbon_forecast(day: date) -> list[float]:
    return _get_forecast("carbon", day, _fetch_carbon_forecast_live)


def prefetch_cache(days: list[date]) -> None:
    """Populate the disk cache for a multi-day window ahead of a live demo run."""
    for day in days:
        get_price_forecast(day)
        get_carbon_forecast(day)
