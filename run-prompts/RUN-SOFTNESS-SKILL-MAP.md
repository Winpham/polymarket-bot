# Long Autonomous Run — SOFTNESS × SKILL MAP: steer the edge to the soft pockets (sports and beyond)

Paste this whole file as the task for a fresh long-running session. **Self-contained.**
Work in `~/polymarket-bot` (Rust workspace; deploy branch `main`, auto-deploys ~5 min after merges).
Companion ground truth already on `main`: `DECISIONS.md` (D1–D17), `REFINED-STRATEGY.md`,
`DATA-MODEL.md`, and the instrument kit in `scripts/` (see "What already exists").

---

## 0. The one-sentence mission

Our consensus-favorite edge is real but lives in the **soft pockets** of the market, not the popular
ones — the World Cup is one of our *softest* venues (casual/patriotic money floods thin sub-markets),
while heavily-modeled cells (MLB totals, tennis handicaps) are *sharp* and lose. **Build the
`category × market-type × band` SOFTNESS×SKILL MAP** that (a) finds where casual money pools, across
sports AND non-sports (politics/elections, esports, econ), (b) measures whether our consensus adds
real *skill* on top of that softness, and (c) emits a SILENT, gated, forward-measured steering overlay
that concentrates on the soft-AND-skilled cells and DODGES the sharp ones — **so the same generic
strategy earns more by fishing where the fish are.** No new signal is invented; we aim the existing
edge. Paper-only, gate-judged, cost-zero.

## The distinction this run exists to make precise (fix BEFORE computing)

- **SOFTNESS** = the blind-favorite edge in a cell = event-clustered `mean(won − at-fire entry)` over
  the `_blind` pool's favorites (entry ≥ 0.6). Large + ⇒ favorites underpriced ⇒ casual-flooded / soft
  market. ≤ 0 ⇒ sharp / professionally-modeled market. This is the OPPORTUNITY SIZE, knowable with far
  less data than a P&L verdict — the reason the map can steer FORWARD.
- **SKILL** = the consensus surplus = event-clustered `mean((won − entry) − blind_edge[regime,band])`
  for the strategy — what the consensus ADDS beyond the blind favorite at the same price. This is the
  EDGE; it must clear the capture-cost margin to be bankable.
- **REALIZABLE ROI** = the bankable number at MEASURED costs (0.5¢ haircut + 2% fee, honest_pnl).
- **Softness is necessary, not sufficient.** A soft cell (+3% underpricing) can still be −EV after the
  ~3% capture cost; only SKILL that clears costs is an edge. And a sharp cell (softness < 0) bleeds on
  the base rate no matter who we follow — DODGE it. The map's job is to separate these three numbers
  per cell and never conflate softness with profit.

## Ground truth you must NOT relitigate (re-verify, don't re-argue)

From the truth audit (DECISIONS D16, reports/entries/13) and the sport tracker (entry 15):
- The `favorite` edge is REAL and attack-hardened: at match-level clustering +12.5% surplus over ~70
  matches, selection-null p=0.0000 (z 4.35), grading 0/305-mismatch vs Gamma, mirror symmetric, placebo
  flat, both time-halves positive, fills real, not latency-fragile, 97.6% capture.
- **It is NOT World-Cup-dependent — WC soccer is favorite's WEAKEST regime (+5.3%).** Non-WC is
  stronger (+15.2%), carried by tennis (+11.8%). Tennis is an *efficient* market yet shows real skill —
  the best transfer signal.
- **The certification wall is ACCRUAL, not the edge (D16-a).** The scoreboard SE now deflates to
  distinct event-DAYS (Moulton, commit 5b83d33; the effective-N reconciliation landed entry 14 / D17);
  4 correlated summer days cannot certify at any clustering. Softness-based steering is valuable
  precisely because softness needs *less* data than a skill verdict.
- **elite_fresh_fav is materially weaker** (N=27 < 30 floor at match level; +2.6% composition premium);
  treat `favorite` as primary; it has no MLB/other regime → goes near-silent post-Wimbledon.
