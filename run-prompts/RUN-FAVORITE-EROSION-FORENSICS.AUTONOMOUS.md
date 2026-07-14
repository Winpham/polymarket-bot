# Autonomous Run: Favorite‑Edge Erosion Forensics — WHY is the champion `favorite` 0.71–0.98 softening, and is there anything mechanism‑justified we can do about it?

> **Read this whole brief before touching anything.** You are an autonomous forensic worker on
> `~/polymarket-bot` (Rust + Python + SQL Polymarket consensus/copy‑trading **PAPER** system). The champion
> strategy — `favorite`, price band **0.71–0.98**, match‑clustered — held ~**+8% cumulative ROI‑on‑turnover**
> for two weeks, then **eroded** over the last several days: cumulative slid 8.4% → 8.3% → 8.0% → 7.8% →
> **7.1%**, win rates drifted 90–100% → ~83%, and a full‑volume day (07‑13, 29 bets/20 matches) came in
> **−2.8%** — the first real‑N down day in the recent cluster (07‑11 +2.9, 07‑12 −8.5, 07‑13 −2.8). Your job:
> **enumerate and TEST every plausible cause of this softening, attribute it, and determine whether any
> mechanism‑justified, belief‑blind‑validated response exists — or prove the honest answer is "variance" or
> "summer‑tournament edge fading on schedule, nothing to do but stop/wait."** If you catch yourself
> curve‑fitting a patch to the last week, chasing the story instead of ruling out variance FIRST, or
> proposing a "fix" with no a‑priori mechanism, STOP — you have drifted. **Both "here is the diagnosed cause
> + a mechanism‑justified, forward‑gated response" and "it is variance / on‑schedule tournament fade — no
> action is warranted, here is the proof" are SUCCESS. A goal‑sought fix is failure.**

---

## 0. READ FIRST — inherit the state, do not re‑derive it

- **`STRATEGY-HANDOFF-favorite-consensus.md`** (repo root, `main`) — the strategy, the honest numbers, and
  THE central measurement hazard (capture bias).
- **`DATA-MODEL.md`** — schema/flow. DB = docker `polymarket-bot-postgres-1`, db `polymarket`, user `bot`.
  Reproduce the daily table: favorite, resolved, band 0.71–0.98, clustered at `superkey.super_event`, fee
  `0.03·p·(1−p)`, per `first_detected_at::date`.
- Memory: `project-polymarket-soft-market-esports` (capture bias + renovated favorite + volume drain),
  `project-polymarket-drawdown-0706` (the TEMPLATE — a prior drawdown DIAGNOSED to supply‑regime + eligibility
  hole, variance ruled out at p≈0.002; reuse its method), `project-polymarket-cell-scan` (champion is
  singular; tennis rides the same summer softness), `project-polymarket-regime-persistence` (SOCCER‑ARTIFACT
  confirmed — the edge is tournament‑carried), `project-polymarket-softness-skill-map`.

**Settled context — the softening is EXPECTED‑ish, so weigh variance heavily:** the edge is
summer‑tournament‑carried (World Cup, Wimbledon), its skill is ~5pt over a ~2pt structural blind baseline,
and Wimbledon has ended / the World Cup final is ~07‑19. A fade as tournaments end is the PRIOR, not a
surprise. Your job is to distinguish *which* fade this is and whether anything is actionable.

---

## 0.5. THE QUESTION (this is the whole run — answer THIS, nothing else)

> **Decompose the recent ROI erosion of `favorite` 0.71–0.98 into its cause(s), ruling out variance FIRST
> with a hard test; then determine whether any response is mechanism‑justified AND survives belief‑blind /
> OOS validation — or conclude no action is warranted.**

The winning deliverable is a **trustworthy attribution + an honest action verdict**, NOT a patch that makes
the backtest prettier. Measure everything on the locked realizable metric (cluster‑robust ROI‑on‑turnover at
OUR entry, match‑clustered, belief‑blind surplus over `_blind`). Win rate and total P&L are diagnostics only.

---

## 1. Mission — enumerate → test → attribute → act (or don't)

**HARD‑STOP + commit + write findings after EACH phase** so a reaped run is salvageable.

