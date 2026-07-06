# FORGE DEBATES — Specialist Selection (slice-aware tailing)

Compressed record of the two designs per gap, the grep-verified reality-check findings, and the
forced-choice synthesis. Governing frame: DECISIONS.md **D2 / charter §0.5** — a per-SPORT
specialist book is **DEAD on current data** (0 capturable persistent specialists at every cut: sample
floor + thin capture margin + slate collapse, ~2 WC-soccer days) — and **eff⊂favorite / 0-of-12
strategies diversify favorite**. Every choice is shaped by those two adversaries: build measurement +
an inert, forward-gated mechanism; promote nothing until a forward gate clears AND Tue approves.
Scarce resource = statistical power (distinct-event N/cell) + multiplicity budget (Bonferroni across
arms AND wallets×cells) + forward calendar-weeks. No dollars, no tokens.

## Reality-check findings (every symbol opened against `~/polymarket-bot`, not copied)

Confirmed with the claimed shape:
- `score_market` base match @ `consensus.rs:474-482`; `WeightMode{Count,Quality,Dollars,TrustWeighted}`
  @ `:121`; `TrustWeighted => backers.values().map(|v| v.earned_quality).sum()` @ `:481`. **All four
  modes wallet-level; none consults the market's cell.**
- `earned_quality(trust, wallet, rank) -> (f64,bool,bool)` @ `consensus_cycle.rs:69`; `Some` arm
  returns `(earned, certified, certified)` with `damp = n/(n+20)`; `None ⇒ (qw, true, false)` @ `:83`.
  Signature carries NO sport. The comment @ `:67` literally blesses the pooling seam: *"Shrink-toward-0
  lives HERE (regularizing the continuous multiplier), never at the verdict."*
- `trader_slice_scores` @ `consensus.rs:1459` and `_asof` @ `:1526`: **`blind AS (SELECT band, AVG(a)
  … GROUP BY band)`** in BOTH (`:1470`, `:1527`) — the baseline is 1-D on band. `tagged` emits
  `overall|sport|band[+recency live-only]`. `_asof` adds `resolved_at < $1` and drops recency.
- `TraderSliceStat` @ `common consensus.rs:1855` — FromRow column order load-bearing; new axes must be
  new `slice_kind`/`slice_key` VALUES.
- `surplus_bounds(distinct_events, surplus, surplus_sd: Option<f64>, n_comparisons, p)` @
  `promotion.rs:281`: `alpha_corr = alpha/n_comparisons`, `z = probit(1−alpha_corr)`, `se =
  sd/√distinct_events`. `probit` @ `:33` is **private** (`fn probit`, no `pub`).
- `PromotionParams::default{min_events:30, margin:DEFAULT_PROMOTION_MARGIN, alpha:0.05}` @ `:105-118`.
- `trust_verdict` @ `trader_trust.rs:118` → `trust_verdict_with(slices, &PromotionParams::default())`;
  `n_comparisons = slices.filter(surplus.is_some()).count().max(1)` @ `:129`; `eff_n =
  o.n_days.clamp(1, o.n_events.max(1))` @ `:179` — **day-deflated**; `Trusted=lo>margin`, `Avoid=hi<0`.
- `honest.rs::pilot_verdict` @ `:90` builds `PromotionParams{min_events:th.min_events(50), margin:
  min_pilot_roi, alpha}` @ `:100-104` then `surplus_bounds(inp.distinct_events, honest_roi,
  inp.honest_roi_sd, inp.n_family, …)` @ `:105-109` — **passes EVENT-N** (D16-a split). `PilotThresholds
  {min_pilot_roi:0.02, min_events:50, min_regimes:5, …}` @ `:41-56`.
- `family()` @ **`copy-trading-bot/src/scanner/enrich/mod.rs:338`** (NOT `enrich/mod.rs` — both designs
  drop the `scanner/` prefix); `EXPERIMENTAL` const @ `:339-352` lists `consensus_ens … trust_weighted,
  trusted_only, cross_cohort, strict_retuned, sharp_tail_fresh, sharp_tail` — **no slice arm, no
  favorite/elite_fresh_fav**; defaults unknown → `"core"` @ `:356`; test `family_splits_experimental_from_core`
  @ `:365`.
