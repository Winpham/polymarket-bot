# Autonomous Run: The Evergreen Book + The Sharps — what pays every day, and who actually pays it

> **Read this whole brief before touching anything.** You are an autonomous build worker on
> `~/polymarket-bot` (Rust + Python + SQL Polymarket consensus/copy-trading **PAPER** system —
> no real money, ever, in this run). The tracked universe was just widened to **depth 1000**
> (2026-07-13) and a **market-side discovery lane** was built that enumerates traders the
> leaderboard structurally cannot show us. You now have, for the first time, a pool wide enough
> to ask the two questions that actually matter:
>
> **A. WHICH EVERGREEN MARKETS PAY — every day, repeatedly, at OUR price?**
> Families that resolve on a daily cadence (temperature, esports dailies, sports dailies, …) are
> the only ones that compound: capital turns over, and an edge that is small per-signal can still
> be large per-year. Find the ones whose edge is **real, repeatable, and survives the cost of
> being a copier** — or prove there are none.
>
> **B. WHO ARE THE GENUINELY PROFITABLE TRADERS — across every market and strategy, in the whole
> wide pool?** Not the biggest. The *best*. Efficient, reliable, and — the part that has killed
> every previous attempt — **copyable at the price WE can actually get.**
>
> **Both "here is a certified evergreen book + a certified sharp roster, with forward proof" and
> "nothing certifies, and here is the proof of absence" are SUCCESS.** A goal-sought green is
> failure. If you catch yourself loosening a floor, dropping an inconvenient category, or tuning
> a knob to make a number go positive, **STOP — you have drifted.**

---

## 0. READ FIRST — inherit this state. Do NOT re-derive it, do NOT re-litigate it.

### The instruments (all `--self-test` green — **reuse, do not fork**)
- `scripts/specialist_mining.py` — per-(wallet × sport) surplus over the cell-blind favorite,
  clustered at the **match super-key**, with the **copyability transform** (re-price at OUR entry
  net of the measured per-sport follower tax), MM/price-improver exclusion, selection-null, and
  **BH-FDR q=0.10**. This is the trader-question engine. Extend it; do not rewrite it.
- `scripts/cell_lib.py`, `cell_scan.py`, `cell_map.py`, `regime_cell_scoreboard.py` — the cell
  machinery for the market-question.
- `scripts/skilled/` (`ws1_clv.py`, `ws2_reduced_variance.py`, `ws3_structural.py`,
  `ws4_roundtrip.py`, `null_baseline.py`, `skill_common.py`) — the skill battery.
- `scripts/audit_pnl_books.py`, `capture_completeness.py`, `audit_entry_realism.py`.
- `scripts/weather_scan.py`, `weather_verdict.py`, `weather_regions.py`.
- DB: `docker exec -i polymarket-bot-postgres-1 psql -U bot -d polymarket -c "..."`

### Memory to load first
`project-polymarket-market-side-discovery`, `project-polymarket-deep-universe-1000`,
`project-polymarket-exec-policy`, `project-polymarket-capacity`, `project-polymarket-weather`,
`project-polymarket-cell-scan`, `project-polymarket-identify-skilled`,
`project-polymarket-capture-defects`, `project-polymarket-favorite-consensus-null`,
`project-polymarket-latency`, `project-polymarket-honest-pnl`, `feedback-edge-exists-prior`.

### SETTLED — build on these, never re-derive them

**S1. The leaderboard is a VOLUME sort, not a skill sort.** Measured on our own pool:
`corr(rank, ROI) = −0.05` — rank says essentially **nothing** about efficiency. Mean volume falls
$11.2M (top-40) → $321k (rank 501–1000). Wallets with >10% ROI: 32 in the top-40, **304 in ranks
501–1000**.
⇒ **NEVER rank, select, weight, or gate a trader by rank, PnL, or volume.** Those are bankroll
proxies. If you find yourself sorting by PnL, you have reproduced the bug.

