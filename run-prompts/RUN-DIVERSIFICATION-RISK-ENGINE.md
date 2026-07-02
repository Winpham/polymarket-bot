# Long Autonomous Run — Diversification & Risk Engine: concentration measured, sizing optimized, P(profit) made real

Paste this whole file as the task for a fresh long-running session. **Self-contained.**
Work in `~/polymarket-bot` (Rust; deploy branch = `main`, auto-deploys ~5 min after merge).
Companion reading (house style + ground truth you must not relitigate): `DECISIONS.md`
(D1–D13+), `REFINED-STRATEGY.md`, `reports/entries/2026-07-02-10-slice-study.md`,
`reports/slice_study.json`, `scripts/slice_study.py`, `scripts/selection_null.py`,
`run-prompts/RUN-ADAPTIVE-SLICE-OVERLAY.md` (the sibling run: breadth/supply — this run
owns ALLOCATION/risk; keep the seam clean).

---

## 0. The one-sentence mission

Measure the TRUE concentration of our forward record (how few independent bets we
actually hold once same-event, same-slate, and same-regime correlation is priced in),
build a correlation-aware paper risk engine that Monte-Carlos the winners' measured
joint structure under a FROZEN menu of sizing policies (flat-shares, fractional Kelly,
exposure caps, drawdown throttles), and emit the pre-registered **default risk policy**
that maximizes long-run growth subject to explicit loss-probability ceilings — so that
the day D7 ever certifies real money, the sizing question is already answered with
numbers, not vibes.

## The honest reframe of the goal (read this first, it is binding)

The owner asked for "almost guaranteed profit." **No honest system can promise that, and
this run must never claim it.** The correct translation, and this run's actual product:

- **P(profit) is a NUMBER, not a promise.** Given a strategy's measured edge, variance,
  correlation structure, and costs, compute P(P&L > 0 at horizon H) and P(max drawdown >
  X) — with CIs — under each candidate policy. Then pick the policy that maximizes
  growth subject to pre-registered ceilings (below). Report the number even if it's ugly.
- **Sizing sizes an edge; it cannot create one.** If the edge is zero, every policy loses
  to costs eventually. All P(profit) outputs are CONDITIONAL on the measured edge being
  real (D7's job, not this run's) and on it persisting. State this on every output.
- **Diversification cannot be optimized into existence.** The 2026-06-30 congregation
  run already proved the record collapses to ~one tournament weekend (slate collapse:
  effective independent N ≪ nominal N). If that still holds, the honest finding is
  "diversification ACCRUES with market breadth (the sibling run's lever); today the only
  real levers are sizing + exposure caps" — quantified, not lamented.

## Ground truth you must NOT relitigate

- Gate = AT-FIRE entry (D6); event-cluster by `COALESCE(event_slug, condition_id)`
  ALWAYS; D7 promotion rule unchanged; nothing here promotes anything or touches money.
- **Winners:** `favorite` (+10.5% surplus N=94, realizable ≈ +9.3%/bet) and
  `elite_fresh_fav` (+9.1% N=39, ≈ +7.7%) — certified-ELIGIBLE, not promoted; floors
  N≥50 + post-Wimbledon re-read stand. `elite_fresh_fav` is heavily a SUBSET of
  `favorite` — their "diversification" across strategies is largely the same bets;
  measure the overlap, never double-count it.
- **Sizing truths already settled:** flat-SHARES (or fractional Kelly), NEVER flat-$
  (flips the P&L sign); skip longshots; costs = 0.5¢ measured haircut + 2% fee; no decay
  <30 min (manual execution fine).
- **Slice map (entry 10):** PRIORITIZE = favorite's favorite-band slices at 10–20
  ev/day; DODGE = the fleet's non-favorite residue. The record is ~89% WC soccer +
  Wimbledon; both end within weeks. Crypto: blind-rich, consensus never fires.
- The record is 4–6 days of one tournament cycle. Every portfolio statistic you compute
  inherits that. Say so wherever it matters.

## Non-negotiable guardrails

1. **Reversibility.** Isolated git worktree off `main`, fresh branch, tag the pre-run
   state. Parallel sessions exist — check `git worktree list`, non-overlapping file
   slice, DECISIONS.md append-only at the end. The sibling overlay/breadth run may be
   live: do NOT touch `scripts/map_state.py` / `map_checkpoint.py` / its entry.
2. **Gate every commit:** `RUSTFLAGS="--cfg tokio_unstable -Dwarnings" cargo fmt --check
   --all && cargo clippy --workspace --all-targets && cargo test --workspace`; Python =
   `py_compile` + self-tests on synthetic fixtures. **Re-run the FULL gate on post-merge
   main** (the auto-deployer ships whatever is there).
3. **Applied migrations are IMMUTABLE.** This run should need ZERO migrations (it reads
   the record and writes reports). If one becomes truly necessary, next free number,
   additive, append-only — and justify it in the report.
