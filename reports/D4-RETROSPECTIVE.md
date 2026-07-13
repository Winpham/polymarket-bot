# D4 RETROSPECTIVE — "what did the D4 fix actually do for us?"

**Date:** 2026-07-13 · **Basis:** prod DB (`polymarket`), live · **Verdict:** *shipped, partially
effective, and structurally incapable of the thing it was aimed at.*

---

## The short answer

**D4 is live in prod — the handoff docs that say it isn't are stale.** It has done two real things and
missed the headline one:

| | before | after | verdict |
|---|---|---|---|
| ask-capture **p50 lag** | 26.2 min | **19.1 min** | ✗ headline **MISSED** (target was <5s) |
| ask-capture **p99 lag** | 60 h | **3.5 h** | ✓ extreme tail crushed |
| weather asks in the **dead ≥0.90 band** | 64.9% | **51.7%** | ✓ real improvement |
| weather asks in the **0.71–0.90 cert band** | 31.3% | **45.8%** | ✓ real improvement |
| sports asks in the **dead ≥0.90 band** | 34.7% | **16.0%** | ✓ real improvement |
| **loser-tilt** (`entry_ask` edge by outcome) | −1.04% vs +1.71% | *not evaluable* | ⚠ underpowered |

**The one-line answer to Tue's question:** D4 made the *captured band* meaningfully healthier — which is
the data the gates actually eat — but it **did not and cannot give us a fresh ask.** The median is still
19 minutes. And the fix that *can* get to <5s was **never armed**. It is armed now.

---

## 1. Is it even running? — YES (the brief and `EXECUTION-READINESS.md` are both wrong)

- `e74f4e7` ("fix(capture): un-starve the decision-time entry_ask lane") is an **ancestor of `main`**,
  merged 2026-07-12 20:09 via `1e199a5`.
- Prod's deployed commit is `0ce4699` (`.last_built_commit`), which **contains** `e74f4e7`.
- The autoupdater rebuilt and the bot has been up ~8 h. **D4 went live ~2026-07-13 09:32 UTC.**

So the "it never shipped, therefore it did nothing" answer I was primed to give is **false**. It shipped.
Everything below is measured on the ~8 h of post-deploy data (and is honestly labelled where that is thin).

## 2. What it did — the lag

