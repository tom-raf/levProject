# Handoff

Where this stands as of 2026-08-18, for picking back up tomorrow.

## What this project is

Grid Dispatch Loop — two AI agents (Analyst, Reviewer) decide when to charge a grid-scale battery by weighing live UK electricity price against grid carbon intensity. Full backstory/rationale in `docs/initial-plan/PLAN.md`; domain vocabulary in `CONTEXT.md`.

## What's built and verified (all committed, pushed to `origin/main`)

- `rules.py` — hard constraints (`check_rules`, `price_cap`), already existed before this session's build.
- `decision.py` — the single-day decision core: propose → check → replan-once → approve/unresolved. 5 passing tests in `test_decision.py`.
- `tools.py` — live/cached fetch for price (Octopus Agile) and carbon (Carbon Intensity API), with automatic live→cache fallback. Verified against the real APIs.
- `windows.py` — shared candidate-window arithmetic (4h rolling windows over 30-min slots).
- `simulate.py` — the 2-day simulated run (day 1 seeded to guarantee a reject→replan story, day 2 real fetched data), heuristic or real-LLM Analyst/Reviewer. Run with:
  ```
  .venv/bin/python -m pytest test_decision.py -v   # unit tests
  .venv/bin/python simulate.py                      # heuristic stand-in, no API cost
  .venv/bin/python simulate.py --llm                # real OpenRouter models
  ```
- `llm_agents.py` — real Analyst (`anthropic/claude-opus-5`) / Reviewer (`anthropic/claude-sonnet-5`) via OpenRouter. Verified working end-to-end with real credit.

**GitHub**: spec is issue [#1](https://github.com/tom-raf/levProject/issues/1) (open, parent — left open deliberately). Tickets #2–#5 (decision core, data tools, multi-day run, OpenRouter wiring) are all closed with verification comments.

## Key discovered constraint

Octopus Agile only publishes ~1 day ahead in practice (confirmed live). The multi-day loop was originally envisioned as 3–5 days; it's 2 days for real reasons, documented in `PLAN.md`'s "Data horizon" section. A "replay N real past days" option remains available if a longer demo is wanted later — not built.

## Environment

- `.venv/` has everything installed (`requirements.txt`: requests, python-dotenv, openai, pytest).
- `.env` holds `OPENROUTER_API_KEY` (rotated after an earlier accidental exposure in this session — the old key should be treated as dead). ~$5 credit loaded and confirmed working against real Opus/Sonnet calls.
- `.env`, `.venv/`, `.cache/`, `output/` are all gitignored.

## In progress: interactive dashboard (not built yet — this is tomorrow's work)

A designer (a separate Claude session) produced a high-fidelity static dashboard mockup, handed off in `design/design_handoff_dashboard/` (`levCell Dashboard.dc.html` + its own README). Reviewing it for feasibility, then a `/grill-me` session about it, evolved the scope significantly — from a static 2-day snapshot viewer into an **interactive dashboard with a live backend**. Full settled design and spec:

- `design/PLAN.md` — the locked design decisions (read this first).
- `design/SPEC.md` — user stories, implementation/testing decisions, seams, out-of-scope, based on the plan.

**The short version**: two buttons instead of static tabs — **Live** (a single real `decide_day()` call against a rolling today+tomorrow forecast horizon, streamed step-by-step via Server-Sent Events so you watch the agents reason in real time) and **Simulated** (instant replay of an already-captured real transcript from the seeded scenario — zero cost, zero API dependency, guaranteed to show the reject→replan story). History kept as tabs across presses. Needs a small Flask backend; the mockup's `.dc.html` format isn't runnable as-is (confirmed) — it's a visual spec to recreate in plain HTML/CSS/JS, not code to copy.

**Not yet resolved**: nothing design-wise — the grilling session reached an empty frontier and the spec is written. Next step is implementation, starting with `decide_day()`'s new optional `on_step` callback and the `build_rolling_forecast()` helper (the two seams from `design/SPEC.md`), then the Flask routes, then the frontend.

## Not yet committed

`design/` (mockup, `PLAN.md`, `SPEC.md`) and a stray `.DS_Store` are currently untracked — nothing lost, just not pushed yet. Worth committing before diverging further; `.DS_Store` should probably be added to `.gitignore` rather than committed.

## To resume tomorrow

Read `design/SPEC.md`, then start implementing per its Implementation Decisions section.
