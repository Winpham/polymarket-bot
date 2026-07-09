# Policy-Search Log — favorite-book exclusion/refinement (RUN-GARBAGE-EXCLUSION-FILTERS)

Read-only, paper-only. Corrected fee = sports `0.03·p(1−p)` entry-only, maker 0. Turnover = $100/bet.
Belief-blind surplus = event-clustered mean of `(won−entry) − blind_edge[band]` (selection_null statistic).
All forward-applicable axes use **at-fire `initial_*` fields** (decision-time, zero look-ahead).

---

## ITER 0 — Reproduce base forensics + MATERIAL DISAGREEMENT WITH §0 (checkpoint)

`scripts/garbage_segments.py` → `reports/GARBAGE-SEGMENTS.json`. Full book reproduces the
RUN-HARDEN anchor exactly: **215 bets, +2.81% taker** (stake-wtd +3.45%), win 84.7%.

### §3 STOP-AND-REPORT: the §0 seed table does NOT reproduce; two seeds are artifacts.

| §0 seed (in-session read) | §0 claim | AT-FIRE (forward-valid) reality | Verdict |
|---|---|---|---|
| Stale `recency>720` | 4 bets, 0% win, −$408 | **1 bet** at-fire (signals fire fresh, avg age 14 min). The "58 bets +$589" only appears on the **LIVE `recency_mins`** field, which is **look-ahead contaminated** (updated post-fire toward resolution; corr-with-outcome +0.126 vs +0.043 at-fire, avg 687 vs 14 min). | **Seed INVERTED / non-axis.** Freshness is not a usable exclusion axis for this book. A cut on live recency is unimplementable forward and leaky. |
| Thin `total_usd<$1k` | 71 bets, −4% | **19 bets, −11.25%, surplus −12.17%** on at-fire `initial_total_usd`. (Live field dilutes to +2.3%.) | **Seed CONFIRMED (stronger)** — real negative with negative belief-blind surplus. |
| Obscure `^(col\|ucl\|swe\|chi)-` | 6 bets, −35.7% | 7 bets, −29.9%, surplus −30.6% | Confirmed but low support (n=7); likely a liquidity/sport proxy — test subsumption. |
| Exact-score | 60 bets, 93% win, −1.1% | 60 bets, **+1.49%**, surplus +0.87% | **Seed REJECTED** — exact-score is *not* garbage; cutting it is curve-fitting. |
| Crude "exclude all four" | 105 bets, +$835, **+7.9%** | at-fire: 131 bets, +6.12%, +$802 — but this includes cutting **positive** exact-score bets, which inflates the ratio without a mechanism. | The "+7.9% existence proof" was a **field artifact** (kept the leaky-stale winners, cut positive exact-score). Honest lift comes only from removing the genuinely negative thin+obscure slices. |

**Consequence for the run:** the seeds were guesses (as the brief states) and two are wrong. The
mission stands but re-grounded: the real garbage is **illiquidity-driven**, not staleness or
exact-score. Proceeding on at-fire fields only. No cut will ever be adopted on the leaky live fields.

### Honest multi-axis negative slices (at-fire, corrected fee), ranked by $-drag × mechanism-confidence

| slice | n | ROIt | surplus | $drag | mechanism | confidence |
|---|---|---|---|---|---|---|
| `initial_total_usd < 1000` | 19 | −11.25% | −12.17% | −$214 | illiquidity / unfillable | HIGH |
| `entry_ask − p ∈ [0.01,0.03]` (pay-up) | 45 | −5.96% | −10.03% | −$268 | chasing / negative CLV at fill | MED |
| obscure leagues (col/ucl/swe) | 5 | ≈−45% | ≈−45% | −$267 | thin coverage (liquidity proxy?) | MED, low-n |
| best_backer_rank 5–20 (at-fire) | 67 | ≈−9% | ≈−7% | −$590 | UNCLEAR — **non-monotonic** (rank 20–50 = +27.7%) | LOW (confound risk) |
| regime "other" / nba/cbb | 15 | −16% | −17% | −$240 | non-core sport (liquidity proxy?) | MED, low-n |

