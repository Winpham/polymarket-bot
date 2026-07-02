# Long Autonomous Run — TRUTH AUDIT: try to kill the edge before money does

Paste this whole file as the task for a fresh long-running session. **Self-contained.**
Work in `~/polymarket-bot` (Rust; deploy branch `main`, auto-deploys ~5 min after merges).
Companion ground truth: `DECISIONS.md` (D1–D12), `REPORT.md`, `REFINED-STRATEGY.md`,
`scripts/{selection_null,scoreboard_parity,decay_analysis}.py`, `DATA-MODEL.md`.

---

## 0. The one-sentence mission

The consensus-favorite edge (`favorite` +10.7% surplus N=95, `elite_fresh_fav` +9.2% N=39,
both selection-null p<0.0005, green every day, realizable at measured costs) **looks too good
to be true — so your job is to BREAK it.** Attack every mechanism by which it could be fake,
quantify every gap a skeptical co-engineer raised, and report what survives. You are
rewarded for finding real flaws, not for green tables. **A refuted edge, correctly
established, is a successful run. A confirmed edge that survived genuine attack is worth
real money. A soft audit is worth nothing.**

## The specific doubts this run exists to answer (from Tue's co-engineer — treat each as a
pre-registered attack, numbered A–F)

- **A. "Do these Polymarket sharps ever cash out early?"** We copy their ENTRIES and hold to
  resolution — but `trader_fills` captures BOTH sides (400k+ resolved fills, BUY and SELL,
  timestamped). If backers systematically exit before resolution, (1) our hold-to-resolution
  payoff is a DIFFERENT bet than theirs — measure whose is better; (2) an early exit may be
  INFORMATION (they learned something) — measure whether a backer's pre-resolution SELL on a
  consensus market predicts our held position's failure. If it does, an exit-follow rule is
  a nomination (silent, gated); if it doesn't, holding is vindicated. Either answer is gold.
- **B. "The bot polls every minute — how much edge dies in that window?"** The vote atoms
  (`observed_votes`) carry each backer's FILL timestamp; `first_detected_at` is our
  detection. Reconstruct the fill→detection latency distribution per signal; regress
  within-signal outcome-advantage against detection latency (event-clustered, at-fire);
  reconcile with the measured structural tax (+2.1¢ favorite / +1.3¢ eff) and the decay
  curve (no loss <30 min AFTER detection). Answer: how much edge is lost BEFORE detection,
  is faster polling worth anything, and does latency-sensitivity threaten the live edge?
- **C. "Are there gaps in the record?"** There is no backtest by design (forward-only), so
  the honest version of this question is CAPTURE COMPLETENESS: quantify polling downtime
  (laptop asleep → cycle gaps in `consensus_signals.last_updated_at` / cycle logs /
  `capture gaps` counters), 429 losses, page-overflow gaps (`record_capture`), and the
  windows where signals COULD have fired but the bot wasn't looking. Then answer the bias
  question: is missingness plausibly correlated with outcomes (e.g. bot down overnight =
  specific slates missed), or does it only cost frequency? Show the daily capture-coverage
  timeline next to the daily P&L.