### Phase A — Rule out VARIANCE first (the null; do this before any story)
Is the ~1.3pt cumulative drop over ~5 days even outside the noise of a stable +8% edge? Block‑bootstrap /
permutation the per‑MATCH ROI: under the null of a constant +8% edge with the observed match‑level variance,
what is the probability of a recent‑window drawdown ≥ what we saw? (Mirror the drawdown run's method that
returned p≈0.002.) Report the p‑value. **If variance is NOT ruled out (p not small), the honest answer may
already be "cold streak — no action"; still run the decomposition below for completeness but weight it
accordingly.** Emit `reports/EROSION-VARIANCE-NULL.json`. **Commit.**

### Phase B — Decompose the erosion across every plausible axis (only if/where variance is suspect)
For each, compare the recent window to the earlier window on the realizable, belief‑blind metric:
1. **Edge decay** — is the skill (surplus over `_blind` at the same band) actually shrinking over time, or
   only the raw ROI? Rolling skill vs rolling total edge.
2. **Market efficiency / crowding** — is the `_blind` structural underpricing ALSO shrinking (whole market
   tightening as late‑tournament money enters), i.e. softness being arbitraged away?
3. **Tournament/regime MIX shift** — is the erosion because the firing MIX moved to lower‑edge cells
   (Wimbledon ended → tennis gone; World Cup group‑stage softness → knockout efficiency; new sports)? Decompose
   recent ROI by sport / tournament / phase. This is the leading hypothesis given the prior.
4. **Price‑band drift** — are recent picks landing in worse sub‑bands (nearer 0.71 or deeper 0.90+)? Entry
   distribution over time.
5. **Trader/eligibility composition** — are recent signals backed by different/fewer sharps, lower
   convergence (net_count, n_backers), or a rotated top‑40? Convergence‑quality over time.
6. **Pipeline/data artifact** — resolution completeness of recent days (are recent "picks" fully resolved?),
   entry‑price capture behavior over time, any capture‑bias interaction that worsens recent days. Rule OUT a
   measurement artifact before believing a real decay.
7. **Single‑cell contamination** — LODO by sport/tournament/day on the recent window: is one bad
   slate/discipline dragging the whole thing (like the dota2 artifact)?
Emit `reports/EROSION-DECOMPOSITION.json` attributing the drop across these axes (with % contribution where
estimable). **Commit.**

### Phase C — Action verdict (mechanism‑justified only)
For the attributed cause(s), determine whether a response is warranted AND defensible:
- **Variance** → do nothing (sizing/patience only).
- **On‑schedule tournament fade / crowding** → the edge is genuinely draining; the action is to PAUSE/stop as
  volume/softness dies, not to patch. Define the volume/skill floor below which the strategy self‑suspends.
- **Mix shift to a bad cell** → a mechanism‑justified exclusion (e.g. "knockout‑phase favorites are efficient")
  — but ONLY if it has an a‑priori mechanism AND survives belief‑blind + OOS + LODO (no data‑dredged patch).
