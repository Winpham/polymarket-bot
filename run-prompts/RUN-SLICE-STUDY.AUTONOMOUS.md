# Long Autonomous Run — Slice Study: what to PRIORITIZE, what to DODGE

Paste this whole file as the task for a fresh long-running session. **Self-contained.**
Work in `~/polymarket-bot` (Rust; deploy branch = `main`, auto-deploys ~5 min after merge).
Companion reading (house style + the ground truth you must not relitigate): `DECISIONS.md`
(D1–D12), `REFINED-STRATEGY.md`, `REPORT.md`, `run-prompts/README.md`,
`scripts/selection_null.py`, `scripts/scoreboard_parity.py`, `scripts/decay_analysis.py`.

---

## 0. The one-sentence mission

Map the ENTIRE forward record into pre-registered slices, measure each slice's
**reliability** (surplus vs matched blind, selection-null, persistence) AND its
**frequency** (qualifying events/day), combine them into an expected-daily-profit-with-
confidence ranking, and emit a binding **PRIORITIZE / NEUTRAL / DODGE** table — because the
more often a reliable edge fires the more it earns, but frequency without reliability is
just faster losses.

The motto: **a slice is a hypothesis, the family is corrected, exploration never promotes —
it nominates cells for pre-registered forward confirmation.**

---

## Ground truth you must NOT relitigate (established, evidence in DECISIONS.md/REPORT.md)

- The gate judges the **AT-FIRE entry** (`COALESCE(initial_mean_price, mean_price)`), never
  the upsert-drifted `mean_price` (D6). Every analysis in this run uses at-fire.
- **Promotion rule (D7, binding):** eligible ⇔ gate LB > 3% capture margin (N≥30 events) ∧
  selection-null p ≤ 0.01 ∧ ≥2 disjoint sport-regimes positive. This run does not change it.
- **The two certified-eligible winners:** `favorite` (+10.7% surplus, N=95, p<0.0005,
  positive every day/regime/band, realizable +9.3%/bet at measured costs) and
  `elite_fresh_fav` (+9.2%, N=39, p<0.0005, realizable +7.7%). They are the baseline any
  refinement must beat — at the bar, not by point estimate.
- **The boundary (2026-07-02 battery):** the WIDE pool "any consensus at entry ≥0.65"
  (200 events) is +4.65% surplus but **−1.4% realizable after real costs** — the strict
  quality gates (≥3 one-sided backers, ≤1 opposer, σ≤0.10, freshness) are load-bearing.
  Loosening filters to buy frequency is the known failure mode. Volume must come from more
  MARKETS, not weaker GATES.
- Blind-tail loses; consensus is fully formed at fire (never wait); flat-SHARES sizing (or
  ¼-Kelly), never flat-$; skip longshots as a strategy (their per-share selection signal is
  cost-dead); market_resid stays OFF (refuted); no edge decay inside ~30 min (manual
  execution fine); measured real haircut ≈ **0.5¢** median (use it, not the 1¢ guess);
  `resolved_at` is processing time; event-cluster by `COALESCE(event_slug, condition_id)`
  ALWAYS (the within-match leak).
- Crypto: the blind baseline is rich there but consensus strategies essentially never fire
  on it — a frequency observation to quantify, not a bug.

## Non-negotiable guardrails

1. **Reversibility.** Isolated git worktree off `main`, fresh branch; tag the pre-run state.
   Never work in the shared checkout; other Claude sessions run in parallel — check
   `git worktree list`, keep your file slice non-overlapping, smallest-possible additive
   changes to shared files, and say so when you must.
2. **Gate every commit:** `RUSTFLAGS="--cfg tokio_unstable -Dwarnings" cargo fmt --check
   --all && cargo clippy --workspace --all-targets && cargo test --workspace`; Python =
   `python3 -m py_compile` + a synthetic-fixture smoke run. **Re-run the FULL gate on main
   AFTER your merge lands** — main moves under you and the auto-deployer ships whatever is
   there (two cross-merge breaks were caught exactly this way).
3. **Applied migrations are IMMUTABLE** (even a comment edit ⇒ sqlx checksum crash-loop in
   prod; happened 2026-07-02). This run should need NO migration; if you truly need one,
   next free number only, append-only.
4. **Paper-only, additive-and-OFF, belief-blind.** No real money, no order placement, no
   alerting changes, no auto-promotion. New strategy variants (if any) are SILENT
   (`alerting: false`) and cost a Bonferroni slot — budget ≤ 2 new variants TOTAL, only if
   Phase 3 justifies them, pre-registered before enabling.
