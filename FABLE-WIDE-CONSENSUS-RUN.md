# FABLE Wild-Generator Run — Wide-Pool Consensus (2026-07-08)

**One-line:** the champion's turnover is bounded by SIGNAL ARRIVAL, not capital or edge —
and the single largest measured pool of trapped signals is the voter-pool cutoff. The top-40
leaderboard rank gate throttles supply ~5× while carrying zero protective information
(past-PnL rank ≠ skill — refuted 5 ways, D30). This run ships `favorite_wide`: the exact
champion mechanism scored on the full tracked wallet universe (eligible ∪ deep non-bot),
paper-only, silent, shadow-first, judged by the standing gate.

Branch: `feat/wide-consensus` (off main 4940509). Flag: `CONSENSUS_WIDE_ARMS` (default OFF —
zero behavior change until flipped). Prereg: `reports/PREREG_20260708_wide_consensus.md`
(frozen before any forward outcome).

---

## 1. Ground truth established first (what actually binds the money)

- **There is no capital cap anywhere in the paper path.** Every qualifying signal books
  $100 flat at resolution (`FLAT_STAKE`, `append_paper_bet`). Turnover-multiple 1.14×/day is
  `avg daily staked ÷ peak concurrent capital` — a pure consequence of signal scarcity.
- **The supply cliff is here.** Favorite fires: 73/day (06-29) → 23-26/day (07-07/08), open
  concurrency 24 → 4. Recurring post-tournament supply ≈ 2.6-5 ev/day (FAVCONSENSUS-DEEPEN).
  The champion's daily $ is about to fall ~5× on the calendar alone.
- **The universe is not the constraint.** Tracked sharps touch ~2,500 events / ~7,000 markets
  per day (`trader_fills`). The consensus mechanism fires on ~20.
- **The voter cutoff is the hidden throttle.** Only rank ≤ 40 wallets vote
  (`TRACK_CONSENSUS_RANK_CUTOFF`); 60 active wallets. 236 active deep wallets (ranks 41-200)
  are already captured, polled, MM-screenable — and structurally voteless
  (`load_window_votes` excludes them; migration 033/035).
- **Two solution-space lenses are already refuted in-repo** and were not re-proposed:
  early-exit capital recycling (CLV-exit overlay: −1.0 to −1.6% vs hold, CONSOLIDATE_IMPROVE §4)
  and resting-maker capacity (adverse-selection trap: D26, D31/G3).

## 2. The retrospective read (motivation, NOT certification)

Replicating `score_market` semantics in SQL over 9 days of `trader_fills` (tracked-active
wallets, BUY-side, two-sided-MM drop, ≥3 net backers ≤1 opposer, price_std ≤ 0.10, band
0.65-0.98, entry = mean sharp fill + 1¢ haircut, ledger fee 2%):

| cohort | resolved | events | days | avg px | win rate | edge/share (post-haircut) | ledger-style ROI |
|---|---:|---:|---:|---:|---:|---:|---:|
| ELIGIBLE-pool fires | 21 | 18 | 9 | 0.786 | 0.810 | +1.3¢ | −1.1% |
| **WIDE-only fires** | **209** | **131** | **9** | 0.846 | **0.928** | **+7.2¢** | **+7.1%** |

- Wide-only daily ROI positive **8/9 days** (mean ≈ +11.5%, sd ≈ 13.4%); the day split and
  sport split both hold: tennis 28 ev +6.9%, MLB 8-for-8, esports (cs2/dota/lol) 8-for-8,
  NBA 4-for-4, other 17 ev +17.8%; soccer is the thin cell (+2.1% at 0.872 avg px).
- Post-cliff days (07-07/07-08): wide 40 and 17 resolved fires vs eligible 4 and 1.
- ~46 of the 209 overlap what live `favorite` actually fired (day-bucket reconstruction
  under-fires both cohorts vs the live 48h rolling window) → honest incremental supply
  ≈ **160+ resolved signals / 9 days ≈ 3-8× the champion's rate**, precisely when the
  champion's own supply collapses.

