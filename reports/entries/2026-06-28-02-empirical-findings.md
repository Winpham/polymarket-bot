# 2026-06-28 · Entry 02 — Empirical findings from live-API probes

All from direct probes of the live Polymarket data API (scripts in scratchpad +
`scripts/consensus_backtest.py`).

## 1. APIs are live and rich
- `GET /v1/leaderboard?timePeriod={DAY,WEEK,MONTH,ALL}&limit=N` (cap 50) →
  rank, proxyWallet, userName, vol, pnl.
- `GET /activity?user=<wallet>&type=TRADE&limit=N` → conditionId, **outcomeIndex**,
  outcome, side, price, usdcSize, slug, eventSlug, title, timestamp.
- A position must be keyed by **(conditionId, outcomeIndex)** — buying "No" / a different
  outcome is the *opposite* bet. (The old copy cycle hardcoded YES — a real bug for consensus.)

## 2. Naive consensus is NOISE (the design pivot)
Probing ~143 top traders over 7d, "≥2 traders bought the same outcome" = 138 hits, but:
- **Top traders sit on BOTH sides** of popular markets (market-makers). "Portugal win" had
  **13 buying No AND 8 buying Yes.**
- Leaderboard is **~90% sports** right now (World Cup).
- "Same outcome" spans **wild entry prices (3¢–99¢)** → not a coherent entry.

## 3. The signal that survives
Strict gate — **NET directional** (backers − opposers ≥ 3, opposers ≤ 1) + **price-coherent**
(entry σ ≤ ~0.10) + **fresh** (< 48h), dropping wallets seen on both sides — collapsed
1021 raw positions → 55 (≥3 backers) → **8 clean** → 1 non-sports. Rarity is the feature.

## 4. NO backtest is possible (important)
- Of 150 recent top-trader market slugs, **78 are in Gamma but 0 are closed** — everything
  they're trading is live/unresolved (World-Cup-heavy window).
- The activity API effectively **ignores `startTs`/`endTs`/`offset`** (always newest-first),
  and hyperactive whales bury older trades — can't assemble a resolved historical sample.
- Resolution logic itself is verified correct (closed markets show `["1","0"]` outcome prices;
  `resolved_outcome_won(idx)` handles binary + multi-outcome).

**Consequence:** edge can only be measured **forward**. This is *why* we run a portfolio of
strategies simultaneously (entry 03) rather than picking one offline.

## 5. Other notes
- Sports vs non-sports is the major axis; do NOT assume sports is unprofitable for *copy*-
  consensus (the trading-bot blocks sports for its ML, a different mechanism). Let forward
  data decide, sliced by segment.
- Down-weight chronically two-sided wallets (market-makers) — already done by dropping them
  per-market; a global directionality score is a future refinement.
