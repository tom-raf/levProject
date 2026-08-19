from datetime import date, datetime

from decision import DayForecast, decide_day
from rules import ProposedWindow


def make_forecast() -> DayForecast:
    prices = [20.0 + i for i in range(48)]  # 30-min slots across a day
    carbon = [150.0 for _ in range(48)]
    return DayForecast(day=date(2026, 8, 19), prices=prices, carbon=carbon)


def cheap_window() -> ProposedWindow:
    # 20.0 is the day's minimum -> well under the 25th-percentile price cap
    return ProposedWindow(start=datetime(2026, 8, 19, 1, 0), avg_price=20.0)


def expensive_window() -> ProposedWindow:
    # above the 25th-percentile price cap -> hard-rule violation
    return ProposedWindow(start=datetime(2026, 8, 19, 20, 0), avg_price=60.0)


def test_approve_on_first_proposal():
    analyst = lambda forecast, reason: (cheap_window(), "cheapest and cleanest slot")
    reviewer = lambda window, forecast: (True, "looks good")

    rec = decide_day(make_forecast(), analyst, reviewer, last_window_end=None)

    assert rec.status == "approved"
    assert rec.window == cheap_window()


def test_soft_reject_then_approve_on_replan():
    calls = {"n": 0}

    def reviewer(window, forecast):
        calls["n"] += 1
        if calls["n"] == 1:
            return False, "cheaper option exists but carbon-heavy - reconsider"
        return True, "better trade-off now"

    analyst = lambda forecast, reason: (cheap_window(), "explanation")

    rec = decide_day(make_forecast(), analyst, reviewer, last_window_end=None)

    assert rec.status == "approved"
    assert calls["n"] == 2


def test_soft_reject_twice_is_unresolved():
    reviewer = lambda window, forecast: (False, "still not satisfied with the trade-off")
    analyst = lambda forecast, reason: (cheap_window(), "explanation")

    rec = decide_day(make_forecast(), analyst, reviewer, last_window_end=None)

    assert rec.status == "unresolved"
    assert rec.reviewer_reasoning == "still not satisfied with the trade-off"


def test_hard_rule_violation_then_replan_fixes_it():
    calls = {"n": 0}

    def analyst(forecast, reason):
        calls["n"] += 1
        if calls["n"] == 1:
            return expensive_window(), "first attempt"
        return cheap_window(), "replanned within the price cap"

    reviewer = lambda window, forecast: (True, "approved")

    rec = decide_day(make_forecast(), analyst, reviewer, last_window_end=None)

    assert rec.status == "approved"
    assert rec.window == cheap_window()
    assert calls["n"] == 2


def test_min_gap_violation_is_caught():
    last_end = datetime(2026, 8, 19, 0, 0)
    # cheap_window starts at 01:00 -- only 1h after last_end, below the 16h min gap
    analyst = lambda forecast, reason: (cheap_window(), "explanation")
    reviewer = lambda window, forecast: (True, "approved")

    rec = decide_day(make_forecast(), analyst, reviewer, last_window_end=last_end)

    assert rec.status == "unresolved"
    assert "since last window" in rec.reviewer_reasoning  # message comes from rules.py's check_rules()
    assert "16" in rec.reviewer_reasoning


def test_on_step_sequence_for_approve_on_first_proposal():
    analyst = lambda forecast, reason: (cheap_window(), "cheapest and cleanest slot")
    reviewer = lambda window, forecast: (True, "looks good")
    events = []

    rec = decide_day(make_forecast(), analyst, reviewer, last_window_end=None, on_step=events.append)

    assert [e["step"] for e in events] == ["proposal", "rule_check", "reviewer_verdict", "final"]
    assert rec.status == "approved"


def test_on_step_sequence_for_soft_reject_then_approve():
    calls = {"n": 0}

    def reviewer(window, forecast):
        calls["n"] += 1
        if calls["n"] == 1:
            return False, "cheaper option exists but carbon-heavy - reconsider"
        return True, "better trade-off now"

    analyst = lambda forecast, reason: (cheap_window(), "explanation")
    events = []

    rec = decide_day(make_forecast(), analyst, reviewer, last_window_end=None, on_step=events.append)

    assert [e["step"] for e in events] == [
        "proposal", "rule_check", "reviewer_verdict",
        "replan",
        "proposal", "rule_check", "reviewer_verdict", "final",
    ]
    assert events[3]["reason"] == "cheaper option exists but carbon-heavy - reconsider"
    assert events[-1]["status"] == "approved"
    assert rec.status == "approved"


def test_on_step_sequence_for_soft_reject_twice_is_unresolved():
    reviewer = lambda window, forecast: (False, "still not satisfied with the trade-off")
    analyst = lambda forecast, reason: (cheap_window(), "explanation")
    events = []

    rec = decide_day(make_forecast(), analyst, reviewer, last_window_end=None, on_step=events.append)

    assert [e["step"] for e in events] == [
        "proposal", "rule_check", "reviewer_verdict",
        "replan",
        "proposal", "rule_check", "reviewer_verdict", "final",
    ]
    assert events[-1]["status"] == "unresolved"
    assert rec.status == "unresolved"


def test_on_step_sequence_for_hard_rule_violation_then_replan():
    calls = {"n": 0}

    def analyst(forecast, reason):
        calls["n"] += 1
        if calls["n"] == 1:
            return expensive_window(), "first attempt"
        return cheap_window(), "replanned within the price cap"

    reviewer = lambda window, forecast: (True, "approved")
    events = []

    rec = decide_day(make_forecast(), analyst, reviewer, last_window_end=None, on_step=events.append)

    # attempt 1's hard-rule violation means the reviewer is never called for it
    assert [e["step"] for e in events] == [
        "proposal", "rule_check",
        "replan",
        "proposal", "rule_check", "reviewer_verdict", "final",
    ]
    assert events[1]["violations"]  # attempt 1's rule_check has a non-empty violation list
    assert events[-1]["status"] == "approved"
    assert rec.status == "approved"