Cohorted by **fire time** (so a signal's whole lifecycle sits on one side of the deploy), versus the
matched prior-24h window:

| cohort | n | p50 | p90 | mean |
|---|---|---|---|---|
| BEFORE (prior 24 h) | 175 | 26.2 min | 65.8 min | 42.2 min |
| AFTER (fired under D4) | 264 | **19.1 min** | 92.6 min | 27.6 min |

Across *all* history the tail improvement is unmistakable — **p99 fell from ~60 h to ~3.5 h** — and the
mean fell by a third. But **the median barely moved, and p90 got worse in the matched window.**

### Why the median could never move — this is the load-bearing finding

D4 is an **ordering** fix *inside the housekeeping cycle*. It changes **who** gets the scarce ask budget,
not **when** the budget is spent. And the housekeeping loop:

- **sleeps 5 minutes** between cycles (`copy-trading-bot/src/live.rs:221`), and
- takes **~10–15 min** for a full pass over the open backlog (`config.rs:569`, ~120 ms/condition).

So a capture cannot land sooner than roughly **15–20 minutes** after a signal fires. **The measured
post-D4 p50 is 19.1 min — i.e. D4 is already sitting on its own structural floor.** It extracted
essentially all the value available to it. There is no tuning left: *no ordering change inside
housekeeping can ever produce a <5s ask.* Only a capture **inside the consensus cycle, at the instant the
signal fires**, can.

## 3. What it did — the band (the actual win)

This is the part that matters for certification, and it is a genuine improvement. The pre-fix defect
pushed captured asks into the **dead ≥0.90 band** (a winner's favourite drifts toward 1.0 and stops being
buyable, so a *late* look disproportionately finds deep chalk and losers):

| family | band | before | after |
|---|---|---|---|
| weather | dead ≥0.90 | 64.9% | **51.7%** |
| weather | **cert 0.71–0.90** | 31.3% | **45.8%** |
| sports | dead ≥0.90 | 34.7% | **16.0%** |
| sports | **cert 0.71–0.90** | 48.7% | **60.0%** |

*(n after: weather 118, sports 25.)* The weather arm was accruing asks that **could not have certified it
no matter how long it ran**; it now accrues ~46% in-band instead of ~31%. That is real and it compounds
daily.

## 4. What is NOT yet answerable — and I will not fake it

The **loser-tilt** (the −1.04% vs +1.71% raw-edge gap) is **not evaluable on 8 hours of data.** The
post-deploy resolved cohort is heavily **right-censored**: only fast-resolving markets have resolved yet,
so the captured-vs-uncaptured comparison is confounded by exactly the selection effect it is trying to
measure. The raw numbers (winners 6.5% captured vs losers 13.0%, n=35 captured resolutions) *look* like the
tilt got worse — **that read is an artifact, not a finding.** Re-run this at ≥7 days.

**This is the same trap that produced the retracted "15 min = 8¢" latency claim.** No control, no n, no
verdict.

---

## 5. The thing that was actually broken: the fix that fixes it was never armed

| lane | state (before today) |
|---|---|
| `entry_ask` (housekeeping, D4) | ✅ live — but floored at ~19 min |
| **`entry_ask_fire` (at-fire, mig 042)** | ❌ **0 rows.** Flag `CAPTURE_ENTRY_ASK_AT_FIRE` absent from the prod env; migration never applied (`_sqlx_migrations` max = 40); code stranded on `feat/paper-executor`. |

**And a second, larger hole underneath it — the price tape was blind to the weather arm.**

`live_tape` derived its subscription universe from `tracked_tape_assets`, which carries a literal
`AND is_sports`. Measured on prod: **of the 583 distinct non-sports conditions we have ever fired a signal
on, ZERO appear in `clob_price_tape`.** The single arm whose edge survives LODO (null p=0.0005) was
accruing **no price curve at all**.

And deleting that predicate is **not** the fix — it is a worse bug:

| universe | tokens | vs pool capacity (200×8 = **1600**) |
|---|---|---|
| current (`AND is_sports`, 6 h) | **2,507** | already ~900 **over** — tail silently dropped |
| naive fix (drop `is_sports`) | **9,965** | **6× over** — coverage hole gets *worse* |
| **our open signals** | **304** | comfortably inside |

The right set was never "what tracked traders filled" — it is **"what WE signalled."** An entry ask, a
basis, a trajectory are all properties of *our* signal.

## 6. What shipped today (commit `00729ee`, branch `fix/arm-atfire-capture`)

1. **At-fire ask capture armed** — mig 042 ported to main as **041** (renumbered to keep the sequence
   *dense*: a gap would let a later-merging 041 from `feat/exec-policy` apply out-of-order behind an
   applied 042 and crash-loop the app on boot). DDL is idempotent; the columns already exist unrecorded on
   prod, so it applies there as a no-op. Flag `CAPTURE_ENTRY_ASK_AT_FIRE`, **default OFF**.
2. **`price_tape_universe()`** — our open signals **first** (304 on prod, **280 of them weather**), then
   tracked-fill assets to fill the remainder, hard-`LIMIT`ed to pool capacity. Measured after: 304 prio-0 +
   1,296 prio-1 = **exactly 1,600, no overflow**. The weather arm goes from **0% tape coverage to 100%**.
   Ordering is what makes the cap safe: what gets dropped is now the *least* important thing rather than an
   arbitrary tail. `tracked_tape_assets` is untouched and still backs `live_fills`, where tracked traders'
   assets *are* the correct universe.

307 tests green; clippy 0 warnings.

## 7. Fee model — corrected, and verified twice

The four disagreeing documents are resolved **against the venue itself**, not against each other:

- **Taker:** `Fee = 0.06 × C × p × (1−p)` — confirmed on `docs.polymarket.us/fees` **and** independently by
  `feeCoefficient: 0.06` present on **every one of 1,200** US markets sampled from the public gateway.
- **Maker:** coefficient **−0.0125** — **the maker is PAID.**

At the certification band that is **1.20¢/share at p=0.80** taker versus **+0.25¢/share** maker — a
**~1.45¢ swing per share**, against a total measured edge of only 3–7¢. *The fee is not a rounding error;
it is a large fraction of the edge, and the taker/maker choice may matter more than the pick.*

---

## What to do next

1. **Merge and set `CAPTURE_ENTRY_ASK_AT_FIRE=1` in prod.** Backfill is impossible — every day this is off
   is a day of realizable-edge truth that can never be recovered, and it is the ceiling on what could ever
   transfer to the US book.
2. **Re-run §4's loser-tilt at ≥7 days**, with the control arm, before anyone reasons about it.
3. Once `entry_ask_fire` has ≥1 week of rows, **measure the bias directly** (fire-ask vs housekeeping-ask
   on the *same* signal) — the two columns exist side-by-side precisely so this is a measurement and not an
   argument.