- **D. "Is the grading actually right?"** Independently re-verify a random sample of ≥50
  graded signals (stratified: wins/losses/each sport, both winners' picks oversampled)
  against a SECOND source (Gamma API `outcomePrices` / market pages), plus every signal
  where the two winners DISAGREED with the blind majority. Any grading mismatch is a
  first-order bug — report each with its condition_id.
- **E. "Is N inflated by correlated markets?"** Event-clustering keys on `event_slug` — but
  one real-world match can span MULTIPLE event_slugs (game winner, O/U, exact-score, props).
  Build a match-level super-key (slug prefix + date + team/player tokens), measure how many
  "distinct events" collapse, and RECOMPUTE the headline z/LB at match-level clustering.
  If favorite's z=3.9 becomes z=1.5 at honest clustering, say so loudly.
- **F. "Too good to be true" — the adversarial battery.** Pre-registered attacks, all must
  be run and reported whether they kill or clear:
  1. **Anti-consensus mirror**: bet AGAINST the winners' picks at the same at-fire prices —
     must show ≈ −(surplus) (symmetry check; a data artifact often breaks symmetry).
  2. **Time-shifted placebo**: assign each pick the outcome of a random same-band,
     same-day, same-regime blind market — must read ≈ 0 (the selection-null already does a
     version of this; run it at match-level clustering from E).
  3. **Split-half persistence**: first half of the record (by time) vs second half —
     pre-registered: BOTH halves positive at match-level clustering, or flag temporal
     fragility.
  4. **Odd/even event holdout**: fit nothing, just verify both disjoint halves are positive
     (a cheap independence check).
  5. **Book-vs-outcome sanity**: for 20 sampled wins, confirm the market actually traded
     near our at-fire price AFTER detection (the fill was gettable) — kills any
     "phantom price" story.

## Ground truth you must NOT relitigate (evidence in DECISIONS.md; re-verify, don't re-argue)

At-fire entry is the judged statistic (D6); the D7 rule (gate LB>3% ∧ null p≤0.01 ∧ ≥2
regimes) is the promotion bar; the wide ≥0.65 pool is −EV after costs (gates are
load-bearing); flat-shares sizing; no decay <30 min post-detection; measured haircut 0.5¢;
market_resid refuted; blind-tail loses; event-cluster ALWAYS (though E upgrades the key);
survivorship in realizable ROI biases AGAINST us (measured: excluded favorite rows were 100%
winners). The winners were pre-registered 2026-06-29 ~10:07 before the record accrued.

## Non-negotiable guardrails

1. Isolated git worktree off `main`, fresh branch, tag first. Other sessions run in
   parallel — check `git worktree list`, non-overlapping slice, smallest additive change to
   any shared file. **Applied migrations are IMMUTABLE** (sqlx checksum crash-loop; happened
   once already). This run needs NO migration and NO behavior change: analysis scripts +
   docs + at most ONE silent nomination if A justifies it.
2. Gate every commit: `RUSTFLAGS="--cfg tokio_unstable -Dwarnings" cargo fmt --check --all
   && cargo clippy --workspace --all-targets && cargo test --workspace`; Python:
   `py_compile` + synthetic-fixture self-test for every new instrument (house rule: an
   instrument ships only with a PASSING self-test that recovers an injected effect AND
   reads flat on a null fixture). **Re-run the full gate on post-merge main** before the
   auto-deployer ships it.
3. Paper-only; no env flips on the live bot (propose, don't apply); deploys only via
   `scripts/consensus-autoupdate.sh`; cost-zero (no API keys, no child claudes).
4. **Report every attack's result, especially the ugly ones.** If a number moved against
   us, it leads the report. No attack may be silently dropped for being inconvenient.

## Pre-registration (fix BEFORE computing)

- Populations: `favorite`, `elite_fresh_fav`, and (for A/B) their union's backer set.
- All statistics event-clustered at BOTH keys: `event_slug` (incumbent) and the E
  super-key (match-level); headline conclusions use the STRICTER (match-level) key.
- Floors: no verdict from N<20 events; sub-splits below floor read INDETERMINATE.
- Multiplicity: the attacks are confirmatory (pre-registered, one-shot each) — report raw
  p's; the A exit-follow nomination (if any) enters the experimental Bonferroni family.
- Kill criteria (binding): K1 grading mismatches >1% of sample ⇒ STOP, fix grading, all
  downstream numbers are void until re-run. K2 match-level clustering drops favorite's
  surplus LB below the 3% capture margin ⇒ the D7 eligibility is REVOKED in the report and
  the accrual clock restarts at the stricter key. K3 anti-consensus mirror or placebo
  fails symmetry/flatness ⇒ there is a data artifact — finding it becomes the run's sole
  priority. K4 split-half shows sign flip ⇒ edge is temporal-fragile: say so, downgrade to
  indeterminate, define the re-read trigger.

## Phases (each gate-green + committed; report incrementally in the run report)

### Phase 0 — Setup + reproduce (~30 min)
Worktree, branch, tag. Reproduce the two winners' headline numbers on the live DB within
noise (if not: stop, diagnose). Print record shape (events/day, per regime, per strategy).

### Phase 1 — E first (it re-keys everything): match-level super-key
Build the super-key (document the token rules; measure collapse rate: how many event_slugs
per super-event, worst offenders listed). Recompute BOTH winners' surplus/sd/N/LB/z and the
selection-null at match-level clustering. This is the single most likely place the story
changes — do it before anything else so later phases inherit the honest key.

### Phase 2 — D: independent grading verification
The ≥50-signal stratified re-grade vs Gamma + the winners-vs-blind-majority disagreement
set. Report mismatch rate; K1 binds.

### Phase 3 — A: the cash-out study (`scripts/exit_study.py`, self-testing)
From `trader_fills` (both sides): per consensus signal of the two winners, for each backer
in the atoms — did that wallet SELL the same (condition, outcome) before resolution? Metrics:
(1) fraction of backers exiting early, by time-to-resolution decile and by profit-at-exit
sign; (2) OUR held-position outcome conditional on {no exits, some exits, majority exited}
(event-clustered, matched-baseline); (3) counterfactual P&L: hold-to-resolution (ours) vs
mirror-their-exits (sell when each backer sells, at the then-captured mid/snapshot price —
mark clearly where price data is too coarse to price the exit and report coverage); (4) the
information test: does "≥1 backer exited" as a live-observable event predict subsequent
failure vs matched non-exit signals? Self-test: synthetic fixture where exits are injected
to be informative must be detected; a random-exit fixture must read flat.

### Phase 4 — B: detection-latency anatomy (`scripts/latency_anatomy.py`, self-testing)
From atoms: per signal, last-backer-fill→first_detected_at distribution (and first-backer→
detection). Within-signal: advantage vs detection-latency quartiles, event-clustered,
matched baseline (careful: latency correlates with slate density and sport — control by
regime). Reconcile the three numbers (structural tax, detection latency, post-detection
decay) into ONE coherent time-anatomy of the edge: fill → detectable → detected → acted.
Answer numerically: what would a 10s poll (vs 60s) plausibly recover, in points?

### Phase 5 — C: capture-completeness audit
Cycle-gap timeline (from signal update cadence + logs + 429/gap counters), downtime windows,
estimated missed-fire count (blind fires per active-hour × downtime hours), and the bias
argument (are downtime windows correlated with regimes/outcomes? show, don't assert).
Overlay daily coverage vs daily P&L in the report.

### Phase 6 — F: the adversarial battery
All five attacks, at match-level clustering, results tabulated kill-or-clear with numbers.

### Phase 7 — Synthesis: the truth report
`reports/entries/NN-truth-audit.md` + DECISIONS.md D13/D14: per doubt A–F, the verdict with
its strongest evidence; the REVISED headline (surplus/LB/z at match-level clustering — the
new official numbers); what was killed/downgraded (loudly, first); what survived attack;
the residual-risk list that remains before real money (persistence re-read, fill-probability
pilot, jurisdiction — the standing three); at most ONE nomination (exit-follow rule from A,
silent, D7-gated) if and only if its evidence is FDR-clean. Update REFINED-STRATEGY.md only
where an attack's result binds. Merge --no-ff, re-gate post-merge main, verify the deployer
stays healthy.

## Rejected approaches (do not do)

- Confirmation-shopping: re-running an attack with tweaked parameters until it clears. Each
  attack runs ONCE as pre-registered; parameter changes require re-registration in the
  report with the original result shown alongside.
- Pricing backer exits with data we don't have (no per-exit orderbook history): where the
  snapshot grid is too coarse, the counterfactual is reported with its coverage % and
  labeled UNPRICEABLE, not interpolated into existence.
- Building a faster poller (B measures whether it's worth it; building it is a later,
  separate run if the number says so).
- Any real-money action, any alerting change, any env flip.

## Acceptance

Every attack A–F executed once, pre-registered, reported kill-or-clear with numbers; new
official headline stats at match-level clustering; self-testing instruments
(`exit_study.py`, `latency_anatomy.py`, the super-key lib) committed; grading verified
independently; kill criteria honored (a revoked eligibility is a valid outcome); ≤1 silent
nomination; docs updated; merged + post-merge re-gated; live behavior unchanged. The
deliverable is THE TRUTH — with its uncertainty stated, whichever way it points.
