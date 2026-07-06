# Autonomous run — "Unified System": compose the corrected corpus (D13–D22 + the 6-rule thesis) into the most reliable single book

> **How to run.** Paste this whole file as the task for a fresh Claude Code session opened in
> `~/polymarket-bot`, or dispatch it:
> `claude -p "$(cat ~/polymarket-bot/UNIFIED-STRATEGY-INTEGRATION-PROMPT.md)"`
> Long, self-directed run to a finished, gate-green, merged deliverable: ONE unified end-to-end system
> (capture → select → size → reliability-gate → alert → go-live), every component adjudicated against
> the LATEST evidence, every synergy tested. Only stop for a decision genuinely Tue's ("realign the
> alert path — y/n", "apply to live bot — y/n", "real money — y/n").
> **FRESHNESS CHECK FIRST (mandatory):** `main` moves under you — several chats run in parallel
> (`git log --oneline -15`, `git worktree list`, `ls reports/entries | tail`, `grep '^## D' DECISIONS.md
> | tail`). Before writing anything, re-read the numbers this brief cites and CORRECT them if the repo
> has moved past them. The brief was written at `main` = `2c0fcd2` (entry 19/D21 = corr-risk-verify,
> record 229 pos/80 games); if a later entry/D exists, take the next free number and reconcile.
> Companion reading: `DECISIONS.md` (esp. **D20 AND its correction D21**), `REFINED-STRATEGY.md`, and
> entries 10 (slice/D13), 12 (risk/D15), 13 (truth/D16), 14 (reliability/D17), 17 (effectiveness/D19),
> **18 (corr-risk/D20) + 19 (corr-risk-VERIFY/D21 — the correction)**. Instruments: `scripts/{slice_study,
> risk_engine,effective_n,edge_orthogonality,portfolio_constructor,persistence_tracker,corr_risk_engine,
> corr_risk_verify,game_correlation,selection_null}.py`. Live parallel work: **`specialist-selection`**
> (SELECT-stage; `reports/selection/FINDINGS.md`) — CONSUME its outputs, do not re-derive selection.

---

## 0. The mission (read twice)

The repo solved the pieces one decision at a time — **selection** (D13, + the live `specialist-selection`
refinement), **sizing** (D15), **survival-under-attack** (D16), **the book + orthogonality + honest
effective-N** (D17), **the wait-vs-bet tradeoff + the live alerting leak + persistence** (D19), **the
correlation UNIT** (D20) **and its adversarial correction** (D21) — plus a proposed 6-rule thesis (below).
**They have never been composed into one system, and today they partly contradict each other.** The two
sharpest contradictions:
- **The live alerting leak (D19):** the bot alerts `strict` (which contains the D13 **DODGE** residue,
  −13.7…−23.7%) while the certified winner `favorite` is **silent**. D19 named this the single biggest
  realized-P&L lever, still open.
- **The sizing story moved (D20→D21):** D20 proposed a blunt `≤3/game` cap as "the knee"; D21 corrected
  it — the **Kelly fraction is the first-order lever**, the blunt cap is not a Pareto win, and *if* you cap,
  cap **directionally**. A unified system must be built on **D21's corrected sizing, not D20's**.

This run does NOT re-derive any piece and does NOT re-run selection (specialist-selection owns that). It
**composes the corrected corpus into ONE book where each component maximises the others**, gives every
component a cited verdict, tests the synergies, and emits the most **reliable** profitable system the
evidence supports — reliability the hard constraint, profit maximised strictly within it.

> **One sentence:** turn the (now internally-corrected) findings into one pipeline that selects where the
> edge is, sizes with the right first-order lever (Kelly fraction) plus optional directional insurance,
> gates on honest game-grain independent-block reliability, alerts on the thing that actually earns, and
> goes live only when the edge (δ) is established forward.

**The motto:** *reliability is the constraint, profit the objective; use the LATEST verdict on each piece
(D21 over D20 where they conflict); a component earns its place only by making another measurably better.*

---

## The pipeline to assemble (the spine)

