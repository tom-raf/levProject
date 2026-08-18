# Initial Plan — Grid Dispatch Loop

Status: **planning only** — nothing built yet. See [`grid-dispatch-loop.html`](./grid-dispatch-loop.html) for the architecture diagram this doc describes.

## What this is

A small demo for an interview at an electricity/battery/data-centre company. It shows two AI agents deciding *when* to charge a grid-scale battery (simulated as a data-centre asset, no fixed deadline) by weighing live electricity price against live grid carbon intensity, looped across several simulated days. A deferred-compute-load version (the data centre's own batch jobs) was considered and set aside — see "Deliberately left out."

## Why this problem

Electricity price and grid carbon intensity both swing hard over a day — UK Agile tariff rates move roughly 5–10x between the cheapest and most expensive half-hours, and grid carbon intensity swings 2–4x depending on wind/solar output at that moment. Anything with flexibility in *when* it draws power (a battery, a batch job) can save money and cut emissions by shifting to a better half-hour. This is a real, named practice in the energy industry ("demand response" / "load shifting"), and it's directly relevant to data centres, whose growing power demand means operators are increasingly asked to be flexible consumers rather than constant-draw ones.

The cheapest window and the cleanest window don't always match — that mismatch is the actual judgment call, and it's why this is framed as reasoning agents rather than a plain sort-and-pick script.

## Why two agents, not one

- **Analyst** proposes a window and has to explain the trade-off in plain language — a real ops person needs to trust and audit a recommendation, not just receive a timestamp.
- **Reviewer** checks that proposal against both hard rules (`check_rules()`, deterministic) *and* its own judgment of the trade-off's quality (e.g. a cheaper window exists but is carbon-heavy) — and can send it back once. The soft-judgment half is deliberate: a pure pass/fail gate could be a script, not an agent.

Worth being honest about: a plain algorithm could solve the narrow scheduling problem alone. The point of doing it as agents is the judgment call under competing constraints, the explanation, and the independent check — not raw optimization power.

## Architecture (see the diagram for the full picture)

```
Carbon Intensity API ──▶ get_carbon_forecast() ─┐
Octopus Agile API    ──▶ get_price_forecast()   ├─▶ Analyst
rules.py (constants) ──▶ check_rules()          │        │
                                    Reviewer ◀───┘   propose_window()
                          (hard gate + soft judgment)
                                    │  │
                        reject → replan ×1   approve → emit
                                    │              │
                                    └──▶ Analyst    ▼
                                              Recommendation
```

Looped once per simulated day (e.g. 3–5 days), reusing the same propose→check→replan→approve flow each time — not a continuous intraday scheduler. Model choice per agent is TBD (see "Open questions").

- **Data:** two public, unauthenticated UK energy APIs — verified live while scoping this — plus a local `rules.py` of plain constants (price cap, allowed window, min gap, charge duration). The rules file is not an API and is checked in code, not by a model. Both APIs return 30-minute-granularity data.
- **Tools:** thin wrappers around the two APIs, plus one that reads `rules.py`. No logic beyond fetch/parse/return. Both a live path and a disk-cached path are implemented with an easy switch — live is primary for the actual interview, cache is the fallback if live fails, and the sole path for rehearsal runs.
- **Agents:** two LLM calls per simulated day.
- **Output:** one markdown brief per simulated day, plus a short end-of-run rollup (days simulated, count sent back, avg price/carbon saved vs. a price-only baseline) — the same handover a human ops analyst would give at shift change.

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python | fastest path to something runnable in 2 days |
| Model access | **TBD** — likely OpenRouter, possibly Anthropic API direct | pending; see "Open questions" |
| Analyst model | **TBD** | pending model-provider decision |
| Reviewer model | **TBD** — leaning toward a stronger model than a narrow rule-checker now that Reviewer does soft judgment, not just a pass/fail gate | pending model-provider decision |
| Orchestration | plain Python, no agent framework (line count TBD — grew since the original ~30-line one-shot estimate once the multi-day loop, live/cache switch, and soft-judgment handling were added) | control flow — propose → check → reject-once → approve, looped per day — stays visible in one file, not hidden behind a framework abstraction |
| Data sources | `api.carbonintensity.org.uk` (National Grid ESO), `api.octopus.energy` (Agile tariff) | both free, unauthenticated, real UK utility-grade data — no mocking; both confirmed live at 30-minute granularity |
| Output | stdout trace + one markdown brief per simulated day + end-of-run rollup | no dashboard, no database — a printed trace is easier to narrate live than a UI |

## Deliberately left out (for the 2-day timeline)

- Battery state-of-charge modelling — real engineering, zero agent content (min-gap is a wall-clock timestamp check, not an SOC model)
- More than one reject/replan round — one shows the mechanism just as well
- A dashboard UI — a printed trace is easier to narrate live
- A third data source — two signals (price, carbon) is enough to show a genuine trade-off
- The deferred-compute-load (batch job) task type — grid-scale battery only for the core demo; see Extensions below
- Continuous intraday scheduling, and exposing the search process live — see Extensions below

## Extensions (stretch goals if time allows, not core scope)

- Exposing the Analyst's search process live — walking through each candidate window and narrating why it's kept/rejected, instead of only returning the final answer. This is the more interesting "why agents, not a script" story if there's time to build it.
- The deferred-compute-load axis (the data centre's own batch jobs, with an invented soft priority/SLA input) as an alternative or additional task type to the battery.

## `rules.py` constants (resolved)

- `price_cap`: 25th percentile of that simulated day's quoted Agile prices — derived per day, not hardcoded, since a fixed p/kWh number would already be stale by the interview
- `allowed_window`: bounded only by the forecast horizon (~24–48h ahead, matching API data availability) — no time-of-day restriction, since there's no real deadline for a grid-scale battery
- `charge_duration_hours`: 4 — matches the most common real UK utility-scale BESS configuration
- `min_gap_hours`: 16 — wall-clock hours required between the end of one recommended window and the start of the next

Day 1's seed state: cheapest window and cleanest window don't overlap, and the Analyst's first proposal overweights price — giving the Reviewer a genuine, explainable reason to send it back once, rather than a contrived rule trip.

## Open questions before building

- **Model provider and tiering** — likely OpenRouter (a few pounds of credits going on tomorrow), possibly Anthropic API direct. Reopens Analyst/Reviewer model choice and whether the orchestration can still use a ready-made tool-use loop or needs one hand-rolled.
- `ANTHROPIC_API_KEY` confirmed **not set** in this environment — only relevant if the Anthropic-direct path is chosen
