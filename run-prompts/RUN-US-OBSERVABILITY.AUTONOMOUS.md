# RUN — US VENUE OBSERVABILITY: get a live view of Polymarket US, and do not stop at a 404

**Type:** long autonomous run. **Repo:** `~/polymarket-bot`. **Owner:** Tue.
**Sibling run:** `run-prompts/RUN-US-VENUE-PORT.AUTONOMOUS.md` (the certification question). **This run is
its prerequisite: it builds the eyes.**

---

## 0. THE BRIEF IN ONE PARAGRAPH

We can legally trade **Polymarket US** (`api.polymarket.us` / `gateway.polymarket.us` — QCX LLC, a
CFTC-regulated DCM+DCO), not the international book. **A partial live view already works:** markets, BBO,
and book depth all return from the public gateway. **Four endpoints 404'd** — `/trades`, `/leaderboard`,
`/activity`, `/positions` — and a previous session treated that as terminal. **It is not.** Your job is to
build the **most complete, most reliable live view of the US venue that is obtainable by any legitimate
means**, and to state — with evidence, not assumption — exactly what is obtainable and what provably is not.

**A 404 on one guessed path is not a finding. It is the start of the search.**

---

## 1. THE DISTINCTION THAT DECIDES THIS RUN

| What we want | Status | Prior |
|---|---|---|
| **Live prices / BBO / book depth / markets** | **Already works** on `gateway.polymarket.us` | Confirmed live 2026-07-13 |
| **Trade prints (a tape: price, size, time — no identity)** | **UNKNOWN — GO FIND IT.** This is the single highest-value target of the run. | Never searched properly |
| **Per-trader identity (who bought)** | **Probably does not exist in any client.** | See below |
| **Our own account's fills/positions** | Authenticated; should work with a key | Not tested (no account yet) |

**On identity — think before you grind.** The international venue exposes traders because it is
**pseudonymous, on-chain**: every fill is a public Polygon event with a wallet address. Polymarket US is
**KYC'd fiat accounts on a regulated exchange with a central clearinghouse.** Trader identity is almost
certainly **never emitted to any client, in any form** — not hidden behind an undocumented endpoint,
**absent by design**. Scraping recovers what a site *publishes but doesn't document*; it cannot conjure what
is never sent. **Do not spend the run trying to make wallets appear on a venue that has no wallets.**

**But prove it, don't assume it.** And note what a *tape without identity* would still buy us: prints,
volume, aggressor side, and order-flow imbalance. That is real, tradeable microstructure — and it is enough
for **capacity, slippage, and impact measurement**, which are exactly the numbers our whole business is
currently blocked on. **A tape with no names is a big win. Go get it.**

**And remember the architecture (from `RUN-US-VENUE-PORT.AUTONOMOUS.md`): we do NOT need a copy signal from
the US venue.** The signal comes from the **international** book, which we can read freely. The US venue only
needs to be observable enough to **price, size, and execute**. Anything beyond that is upside, not a
requirement. **Scope the run accordingly — do not let "find the sharps on US" become the mission.**

---

## 2. THE SEARCH LADDER — exhaust it in this order, and log EVERY probe

**Reliability order. Do not skip to scraping because it feels faster — it is the least durable rung and it
is the one that silently breaks in production.**

### Rung 1 — the OFFICIAL, DOCUMENTED surface (start here, be exhaustive)
- Read **all** of `docs.polymarket.us`, starting from its **`llms.txt` index** (it exists — use it).
  Enumerate **every** REST route, **every** WS channel, and their auth requirements.
- **`wss://api.polymarket.us/v1/ws/markets`** — the public market channel. **Does it push TRADE PRINTS, or
  only book/BBO updates?** If it pushes prints, **the tape problem is solved on Rung 1** and most of this
  run is unnecessary. **TEST THIS FIRST — it is the highest-value, cheapest probe available.**
- **`wss://api.polymarket.us/v1/ws/private`** — what does the authed channel carry beyond our own fills?
- **FIX 4.x** — they run an order-entry **and drop-copy** stack. Drop-copy is a *reporting* channel.
  **Does their FIX offer a market-data session (MDIncRefresh / trade ticks)?** Get the FIX spec.