**S2. We were seeing 1.2% of the population.** Of the **4,341 wallets that traded recent weather
markets, our depth-1000 pool contained 50.** Depth 250→1000 only moved it ~17→50. An efficient
low-volume trader may never appear on the leaderboard **at any depth**. The net is
`/trades?market=<condition_id>` (**O(markets), not O(wallets)** — the wide net is *cheaper* than
the narrow one). Lane: `feat/market-harvest`, `cycles/market_harvest.rs`, flag `MARKET_HARVEST`.

**S3. COPYABILITY AT OUR PRICE IS THE BINDING CONSTRAINT — this is the wall that has killed every
prior attempt.** Follower tax ≈ **1.3¢**. In the leaderboard pool, **86 wallets had a real edge at
THEIR price and were DEAD at OURS** (typical: +1.0% edge vs a 1.3¢ tax ⇒ −0.3%). **0 certified.**
⇒ Raw profitability is not the question and never was. **Every claim in this run must be stated at
OUR realizable entry, net of the tax.** An edge that only exists at the sharp's fill price is a
publishable *negative*, not a finding.

**S4. Cluster at the MARKET / MATCH / DAY — never the fill.** A naive fill-clustered scan of the
wide pool put a **+0.69 surplus/fill "specialist" at the top of the list. It had 2 distinct
markets.** Pure small-N artifact. The independent-cluster count (distinct markets, distinct event
DATES) is the honest N and it is the wall. Day-deflated SE is the real bar; event-N SE is the
generous one — report both, certify on the former.

**S5. Market-maker / price-improver profit is STRUCTURALLY UNCOPYABLE.** Two-sided wallets and
systematic price-improvers must be excluded and reported, not ranked. (`specialist_mining` Phase 3
already does this — reuse it.)

**S6. DO-NOT-REOPEN: favorite-consensus is NULL.** Six converging negatives; Tue called STOP. No
more slicing, no more category-dropping, no more "but what if we condition on…". The incumbent
champion (`favorite` 0.71–0.98, **+5.6% LB**) is the **floor you must beat**, not a thing to
re-tune.

**S7. Latency is NOT the lever (RETRACTED).** The "15min = 8¢" claim was killed: real cost
+2.05¢ ± 4.0¢, p=0.36, and the placebo drifts more. **Speed is not the edge — spread is.** Do not
build a fast-lane and call it alpha.

**S8. Capacity: the BOOK binds, not the spread.** $50/signal comfortable (net +8.6% @p90), $100
ceiling, $250 hard stop, $500 negative. **A day is ONE correlated bet (~$1k/day).** Any "edge" that
requires size the book cannot absorb is not an edge.

**S9. Bounded budget + bad order = starvation (D1–D4).** Every bounded queue, every `LIMIT`, every
truncating cap in a pipeline you build or touch **must be audited for order-bias**. This class has
bitten this codebase four times. It will bite you.

**S10. Beware the 5-minute siren.** The btc/eth "+21.7%" was an artifact of 5-min up/down markets.
**Daily turnaround must not degenerate into high-frequency noise-mining.** A family qualifies as
"evergreen + daily" on *resolution cadence and repeatability*, not on trade frequency.

---

## 1. Mission

Produce **two certified artefacts, or two honest proofs of absence**:

1. **THE EVERGREEN BOOK** — the set of market families that pay **repeatably, every day, at our
   price, at a size the book can absorb**, with their measured correlation to each other.
2. **THE SHARP ROSTER** — the traders across the whole wide pool (leaderboard-1000 **+**
   market-harvested) who are genuinely skilled **and copyable**, with a per-trader certification.

And then the question that ties them together: **do the certified sharps concentrate in the
certified families?** If yes, that intersection is the product. If no, say so plainly.

---

## 2. Workstreams

### WS0 — Foundation: make the archive trustworthy before you mine it
Nothing downstream is worth anything if the capture is biased. Do this first, and be adversarial.

- Confirm the **full-history backfill** completed across the widened pool (`trader_fills`, ~2.3k
  wallets). Re-run `copy-trading-bot backfill` if not (idempotent).
