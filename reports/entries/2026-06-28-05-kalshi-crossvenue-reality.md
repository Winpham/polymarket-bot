# 2026-06-28 · Entry 05 — Kalshi + cross-venue: live empirical reality

Direct live-API probes (complementing the strategy-foundry workflow's doc research).

## Kalshi public data — what's actually there
- `api.elections.kalshi.com/trade-api/v2` is **public, no auth** for: `/markets`, `/markets/{ticker}/orderbook`
  (REAL resting liquidity — confirmed books with thousands of contracts), `/markets/trades` (global +
  per-market trade tape), WebSocket for live. Field names use `_dollars` / `_fp` suffixes.
- **Gotcha:** the markets-LIST quote fields (`yes_bid_dollars` etc.) are largely **empty/unreliable** — the
  *orderbook* endpoint is the source of truth for live prices. Don't filter liquidity off the list view.
- **Individual trader positions are NOT in the official API** (only your own). Copy-trading on Kalshi would
  require SCRAPING the website/leaderboard (e.g. Apify) — fragile, treat as a first-class risk.

## Where Kalshi liquidity actually IS (from the live global trade feed)
Most-traded series right now: **crypto short-term** (`KXBTC15M`, `KXBTCD`, `KXETH15M`, `KXHYPE15M`),
**tennis/cricket/golf** (`KXATPCHALLENGERMATCH`, `KXWT20MATCH`, `KXT20MATCH`, `KXITFMATCH`, `KXPGAH2H`),
**esports** (`KXMVESPORTSMULTIGAMEEXTENDED`, **`KXCS2GAME`**), and some World Cup (`KXWCADVANCE`, `KXWCGAME`).
**International soccer is THIN on Kalshi** — World Cup game markets showed no list-view bids while Polymarket
trades them actively.

## Cross-venue (Polymarket ↔ Kalshi) reality
- Same events exist on both, BUT divergence-arb only works where BOTH venues are liquid. From the data:
  **viable pairs = crypto short-term (BTC/ETH up-down), CS2 esports, possibly World Cup advance** — **NOT
  soccer match outcomes** (Kalshi too thin). A soccer cross-venue strategy would be stillborn.
- Because we place **no real trades**, "arb" = a **divergence ALERT** (venue A vs venue B price gap on the
  same event) + a lead-lag study (which venue moves first / is "smarter"). Fully free-data, forward-measurable.

## The Foresight bridge (worth flagging)
**`KXCS2GAME` = CS2 match markets on Kalshi.** Tue's Foresight project is CS2 player-prop ML. There may be a
real connection: CS2 map/match-winner consensus or model signals could span Kalshi + Polymarket. Parked as a
high-interest cross-project lead. See [[project-foresight]].

## Implications for the strategy catalog
1. Kalshi copy-consensus (Polymarket's mechanism) does NOT transfer — no public positions. De-prioritize.
2. Kalshi-native edge = public ORDER-FLOW / microstructure (order-book imbalance, trade-tape momentum) on its
   liquid series (crypto-15m, tennis, CS2), + scraped-leaderboard copy (fragile).
3. Best NEW cross-venue angle = **divergence/lead-lag alerts on crypto-short-term + CS2**, where both venues are liquid.
