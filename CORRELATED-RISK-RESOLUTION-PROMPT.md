# Autonomous run — "Correlated Risk": size the GAME, not the position — and keep the profit

> **How to run.** Paste this whole file as the task for a fresh Claude Code session opened in
> `~/polymarket-bot`, or dispatch it:
> `claude -p "$(cat ~/polymarket-bot/CORRELATED-RISK-RESOLUTION-PROMPT.md)"`
> Long, self-directed run. Work autonomously to a finished, gate-green, merged deliverable +
> a corrected go/no-go memo. Only stop for a decision that is genuinely Tue's (e.g. "apply the
> new sizing to the live bot — yes/no", "commit real money — yes/no").
> Companion reading (house style + ground truth): `DECISIONS.md` (D1–D19), `REFINED-STRATEGY.md`,
> `REPORT.md`, `scripts/risk_engine.py`, `scripts/portfolio_concentration.py`,
> `scripts/effective_n.py`, `scripts/selection_null.py`, `reports/entries/2026-07-02-12-diversification-risk.md`,
> `reports/entries/2026-07-02-14-reliability-portfolio.md`.

---

## 0. The mission (read twice)

A pre-run investigation established a risk the current instruments under-count: **the book's
true unit of correlation is the GAME (match-key), not the position and not the `event_slug`.**
The `favorite` book holds **219 positions on only 79 games**, and **62% of positions sit on 10
World Cup soccer games** (17, 16, 16, 15, 14, 14, 12, 12, 11, 9 positions each). Positions on one
game — moneyline, spread, six "Exact Score X — No", O/U, "team to advance" — all resolve on the
**same underlying outcome**. With flat-shares on favorites the per-position payoff is asymmetric
(**+$8 win / −$92 loss** on a 0.90 favorite), so a single upset in a stacked game is a
**synchronised −$600 to −$1,200 block loss**, versus ~+$50–100 when it goes chalk (~10:1
downside:upside on the block).

The existing `portfolio_concentration.py` reported within-slate **ICC ≈ 0.008 ("independent")**.
That number is an artifact of (a) being computed on advantage *residuals vs a matched-blind
baseline* (which subtracts the shared favorite factor by construction), (b) a **93%-win sample with
essentially no losing day** (near-zero residual variance ⇒ ICC ⇒ 0), and (c) the event-clustering
step having already collapsed the worst same-`event_slug` stacks *before* the ICC was measured. A
game-clustered Monte Carlo with a nested copula + edge-haircut sweep (the pre-run sim, reproduce it)
showed the honest tail: at the **measured** edge, 1-yr maxDD p95 ≈ 13%; at **half** the edge P(loss)
≈ 7% with p95 maxDD ≈ 30%; at a **quarter** edge P(loss) ≈ 38%; **edge-zero (efficient market)**
P(loss) ≈ 77% with p95 maxDD ≈ 82%. The whole go/no-go pivots on λ = how much of the measured edge
is real — and **4 benign days cannot distinguish λ=1 from λ=0.25**, because the separating event (an
adverse correlated day) is exactly what the record does not contain.

> **One sentence:** Make the risk engine measure and size the real correlation unit (the game),
> then find the sizing/selection policy that **maximises profit PER UNIT of honestly-measured,
> edge-robust tail risk** — not the policy that minimises risk, and not the one that maximises raw
> growth on a no-loss sample.

**The motto:** *the game is the bet; a dozen markets on one game is one bet levered a dozen times;
size the bet, keep the edge, drop the redundancy that is pure levered variance.*

---

## Ground truth you must NOT relitigate (evidence in DECISIONS.md / the entries)

- **The correlation unit is the match-key**, defined as `event_slug` (or `condition_id`) with the
  trailing market suffix stripped:
  `regexp_replace(COALESCE(event_slug,condition_id), '-(exact-score|more-markets|first-to-score|halftime-result|total-corners|player-props|score)$','')`.
  One game = up to 3 distinct `event_slug`s and up to 17 positions. Use this key everywhere risk is
  aggregated. (`portfolio_concentration.py` already strips a suffix for its MATCH grain — reuse/extend
  that exact helper; do not invent a second key.)
- **The gate judges the AT-FIRE entry** `COALESCE(initial_mean_price, mean_price)` (D6), event-clustered
  on `COALESCE(event_slug, condition_id)`, at **measured costs** (0.5¢ haircut + 2% fee). Never the
  drifted `mean_price`. This run does not change the promotion gate (D7) or the null (`selection_null.py`).