- migrations: `036_initial_atfire_shape.sql` latest → **037 next free** (confirmed `ls migrations/`).
  `wt/*` worktrees carry their OWN `migrations/` and `enrich/mod.rs` — collision risk is real.
- `earned.rs`: `deep_sharp_pass` @ `:46`, `promotable_deep_sharps` filters `Trusted` @ `:75-77`.
- `compute_trust_map` @ `consensus_cycle.rs:95`; `books_from_window_votes` @ `:522`, call site
  `(eq,trusted,certified)=earned_quality(...)` @ `:537`, set on vote @ `:547`; `active_portfolio`
  guard `cfg.consensus_trust_arms` @ `:859`.
- Scripts present: `bh_fdr` @ `slice_study.py:197`; `selection_null.py` (`N_PERM=2000`,
  `null_pvalue`/`clustered_surplus`); `edge_orthogonality.py`, `portfolio_constructor.py`,
  `persistence_tracker.py`.

**Findings that shaped the synthesis (the adversarial ones):**

- **F1 · incomplete (both designs).** `family()` is at `scanner/enrich/mod.rs:338`, not
  `enrich/mod.rs:338`. Blueprint cites the correct path; the EXPERIMENTAL const must gain
  `"slice_sport_tail"` or the arm silently lands in `strict`'s core Bonferroni family.
- **F2 · verified-safe (Design B GAP-1, the crux).** B's K_POOL is a **fixed config const**, not a
  fitted quantity ⇒ **leak-free**. A fitted K would be a hidden search that re-inflates the family. B
  correctly keeps K fixed and defines permutation "picks" by a deterministic pre-registered ε rule ⇒
  the "no cell selection → live family size 1" claim genuinely holds. This is the load-bearing check
  the prompt flagged, and it passes.
- **F3 · weak → binding (Design B GAP-5 over-claim).** B claims the cell-blind (GAP-2) makes
  `edge_orthogonality.py`'s **G2 largely pre-satisfied**, collapsing G1∧G2∧G3 to a thin confirmatory
  check. Half-right and dangerous: the cell-blind removes the **MEAN** favorite artifact within
  `(sport,band)` but NOT the event-level **covariance/overlap** with `favorite` — and `eff⊂favorite`
  / 0-of-12 is a covariance/independent-VOLUME finding, which B concedes in its own Trade-offs. The
  full gate MUST stay binding.