4. **Paper-only, read-only on live behavior.** No real money, no orders, no alerting or
   env changes, no auto-promotion. Output = instruments + a pre-registered policy DOC.
5. **Deploys only via `scripts/consensus-autoupdate.sh`**; anything touching the live
   bot's behavior requires Tue's explicit go — this run should require none.
6. Cost-zero (Max only, no ANTHROPIC_API_KEY, no child claude spawns).

---

## Pre-registration (write into the report BEFORE computing anything)

### Concentration metrics (the "are we over-reliant" battery — frozen)

Per strategy (favorite, elite_fresh_fav, strict-as-fleet-reference) over the resolved
record, all at-fire, all cost-realistic:

1. **Correlation grains:** outcome co-movement at (a) same event (multi-market same
   match — favorite fires several markets of one game), (b) same slate = (regime ×
   UTC-day), (c) same regime across days, (d) cross-strategy overlap (favorite ∩
   elite_fresh_fav shared events, share of each). Estimator: event-level advantage
   residuals; report the intraclass correlation per grain.
2. **Effective N:** N_eff = N / design-effect from the measured ICCs, per grain and
   combined. The single most important number of the run: how many INDEPENDENT bets the
   record actually contains (the congregation run's slate-collapse finding, now at
   portfolio grain).
3. **Concentration indices:** HHI of exposure by regime, by event-day, by tournament;
   share of P&L from the top-1 tournament (the WC-reliance number the owner asked
   about, stated as % of profit).

### The policy menu (frozen — no additions after looking at results)

All policies applied to the SAME pick stream (a strategy's resolved picks in fire
order), same costs, bankroll parameterized B ∈ {$1k, $5k, $25k}:

- P0 `flat_dollar_100` — control, known bad (must reproduce the sign flip).
- P1 `flat_shares_100` — current house default.
- P2 `kelly_quarter`, P3 `kelly_eighth` — fractional Kelly on the strategy's OWN
  measured (edge, odds) per band, shrunk toward 0 by the band's estimation SE
  (shrinkage factor frozen: LB/point-estimate ratio); never per-market fitting.
- P4 `flat_shares_capped` — P1 + exposure caps: max 1 unit per event, max K=3 units per
  slate (regime × UTC-day), max 40% of daily units in one regime, daily stop-loss at
  −L units (L=5) pausing NEW entries until next UTC day.
- P5 `kelly_eighth_capped` — P3 + P4's caps (the expected winner a priori; the data
  decides).
- Ceilings for "acceptable": P(loss at H=300 resolved events) and P(maxDD > 30% of B).
  The RECOMMENDED policy = highest median log-growth subject to P(maxDD>30%) ≤ 10%.
  The ceilings are frozen now, before any simulation.

### The Monte Carlo (frozen)

- **Block bootstrap at the slate grain** (resample (regime × UTC-day) blocks with
  replacement, preserving within-slate and within-event correlation exactly) — NEVER
  iid-per-pick resampling (it would fake diversification that isn't there). Sensitivity
  check at event-day and regime-week grains: report all three; the CONSERVATIVE one
  binds (K2).
- ≥10,000 paths per (strategy × policy × B), seeded. Horizons H ∈ {100, 300, 1000}
  resolved events (and the calendar-time equivalent at measured freq_recent — state
  both, frequency is tournament-dependent).
- Outputs per cell: median and 5th-pct terminal P&L, P(P&L>0), max-drawdown
  distribution, ruin probability (bankroll ≤ 20% of B), growth per 100 events.
- **Diversification experiments (descriptive):** variance and P(loss) of favorite-only
  vs favorite+eff (dedup overlap) vs favorite restricted to its PRIORITIZE cells vs
  spread-across-regimes-equally (feasibility-weighted by actual freq) — the marginal
  value of each diversification axis GIVEN today's correlation, stated honestly.

### Self-tests (mandatory, like decay_analysis.py / slice_study.py)

- iid fixture with known edge/odds → simulated optimal Kelly fraction and P(loss) must
  match analytics within CI.
- Correlated fixture (known ICC) → block bootstrap must reproduce the inflated variance
  (and iid resampling on the same fixture must UNDERSTATE it — prove the leak the design
  avoids); N_eff estimator must recover the true design effect.
- Cap-policy fixture: a scripted losing streak inside one slate must trigger the caps
  and provably truncate the drawdown vs P1.
- Ship only with self-test PASS.

### Kill criteria (binding)

- K1: if N_eff over the whole record < ~40 (likely), every P(loss) at H=1000 is an
  EXTRAPOLATION — label those cells as such and lean on H=100/300; do not present
  extrapolated certainty.
- K2: grain sensitivity — if conclusions flip across bootstrap grains, the conservative
  grain binds and the fragility is a headline finding, not a footnote.
- K3: **no "guaranteed" language anywhere.** Every P(profit) is conditional on the
  measured edge persisting; the report must carry the zero-edge line: "if the edge is
  not real, every policy loses; this engine sizes edges, it does not create them."
- K4: nothing changes live behavior; the recommended policy is PRE-REGISTERED for the
  hypothetical real-money day (which still requires D7 + pilot floors + Tue), not
  applied to anything.

---

## Phases (each ends gate-green + committed)

### Phase 0 — Setup & reproduction (~30 min)
Worktree + branch + tag. Reproduce the winners' headline surplus and realizable ROI
within noise (STOP and diagnose if not). Print the record's shape: picks, events,
slates, regimes, days per strategy; the favorite∩eff overlap share; the % of each
strategy's P&L from WC rows (the owner's over-reliance number, first read).

