# 2026-06-28 · Entry 07 — Data readiness: capture results properly, track like a stock, know what for

Directive: build everything so that once data flows it's used properly; get an accurate read on
outcomes ("if we can't capture the result there's no point"); capture the initial position and how
it changes ("works like a stock").

## 1. Robust result capture (verified) — the linchpin
The old path resolved by Gamma slug, which is absent for ~50% of markets (all sports). **Switched to
CLOB `/markets/{condition_id}`** — keyed by the conditionId we always have, it resolves EVERY market
(sports included) and returns `winner` (resolution) + per-outcome `price` (live) in one call.
- `ClobMarket`/`ClobToken` + `fetch_clob_market` + `outcome_won`/`outcome_price` (unit-tested).
- Housekeeping resolves by condition_id (deduped).
- **PROVEN end-to-end:** 3 injected known-resolved markets resolved with the correct outcome,
  including the **sports slug-gap market** (Yes-won) now resolving; a real market that closed
  mid-test resolved correctly too.

## 2. Position trajectory — "works like a stock" (verified)
Each signal = an entry, a live price that moves each cycle, a 0/1 resolution. We now capture the chart.
- migration 023: `consensus_snapshots` (ts, net, backers, mean_entry, market_price) + `initial_*`
  (set once) + `last_market_price` on the signal.
- Housekeeping appends a snapshot per open signal each pass (CLOB live price + consensus state),
  skipping the `_blind` population to bound volume.
- **PROVEN:** 15 snapshots with live prices; e.g. entry 0.67 → live 0.870 (moved up), 0.56 → 0.535
  (drifted down), with `net_count` (consensus strength) tracked. CLV = entry vs price near close.

## 3. Belief-blind promotion gate — "know what the data is for" (built + tested)
Decides when a silently-tracked strategy has EARNED promotion (the call stays human; the gate informs).
- Scoreboard now computes **cluster-robust** surplus: per-signal surplus → averaged to EVENT level →
  across events (correlated outcomes of one event count once — the within-match leak fix); returns
  surplus + surplus_sd + distinct_events.
- `scanner/promotion.rs` (pure, probit + 5 tests): **Bonferroni-corrected one-sided lower confidence
  bound** on surplus must clear a margin over a **≥30 distinct-EVENT floor**; stricter as the family grows.
- `/consensus` shows ✅ promotable / ⏳ hold + the lower bound per strategy.
- **VERIFIED:** synthetic resolved data → surplus 0.333 / sd 0.577 over 3 events vs the `_blind` band
  baseline; gate correctly holds (needs 27 more events).

## Net
Once deployed, every signal is captured at entry, tracked like a stock through its life, resolved
robustly (incl. sports), scored on favorite-longshot-neutralized surplus at the honest event-level N,
and judged by a multiple-comparisons-aware gate. The data will be **used properly, and we know what for.**

## Remaining
`atom-replay-cli` (score new strategies over stored atoms), cross-venue resolution-truth → divergence,
and the standing deploy (your Telegram token + persistent Postgres) so the gate's N starts climbing.