- Strategies are GENERIC, sport-blind price/quality filters (`favorite` = price 0.65–0.98;
  `elite_fresh_fav` = elite + fresh + 0.80–0.97) — there is NO World-Cup tuning to undo. Trader
  selection is the GLOBAL leaderboard (top-N by PnL, category-blind), auto-rotating to whoever's hot.
- Measured softness by cell (blind-fav edge, entry≥0.6): soccer/WC **props +3.3%** (softest), other
  props +3.2%, tennis moneyline +2.7%, other moneyline +1.5%, crypto deriv +1.3%, soccer moneyline
  +1.2%, **MLB props −5.1%**, **tennis handicaps −9.0%** (sharpest). Softness is a *cell* (sport ×
  market-type), not a sport. Crypto never fires consensus (sharps never agree one-sided) — baseline only.

## What already exists (reuse, don't reinvent — the [[extend-dont-rebuild]] rule)

Self-testing Python instruments on `main` (each: mandatory self-test recovers an injected effect AND
reads flat on a null; run `--self-test`):
- `scripts/superkey.py` — `super_event(event_slug, slug)` match-level cluster key. USE for all clustering.
- `scripts/sport_edge_tracker.py` — the softness-vs-skill decomposition PER SPORT (this run generalizes
  it to category × market-type × band). Its `sport()` classifier already wires nfl/nba/cfb/cbb/nhl.
- `scripts/selection_null.py` — the (band×day)-matched selection null; `--calibrate` self-test. Reuse
  its machinery for per-cell selection nulls (CLI byte-identical, DECISIONS D7).
- `scripts/slice_study.py` — the pre-registered PRIORITIZE/NEUTRAL/DODGE slice engine with BH-FDR
  q=0.10, matched (regime×band) baseline, LODO, K2 drift-stability, self-test. The softness×skill map is
  its sibling keyed on SOFTNESS (knowable before 30 resolved events), not realized P&L.
- `scripts/map_state.py` + `scripts/map_checkpoint.py` — the append-only versioned map STATE MACHINE
  (ENTER on whole record / EXIT on recent window; STALE/THRASH guards; entry 11 / D14). If a steering
  overlay is emitted, express it as a new map dimension here, do NOT build a parallel state store.
- Scoreboard math (`common/src/storage/consensus.rs::consensus_scoreboard_by_strategy`) and the gate
  (`copy-trading-bot/src/scanner/promotion.rs`: `surplus_bounds`/`promotion_verdict`, probit, day-N SE).
  Mirror them EXACTLY when you compute surplus/LB (see rekey_headline.py entry 13 for a faithful mirror).

DB access: `docker exec -i polymarket-bot-postgres-1 psql -U bot -d polymarket --csv -q`. At-fire entry
= `COALESCE(initial_mean_price, mean_price)` (D6). Gamma second-source for grading:
`https://gamma-api.polymarket.com/markets?closed=true&condition_ids=<cid>` (needs a non-default
User-Agent header, e.g. `curl/8.4`; batch via repeated `condition_ids=` params).

## Non-negotiable guardrails

1. **Isolated git worktree off fresh `main`, new branch, tag first.** Other sessions run in parallel and
   `main` MOVES UNDER YOU (it moved 3× during the last two runs) — `git worktree list`, take a
   non-overlapping slice, smallest additive change to any shared file (`DECISIONS.md`,
   `REFINED-STRATEGY.md` are high-contention; append at the tail, renumber D/entry if they collide).
   **Applied migrations are IMMUTABLE** (sqlx checksum crash-loop). This run needs NO migration and NO
   behavior change: analysis scripts + docs + at most ONE silent, gated overlay dimension.
2. **Gate EVERY commit.** Python: `py_compile` + the mandatory self-test (ships only with a PASSING
   self-test that recovers an injected effect AND reads flat on a null). If you touch Rust:
   `cargo fmt --check --all && RUSTFLAGS="--cfg tokio_unstable -Dwarnings" cargo clippy --workspace
   --all-targets --locked && RUSTFLAGS="--cfg tokio_unstable" cargo test --workspace --locked`.
   **The `--cfg tokio_unstable` flag is REQUIRED** (`.cargo/config.toml` sets it; a bare
   `RUSTFLAGS="-Dwarnings"` overrides it and the build fails on a gated tokio_metrics field — a false
   red). **Re-run the FULL gate on post-merge `main`** before the ~5-min auto-deployer ships it.
