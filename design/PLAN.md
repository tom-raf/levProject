# Live dashboard for Grid Dispatch Loop

## Context

A design mockup for a dashboard (`design_handoff_dashboard/levCell Dashboard.dc.html`) was reviewed for feasibility, which surfaced two real gaps against the existing pipeline (no battery-SOC data source, and `decide_day()` discarding the first-attempt history needed for a transcript). During a grilling session about the design, the scope evolved substantially: from "static snapshot of a pre-computed 2-day run" into an interactive dashboard with two on-demand buttons — a genuinely live run and a guaranteed-narrative replay — which needs a small backend rather than a self-contained static file. This plan captures the settled design before any of it gets built; nothing has been implemented yet.

## Locked decisions

1. **SOC gauge (FIG.2)**: kept, illustrative-only, visually/textually marked as not real telemetry. No wiring effort spent making it real — it has no backing data source and `PLAN.md` explicitly excludes battery state-of-charge modelling.
2. **Two buttons, not a static file**: "Live" and "Simulated". Live execution requires a small backend now — the earlier "single self-contained HTML" option is superseded.
3. **Live = a single `decide_day()` call**, not the multi-day loop, against a **rolling forecast horizon**: today's remaining slots (from "now" onward) concatenated with tomorrow's published slots (Octopus only publishes ~1 day ahead — see the root `docs/initial-plan/PLAN.md`'s "Data horizon" note). Needs a new helper to build this concatenated forecast and to compute window-start times relative to `now` rather than midnight.
4. **Live streams progressively via Server-Sent Events**: each completed step (Analyst proposal → hard-rule check → Reviewer verdict → replan if needed → final) is pushed as it completes, so the transcript panel fills in live rather than waiting for one final blob. This is the actual point of adding live execution — exposing the reasoning process, not just a fresher final answer.
5. **Simulated replays a real captured transcript**, not a live call. Uses a real `llm_agents` run's output (a dedicated seed, not `build_seed_day1()` — see Further Notes) — zero cost, zero OpenRouter dependency, instant/staged for visual consistency with Live's streaming feel. Same resilience pattern already used for price/carbon data (live-primary, real-capture fallback), applied to guarantee one button always works regardless of API/credit state.
   - **Revised during implementation**: the original "guaranteed reject→replan narrative" framing doesn't hold against real models — see Further Notes. The captured transcript is genuine real Opus/Sonnet output, whatever narrative it naturally produced (here: approved on first proposal), not a forced or invented rejection.
6. **History kept as tabs**: every press of either button adds a new timestamped tab; old results stay viewable rather than being overwritten. This is what makes "Live genuinely varies" and "Simulated is stable" demonstrable side by side.
7. **Min-gap panel (FIG.3) wired for Live only**: each Live press passes the end of the most recently *approved* Live window this session (if any) as `last_window_end` into `decide_day()`, so the real 16h rule can actually fire live. Simulated stays independent of this state — it's a frozen replay, not reactive.
8. **Chart (FIG.1) must handle a variable-length series** for Live (rolling-horizon length depends on time of day), while still rendering Simulated's fixed 48-slot seeded series correctly.

## Implementation approach

- **Backend**: a small Flask app (matches the codebase's existing synchronous style — nothing else in the project is async). Single process, single user, no auth — a local demo tool, not a service.
- **Routes**:
  - `GET /` — serves the dashboard (HTML/CSS/vanilla JS). The delivered `.dc.html` is Claude.ai's internal artifact templating format (`x-dc`, `sc-for`, a `DCLogic` class, a missing `support.js`) and is explicitly not runnable as-is per its own README — it's a visual/interaction spec to recreate, not code to copy. The blueprint aesthetic, layout, and inline SVG chart translate directly; the templating mechanics need rewriting as plain DOM updates + `EventSource`.
  - `POST /run/live` (SSE) — builds the rolling-horizon forecast, runs `decide_day()` with the real `llm_agents` Analyst/Reviewer, streaming each step as an event.
  - `POST /run/simulated` (SSE) — streams the pre-captured transcript with staged delays; no computation, no network call.
- **New code**:
  - A helper (e.g. in a new `live.py`) building the rolling-horizon `DayForecast`-equivalent from `tools.get_price_forecast`/`get_carbon_forecast` for today + tomorrow, with window-start math relative to `now`.
  - An in-memory session history store (list of past runs: type, timestamp, resulting `Recommendation`/transcript) — no database needed.
  - A saved fixture of the real captured seeded-scenario transcript, for the Simulated endpoint to replay.
  - Frontend JS: `EventSource` consumers for both SSE endpoints, history-tab rendering, and the chart/gauge/min-gap SVG components recreated from the design spec.
- **Reused unchanged**: `rules.py`, `decision.py` (`decide_day`/`check_rules` — ticket #2's seam, exactly as built and tested), `windows.py`, `llm_agents.py` (Live calls these directly), `tools.py` (Live's rolling-horizon fetch calls these directly).

## Verification

- Run the Flask app locally; press **Simulated** — confirm the transcript streams in with the exact previously-captured real text, and confirm via logs that zero OpenRouter requests fire.
- Press **Live** — confirm a real OpenRouter call fires, the transcript streams progressively (not all at once), and the chart renders whatever slot-count the rolling horizon actually returns at that time of day.
- Press **Live** twice in quick succession — confirm the second press's min-gap check uses the first press's approved window end as `last_window_end`, and genuinely rejects if within 16h.
- Confirm history tabs accumulate across multiple presses of both buttons in one session and remain individually selectable.

## Deliberately deferred (not silently assumed)

- Exact cap on number of history tabs before scrolling/trimming — no hard limit decided, not a real design branch.
- Exact pacing of Simulated's staged reveal relative to Live's typical latency — implementation polish, not a decision needed up front.

## Further Notes (discovered during implementation)

- **The "guaranteed reject→replan narrative" for Simulated doesn't hold against real models.** Six real capture attempts, across three different forcing strategies, all failed to produce a genuine rejection:
  1. `build_seed_day1()`'s original bias (calibrated for the heuristic stand-in's naive price-first behavior) didn't work — the real Analyst's first-attempt instruction already says "weigh price against carbon," so it finds a good trade-off immediately; there's no naive first pass for the Reviewer to correct.
  2. Forcing a min-gap (hard-rule) rejection surfaced two real latent bugs in `llm_agents.py` (now fixed — see decision.py's `DayForecast.last_window_end` field and `llm_agents.py`'s candidate filtering): the Analyst's stateless replan call had no memory of its own prior proposal and would hallucinate one; the Reviewer had no visibility into which candidates were min-gap-excluded and would reject a valid window for being "dominated" by an actually-ineligible one. Once properly fixed, candidates are filtered before either model sees them — closing the bug, but also closing off this forcing mechanism, since the model now never proposes an ineligible window in the first place.
  3. A genuine Pareto-frontier dilemma (two within-cap options, neither dominating) still didn't produce disagreement — Analyst and Reviewer are both Claude models from the same family and apply similar cost-per-tonne judgment to the same information, so they tend to agree rather than genuinely disagree.
  - **Decision**: accept the real captured transcript as-is, whatever narrative it produces. User stories 7–8 in the parent issue are revised accordingly (see issue #6).
- The two `llm_agents.py` bugs found and fixed along the way are real correctness improvements independent of the fixture question — they also apply to a Live min-gap rejection (ticket #11), not just Simulated's capture.
