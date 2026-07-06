# Autonomous run — "Edge Truth & Levers": stop ASSUMING the edge, MEASURE it; size it right; stop the leak; prepare the pilot

> **How to run.** Paste this whole file as the task for a fresh Claude Code session opened in
> `~/polymarket-bot`, or dispatch it:
> `claude -p "$(cat ~/polymarket-bot/EDGE-TRUTH-AND-LEVERS-PROMPT.md)"`
> Long, self-directed run. Work autonomously to finished, gate-green, merged deliverables. **Stop
> only for the two decisions that are genuinely Tue's:** "flip the favorite/elite alert live —
> yes/no" and "commit real money to the pilot — yes/no." Everything else you build, verify, and
> ship on paper without asking.
> Companion reading (house style + ground truth): `DECISIONS.md` (D15–D21), `REFINED-STRATEGY.md`,
> `reports/entries/2026-07-02-{12,14,15,17}-*.md` and `2026-07-02-{18,19}-correlated-risk*.md`,
> `scripts/{corr_risk_verify,corr_risk_engine,persistence_tracker,selection_null,effective_n}.py`.

---

## 0. The mission (read twice)

Every profit number this program has ever produced is **conditional on λ — how much of the measured
favorite edge (δ = realized-WR − price ≈ +0.14) is REAL versus favorite-longshot bias.** Four
benign World-Cup days cannot distinguish λ=1 (life-changing) from λ=0.25 (near break-even with 50%
drawdowns) from λ=0 (you lose), because the separating event — an adverse correlated day — has not
occurred. The sizing question is SETTLED (D18–D21: de-lever, the game is the correlation unit, the
Kelly fraction is the first-order lever, no per-game cap improves portfolio downside). **The
bottleneck is no longer HOW to bet — it is WHETHER the edge is real, and stopping the value that
leaks out today.** This run attacks exactly that, on four fronts:

- **WS-A · MEASURE λ, don't assume it (CLV).** If our at-fire entries consistently beat the market's
  CLOSING line, that is independent, pre-resolution evidence the edge is REAL (the line moves our
  way) rather than luck or favorite-longshot bias. Build the closing-line-value instrument the D18
  stress test flagged as an EMPTY monitor, and turn δ from an assumption into a measured, null-tested
  number with a data-driven λ estimate. **This is the marquee — it attacks the one unknown everything
  else is conditional on.**
- **WS-B · SIZE it correctly (optimal de-lever).** D18/D19/D21 all concluded "de-lever the band-5
  Kelly" but never PINNED the fraction. Find the Kelly multiplier that maximizes growth-per-unit-of-
  CVaR under the adverse (t-copula + heterogeneous-correlation) model, robust across λ∈{1,0.5,0.25}.
- **WS-C · STOP the value leaking now (the alert leak).** D19-b: effective alerting is `strict` ONLY
  (−EV after costs, the entry-10 DODGE) while `favorite`/`elite_fresh_fav` stay SILENT — anyone
  acting on alerts follows the WRONG signal. This is the single biggest **realized**-P&L lever and it
  costs nothing. **Build + shadow-verify + PROPOSE** the fix; the live flip is Tue's call.
- **WS-D · PREPARE the one thing that generates truth (a tiny de-levered pilot).** D18/D19: a small
  pilot DOMINATES waiting — it is the only thing that produces genuine OUT-of-sample truth to move λ
  off "unknown." **Build + shadow the harness** (de-levered sizing, kill-switches, CLV + honest-P&L
  tracking) so it is one-approval-away. **No real money is placed by this run.**

> **One sentence:** turn the edge from an ASSUMPTION into a MEASUREMENT (CLV/λ), size it with the
> honestly-pinned de-lever fraction, stop the winners' signal from leaking out silently, and stand up
> a real-money-ready-but-not-armed pilot — so the next dollar of work buys TRUTH, not more modeling.

**The motto:** *we have modeled the edge to death; now go find out if it's real, and stop giving it
away for free while we wait.*

---

## Ground truth you must NOT relitigate (evidence in DECISIONS.md / the entries)

- **The favorite edge is REAL and attack-hardened but NOT certified** (D16: +12.5% match-level,
  selection-null p=0.0000, 4/4 regimes+). The wall is OUT-of-sample persistence = COUNT of independent
  clusters (~4 days / ~2 tournament cycles), not the point estimate. Do not re-run the selection null
  or the truth audit; build ON them.
- **The game is the correlation unit; the per-game cap does NOT improve portfolio downside** (D20 →
  D21 correction). The Kelly FRACTION is the first-order risk lever (P0 flat-shares ~4× safer on CVaR
  than any ⅛-Kelly cap). **Do not re-open the sizing/game-cap debate** — WS-B pins the fraction, it
  does not re-litigate the cap.