- **Pipeline artifact** → a real fix (likely a separate run; STOP + report if it's a schema/capture defect).
Emit `reports/EROSION-ACTION-VERDICT.json` + a one‑paragraph verdict. Any proposed response ships ONLY as an
additive default‑off shadow arm + a frozen forward‑gate prereg; nothing promotes. **Commit.**

---

## 2. Rigor & anti‑overfit defense (LOAD‑BEARING)

- **Variance FIRST.** Do not construct a causal story before ruling out a cold streak. A 15‑day, ±15%‑daily
  series will *look* like it has trends that are pure noise. The bootstrap/permutation p‑value gates everything.
- **THE CAPTURE BIAS.** `entry_ask` is loser‑tilted (captured only on slow/contested picks). Prefer the
  unbiased `clob_price_tape` best_ask where it covers the window; else use `initial_mean_price` after
  confirming ≈ ask per window. A "recent decay" that is really a shift in capture coverage is an ARTIFACT —
  Phase B.6 must rule it out.
- **Match clustering mandatory** (`superkey.super_event`), never `event_slug` (leg‑piling inflates N and
  manufactures false trends). All windows compared at the match level.
- **Belief‑blind decomposition.** Always separate skill (surplus over `_blind` at the same band) from the
  structural/softness component. "Raw ROI fell" is ambiguous; "skill fell vs softness fell" is the real answer.
- **No data‑dredged patches.** Any exclusion/response needs an a‑priori mechanism you'd predict before looking,
  AND must survive belief‑blind + a time‑split OOS + LODO. Removing "whatever lost last week" is FORBIDDEN — it
  always improves the backtest and never replicates; it is the exact trap this run must avoid.
- **Multiple testing.** You are testing many axes/sub‑windows; Bonferroni/BH over the count and say how many.
- **Small‑window humility.** The "recent" window is a handful of days / ~50–100 matches — every recent‑window
  estimate has a wide CI. Read cluster‑robust LBs at small‑cluster t, and don't over‑attribute to a 3‑day blip.
- **Don't re‑litigate settled findings** (§0): per‑sport conditioning into efficient markets is regressive;
  past‑PnL trader rank is refuted; finer bands overfit; liquidity floor hurts; the edge is tournament‑carried.

---

## 3. Build order (checkpoint + commit after EACH; a timed‑out run is "incomplete + resumable")

1. Phase A variance‑null → `reports/EROSION-VARIANCE-NULL.json` + p‑value + one‑line read. **Commit.**
2. Phase B decomposition script (read‑only, `--selftest`, reuses `effective_n`/`superkey`/`market_taxonomy`/
   `sport_edge_tracker`/`selection_null`) → `reports/EROSION-DECOMPOSITION.json`. **Commit.**
3. Phase C action verdict + (if warranted) an additive default‑off shadow arm in `consensus.rs` (champion +
   incumbents byte‑identical; `cargo test --bin copy-trading-bot` + clippy green) + frozen
   `reports/PREREG_<UTCstamp>_erosion.md`. **Commit.**

Branch off `main`; isolate with `git worktree add`; never edit another active worktree's branch.

---

## 4. Guardrails (violating any = failed run)

- **Paper‑only; promotes nothing; arms nothing; real‑money eligibility UNCHANGED.** Any new arm
  `alerting=false`, default‑off flag; no `.env` arming edits.
- **Safe‑swap:** champion `favorite` + all incumbents (`favorite_liq`/`favorite_v2`/`elite_fresh_fav`/`strict`/
  `soft_fav*`) + `ConsensusParams::default` byte‑identical; every new knob a no‑op default.
- **Cost‑zero / Max‑only:** never set `ANTHROPIC_API_KEY`, never spawn child `claude`. Python =
  numpy/pandas/psql/stdlib only. DB read‑only except the bot's normal accrual writes; `clob_price_tape`/
  `trader_fills` SELECT‑only.
- **No new migration** unless a genuine schema/capture defect — then STOP and report. Rust gate =
  `cargo test --bin copy-trading-bot` + clippy.
- **Coordinate** with other worktrees (maker‑copy‑g3 owns tape/fills); non‑overlapping; yield on collision.

---

## 5. Completion criteria (honest definition of done)

Green = ALL of: (1) variance ruled in/out with a reported p‑value (`EROSION-VARIANCE-NULL.json`); (2) the
erosion decomposed across the seven axes on the realizable, belief‑blind, match‑clustered metric
(`EROSION-DECOMPOSITION.json`); (3) an action verdict that is EITHER "no action (variance / on‑schedule fade),
here's why" OR a mechanism‑justified response shipped as a default‑off shadow arm + frozen forward gate
(`EROSION-ACTION-VERDICT.json`); (4) a one‑paragraph bottom line.

**Do NOT claim the edge is "dead" or "fixed."** Claim: what the recent erosion IS (variance vs decay vs
mix‑shift vs crowding vs artifact), with the numbers; whether anything mechanism‑justified can be done; and
that the durability verdict lands in forward weeks past the World Cup final (~07‑19). If the honest answer is
"this is a summer‑tournament edge fading on schedule as the tournaments end — the only sound action is to let
it self‑suspend on the volume/skill floor and wait for fall sports to test transfer" — that is a fully valid,
high‑value result that stops the human from over‑engineering a patch for a cold, seasonal tail. The value is a
trustworthy attribution, not a prettier recent‑window number.
