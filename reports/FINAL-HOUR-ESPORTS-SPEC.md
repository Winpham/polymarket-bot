# Final-hour favourite via a live esports game-clock feed — DATA-ACQUISITION spec (certification second)

**Branch `feat/evergreen-cert`. Paper / read-only. Spec only — NO harness built here, no orders, no
API key, no merge.** Grounds: `reports/CONFIDENCE-FORENSICS.md` phases 7–9, `PREREG_20260715_final_hour_favourite.md`,
`scripts/niche/finalhour_forward.py` (the tennis/ESPN harness this forks), `[[project-polymarket-us-efficiency]]`.

---

## 0. HONEST PRIORS (read first)

This is a **data-acquisition project that MIGHT yield an arm — not a known edge.** The base rate in
this repo is NO: champion, collapse, weather, and every prior candidate dissolved under walk-forward +
λ + official settlement. The **only** reason this one is worth building is that it is the single lead
in the entire investigation with a **real information signature (λ>0)** that survives at a realizable
price. Two caveats stated up front, not buried:

1. **λ was corrected DOWN in the phase-9 audit.** The headline "λ=0.73" was measured with the CLV
   close 5 min before resolution (near-degenerate = hindsight). At a fair tradeable close it is
   **λ ≈ 0.44 (LB 0.22) at −30 min, λ ≈ 0.10 (LB 0.00) at −45 min** — modest, *slow* information (the
   thin book grinds the near-decided favourite up over ~30 min), not a fast re-rating. The **profit is
   intact** (survives a 3¢ ask haircut: +3.4¢ p=0.025). Do not spec this as "strong information."
2. **Esports λ standalone is UNMEASURED.** The pooled λ was dominated by tennis (n287 ATP/WTA + n840
   ITF). Esports contributed measured *profit* (+4.51¢ @ −0.5h, n218, p=0.02) but its own λ has never
   been isolated. **Establishing esports-specific λ is the primary job of the forward test** — that is
   why this is data-acquisition-first.

---

## 1. THE EDGE, PRECISELY RESTATED

**What it is.** A thin US (regulated, `aec-*`) book systematically *underprices the leading favourite
in the final minutes* of a near-decided match and only converges to the outcome in the last ~30 min.
Retrospectively, at the true resolution anchor (`maturity_time`, buy-favourite [0.65,0.98], 1¢ haircut,
event-clustered):

| horizon before resolution | net (all sports) | verdict |
|---|---|---|
| −0.5h | **+6.29¢** [+3.86,+8.54] p≈0 | underpriced (edge) |
| −1h | **+3.92¢** [+0.89,+6.83] p=0.004 (431 ev) | underpriced (edge) |
| −2h | −6.91¢ | OVERpriced (efficient-to-rich) |
| −3h/−6h | −5 to −6¢ | overpriced |

The sign **inverts by horizon** — this is a late-convergence / in-play-latency inefficiency, not a
static favourite premium (that is what distinguishes it from weather and the champion).

**It generalizes across three independent regimes** (kills the `favorite_v2` tennis-artifact worry):

| regime | −0.5h | n |
|---|---|---|
| ATP/WTA tennis | **+7.55¢** p<.005 | 287 |
| ITF tennis | **+3.94¢** p<.005 | 840 |
| **esports (CS2/Valorant/Dota/LoL)** | **+4.51¢** p=0.02 | 218 |

An artifact would be sport-specific; the same horizon signature across three regimes is a **universal
microstructure effect** — a thin book lags a near-decided favourite. The −0.5h anchor (final ~30 min)
is where it is strongest and most universal — live, that is "serving for the match" (tennis) or
**"map/match point" (esports).**

**Why every LIVE-KNOWABLE trigger was negative WITHOUT an external clock (the whole reason a feed is
required).** Retrospective capture needs the *actual* resolution time to ±30 min, and nothing in our
market data locates it:
- venue `endDate` is **~4h BEFORE** actual resolution (median last-print − endDate = **+239 min**);
- `gameStartTime` is +123 min from the last print (IQR [89,170]);
- price-only triggers (persistence, drawdown-from-max, low-vol), fraction-of-observed-life, and every
  schedule-anchored proxy all read **−3 to −6¢** (p≥0.97).
- anchor jitter survives ±30 min (+3.78¢) but **collapses at ±60 min** (+0.44¢, p=0.39).

So the edge lives entirely in the **game-clock dimension**, invisible to price+schedule. **Only a live
game-state feed locates the final ~30 min.** That is this project's entire premise.

---

## 2. THE bo3.gg FEED