- **The bot stakes one flat bet per `(strategy, condition_id, outcome_index)` row** (verified against
  the Rust in entry 19: `housekeeping.rs:163`, `consensus.rs:896`). Event clustering is stats-only,
  never sizing. Any P&L/CLV aggregation is at the position (row) grain, event-clustered only for the
  gate statistic.
- **flat-SHARES, never flat-$; skip longshots; ⅛-Kelly is the current ceiling and D21 says go LOWER.**
  P(profit)=100% on the record is the no-losing-slate artifact (D15), never a promise; every number is
  conditional on λ and carries the λ=0 costs-only line.
- **Reliability is supply-limited (D15/D17): 0/12 orthogonal edges.** Do NOT build a second strategy;
  `trust_weighted` is the only power-starved near-miss. This run does not add a partner edge.
- **Applied migrations are IMMUTABLE** (a comment edit ⇒ sqlx checksum crash-loops prod). Prefer NO
  migration: `signal_price_trajectory`, `consensus_signals.{initial_mean_price, mean_price,
  last_market_price, initial_market_price, resolved_at, last_updated_at}` already exist and carry
  everything CLV needs. If you TRULY need one, next free number only, additive, append-only.

## Non-negotiable guardrails

1. **Two — and only two — decisions are Tue's; STOP for each, do not auto-execute:**
   (i) flipping `favorite`/`elite_fresh_fav` alerts to fire LIVE (WS-C); (ii) committing REAL MONEY to
   the pilot (WS-D). Everything else is paper/shadow/proposal and you ship it without asking.
2. **Paper-only, additive, belief-blind.** No real money, no order placement, no alerting FLIP, no env
   flip, no auto-promotion, no change to the promotion gate (D7) or the null. New sizing / alert config
   / pilot harness are **built and PROPOSED**, wired behind a default-OFF flag, never armed.
3. **Reversibility.** Isolated git worktree off fresh `main`, new branch, tag the pre-run state. Other
   Claude sessions run in parallel — `git worktree list`, keep your file slice non-overlapping, smallest
   additive changes to shared files, say so when you must touch one. Never edit a file another chat has
   claimed; re-scope instead.
4. **Gate every commit:** `RUSTFLAGS="--cfg tokio_unstable -Dwarnings" cargo fmt --check --all &&
   cargo clippy --workspace --all-targets && cargo test --workspace`; Python = `python3 -m py_compile`
   + a self-test / synthetic-fixture smoke run. **Re-run the FULL gate on `main` AFTER you land** (main
   moves under you; the autoupdater ships whatever is on main).
5. **Deploys only via `scripts/consensus-autoupdate.sh`** (never manual `docker compose up`). The
   autoupdater rebuilds ONLY on a `common/|copy-trading-bot/|migrations/|Cargo.|Dockerfile.consensus|
   docker-compose.consensus.yml` diff; confirm your doc/script changes show "skipped rebuild."
6. **Cost-zero** (Max only, no `ANTHROPIC_API_KEY`, no child `claude` spawns).
7. **DB is read-only:** `docker exec -i polymarket-bot-postgres-1 psql -U bot -d polymarket --csv -q`.

---

## Pre-registration (write this into each entry BEFORE computing anything)

### WS-A — CLV / λ measurement (the marquee)
- **CLV definition (frozen).** Per resolved favorite position: `entry = initial_mean_price` (at-fire,
  D6). `close = ` the LAST price observed while the outcome was still UNCERTAIN — reconstruct from
  `signal_price_trajectory` as the latest trajectory point at or before `resolved_at` MINUS a guard
  window (e.g. the last point with price ∈ [0.02, 0.98], to exclude the degenerate near-0/1 print once
  the result is effectively known). Fall back to `last_market_price` / `mean_price` only when the
  trajectory is empty, and FLAG the fallback rate (a high fallback rate is a data-quality caveat, not a
  result). **CLV = close − entry** for a back. Report the trajectory-coverage % up front.
- **The three questions, each pre-registered with a null:**
  (1) *Is CLV > 0 on favorites?* Event-clustered mean CLV, with a **selection-matched null** (reuse
      `selection_null.py` machinery: random band×day-matched draws from `_blind`) — positive, p≤0.01 =
      the line reliably moves our way = independent evidence δ is real.
  (2) *Does CLV EXPLAIN the surplus?* Decompose realized surplus into a CLV-explained component (value
      we captured that the market later confirmed) and a residual (luck/variance). A high CLV-explained
      fraction ⇒ λ closer to 1.
  (3) *Data-driven λ estimate.* Translate mean CLV into a λ on the same scale as δ (e.g. λ̂ ≈
      clip(mean_CLV / δ, 0, 1) as a first-order read, plus a CI from the block/selection bootstrap).
      Report λ̂ with its honest CI — it will be WIDE on this record; the width is the finding.