### Phase 1 — Concentration & correlation instrument
`scripts/portfolio_concentration.py`: the pre-registered battery (ICC per grain, N_eff,
HHI, top-tournament P&L share, cross-strategy overlap dedup). Self-test with synthetic
known-ICC fixtures. Run live; the headline is N_eff vs N and the WC P&L share. If slate
collapse dominates (K1 expected), say plainly: "the record currently holds ~X
independent bets; diversification is supply-limited (sibling run), not
allocation-limited."

### Phase 2 — The risk engine
`scripts/risk_engine.py`: the frozen policy menu × block-bootstrap Monte Carlo ×
bankrolls × horizons, seeded, with ALL self-tests. JSON artifact under `reports/` +
stdout verdict table (policy × strategy: median growth, P(loss@H), P(maxDD>30%), ruin).
Include P0 flat-$ reproducing the known sign flip as a validity anchor.

### Phase 3 — The diversification read & the policy verdict
Run the diversification experiments; answer, with numbers: (1) how much does adding
eff to favorite actually reduce risk after dedup (suspicion: little — mostly the same
bets)? (2) does restricting to PRIORITIZE cells improve risk-adjusted growth or just
shrink N? (3) what would an extra independent regime be WORTH (variance reduction per
ev/day of uncorrelated volume) — the number that prices the sibling breadth run's
lever. Then the verdict: the RECOMMENDED default policy per the frozen ceilings, its
exact parameters, its P(profit)/P(maxDD) numbers at each horizon with the conditional-
on-edge caveat, and the accrual triggers for re-running (post-WC, +N events, and BEFORE
any real-money pilot).

### Phase 4 — Ship & verify
`reports/entries/NN-diversification-risk.md` (pre-registration verbatim + results +
the honest P(profit) table); DECISIONS.md += next D number (policy verdict + why the
ceilings + what would change it); REFINED-STRATEGY.md: replace rule 3's bare
"flat-SHARES (or ¼-Kelly)" with the measured recommendation ONLY if the engine's
verdict differs from the current default (cite the entry). Merge `--no-ff`; re-run the
FULL gate on post-merge main; confirm the updater log (scripts/docs-only → "skipped
rebuild"). Final report to Tue: N_eff + WC-share headline, the policy table, the
recommended policy + its numbers, what an independent regime is worth, what was NOT
done, exact rollback.

---

## Rejected approaches (do not build)

- **Markowitz / mean-variance / covariance-matrix optimizers** on a 4–6-day record —
  estimation noise dressed as science; the block bootstrap + caps menu IS the honest
  version at this N.
- **Per-market or per-cell Kelly fitting** — same overfit class as per-cell threshold
  tuning (rejected in entry 10); Kelly inputs are per-band with SE shrinkage, frozen.
- **Martingale / loss-recovery / "double after drawdown" sizing** — never; ruin
  machines.
- **Normal-approximation VaR theater** — every tail number comes from the bootstrap
  paths.
- **Adding markets/venues to manufacture diversification** — supply is the sibling
  run's lane; this run prices what supply would be worth, it does not procure it.
- **Any "guaranteed profit" framing** (K3) — the deliverable is a maximized, measured
  P(profit) with its conditions stated, which is the only version of "almost
  guaranteed" that survives contact with reality.

## Acceptance

Gate-green commits; `portfolio_concentration.py` + `risk_engine.py` with PASSING
self-tests (analytic-Kelly match, correlated-fixture variance recovery incl. the
iid-understates proof, cap-truncation proof); the pre-registered policy menu evaluated
over ≥10k seeded paths × 3 bankrolls × 3 horizons at the conservative grain; N_eff /
HHI / WC-P&L-share headline; the recommended default policy with explicit
P(profit)/P(maxDD)/ruin numbers and the conditional-on-edge caveat on every table;
entry NN + DECISIONS + (only-if-evidence-binds) REFINED-STRATEGY rule-3 update;
merged + post-merge re-gated; live behavior unchanged; paper-only; zero migrations
(or one, justified). The output is a RISK CONSTITUTION — how we would bet when the
gate ever says yes, sized so the measured chance of losing is as small as the data
allows us to honestly claim — not a promise of profit.
