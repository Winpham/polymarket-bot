# Deep universe: 250 → 1000 (2026-07-13)

**Branch:** `feat/deep-universe-1000` (commit `be280e5`) — **not merged, not deployed.**
Prod autoupdates from `main`, and this changes the primary ingestion path, so the merge
and the `TRACK_DEPTH` flip are yours to make.

**Ask:** expand the top-250 ingestion to handle 1000, fast and reliably.

**Verdict:** depth 1000 is comfortably feasible — capacity was never the constraint. But
it was blocked by a **live, silent data-loss bug in the ingestion path**, which widening
would have amplified across 800 new wallets. That is fixed, and the fix is the bulk of
this work.

---

## 1. The bug: the poll never filtered by time at all

`poll_trader_activity` requested `/activity?user=…&type=TRADE&startTs=<cursor>`.

**`startTs` is not a real parameter.** The data-api silently ignores it (the honoured
ones are `start`/`end`). With no time filter and no `limit`, every poll returned **the
newest 100 events, regardless of the cursor** — and `consensus_cycle` then stamped the
cursor to `now`, so everything older was skipped **permanently**.

This was already known — `fetch_full_history` (the backfill lane) carries the comment
*"`startTs` is silently ignored by the data-api; `offset`/`limit=500` and `start`/`end`
DO work, verified live 2026-07-03"*. The consensus poll — the primary lane — was never
fixed.

### Blast radius — corrected against the live DB (read this, not the first draft)

My first draft of this report claimed the bug had destroyed 96.8% of first-sight history
and implied prior research sat on corrupted capture. **I checked against the production
database, and that is wrong. The archive is intact.** The correction:

**What is true in isolation:** if the poll were the *only* ingestion path, it would lose
96.8% of a busy wallet's 48h history (measured: 32 wallets, ranks 1–1000, 50,887 true
events vs the 1,622 the old poll could return).

**Why that did not happen in practice — two things rescue it:**

1. **Steady state was never lossy.** `/activity` returns one event per *fill*, and even
   the busiest wallet in the universe generates only ~8 events/min. At 1-min cadence the
   newest-100 page reaches back ~12 minutes — comfortably more than the delta. Verified
   against the live DB over the last 6h: **0% missing** on the rank-1 HFT wallet, a
   rank-131 deep wallet, and a rank-71 wallet.
2. **The `backfill` mode (separate binary mode) uses the CORRECT params** and has been
   run. `trader_fills` holds 2.7M rows going back to 2022 across all three bands.

**So the real exposure is narrower, and it is still worth fixing:**

- **Any gap > ~12 min permanently loses the busiest wallets' trades.** Deploys, restarts,
  crashes. The cursor advances to `now` regardless, so the hole never heals.
- **First sight of a new wallet** is only rescued by someone *remembering to manually run
  the backfill mode* — precisely the wrong thing to depend on when onboarding 800 new
  wallets at once.
- **Cadence stretch at depth 1000** widens the delta, which widens the hole.

The fix makes the poll self-healing and removes the dependence on a manual step. That is
its real value — not a catastrophe averted.

> This is the same defect class as D1–D4: **a bounded budget plus a bad order is
> starvation.** Here the budget was an unadvertised 100-row page and the order was
> newest-first. Every bounded queue in this system deserves the same audit.

## 2. The fix: cursor on *coverage*, not on recency

`poll_trader_activity` now drains a bounded `[start, end]` **window** using the real
params (DESC + `offset`, `limit=500`), and returns `covered_through`: the instant
through which coverage is **complete**.

The invariant — stated as a pure, tested function, `cursor_target()`:

> **Never advance a cursor past a range you did not fully read.**
> Complete window → `now`. Incomplete → `covered_through`, never further. Nothing
> covered → don't move.

It keys on **coverage, not on the newest event seen**, which matters for the empty
window: a quiet wallet returns no events yet is fully covered, and its cursor must still
advance or it re-scans forever.

The server refuses `offset > 3000` (**3500 events per window, hard**), so a window too
dense to page is **halved**, not paged on. A 48h backfill drains 6h per cycle. Bounded
budget + window coverage = **lag, never loss**.

