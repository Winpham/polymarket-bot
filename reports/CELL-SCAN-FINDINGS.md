# Generalize-the-Band-Strategy — findings log

Run: is there ANY other optimized profitability cell (category × sport × price-band × trader-cohort)
that matches/beats the champion `favorite` 0.71–0.98 at realizable, copyable, anti-overfit-survived,
per-dollar ROI? Both "a certified new cell + forward gate" and "no other cell generalizes — the
champion is singular, here is the proof" are success. Paper-only; promotes nothing.

---

## Phase 1 — cell map + power flags (`reports/CELL-MAP.json`)

**Coverage read.** The realizable cell space is far smaller than the nominal grid because
copyable entry only exists where a signal captured a leak-free `entry_ask` (the LIVE `favorite` arm)
or where the 72h `clob_price_tape` covers the convergence instant. The tape retains only
**2026-07-08 → 07-11 (3 days)**, and `consensus_eligible` is exactly the top-40 cohort, so **every
replay-only cohort/category cell is duration-capped to 3 realizable days and reads INDETERMINATE by
construction** — the same wall the soft-esports run hit. Match-clustered at the super-key (never
`event_slug`; soccer's 115 realizable picks are only **17 matches** of leg-piling), the ONLY
realizably-POWERED cell in the entire space is the **champion pool itself** (soccer+tennis favorite
0.71–0.98: 156 picks, **57 matches, 13 active days, 2 disjoint regimes** soccer-w26 + tennis-w26).
No single category×band sub-cell clears all three floors alone: **tennis 0.71–0.98** is the closest
(24 clean 1:1 matches, 7 days — clears volume+duration) but is a **single regime** (Wimbledon week),
and **soccer 0.71–0.98** leg-piles to 17 matches (below the 20-cluster volume floor). Replay cohorts
carry enormous *directional* volume (wide 1–250 cohort = **680 match-clusters**), but their
tape-realizable coverage is 4–25% over 3 days → none is durably measurable. Everything outside
soccer/tennis (baseball, basketball, esports, nonsport) is ≤7 realizable matches. The map already
tells the shape: **the answerable realizable question is confined to soccer + tennis; the cohort and
other-category axes are answerable only directionally (non-copyable ceiling), not at realizable cost.**
Phase 2 measures the edges; phase 3 runs the anti-overfit battery + champion head-to-head.
