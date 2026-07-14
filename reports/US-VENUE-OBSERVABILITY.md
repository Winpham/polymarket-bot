# US-VENUE OBSERVABILITY — findings, systems, and verdicts

**Date:** 2026-07-13 → 07-14. **Branch:** `feat/us-venue`. **All read-only.** Client identified
honestly on every request; public/unauthenticated throughout; ≤12 concurrent, under the 20 rps limit.

This is the observability half of the US-venue work (sibling: the mapper/basis port, Phases A–C).
It answers: *what can we see on Polymarket US, from which rung, how reliably* — and it ships the
systems that put the US venue on the same footing as the international side (live tape, history,
book depth) plus the two-book arbitrage layer.

---

## 0. HEADLINE — the "US identity is unobservable" prior is FALSIFIED

The standing belief ([[project-polymarket-us-venue]]) was that Polymarket US, being a KYC'd fiat
DCM, never emits trader identity, so the copy signal is unobservable there. **That was inferred
from four REST 404s and is wrong.** The retail app streams a **live trade tape with persistent
per-trader usernames** from an undocumented, **unauthenticated** WebSocket it uses itself:

```
wss://gateway-ws-markets.polymarket.us/v1/ws/subscriptions
```

- Found on Rung 2 (the `polymarket.us` Next.js bundle env `NEXT_PUBLIC_US_WS_URL`). The **documented**
  socket `api.polymarket.us/v1/ws/markets` is the one that returns 401; this gateway host is public.
- A **venue-wide** subscription (empty `marketSlugs`) delivers **every trade on the exchange from one
  connection** — confirmed: markets we never named streamed in.
- Each print carries `taker{username,side,intent,outcomeSide}` + `maker{…}` + price + qty + a
  nanosecond exchange timestamp. **Measured live: taker username on ~99–100% of prints, maker on
  ~46–52%**, hundreds of distinct persistent handles per minute.
- The docs' own trade example omits `username`, which is why a docs-only search never found it.

**Consequence:** the copy signal we thought lived only on the intl on-chain book is *also* observable
on US — as usernames on the aggressor of (almost) every trade. There is no public per-username
history endpoint, so **we build that history ourselves by ingesting the tape continuously** (Phase 1).

---

## 1. THE SEARCH LADDER — what each rung yields

| Rung | Surface | Tape? | Identity? | Auth | Reliability |
|---|---|---|---|---|---|
| 1 official docs | `docs.polymarket.us` (271-line `llms.txt` index; REST + WS + FIX + gRPC) | via authed WS `SUBSCRIPTION_TYPE_TRADE` | maker/taker side (no username in docs) | key | high (with key) |
| 2 undocumented | `gateway-ws-markets` WS (from app bundle) | **yes, live** | **yes — usernames**, unauthed | none | medium — undocumented; monitor + freshness-gate |
| 3 regulatory | `polymarketexchange.com` Time&Sales + Daily Market Report CSVs | yes (anonymized) | no (by design) | none | **highest** — CFTC DCM statutory publication |
| 4 scraping | web UI | n/a — app is a login wall (app-first) | n/a | — | not needed; not used |

The public gateway serves only `/v1/{markets,events,series,sports,search,tags,health}` + per-market
`/book /bbo /settlement`. **Every tape-shaped REST path 404s** (`/trades /prints /tape /executions
/candles /ohlc /volume /open-interest`, and a `/v2 /v3 /api/v1` version-walk) — the prints live on the
WS and the CSVs, never on REST. Full 62-probe table: `reports/US-API-SURFACE.md`.

---

## 2. VERDICTS (with evidence)

**TAPE — obtainable three ways.** (1) Live + identity via the gateway WS (Rung 2). (2) Live, side-only,
authed via the documented WS (Rung 1, needs key). (3) Durable, anonymized, no-account via the daily
Time & Sales CSVs (Rung 3): **258 files, 5.4 GB, back to 2025-10-29**, ~1.9M prints/day (time, symbol,
price, size).

**IDENTITY — YES on the live WS, NO on REST/CSV.** Reverses the prior. Usernames are persistent handles,
public and unauthenticated, on the aggressor of ~all prints and ~half of resting legs. The regulatory
CSVs are anonymized by design; every public-readable OpenAPI schema (market, markets, orderbook) has
**zero** identity fields (all `account`/`user`/`participant` fields live only in authed, self-scoped
schemas). FIX drop-copy can be provisioned "for all participants" but only to clearing members /
authorized service providers — not a retail path. So identity is obtainable, but **only** via the live
WS, and only going forward (no history endpoint) — hence continuous ingestion.