**Verified live on the worst wallet in the universe** (an HFT bot, 29,456 trades/48h,
which forced repeated window halving): **29,456 / 29,456 events captured, zero gaps, no
livelock**, drained in 16 cycles with strict forward progress.

## 3. Scaling to 1000 (measured, not assumed)

The data-api sustains **~38–40 req/s** with zero 429s — far more headroom than assumed.

| Gate | Result |
|---|---|
| 962 wallets @ concurrency 24, 3 back-to-back cycles | 25–31s, **0 × 429**, 0 errors |
| **Onboarding burst** (all 1000 first-sight backfilling at once — peak load) | **30.4s of the 60s cycle**, 1,242 req @ 40.8 req/s, **0 × 429**, 123,716 events |
| Steady state | ~1 request/wallet ⇒ ~1000 req/cycle |

Half the deep pool (507/1000) is **dormant** over 6h, which is why depth 1000 stays
cheap. Note also what depth buys: rank ~1000 is a **$200/week** trader. The deep pool is
a *candidate/discovery net* (`consensus_eligible = FALSE`), not new voters — which is
the right use for it, and consistent with weather-arm specialists sitting at mediocre
global rank.

Changes made:

- **`CONSENSUS_MAX_CONCURRENCY` 8 → 24.** At 8 the fan-out yields ~18.6 req/s ⇒ ~54s for
  1000 wallets, which overruns the 60s cycle the moment a poll costs more than one page.
- **Leaderboard pagination**: pages now fetch concurrently with per-page retry and spread
  backoff. Depth 1000 is 20 pages × N periods; previously **one transient failure
  discarded the whole period**, leaving the universe stale. It still aborts rather than
  admit a rank-shaped hole in the universe.
- **Batched upsert** (UNNEST): a depth-1000 refresh was 1000 sequential DB round-trips.
- **Staleness-fair poll order** (oldest cursor first, replacing rank-first). The fan-out
  polls everyone, so this is irrelevant in a cycle that *completes* — it decides who
  loses when one **doesn't** (restart, deploy, timeout). Under rank order the same deep
  tail was the casualty every time, biasing capture invisibly. Now the loss rotates.
- **Observability**: ingest duration, wallets polled, incomplete polls, unreadable
  windows — plus an explicit warn when ingest outgrows its interval. The driver sleeps
  *after* the cycle, so an overrun never piles up tasks; it silently stretches cadence,
  and every latency claim drifts with it. Now it says so.

Gate: **305 tests green** (5 new cursor-invariant tests: the regression guard, the
empty-window case, a liveness/convergence proof), clippy clean.

---

## 4. To deploy (your call)

```diff
# .env.consensus
- TRACK_DEPTH=200
+ TRACK_DEPTH=1000
+ CONSENSUS_MAX_CONCURRENCY=24   # code default is now 24; explicit is better here
```

`TRACK_CONSENSUS_RANK_CUTOFF` stays at 40 — **depth widens capture, not the voter set**,
so no live signal changes.

Watch after the flip: `consensus_ingest_duration_seconds` (must stay < 60s),
`consensus_data_api_429_total` (must stay 0), and
`consensus_activity_window_unreadable_total` (must stay 0 — anything else is a real
capture hole).

## 5. Open items I did not touch

- **LIVE_TAPE will exceed its subscribe ceiling at depth 1000.** Prod is
  `MAX_SUBS=200 × MAX_CONNS=8 = 1600` tokens, and the tape universe already sits ~1.6k at
  depth 200. It already warns ("tail tokens UNCOVERED") but the dropped tail is a
  *deterministic slice* — the same tokens every time, which is the starvation pattern
  again. Needs either a `MAX_CONNS` raise or a fair rotation before the tape is trusted
  at depth 1000. Separate lane (price tape, not trader ingestion), so out of scope here.
- **Backfilled history is now real, and much larger.** `trader_fills` will grow
  substantially once wallets actually backfill (123k events in a single onboarding
  cycle). Worth a look at retention/pruning before the flip.
- ~~Every prior result rests on ~3% of the busy wallets' history.~~ **Retracted** — see
  the corrected blast-radius section. The `trader_fills` archive is intact (2.7M rows,
  back to 2022, via the correct-params `backfill` mode). Prior conclusions stand on their
  own merits; this bug does not impeach them.
