# DECISIONS — Optimal Congregation Engine run (2026-06-30)

Non-obvious choices and their "why", so a future run resumes with full context.
Branch `feat/congregation-engine` (worktree off `feat/consensus-engine`).

---

## D1 — The as-of time axis is the slug-parsed EVENT DATE, not `resolved_at` or `ts`

**Context.** Charter H2 requires leak-free identification via `trader_slice_scores_asof(cut)`
with `resolved_at < cut`. The blueprint (Item 6) names `trader_fills.resolved_at` as the
cut key.

**Reality found (read-only SQL, this DB).**
- `resolved_at` for **all** 134,099 resolved fills falls in a 2-day window
  (130,280 in 2026-06 + 3,856 in 2026-07). It is a **bulk-backfill / ingest** stamp,
  not true market-resolution time. A `resolved_at < cut` split for any cut before the
  backfill puts *every* row in the test set → the harness is vacuous.
- `ts` (fill time) is *also* mostly a crawl stamp: **119,579 of ~134k resolved buys
  share `ts::date = 2026-06-30`**; the "4-year archive" is a few hundred stray old rows.
- `event_slug` **does** carry the true event date (`fifwc-fra-swe-2026-06-30`,
  `nba-por-phi-2026-03-15`): 125,134 / 129,242 rows parse a `YYYY-MM-DD`. This is the
  only honest economic time axis on the archive.

**Decision.** For the **retrospective pre-flight/research** on this archive, cut on the
slug-parsed event date (`scripts/asof_slice_scores.sql`). For the **in-engine forward
instrument** (`trader_slice_scores_asof`, Phase 0.5) keep `resolved_at < cut` as the
blueprint specifies — that is correct once `resolved_at` is populated in real time on
forward data; it is only degenerate on the backfilled historical archive. Both facts
are documented at the call sites. This is a reversible, evidence-backed reality
correction (charter H9 posture), not a mission change.

**Why it matters.** Using `resolved_at < cut` literally on this archive would have
manufactured a "clean" but meaningless harness. The finding below depends on getting the
time axis right.

---

## D2 — §0.5 pre-flight verdict: the diversification premise is DEAD ON THIS DATA → stop before the arms

**The binding experiment (reproducible: `scripts/asof_preflight.py`).**
As-of certification faithfully replicating `trader_slice_scores` + `surplus_bounds`
(per-wallet Bonferroni denominator = slices-with-data; `z = probit(1−0.05/nComp)`;
`lo = surplus − z·se`; Trusted@capture ⇔ `N≥30 ∧ lo > 3%`).

| test | result |
|---|---|
| per-sport specialists Trusted@capture, cut 2026-06-29 (train side) | **0** |
| per-sport specialists Trusted@capture, cut 2026-06-30 (train side) | **0** |
| **full-window, in-sample** (no walk-forward, most generous) Trusted@capture per-sport cells | **0** |
| wallet-sport cells with ≥30 events on **both** sides of any cut | **0** (only cut 06-30 even has 3 cells with ≥30 both sides; disjoint cut 06-29 has 0) |

