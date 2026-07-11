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

---

## Phase 2 — edge measurement (`reports/CELL-EDGE-MAP.json`)

**The capture-bias correction is the load-bearing methodological result.** Measured on the copyable
`entry_ask` alone, EVERY cell — the champion included — has a negative realizable LB (champion
−0.019). But that is the capture bias, not the truth: `entry_ask` is present only on the slow,
loser-tilted subsample. Confirming the brief §2 condition per cell, the **capture-haircut
(ask − at-fire mid on the SAME picks) is ≈0 everywhere** (champion +0.13¢, soccer +0.31¢, tennis
−1.05¢, 0.71–0.82 band −0.47¢) — so `entry_ask ≈ at-fire mid`, and the entire atfire-vs-ask-bracket
gap is **sample composition**, not the ask/mid spread. That vindicates the **at-fire mid on the FULL
population** as the unbiased realizable basis (also the handoff's headline basis and a fast-copier
proxy). `entry_ask` is reported as the conservative, capture-biased bracket only.

**On the vindicated at-fire basis (cluster-robust ROI-turn LB, match super-key):**

| cell | LB | boot LB | skill/blind | G | verdict |
|---|---|---|---|---|---|
| **CHAMPION favorite 0.71–0.98** | **+0.056** | +0.053 | +0.050 | 130 | positive, powered (5 regimes) |
| live_favorite **tennis** 0.71–0.98 | +0.075 | +0.076 | **+0.092** | 69 | beats champ; 3 wks all Wimbledon |
| live_favorite pooled **0.71–0.82** | +0.086 | +0.083 | +0.094 | 79 | beats champ; sub-band of champ |
| live_favorite **soccer** 0.71–0.98 | +0.027 | +0.025 | +0.033 | 29 | positive but WEAKEST half |
| pooled 0.82–0.90 / 0.90–0.98 | +0.008 / +0.030 | — | +0.021 / +0.035 | 61 / 41 | positive, deeper = thinner edge |
| baseball / basketball / esports / nonsport | +0.16 / +0.08 / −0.12 / −0.09 | — | — | 10 / 2 / 8 / 12 | all under-powered → INDETERMINATE |

**Replay cohorts (DIRECTIONAL, at the sharps' own fill = NON-copyable ceiling):** wider cohorts show
*more* directional edge — top40 +0.052, r41–100 +0.076, r101–250 +0.104, wide 1–250 +0.107 (G=680) —
but this is the sharps' price, not ours; the copyable (72h-tape) coverage is 4–25% over 3 days, so
none is realizably certifiable. A directionally-fatter wider cohort that we cannot copy certifies to ~0.

**Read:** the champion's edge is REAL and positive on the unbiased basis (+5.6% LB, +5.0% skill over
the blind favorite). The two cells that "beat" it — **tennis** and the **0.71–0.82 band** — are
SUBSETS of the champion pool (its strongest regime and its softest band), NOT new venues or
low-correlated complements; soccer (the bulk of picks) is the champion's WEAKEST component. No other
CATEGORY is powered; no wider COHORT is copyable. Phase 3 runs the anti-overfit battery (LODO,
time-split, Bonferroni, selection_null) + the champion head-to-head + correlation to decide whether
tennis/the-band is a durable, promotable refinement or the same summer-Wimbledon softness re-labeled.
