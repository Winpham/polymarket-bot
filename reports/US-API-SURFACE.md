# US-API-SURFACE — the complete probe table & surface map

**2026-07-13/14. Read-only, honest UA, ≤12 concurrent (<20 rps). 62 probes logged.**

The previous session stopped at four REST 404s and called the venue unobservable. This is the full
surface: every route/host tried, the official docs surface, the undocumented app surface, and the
regulatory surface. A 404 here is *data about the shape of the surface*, not a dead end.

## Hosts
- `gateway.polymarket.us` — public read API (markets/events/series/sports/search/tags/health + per-market book/bbo/settlement). No auth.
- `api.polymarket.us` — authed trading/portfolio/account + WS. All data paths 401 without a key.
- `api.prod.polymarketexchange.com` — institutional EP3/Connamara exchange core (report/orderbook, 401).
- `gateway-ws-markets.polymarket.us` — **UNDOCUMENTED public WS** (from the app bundle): venue-wide book + BBO + **trade prints with usernames**, unauthenticated.
- `www.polymarketexchange.com` — regulatory publications (Time & Sales + Daily Market Report CSVs), robots `Allow: /`.

## Key facts
- Public gateway 200s: `/v1/markets`, `/v1/events`, `/v1/series`, `/v1/sports`, `/v1/search`, `/v1/tags`, `/v1/health`.
- **Every tape-shaped REST path 404s** on the gateway: `/trades /leaderboard /activity /positions /prints /tape /time-and-sales /executions /history /candles /ohlc /volume /open-interest /orderbook /book /bbo` (top-level), plus a `/v2 /v3 /api /api/v1 /api/v2` version-walk. The prints are NOT on REST — they are on the WS and the regulatory CSVs.
- Query params except `limit`/`offset` are IGNORED by the gateway (filter client-side); markets list is oldest-first over ~224k markets.
- WS: documented `api.polymarket.us/v1/ws/markets` → 401; undocumented `gateway-ws-markets…/v1/ws/subscriptions` → open. Subscribe shape: `{"subscribe":{"requestId","subscriptionType":"SUBSCRIPTION_TYPE_{TRADE|MARKET_DATA|MARKET_DATA_LITE}","marketSlugs":[…]}}`; empty marketSlugs = venue-wide.
- Regulatory: `/files/time-and-sales/manifest.json` (258 files, 5.4GB) + `/files/daily-market-report/manifest.json` (257 files). Updated ~6PM ET daily.

## Full probe table
| host | path | status | meaning |
|---|---|---|---|
| gateway.polymarket.us | `/v1/markets` | 200 | OK (public) |
| gateway.polymarket.us | `/v1/events` | 200 | OK (public) |
| gateway.polymarket.us | `/v1/series` | 200 | OK (public) |
| gateway.polymarket.us | `/v1/sports` | 200 | OK (public) |
| gateway.polymarket.us | `/v1/search?q=weather` | 200 | OK (public) |
| gateway.polymarket.us | `/v1/tags` | 200 | OK (public) |
| gateway.polymarket.us | `/v1/sports/leagues` | 404 | absent |
| gateway.polymarket.us | `/health` | 404 | absent |
| gateway.polymarket.us | `/v1/health` | 200 | OK (public) |
| gateway.polymarket.us | `/v1/trades` | 404 | absent |
| gateway.polymarket.us | `/v1/leaderboard` | 404 | absent |
| gateway.polymarket.us | `/v1/activity` | 404 | absent |
| gateway.polymarket.us | `/v1/positions` | 404 | absent |
| gateway.polymarket.us | `/trades` | 404 | absent |
| gateway.polymarket.us | `/leaderboard` | 404 | absent |
| gateway.polymarket.us | `/activity` | 404 | absent |
| gateway.polymarket.us | `/positions` | 404 | absent |
| gateway.polymarket.us | `/v1/markets/trades` | 404 | absent |
| gateway.polymarket.us | `/v1/market-data/trades` | 404 | absent |
| gateway.polymarket.us | `/v1/prints` | 404 | absent |
| gateway.polymarket.us | `/v1/tape` | 404 | absent |
| gateway.polymarket.us | `/v1/time-and-sales` | 404 | absent |
| gateway.polymarket.us | `/v1/executions` | 404 | absent |
| gateway.polymarket.us | `/v1/history` | 404 | absent |
| gateway.polymarket.us | `/v1/prices-history` | 404 | absent |
| gateway.polymarket.us | `/v1/candles` | 404 | absent |
| gateway.polymarket.us | `/v1/candlesticks` | 404 | absent |
| gateway.polymarket.us | `/v1/ohlc` | 404 | absent |
| gateway.polymarket.us | `/v1/stats` | 404 | absent |
| gateway.polymarket.us | `/v1/volume` | 404 | absent |
| gateway.polymarket.us | `/v1/open-interest` | 404 | absent |
| gateway.polymarket.us | `/v1/orderbook` | 404 | absent |
| gateway.polymarket.us | `/v1/book` | 404 | absent |
| gateway.polymarket.us | `/v1/bbo` | 404 | absent |
| gateway.polymarket.us | `/markets` | 404 | absent |
| gateway.polymarket.us | `/v1/markets` | 200 | OK (public) |
| gateway.polymarket.us | `/v2/markets` | 404 | absent |
| gateway.polymarket.us | `/v3/markets` | 404 | absent |
| gateway.polymarket.us | `/api/markets` | 404 | absent |
| gateway.polymarket.us | `/api/v1/markets` | 404 | absent |
| gateway.polymarket.us | `/api/v2/markets` | 404 | absent |
| api.polymarket.us | `/v1/portfolio/positions` | 401 | exists, needs key |
| api.polymarket.us | `/v1/portfolio/activities` | 401 | exists, needs key |
| api.polymarket.us | `/v1/orders/open` | 401 | exists, needs key |
| api.polymarket.us | `/v1/account/balances` | 401 | exists, needs key |
| api.polymarket.us | `/v1/report/trades/search` | 401 | exists, needs key |
| api.polymarket.us | `/v1/markets` | 401 | exists, needs key |
| api.polymarket.us | `/v1/health` | 200 | OK (public) |
| api.polymarket.us | `/v1/incentives/programs` | 401 | exists, needs key |
| api.prod.polymarketexchange.com | `/v1/report/trades/search` | 401 | exists, needs key |
| api.prod.polymarketexchange.com | `/v1/refdata/symbols` | 404 | absent |
| api.prod.polymarketexchange.com | `/v1/refdata/instruments` | 404 | absent |
| api.prod.polymarketexchange.com | `/v1/orderbook/bbo` | 401 | exists, needs key |
| api.prod.polymarketexchange.com | `/v1/orderbook/book` | 401 | exists, needs key |
| api.prod.polymarketexchange.com | `/v1/health` | 200 | OK (public) |
| api.prod.polymarketexchange.com | `/health` | 404 | absent |
| www.polymarketexchange.com | `/files/time-and-sales/manifest.json` | 200 | OK (public) |
| www.polymarketexchange.com | `/files/daily-market-report/manifest.json` | 200 | OK (public) |
| www.polymarketexchange.com | `/robots.txt` | 200 | OK (public) |
| www.polymarketexchange.com | `/sitemap.xml` | 404 | absent |
| www.polymarketexchange.com | `/rulebook.html` | 404 | absent |
| www.polymarketexchange.com | `/market-data.html` | 404 | absent |