- **Enable the market-side harvest** (`feat/market-harvest`, `MARKET_HARVEST=true`) so the hidden
  population's fills land. **Verify the safety invariants hold in prod**: harvested wallets are
  `active=FALSE, consensus_eligible=FALSE`, are never wallet-polled, and never back a signal.
  Watch `consensus_ingest_duration_seconds` (< 60s), `consensus_data_api_429_total` (0),
  `consensus_activity_window_unreadable_total` (0).
- **Audit for capture bias (S9).** `capture_completeness.py`. Ask specifically: is any bounded
  queue, page cap, or `LIMIT` dropping a *non-random* slice (deep ranks, the busiest wallets, the
  oldest fills, one family)? **A biased archive produces a confident wrong answer — that is the
  worst outcome available to you.**
- Known limitation to state, not hide: `fetch_full_history` is capped by the server at **3500
  events/wallet** (offset ceiling 3000). For a hyperactive wallet this is a *recent slice*, not
  full history. Quantify how many wallets are truncated and whether that truncation correlates
  with anything you go on to conclude.

### WS1 — The Evergreen Book: which families pay, every day, at our price?
Candidate families (do not stop here if the data suggests others): **temperature high**,
**temperature low**, **esports (cs2 / lol / dota)**, **daily sports** (mlb/nba/tennis/soccer
dailies), and any family with a **daily resolution cadence** you can defend. Apply S10 — screen out
the 5-minute siren.

For each family, in this order (stop early when a floor fails — that is a result, not a failure):
1. **The blind baseline.** What does the dumb favorite earn here? (Weather-high ≈ +2.1%;
   weather-low is *negative* — the casual crowd mis-prices cold. The blind is what your sharps must
   beat, and it differs per family. Never compare across families without it.)
2. **Skill over blind**, day-clustered, at the validated band **0.71–0.98** (and report 0.71–0.90 —
   deep chalk 0.90–0.98 is a known win-rate trap).
3. **Copyable edge at OUR realizable entry**, net of the measured per-family follower tax (S3).
   This is the number that decides. State it with a **day-clustered lower bound**.
4. **Repeatability** — the "consistent" in consistently profitable. Positive in **≥ N of M disjoint
   weeks**, survives **LODO** (leave-one-day/period-out), survives a **held-out period** you freeze
   BEFORE looking. Pre-register the split.
5. **Per-day compounding, not per-signal ROI.** This is the whole point of daily turnaround: a
   family with +3% per signal that fires daily beats one with +8% that fires monthly. Report
   **ROI-per-turn × turns/day**, net of cost, at a size the book absorbs (S8). Baseline to beat:
   the honest tracker's 6.95% ROI-turn @ 1.14 turns/day.
6. **Capacity** — book depth at fire time. An edge that dies at $50/signal is not tradeable (S8).
7. **Correlation across families.** The portfolio only diversifies if the day-ROI correlation is
   genuinely low (weather high×low ≈ +0.02 at the tradeable band — but that was **5 common days**,
   which is nothing. Re-measure it with real N before believing it).

### WS2 — The Sharp Roster: who is actually good, across everything?
The wide pool is the point. Score **every** wallet — leaderboard-1000 *and* market-harvested —
identically and **belief-blind**. Rank/PnL/volume must not enter the score (S1).

Pipeline (reuse `specialist_mining.py`; extend it to the harvested population):
1. **Surplus over the cell-blind favorite**, per (wallet × family), clustered at the **market/match
   super-key** with distinct-event-DATE N as the honest independent count (S4).
2. **Exclude MMs / price-improvers** (S5) — report them as a separate, named class.
3. **N-floor on independent clusters.** Pre-register it. This is your primary defence against the
   +0.69/2-market artifact, and with a 4,000-wallet pool it is doing most of the work.
4. **Copyability transform** — re-price at our entry net of the tax (S3). This is the gate that
   killed 86/86 last time. Expect carnage. **The prior finding is that the hidden population has
   candidates at +4% to +12% surplus/market vs a ~1.3¢ tax (3–9× the tax) where the leaderboard
   population had none — that is the hypothesis under test, not a result to confirm.**
5. **Selection-null** (is this wallet's selection distinguishable from a random same-(band × date)
   picker?) **+ BH-FDR q=0.10** across the whole wallet × family family. With thousands of
   candidates, multiplicity is not a formality — it is the main threat.