- **gRPC (institutional)** — what does its service definition expose? Get the `.proto` if published.
- **The Builder / market-maker / liquidity-incentive programs** — these give *privileged data access* to
  participants. **What data does a registered builder or MM get that the public gateway does not?**
  This is a legitimate, durable, officially-sanctioned path to better data. **Price it out.**

### Rung 2 — the UNDOCUMENTED-BUT-REAL surface (the app knows things the docs don't)
The retail app **must** render *something* — recent trades, volume, "last price," a chart, open interest.
**Whatever the UI can draw, an endpoint is feeding it.** Find that endpoint.

- **Use the `chrome-devtools` MCP tools** (available in this session): open `polymarket.us` in a real
  browser, navigate a live market, and **capture the network log** (`list_network_requests`,
  `get_network_request`). Every XHR/fetch/WS frame the app makes is a documented-by-behaviour API.
- Pull the app's **JS bundles** and grep them for route strings, WS channel names, and GraphQL documents.
  Frontends routinely ship a complete map of their own backend.
- Probe the **iOS app** if the web app is thin (`polymarket.us` may be app-first): a proxy capture of the
  app's traffic is the same technique.
- **Version-walk the API**: `/v1/…` implies a `/v2/…` may exist. Enumerate paths systematically rather than
  guessing four and quitting. **Log every probe and its status code into a table** — a 404 is *data* about
  the shape of the surface, and the table is a deliverable.

### Rung 3 — the REGULATORY surface (the most overlooked, and the most durable)
**A CFTC-regulated DCM has statutory public-reporting obligations.** This is a legally *guaranteed* data
source that cannot be silently removed the way a private endpoint can.

- DCM Core Principles require publication of **daily trading volume, open interest, opening/closing ranges,
  and settlement prices.** **Where does QCX LLC publish these?** Find the actual files/pages.
- **Get the QCX DCM rulebook** (a large PDF — a previous session failed to text-extract it locally; **use a
  proper PDF extractor or an OCR fallback, and actually read it**). It defines what the exchange must
  publish, its market-data policy, its fee schedule, and its rules on automated/API access.
