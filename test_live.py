from datetime import datetime, timedelta, timezone

from live import build_rolling_forecast, rolling_window_start


def _slots(n: int, offset: float = 0.0) -> list[float]:
    return [offset + i for i in range(n)]


def test_concatenates_remaining_today_and_tomorrow():
    now = datetime(2026, 8, 19, 13, 5, tzinfo=timezone.utc)  # not on a slot boundary
    today_prices, today_carbon = _slots(48), _slots(48, offset=1000.0)
    tomorrow_prices, tomorrow_carbon = _slots(48, offset=100.0), _slots(48, offset=2000.0)

    forecast = build_rolling_forecast(now, today_prices, today_carbon, tomorrow_prices, tomorrow_carbon)

    # 13:05 -> next slot boundary is 13:30, index 27
    assert forecast.start == datetime(2026, 8, 19, 13, 30, tzinfo=timezone.utc)
    assert forecast.prices == today_prices[27:] + tomorrow_prices
    assert forecast.carbon == today_carbon[27:] + tomorrow_carbon
    assert rolling_window_start(forecast, 0) == forecast.start
    assert rolling_window_start(forecast, 1) == forecast.start + timedelta(minutes=30)


def test_now_exactly_on_a_slot_boundary_includes_that_slot():
    now = datetime(2026, 8, 19, 13, 30, tzinfo=timezone.utc)
    today_prices, today_carbon = _slots(48), _slots(48)

    forecast = build_rolling_forecast(now, today_prices, today_carbon)

    assert forecast.start == now
    assert forecast.prices == today_prices[27:]


def test_near_midnight_keeps_almost_all_of_today():
    now = datetime(2026, 8, 19, 0, 5, tzinfo=timezone.utc)
    today_prices, today_carbon = _slots(48), _slots(48)

    forecast = build_rolling_forecast(now, today_prices, today_carbon)

    assert forecast.start == datetime(2026, 8, 19, 0, 30, tzinfo=timezone.utc)
    assert forecast.prices == today_prices[1:]
    assert len(forecast.prices) == 47


def test_near_end_of_day_before_tomorrow_publishes_is_thin():
    now = datetime(2026, 8, 19, 23, 45, tzinfo=timezone.utc)
    today_prices, today_carbon = _slots(48), _slots(48)

    forecast = build_rolling_forecast(now, today_prices, today_carbon, tomorrow_prices=None, tomorrow_carbon=None)

    # 23:45 -> next boundary is tomorrow 00:00 -- the in-progress 23:30 slot is excluded
    assert forecast.start == datetime(2026, 8, 20, 0, 0, tzinfo=timezone.utc)
    assert forecast.prices == []
    assert forecast.carbon == []


def test_near_end_of_day_once_tomorrow_has_published():
    now = datetime(2026, 8, 19, 23, 45, tzinfo=timezone.utc)
    today_prices, today_carbon = _slots(48), _slots(48)
    tomorrow_prices, tomorrow_carbon = _slots(48, offset=100.0), _slots(48, offset=2000.0)

    forecast = build_rolling_forecast(now, today_prices, today_carbon, tomorrow_prices, tomorrow_carbon)

    assert forecast.start == datetime(2026, 8, 20, 0, 0, tzinfo=timezone.utc)
    assert forecast.prices == tomorrow_prices
    assert forecast.carbon == tomorrow_carbon
