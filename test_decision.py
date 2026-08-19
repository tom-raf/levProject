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
    reviewer = lambda window, forecast, violations: (True, "looks good")

    rec = decide_day(make_forecast(), analyst, reviewer, last_window_end=None)

    assert rec.status == "approved"
    assert rec.window == cheap_window()


def test_soft_reject_then_approve_on_replan():
    calls = {"n": 0}

    def reviewer(window, forecast, violations):
        calls["n"] += 1
        if calls["n"] == 1:
            return False, "cheaper option exists but carbon-heavy - reconsider"
        return True, "better trade-off now"

    analyst = lambda forecast, reason: (cheap_window(), "explanation")

    rec = decide_day(make_forecast(), analyst, reviewer, last_window_end=None)

    assert rec.status == "approved"
    assert calls["n"] == 2


def test_soft_reject_twice_is_unresolved():
    reviewer = lambda window, forecast, violations: (False, "still not satisfied with the trade-off")
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

    reviewer = lambda window, forecast, violations: (True, "approved")

    rec = decide_day(make_forecast(), analyst, reviewer, last_window_end=None)

    assert rec.status == "approved"
    assert rec.window == cheap_window()
    assert calls["n"] == 2


def test_min_gap_violation_is_caught():
    last_end = datetime(2026, 8, 19, 0, 0)
    # cheap_window starts at 01:00 -- only 1h after last_end, below the 16h min gap
    analyst = lambda forecast, reason: (cheap_window(), "explanation")
    reviewer = lambda window, forecast, violations: (False, f"disqualified: {'; '.join(violations)}")

    rec = decide_day(make_forecast(), analyst, reviewer, last_window_end=last_end)

    assert rec.status == "unresolved"
    assert "since last window" in rec.reviewer_reasoning  # reviewer echoed rules.py's check_rules() message
    assert "16" in rec.reviewer_reasoning


def test_reviewer_is_called_even_on_hard_rule_violation():
    calls: list[list[str]] = []

    def reviewer(window, forecast, violations):
        calls.append(violations)
        return False, "detailed explanation of the disqualification"

    analyst = lambda forecast, reason: (expensive_window(), "explanation")

    rec = decide_day(make_forecast(), analyst, reviewer, last_window_end=None)

    assert len(calls) == 2  # attempt 1 and the replan attempt both call the reviewer
    assert calls[0]  # attempt 1's violations list is non-empty
    assert rec.reviewer_reasoning == "detailed explanation of the disqualification"


def test_hard_rule_violation_cannot_be_overridden_by_reviewer():
    # A misbehaving/non-compliant reviewer says approved=True despite a hard
    # violation -- decide_day() must not trust it.
    analyst = lambda forecast, reason: (expensive_window(), "explanation")
    reviewer = lambda window, forecast, violations: (True, "looks fine to me")

    rec = decide_day(make_forecast(), analyst, reviewer, last_window_end=None)

    assert rec.status == "unresolved"


def test_on_step_sequence_for_approve_on_first_proposal():
    analyst = lambda forecast, reason: (cheap_window(), "cheapest and cleanest slot")
    reviewer = lambda window, forecast, violations: (True, "looks good")
    events = []

    rec = decide_day(make_forecast(), analyst, reviewer, last_window_end=None, on_step=events.append)

    assert [e["step"] for e in events] == ["proposal", "rule_check", "reviewer_verdict", "final"]
    assert rec.status == "approved"


def test_on_step_sequence_for_soft_reject_then_approve():
    calls = {"n": 0}

    def reviewer(window, forecast, violations):
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
    reviewer = lambda window, forecast, violations: (False, "still not satisfied with the trade-off")
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

    reviewer = lambda window, forecast, violations: (not violations, "; ".join(violations) or "approved")
    events = []

    rec = decide_day(make_forecast(), analyst, reviewer, last_window_end=None, on_step=events.append)

    # the reviewer is now called even on attempt 1's hard-rule violation, to
    # supply a detailed explanation -- its approved return is still overridden
    # by decide_day() whenever violations is non-empty.
    assert [e["step"] for e in events] == [
        "proposal", "rule_check", "reviewer_verdict",
        "replan",
        "proposal", "rule_check", "reviewer_verdict", "final",
    ]
    assert events[1]["violations"]  # attempt 1's rule_check has a non-empty violation list
    assert events[2]["approved"] is False  # forced False despite violations being the only signal here
    assert events[-1]["status"] == "approved"
    assert rec.status == "approved"