- Check **CFTC filings/submissions** by QCX (rule submissions are public) and any **market-data vendor**
  redistribution (a DCM's data is often licensed to vendors — that is a paid but *very* reliable feed).

### Rung 4 — SCRAPING (last resort, and only within the rules)
Only if Rungs 1–3 leave a genuine gap that matters.

- Scrape the **public web UI** for what it renders. Prefer the JSON the page fetches over parsing HTML.
- **RULES — non-negotiable:** obey `robots.txt` and the site's ToS; identify the client honestly; respect
  rate limits (the documented API limit is **20 rps/key** — assume the web tier is *tighter*); back off on
  errors. **Do NOT circumvent bot protections, CAPTCHAs, or any access control. Do not evade geoblocks or
  use a VPN. If a workaround requires defeating a protection, STOP AND REPORT — it is out of bounds, and it
  is also how accounts get closed.** We are a legitimate, KYC'd, fee-paying customer of this venue; act like
  one.
- **Treat any scraper as a liability, not an asset:** it must be monitored, it must fail loudly, and it must
  never be a load-bearing input to an order without a freshness check.

---

## 3. WHAT TO BUILD (once you know what is obtainable)

A **US market-data spine** that mirrors what we have internationally, and is honest about its own quality.

- **Ingestion** into Postgres: `us_markets`, `us_book_tape` (BBO + depth), and — **if it exists** —
  `us_trade_tape` (prints). Migration numbering: main ends at **040**; `feat/exec-policy` has **041**;
  `feat/paper-executor` has **042**. **Take 043+ and resolve nothing by guessing.**
- **A source-quality column on every row.** Each datum records **where it came from** (`official_ws`,
  `official_rest`, `undocumented_rest`, `scraped`) and **when it was seen** (`seen_at DEFAULT now()` — the
  instrument the international side is *still* missing, and its absence made our own ingestion latency
  invisible for months. **Do not repeat that mistake here.**)
- **A staleness contract.** Anything feeding a pricing or sizing decision must carry an age, and a stale
  datum must **fail closed** (skip the trade), never silently pass through. Scraped data especially.
- **Coverage + depth measurement, with n and dispersion:** how many levels are real, what the touch depth
  is, what the spread is, and **whether our arms' families (sports favorites; and WEATHER — our best arm)
  are actually listed and liquid.** A prior spot-check saw a US book with **2 bid levels vs 15 ask levels**
  and offers at 0.2020/0.4800/0.9700 — *that is not a mature book.* **Quantify this properly; it may be the
  finding that kills or makes the whole venture.**

---

## 4. HARD RULES

1. **No geoblock evasion, no VPN, no ToS circumvention, no defeating bot protections.** If a path requires
   it, stop and report. This is not negotiable and it is not a judgement call.
2. **Read-only. This run places no orders and needs no money.** Rungs 1–3 need no account at all.
3. **The evidence rule (binding — earned via 4 retractions, 2 of which reversed sign):** no claim ships
   without **(a) a control, (b) a significance test, (c) explicit n + dispersion.**
4. **`merge to main == auto-deploy to prod.`** Work on a branch. Every new path **default-OFF**; follow the
   `live.rs` pattern (*flag off ⇒ task never spawned ⇒ binary byte-identical*).
5. **Log every probe.** The probe table (path → method → auth → status → what it returned) is a first-class
   deliverable. **A negative result with a full probe table is a real finding. A negative result from four
   guesses is not.**
6. **Do not overclaim reliability.** A scraped feed is not an API. Say which rung each datum came from, and
   what happens the day it breaks.
7. Commit incrementally on the branch — a reaped long run must be salvageable from the worktree.
8. Report honestly: partial ⇒ **"incomplete + resumable"**, never "done."

---

## 5. DELIVERABLES

1. **`reports/US-API-SURFACE.md`** — the complete probe table (every route/channel tried, with status), the
   full official surface from the docs, the undocumented surface found in the app's own traffic, and the
   regulatory surface. **This is the core artifact.**
2. **A verdict on the TAPE**, with evidence: *can we get trade prints (price/size/time/aggressor) on the US
   venue — yes or no, from which rung, and how reliably?* **This is the run's headline question.**
3. **A verdict on IDENTITY**, with evidence: *is per-trader attribution obtainable by ANY legitimate means —
   or is it, as expected, never emitted?* **A clean, well-evidenced NO is a complete success here** — it
   permanently closes a question we would otherwise keep re-opening, and it confirms the intl-signal /
   US-execution architecture is the only one available.
4. **The US market-data spine**, on a branch, default-OFF, `cargo test` green — with source-quality and
   staleness columns.
5. **`reports/US-BOOK-DEPTH.md`** — is this book deep enough to fill $50 clips in our arms' families?
   With n and dispersion. **This gates everything downstream.**
6. **A `DECISIONS.md` entry** recording what is obtainable, what is not, and the reliability of each source.
7. If a **Builder / market-maker program** would materially upgrade our data access: **a written
   recommendation for Tue**, with what it costs and what it buys.

## 6. WHAT NEEDS TUE (surface these; do not block on them)

- **A Polymarket US account + API key** (iOS app → identity verification → `polymarket.us/developer`; an
  invite code may be required). **Rungs 1–3 and most of this run need NONE of it** — the gateway is public.
  Only the authed WS/private endpoints and our own fills need a key.
- **Any Builder / MM / institutional program application** — a human, contractual decision.

## 7. THE FRAME

The previous session stopped at four 404s and called the venue unobservable. **That was premature, and Tue
was right to push.** But the honest opposite error is just as bad: grinding for weeks to scrape identities
off a venue that **structurally has none**, when the identities we need are already free on the
international book — where reading is legal and where our entire signal already lives.

**So: be relentless about the tape and the book. Be rigorous — and quick — about identity. And be honest
about which rung every byte came from.**