Positive slices to PROTECT (do not cut): exact-score, price 0.75–0.80 (+16.8%), 0.90–0.95 (+7.5%),
2500–5000 backing (+12%), rank<3 & 3–5, ask within ±1¢ of consensus (+5.3%).

**Next (ITER 1):** subsumption test — does a liquidity floor absorb obscure-league + "other"-regime?
Then sweep the liquidity threshold on a plateau; test whether pay-up and rank are independent
negatives or confounded with liquidity. OOS = time-split + non-FIFWC. Multiple-testing corrected.

---

## ITER 1 — Liquidity floor (ADOPT). Mechanism: illiquidity.

Sweep `initial_total_usd` (covered subset n=157; nulls kept, unevaluable in-sample, apply forward):

| floor | n_keep | roi_keep | n_cut | roi_cut | drag_removed |
|---|---|---|---|---|---|
| 250 | 152 | +0.82 | 5 | **+7.21** (cuts WINNERS) | +36 |
| 500 | 145 | +1.82 | 12 | −8.61 | −103 |
| 750 | 141 | +2.37 | 16 | −10.88 | −174 |
| **1000** | **138** | **+2.71** | **19** | **−11.20** | **−213** |
| 1500 | 130 | +2.77 | 27 | −7.41 | −200 |
| 2000 | 123 | +3.37 | 34 | −7.47 | −254 |

**Plateau 750–1500** (roi_keep +2.4…+2.8, stable). Below $500 cuts winners; above $1500 eats
marginal-negative (−2.7%) bets to chase the ratio → overfit. **Adopt floor = $1000** — the round
"< $1k sharp backing = thin" value, at the most-negative removed set (−11.2%, surplus −12.2%).
On the full 215-book this lifts +2.81% → **+4.17%**; OOS: late +2.61, non-FIFWC −1.02 (from −2.08),
removed set negative in **every** fold. **ADOPTED.**

## ITER 2 — Require top-5 backer (ADOPT). Mechanism: backer skill. Confounds cleared.

Rank sweep (cut = best_backer_rank ≥ thr): plateau at thr∈{3,4,5} (roi_keep +6.8…+7.4), knee at 5→7.
Confound table (at-fire, rank present):

| rank bin | n | avg_price | avg_iusd | %soccer | ROIt |
|---|---|---|---|---|---|
| rank<5 | 85 | 0.818 | 62.7k | 71 | **+7.20** |
| rank 5–9 | 38 | 0.816 | 68.2k | 82 | **−8.32** |
| rank≥10 | 34 | 0.800 | 69.2k | 53 | −3.97 |

Rank is **not** a price proxy (prices identical), **not** a liquidity proxy (backing identical),
**not** a sport proxy (rank 5–9 is *more* soccer yet loses worst). Within every price band, weak
rank underperforms elite. Two INDEPENDENT mechanisms (liq∩rank overlap = 8 bets). Boundary is at 5
(rank≥5 net-negative). **Adopt require `best_backer_rank < 5`.** Removes ~39% volume — aggressive,
but every fold's removed set is negative and every fold's keep set is positive.

## ITER 3 — Reject the remaining candidates (subsumed / positive / below-support).

- **exact-score**: +1.49%, surplus +0.87% → POSITIVE. REJECT (cutting it is curve-fitting).
- **pay-up ask−p∈[.01,.03]**: −5.9% all → **−0.2% inside the liquid subset** → SUBSUMED by liquidity.
- **"other"/non-core regime**: −3.9% all → **+14.9% inside liquid subset** → SUBSUMED by liquidity.
- **obscure league (col/ucl/swe/chi)**: `chi` is +29% (a winning soccer league, mislabeled by the
  seed); only ucl/col/swe lose (n=5, **below support**) → REJECT as its own cut.
- **freshness**: non-axis (signals fire fresh) + live field is leaky. REJECT.

## CONVERGENCE — `favorite_v2` = liquidity ≥ $1000 AND best_backer_rank < 5

