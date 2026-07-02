# Reliability-first portfolio — one honest effective-N, an orthogonality gate, and the book (2026-07-02, entry 14)

Branch `feat/reliability-portfolio` (worktree off `main` 210b745, tag
`pre-reliability-portfolio-20260702`). Paper-only, read-only on live behavior, **zero
migrations**, nothing promoted, no env/alert change. Builds directly on the diversification &
risk run (entry 12 / D15) and the truth audit (entry 13 / D16). Three new self-testing
instruments, each reusing the gate's machinery byte-identically:

- `scripts/effective_n.py` — reconciles the two Rust SE conventions the truth audit found
  disagreeing (D16-a/E-1). Reuses `rekey_headline` (the validated `surplus_bounds` mirror) +
  `portfolio_concentration` (ICC / N_eff).
- `scripts/edge_orthogonality.py` — a belief-blind gate: is there a SECOND edge in the
  already-captured stream that actually *diversifies* favorite? Reuses `selection_null`.
- `scripts/portfolio_constructor.py` — composes the above + `risk_engine` into the
  reliability-optimal book, and prices what is missing.

## The mission, honestly stated

The owner asked to optimize BOTH reliability (diversification, open to other levers) and
profitability. The honest translation this run delivers: **reliability is not something you can
allocate into existence** (D15). So this run (1) fixes the load-bearing "when can we bet"
number the truth audit left unreconciled, (2) tests rigorously whether any second edge exists
to diversify into, and (3) emits the most reliable profitable book the data actually supports
today — with every conditional stated. Sizing sizes an edge; it does not create one.

---

## Pillar 1 — effective-N reconciliation: board.rs gets the right answer via a misleading mechanism