Known biases, stated: entry is the sharps' fill price + 1¢ (not our decision-time ask — the
measured real follower tax is ~1.0-1.3¢, `real_tax.json`, so the haircut is in range but not
exact); resolved-only; day-bucketed windows; not event-day-clustered. This read RANKS the
candidate; the standing gate judges it forward.

## 3. Candidates considered (T/A/V/P), ranking

**K1 — Wide-pool consensus (`favorite_wide`) — SELECTED.**
Mechanism: identical to champion (≥3 distinct one-sided backers, ≤1 opposer, price coherence
≤ 0.10, band 0.65-0.98, two-sided-MM drop, 48h window) on the widened sensor array
(eligible ∪ tracked deep non-bot, ~60 → ~296 active voters). Named loser: the same soft money
the champion eats — retail favorite-longshot bias and late herding on favorites — harvested on
the ~85% of sharp-consensus events the top-40 array never sees. Why the cutoff is safe to
widen: leaderboard rank is a past-PnL magnitude ordering, and past-PnL carries no skill signal
(D30, 5 refutations) — the cutoff throttles supply without protecting edge; the edge lives in
the consensus MECHANISM (independent one-sided agreement), which is unchanged.
- T: fires ~20 → 60-85/day tournament, ~15-25/day post-cliff (vs champion 3-5); turnover-multiple
  1.14× → est. 2.5-3.5× (resolution speed supports ~8.8×; supply was the binder).
- A: unchanged ($100 flat/signal; per-event capacity same question as champion).
- V: daily Sharpe est. ~0.8-0.9 vs 0.56-0.62 (8/9 positive days; ~4× independent events/day).
- P: non-soccer share of wide supply large (tennis/MLB/esports/NBA all positive in the read);
  survives the soccer/tennis tournament expiry by construction of the wider array.
- Eligible-N/day ≈ 15-25 → 30-event gate floor in ~2 days; ≥5 day-clusters in 5 days;
  within-category + selection-null judgment feasible in ~2-3 weeks.
- Feasibility: shipped in this pass, ~zero new infrastructure (deep votes were already captured).

**K2 — Live-fill fast consensus (latency).** Wire `LIVE_FILLS`/`LIVE_FILLS_TO_CONSENSUS`
(migration 040) so votes arrive in seconds instead of poll-lag minutes; cuts the ~1-1.5pt
follower tax. Real but small absolute $: same supply, +~1pt ROI-turn; P4 is deliberately gated
on a positive latency-curve verdict that hasn't accrued. **Rank 2 — stackable later; not taken.**

**K3 — Early-exit capital recycling.** REFUTED in-repo before proposal (CLV-exit overlay
lowers returns −1.0 to −1.6% vs hold). Dead.

**K4 — Soft-cell blind-favorite harvester.** Softness map's own verdicts kill it: soft ≠
bankable (K2 rule, D24); tested soft cells have realizable-ROI-LB < 0 without consensus skill.
Dead on the repo's own measurements.

**K5 — Correlated-leg sizing re-read under 3× supply.** D21's "no per-game cap improves CVaR"
was measured at FIXED supply (caps shed +EV volume with nothing to refill). At 3× independent
supply the trade-off changes — re-run `corr_risk_engine` once `favorite_wide` accrues ~2 weeks.
Not a strategy; queued as the natural follow-up instrument.

Ranking by realized-daily-$ = turnover × edge × persistence × feasibility: **K1 dominates**
— it multiplies the binding factor (supply) while holding the proven mechanism constant, lands
exactly when the champion's supply collapses, and costs no new infrastructure. K2 adds ~1pt of
edge on unchanged supply; K3/K4 are dead; K5 is an instrument.

## 4. What shipped (one code pass, additive, champion path byte-identical)