- **Kill criteria.** K1 trajectory coverage < ~50% ⇒ CLV is fallback-dominated ⇒ report as
  INDETERMINATE-BY-DATA, not a λ. K2 CLV null p > 0.01 ⇒ no CLV evidence the edge is real ⇒ say so
  plainly (this would be a genuine negative — do not launder it). K3 the degenerate post-resolution
  price must be excluded; prove it in the self-test (a synthetic trajectory that spikes to 0.99 at
  resolution must NOT count as +CLV).

### WS-B — optimal de-lever fraction
- **Objective (frozen).** Sweep the Kelly multiplier `k ∈ {1/4, 1/6, 1/8, 1/12, 1/16, 1/24, 1/32}`
  (and flat-shares as the floor). For each, under the ADVERSE model (t-copula ν=4 + heterogeneous
  within-game correlation, `corr_risk_verify.py`), compute median growth/100, CVaR₅, p95/p99 maxDD,
  P(loss), across λ∈{1, 0.5, 0.25, 0}, multi-seed. **RECOMMENDED k = the one maximizing median growth ÷
  |CVaR₅| at λ=0.5 subject to P(maxDD>25%) ≤ 10% at λ=0.5** — the honest de-lever knee. Report the
  frontier; recommend the knee, not a corner.
- **Kill criteria.** K1 if the knee is flat-shares (k→0), say the honest answer is "don't Kelly-size at
  all yet." K2 report the number with its λ-sensitivity; if the knee flips across λ, the conservative
  (lowest-k) binds.

### WS-C — alert-leak fix (build + shadow + PROPOSE)
- Locate the alert path (the consensus cycle / notifier; `copy-trading-bot/src/cycles/consensus_cycle.rs`
  alert dedup at ~:384, and the strategy→alert config). Establish EXACTLY why `favorite`/`elite_fresh_fav`
  are silent while `strict` fires (the D12 config). Build the minimal change so the winners alert,
  **behind a default-OFF flag**. **Shadow-verify on the resolved record:** would the change have fired on
  the favorite/elite signals (the +EV ones) and NOT spam-fired (dedup intact, volume sane)? Quantify the
  realized-P&L the leak has cost (favorite/elite signals that fired no alert × their realizable edge).
- **Kill criteria.** K1 no live behavior changes until Tue flips the flag — the run PROPOSES with the
  shadow evidence and STOPS for the decision. K2 if enabling would spam (alert volume blows up), report
  the volume and gate the proposal on a rate-limit.

