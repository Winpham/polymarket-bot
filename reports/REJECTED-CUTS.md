# Rejected Cuts — negative slices that must NOT be excluded (anti-overfitting ledger)

A slice appears here when it is negative in-sample but has **no mechanism**, fails **OOS**, is
**below support**, or is a **field artifact**. Cutting anything here would be curve-fitting.

| slice | why negative-looking | why REJECTED |
|---|---|---|
| Stale `live recency_mins > 720` (58 bets, "+$589") | actually POSITIVE — but on a **look-ahead-contaminated** field | Live recency is updated post-fire toward resolution (corr +0.126 vs +0.043 at-fire). Not knowable at decision time → unimplementable forward + leaky. At-fire stale = 1 bet (non-axis). |
| Exact-score (60 bets) | §0 seed guessed −1.1% | Reproduces at **+1.49%, surplus +0.87%** — positive EV. Cutting positive bets to raise the mean ratio is textbook overfitting. |
| Freshness axis generally | §0 seed hypothesis #1 | Signals fire fresh (avg at-fire age 14 min; 1 bet >720). No forward-usable freshness variation exists in this book. |

_(Entries appended as the loop rejects further candidates.)_

## Appended by the loop (iter 1–3)

| slice | why negative-looking | why REJECTED |
|---|---|---|
| pay-up `entry_ask−p ∈ [0.01,0.03]` (45 bets, −5.9%) | wide-ask premium | **Subsumed by liquidity**: −0.2% inside the liquid (≥$1k) subset. The penalty is a thin-market artifact, not an independent axis. |
| "other" / non-core-sport regime (15 bets, −16%) | non-core venues | **Subsumed by liquidity**: +14.9% inside the liquid subset. Only the *thin* "other" bets lose. |
| obscure-league blacklist `col/ucl/swe/chi` (7 bets) | §0 seed guess | `chi` is a **winning** soccer league (+29%) mislabeled by the seed; real losers ucl/col/swe are **n=5 (below support)** and are a liquidity/coverage proxy already handled by the floor. A league blacklist is less general than the liquidity mechanism. |
| price 0.95–1.00 extreme-favorite (n=14 in keep-set, −3.8%) | FLB tax | Below support (n=14) and surplus only −0.9% (composition, not selection). Cutting the band top is a knife-edge tune, not a mechanism. |
| best_backer_rank<10 as the boundary (vs <5) | codebase elite=10 precedent | Keeps the **worst** bin (rank 5–9, −8.3%); belief-blind p_emp=0.0025 fails Bonferroni (~40 tests → 0.10). rank<5 is the mechanism-correct boundary (rank≥5 net-negative). |
