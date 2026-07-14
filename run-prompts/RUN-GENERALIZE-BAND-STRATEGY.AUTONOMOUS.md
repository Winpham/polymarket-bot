# Autonomous Run: Generalize the Band‑Strategy — find any OTHER optimized profitability cell (market × sport × price‑band × trader‑cohort) that matches or beats the champion `favorite` 0.71–0.98

> **Read this whole brief before touching anything.** You are an autonomous build worker on
> `~/polymarket-bot` (Rust + Python + SQL Polymarket consensus/copy‑trading **PAPER** system). A prior
> run found ONE validated edge: `favorite`, price band **0.71–0.98**, no liquidity floor, ~**+8% ROI‑on‑
> turnover** in‑sample with ~5pts of genuine consensus skill over the blind‑favorite baseline. Your job:
> **systematically test whether a SIMILAR optimized cell exists ANYWHERE ELSE** — other market categories,
> other sports, other price zones, other trader (wallet) cohorts — measured with the SAME rigor, and
> identify any cell that BEATS or COMPLEMENTS the champion on risk‑adjusted per‑dollar return OOS. If you
> catch yourself grid‑searching for the highest in‑sample number, chasing win rate, or reporting a cell
> that dies under the anti‑overfit battery, STOP — you have drifted. **Both "here is a certified new cell
> that beats/complements the champion + forward gate" and "no other cell generalizes — the champion
> 0.71–0.98 is unique, here is the proof" are SUCCESS. A goal‑sought green is failure.**

---

## 0. READ FIRST — inherit the state, do not re‑derive it

Before any query, read these (they are the accumulated truth; re‑deriving them wastes the run):
- **`STRATEGY-HANDOFF-favorite-consensus.md`** (repo root on `main`) — the champion strategy, the honest
  numbers, and THE central measurement hazard (capture bias, §below).
- **`DATA-MODEL.md`** — schema/flow. DB = docker `polymarket-bot-postgres-1`, db `polymarket`, user `bot`.
  Query: `docker exec -i polymarket-bot-postgres-1 psql -U bot -d polymarket -c "..."`.
- **`reports/SOFT-MARKET-EDGE.json`, `reports/ESPORTS-CONVERSION-GAP.json`, `reports/PREREG_20260710T050430Z_softmarket.md`.**
- The memory topics: `project-polymarket-soft-market-esports`, `project-polymarket-crossmarket-bands`,
  `project-polymarket-identify-skilled`, `project-polymarket-per-sport-conditioning`,
  `project-polymarket-garbage-policy`, `project-polymarket-softness-skill-map`.

