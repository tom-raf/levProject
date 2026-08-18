# Handoff: levCell Dashboard

## Overview
Single-screen dashboard for levCell, a grid-scale battery dispatch system. Shows the AI-recommended charge window for the day, weighed against electricity price and carbon intensity, plus the Analyst/Reviewer agent transcript behind the decision.

## About the Design Files
The bundled `levCell Dashboard.dc.html` is a **design reference prototype** (streaming HTML component format), not production code to copy directly. Recreate this design in the target codebase's actual framework (React/Vue/etc., or your choice if none exists yet), using its existing component patterns, data fetching, and state management — treat this file as the visual/interaction spec, not a diff to merge.

## Fidelity
**High-fidelity.** Colors, typography, spacing, and layout are final. Data shown (prices, carbon, transcript text) is illustrative/mock — wire it to real telemetry.

## Aesthetic
"Creamy old technical drawing" style — cream paper background with a faint grid (drafting-paper texture), deep ink-blue linework, monospace/condensed-sans type, blueprint motifs (hatched fills, dashed leader lines, title block, corner brackets).

### Design tokens
- Background (cream): `oklch(96% 0.014 80)`
- Paper grid line: `oklch(90% 0.018 78)`
- Hairline/border: `oklch(80% 0.02 75)`
- Ink (primary text/lines): `oklch(24% 0.045 255)`
- Ink soft (secondary text): `oklch(46% 0.03 255)`
- Ink faint (tertiary): `oklch(60% 0.02 250)`
- Accent blue (price): `oklch(48% 0.12 250)`
- Accent copper (carbon): `oklch(56% 0.13 48)`
- Accent red (rejection/constraint marks): `oklch(50% 0.16 25)`
- Accent green (approved/ok): `oklch(50% 0.1 150)`
- Fonts: IBM Plex Mono (data/labels/body), IBM Plex Sans Condensed (large numerals/wordmark), both Google Fonts, weights 400–700
- Borders: 1–1.5px solid ink throughout; no shadows, no rounded corners
- Base grid unit: 28px (drafting-paper background grid)

## Screens / Views

### Dashboard (only screen)
**Purpose:** Operator checks today's recommended charge window, why the agents chose it, and how it trades price vs. carbon vs. constraints.

**Layout:**
- Full-bleed cream background, 1360px max-width content column, centered, 28px/36px page padding.
- Header row (flex, space-between, align to baseline): wordmark "LEVCELL" (34px, IBM Plex Sans Condensed 700, "CELL" in copper) + tagline, vs. a bordered "title block" widget (DWG NO. / DATE / REV rows in a 2-col grid, 70px label column).
- Day-tab row: one tab per simulated day, flex row, gap 2px, each tab a bordered rectangle; active tab gets inverted ink background + 3px copper bottom border.
- Row A: CSS grid `2fr 1fr` — (1) chart panel, (2) recommendation card.
  - Chart panel: bordered box, header with figure title + legend swatches, SVG line chart (900×220 viewBox) plotting price (solid blue line) and carbon (dashed copper line) across 48 half-hour slots, gridlines + hour ticks + dual y-axes (price left, carbon right), a hatched+dashed rectangle over the recommended window, hover crosshair + readout line below the chart.
  - Recommendation card: status dot + label, large window-start time (30px condensed), duration/end time, 2-up stat grid (avg price, avg carbon), price-cap footnote.
- Row B: CSS grid `1fr 1.3fr 1fr` — battery SOC gauge (two schematic "cell" bars, now vs. post-charge %), min-gap constraint diagram (SVG timeline: prev window end → +16h min-gap → eligible time → next window start), savings panel (two labeled progress bars: price premium vs. carbon saved, vs. price-only baseline, plus days-simulated/sent-back counters).
- Row C: full-width bordered panel, clickable header (toggles expand/collapse), body = vertical list of transcript entries (role label column 78px + colored left border + text), rejected entries shown dimmed with strikethrough.

**Colors/typography:** see Design Tokens above; all type is IBM Plex Mono except the wordmark and the big recommendation time (IBM Plex Sans Condensed).

**Content (verbatim mock copy):**
- Day tabs: "18 AUG 2026 — REV A", "19 AUG 2026 — REV B"
- Day A (18 Aug): status "APPROVED (SENT BACK x1)", window 10:00 for 4h → 14:00, avg price 26.00p, avg carbon 70g, price cap 25.10p. Transcript: rejected 03:00 proposal (22.10p, ~320gCO2) → Reviewer flags carbon → Analyst replans to 10:00 → Reviewer approves.
- Day B (19 Aug): status "APPROVED", window 09:30 for 4h → 13:30, avg price 22.48p, avg carbon 67g, price cap 23.67p. Transcript: Analyst explains solar-window pick is near-optimal; Reviewer confirms Pareto-optimality.
- Savings panel: "+5.57p/kWh" price premium, "+125 gCO2/kWh" carbon saved vs. a price-only baseline; "DAYS SIMULATED: 2", "SENT BACK: 1".

## Interactions & Behavior
- **Day tabs**: click switches the whole dashboard's data (chart series, recommendation card, battery %, transcript) to that day. Two days exist in the mock.
- **Chart hover**: mousemove over the SVG computes the nearest of 48 half-hour slots from cursor x-position, shows a vertical guide line + two dots (price/carbon) + a readout line below the chart with time, price, carbon values. Mouseleave clears it.
- **Transcript panel**: header is clickable, toggles expand/collapse of the transcript body; label switches between `[ + EXPAND ]` / `[ − COLLAPSE ]`. Defaults to expanded.
- No other navigation — single screen.

## State Management
- `selectedDayIndex` (0|1) — which simulated day is shown.
- `transcriptExpanded` (bool) — transcript panel open/closed.
- `hoverIdx` (number|null) — currently hovered chart slot (0–47), drives the crosshair/readout.
- Real implementation should replace the two hardcoded day objects with a fetch of N days' recommendations (window, avg price/carbon, price cap, status, transcript) plus the 48-slot price/carbon forecast series for the selected day.

## Assets
No image assets — all visuals (chart, battery gauge, min-gap timeline, hatch pattern) are inline SVG/CSS. Fonts loaded from Google Fonts (IBM Plex Mono, IBM Plex Sans Condensed).

## Files
- `levCell Dashboard.dc.html` — the full design (markup + interaction logic in one file).