- **Reliability is supply-limited, not allocation-limited (D15/D17):** no orthogonal second edge exists
  today (0/12; `trust_weighted` is the only power-starved near-miss). So this run does NOT try to
  diversify into a second strategy — it makes the ONE edge's sizing honest about within-book correlation.
- **`kelly_eighth_capped` is the current risk-constitution sizing (D15/D17):** ⅛-Kelly per band, SE-shrunk,
  caps `≤1 unit/event`, `≤3 units/slate`, `≤40%/regime`, −5-unit daily stop. **The load-bearing gap this
  run fixes:** those caps key on `event_slug`, so they do NOT bind at the true game level (one game spans
  3 `event_slug`s). The `≤1 unit/event` cap lets a single game take ≥3 units today.
- **flat-SHARES, never flat-$** (the sign-flip/ruin on longshot-carrying streams reproduces on flat-$);
  **skip longshots**; **no edge decay inside ~30 min**; `resolved_at` is processing time; **P(profit)=100%
  on the record is the "no-losing-slate" artifact**, never a promise (D15). Every P(profit) is
  **conditional on the edge being real and persisting** — that is D7's job, not this run's.
- **Applied migrations are IMMUTABLE** (comment edit ⇒ sqlx checksum crash-loop in prod). This run should
  need **no** migration. If you truly do, next free number only, additive, append-only.

## Non-negotiable guardrails

1. **Reversibility.** Isolated git worktree off fresh `main`, new branch, tag the pre-run state. Other
   Claude sessions run in parallel — `git worktree list`, keep your file slice non-overlapping, smallest
   additive changes to shared files, say so when you must touch one.
2. **Gate every commit:** `RUSTFLAGS="--cfg tokio_unstable -Dwarnings" cargo fmt --check --all && cargo
   clippy --workspace --all-targets && cargo test --workspace`; Python = `python3 -m py_compile` + a
   synthetic-fixture smoke run. **Re-run the FULL gate on `main` AFTER your merge lands** (main moves under
   you; the autoupdater ships whatever is on main).
3. **Paper-only, additive, belief-blind.** No real money, no order placement, no alerting change, no env
   flip, no auto-promotion. Any new sizing policy or per-game cap is **proposed, not applied** to the live
   Rust; behaviour flips on the live bot require **Tue's explicit go**.
4. **Deploys only via `scripts/consensus-autoupdate.sh`** (never manual `docker compose up`).
5. **Cost-zero** (Max only, no `ANTHROPIC_API_KEY`, no child `claude` spawns).
6. **DB access** is read-only: `docker exec -i polymarket-bot-postgres-1 psql -U bot -d polymarket --csv -q`.

---

## Pre-registration (write this into the report BEFORE computing anything)

### The objective function (the thing being maximised — frozen)

**RECOMMENDED policy = the one that maximises median log-growth per 100 events, SUBJECT TO
`P(maxDD > 25%) ≤ 10%` evaluated under the GAME-BLOCK-correlated model AT λ = 0.5 (half the measured
edge).** The λ=0.5 constraint is the teeth: the chosen policy must survive the edge being only half real,
because the correlated tail is exactly what punishes an over-estimated edge. Report the full frontier;
recommend the knee, not a corner. Also report a **risk-adjusted-return ratio** = median growth ÷ p95-maxDD
(both under the game-block model at λ=0.5) for every policy, so "profit in relation to risk" is a single
comparable number.

### The correlation model (frozen — this is the fix)

Monte Carlo resamples **match-key (game) blocks with replacement**, not positions and not `event_slug`s.
Two arms, always both reported:
- **A · block-bootstrap (benign):** each sampled game keeps its REAL joint outcome — preserves the
  measured within-game correlation exactly. This is the "future = the good days we saw" floor.
- **B · parametric copula + edge-haircut (the honest tail):** true `P(win) = clip(entry + λ·δ, 0.02, 0.995)`,
  δ calibrated so λ=1 reproduces the realized win rate; nested Gaussian copula with a **within-game** latent
  weight `w_game` and a **within-slate-day** weight `w_day`. Sweep **λ ∈ {1, 0.5, 0.25, 0}** and report the
  whole curve; the verdict lives in its shape. `w_game` is an assumption you must not fit on a no-loss
  sample — instead **estimate a data-driven LOWER BOUND** from the games that actually had mixed win/loss
  (e.g. Germany–Paraguay 12/14, Mexico–Ecuador 15/17), and sweep `w_game ∈ {lower_bound, 0.4, 0.55, 0.8}`;
  report tail sensitivity to it (higher correlation ⇒ fatter tail ⇒ report it as the binding uncertainty).

### The policy family (frozen — no additions after seeing results)