- **F4 · broken (Design B GAP-2 fallback).** B's `surp` uses `COALESCE(blind_edge, 0)` — an empty
  `(sport×subtype×band)` blind cell → surplus = raw advantage (no neutralization) → favorite-in-disguise
  leaks back exactly where the baseline is thinnest. Design A's cascade `COALESCE(blind_cell,
  blind_band, 0)` degrades to the incumbent per-band FLB neutralizer and never fails open. A wins this
  sub-point decisively.
- **F5 · incomplete (both GAP-6).** `PilotInputs` (`honest.rs:21`) has NO `distinct_days` field. GAP-6
  therefore requires ADDING `pub distinct_days: i64` + populating it at the construction site — a real
  (small) struct change, not a one-liner. Verified: day-deflation only LOWERS pilot N ⇒ wider CI ⇒
  stricter GO (the prompt's "honest.rs:105 unification only makes the pilot stricter" claim is TRUE).
- **F6 · weak (Design B GAP-7 coupling).** `earned_eligible` is a boolean admitting a wallet to the
  voter set broadly; earning "for soccer" but voting everywhere is safe only if the consuming arm uses
  the pooled per-cell weight. Must gate the cell-earn on `slice_pooled` on + the forward-flip, else
  weak-sport votes leak at full weight.
- **F7 · verified (both GAP-3).** `TrustParams{25}` split from `PromotionParams` with `honest.rs:100`
  untouched is correct and identical in both designs; a 25-event hairline still reads Indeterminate.

## Per-gap: both designs, verdict, synthesis

### GAP-1 — score weights wallet-level, not per-(wallet×cell) [the named task]
- **Direct (A):** hard cell-verdict switch into a `slice_earned_quality` sibling — cell Trusted ⇒
  up-weight, Avoid ⇒ down-weight, Indeterminate/absent ⇒ overall; one axis (sport), fail-closed; two
  new vote fields + `SliceTrustWeighted` mode.
- **Rethink (B):** continuous partial-pooling of the multiplier toward the overall by `N/(N+K)`, K
  fixed; no selection event; thin cells borrow strength from the parent; one new vote field +
  `CellPooled` mode.
- **Verdict — RETHINK (pooled), REFINED.** The old FORGE_DEBATES rejected Rethink's shrinkage for three
  reasons — needs `probit` public, adds a DL/τ² EB estimator, buys only continuity. B avoids all three
  (F2): pooling is arithmetic on `lo/hi` already returned; K is a fixed const (same pattern as the
  shipped `damp=n/(n+20)`); and its real benefit is not continuity but **thin-cells-borrow-strength**,
  the direct structural answer to the congregation sub-30-discard death. B is also strictly
  lower-multiplicity — no argmax ⇒ live family size 1 (§GAP-4). We keep it minimal (one vote field,
  fixed K) and, per the prompt's BAR, require the forward test (GAP-5) to show pooling adds edge over
  BOTH favorite-only AND global `trust_weighted`. Adopt A's fail-closed clarity for the N=0/Indeterminate
  ladder. The hybrid seam (B's pooled picks → A's forward gate) is sound: pooled "picks" are
  deterministically defined (|Δweight|>ε), which the gate judges — no seam conflict.

### GAP-2 — bet_type axis + cell-blind baseline (favorite-in-disguise neutralizer)
- **Direct (A):** bettype axis (mig 037) + `(sport,band)` blind with cascade
  `COALESCE(blind_cell, blind_band, 0)`; defer subtype in the blind until a subtype specialist survives.
- **Rethink (B):** frames the per-cell blind as a **favorite-residual** (blinding within band subtracts
  favorite-loading at the verdict — the sharpest insight in either design), keyed `(sport,subtype,band)`,
  fallback `COALESCE(blind_edge, 0)`.
- **Verdict — REFINED (B's framing + A's fallback).** B's favorite-residual framing is *why* the
  baseline defeats the congregation leak and is adopted verbatim as the anti-"favorite-in-disguise"
  mechanism. But B's `COALESCE(...,0)` fails open on thin blind cells (F4) — replaced by A's cascade,
  which preserves the per-band FLB neutralizer as the floor (a hard preservation requirement). Ship the
  blind at `(sport,band)`; stage subtype into the blind post-Item-5. bettype axis = ADOPT-AS-IS
  (both agree, old plan Item 2).

### GAP-3 — 30→25 floor as a `TrustParams` isolated from `PilotThresholds`
- **Direct (A) = Rethink (B):** identical — a named `TrustParams{min_events:25}` with an
  `into_promotion()` adapter; `honest.rs:100` untouched; 25-event hairline still Indeterminate.
- **Verdict — DIRECT (= both).** Adopt as-is. The only way to drop the trust floor without a
  spooky-action regression of the real-money pilot bar (F7). Regression test asserts the two floors are
  independent.

### GAP-4 — multiplicity-at-scale (78 wallets × cells × arms)
- **Direct (A):** three layers — L1 live one-cell-per-vote (per-wallet Bonferroni), L2 `bh_fdr` +
  ×-wallet Bonferroni screen (non-binding), L3 forward `(cell×day)` label-permutation (binding, family
  size 1).
- **Rethink (B):** same three layers, but pooling **dissolves the live cell-family entirely** (no
  selection ⇒ nothing to correct at L1) — stronger than A's "one cell per vote," which still selects.
- **Verdict — HYBRID (B's dissolution + A's forward-permutation binding + explicit ×-wallet screen).**
  B's dissolution is real *only because* K is fixed and pick-membership is a deterministic ε rule (F2)
  — verified, not accepted on B's say-so. Adopt A's L2 screen with the explicit ×-wallet Bonferroni
  denominator (the NEW-DELTA refinement the old plan left as "watchlist only") and A's L3 forward
  permutation as the binding control. The cell-blind residual baseline is a fitted quantity and is
  leak-free ONLY because L3 computes it inside `trader_slice_scores_asof` — enforced.

### GAP-5 — orthogonality/integration vs favorite (must add INDEPENDENT edge)
- **Direct (A):** full G1∧G2∧G3 (`edge_orthogonality.py`) on `S_only` picks + `portfolio_constructor.py`
  marginal-LB BAR; a favorite-relabel arm fails G1.
- **Rethink (B):** COLLAPSE — the cell-blind pre-satisfies G2, leaving a thin forward G1/G3 confirm.
- **Verdict — REFINED, leaning DIRECT (challenges the prompt's prior).** The prompt's prior favored
  anchoring GAP-5 on B's residual baseline. B's baseline genuinely *helps* (removes the mean artifact,
  makes G2 reachable) and is adopted as a **pre-filter**. But B's *collapse* under-armors the
  covariance/independent-volume dimension that is exactly what killed `elite_fresh_fav` and produced
  0-of-12 (F3). So the full forward G1∧G2∧G3 + `portfolio_constructor` marginal-LB stays the BINDING
  BAR — and the marginal test must beat BOTH `favorite`-only AND global `trust_weighted` (the prompt's
  explicit requirement, since a pooled weighting could reproduce `trust_weighted` on favorite events).
  This is the one place the synthesis overrides the stated prior, and the prompt itself endorses it
  ("keep that BAR").

### GAP-6 — D16-a SE-convention split (day-deflated vs event-N)
- **Direct (A) = Rethink (B):** unify to day-deflated everywhere — change `honest.rs:105` to pass
  `distinct_days.clamp(1, distinct_events)`; B adds that pooling is SE-convention-agnostic (reads
  already-day-deflated `lo/hi`).
- **Verdict — DIRECT (= both).** Adopt. Verified prerequisite (F5): `PilotInputs` has no `distinct_days`
  — must add + populate. Monotone-safe: day-deflation only makes the pilot stricter. Ship before any GO,
  not before building Items 1–5. `strict` never calls `pilot_verdict`.

### GAP-7 — the "0 earned_eligible" puzzle
- **Direct (A):** diagnose (query) + `promotable_deep_sharps_cell` keeping a wallet if any sport cell is
  Trusted, cell-scoped earn.
- **Rethink (B):** same one-predicate change, framed as the gap dissolving once GAP-1/2/3 land.
- **Verdict — HYBRID.** Diagnose first (read-only; the honest outcome may be "genuinely nobody"). The
  fix rides GAP-1/2/3 but MUST be gated on the Item 4 L3 forward-flip (never in-sample cells — the
  congregation defense) AND on `slice_pooled` being on (F6, the coupling caveat) so a cell-earned
  wallet's weak-sport votes are pooling-down-weighted, not leaked at full weight.

## Key insights that emerged

- **The DEAD premise still governs — but the terrain moved.** Congregation died on a 1-D band-blind +
  a 30-event floor + a 2-day slate. Three of those four are now different: the archive is real
  (2022→2026, 78 wallets ≥30ev), the baseline is a favorite-residual (GAP-2), and thin cells borrow
  strength instead of being discarded (GAP-1 pooling). The fourth — forward slate diversity — is still
  thin, so the binding control stays forward cross-window persistence (GAP-4 L3), and today's honest
  answer is PENDING.
- **Pooling beats the hard switch on the congregation axis specifically.** The switch reproduces the
  death (discard thin cells) or its opposite failure (let a thin cell swing a vote on a correlated
  slate). Continuous pooling with fixed K is the only option that both reaches a specialist and tempers
  a thin/correlated cell toward the parent — and it removes the live multiplicity search by
  construction.
- **The cell-blind defeats favorite-in-disguise at the MEAN, not the covariance.** This is the sharpest
  correction to Rethink: the residual baseline is necessary but not sufficient against eff⊂favorite.
  The independent-volume/covariance dimension (0-of-12) needs the full forward orthogonality gate,
  which the per-sport book never ran. Keeping that gate binding is what makes "this isn't
  congregation-2" true forward, not just in-sample.
- **Every fitted quantity is asof-gated.** The cell-blind residual, the per-cell verdicts feeding the
  earn, and the permutation surplus are all computed via `trader_slice_scores_asof` for any forward
  claim; K and ε are fixed pre-registered consts. A fitted K or a live-blind forward claim would be the
  leak — both are closed.
- **The binding budget is false-promotion risk, paid in forward-weeks.** Item 1 widens profiling
  reach but tightens the CI; Item 2 re-measures history conservatively; Item 3 is one experimental
  hypothesis; Item 4 L3 and Item 5 are family size 1; Item 6 only makes the pilot stricter. Nothing in
  the plan can false-promote, and real money stays gated on the unchanged pilot bar (N≥50, ≥5 regimes)
  plus the forward orthogonality BAR plus Tue.