**The disagreement (D16-a).** `board.rs`/`promotion_verdict` deflates the surplus SE to
distinct **event-DAYS** (`effective_n = clamp(distinct_days,1,events)` — Moulton, assumes
within-day ICC = 1); `honest.rs`/`surplus_bounds` uses **event-N** (assumes ICC = 0). For
favorite these are the two extreme endpoints of one design-effect formula. `effective_n.py`
introduces the cluster-robust estimator `n_eff_CR = sd²/V_CR`, self-test-proven to span them
exactly (→ event-N at ICC 0, → #clusters at ICC 1, → analytic value at known ρ).

**The finding.** The single day-deflated SE conflates two different questions:

| question | favorite (match-level clustering) | verdict |
|---|---|---|
| **Q1 — within-sample precision** of the +12.4% surplus | measured within-day ICC = **0.007 ≈ 0** ⇒ events ~independent in-sample ⇒ event-N LB **+4.6%** ≈ cluster-robust LB +3.9% > 3% | board.rs's day-N **−20.3%** is a FALSIFIED-mechanism artifact; the surplus is well pinned down |
| **Q2 — out-of-sample persistence** (does it hold in a tournament we have NOT seen) | **NOT a within-sample SE.** Encoding persistence as one is grain-arbitrary: small-cluster t LB = **−8% at day grain (G=4)** vs **+4.5% at tournament grain (G=6)** — the answer flips on an arbitrary grain | the binding wall is the **COUNT of independent clusters** (~4 days / ~2 tournament cycles), which caps the d.o.f. of ANY robust CI |

The point estimate is strong and consistent — favorite is individually positive in **4 of 4
disjoint regimes** (tennis +11.4%, soccer +6.9%, mlb +22.6%, other +15.7%). So the honest
status is **promising but unproven**: real edge, well-estimated in-sample, blocked by too few
independent regime-blocks to establish generalization. board.rs reaches the right conclusion
(hold) but via a mechanism (ICC=1 → "edge looks statistically dead at −20%") that misreads a
strong near-independent edge; honest.rs's event-N ignores Q2 entirely.

> **Self-caught overclaim (recorded for honesty).** An intermediate version of this pillar
> presented the −8% day-grain small-cluster-t LB as "the honest CI" and concluded the surplus
> cleared 3%. That committed the SAME misleading-mechanism sin as board.rs (it used the gate's
> normal z, hiding the small-cluster degrees of freedom). Corrected above: within-sample
> precision and out-of-sample persistence are different questions and must not share one SE.

**Reconciled convention (PROPOSED, not applied to live Rust — paper-only, Tue's call):**
(a) compute the surplus within-sample LB from the cluster-robust SE at the **measured** ICC
(≈ event-N here) — drop the ICC=1 √days deflation entirely; (b) make the BINDING certification
gate an **explicit independent-cluster-COUNT / persistence floor** (≥K disjoint day/regime
blocks), which no SE re-derivation can shortcut. This makes board.rs and honest.rs agree and
stops the board reading a real edge as "dead."

## Pillar 2 — orthogonality gate: is there a SECOND edge that diversifies favorite?

D15 proved reliability is *supply-limited, not allocation-limited*. `edge_orthogonality.py`
makes that testable rather than asserted. A candidate strategy `S` diversifies favorite iff:

- **G1** it fires on ≥10 events favorite does NOT (independent volume — a nested strategy adds 0);
- **G2** the diversifying picks THEMSELVES carry edge (selection-null p ≤ 0.01/`n_candidates`
  Bonferroni, positive);
- **G3** they are independent of favorite (shared-event residual |r| ≤ 0.3 two-sided; disjoint-
  event regime-shock r ≤ 0.5 one-sided — a *negative* shock correlation is a hedge and passes).

Self-test proves it: an injected orthogonal edge PASSES; a nested decoy fails G1; a losing-
residue decoy fails G2; a positive-shock decoy fails G3 *as the deciding gate*; a negative-shock
+edge hedge passes all.

**Live verdict: 0 of 12 candidates diversify favorite.**

| class | candidates | why not |
|---|---|---|
| broad consensus | strict, count, sports_only, whales, elite_gated, fresh2h, loose | add independent VOLUME (52–78%) but the orthogonal component is the reliably-**losing** non-favorite residue (orth surplus ≈ −0.9%, **G2 fail**) AND co-moves with favorite (r_shared +0.5..0.64, **G3 fail**) |
| nested | elite_fresh_fav | 100% ⊂ favorite → 0 independent events (**G1 fail**) |
| power-starved watch-items | trust_weighted, longshot, tight_cluster | positive orthogonal point estimate but not selection-significant at Bonferroni (**G2 fail**) |

**Standout: `trust_weighted`** (consensus-ladder L3, per REFINED-STRATEGY's "frontier").
It PASSES independence — orthogonal surplus **+4.7%**, r_shared **−0.05**, regime-shock **−0.76**
(a genuine hedge) — and fails ONLY G2 (p≈0.24 vs Bonferroni 0.0008, N=46). This is the exact
"data-starved frontier" the strategy doc flagged: the leading orthogonal-edge candidate, not yet
certifiable. The gate will certify it the instant its edge clears the bar.

## Pillar 3 — the reliability-first book, and the price of what is missing

`portfolio_constructor.py` composes the gate (menu = anchor + orthogonality-certified
diversifiers, built from data not hardcoded), dedups, sizes by the risk engine's frozen rule,
and prices independence.

- **STEP 1 dedup:** BOOK = **[favorite]** only. elite_fresh_fav adds 0 independent bets → dropped
  (never double-count). 0 orthogonality-certified partners → nothing to add.
- **STEP 2–3 sizing:** `kelly_eighth_capped` (⅛-Kelly per band, SE-shrunk — bands 4:0.03, 5:0.58;
  losing bands auto-zeroed — with ≤1/event, ≤3/slate, ≤40%/regime, −5-unit daily-stop caps).
  All horizons are labelled **EXTRAPOLATION beyond n_eff ≈ 59** (K1) — the honest P(profit)/P(maxDD)
  cells are reported but H=1000 is not to be leaned on.
- **STEP 4 — a second edge's worth, priced two honest ways:** (a) *decorrelating fixed volume*
  buys ≈ 0 (favorite's within-slate corr ≈ 0; and P(loss)=0% is the D15 no-losing-slate artifact,
  uninformative). (b) *adding* independent volume shrinks the combined per-bet SE by √((Na+Nb)/Na)
  — THIS is where a second edge pays: **volume + continuity** (betting through post-WC supply
  droughts) **+ insurance** (if favorite's edge degrades). Not per-bet variance reduction.

**Pre-registered book for the hypothetical GO day** (still gated on D7 + persistence accrual +
Tue): favorite only, `kelly_eighth_capped`, quarter-Kelly unlocked only once an adverse regime
accrues and the DD ceiling can bind. Re-run triggers: post-WC + post-Wimbledon; +50 favorite /
+300 fleet events; any `edge_orthogonality` candidate reaching G1∧G2∧G3; MANDATORY before any
real-money pilot.

---

## What optimized both axes (the owner's ask, answered with numbers)

- **Reliability.** (1) Corrected the effective-N so the binding wall is named honestly
  (independent-cluster count / persistence, ~4 blocks), not a misleading −20% that hides a real
  edge. (2) Proved — not asserted — that no orthogonal second edge exists to diversify into today
  (0/12), so reliability accrues only with forward time + new uncorrelated SUPPLY (the sibling
  breadth run's lane) or a matured `trust_weighted`. (3) The structural caps bound drawdown by
  construction regardless of the (unpriceable) adverse-regime distribution.
- **Profitability.** Confirmed `kelly_eighth_capped` as the reliability-optimal sizing of the one
  real edge (no change to the D15 recommendation — the constructor re-derived it), with the honest
  P(profit) conditional-on-edge, and identified `trust_weighted` as the highest-value profitability
  *lever to watch* (an orthogonal edge would add +EV volume that favorite's thinning post-WC supply
  cannot).

## Kill criteria honored

- **K1** (n_eff < ~40 ⇒ H=1000 is extrapolation): favorite n_eff_CR ≈ 59; H=1000 labelled
  extrapolation in the constructor, leaned on H=100/300.
- **K2** (grain sensitivity ⇒ conservative binds): the day-vs-tournament persistence-LB swing IS
  the headline of Pillar 1; the conservative (fewest-cluster) grain governs → hold.
- **K3** (no "guaranteed" language): every P(profit) cell carries the conditional-on-edge caveat;
  the zero-edge line stands.
- **K4** (nothing changes live behavior): confirmed — instruments + docs + a *proposed* (not
  applied) SE convention only.

## What was NOT done / limitations

- The Rust SE reconciliation is **proposed, not applied** (crosses `board.rs`/`honest.rs`;
  changes what the board and pilot gate would say; house rule = Tue's explicit go).
- The orthogonality gate's shock leg only sees co-movement WITHIN shared (regime×day) slates; a
  market-wide cross-regime day shock is invisible (acceptable under the "orthogonal regime" frame).
- Every number inherits the 4-day, ~2-tournament-cycle record. The constructor's P(profit) is
  conditional on favorite's edge being real and persisting — D7's job, not this run's.

## Rollback

`git revert` the merge of `feat/reliability-portfolio`; delete `reports/{effective_n,
edge_orthogonality,portfolio_constructor}.json`. No migrations, no env, no live behavior touched.