```
CAPTURE ─▶ SELECT ─▶ SIZE ─▶ RELIABILITY-GATE ─▶ ALERT ─▶ GO-LIVE
 (deep    (D13 cells +   (D21-corrected:        (D17 orthogonality;   (fix the    (δ/λ established
  ingest, specialist-    ⅛→⅒–⅟₁₆-Kelly is       effective-N at the    D19 LEAK:   forward: ≥K adverse
  top-200) selection:     the FIRST-order        GAME grain; D19       alert the   correlated days,
           moneyline,     lever; ≤1/event;       persistence count;    SELECTED    ≥5 non-expiring
           opp≥1,         OPTIONAL market-type-  supply-only growth)   winners,    regimes, months —
           horizon<6h,    aware DIRECTIONAL cap                        silence     D18/D19/D20/D21)
           band .80-.90;  for the rare stacked-                        the DODGE)
           favorite book; game catastrophe —
           DODGE residue) NOT D20's blunt ≤3)
```

Every arrow is a hand-off this run must make coherent. **SELECT→ALERT is the highest-value fix; SIZE is
governed by D21 not D20.**

---

## Component adjudication (frozen inputs — verdicts are the run's job; use the LATEST evidence)

| Component | Contributes | Standing status to reconcile |
|---|---|---|
| **D13 slice + live `specialist-selection`** | SELECT map: PRIORITIZE cells (moneyline +15.6% ROI, opp≥1, horizon<6h, band .80–.90); DODGE residue | keep; **CONSUME specialist-selection's `reports/selection/FINDINGS.md`** for the current selection axis — do not re-run selection or edit its files (active chat) |
| **D15 risk engine** | SIZE machinery: block bootstrap, flat-SHARES, `kelly_*` | keep the machinery; **its ⅛-Kelly default and event-keyed caps are SUPERSEDED by D21** (Kelly-fraction-first) |
| **D16 truth audit** | favorite edge survived attack (selection-null p=0.0000, +6–11pt vs blind); "+3.33%" STALE | keep as the reliability floor; **this is where edge-reality lives — the sizing engine can't (δ shuffle-invariant, D21-Q4)** |
| **D17 reliability portfolio** | BOOK=favorite-only; orthogonality 0/12 (trust_weighted power-starved); effective-N Q1≠Q2 | keep; **re-run effective-N at the GAME grain (D20 unit)** — fewer independent blocks ⇒ persistence wall farther than D17's match-level number |
| **D19 effectiveness** | tradeoff quantifier; **the LIVE ALERT LEAK** (biggest realized-P&L lever); persistence tracker | **RESOLVE the leak**: propose realigning ALERT to the selected favorite/PRIORITIZE stream (spec/paper; live flip = Tue) |
| **D20 correlated risk** | UNIT = game (TRUE, robust); position-bootstrap understates tail 3× | keep the UNIT finding; **its blunt ≤3/game recommendation is OVERSTATED (superseded by D21)** |
| **D21 corr-risk-verify** | the correction: Kelly-fraction is first-order; base = P1 (no game cap); if capping, market-type-aware DIRECTIONAL; edge is δ's not the engine's | **this is the governing sizing verdict** — build SIZE on it |
| **6-rule thesis** | 3,5,6 CONFIRMED; **rule 1 (≤K/game cap) REFINED — blunt cap demoted, Kelly-fraction is the lever**; rule 2 (drop padding) REFUTED (independent markets are +EV ballast, D21-Q5); rule 4 (size-to-λ) → reconcile with Kelly-fraction de-lever | fold in with these corrected verdicts |

**K6 (adjudication honesty):** every component ends with a cited verdict — KEEP / REPLACED-BY-X /
RESOLVED-AS-Y / SUPERSEDED-BY-Z (D20→D21 is the model case). Nothing silently dropped or kept for tidiness.

---

## The synergies to test (quantify each; a component earns its place by improving another)

1. **SELECT × ALERT (the leak — highest value).** Measure the realized-P&L delta of realigning alerts from
   `strict` (holds the DODGE residue) to the D13/specialist-selection winners. **Propose, do not apply**
   (live alerting flip = Tue). The run's most important number.
2. **SELECT × SIZE (within-game keep-rule).** D21-Q5 already answered the shape: keep the near-independent
   totals/exact-score (+EV ballast), cap only the directional stack. **Build on it**, don't re-pose it:
   confirm it under the current record + specialist-selection axis, and state the rule-2 correction plainly.
3. **UNIT × RELIABILITY (game-grain effective-N).** Re-run `effective_n.py` at the GAME grain — how far does
   the honest independent-block count fall vs D17's match-level number, and how much farther does that push
   the go-live clock?
4. **SIZE lever reconciliation (resolves rule 4).** D21 says the Kelly FRACTION is first-order. Reconcile
   "size-to-λ=0.5" (thesis rule 4) with "de-lever to ⅒–⅟₁₆-Kelly" (D18/D19/D21): are they the same lever in
   different clothes? Pick the single sizing rule that holds `P(maxDD>25%)≤10%` at λ=0.5 with the most λ=1
   growth, with the directional cap as optional second-order insurance.