### WS-D — pilot harness (build + shadow; real money = Tue only)
- Stand up the pilot as a **default-OFF, paper-shadowed** module: de-levered sizing (WS-B's `k`), a tiny
  configured bankroll, and HARD kill-switches (per-day stop-loss, cumulative-drawdown halt, edge-
  degradation halt keyed on the CLV/persistence monitors, and a manual master switch). It must track CLV
  + honest realizable P&L per fill and reconcile paper-vs-would-be-real. **It places NOTHING** — the
  order-placement call is stubbed/guarded behind an `ARMED` flag that only Tue sets.
- **Kill criteria.** K1 the ARMED path is unreachable without an explicit env flag + Tue's go; prove it
  (a test that the module refuses to place with the flag unset). K2 shadow the harness on live-forward
  paper for the run's duration and report what it WOULD have done; no real order ever.

### Cross-cutting kill criteria
- **K-λ:** every profit/risk number in every WS carries the conditional-on-λ caveat and the λ=0 line;
  no "guaranteed"/"almost guaranteed" language. WS-A's whole job is to narrow λ, not to declare it 1.
- **K-scope:** if a workstream's honest result is negative (CLV null, knee = flat, leak fix would spam),
  that IS the deliverable — report it; do not force a positive.

---

## Phases (each ends gate-green + committed)

### Phase 0 — Setup & data reconnaissance (~30 min)
Worktree + branch + tag (`pre-edge-truth-<date>`). Read the companion docs. **Resolve the CLV data
question FIRST:** trajectory coverage %, the distribution of (close − entry), and the degenerate-price
guard — if coverage is too thin, WS-A pivots to the `last_market_price` proxy with the caveat stated.
Reproduce the current favorite record (≈231 positions / 80 games / WR ~0.935 / δ ~0.14). Confirm the
alert config location and the current strategy→alert wiring for WS-C.

### Phase 1 — WS-A: the CLV / λ instrument (marquee)
`scripts/clv_lambda.py` — house pattern (stdlib+numpy, docker-exec psql, seeded, verdict + JSON under
`reports/`, `--selftest`). Reconstructs CLV, runs the selection-matched null, decomposes surplus, emits
λ̂ + CI. Self-test MUST include the degenerate-price exclusion and a positive-CLV recovery fixture.
Populate the empty CLV monitor. Ship on PASS. Entry: `reports/entries/<date>-clv-lambda.md`.

### Phase 2 — WS-B: pin the de-lever fraction
Extend `corr_risk_verify.py` (or a sibling reusing it) with the k-sweep + the growth-÷-CVaR objective;
emit the frontier and the recommended `k`. Cross-check it against D18's ⅟₁₆ hint and D21's flat-shares
floor. Fold the pinned number into `REFINED-STRATEGY.md` rule 3 (as the proposed default, not applied).

### Phase 3 — WS-C: alert-leak fix (build + shadow + PROPOSE)
Implement the default-OFF winners-alert config; shadow-verify on the resolved record (fires on the right
signals, no spam); quantify the leak's realized-P&L cost. Gate green. **STOP and present the proposal +
evidence to Tue for the live-flip decision** (do not merge a live flip; merge only the OFF-by-default
scaffolding + the shadow report).

### Phase 4 — WS-D: pilot harness (build + shadow; unarmed)
Build the default-OFF, ARMED-gated pilot module with kill-switches + CLV/honest-P&L tracking; prove the
place path is unreachable without Tue's flag (a test). Shadow it forward on paper. **STOP and present the
harness + the go/no-go conditions to Tue for the real-money decision.**

### Phase 5 — Synthesis & ship
`DECISIONS.md += D22` (the CLV/λ read, the pinned de-lever k, the leak's cost + the proposed fix, the
unarmed pilot; what changed live = NOTHING). Update `REFINED-STRATEGY.md` where this run's evidence
sharpens it (the measured λ̂ replaces the assumed λ in the go/no-go; the de-lever k; the leak fix status).
Merge `--no-ff` to `main`; re-run the full gate on post-merge main; confirm the autoupdater logs "skipped
rebuild" for the doc/script parts (and a clean rebuild only if a genuinely code-level, Tue-approved change
landed — it should NOT this run). Final report to Tue: the **measured** λ̂ (with its wide CI) and what it
does to the profit/risk picture; the de-lever number; the leak's dollar cost + the one-approval fix; the
armed-only pilot; and the two decisions awaiting his yes/no.

---

## Rejected approaches (do not build)

- **Re-deriving the sizing / game-cap** — settled (D20/D21). WS-B pins the Kelly fraction; it does not
  re-open the cap.
- **Fitting λ or w_game on the benign record** — you cannot; WS-A MEASURES λ from CLV (forward-looking
  price movement), it does not fit it from outcomes.
- **Taking CLV at the degenerate post-resolution price** — the price → 0/1 once the result is known;
  that is not value, it is hindsight. Guard it and prove the guard in the self-test.
- **Flipping alerts live or placing real money** — the two Tue-only decisions. Build, shadow, propose,
  STOP. Never arm.
- **A second strategy / relational layer / per-cell threshold tuning** — supply-limited (D15/D17) and
  the overfit class (market_resid / entry-10). Not this run.
- **Treating a positive CLV as certification** — CLV is EVIDENCE that narrows λ, not the D7 gate.
  Persistence (independent-cluster count across ≥5 non-expiring regimes, months) still governs real
  money; CLV shortens the epistemic wait, it does not remove the gate.

## Acceptance

Gate-green commits; `scripts/clv_lambda.py` (PASSING self-test incl. the degenerate-price guard) with a
populated CLV monitor and a data-driven **λ̂ + honest CI**; the **pinned de-lever `k`** with its frontier;
the alert-leak **fix built OFF-by-default + shadow report + dollar cost** (live flip awaiting Tue); the
**unarmed pilot harness** with proven-unreachable place path (real money awaiting Tue); `DECISIONS.md`
D22; `REFINED-STRATEGY.md` updated to the MEASURED λ; merged + post-merge re-gated; live behavior
unchanged; nothing armed. The output is **the edge turned from an assumption into a measurement, sized
correctly, with the free realized-P&L leak stopped-pending-approval and a truth-generating pilot ready to
arm on Tue's word** — plus the honest statement of how wide λ̂ still is on this record.