Same pick stream, at-fire entry, measured costs, bankrolls B ∈ {$5k, $10k, $25k}:
- **P0 flat_shares** (current default) and **P1 kelly_eighth_capped** (current constitution) — baselines to beat.
- **P2 per-game cap:** P1 + a hard `≤ K_game units per MATCH-KEY` cap, keyed on the game, swept `K_game ∈
  {1, 2, 3, 5, ∞}`. When capped, keep the **highest-edge** positions in the game (rank by matched-blind
  surplus / by band), not arbitrary ones.
- **P3 within-game selection:** P2 + **drop the redundant near-certain markets** (the "Exact Score X — No"
  family and any market whose at-fire entry ≥ 0.95 whose EV per unit of block-variance is dominated). Test
  whether dropping them is EV-free or EV-positive on a risk-adjusted basis (they pad win-rate for ~+$5 upside
  while adding correlated tail).
- **P4 per-game Kelly:** size the GAME as one bet (aggregate the game's independent-information content),
  then split across its kept markets — i.e. Kelly on the de-duplicated game exposure, not per position.
- **Ceiling / ruin:** maxDD peak-relative; ruin = bankroll ever ≤ 20% of B. Caps evaluated inside each
  resampled block (no outcome leakage except a realized-P&L stop-loss).

### Metrics per policy (all game-clustered, at-fire, measured costs)
median & 5th-pct terminal P&L; **P(loss)**; **P(maxDD>25%)** and maxDD median/p95; **worst single-GAME block
loss** (med/p95) — the headline the pre-run sim surfaced; **ruin prob**; growth per 100 events; the
**risk-adjusted ratio** above. All at λ ∈ {1,0.5,0.25,0} and the `w_game` sweep. Horizons H ∈ {1×record,
~1yr (5×)} with K1 extrapolation labelling beyond n_eff.

### Kill criteria (binding)
- **K1** `n_eff` (game-grain) < ~40 ⇒ long-horizon P(loss)/maxDD is EXTRAPOLATION; lean on H=1×.
- **K2** conclusions flipping across `w_game` or bootstrap grain ⇒ the conservative (fattest-tail) setting
  binds and the fragility is a headline, not a footnote.
- **K3** no "guaranteed"/"almost guaranteed" language; every P(profit) carries the conditional-on-edge caveat
  and the λ=0 line; report the risk-adjusted ratio at λ=0.5 as the honest number.
- **K4** nothing changes live behaviour — instrument + proposed policy + memo only. The recommended sizing is
  **pre-registered for the hypothetical GO day**, not applied to the Rust bot.
- **K5 (profit-preservation, the "keep the profit" teeth):** the recommended policy's **median growth at λ=1
  must be ≥ 90% of P0/P1's** — i.e. de-levering the correlated tail must NOT throw away the profit. If no
  policy both cuts the tail AND preserves ≥90% of the edge's growth, that IS the finding (state it; do not
  pick a tail-safe policy that guts EV).

---

## Phases (each ends gate-green + committed)

### Phase 0 — Setup & reproduction (~30 min)
Worktree + branch + tag. Read the companion docs. Pull the resolved `favorite` record; reproduce the pre-run
facts (219 positions, 79 games, 62% on 10 WC games, realized WR ≈ 0.93, δ ≈ 0.11, worst-game block loss
−$600…−$1,200 under the copula). Reproduce the ICC ≈ 0.008 and **explain in one paragraph why it is a benign-
sample artifact** (residual-vs-baseline + no-loss + pre-collapsed stacks). If any of these don't reproduce
within noise, STOP and diagnose before proceeding.

### Phase 1 — The honest correlation measurement
Extend `portfolio_concentration.py` (or a new sibling `scripts/game_correlation.py` reusing its match-key
helper + `selection_null` fetch/band/regime) to report, per strategy: positions→games→effective-games; the
**position-per-game distribution**; the **data-driven lower-bound within-game correlation** estimated from
mixed-outcome games; and **n_eff at the GAME grain** (reuse `effective_n.py`'s cluster-robust estimator — it
already spans the ICC endpoints). Deliver the honest "how many independent bets do we really hold" number at
the game unit (expected: well below 79, far below 219).