5. **ORTHOGONALITY × SUPPLY.** Re-confirm 0/12 on the current record; restate that reliability accrues only
   via independent SUPPLY or a matured trust_weighted, and that the game-unit correction makes each
   tournament worth fewer independent blocks than the position count implied.

---

## Ground truth you must NOT relitigate
- **Unit = match-key** (suffix-stripped; `game_correlation.py` helper; one game ≤7 event_slugs; favorite
  ≈**229 pos / 80 games**, 66% WC — accruing, re-pull). **D15 ICC≈0.008 is a benign-sample artifact** (no
  upset sampled); `n_eff(game)` binds on the **unmeasurable w_game** — sweep, never fit. Position bootstrap
  understates the tail ~3× (D20/D21 self-tests). **The single-bet grain of the live bot is one flat stake
  per `(strategy,condition_id,outcome_index)` — event-clustering exists only in the edge stats, never sizes
  stakes** (D21-Q3, read from the Rust — do not re-assume).
- **D21 governs sizing:** base = P1 (⅛-Kelly, ≤1/event, no mandatory game cap); **Kelly fraction is the
  first-order tail lever**; optional market-type-aware directional cap only; **δ is shuffle-invariant so the
  sizing engine cannot validate the edge — reliability is D16/selection-null/persistence, unchanged NOT-YET.**
- **AT-FIRE entry** `COALESCE(initial_mean_price,mean_price)` (D6); measured costs 0.5¢+2%; **flat-SHARES
  never flat-$**; **skip longshots**; null (`selection_null.py`) + promotion gate (D7) unchanged; go/no-go
  turns on δ/λ; nothing here shortens that clock.
- **Applied migrations IMMUTABLE.** This run needs **no** migration.

## Non-negotiable guardrails
1. **Reversibility + coordination.** Worktree off fresh `main`, new branch, tag `pre-unified-system-<date>`.
   `git worktree list` shows active chats (congregation, deep-edge, edge-truth, honest-pnl, entry-ask,
   **specialist-selection**). Keep your file slice non-overlapping; **do NOT touch `reports/selection/*` or
   the selection scripts specialist-selection owns** — consume their committed outputs only. BUILD ON the
   shipped instruments; do not fork copies. Smallest additive changes to shared files; say so if you must.
2. **Gate every commit:** `RUSTFLAGS="--cfg tokio_unstable -Dwarnings" cargo fmt --check --all && cargo
   clippy --workspace --all-targets && cargo test --workspace`; Python = `py_compile` + fixture smoke.
   **Re-gate `main` after the merge lands** (it moves under you; the autoupdater ships main).
3. **Paper-only, additive, belief-blind.** No real money, no order placement, **no alerting/env flip**, no
   auto-promotion. The alert-realignment (synergy 1) is **spec/paper only** — the most consequential
   proposal, explicitly Tue's call.
4. **Deploys only via `scripts/consensus-autoupdate.sh`.** **Cost-zero** (Max only; no `ANTHROPIC_API_KEY`;
   no child `claude`). DB **read-only**: `docker exec -i polymarket-bot-postgres-1 psql -U bot -d polymarket --csv -q`.

## Pre-registration (write BEFORE computing)
- **Objective (frozen):** maximise median log-growth/100 events SUBJECT TO `P(maxDD>25%) ≤ 10%` under the
  **game-block copula at λ=0.5**; report **risk-adjusted ratio = median growth ÷ p95-maxDD** (game-block,
  λ=0.5) and **portfolio CVaR₅ + p99 maxDD** (the metrics D21 showed the blunt cap *worsens* — carry both,
  they can disagree) for every candidate. **Baseline to beat = D21's P1** (not D20's ≤3/game). **Reliability
  is the hard constraint** (orthogonality-clean, favorite-anchored, honest game-grain persistence); profit
  maximised only within it.
- **K1** game-grain n_eff<~40 ⇒ long-horizon = EXTRAPOLATION; lean H=1×. **K2** flip across w_game/grain ⇒
  fattest-tail binds. **K3** no "guaranteed"; conditional-on-δ + the λ=0 line always. **K4** nothing live
  changes — instruments + a *proposed* policy + spec + the alert-leak proposal only. **K5** unified λ=1
  growth ≥90% of P1 (don't gut EV). **K6** per-component cited verdict incl. D20→D21. **K7 (reliability
  floor)** stays orthogonality-clean + favorite-anchored; no uncertified arm added to buy profit. **K8
  (no-collision)** do not re-derive or edit specialist-selection's SELECT work; consume it.