**Why zero — legible, not a bug (exactly the Forge's predicted binding constraints):**
1. **Sample floor.** The wallets with a visible point-estimate edge are *below* 30 events
   (soccer +0.274 @ N=28, +0.197 @ N=20) — small N, not evidence. World Cup is a short
   tournament; a wallet bets ~20–28 distinct matches.
2. **Capture margin + variance.** The wallets that *do* clear N≥30 have either tiny
   surplus (tennis ~+0.04 @ N≈108, below the 3% margin once bounded) or high variance
   (soccer +0.108 @ N=58 → lo −0.034). None clears `lo > 3%`.
3. **Slate collapse (H4).** The whole record is essentially **two adjacent days of one
   tournament** (World Cup soccer, 2026-06-29/30) plus Grand Slam tennis bursts (166
   tennis events over just 9 event-days). Even the ≥30-event cells are correlated
   within-tournament markets → effective independent-N ≪ 30, and any two "specialists"
   are co-active on the same slate. Diversification across independent certified edges —
   the entire north star — is impossible when the data is one tournament weekend.

**Decision (binding, charter §0.5).** `<2` capturable, persistent per-sport specialists
(in fact **0**, even in-sample) **and** maximal slate collapse ⇒ premise DEAD ON THIS
DATA. Per the decision rule: **do NOT build Phases 2/5** (the specialist/contrarian/
edge-pool/coalition arms). Deliver the as-of harness, the honest-null finding, and the
accrual curve. This is *also* the leak-free answer to the §7 escalation trigger
("does per-context certification predict forward edge out-of-sample" — unanswerable
here because no wallet certifies in-sample and there is no second disjoint cut). Per the
charter, **a dead premise correctly established in one hour is a successful run.**

---

## D3 — What DID ship, and why (not nothing, not the arms)

The DEAD branch says deliver "the as-of harness". Shipped, each non-regressive and
gate-green:
- **Phase 0 — capture margin at the strategy gate.** `board.rs` render gates arms at
  `slippage_pct + fee_pct = 3%` instead of `margin 0`. Pure rigor; raises the bar for
  every existing arm; touches neither `strict` alerting nor `trader_trust`. This is the
  exact bar the pre-flight certifies against, so the live board and the report now agree.
- **Phase 0.5 — `trader_slice_scores_asof(cut)`** — the leak-free forward instrument
  (blueprint Item 6), `resolved_at < cut` in both the slice surplus and the band-blind,
  recency slices dropped. Plus the reproducible pre-flight harness
  (`scripts/asof_slice_scores.sql` + `scripts/asof_preflight.py`) that produced D2.

**Not shipped (deliberately):** Phase 1 `SliceTrustMap` (exists only to feed arms),
Phases 2–5 arms. No arm can be honestly certified when 0 specialists exist. Building them
silent+OFF would add hypotheses to the family Bonferroni for zero information. The clean
extension point remains: when accrual (D4) yields ≥2 persistent cross-sport specialists,
Phase 1 + Arm A/D are the next run's first move, and this harness is their gate.

---

## D4 — Accrual: when could ≥2 persistent specialists emerge?

Dated independent **event-days** per sport on the whole archive: soccer 21, tennis 9,
mlb 12, everything else ≤4; crypto has 237 events but **zero** parseable date (no time
axis — cannot be walk-forward split at all). A wallet cannot reach 30 *independent*
soccer event-days when the fleet has only 21 in total. Event accrual is bursty and
tournament-gated (World Cup, Grand Slams), and tournaments are seasonal with gaps.

**Honest ETA.** Two conditions must *both* hold, and the second is the real wall:
1. *Coverage:* ~30 independent event-days in a single sport per wallet — realistically
   **months** of continuous major-tournament slates (and the World Cup ends imminently,
   after which soccer density collapses).
2. *Edge:* a surplus that clears `lo > 3%`. The full-window in-sample test shows this is
   **absent for every wallet today**, consistent with the standing "consensus count is
   noise / the market is ~efficient" prior. More data mainly tightens bounds around
   point estimates that mostly sit below the capture margin — it does not create an edge
   that is not there. So the defensible ETA to a bettable per-sport specialist is
   **not estimable as a near-term date**; the correct posture is to keep accruing the
   forward record and re-run this one-hour pre-flight after each major tournament block,
   promoting nothing until ≥2 cross-sport cells clear `lo>3%` on ≥2 disjoint cuts.

---

# DECISIONS — Fable improvement run (2026-07-02)

Branch `fable/improve-run-20260702` (worktree off `main` ae0db80, tag `pre-fable-run-20260701`).

## D5 — CAPTURE_ENTRY_ASK turned ON (ops, not git-tracked)

`.env.consensus` gained `CAPTURE_ENTRY_ASK=true` (2026-07-02) and the stack was recreated.
The flag-gated real-ask capture shipped in 8e59b68 but was never enabled — coverage was 0%,
and every day off is unrecoverable realizability data (asks cannot be backfilled). Verified
live: 40 rows captured within the first cycle (the per-cycle cap). Revert = delete the env
line + `docker compose … up -d`. Backup of the pre-run env:
`backups/pre-fable-run-20260701-untracked/.env.consensus.bak`.

## D6 — The gate judges the AT-FIRE entry, not the drifted upsert state

**Reality found.** `consensus_signals.mean_price` is overwritten on every 2-min upsert
(consensus.rs upsert `DO UPDATE SET mean_price = EXCLUDED.mean_price`), so the scoreboard's
`a = won − mean_price` embedded post-fire information: avg drift +1.2¢ on strict, ~29% of rows
moving >2¢. The set-once at-fire columns (`initial_mean_price`, insert-only VALUES) exist
precisely for this and have 100% coverage.

**Decision.** `consensus_scoreboard_by_strategy` now computes `a`, the band, and `capture_lag`
from `COALESCE(initial_mean_price, mean_price)` — for strategy rows AND the `_blind` baseline.
The strategy spec (REFINED-STRATEGY rule 4) is "act at fire"; judging a drifted entry both
leaks and empirically UNDERSTATES the at-fire edge. Safe-swap proof: `scripts/scoreboard_parity.py`
(K1: per-strategy N identical old-vs-new; only surplus values move). Effect on live data:
favorite LB @3% margin +0.21% → **+3.33%** (flips promotable), elite_fresh_fav +4.01% → +4.80%.
Deliberately KEPT on the drifted mean: `honest_pnl`'s reference-only `sharp_adv` column — the
sharps' realized average fill is legitimately the final mean; it never judges promotion.
Regression test: `scoreboard_at_fire_it` (#[ignore], throwaway-PG verified).

## D7 — Pre-registered promotion rule: gate LB ∧ selection-null ∧ regime persistence

The market_resid episode showed the gate's one blind spot: surplus-vs-population-baseline can
false-promote a strategy whose *composition* (not selection skill) differs from the blind pool.
Standing defense shipped as `scripts/selection_null.py`: (band × UTC-day)-matched random
selections from `_blind`, scored with the exact scoreboard statistic, 2000 seeded draws;
`--calibrate` self-test must PASS before any reading is trusted (K2: pseudo-null strategies
from `_blind` must give ~uniform p; measured 6% below 0.05, 76% in [0.1,0.9] → PASS).

**The rule (binding on any future promotion/alerting/real-money call):** promotion-ELIGIBLE ⇔
(a) belief-blind gate lower bound > capture margin (3%) at N≥30 (unchanged promotion.rs math),
(b) selection-null p_emp ≤ 0.01 at ≥1000 draws, AND (c) regime-matched surplus > 0 in ≥2
disjoint sport-regimes. Eligibility is necessary, not sufficient — promotion stays a human call.
Why p≤0.01: with ~11-13 strategies tested each run, 0.01 keeps the family-wise false-positive
odds ~10% even before the informal Bonferroni note the script prints; and both live candidates
(elite_fresh_fav, favorite) pass at p=0.0000 — the bar costs nothing real.

First full reading (2026-07-02, 11,819 resolved signals / 3,113 blind events, 4 days):
elite_fresh_fav p=0.0000 (z 2.77) and favorite p=0.0000 (z 3.82) are SELECTION-REAL and pass
regimes (elite_fresh_fav: soccer +6.0% N=20, tennis +8.3% N=17; favorite: positive in 4/4);
strict/count/whales/sports_only/fresh2h/elite_gated/longshot indeterminate (p 0.019-0.030);
loose/tight_cluster NULL. Still NOT promoted: elite_fresh_fav N=38 < 50 pilot floor; regimes
thin; one 4-day window ≠ two disjoint accrual blocks. Re-run after Wimbledon completes.

## D8 — Deliberately NOT done (and why)

- **No promotion of anything to alerting or money** — see D7; floors unmet. The run's product is
  honest instruments, not eager promotion.
- **Sport-regime segments NOT added to the Rust honest panel; flat-shares NOT added to
  `ledger_stats`** — two parallel sessions (feat/entry-ask-decision, feat/deep-leaderboard) have
  uncommitted edits in exactly those regions (`honest_pnl_segments`, `render_honest`, board.rs);
  the coordination rule (smallest additive change to shared files; never edit the same regions in
  parallel) wins. Both readouts ship in `selection_null.py` output instead; the Rust surfacing is
  the pre-registered follow-up once those branches merge. ⚠ Note for the integrator: both
  parallel sessions minted migration 032 (`032_entry_ask_decision_time.sql` committed on
  feat/entry-ask-decision; `032_consensus_eligible.sql` untracked in wt/deep-lb) — they will
  conflict with each other; renumber at merge.
- **`longshot`'s selection signal (p=0.03, +5.1% per-share) parked** — real-ish selection but
  cost-dead per standing findings (flat-shares P&L −$227 after haircut+fee even before spread
  reality); recorded as an instrument observation, no arm, no Bonferroni slot.
- **market_resid untouched, stays OFF** (refuted 2026-07-01). **No relational-consensus build**
  (data-starved). **No crypto arm** — consensus strategies never fire there (sports-concentrated
  sharps); crypto mass serves as baseline only.

## D9 — Independent audit findings folded in (gate-wiring + resolution-path audits, 2026-07-02)

Two read-only audit passes ran alongside this run. What they found, and what was done:

- **Honest pilot GO gate has NO blind baseline** (honest.rs:105 judges `honest_roi` vs own entry
  only) — favorite-loading is structurally +ROI and *regime-persistent*, so the day-regime guard
  cannot catch it. This is the market_resid class with the baseline removed, on the designated
  real-money gate. Mitigated NOW by D7 (rule (a) requires the blind-baselined scoreboard LB, so
  no GO can be acted on without the blind test passing); the code-level fix (blind-baselined
  surplus requirement inside `pilot_verdict`) is DEFERRED — honest.rs plumbing crosses board.rs,
  an active parallel-session edit region.
- **Telegram `/consensus` gated at margin 0 while the web board gates at capture margin (3%)** —
  same arm, looser ✅ on Telegram. **FIXED this run** (commands.rs: margin = slippage+fee from
  config; single-file change, no signature change — live.rs already passed cfg).
- **Bonferroni denominator = rows-present per family** → a lone early experimental arm gets
  fam_n=1 (no correction); and repeated board looks are uncorrected (optional stopping).
  DEFERRED + documented: denominator floor = registered-arm count, and a promotion checklist rule
  "read the gate at pre-registered evaluation points only (N=30, then every +15)" — the latter is
  already H5 house practice; enforcing it in code is a later change.
- **Trader-trust corrects within-wallet slices but not across the ~hundreds-wallet fleet** —
  best-of-N artifact risk feeding trusted_only/trust_weighted arms. DEFERRED: add fleet-size
  correction (or FDR) to `trust_verdict`; those arms are experimental-family and OFF by default,
  so exposure today is display-level.
- **Resolution path** (independent audit): the >30h unresolved backlog is EXPECTED (measured:
  1,550 of 1,840 are `_blind` on long-dated open markets; 0 empty-condition rows). Three latent
  defects documented for follow-up, none touched this run (housekeeping.rs is a parallel-session
  edit region): (1) `fetch_clob_market` has no HTTP-status check → 404s parse-fail → silent
  retry-forever; no dead-letter/expiry for never-closing markets (unbounded tail growth);
  (2) VOID markets grade as LOSSES in consensus but are skipped in trader_fills — phantom-loss
  bias, direction CONSERVATIVE (understates edge; cannot false-promote); (3) `resolved_at=NOW()`
  is processing time, not close time (conservative for leakage; inflates avg_hours_to_resolve).

## D10 — Winner alerting: WATCH-tier pushes + cross-strategy dedup (why flags alone were useless)

Investigation before code: `favorite` had only 6 STRONG+ signals and ALL were already alerted by
`strict`; the winners' edge lives at net=3 = WATCH tier, which the alert path unconditionally
dropped. So "flip alerting=true" would have changed nothing. Shipped instead (all default-inert):
`CONSENSUS_ALERT_STRATEGIES` (override the alerting set), `CONSENSUS_ALERT_WATCH_FOR` (strategies
whose WATCH fires push, priority-3 ntfy), `CONSENSUS_ALERT_CROSS_DEDUP_MINS` (one push per
(market,outcome) across strategies; same-strategy re-alerts exempt ⇒ strict byte-identical; fail-
open on DB errors so an outage can never silence alerts). Intended ops values (D12):
`CONSENSUS_ALERT_STRATEGIES=strict,favorite,elite_fresh_fav`,
`CONSENSUS_ALERT_WATCH_FOR=favorite,elite_fresh_fav`. Expected volume ≈ favorite∪elite events/day
≈ 25-30 pushes/day during peak slates — the strategy's true trade stream; tune via env if noisy.

## D11 — Dense capture ON + the first speed budget (and what it did NOT measure)

`signal_price_trajectory` (migration 034) + a flag-gated 45s dense capture loop for fresh
actionable signals (bounded: 15-min window, 40 pairs/tick, dedup to earliest anchor). The decay
instrument (`scripts/decay_analysis.py`, self-testing: injected decay recovered within CI,
no-decay fixture flat) produced the first confound-controlled reading on 5-min data:
**no material decay inside 30 min** for favorite (+8.2% fire edge, budget ≈54m) and
elite_fresh_fav (flat to 60m within CI) → **manual execution is fine**; the structural follower
tax (sharps' fill → our first mid; speed cannot recover it) is +2.1¢ / +1.3¢ / +0.8¢ for
favorite / elite_fresh_fav / strict. NOT measured yet: τ < 10 min (change-only 5-min snapshots
echo the p0 anchor → exact-zero artifact, flagged in the report). Dense capture exists precisely
to fill that; re-run after a few days of DENSE_CAPTURE=true. Deferred deliberately (no-bloat):
the board decay panel + hourly launchd re-run — they earn their place when the sub-10-min buckets
become publishable; until then the instrument runs at gate-reads.

## D12 — Ops changes (2026-07-02, not git-tracked; .env.consensus)

Appended: `CONSENSUS_ALERT_STRATEGIES=strict,favorite,elite_fresh_fav`,
`CONSENSUS_ALERT_WATCH_FOR=favorite,elite_fresh_fav`, `DENSE_CAPTURE=true`. Deploy via
`scripts/consensus-autoupdate.sh` (the sanctioned path). Revert = delete the lines + re-run the
updater. Backup: backups/pre-fable-run-20260701-untracked/.env.consensus.bak (pre-run state).