6. **Reliability**, explicitly: consistent across disjoint periods, not one hot streak. A trader who
   is +20% in one week and −8% in three others is not a sharp; they are variance.
7. **Cross-market breadth**: is anyone good in *more than one* family? (A generalist who clears the
   bar in three families is worth more than three specialists who clear it in one — different
   correlation profile.) Report the strategy archetypes you find, not just the names.

### WS3 — The intersection, and the portfolio
- Do the certified sharps **concentrate** in the certified families? Quantify. If the sharps live
  where the families pay, that intersection is the product.
- Build the candidate **portfolio**: certified families/sharps, weighted by the day-clustered lower
  bound, capacity-capped (S8), correlation-aware. A day is ONE correlated bet — size accordingly.
- **Does the portfolio beat the incumbent champion's honest floor (+5.6% LB)?** If it does not, say
  so. That is the bar. Beating it on an in-sample number is not beating it.

### WS4 — Adversarial verification (every survivor, no exceptions)
A finding that has not survived this is a hypothesis, not a result:
- **Label-permutation null** — shuffle outcomes, re-run the whole pipeline end to end. Your
  "edge" must vanish. (This is what refuted `market_resid`. It will refute things here too.)
- **Held-out period** frozen before you looked.
- **At realizable entry** — never at the sharp's fill, never at a proxy mid (the "at-fire mid" was a
  measured defect, D2; `entry_ask` was loser-tilted, D4).
- **Capacity stress** at $50 / $100 / $250.
- **Day-clustered LB > 0.** Event-N SE is the generous read; report it, but never certify on it.

### WS5 — Ship the truth
- **Pre-register** the forward gate for every survivor *before* enabling anything, in
  `reports/PREREG_<ts>_<name>.md`. Frozen. Floors may be ADDED, never loosened.
- Survivors become **shadow arms** (`alerting=false`, paper) and/or an **earned-trust promotion**
  for sharps — never an auto-promotion. Discovery is not trust.
- **`reports/EVERGREEN-AND-SHARPS.md`**: what pays, who pays it, what does not, and what you could
  not determine and why (power, capture, or capacity). Update memory.

---

## 3. Kill criteria — state these plainly when they fire

- **K1** — A family's copyable edge at our entry has a **day-clustered LB ≤ 0** ⇒ the family is DEAD
  for us, regardless of how good it looks at the sharp's price. Publish and move on.
- **K2** — A wallet's edge is real at THEIR price and dead at OURS ⇒ **K2-dead**. This is the
  expected majority outcome. Count them; do not rescue them.
- **K3** — A family/sharp survives in-sample but fails the **held-out** period or **LODO** ⇒ not
  reliable. "Consistently profitable" is the ask; one good window is not it.
- **K4** — Profit is structurally uncopyable (market-making, price improvement, size we cannot get)
  ⇒ a **publishable finding**, not a failure.
- **K5** — The whole roster/book fails to beat the champion's **+5.6% LB** floor ⇒ the honest answer
  is "the champion is still singular", and the deep pool bought us **coverage, not edge**. That is a
  legitimate and valuable result. **Say it.**
- **K6** — Power-limited (N too small to distinguish from zero) ⇒ **INDETERMINATE**, never "no
  effect", never "promising". Report the N you would need and how long it takes to accrue.

## 4. Rules of engagement

- **No real money. Paper only.** Nothing in this run promotes an arm to alerting or trading.
- **Extend, don't rebuild.** Every instrument you need mostly exists. Forking one to get a friendlier
  number is the failure mode this brief exists to prevent.
- **Honest completion.** A timed-out or partial run is "incomplete + resumable", never "done".
  Commit incrementally on a branch so a reaped run is salvageable.
- **Isolate the work**: branch + worktree. **Do NOT merge to `main`** — main auto-deploys to prod
  (the autoupdater builds local `main` on HEAD advance). Merging is Tue's call.
- **Report the negative as loudly as the positive.** The most valuable output of this run may well be
  "the deep pool gave us 80× the coverage and zero new certified edge" — and if that is the truth,
  it must be the headline, not a footnote.