| metric | champion `favorite` | `favorite_v2` (converged) |
|---|---|---|
| bets (ledger, at-fire) | 215 | 132 (−39% vol) |
| resolved ROI (taker, corrected fee) | +2.81% | **+9.66%** |
| OOS time-late | +0.97% | **+8.10%** |
| **OOS non-FIFWC** | **−2.08%** | **+7.63%** (FLIPS positive) |
| belief-blind surplus (ledger pop) | +2.85% | **+10.84%** |
| belief-blind z / p_emp / LB | 1.13 / 0.13 / −1.07% | **3.60 / 0.0000 / +5.86%** |

Belief-blind gate (in-sample): p_emp=0.0000 clears Bonferroni (~40 slice-hypotheses tested →
40×(1/2000) ≈ 0.02 < 0.05); LB +5.86% > 3% margin. Removed set negative in all 4 folds.

**Power limitation (honest):** the "≥2 disjoint non-soccer regimes positive" clause is NOT met
in-sample — only tennis (n=14, +16.1%) is positive at support; mlb (n=3) and other (n=7) are below
support. So the belief-blind gate's regime clause is **power-limited**, exactly the champion's own
binding constraint. → `favorite_v2` earns a SHADOW slot + forward gate, promotes nothing.

## RESIDUAL SCAN (converged keep-set, n=132) — §6 stop condition MET

`policy_search.py --residual`: **0 structural negative slices at power (n≥20)**. Only below-support
negatives remain (price 0.95–1.00 FLB tax n=14; extreme pay-up n=9) — power-limited / irreducible.
The loop stops: no defensible cut beyond {liquidity, rank} survives OOS + support + mechanism.

---

## ITER 4 — Decouple + weight-not-cut (Tue's critical review, 2026-07-09)

Tue's steer: **don't cut volume / don't regress; recognize higher-profit areas by WEIGHTING**, and
decouple the trustworthy liquidity claim from the fraught rank claim. Decomposition:
- liquidity floor ALONE: +2.81% → **+4.17%** (~+1.4pp, keeps 91% volume) — the trustworthy part.
- adding `rank<5`: +4.17% → +9.66% (~+5.5pp) but cuts **39% volume** — an "only follow top-5" strategy.

### `policy_search.py --weight` — full-volume tilt vs flat vs exclusion

| scheme (100% volume) | ROI_full | ROI_late | ROI_nonFIFWC |
|---|---|---|---|
| flat (baseline) | +2.81% | +0.97% | −2.08% |
| liquidity-tilt | +2.82% | +2.22% | −3.07% |
| top5-bonus tilt | +4.44% | +2.65% | −2.69% |
| liq×top5 tilt | +5.68% | +4.36% | −2.24% |
| **favorite_liq (exclude, 91% vol)** | **+4.17%** | +2.61% | **−1.02%** |
| favorite_v2 (exclude, 61% vol) | +9.66% | +8.10% | +7.63% |

**Findings:**
1. **Weighting keeps volume but recovers only ~half the lift** (+5.68% combined) AND **no tilt
   reproduces the non-FIFWC flip** (all stay −2…−3%). The +7.63% appears only when you *exclude* the
   few tennis-carried rank≥5 non-soccer bets → it is SELECTION, not a sizeable edge you can size into.
   This is the quantified version of the Wimbledon worry.
2. **For liquidity, exclusion beats tilting** (thin books are junk — remove, don't downweight):
   favorite_liq +4.17%, non-FIFWC −1.02% (improves), 91% volume kept. Trustworthy + minimal cost.

### Decision (revised)
- **Register `favorite_liq` (liquidity-only) as the primary decoupled shadow arm** — the "cut the
  garbage" arm Tue actually asked for: small cut, mechanism-clean, helps OOS.
- **Keep `favorite_v2` (liq+rank) as a shadow ONLY to let the forward gate rule on rank** — billed
  UNPROVEN + historically fraught (refuted rank axis, non-monotonic, tennis-carried), NOT a validated
  +9.66%. See PREREG for the two claim-breakers (durability-past-tournaments, fire-rate/capacity).
- **Rank-weighting is NOT baked into a live arm.** A rank tilt only matters at the sizing layer
  (paper ledger is flat $100, so a WeightMode change is inert in P&L), and the tilt failed the OOS
  durability test. Deferred as a forward-gated sizing-overlay PROPOSAL, not built — avoids
  re-concentrating stake on the same fraught rank noise before the forward gate rules.