**Settled — do NOT re‑litigate (build on, don't repeat):**
- Champion `favorite` 0.71–0.98, no liquidity floor, flat‑shares, match‑clustered. The 0.65–0.71 band is
  DEAD (near‑coinflip favorites are efficient). The liquidity floor HURTS here (the edge lives in softer,
  less‑liquid markets). Tennis is POSITIVE on the unbiased sample (+13.5%/LB+6.3%) — the old "tennis
  negative" was a capture‑bias artifact, corrected.
- DEAD, do not revisit: past‑PnL trader ranking (refuted 5 ways), `market_resid`, congregation/specialist
  book, per‑sport conditioning INTO efficient markets (regressive), min‑backers loosening, finer‑than‑0.10
  price bands, wide‑consensus.
- The champion's edge is ~2pt structural (favorite‑longshot) + ~5pt consensus skill, but it is
  SUMMER‑TOURNAMENT‑heavy and its signal VOLUME is draining as tournaments end — transfer to fall/efficient
  markets is UNPROVEN. Treat "does it transfer / is there a non‑tournament cell" as the live question.

---

## 0.5. THE OBJECTIVE (this is the whole run — optimize THIS, nothing else)

> **For each candidate cell = (category × sport × price‑band × trader‑cohort), maximize the CLUSTER‑ROBUST
> one‑sided 95% LOWER BOUND of realizable, COPYABLE ROI‑on‑turnover, subject to a bet‑volume floor AND a
> duration/disjoint‑regime floor, that SURVIVES the full anti‑overfit battery and BEATS (or usefully
> complements, i.e. is uncorrelated‑positive with) the champion `favorite` 0.71–0.98 on that same metric.**

- **Realizable copyable ROI‑turn** = Σpnl / Σstake at OUR executable entry, fee `0.03·p·(1−p)` per share.
  Entry basis: prefer `entry_ask` where UNBIASED coverage exists; else `initial_mean_price` ONLY after
  re‑confirming (per cell) that it ≈ `entry_ask` (the champion check: sharp‑fill − ask ≈ −0.13¢). NEVER
  the sharps' early fill if it diverges from the realizable ask (copyability cap).
- **Belief‑blind SKILL is mandatory**: report surplus over the `_blind` baseline AT THE SAME band/cell.
  Favorites are ~2pt structurally underpriced everywhere; only the surplus over blind is the harvestable
  skill. A cell whose edge ≈ its blind baseline is riding structure/softness, not skill — it will not
  transfer. Also run `selection_null` (p≤0.01, ≥1000 draws) on any candidate.
- **Volume floor** ≥ ~20 MATCH‑clusters AND ≥ ~3 signals/active‑day (deployability). Below → INDETERMINATE,
  never "best".
- **Duration/regime floor** ≥ ~7 active days AND ≥2 disjoint non‑expiring regimes (e.g. ≥2 distinct sports/
  disciplines/tournaments each over an 8‑cluster sub‑floor). One tournament weekend is NOT a strategy.
- **Win rate and total P&L are DIAGNOSTICS ONLY.** The win‑rate trap (deep favorites win ~99% but earn ~0
  per dollar) and the total‑P&L trap (one soft week inflates Σ$) are both disqualifying framings.
- The deliverable = the ranked cell map + any cell that clears ALL floors + belief‑blind + anti‑overfit AND
  beats/complements the champion OOS. Nothing promotes; a forward gate is the arbiter.

---

## 1. Mission — map → measure → gate → register

**HARD‑STOP + commit + write findings after EACH phase** so a reaped run is salvageable.

1. **Map the cell space.** Enumerate cells with `scripts/market_taxonomy.py` (category × market‑type),
   `scripts/sport_edge_tracker.py` (sport regimes), the ~0.10 price bands (0.55–0.65 / 0.65–0.71 /
   0.71–0.82 / 0.82–0.90 / 0.90–0.98), and TRADER COHORTS (eligibility‑rank bands: top‑40 / 41–100 /
   101–250 / 251+, and consistency‑ranked candidate wallets — see §2 trader guard). Emit
   `reports/CELL-MAP.json` with per‑cell resolved counts + match‑cluster counts so under‑powered cells are
   flagged BEFORE measurement (they read INDETERMINATE, not "worst"). **Commit.**
2. **Measure each cell on the objective.** Extend `scripts/soft_market_edge.py` (reuse
   `effective_n.cluster_robust`, `superkey.super_event`, its LODO + duration/regime gates) into a
   `scripts/cell_scan.py` (read‑only, `--selftest`) that computes, per cell: realizable ROI‑turn point +
   cluster‑robust LB + bootstrap LB, win‑rate + skill‑over‑blind + capacity (deployable‑$ from
   `clob_price_tape` where present) as diagnostics. Emit `reports/CELL-EDGE-MAP.json` ranked by the LOCKED
   objective. **Commit.**
3. **Apply the anti‑overfit battery + head‑to‑head.** For every candidate above the floors: LODO jackknife
   (drop the dominant sub‑regime), time‑split OOS (early vs late), cluster bootstrap 2nd opinion, Bonferroni/
   BH over the # of cells tested (say how many), a documented A‑PRIORI MECHANISM for any band cut, and the
   `selection_null` gate. Head‑to‑head each survivor vs champion `favorite` 0.71–0.98 on the identical
   realizable metric, and test correlation (a COMPLEMENT must be positively‑EV AND low‑correlated with the
   champion's match‑level returns). **Commit.**
4. **Shadow‑register + pre‑register the forward gate.** Any cell that BEATS or COMPLEMENTS the champion,
   clears the floors + belief‑blind + battery, earns an additive `alerting=false`, default‑off shadow arm
   in `consensus.rs` (champion + all incumbents byte‑identical) + a frozen
   `reports/PREREG_<UTCstamp>_cellscan.md` (objective, NI margin vs champion, floors, ≥2‑regime rule,
   LODO‑must‑survive, kill condition). Nothing promotes; forward data decides. **Commit.**

---

## 2. Rigor & anti‑overfit defense (LOAD‑BEARING — this is where the prior run's mistakes live)

- **THE CAPTURE BIAS (read this twice).** `entry_ask` is captured on the first housekeeping pass (~10–15
  min post‑fire), so FAST‑resolving picks (obvious chalk = winners) never get an ask; only slow/contested
  (loss‑prone) markets do. The captured‑ask sample is loser‑tilted by ~7pts — measuring realizable ROI on
  it alone is PESSIMISTICALLY biased and will falsely kill real cells (it already falsely killed "tennis").
  Mitigations, in order: (a) prefer the `clob_price_tape` best_ask (continuous, UNBIASED) where it covers
  the cell's window; (b) else use `initial_mean_price` AFTER per‑cell confirming it ≈ `entry_ask`; (c)
  report entry_ask‑only numbers as a biased bracket, never as the truth. If you can cheaply implement
  **capture‑at‑detection** (record the ask the instant a signal fires) that is the highest‑value fix — but
  it is default‑off and paper‑only.
- **Match clustering is mandatory** (`superkey.super_event`), NEVER `event_slug` — soccer/series leg‑piling
  inflates cluster counts and manufactures false‑tight LBs (the prior run's error; soccer's "90 clusters"
  was really ~30 matches).
- **Mechanism‑only cuts.** A band/cell cut is valid ONLY with an a‑priori mechanism you'd predict BEFORE
  looking (e.g. "near‑coinflip favorites are efficient" → drop 0.65–0.71; "deep favorites earn ~0/dollar" →
  watch 0.90+). "Remove whatever lost in‑sample" is FORBIDDEN — it always inflates the backtest and never
  replicates. Do NOT slice finer than ~0.10‑wide bands (the data floor: ~20–90 clusters/band).
- **Belief‑blind + skill split** (mandatory, §0.5). Certify surplus‑over‑blind + `selection_null`, not raw
  win rate or raw softness.
- **LODO jackknife + time‑split OOS + bootstrap** on every candidate (these caught the dota2 soft‑week
  artifact and the champion's own late‑half fade). A cell that only survives WITH its dominant sub‑regime,
  or only in the early half, is not durable.
- **Multiple‑testing is real.** You are scanning many categories × sports × bands × cohorts. Bonferroni/BH
  over the count; report how many cells were tested. The more cells, the higher the LB bar.
- **Realizability + capacity + copyability.** Measure at OUR entry (§capture bias). Report per‑cell
  deployable‑$ ceiling from `clob_price_tape` (read‑only — owned by other runs). Thin soft books = high %
  on tiny $ that does NOT scale; a fat % on unfillable size is not a strategy.
- **TRADER/wallet guard (the refuted axis).** Ranking wallets by past PnL was REFUTED 5 ways (survivorship
  + uncopyable timing/price). Trader cohorts may ONLY be formed by (a) eligibility‑rank BANDS, or (b) a
  sustained‑CONSISTENCY metric over the long `trader_fills` history as a HYPOTHESIS GENERATOR — then
  certified forward/belief‑blind at OUR realizable entry, Bonferroni over the # screened. A wallet whose
  edge is timing/price we can't copy certifies to ~0. Reuse `compute_trust_map`/earned‑trust where it fits.
- **Volume‑flow durability.** The champion's signal volume is draining as summer tournaments end. A cell
  that only fires during an expiring tournament is not a forward strategy — track signals/day and flag
  tournament‑only cells.
- **Correlated‑unit honesty.** Cluster at the MATCH; a complement must be low‑correlated with the champion
  at the match level (else it's the same bet re‑labeled).

**The forward gate is the final arbiter.** In‑sample/OOS certification earns a shadow slot + a frozen
forward gate; forward weeks (especially the transition OUT of summer tournaments) decide.

---

## 3. Build order (checkpoint + commit after EACH; a timed‑out run is "incomplete + resumable")

1. Cell‑space map → `reports/CELL-MAP.json` + a one‑paragraph coverage read. **Commit.**
2. `scripts/cell_scan.py` (read‑only, `--selftest`) + `reports/CELL-EDGE-MAP.json` ranked by the objective.
   **Commit.**
3. Anti‑overfit battery + champion head‑to‑head + complement/correlation test → `reports/CELL-VERDICT.json`
   + a one‑paragraph verdict per surviving cell (or "none survive"). **Commit.**
4. For any survivor: additive default‑off shadow arm in `consensus.rs` (champion + incumbents
   byte‑identical; unit test the knobs inert for every other arm; `cargo test --bin copy-trading-bot` +
   clippy green) + frozen `reports/PREREG_<UTCstamp>_cellscan.md`. **Commit.**

Branch off `main` (which now carries the champion strategy + soft‑market shadow arms + instruments). NEVER
edit another active worktree's branch; use `git worktree add` for isolation.

---

## 4. Guardrails (violating any = failed run)

- **Paper‑only; promotes nothing; arms nothing; real‑money eligibility UNCHANGED.** Any new arm
  `alerting=false`, default‑off flag. No `.env` arming edits.
- **Safe‑swap:** champion `favorite` + `favorite_liq`/`favorite_v2`/`elite_fresh_fav`/`strict`/`soft_fav*` +
  `ConsensusParams::default` byte‑identical; every new knob a no‑op default.
- **Cost‑zero / Max‑only:** never set `ANTHROPIC_API_KEY`, never spawn child `claude`. Python =
  numpy/pandas/psql/stdlib only. DB read‑only except the bot's normal accrual writes;
  `clob_price_tape`/`trader_fills` SELECT‑only.
- **No new migration** unless a genuine schema/pipeline defect — then STOP and report (likely a separate
  run). Rust gate = `cargo test --bin copy-trading-bot` + clippy.
- **Coordinate** with other worktrees/branches (maker‑copy‑g3 owns tape/fills). Non‑overlapping slices; if
  you'd collide, yield.
- **No re‑litigating settled findings** (§0): total‑P&L and win‑rate‑alone are WRONG objectives; per‑sport
  conditioning into efficient markets is regressive; past‑PnL trader rank is refuted; finer bands overfit;
  the liquidity floor hurts the favorite band.

---

## 5. Completion criteria (honest definition of done)

Green = ALL of: (1) the cell space MAPPED with per‑cell power flagged (`CELL-MAP.json`); (2) every
sufficiently‑powered cell MEASURED on the LOCKED objective, belief‑blind, match‑clustered, at realizable
(unbiased) entry (`CELL-EDGE-MAP.json`); (3) the anti‑overfit battery + champion head‑to‑head +
complement/correlation applied, with a per‑cell verdict (`CELL-VERDICT.json`); (4) for any survivor, a
default‑off shadow arm (tests+clippy green, champion byte‑identical) + a frozen forward‑gate prereg; (5) a
one‑paragraph bottom line.

**Do NOT claim any cell is "real" or "bankable."** Claim: which cells (if any) clear the belief‑blind,
realizable, anti‑overfit bar at ≥ the floors and beat/complement the champion OOS; each survivor is
shadow‑registered with a forward gate; and the durability verdict lands in forward weeks (esp. the
transition out of summer tournaments). If the honest answer is "no other cell generalizes — the champion
0.71–0.98 is the only validated edge, and here is the proof (tennis rides the same summer softness; esports
is INDETERMINATE; crypto/econ/politics never fire; deeper trader cohorts add no copyable skill)" — that is a
fully valid, high‑value result: it tells the human the edge is singular and saves wasted build effort. The
value is a trustworthy per‑dollar‑edge verdict across the full cell space, not a bigger in‑sample number.
