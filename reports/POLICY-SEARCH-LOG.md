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
