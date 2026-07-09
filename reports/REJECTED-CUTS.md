# Rejected Cuts — negative slices that must NOT be excluded (anti-overfitting ledger)

A slice appears here when it is negative in-sample but has **no mechanism**, fails **OOS**, is
**below support**, or is a **field artifact**. Cutting anything here would be curve-fitting.

| slice | why negative-looking | why REJECTED |
|---|---|---|
| Stale `live recency_mins > 720` (58 bets, "+$589") | actually POSITIVE — but on a **look-ahead-contaminated** field | Live recency is updated post-fire toward resolution (corr +0.126 vs +0.043 at-fire). Not knowable at decision time → unimplementable forward + leaky. At-fire stale = 1 bet (non-axis). |
| Exact-score (60 bets) | §0 seed guessed −1.1% | Reproduces at **+1.49%, surplus +0.87%** — positive EV. Cutting positive bets to raise the mean ratio is textbook overfitting. |
| Freshness axis generally | §0 seed hypothesis #1 | Signals fire fresh (avg at-fire age 14 min; 1 bet >720). No forward-usable freshness variation exists in this book. |

_(Entries appended as the loop rejects further candidates.)_