3. **Paper-only.** No env flips on the live bot (propose, don't apply); deploy only via
   `scripts/consensus-autoupdate.sh` (the sanctioned path; it rebuilds only when
   `common/|copy-trading-bot/|migrations/|Cargo.|Dockerfile.consensus|docker-compose.consensus.yml`
   change, `--ff-only` so it can't clobber local work, and treats docs/scripts as "no code change").
   Cost-zero: no API keys, no child claudes.
4. **Report every ugly number first.** A sharp cell that kills a hoped-for market, a soft cell whose
   skill is 0, a non-sports category that never fires — those LEAD the report. No cell dropped for being
   inconvenient. Softness is not profit; say so wherever a cell is soft but −EV after costs.

## Pre-registration (fix BEFORE computing)

- **Cell family:** `category × market-type × band`, frozen in the report before anything is computed.
  Categories: tennis, soccer, mlb, nfl/cfb, nba/cbb, nhl, crypto, **politics/elections**, **esports**,
  **econ/other** (extend the classifier; document every prefix/regex rule + measure the collapse/misfire
  rate on a labeled sample). Market-types: moneyline/main vs derivative/prop (document the rule).
- All stats event-clustered at the **match super-key** (`superkey.super_event`), at-fire entry, matched
  (regime×band) blind baseline — never a global-blind baseline (the composition trap, D16-b/F2).
- **Floors:** no verdict from N<20 events; softness needs ≥30 blind favorites in the cell; below floor =
  INDETERMINATE (the watch-list — the whole point is to watch cells cross it).
- **Multiplicity:** BH-FDR q=0.10 across the testable-cell family for the SKILL and softness-null tests;
  report raw p's alongside. Reuse `selection_null.py`'s machinery for the per-cell selection null.
- **Kill criteria (binding):** K1 the map self-test fails (injected soft-skilled cell → PRIORITIZE,
  sharp cell → DODGE, pure-noise fixture → 0 FDR survivors) ⇒ STOP, the map is untrustworthy. K2 a
  PRIORITIZE cell's realizable-ROI lower bound ≤ 0 after measured costs ⇒ it is NOT prioritizable
  (soft ≠ bankable) — downgrade to NEUTRAL and say so. K3 the steering overlay's paired lift over base
  `favorite` is ≤ 0 on forward-only rows ⇒ the map orders nothing; report the null loudly. K4 a
  non-sports category shows softness but the consensus never fires there (like crypto) ⇒ it is an
  observation, not an arm — no Bonferroni slot.

## Phases (each gate-green + committed; report incrementally)

### Phase 0 — setup + reproduce (~30 min)
Worktree, branch, tag. Reproduce `sport_edge_tracker.py` and the softness-by-cell numbers on the live
DB within noise. Print the full `category × market-type × band` cell census: rows, distinct matches,
distinct days, resolved count — so every later floor call is legible.

### Phase 1 — the category taxonomy that reaches beyond sports (`scripts/market_taxonomy.py`, self-testing)
Extend `sport()` into a `category(slug,title)` that adds **politics/elections, esports, econ/other**
with documented rules; self-test on a hand-labeled sample (recover known labels, flag misfires). Then
answer the coverage question honestly per category: volume, resolved count, events/day, and **does the
consensus even fire there** (favorite/elite signal count) — many non-sports cells will be data-starved
or never-fire (K4). Separately identify the **political leaderboard traders** (which tracked wallets are
active in political markets) — the "who to follow for elections" seed for later per-category trust.

### Phase 2 — the SOFTNESS map (`scripts/softness_map.py`, self-testing)
Per cell: softness = event-clustered blind-favorite edge (entry≥0.6), at-fire, with a bootstrap CI and a
null (is softness distinguishable from 0?). Rank cells softest→sharpest. This is the "where casual money
pools" map and it is knowable with modest data — the forward-steering proxy. Self-test: injected
underpriced-favorite cell → high softness; fair-priced cell → ~0; overpriced (sharp) cell → negative.

### Phase 3 — the SKILL map (extend `softness_map.py` or a sibling, self-testing)
Per cell, for `favorite` (and `elite_fresh_fav` where N allows): consensus SKILL = surplus over the
regime×band blind baseline, event-clustered at match level; per-cell selection-null p (reuse
`selection_null.py`); REALIZABLE ROI at measured costs (0.5¢+2%) with its lower bound; N-status. BH-FDR
across the cell family. INDETERMINATE below floor. This is the EDGE map — softness says where it's
*possible*, skill says where it's *real*.

### Phase 4 — the combined PRIORITIZE / NEUTRAL / DODGE steering map (self-testing)
The 2×2 logic, pre-registered: **PRIORITIZE** = skill clears the cost margin (realizable-ROI LB > 0,
FDR-survives) AND softness ≥ 0; **DODGE** = softness < −margin (sharp, base rate bleeds) OR skill ≤ 0;
**NEUTRAL/INDETERMINATE** otherwise. State the inheritance honestly (cells test vs blind, not vs parent
— the map is an ORDERING of forward hypotheses, not a set of certified bets). K1/K2 bind here. Emit the
map as a new dimension in the existing `map_state.py` versioned store (do NOT build a parallel store),
so the adaptive state machine (ENTER-on-record / EXIT-on-recent, STALE/THRASH guards) governs it.

### Phase 5 — the SILENT forward steering overlay
A VIRTUAL overlay strategy that concentrates `favorite` on PRIORITIZE cells, judged FORWARD-ONLY on
paired lift vs base `favorite` (excluded-pick P&L accounted), ONE hypothesis slot, no new Rust arm
unless it EARNS one (K3 — earned, not built), no alert change, no env flip, NO real money. Emit a
watch-list of cells (esp. non-sports + fall sports) approaching the N floor, with the exact re-read
trigger (per cell: N crossing 20 / +7 days / category coming into season).

### Phase 6 — synthesis + merge
`reports/entries/NN-softness-skill-map.md` (per-cell PRIORITIZE/DODGE tables, the non-sports coverage
verdict, the ugly cells first) + a DECISIONS entry + update `REFINED-STRATEGY.md` only where a cell
verdict binds (e.g. "DODGE MLB/tennis derivatives"; "PRIORITIZE soccer/other props while soft";
"politics = year-round soft frontier, ramps to Nov-2026 midterms"). Merge `--no-ff`, **re-gate
post-merge `main`** with the correct RUSTFLAGS, confirm the deployer logs "no code change" and the
container is NOT recreated (behavior unchanged).

## Rejected approaches (do not do)

- **Conflating softness with profit.** Softness is opportunity size; only SKILL that clears the ~3%
  capture cost is an edge. Never PRIORITIZE a cell on softness alone (K2).
- **Manufacturing an edge in a sharp cell.** MLB/tennis derivatives at −5 to −9% softness are DODGE; no
  trader-selection tuning creates an edge where the market is efficient. Say so.
- **Confirmation-shopping** — each cell verdict runs once as pre-registered; re-tuning a threshold
  requires re-registration in the report with the original result shown alongside.
- **Building a Rust steering arm before the overlay earns it** (K3) — the virtual overlay is measured
  forward first; the arm is a later, separate run if the paired lift clears the bar.
- **Any real-money action, alerting change, or env flip.** Any migration. Any global-blind baseline
  (use regime×band — the composition trap). Any child claude or API key (cost-zero).

## Acceptance

The `category × market-type × band` cell family pre-registered and frozen; SOFTNESS, SKILL, and
realizable-ROI computed per cell (event-clustered at match level, at-fire, matched baseline, FDR-
controlled); non-sports categories (politics/elections, esports, econ) classified and their coverage
honestly reported (fires vs data-starved vs never-fire); a self-testing PRIORITIZE/NEUTRAL/DODGE map
committed and expressed in `map_state.py`; ≤1 silent forward overlay (earned, not built) with an
explicit per-cell watch-list + re-read triggers; kill criteria honored (a soft-but-−EV cell downgraded
to NEUTRAL is a valid, honest outcome); docs updated; merged `--no-ff` + post-merge re-gated green; live
behavior unchanged (deployer "no code change"). The deliverable is a map of WHERE the edge can be
harvested — across sports and beyond — with each cell's softness, skill, and bankability stated plainly.
