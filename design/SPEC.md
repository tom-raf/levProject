# Spec — Live dashboard for Grid Dispatch Loop

Based on `PLAN.md` in this folder (a grilling-session result from reviewing `design_handoff_dashboard/`'s mockup).

## Problem Statement

There's a working CLI pipeline (`rules.py`, `decision.py`, `tools.py`, `simulate.py`, `llm_agents.py`) but no way to demonstrate it visually. A designer produced a high-fidelity static dashboard mockup, but as a snapshot viewer of a pre-computed 2-day run it doesn't actually showcase the thing worth showing — genuine agent reasoning happening in response to real, current conditions. What's needed is an interactive dashboard where a press either watches the agents reason live against real data, or reliably replays the guaranteed reject→replan narrative when a live run doesn't happen to produce one — without requiring trust in a static, potentially-stale report.

## Solution

A small Flask-backed dashboard recreating the mockup's blueprint visual design, replacing its static day-tabs with two on-demand actions: **Live** (a single `decide_day()` call against a rolling real-data horizon, streamed step-by-step via Server-Sent Events) and **Simulated** (an instant replay of an already-captured real transcript from the seeded scenario). Every press adds a timestamped tab to a session history so results can be compared rather than overwritten.

## User Stories

1. As a viewer, I want to see a dashboard styled after the "creamy old technical drawing" blueprint aesthetic from the design handoff, so that the demo looks polished and consistent with the design spec.
2. As a viewer, I want a battery state-of-charge gauge on the dashboard, so that the recommendation feels grounded in a physical asset, even though it's clearly marked as illustrative rather than real telemetry.
3. As a presenter, I want a "Live" button that runs a genuine decision against real, current price and carbon data, so that I can show the system reasoning about right-now conditions rather than a pre-baked scenario.
4. As a presenter, I want the Live button's forecast window to include today's remaining hours plus whatever of tomorrow has been published, so that a press late in the day still has real near-term data instead of jumping straight to a mostly-unpublished tomorrow.
5. As a presenter, I want Live's window-start times computed relative to the actual current time, so that the recommended window is never a slot that's already in the past.
6. As a viewer, I want the Live transcript to fill in step-by-step (Analyst proposes, hard-rule check, Reviewer verdict, replan if needed, final outcome) as each step actually completes, so that I can watch the reasoning happen rather than waiting for a single final blob.
7. As a presenter, I want a "Simulated" button that always reliably demonstrates the reject-then-approve mechanism, so that I have a guaranteed narrative even if a live press happens to land on an uneventful day.
8. As a presenter, I want the Simulated button to replay an actual previously-captured real transcript rather than a live re-computation, so that it costs no API credit, has no dependency on OpenRouter being reachable, and is instant.
9. As a viewer, I want the Simulated transcript to also reveal progressively (staged, not an instant dump), so that its visual behavior feels consistent with the Live button rather than jarringly different.
10. As a presenter, I want every button press (Live or Simulated) to add a new timestamped tab rather than replacing the current view, so that I can compare multiple runs side by side within one session.
11. As a viewer, I want to click back through previous tabs to see earlier results, so that nothing is lost as I explore multiple presses.
12. As a presenter, I want a second Live press to correctly apply the 16-hour min-gap rule against the most recently approved Live window in the same session, so that I can demonstrate the constraint actually firing on real data, live.
13. As a presenter, I want the min-gap panel to only apply to Live runs, not Simulated ones, so that a frozen replay isn't misrepresented as reacting to session state it doesn't actually track.
14. As a viewer, I want the price/carbon chart to correctly render whatever length of series a given run actually has (a full 48 slots for Simulated, a variable rolling-horizon length for Live), so that the chart doesn't break or mislabel data when the two run types differ in length.
15. As a developer, I want `decide_day()` extended with an optional step-callback rather than duplicated into a separate streaming implementation, so that the propose→check→replan→approve control flow stays in exactly one place and the existing ticket #2 tests keep passing unmodified.
16. As a developer, I want a pure `build_rolling_forecast()` function that takes already-fetched price/carbon lists and a "now" timestamp and returns the concatenated horizon, so that the horizon-building arithmetic is testable without any network access or time-of-day flakiness.
17. As a developer, I want the Live route to call the real `llm_agents` Analyst/Reviewer exactly as `simulate.py --llm` already does, so that no second implementation of the OpenRouter integration exists.
18. As a developer, I want the Simulated route to read a saved fixture of a real captured transcript rather than any invented text, so that the project's "no mocking" principle holds even for the guaranteed-narrative path.
19. As a presenter, I want the dashboard to run as a single local process with no authentication, so that it's simple to start before a demo and has no login flow to fumble live.
20. As a developer, I want `rules.py`, `decision.py`, `windows.py`, `tools.py`, and `llm_agents.py` to remain the source of truth for all decision/data logic, so that the dashboard is a thin presentation layer, not a second implementation of the pipeline.

## Implementation Decisions

- **SOC gauge**: kept, illustrative-only, clearly labeled as not real telemetry, with no backing data source — deliberately not wired to anything real, consistent with the root `PLAN.md`'s exclusion of battery state-of-charge modelling.
- **Two on-demand actions** replace the mockup's static day-tabs: Live and Simulated.
- **Live**: a single call to `decide_day()` (not the multi-day loop), fed by a new `build_rolling_forecast(now)` — concatenates today's remaining published slots with tomorrow's published slots (Octopus publishes ~1 day ahead), with window-start times computed relative to `now` rather than midnight.
- **`decide_day()` gains an optional `on_step` callback parameter** (default `None`, backward compatible with existing callers/tests), invoked after each meaningful step (initial proposal, rule-check result, reviewer verdict, replan if any, final outcome), so the SSE route can emit events without a parallel decision implementation.
- **Live's Analyst/Reviewer are the real `llm_agents.llm_analyst`/`llm_reviewer`**, called exactly as `simulate.py --llm` already does.
- **Live's `last_window_end`** is sourced from session history: the end of the most recently *approved* Live-type run this session, or `None` if there isn't one yet. Simulated runs never read or write this state.
- **Simulated**: no computation, no network call. Replays a saved fixture (the transcript already captured from a real `llm_agents` run against `build_seed_day1()`) via a generator yielding entries with small delays, matching Live's step-by-step cadence.
- **Backend**: a small Flask app, single process, no auth, synchronous (matching the rest of the codebase). Two `POST` routes (`/run/live`, `/run/simulated`) returning Server-Sent Events streams; one `GET` route serving the dashboard page.
- **Session history**: in-memory list of past runs (type, timestamp, resulting transcript/`Recommendation`), lost on process restart — acceptable for a local demo tool, no persistence layer needed.
- **Frontend**: plain HTML/CSS/vanilla JS recreating the mockup's visual design (tokens, layout, inline SVG chart/gauge/min-gap diagram) using `EventSource` to consume the two SSE routes; history renders as clickable tabs instead of the mockup's static day-tabs. The delivered `.dc.html` is Claude.ai's internal artifact templating format and isn't runnable as-is (confirmed: relies on a missing `support.js` and proprietary `x-dc`/`sc-for`/`DCLogic` constructs) — it's a visual/interaction spec to recreate, not code to adapt.
- **Chart rendering must handle variable-length series**: Live's rolling horizon varies by time of day; Simulated is always the fixed 48-slot seeded series.

## Testing Decisions

- Good tests here exercise the two seams' external behavior only — not Flask/SSE/HTTP machinery, and not real network or model calls.
- **`build_rolling_forecast()`**: given fixed today/tomorrow price+carbon lists and a fixed `now`, assert the returned concatenated series and window-start offsets are correct — including edge cases where `now` is near midnight (almost all of today remaining) and near end-of-day (almost none of today remaining, mostly tomorrow).
- **`decide_day()`'s `on_step` callback**: reuse the existing fake-Analyst/Reviewer pattern from `test_decision.py`, additionally asserting the callback receives the expected sequence of step events for each of the four scenarios already covered (approve-first-try, soft-reject-then-approve, soft-reject-twice-unresolved, hard-rule-violation-then-replan). The callback must not change any existing return-value assertions.
- Prior art: `test_decision.py`'s fake-Analyst/Reviewer injection pattern is the direct precedent for both of the above.
- Not directly unit-tested at this seam: the Flask routes themselves, the SSE wire format, the frontend JS, and the Simulated fixture-replay generator's timing — verified manually per `PLAN.md`'s Verification section, consistent with how the rest of this project treats framework/glue code as outside the unit-test seam.

## Out of Scope

- Exact history-tab cap and exact Simulated pacing — both listed as deliberately deferred in `PLAN.md`, not real design branches.
- Persisting session history across process restarts.
- Any authentication or multi-user support.
- Making the SOC gauge reflect real data — explicitly staying illustrative-only per the locked decision.
- The multi-day loop / `simulate.py`'s existing batch CLI path — unaffected; `decide_day()`'s new parameter is optional and unused by existing callers.
- Any changes to `rules.py`, `windows.py`, or `tools.py`'s existing behavior — reused as-is.

## Further Notes

- This spec operationalizes `design/PLAN.md`, itself the result of a grilling session reviewing `design_handoff_dashboard/`'s mockup.
- The mockup's own README discloses its data as "illustrative/mock — wire it to real telemetry"; this spec's Live path is exactly that wiring for everything except the SOC gauge, which stays illustrative by deliberate choice.
- `decide_day()`'s callback addition must be strictly additive and backward-compatible — ticket #2's existing tests need to keep passing unmodified.
- Not published to the issue tracker yet — this is still a design-stage artifact (file only, per instruction).
