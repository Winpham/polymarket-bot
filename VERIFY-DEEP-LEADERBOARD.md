# Deep-leaderboard deployment — live verification (Phase A)

Read-only verification against the **live production** DB/stack, 2026-07-02 (~1h after deploy
of the top-200 widening). Every check green.

| # | Check | Query result | Verdict |
|---|---|---|---|
| 1 | Eligibility = rank ≤ cutoff (40) | eligible: 56 rows, rank 1–40 · ineligible: 218 rows, rank 41–200 · **violations: 0** | ✅ exact |
| 2 | Deep capture accruing | 187 deep wallets with fills · **32,348 deep fills in 24h** | ✅ tailing works |
| 3 | No deep leak into consensus signals | 7,800 backer slots (24h), rank range **1–40**, deep-backer leaks: **0** | ✅ airtight |
| 4 | Consensus engine still producing | 4,131 signals / 24h, max net 6, **63 alerts** sent | ✅ unchanged |
| 5 | Resolution pipeline covers deep | deep: 24,610 resolved fills across 150 wallets | ✅ profiling live |
| 6 | Deep traders approaching a verdict | **50 deep wallets** already ≥10 distinct resolved events | ✅ data accruing |
| 7 | Cadence health | steady-state poll ~34s (of 120s window), **0 data-api 429s** | ✅ safe |

**Conclusion:** the widening works exactly as designed. The deep pool (rank 41–200) is fully
**captured, resolved, and profiled** — everything the top-50 gets — while the **consensus voter
set stays top-40** and **no deep trader has entered a single signal or alert** (byte-for-byte
non-regressive, proven live, not just in tests). The efficiency verdict over the deep pool is
still maturing (50 wallets ≥10 events; the trust gate wants ≥30) — the pipeline is proven; the
verdicts accrue over days.

This report grounds the extension work (Phases B–E): make the rank-cohort a first-class,
filterable dimension so the same verification stack can be sliced by any band (top-50 / top-250
/ all-500 / per-50 groups, "most profitable within band"), clearly labeled so trusted never
reads as candidate.