- `common/src/storage/consensus.rs` — `load_wide_window_votes()`: eligible ∪ tracked deep
  non-bot (`trader_type <> 'bot'` — the router's echo/copy-bot screen). Superset of the live
  book by construction. + `wide_window_pool_membership` integration test (passed against a
  migrated throwaway Postgres: eligible/excluded/wide splits verified end-to-end).
- `copy-trading-bot/src/scanner/consensus.rs` — `ConsensusParams.max_best_backer_rank`
  (anchor gate, fail-closed on unranked) + `wide_arms()`: `favorite_wide` (champion params,
  wide book), `favorite_wide_anchored` (≥1 top-40 co-signer — separates "deep confirms" from
  "deep alone"), `_blind_wide` (capture-all baseline on the SAME wide book so
  surplus-over-blind and `selection_null.py` get a pool-matched population). All
  `alerting: false`. + 2 unit tests.
- `copy-trading-bot/src/cycles/consensus_cycle.rs` — flag-gated wide pass AFTER the eligible
  portfolio is scored+enriched: loads wide window every Nth cycle (`CONSENSUS_WIDE_EVERY`,
  default 5 — the wide read is ~2.3× the eligible read; stride keeps DB load flat), builds
  books, scores ONLY wide arms, merges atoms fill-only (champion rows keep exact atoms; a wide
  signal on an overlapping pair stores subset atoms — replays under-fire, never over-fire).
  Errors degrade to a skipped pass, never a failed cycle.
- `copy-trading-bot/src/cycles/housekeeping.rs` — ledger scope predicate extracted +
  `_blind` PREFIX exclusion (so `_blind_wide` can never leak into the paper ledger even with
  an empty `LEDGER_STRATEGIES`). + unit test.
- `copy-trading-bot/src/scanner/enrich/mod.rs` — `favorite_wide`/`favorite_wide_anchored`
  added to the EXPERIMENTAL Bonferroni family (never tightens core's bar).
- `copy-trading-bot/src/config.rs` + `docker-compose.consensus.yml` — `CONSENSUS_WIDE_ARMS`
  (default false), `CONSENSUS_WIDE_EVERY` (default 5).

Gate: fmt-clean on touched code (pre-existing drift at 2 untouched sites fails `--check` on
pristine main too), clippy 0 warnings, `cargo test --workspace` 291 passed / 0 failed, wide
integration test green on live Postgres.

Downstream is untouched and automatic: signals upsert → decision-time `entry_ask` capture →
resolution grading → paper ledger (`LEDGER_STRATEGIES`) → honest scoreboard → standing gate
(`promotion.rs` LB > 3% at ≥30 events + `selection_null.py` p ≤ 0.01 + regime persistence),
promotion to alerting stays a human call.

## 5. Ops to arm it (Tue's flip, not done here)

```
# .env.consensus
CONSENSUS_WIDE_ARMS=true
LEDGER_STRATEGIES=favorite,elite_fresh_fav,favorite_wide,favorite_wide_anchored
DENSE_STRATEGIES=strict,favorite,elite_fresh_fav,proven_router,favorite_wide
# then: docker compose -f docker-compose.consensus.yml up -d --force-recreate copy-trading-bot
```
(Note: live ledger currently writes ALL non-`_blind` strategies — the running container isn't
seeing `LEDGER_STRATEGIES`; env delivery needs the usual .env + compose-block double-check,
see reference-polymarket-deploy-mechanism.)

## 6. Honest status & what would kill it

- **Nothing is certified by this run.** The retrospective is motivation with stated biases;
  the arms' record starts at flip. The gate needs ≥30 events (≈2 days at measured supply),
  ≥5 day-clusters, LB > 3% after the selection-null — and the within-category baseline rule
  (verify A6) applies to any cell claim.
- **Echo/copy-bot risk is the real failure mode:** deep wallets that mirror top-40 fills could
  turn 1 sharp into 3 "backers". Structural mitigations shipped (labeled-bot exclusion,
  two-sided-MM drop, the anchored variant isolating confirmation-vs-new); the decisive test is
  `favorite_wide` vs `favorite_wide_anchored` vs champion on the SAME forward days.
- **If wide-only edge collapses at our realizable entry** (follower tax on deep-wallet
  detection larger than the 1¢ modeled), the decision-time `entry_ask` capture will show it
  directly in the honest ledger. That is the point of shadow-first.
