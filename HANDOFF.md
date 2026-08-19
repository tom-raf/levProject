# Handoff

Where this stands as of 2026-08-19, for picking back up later.

## What this project is

Grid Dispatch Loop — two AI agents (Analyst, Reviewer) decide when to charge a grid-scale battery by weighing live UK electricity price against grid carbon intensity, now with an interactive dashboard. Full pipeline backstory in `docs/initial-plan/PLAN.md`; dashboard design history in `design/PLAN.md`/`design/SPEC.md`; domain vocabulary in `CONTEXT.md`.

## What's built and verified (all committed, pushed to `origin/main`)

**Pipeline** (from yesterday, unchanged today except two real bug fixes below):
- `rules.py` — hard constraints (`check_rules`, `price_cap`).
- `decision.py` — single-day decision core: propose → check → replan-once → approve/unresolved, plus an optional `on_step` callback added today (backward-compatible) so a caller can observe each step as it happens.
- `tools.py` — live/cached fetch for price (Octopus Agile) and carbon (Carbon Intensity API).
- `windows.py` — shared candidate-window arithmetic.
- `simulate.py` — 2-day simulated CLI run, heuristic or real-LLM.
- `llm_agents.py` — real Analyst (`anthropic/claude-opus-5`) / Reviewer (`anthropic/claude-sonnet-5`) via OpenRouter.

**Dashboard** (today's work — tickets #7–#12, all closed, parent issue [#6](https://github.com/tom-raf/levProject/issues/6) left open deliberately):
- `live.py` — `build_rolling_forecast(now)`: today's remaining + tomorrow's published slots, window-starts relative to `now`. Pure, tested (`test_live.py`).
- `app.py` — Flask app. `GET /` serves the dashboard; `POST /run/simulated` and `POST /run/live` stream step events as SSE (POST, not native `EventSource` — see the docstring for why). In-memory `RUN_HISTORY` backs Live's min-gap lookup.
- `templates/index.html`, `static/style.css`, `static/app.js` — the blueprint-styled frontend, recreating `design/design_handoff_dashboard/`'s mockup in plain HTML/CSS/vanilla JS.
- `fixtures/simulated_transcript.json` — a real captured `llm_agents` transcript (forecast + step events) that Simulated replays. `capture_transcript.py` is the one-off script that produced it (real OpenRouter call — don't re-run casually).

Run it:
```
.venv/bin/python -m pytest test_decision.py test_live.py -v   # 14/14 passing
.venv/bin/python app.py                                        # dashboard on :5050
```

## Two real bugs found and fixed in `llm_agents.py` today

Both surfaced while trying to capture a guaranteed reject→replan transcript, and both are genuine correctness fixes independent of that goal:
1. **Stateless replan had no memory of its own prior proposal.** The Analyst's second call never restated what it had proposed, so it sometimes hallucinated a different prior window and re-derived constraints incorrectly. Fixed: `decision.py` now passes the rejected window's details into the replan prompt.
2. **Reviewer was blind to min-gap-excluded candidates**, so it could reject a legitimately compliant window for being "dominated" by an alternative that was actually ineligible. Fixed: `decision.py`'s `DayForecast`/`live.py`'s `RollingForecast` both gained a `last_window_end` field; `llm_agents.py` filters the candidate list shown to both Analyst and Reviewer by it.

Also fixed: a cross-midnight parsing bug where a picked "HH:MM" got reconstructed against the wrong calendar day for a rolling horizon spanning past midnight. The Analyst's response format changed from `"HH:MM"` to an exact ISO datetime echoed from the candidate list, removing the ambiguity rather than working around it.

## Simulated's fixture isn't the originally-planned narrative

The plan was a *guaranteed* reject→replan story from `build_seed_day1()`. Real models (well-informed, given price + carbon together) reliably find the best trade-off immediately — six real capture attempts across three different forcing strategies never produced a lasting rejection. Decision: accept the real transcript as-is (approved on first proposal). Full account in `design/PLAN.md`'s Further Notes. Not a loose end — just a documented scope revision.

## UI polish fixed today (post-implementation, via real browser testing)

- **Dark-mode inversion**: the page never declared `color-scheme: light`, so the browser was auto-inverting the cream palette to near-black. Fixed with one `color-scheme: light` rule.
- **FIG.3 placeholder text overlapping its own timeline line.**
- **Chart y-axis scale now shared across the whole session** (running min/max, not per-run), so two runs are actually visually comparable rather than each auto-scaling to its own data.
- Rejected transcript entries no longer struck through (was hard to read) — kept dimmed only.
- Hard rule-check violations relabeled from "REVIEWER" to "RULE CHECK" in the transcript — that message is a fixed `rules.py` string, the real Reviewer LLM is never called when a hard rule already fails, and labeling it "REVIEWER" made it look like a lazy model response.

## Not yet visually confirmed

The full FIG.3 min-gap timeline (prev-end / +16h-eligible / next-start markers, color-coded pass/fail) only renders once a prior *approved* Live run exists in session history. Today's real UK prices made every Live attempt end `unresolved` (every window this afternoon genuinely exceeded the price cap — real data, not a bug). The underlying logic is verified (5 zero-cost direct test cases against `_last_approved_live_window_end()`, all passing), just not seen rendered with real approved-then-second-press data. **User's plan: try it after 4pm**, when tomorrow's Octopus prices publish and the picture changes.

## Environment

- `.venv/` has everything installed, including `flask` (added today).
- `.env` holds `OPENROUTER_API_KEY`, confirmed working today (several real calls).
- Dev server may still be running in the background from today's session (`http://127.0.0.1:5050`) — check before starting a second one.

## To resume later

Nothing is blocked. Options:
- Try the after-4pm Live min-gap test (press Live, hope for an approval, press Live again within 16h to see it genuinely reject).
- Anything else — the dashboard is feature-complete per `design/SPEC.md`; issue #6 (parent) is still open as the umbrella reference, same convention as issue #1.