### Phase 2 — The risk-adjusted sizing instrument (core deliverable)
`scripts/corr_risk_engine.py` — house pattern (stdlib+numpy, docker-exec psql, seeded, verdict table to
stdout + JSON under `reports/`), reusing `risk_engine.py`'s sizing/bootstrap machinery byte-compatibly where
possible. Implements exactly the pre-registration: game-block bootstrap + copula/λ sweep, the full policy
family P0–P4, all metrics, the frozen objective + risk-adjusted ratio.
**Self-test (mandatory, ship only on PASS):** (a) an iid fixture ⇒ game-block and position bootstrap agree
and the per-game cap is inert; (b) a **fully-correlated-game fixture** ⇒ the game-block bootstrap recovers the
inflated block variance AND the per-game cap provably truncates the block loss AND a position-level bootstrap
UNDERSTATES it (the exact leak this run fixes); (c) a **zero-edge fixture** ⇒ every policy loses to costs
(λ=0 line); (d) a scripted upset-cluster ⇒ the stop-loss / caps bind as designed.

### Phase 3 — Optimise profit-in-relation-to-risk
Run P0–P4 across the λ and `w_game` sweeps. Produce: the **frontier** (growth vs p95-maxDD, one point per
policy×K_game), the **knee** (recommended policy), and the **K5 profit-preservation check** (recommended
median growth at λ=1 vs baselines). Answer explicitly: **does a per-game cap + dropping the exact-score
redundancy RAISE the risk-adjusted ratio (a free lunch), or do the stacked markets carry independent EV worth
their tail?** Quantify the EV of the dropped markets directly (their own matched-blind surplus and null),
don't assume. Cross-check: does the recommendation survive excluding the World-Cup rows (they expire)?

### Phase 4 — The corrected go/no-go memo
`reports/entries/2026-07-02-18-correlated-risk.md` (house style). Deliver: the honest game-grain n_eff and the
corrected tail table (λ sweep × policy); the **worst-correlated-block** numbers; the **recommended
pre-registered sizing** (which K_game, which within-game selection, which policy) with its risk-adjusted ratio
at λ=0.5 and its growth at λ=1 (the K5 number); and a blunt **go / no-go / not-yet** verdict that turns on λ —
stating plainly that the record cannot yet establish λ and what forward evidence would (survive ≥K adverse
correlated days across ≥5 non-expiring regimes, per D18/D19). If K5 fails (no policy preserves the profit while
cutting the tail), say so and recommend the honest trade-off explicitly.

### Phase 5 — Ship & verify
`DECISIONS.md += D20` (what the corrected model found; the per-game-cap gap in the existing caps; the
recommended sizing; why the multiplicity/robustness machinery is trustworthy; that nothing was applied live).
Update `REFINED-STRATEGY.md` and the risk-constitution note ONLY where this run's evidence sharpens them (cite
each edit): specifically the caps must be re-stated as **match-key-keyed** (`≤ K_game per game`), not
`event_slug`-keyed. Merge `--no-ff` to `main`; **re-run the full gate on post-merge main**; confirm the
autoupdater log shows no rebuild (doc/script-only). Final report to Tue: the corrected tail, the recommended
risk-adjusted sizing, the one number for "profit in relation to risk," what was deliberately NOT done, exact
rollback.

---

## Rejected approaches (do not build)

- **Minimising risk regardless of profit** — the objective is the RATIO; a policy that halves growth to shave
  the tail fails K5. Keep the edge.
- **Diversifying into a second strategy** — refuted as supply-limited (D15/D17); this run sizes the ONE edge
  honestly, it does not invent partners.
- **Fitting `w_game` (or per-game Kelly fraction) on the record** — you cannot estimate correlation or a Kelly
  edge from a no-loss sample; sweep it, bound it from mixed-outcome games, report sensitivity.
- **Per-cell / per-market threshold tuning** — that's fitting noise (the market_resid / entry-10 lesson). Size
  the game as a unit; select within-game by pre-registered surplus rank, not a tuned cut.
- **Applying anything to the live Rust bot or promoting a policy** — this run proposes; D7 + a pilot + Tue
  decide. Three different gates.
- **Treating P(profit)=100% or the benign block-bootstrap as evidence of safety** — it is the no-losing-slate
  artifact; the honest tail is arm B at λ ≤ 0.5.

## Acceptance

Gate-green commits; `scripts/corr_risk_engine.py` with PASSING self-test (incl. the position-bootstrap-
understates-the-tail case); the corrected game-grain tail + frontier + recommended risk-adjusted sizing;
the K5 profit-preservation verdict; a blunt go/no-go/not-yet that turns on λ; `DECISIONS.md` D20;
`REFINED-STRATEGY.md` caps re-keyed to the game; merged + post-merge re-gated; live behaviour unchanged;
paper-only. The output is a **sizing that keeps as much of the edge's profit as possible per unit of
honestly-measured, edge-robust correlated tail risk** — plus the honest statement of what the 4-day record
still cannot tell us.