**What it provides (CS2-anchored).** bo3.gg is a live CS2 match tracker (already used by Foresight for
per-map player stats — `[[project-foresight-data-source]]`): live **series map score** (Bo1/Bo3/Bo5),
the **in-progress map's round score**, team names, and match/series status. It also covers **Dota 2**
and **Valorant**; **LoL** coverage is weaker and should be treated as out-of-scope until verified.
Free, read-only, JSON/HTML endpoints (poll politely — see §5). This is the direct analog of the free
ESPN scoreboard the tennis harness already uses.

**Coverage vs the US esports book (measured, `us_mid_tape`).** The US venue lists exactly the titles
bo3.gg covers, CS2 largest:

| title | US markets | tape ticks | bo3.gg live coverage |
|---|---|---|---|
| **cs2** | 161 | 187k | **core — anchor the build here** |
| lol | 102 | 116k | weak/separate — defer |
| dota2 | 33 | 41k | yes |
| valorant | 30 | 38k | yes |

CS2 alone (161 markets) is a larger clean universe than the tennis harness's Wimbledon window and is
year-round → **evergreen**. Build CS2-first; add Dota2/Valorant once the CS2 join is verified live.

**The join (bo3.gg match ↔ Polymarket US slug).** Identical pattern to `finalhour_forward.py`'s
ESPN↔`us_markets.parquet` join, retargeted:
- Polymarket US esports slug shape: `aec-cs2-<team1>-<team2>-<date>` (match-winner) — team codes are
  truncated, so **never match on the slug code**; match on the **full team names** from the market's
  `outcomes` (the bug that made the tennis harness silently inert was matching ESPN full names against
  truncated slug codes — do not repeat it).
- Name-token overlap (≥4-char tokens, both teams present) + **orientation guard**: the YES contract's
  team is `outcomes[i] where side_long[i]` (NOT slug order); the YES team we would buy MUST equal the
  bo3.gg leader, else it is an inverted losing-side bet → skip. Guard both ways in the self-test.
- Coverage caveat inherited from tennis: the harness fires only when the leader is the YES side
  (~50% of markets); the rest are safely skipped (a future refinement, not a blocker).

**The live trigger (the game-state condition that stands in for "final hour").** Mirror `match_state()`
(the tennis "up a set + serving for the match" logic) onto esports series+map state. Near-decided =
**leader is one map from clinching the series AND commanding the in-progress map**:
- **CS2 match-winner (Bo3):** leader up **1–0 in maps** AND, in map 2, at **map point / within N rounds
  of clinching** (e.g. ≥12 rounds in a first-to-13 / MR12 map with a ≥2-round lead, or any overtime map
  point). (Bo3 2–0 is already resolved — exclude.)
- **CS2 single-map-winner markets:** the map's round score at **map point** (leader ≥12, one round from
  the map).
- **Dota2 / Valorant:** the series map/game score analog (leader one game from clinching + commanding
  in-progress game); freeze the exact per-title thresholds in the PREREG before any data.

Fire ONLY when: (a) bo3.gg says near-decided, (b) the US book still prices the leader's YES **ask** in
band, (c) not warm-up (≥30 min of book history). Enter at the **real ask** (gate the ask actually paid,
not the mid — a wide market can have mid in-band, ask out of band).

---

## 3. THE FORWARD-PAPER HARNESS (fork, do not rebuild)

Fork `scripts/niche/finalhour_forward.py` → `scripts/niche/finalhour_esports_forward.py`, swapping the
feed layer only:
- **Feed:** `espn_live_near_decided()` → `bo3_live_near_decided()` (poll bo3.gg CS2 first; parse series
  map score + in-progress round score; return near-decided matches with leader + feed_state).
- **`match_state()` → `series_state()`** for map/round near-decided (self-tested with fixtures:
  1–0 + map point → fire/leader; 1–1 → no; 2–0 → excluded-as-resolved).
- **Universe/tape:** reuse `us_mid_tape` (`aec-cs2-%`, `aec-dota2-%`, `aec-valorant-%`), `state='OPEN'`.
- **Settlement:** reuse `dmr_outcome()` — official US **DMR** (`us_daily_market_report`,
  `business_date=maturity_date`, `settlement_price∈{0,1}`); terminal-state fallback never defaults a
  null market to a WIN.
- **Ledger:** append-only `finalhour_esports_paper_signals` (new migration, default-inert), same
  columns + `title`. **No order path.**
- **Execution spine (reuse, paper only):** `scripts/execution/risk_gate.py` (kill-switch,
  niche-allowlist, band, min-EV, ⅛-Kelly, per-event cap, $50/$100/$250 ladder) and
  `us_order_client.py` **paper** client (live client refuses at three latches; transport
  unimplemented). Nothing here can place an order.