5. **Deploys only via `scripts/consensus-autoupdate.sh`** (never manual `docker compose up`)
   and **env/behavior flips on the live bot require Tue's explicit go** — propose, don't
   apply.
6. Cost-zero (Max only, no ANTHROPIC_API_KEY, no child claude spawns).

---

## Pre-registration (write this list into the report BEFORE computing anything)

**The slice dimensions (the full family — nothing added after looking):**
Within each of three populations — (P1) `favorite` picks, (P2) `elite_fresh_fav` picks,
(P3) the full fleet's strict-gated picks (`strict` variant, all bands) —

| # | Dimension | Cells |
|---|---|---|
| 1 | sport-regime | crypto / tennis / soccer / mlb / cs2 / other (event_slug prefix, the selection_null.py mapping) |
| 2 | market TYPE within sport | moneyline ("A vs B" winner) / over-under ("O/U", "Over") / exact-score / futures ("winner", "champion") / prop — derive from title+slug patterns, document the classifier, measure its coverage |
| 3 | at-fire price band | 0.65–0.80 / 0.80–0.90 / 0.90–0.97 (finer than the gate's 5 bands, favorites only) |
| 4 | consensus shape | net_count 3 / 4–5 / 6+; opposition 0 vs 1; price σ ≤0.04 vs 0.04–0.10 |
| 5 | backer composition | elite backer present (rank ≤10) yes/no; best_backer_rank ≤10 / 11–25 / 26–40 |
| 6 | freshness at fire | recency ≤30m / 30m–3h / 3h–48h |
| 7 | liquidity proxy | total_usd terciles |
| 8 | time-of-day (UTC) | 00–08 / 08–16 / 16–24 (slate structure, not astrology — interpret with regime) |
| 9 | horizon | resolves <6h / 6–24h / >24h after fire |

**Per-cell metrics (all event-clustered, at-fire entry, matched blind baseline):**
- `surplus` vs the blind baseline matched on (band × regime) — NEVER the global blind alone
- selection-null p (the `selection_null.py` machinery, profile-matched draws)
- realizable ROI at **measured costs** (real `entry_ask` where captured, else mid + 0.5¢, fee 2%)
- `freq` = qualifying events/day over the record, and events/day over the LAST 48h
  (tournament mix shifts — the World Cup is ending; recent frequency is the planning number)
- `expected_$_per_day` = freq_recent × $100-flat-shares × realizable_ROI, with a bootstrap CI
- persistence: positive in how many of the record's UTC days / regimes

**Multiplicity (binding):** the family = ALL cells across ALL dimensions × populations
(~150–250 cells). Rank by lower confidence bound with a Benjamini-Hochberg FDR at q=0.10
across the family for the null p-values. A cell is:
- **PRIORITIZE** ⇔ FDR-surviving null ∧ realizable-ROI lower bound > 0 at measured costs ∧
  N ≥ 20 events ∧ positive in ≥2 regimes-or-days-splits ∧ freq_recent ≥ 1 event/day
- **DODGE** ⇔ realizable-ROI UPPER bound < 0 at N ≥ 20 (reliably losing — the mirror test)
- **NEUTRAL / INDETERMINATE** otherwise (small N is indeterminate, never dodge-by-noise)

**Kill criteria (binding):**
- K1: if the market-type classifier maps <80% of resolved favorite-band titles confidently,
  report coverage and drop dimension 2 rather than guess.
- K2: any cell result that flips sign between the drifted-entry and at-fire computations is
  reported as UNSTABLE, never PRIORITIZE.
- K3: if <5 cells survive FDR, that IS the finding ("the winners are already the right
  granularity — no finer slicing is supported yet"); do NOT lower q or floors to manufacture
  results. A correctly-established "no finer structure" is a successful run.
- K4: nothing from this run changes live behavior. Output = instrument + tables + nominations.

---

## Phases (each ends gate-green + committed)

### Phase 0 — Setup & data honesty check (~30 min)
Worktree + branch + tag. Read the companion docs. Pull the resolved record; verify at-fire
coverage (initial_mean_price 100%), real-ask counts, and print the record's shape (events/day
by regime — the denominator of every frequency claim). Sanity: reproduce the two winners'
headline numbers (favorite ≈ +10.7% N≈95+; eff ≈ +9.2% N≈39+) — if you can't reproduce
within noise, STOP and diagnose before slicing.

### Phase 1 — The instrument: `scripts/slice_study.py` (the core deliverable)
House pattern (stdlib+numpy only, docker-exec psql --csv or DATABASE_URL, seeded, verdict
table to stdout + JSON artifact under `reports/`). Implements exactly the pre-registration:
slice extraction, matched-baseline surplus, profile-matched selection null per cell (≥1000
draws; reuse/refactor the machinery of `selection_null.py` rather than reimplementing —
extract shared helpers into `scripts/_gatelib.py` if cleaner, keeping `selection_null.py`'s
CLI byte-identical), realizable ROI at measured costs, frequency (whole record + last 48h),
expected-$/day with bootstrap CI, BH-FDR across the family, PRIORITIZE/NEUTRAL/DODGE verdicts.
**Self-test mode (mandatory, like decay_analysis.py):** synthetic fixture where cell X has a
known injected edge and cell Y none — the script must PRIORITIZE X, NEUTRAL Y, and a
pure-noise fixture must yield ~0 FDR survivors. Ships only with self-test PASS.

### Phase 2 — Run it, study it, write the map
Run on the live record. Produce the report (`reports/entries/NN-slice-study.md` following the
existing entries' style):
- The PRIORITIZE table (cells, metrics, expected $/day, CI) and the DODGE table.
- The frequency×reliability frontier: a text scatter of cells (freq_recent vs realizable-LB)
  — where does volume live, where does reliability live, where do they overlap?
- The WORST reliably-losing cells (what to dodge) with their mechanism hypothesis (e.g.
  soccer exact-score longshot residue, low-liquidity tails) — each hypothesis labeled as
  interpretation, not finding.
- Cross-checks on anything surprising: leave-one-day-out, drifted-vs-at-fire stability (K2),
  and an explicit "does this survive if the World Cup rows are excluded?" column for
  soccer-driven cells (the WC ends imminently — a WC-only edge has near-zero forward freq).
- An explicit answer to: **"which single change most raises expected $/day WITHOUT dropping
  the reliability bar?"** (candidates the data may or may not support: adding band 0.65–0.80
  from P3-strict to the alert set; a tennis-moneyline-only variant; excluding a DODGE cell
  from `favorite` to raise its ROI; none-of-the-above.)

### Phase 3 — Nominations (pre-registered forward confirmation, NOT promotion)
For at most 2 surviving refinements: write the exact `StrategyDef` params, the forward
evaluation points (first read at N=30 events, then every +15), and the D7 bar they must
clear ON FORWARD DATA before any alerting/promotion talk. If justified, add them as SILENT
variants (additive, `alerting: false`, experimental family if model-like / core if pure
param variants — follow `enrich::family`). If K3 fired, write the "no finer structure yet"
finding instead and define the accrual trigger for re-running this study (e.g. +7 days or
+300 fleet events, whichever first).

### Phase 4 — Ship & verify
DECISIONS.md += D13 (what the study found, what it nominated/dodged, why the multiplicity
machinery is trustworthy); update REFINED-STRATEGY.md's rules ONLY where the study's
FDR-surviving evidence contradicts or sharpens them (each edit cites its cell). Merge
`--no-ff` to main; **re-run the full gate on post-merge main**; confirm the auto-deploy
stays healthy (doc/script-only changes don't rebuild the bot — verify the updater log says
so). Final report to Tue: PRIORITIZE/DODGE tables, the one highest-leverage change, what was
deliberately NOT done, exact rollback.

---

## Rejected approaches (do not build)

- **Optimizing thresholds per cell** (e.g. fitting the best σ cut per sport): that's fitting
  noise at N≈tens; the study SLICES pre-registered cuts, it never tunes.
- **A composite ML ranker over slice features:** the market_resid lesson — composition
  masquerades as skill; only matched-baseline + null-per-cell separates them.
- **Dodge-by-small-N:** an indeterminate cell is not a dodge. DODGE requires the upper bound
  below zero at floor N.
- **Promoting anything from this run's own data:** exploration nominates; forward data
  confirms; the D7 rule promotes. Three different datasets, by construction.
- **Buying frequency with looser gates:** already refuted (the ≥0.65 wide pool is −1.4%
  realizable). Frequency comes from more markets, more sports, more tournaments — or it
  doesn't come.

## Acceptance

Gate-green commits; `slice_study.py` with PASSING self-test; the PRIORITIZE/DODGE report with
FDR-corrected, matched-baseline, cost-realistic, frequency-weighted verdicts; ≤2 pre-registered
silent nominations (or the honest "no finer structure"); DECISIONS D13; REFINED-STRATEGY
updated only where evidence binds; merged + post-merge re-gated; live behavior unchanged.
Paper-only. The output is a MAP — what to prioritize, what to dodge, and what single change
most raises reliable $/day — not a pile of green cells.
