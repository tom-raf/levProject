# Spec — Grid Dispatch Loop demo pipeline

Published as [github.com/tom-raf/levProject#1](https://github.com/tom-raf/levProject/issues/1) (`ready-for-agent`).

## Problem Statement

There's a need for a working demo, relevant to an electricity/battery/data-centre company's operations, showing two AI agents reasoning about *when* to charge a grid-scale battery — a genuine judgment call under competing constraints (price vs. carbon), not a sort-and-pick script. Right now only the design is settled (`docs/initial-plan/PLAN.md`, `CONTEXT.md`, `rules.py`) — none of the orchestration, data-fetching, or agent code exists yet, and the demo needs to run reliably live, with a cache fallback in case the network misbehaves on the day.

## Solution

Build the pipeline described in `CONTEXT.md`/`PLAN.md`: an **Analyst** proposes a 4-hour charge **Window** for a simulated day by weighing live UK electricity price against grid carbon intensity; a **Reviewer** checks it against both the hard constraints in `rules.py` (already built) and its own judgment of the trade-off's quality, and can send it back once. This runs once per simulated day across several days, producing a **Recommendation** (markdown brief) per day plus an end-of-run rollup. Model provider/tiering is explicitly out of scope for this spec (see Out of Scope) — the pipeline should be built so that plugging in the Analyst/Reviewer model calls is the last step, not a prerequisite for everything else.

## User Stories

1. As the presenter running the live demo, I want the system to fetch live price and carbon data by default, so that the demo uses real, current numbers when narrating it.
2. As the presenter, I want an easy switch to a pre-fetched disk cache, so that a live API outage or rate limit during a live run doesn't derail the demo.
3. As the presenter, I want the cache to cover the full multi-day simulated window, so that switching to cache mid-demo doesn't leave later simulated days without data.
4. As the presenter, I want each simulated day to produce a one-page markdown brief, so that I can hand it over exactly as a human ops analyst would at shift change.
5. As the presenter, I want an end-of-run rollup (days simulated, count sent back, average price/carbon saved vs. a price-only baseline), so that the repetition across days adds up to a demonstrable result, not five disconnected printouts.
6. As the Analyst, I want to see that simulated day's price forecast and carbon forecast, so that I can propose the cheapest-and-cleanest available 4-hour Window.
7. As the Analyst, I want to explain my proposed Window's trade-off in plain language, so that a human reviewing the brief can audit *why* this window was picked over others.
8. As the Analyst, I want to receive the Reviewer's rejection reason when a Window is sent back, so that my replanned proposal actually addresses what was wrong with the first one.
9. As the Reviewer, I want to run the proposed Window through `check_rules()` (price cap, min-gap), so that hard constraint violations are caught deterministically, not by model judgment.
10. As the Reviewer, I want to also judge the trade-off's quality even when hard rules pass, so that a technically-legal but poor trade-off (e.g. barely under the price cap in a high-carbon slot) gets a real second look, not a rubber stamp.
11. As the Reviewer, I want to send a Window back to the Analyst exactly once, so that the demo shows a bounded reject→replan cycle rather than an open-ended argument.
12. As the presenter, I want a Window that's still rejected after the one allowed replan to be emitted anyway and flagged "unresolved — needs human review", so that the demo never hard-crashes live and shows the system knowing its own limits.
13. As the presenter, I want day 1's data seeded so the cheapest Window and the cleanest Window don't overlap and the Analyst's first proposal overweights price, so that the Reviewer has a genuine, explainable reason to send it back on the very first simulated day.
14. As the presenter, I want the price cap recomputed per simulated day (25th percentile of that day's quoted prices), so that the constraint reflects that day's actual price shape rather than a number that's already stale.
15. As the presenter, I want the min-gap rule enforced as wall-clock hours between the end of one recommended Window and the start of the next (not tied to any battery state-of-charge), so that back-to-back windows across "different" simulated days are still caught if they land close together in real time.
16. As the presenter, I want the multi-day loop to reuse the exact same single-day decision logic each iteration, so that the control flow stays visible in one place rather than duplicated per day.
17. As a future maintainer, I want the Analyst and Reviewer to be swappable behind a simple interface, so that plugging in the eventual model provider (OpenRouter or Anthropic direct) doesn't require touching the orchestration or rules logic.
18. As a developer testing this system, I want to inject scripted Analyst/Reviewer responses at the single-day decision seam, so that I can exercise approve-first-try, soft-reject-then-approve, soft-reject-twice-unresolved, and hard-rule-violation scenarios without calling a real model or a real API.

## Implementation Decisions

- **`rules.py`** (already built, treat as settled): `price_cap(day_prices)` returns the 25th percentile of that day's prices; `check_rules(window, day_prices, last_window_end)` returns a list of violated hard constraints (price cap, `MIN_GAP_HOURS` = 16, wall-clock only); `CHARGE_DURATION_HOURS` = 4; `ProposedWindow` dataclass (`start`, `avg_price`).
- **Data tools**: thin wrappers around `api.carbonintensity.org.uk` and `api.octopus.energy` — fetch/parse/return only, no logic. Both a live path and a disk-cache path exist behind one switch (env var or flag); live is primary, cache is the fallback on failure, and cache is the only path during rehearsal. The cache must be pre-populated to cover the entire multi-day simulated window before a live demo run.
- **Analyst interface**: a callable taking a simulated day's price/carbon forecast (and, on a replan, the Reviewer's rejection reason) and returning a `ProposedWindow` plus a plain-language explanation string. Model/provider is an implementation detail behind this interface, not decided here.
- **Reviewer interface**: a callable taking a `ProposedWindow`, the `check_rules()` violation list, and the day's forecast, returning an approve/reject decision plus a plain-language reasoning string (covering both hard-rule violations and soft judgment). Model/provider likewise deferred.
- **Single-day decision seam**: one function taking a day's forecast data, the Analyst callable, the Reviewer callable, and `last_window_end`, implementing propose → check (hard + soft) → replan once on reject → approve or unresolved. Returns a `Recommendation` (Window, explanation, status: approved/unresolved). This is the seam the test suite exercises.
- **Multi-day loop**: iterates a configurable number of simulated days (e.g. 3–5), threading `last_window_end` forward between iterations, calling the single-day seam each time, collecting `Recommendation`s.
- **Output**: one markdown brief per simulated day (Window, explanation, approved/unresolved status) plus an end-of-run rollup (days simulated, count sent back, avg price/carbon saved vs. a price-only baseline), printed to stdout and written to file(s).
- **Seed state**: day 1's forecast data is constructed (not fetched live) so that the cheapest and cleanest 4-hour windows don't overlap and the Analyst's unassisted first proposal favors price — giving the Reviewer's soft judgment a real, narratable reason to reject once.

## Testing Decisions

- Good tests here exercise only external behavior at the single-day decision seam: given a day's forecast and *injected* Analyst/Reviewer responses, assert the resulting `Recommendation` — not the internals of how the Analyst or Reviewer arrived at their answer (that's model behavior, out of scope for unit tests).
- Modules tested: the single-day decision function (new), and `rules.py`'s `check_rules()`/`price_cap()` directly (already deterministic and directly testable, no seam needed).
- Scenarios to cover at the seam: approve on first proposal; soft-reject then approve on replan; soft-reject twice → emitted unresolved; hard-rule violation (price cap or min-gap) → reject, with the replanned proposal satisfying the rule.
- No test hits a real API or a real model — Analyst/Reviewer are fakes returning scripted `ProposedWindow`/decision values per scenario.
- Prior art: none — this is a greenfield repo with no existing test suite to match conventions against.
- The fetch/cache layer and the multi-day loop's glue code are not directly unit-tested at this seam, consistent with the doc's own scoping of tools as "no logic beyond fetch/parse/return."

## Out of Scope

- Choosing or wiring a specific model provider/SDK (OpenRouter vs. Anthropic direct) and the resulting Analyst/Reviewer model choice — explicitly deferred by the user to a separate follow-up. This spec builds the Analyst/Reviewer *interfaces* only.
- Battery state-of-charge modelling.
- More than one reject/replan round.
- A dashboard UI.
- A third data source beyond price and carbon intensity.
- The deferred-compute-load/batch-job task type (noted only as a possible future extension, not built here).
- Continuous intraday scheduling and exposing the Analyst's search process live (both noted as possible future extensions, not built here).

## Further Notes

- `CONTEXT.md` and `rules.py` already exist in the repo root and should be treated as settled vocabulary/logic, not re-derived.
- `docs/initial-plan/PLAN.md` documents the full design history and rationale behind every decision above; this spec operationalizes it into buildable work.
- Once the model-provider decision lands, a follow-up ticket should wire the actual Analyst/Reviewer model calls behind the interfaces built here.