- **Persistence:** launchd timer (fork `com.tue.collapse.forward.plist`) → `--scan` + `--settle` every
  ~2–5 min (esports states move faster than tennis; still polite to bo3.gg). Durable, reaper-proof,
  read-only except the append-only ledger.
- **`--report`:** ROI + esports-standalone λ + per-title + warmup split vs the frozen gate.

---

## 4. PRE-REGISTERED SUCCESS BAR (freeze BEFORE any forward data)

All **four modern bars**, on clean (non-warmup) forward CS2 entries at the real ask, official DMR
settlement, event-clustered, plus esports-specific floors:

1. **Walk-forward-stable:** ≥3 expanding folds (test block strictly later than train), pooled ROI
   LB > 0, no fold materially negative. (CS2 is year-round ⇒ disjoint weeks are achievable — the exact
   thing weather structurally could not provide.)
2. **λ CI-LB > 0 at ≥50% trajectory coverage** — the bar that killed weather. Measured on the US mid
   tape (`us_mid_tape`), close = last non-degenerate mid after entry, at a **fair tradeable lead**
   (not the last 5 min). **This is the make-or-break bar and the primary deliverable of the forward
   run** (esports λ has never been isolated).
3. **Brier-beat OOS:** the trigger's implied win-prob beats the market mid's Brier on pooled OOS.
4. **ROI LB > 0 at the realizable ask** on official DMR settlement, net of the corrected US fee
   `0.06·p·(1−p)` (already inside `finalhour_forward.fee_us`).

Plus: **≥60 clean+settled events, point ≥ +2.0%, positive in ≥2 esports titles, across ≥2 disjoint
weeks.** Warm-up entries excluded. Freeze all thresholds in a PREREG file before the first live scan;
do not tune to data. **Exploratory-search discount:** the retrospective edge came from a multi-cell
horizon/band/anchor search — nominal p-values overstate; the cross-regime replication + this forward
test are the mitigation, which is exactly why the gate is pre-registered and live.

---

## 5. COST-ZERO NOW vs NEEDS-TUE

**Cost-zero / buildable now (no human, no money, no key):**
- bo3.gg live polling (free, read-only), CS2 first; `us_mid_tape` already flowing; DMR settlement
  already backfilled; harness fork + execution spine already exist as paper components; launchd
  persistence pattern exists. The entire **paper** forward test is cost-zero.

**Needs Tue (each labelled):**
- **[human — verify before trusting accrual]** bo3.gg **ToS + rate limits**: confirm automated
  read-polling is permitted; if unclear, throttle hard (≥30–60 s between polls, cache aggressively,
  identify a UA) and treat as best-effort. **Read-only always; respect robots/ToS; no scraping that
  the terms forbid.** If bo3.gg disallows automated access, fall back to another free CS2 live source
  (HLTV/Liquipedia live) or mark the CS2 path blocked — do NOT buy a paid feed without Tue.
- **[human — one live-schema pass]** verify the bo3.gg live-match JSON field names against a real LIVE
  CS2 match once (`--scan --dry`), exactly as the tennis harness still needs for ESPN — fixtures ≠ live
  schema.
- **[Tue — money path, LATER, only if it certifies]** the live order transport + credentials + the
  ToS/legal decision on the US venue. Not in scope until all four bars are green forward.
- **No paid feed is required for CS2.** LoL would need a separate source (defer).

---

## 6. WHY THIS ESCAPES WEATHER'S HINDSIGHT TRAP (the crux distinction)

Weather **failed bar #2 structurally**: a weather market's price tracks the day's temperature *as it is
continuously revealed*, so at any fair pre-resolution lead the market has NOT moved toward the pick
(CLV ≈ 0 to negative) — there is no lagging book to exploit, only continuous revelation the market
prices in lockstep. CLV measured late is just the answer leaking in.

The final-hour esports edge is the **opposite mechanism**: a **discrete, verifiable near-decided
game-state** (map point) exists and is knowable via the feed **before the thin US book fully prices
it** — the retrospective λ>0 says the market *subsequently converges up* to confirm the favourite over
the final ~30 min. The information (game state) leads the price; the book *lags* it. That latency is
capturable precisely because the feed observes the state before the market reprices — which is why, at
the true anchor, CLV is **positive** (λ 0.1–0.44) where weather's is negative.

**One-line:** weather's price already knows what the feed would tell us (continuous revelation, no
lag); the esports book does NOT yet know what the feed tells us (discrete state, thin-book lag). Only
the second is an information edge. **The forward test's job is to prove that esports specifically —
not just the tennis-heavy pool — carries that positive λ at a live-knowable trigger.** If it does,
this is the project's first certifiable arm. If it does not, it joins the honest NO ledger. Base rate
says NO; the λ>0 signature is the only reason to spend the build.
