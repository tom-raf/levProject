# Grid Dispatch Loop

A demo scheduling when a grid-scale battery should charge, by weighing electricity price against grid carbon intensity.

## Language

**Window**:
A 4-hour candidate charge block for the battery, bounded only by how far ahead the price/carbon forecasts reach — not by time-of-day. There is no fixed deadline (this is a grid-scale asset, not a home/EV battery).

**Analyst**:
The agent that proposes a Window for a given simulated day and explains the price/carbon trade-off behind it in plain language.
_Avoid_: Proposer, scheduler

**Reviewer**:
The agent that evaluates a proposed Window against both the hard constraints in `rules.py` and its own judgment of the trade-off's quality (e.g. a cheaper Window exists but is carbon-heavy). Can send a Window back to the Analyst once. If still unresolved after that replan, the Recommendation is emitted anyway, flagged unresolved.
_Avoid_: Approver, validator

**Min-gap**:
The minimum wall-clock hours required between the end of one recommended Window and the start of the next, regardless of which simulated day each belongs to. A timestamp check only — the battery's actual state of charge is out of scope.

**Recommendation**:
The output of one simulated day's decision: the approved (or unresolved-flagged) Window plus the Analyst's plain-language explanation, written as a one-page markdown brief.
_Avoid_: Result, output