## Phases (each ends gate-green + committed)
- **Phase 0 — Freshness + setup.** Freshness check (top of file); worktree+branch+tag. Read D20 **and D21**,
  entries 18/19, the instruments, and `reports/selection/FINDINGS.md`. Reproduce the LATEST headlines (D21's
  P1-is-base + directional-cap; D19 leak; 0/12). If any won't reproduce or the repo moved past the cited
  numbers, correct them before proceeding. Confirm you extend, not fork.
- **Phase 1 — Adjudicate + wire SELECT→SIZE.** K6 verdict per component (D21 supersedes D20 on sizing).
  Implement the composed policy in a thin `scripts/unified_system.py` importing slice_study + specialist
  outputs + corr_risk_engine/corr_risk_verify + selection_null. Confirm synergy 2 (D21-Q5 directional keep).
- **Phase 2 — Reliability at the game grain.** Synergy 3 (game-grain effective-N/persistence) + synergy 5
  (re-confirm 0/12). Restate the honest go-live clock with the corrected block count.
- **Phase 3 — Sizing lever + the ALERT leak.** Synergy 4 (reconcile size-to-λ with Kelly-fraction de-lever;
  directional cap optional). Quantify synergy 1 (realized-P&L delta of alert realignment). Headline proposal.
- **Phase 4 — Synthesise + evaluate end-to-end.** Compose select→size→gate→alert→go-live; evaluate on the
  record; confirm ratio, CVaR₅/p99 vs P1, K5 ≥90%, K7 held; survives ex-WC. **Self-test** the composed
  evaluator (each stage; the position-bootstrap-understates-tail case must still fire; a λ=0 fixture must lose).
- **Phase 5 — Ship & verify.** `reports/entries/<date>-<NEXT>-unified-system.md` (pipeline diagram; K6
  verdicts incl. D20→D21; 5 synergy numbers esp. the alert-leak delta + game-grain persistence; the one
  profit-per-risk number vs P1; the δ/λ-gated NOT-YET; the alert-leak proposal for Tue). `DECISIONS.md +=
  <NEXT D>`. Rewrite the relevant `REFINED-STRATEGY.md` section as the single unified system (cite each
  rule's deciding evidence; sizing per D21; caps directional-optional). Merge `--no-ff`; **re-gate post-merge
  main**; confirm autoupdater "no code change — skipped rebuild". Final report to Tue: the system in one
  screen, its one number, the alert-leak decision, the exact go-live trigger, what was NOT done, exact rollback.

## Rejected approaches (do not build)
- **Building SIZE on D20's blunt ≤3/game** — superseded by D21; Kelly-fraction-first + optional directional cap.
- **Re-deriving selection / editing specialist-selection's files** — consume its outputs (K8).
- **Adding an uncertified arm to raise profit** — violates K7 (watch-item until it clears its own gate).
- **Applying the alert realignment or any live flip without Tue** — propose only.
- **Re-deriving any shipped instrument; fitting w_game / a Kelly edge on the no-loss record.**
- **Keeping refuted rule 2 for tidiness** — independent markets are +EV ballast (D21-Q5); keep them.
- **A second strategy / recombination diversification** — supply-limited (D15/D17).
- **Treating P(profit)=100% / benign bootstrap / the sizing engine's "good trade-off" as edge validation** —
  no-losing-slate artifact; δ is shuffle-invariant; edge-reality is D16/selection-null/persistence only.

## Acceptance
Gate-green commits; `unified_system.py` extending the shipped instruments with PASSING self-tests; the K6
per-component verdict table (D20→D21 shown); the 5 synergy results quantified (esp. the alert-leak
realized-P&L delta and the game-grain persistence count); ONE composed system evaluated against **D21's P1
baseline** (ratio, CVaR₅, p99), K5 ≥90%, reliability floor (K7) intact, no specialist-selection collision
(K8); next free entry + D-number; REFINED-STRATEGY rewritten as the unified system with sizing per D21;
merged + post-merge re-gated; live behaviour unchanged; paper-only. Output = **the most reliable single book
the corrected evidence supports** — each component making the others measurably better, profit maximised
strictly within the reliability constraint, real money still gated on δ/λ, and the alert-leak fix put in
front of Tue as the highest-leverage decision on the table.