**BOOK DEPTH — favorites deep, weather thin, time-of-day matters.** See `reports/US-BOOK-DEPTH.md`.

---

## 3. SYSTEMS SHIPPED (this branch) — US to parity + the two-book layer

All are **read-only Python sidecars** (the venue's deliberate pattern: no Rust SDK, read-only path needs
no executor cage; Rust is reserved for order entry). **Default-OFF by construction** — none has a
committed launch unit, so a merge deploys nothing until an operator installs one. Each self-applies its
additive migration.

| Phase | Migration | Sidecar | What it gives |
|---|---|---|---|
| 1 live identity tape | `043_us_trade_tape` | `us_tape_ingest.py` | venue-wide trade prints + per-trader usernames → our own trader history |
| 2 regulatory history | `044_us_daily_market_report` | `us_regulatory_backfill.py` | 257-day DMR (OI/volume/settlement) in Postgres; T&S tape → cold parquet |
| 3 book depth | `045_us_book_tape` | `us_book_sampler.py` | time-of-day depth series (BBO, spread, $50/$250 fill/slip) for our families |
| 4 cross-venue arb | `046_cross_venue_basis` | `us_arb_scan.py` | side-correct US-vs-intl basis + risk-free-basket edge, fails closed on staleness |

**Provenance & honesty conventions** (inherited from 040/042): two clocks never a precomputed lag
(exchange `trade_time` + local `recv_at`, latency derived at read); a `source` rung on every datum;
placebo/staleness as first-class; side-correctness reused by import (no reinvented 90¢ inversion).

Verified end-to-end against the live venue + Postgres:
- tape: 540 prints, 99% taker id, 256 distinct traders, per-trader history emerging, 0 duplicate keys.
- DMR: 321,743 rows / 257 days, 100% with settlement price. T&S: 170 MB CSV → 14.6 MB parquet (12×).
- book: overnight favorite fill50 84% vs 100% at 23:20 ET (real thinning); weather touch ~$44.
- arb: 40 mapped+priced, basis mean −1.5¢ sd 5.9¢, **0 phantom baskets** (side logic correct), 0
  actionable arb on efficient favorites (baskets ~$1.001) — the honest result.

---

## 4. RUNBOOK — turning the sidecars on (operator action, not a code deploy)

```
# schema is self-applied by each sidecar on first run; or apply explicitly:
python3 scripts/us_tape_ingest.py --apply-only

# continuous (each is its own process; keep on a committed branch if long-running):
python3 scripts/us_tape_ingest.py                 # live identity tape, venue-wide
python3 scripts/us_book_sampler.py --loop 900     # depth series, 15-min cadence
python3 scripts/us_arb_scan.py --loop 120         # arb scan, 2-min cadence
python3 scripts/us_regulatory_backfill.py --daily # nightly DMR + T&S increment (after 6PM ET)

# one-time deep history:
python3 scripts/us_regulatory_backfill.py --dmr           # full DMR → Postgres
python3 scripts/us_regulatory_backfill.py --tape          # full T&S → cold parquet (5.4GB)
```
Env: `ARCHIVE_PG_DSN` (Postgres), `US_ARCHIVE_DIR` (cold parquet, default `~/polymarket-archive`).

---

## 5. LIMITS & WHAT NEEDS TUE / NEXT

- **Rung-2 fragility:** the live-identity WS is undocumented; it can change without notice. It carries a
  `source='gateway_ws'` tag and must never feed an order without a freshness check. The regulatory CSVs
  (Rung 3) are the durable fallback for everything except identity.
- **No username→history endpoint:** per-trader history only accrues from continuous ingestion — the clock
  is irreversible, so the tape ingester should run soonest.
- **Arb universe is currently narrow:** only ~40 of ~536 live signals map to an open US market at
  conf ≥ 0.90; efficient favorites show no free lunch. Real edge, if any, will surface on less-efficient
  or less-mapped cells over continuous running — not on the tightest markets.
- **Needs Tue:** an API key (iOS app → verify → `polymarket.us/developer`) unlocks our own fills/positions
  + the authed WS; none of the above required it. A market-maker/builder program (a contractual decision)
  would upgrade data access and pay maker rebates — worth pricing if we execute at scale.
- **Next build:** wire the per-trader tape into the copy/skill machinery (does a US username's history
  predict, the way we tried to on intl?); run the depth sampler across a full US trading day for the
  time-of-day depth verdict near settlement.
