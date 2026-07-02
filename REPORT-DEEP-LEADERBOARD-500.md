# Deep-leaderboard ingestion (top-500 via offset pagination) — run report

**Branch:** `feat/deep-leaderboard` (off `main`, the actual deploy branch — see below).
**Date:** 2026-07-02. **Standing rules honored:** additive, flag-gated, belief-blind,
cost-zero, paper-only, no real money.

## One-line outcome
The tracked-trader universe can now widen from the top-40 to an arbitrary depth via
**offset pagination**, done as an additive/reversible change that **captures + profiles**
the deep pool **without changing a single consensus signal** until a deep trader is
*earned* in. Measured safe; consensus non-regression proven byte-for-byte.

## The API correction (verified live 2026-07-01/02)
- Leaderboard `limit` **is** hard-capped at 50 server-side (the prior "never exceed 50"
  guidance was right about `limit`).
- **`offset` paginates cleanly** — verified: `offset=0` tail PnL **$145,644** →
  `offset=50` head **$141,630** (descending, no overlap). Top-500 = 10 sequential pages
  (`offset=0,50,…,450`). Unauthenticated public GET; a single caller paginating is the
  complete mechanism — **no multi-account** needed. The old "widen across periods, never
  raise N" guidance is **overturned for depth**.

## Deploy-branch correction
The prompt said to merge into `feat/consensus-engine`. Verified against reality: the
launchd autoupdater (`scripts/consensus-autoupdate.sh`) operates on the **checked-out
`main`** (`.last_built_commit` == `main` HEAD; `main` tracks `origin/main`) and rebuilds
when local HEAD advances. `feat/consensus-engine` is **10 commits stale** (main already
contains its work plus the honest-pnl merge). So to actually deploy, this work merges
into **`main`**. Because every new flag defaults to today's behavior, merging is safe.

## What shipped (per phase, each gate-green + committed)
- **P0** `fetch_leaderboard_paged` — additive sibling to `fetch_leaderboard_n` (unchanged):
  offset pages, paced 150ms, 429-as-Err (no silent truncation), dedup by wallet, global
  PnL-descending rank. Unit-tested (contiguous rank, dedup, depth cap) + real-API live test.
- **P1** depth wiring + provenance — `TRACK_DEPTH` (default 40) selects the paged fetch
  when > 50; migration 032 adds `followed_traders.consensus_eligible BOOLEAN DEFAULT TRUE`;
  upsert sets `eligible = rank ≤ TRACK_CONSENSUS_RANK_CUTOFF`, source-aware (manual follows
  never de-eligibled). Board/metrics show the hot/deep split. Live-verified on throwaway PG:
  depth=200 → 50/150 (then 40/160 after the cutoff correction), idempotent, churn-correct.
- **P2** fan-out hardening + cadence budget — Semaphore(8) added to the previously
  **unbounded** legacy `detect_new_trades` (a latent 500-request burst behind
  `COPY_TRADE_ENABLED`); poll count/latency metric + board line.
- **P3** consensus non-regression — the eligibility gate lives at **book-load**, uniform
  across both book sources (`load_window_votes` + `load_buy_fills_since`):
  `COALESCE(consensus_eligible, TRUE) = TRUE`. Deep votes are captured but never counted.
- **P4** efficiency re-rank — "Efficient below the whales" board panel runs the **same
  belief-blind trust gate** over the captured deep pool (no new gate); nothing promotes.

## Poll-cadence budget — MEASURED (the scale gate)
Real depth-200 poll fan-out through the semaphore-bounded path:
**200 traders @ concurrency 8 → 8.5s, 0 failures, 0 data-api 429s** (vs the ~120s consensus
cycle). Extrapolated to depth-500 ≈ 21s — still comfortably inside the cycle. **Verdict:
the semaphore alone is the poll-cadence budget; tiered cadence (`TRACK_DEEP_POLL_EVERY_N`)
is NOT needed and was deliberately not built as dead code.** If a future depth/tighter
cycle pushes latency toward the window, the lever is a deep-only stagger inside the
existing `join_all`+`Semaphore`.

## Non-regression — proven byte-for-byte
- **Storage** (`eligibility_gate_load_is_byte_for_byte`, live PG): both book sources return
  the eligible wallets only; all captured votes (deep included) remain in the archive.
- **Signal** (`deep_pool_excluded_from_signals_shadow_differs`, pure): gated `net_count = 3`
  fires; the shadow where deep *did* vote is `net_count = 6` (crosses `elite_net`) — proof
  the gate is load-bearing, not cosmetic. Book-building is deterministic in the loaded
  votes ⇒ identical loaded set ⇒ identical emitted signals.
- **Contract-correct default:** `TRACK_CONSENSUS_RANK_CUTOFF` defaults to **40** (= today's
  `track_top_n`), so flipping only `TRACK_DEPTH` widens *capture* while the *voter set stays
  exactly today's top-40* — zero consensus change. Raising the cutoff is the deliberate act
  that admits more voters.

## Efficiency-pool finding — HONEST NULL (today)
The instrument is built and verified, but the deep pool **51..depth has zero captured
history** because the widening isn't accrued yet. So the certified-edge verdict over ranks
51–500 is **NULL by construction** right now — it pends forward accrual once `TRACK_DEPTH`
is raised in production. The panel renders this explicitly and, once history accrues, will
surface any sub-whale trader whose forward surplus clears the same gate the top-50 face
(a candidate to earn a vote by a deliberate human flip — never automatic).

## Production config record (flags on/off)
Code defaults = **today's behavior** (reversible in one revert):
| flag | code default | meaning |
|---|---|---|
| `TRACK_DEPTH` | **40** | capture depth; > 50 paginates |
| `TRACK_CONSENSUS_RANK_CUTOFF` | **40** | voters = rank ≤ cutoff (= today's top-40) |
| `TRACK_DEEP_POLL_EVERY_N` | — | not built (semaphore suffices; measured) |

**Chosen shipped depth: `TRACK_DEPTH=200`** (the *measured* value: 8.5s, 0 429s — not the
unmeasured 500). Set in the local, gitignored `.env.consensus`; cutoff left at the default
40 so **consensus alerting is byte-for-byte unchanged** while we begin capturing ranks
41–200's fills for the profile pass. Pure upside, zero live-engine risk.

## Retention
No new knob: `followed_traders` at 200–500 rows is trivial, and deep-fill growth is already
covered by the existing `TRADER_FILLS_RETENTION_DAYS` (default 0 = keep; the daily
`pg_dump` covers `followed_traders`). Add a knob only if row growth later warrants.

## Deploy
Merged `--no-ff` into local `main`; the autoupdater rebuilds on the advanced HEAD and the
new binary reads `TRACK_DEPTH=200` from `.env.consensus`. Pushing `main` to `origin` is left
as a separate (outward-facing) step for the operator.
