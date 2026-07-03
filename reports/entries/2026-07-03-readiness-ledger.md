# 2026-07-03 · WS-2 — the readiness ledger (distance to real money, on one board)

**One line:** fuses every gate (D6–D22) into one honest answer: **GO gates 2/4 · real-money eligible
FALSE · binding constraint = PERSISTENCE (months) · nearest lever = deploy dense capture.** This makes
"how far are we, and on what evidence" a single tracked number instead of a scattered set of verdicts.

## What was built
`scripts/readiness_ledger.py` — reads the instruments' own JSON artifacts (no re-computation) + a
couple of DB reads, and boards every gate: status, current value vs threshold, what's needed, ETA. The
binding constraint = the unmet **GO gate** with the longest horizon. `--selftest` PASS (overall-verdict
logic incl. "MET (caveat)" counting as met, binding = longest-ETA unmet).

## The board (today)

| gate | required | status | current | eta |
|---|:--:|---|---|:--:|
| edge_reality (λ) | ✓ | **INDETERMINATE** | coverage 0%, proxy λ̂_lo 0.08 | weeks |
| persistence | ✓ | **NOT_MET** | 5 event-day clusters (WC-heavy) | **months** |
| power | ✓ | MET (caveat) | 115 events; day-deflated SE ⊂ persistence | none |
| sizing | ✓ | MET | ⅟₁₂-Kelly pinned | none |
| copyability | | MET | favorite 69% survives, net +7.3% | none |
| pilot_harness | | BUILT | unarmed, place-path unreachable | none |
| operational | | NOT_MET | 0 trajectory rows | days |
| alt_thesis | | LEAD | 1 FDR-soft cell: soccer/dir/b5 fade | months |

## What it means
- **2 of the 4 real-money gates are already MET** (sizing, power-on-count). The two that aren't are
  the two that matter most: **edge_reality** (INDETERMINATE — λ not measurable until dense capture)
  and **persistence** (NOT_MET — 5 WC-heavy clusters vs ≥5 non-expiring regimes over months).
- **The binding constraint is persistence — months, calendar-gated, not something we can accelerate.**
  That is the honest timeline governor. No amount of modeling shortens it.
- **The nearest lever that unblocks progress is operational: turn on dense capture.** It doesn't clear
  a GO gate by itself, but it's the only way `edge_reality` becomes *measurable at all* — so it's the
  first domino. (Option B.)
- Run this weekly; it re-reads the artifacts and shows the gates flipping as data accrues.
