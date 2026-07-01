# Autonomous Long-Run Charter — The Optimal Congregation Engine

> **What this is.** A long, self-directed build+research run whose goal is not to
> mechanically type out a blueprint, but to **arrive at the most optimal model for
> congregating Polymarket's best traders into a signal that is measurably better,
> risk-adjusted, than any single one of them** — and to build it as a
> non-regressive, leak-free, belief-blind-certified instrument in the
> `polymarket-bot` consensus engine. Take the time. Depth over speed. An honest
> NULL that is correctly judged beats a green number that is fooling us.

---

## 0. THE NORTH STAR (read this twice)

The naive engine counts backers on an outcome and alerts on the headcount. Its own
calibration proves it tracks the market price with ~zero edge ("count is noise").
We are replacing that with an engine that reasons about **who** agrees, **in what
context**, and **how their signals combine** — and we hold it to the bar: it must
beat BOTH naive `net_count` AND the market price (real mispricing), certified
out-of-sample, after a realistic follower's worse fill.

**The one idea that makes "better than the best of them" mathematically honest.**
You do NOT beat the best soccer sharp by out-picking him on soccer. You beat the
field by **assembling a diversified book of domain-certified specialists and sizing
each by its certified, shrunk edge** — so that many independent, uncorrelated
edges combine into a higher risk-adjusted return (Sharpe) than any single
specialist's, while variance falls. Diversification across genuinely independent
certified edges is the only free lunch, and it is the actual mechanism by which a
congregation can exceed its best member. Correlation is the enemy of that lunch;
identifying and neutralizing it is central work, not a footnote.

So the mission decomposes into four honest sub-problems, in priority order:

1. **Identify** genuine per-context specialists (leak-free, event-clustered,
   sample-floored) — separate the durable sharp-in-a-domain from the lucky and the
   favorite-loader. This is the binding constraint; most of the edge lives here.
2. **Combine** their signals optimally — the aggregation/weighting/routing model —
   such that the combination is provably better-structured than headcount, and,
   where the data supports it, exploits diversification and de-weights correlated
   or reflexive agreement.
3. **Certify** the combination on what a *follower* actually captures (worse entry,
   fees, slippage, latency), never on the sharp's own realized edge.
4. **Abstain** honestly — emit nothing when no certified specialist is present.
   Coverage is earned, not assumed; silence is a valid, correct output.

You have latitude to find the best model for (2). You have **no** latitude at the
gate: belief lives in the generator, rigor lives only at the belief-blind
promotion gate. Be ambitious in what you try; be merciless in what you certify.

---

## 0.5. MINIMUM DECISIVE PRE-FLIGHT — do this FIRST, before any build (read-only, ~1 hour)

The entire mission rests on one empirical precondition: **that ≥2 independent,
capturable, persistent per-context specialists actually exist on this data.** If
they don't, the diversification north star is dead and Phases 2/5 are wasted hours.
Falsify-or-proceed before building anything.

**Prerequisite:** the leak-free instrument must exist before the research that uses
it. So **`trader_slice_scores_asof(cut)` is Phase 0.5 (see §4), and it lands before
this pre-flight.** `trader_slice_scores` today is a GLOBAL resolved-only snapshot
with NO as-of cut (`common/src/storage/consensus.rs`, `WHERE resolved AND
side='BUY'`) — using it to "certify then check forward" is selection-on-the-outcome
and inadmissible. Every identification/persistence claim below uses the `_asof`
variant with an explicit train/test cut.

**The experiment (read-only SQL over `trader_fills`, one as-of cut, ≥2 disjoint cuts
to confirm):**
1. Count wallets gate-Trusted **at the CAPTURE bar** (`lower_bound > slippage_pct +
   fee_pct = 3%`, not margin 0), N≥30 distinct events, on **any single sport
   slice**, certified on `resolved_at < cut` — then count how many persist as
   Trusted-in-that-sport on the post-cut window.
2. Among survivors, count pairs Trusted in **different** sports, and measure their
   pairwise **slate-level** (event-day within league) co-occurrence.

**Decision rule (binding).** If (1) yields **<2 capturable, persistent per-sport
specialists**, OR (2) shows they collapse onto the same slate → the diversification
premise is **DEAD ON THIS DATA**. Do NOT build Phases 2/5. Deliver only: the as-of
harness, the honest-null finding, and the accrual curve (when would ≥2 emerge at the
current data-arrival rate). This same result IS the leak-free answer to the §7
escalation trigger — record it and proceed accordingly. A dead premise, correctly
established in one hour, is a successful run.

---

## 0.6. HARDENING RAILS (v2 — these OVERRIDE anything below on conflict)

Adversarial review of v1 found selection/leakage holes that "good-faith" research
would still fall into. These are binding:

- **H1 (train/holdout, pre-registered).** Any choice made by comparison — which
  weighting scheme, which contexts, which floors, which specialist set — is a TRAIN
  decision. Pre-register the FULL candidate set in `RESEARCH.md` before looking;
  select on TRAIN cuts; FREEZE; report the bound ONCE on untouched HOLDOUT cuts.
  "Let the gate pick the winner on the holdout" is forbidden — that is selection on
  the holdout. If a winner is ever chosen on holdout, its reported bound MUST carry
  a Bonferroni denominator = number of candidates tried (≥5), not 1. Document every
  loser WITH its holdout bound so the selection is auditable.
- **H2 (identification is leak-free or inadmissible).** "Does per-context
  certification predict forward edge" is answered ONLY via `trader_slice_scores_asof`:
  certify on `resolved_at < cut`, measure edge strictly on events whose freshest
  backer ts ≥ cut, over ≥2 disjoint cuts. An in-sample (no-cut) answer does not
  satisfy the §7 kill-switch and must not be reported as a "yes".
- **H3 (fleet-relative ≠ market).** The substrate's `surplus` is measured against a
  band-blind that is the fleet's own per-band average INCLUDING the scored wallet
  (`consensus.rs`, documented) — so it means "beats the average tracked sharp in
  that band," NOT "beats the open market," and it mechanically cross-correlates every
  wallet's surplus series. Therefore: (a) estimate specialist-signal correlation on a
  MARKET-relative return (outcome_won − CLOB mid at signal time) or a **leave-one-out**
  band-blind, never on the raw shared-baseline surplus; (b) "beats the market" is only
  established once the capture margin AND the CLV lens agree — say so wherever you
  claim it.
- **H4 (slate-level correlation for diversification).** The within-wallet gate stays
  on `event_slug` (correct, unchanged). But the CROSS-wallet diversification/
  correlation estimate MUST cluster co-active specialist signals at the **slate level**
  (event-day within sport/league): two different specialists on two different games of
  the same World-Cup day share favorite-direction and public info despite distinct
  event_slugs. Report the diversification benefit under BOTH grains; if it vanishes
  under slate-clustering, it was an independence artifact — say so.
- **H5 (no peeking / pre-registered evaluation points).** The board re-judges the
  forward record every refresh; a one-shot gate applied repeatedly as N grows
  manufactures passes at the first refresh the bound clears. A TRUSTED verdict is
  reportable ONLY at pre-registered evaluation points — first eval at N=30 distinct
  events since the arm started, then every +15 — never at the first clearing refresh.
  Report the N at which each arm was evaluated.
- **H6 (capture-completeness ≠ price haircut; survivorship).** Follower capture has
  TWO losses, not one: (a) worse price (haircut), and (b) missed events we didn't poll
  in time (`followed_traders.capture_gap_count`). Bound the capture-completeness
  transfer separately — what fraction of a specialist's qualifying events did we
  actually observe in the freshness window; treat unobserved qualifying events as
  missed, not free. And note the survivorship caveat: the followed universe is
  selected on past leaderboard PnL, so historical specialist base rates are inflated —
  the FORWARD record, not the historical certification, is the unbiased read.
- **H7 (routing dimensions that exist).** Route specialists on **(sport, band)** only
  — the slices the schema actually emits (`overall/sport/band/recency7d/recency30d`).
  "line-type" is NOT in the schema; do not invent it. If ever introduced, pre-register
  the exact taxonomy and charge its slice count into the Bonferroni denominator.
- **H8 (family routing before coalitions).** `family()` is a static const-match today
  — any tag NOT in the hardcoded `EXPERIMENTAL` list falls to `"core"` and would
  tighten live `strict`'s family. BEFORE any dynamically-named coalition arm exists,
  change `family()` to a PREFIX match: `spec_*`/`edge_pool` → `"experimental"`,
  `coalition_*` → its own `"coalition"` family; add a unit test asserting
  `family("<any new tag>") != "core"`. Correct the Bonferroni arithmetic: the
  `EXPERIMENTAL` list already holds 8 today, so the two spec arms make it 9→10.
- **H9 (line cites are indicative).** The reality pass drifted ~+76 lines vs today's
  tree (`EnrichCtx` is ~234 not ~159; `family` ~305; board is `src/board.rs`).
  Re-grep symbol NAMES before editing anything by line number.
- **H10 (clippy advisory if baseline dirty).** If the baseline tree is not already
  clippy-clean, `cargo clippy -D warnings` is advisory and the HARD gate is
  `cargo build && cargo test`. Confirm baseline cleanliness in Phase 0.5. Route both
  trust maps through the existing `cached_slice_scores` TTL cache, not a raw
  `trader_slice_scores()` per refresh (avoids a doubled full-table scan).

---

## 1. GROUND TRUTH — what exists, what's verified, where to start

- **Repo:** `~/polymarket-bot`, branch `feat/consensus-engine`. Rust workspace
  (`copy-trading-bot` + `common`). Paper-only; **never** add real-money execution.
- **The vetted design floor:** `run-prompts/RUN-COMPLEX-CONSENSUS.md` (the Forge
  blueprint) and `run-prompts/RUN-COMPLEX-CONSENSUS.FORGE_DEBATES.md` (why choices
  were made, what was rejected and verified). **Read both fully before touching
  code.** The blueprint is your FLOOR, not your ceiling: implement its spine, but
  you are explicitly charged with improving the aggregation model beyond it if the
  data and your research justify it. If you diverge, record why (§7).
- **The forward-only judging harness already exists** — this is why the build is
  tractable and non-regressive. Arms emit silent `Tier::Watch` rows under a
  strategy tag (`scanner/enrich/mod.rs`); the event-clustered, favorite-longshot-
  neutralized surplus scoreboard judges them (`storage/consensus.rs:466`,
  `consensus_scoreboard_by_strategy`); the belief-blind gate corrects per-family
  Bonferroni (`scanner/promotion.rs`, `promotion_verdict`/`surplus_bounds`). The
  per-context substrate exists too (`trader_slice_scores`, per-sport/band surplus).
- **Verified facts you must not re-litigate (from the Forge reality pass):**
  - `event_slug` is a **date-stamped per-game slug** → existing event-clustering
    already collapses the within-match multi-market leak AND encodes the day. A
    naive `(event_slug, day)` re-clustering is a **no-op for sports and
    anti-conservative** for multi-day futures. Do NOT add it; if you touch
    clustering, first run the multi-day-futures distribution probe and justify.
  - `_blind` rows are **never price-snapshotted** (`housekeeping.rs:148`), so a
    CLV band-blind degenerates to zero. CLV/line-movement is a lower-variance
    **reported lens + reflexivity guard**, NOT a sole certifier. Primary
    certification stays on the outcome scoreboard, whose `_blind` baseline works.
  - Per-arm gating uses the `EnrichModels` bool pattern (mirror `bayes_enabled`,
    set in `load_models`, checked at the top of each arm), NOT `is_empty()` or
    non-existent `ctx.cfg_*()` accessors.
  - Binding constraint: only ~10/90 wallets clear even the overall 30-event floor;
    per-sport specialists are rarer. Expect much of the board to read
    INDETERMINATE. That is a correct result, not a failure.
  - **Line cites in the blueprint drifted ~+76 lines vs today's tree (H9).** Treat all
    line numbers as indicative; re-grep symbol NAMES before editing. And the substrate's
    `surplus` is fleet-relative, not market-relative (H3) — never equate a certified
    surplus with "beats the market".

---

## 2. NON-NEGOTIABLE RAILS (the gate — violate none)

1. **Non-regression is sacred.** Every new capability ships SILENT (`alerting:false`,
   `re_emit` forces `Tier::Watch`), flag-gated **default OFF**. With all flags off,
   the consensus path is byte-identical and live `strict` alerts are untouched.
   Never destroy or regress the proven path to build the new one (safe-swap).
2. **Reuse the gate; add ZERO new unvetted statistics** where `promotion_verdict` /
   `surplus_bounds` already supply one. New cleverness lives in the
   generator/aggregation, never in a bespoke significance test.
3. **Leak-free, as-of.** Any weight/trust/coalition/edge used to score a signal is
   derived ONLY from data resolved BEFORE that signal's timestamp. Live-forward arms
   are leak-free by construction (they predict unresolved markets). Any arm that
   FITS or MINES on history requires the walk-forward `..._asof(cut)` harness FIRST
   — it lands before the arm that depends on it. No exceptions.
4. **Event-clustered inference.** The independent unit is the event, not the fill
   or the line. Treat correlated fills/lines/co-bets as one sample everywhere —
   identification, correlation estimation, sizing, and certification.
5. **Certify on the follower's capture,** not the sharp's edge: debit the
   `slippage_pct + fee_pct` capture margin at the gate, model a worse/later entry,
   and guard against reflexive line-movement (own-fleet market impact).
6. **Null-calibrated.** Every discovered structure (a weighting, a specialist set, a
   coalition) must survive identity-shuffle AND outcome-shuffle nulls collapsing its
   edge to ≈0. If it doesn't, it is an artifact — discard it.
7. **Propose, never auto-flip.** No arm gains alerting authority automatically. The
   run's output is a certified verdict + a proposal; a human flips the flag.
8. **Honest NULL is success.** If the optimal model, honestly judged, does not clear
   on current data, the deliverable is the correctly-built instrument + the honest
   verdict + the accrual plan. Do not tune thresholds, drop the floor, or p-hack to
   manufacture a pass. Report exactly what is and isn't there.
9. **Cost-zero, model-disciplined.** Max subscription only; refuse any
   `ANTHROPIC_API_KEY` in env; no child-`claude` spawns from workers. Opus for
   reasoning-heavy sub-work, Sonnet minimum; never trade model quality for capacity.
10. **Verify gate must be worktree-satisfiable.** Work in an isolated git worktree
    off `feat/consensus-engine`. The gate is `cargo build && cargo test` (+ `cargo
    clippy -- -D warnings` and `cargo fmt --check`). Every phase ends green. Commit
    per green phase so a killed run is salvageable from the worktree — assume the
    run may be interrupted; leave the tree recoverable and the progress legible.

---

## 3. RESEARCH MANDATE — hone in on the optimal model BEFORE locking it

Do not jump straight to the blueprint's arms. First, spend a real research phase on
the **trader_fills archive** (4 years, ~37k fills, offline, as-of-clean) and the
forward consensus history to answer the questions that determine the optimal
congregation model. Produce a written `RESEARCH.md` with evidence before Phase 2.

**Obey the H1–H10 hardening rails (§0.6) throughout this phase** — every comparison
is a pre-registered TRAIN decision certified once on HOLDOUT (H1); identification is
as-of only (H2); correlation is estimated market-relative/leave-one-out (H3) at the
slate grain (H4); route on (sport, band) only (H7). This phase is where selection
bias hides — pre-register the candidate set in `RESEARCH.md` before you look.

**Identification questions (sub-problem 1):**
- How many wallets are certifiable specialists per (sport, band, line-type) at the
  30-event floor, today and on the accrual curve? Where is the coverage cliff?
- Does per-context certification (soccer-sharp) predict FORWARD per-context edge
  out-of-sample, or is it in-sample overfit? Prove it with a walk-forward split.
- What distinguishes a durable specialist from a favorite-loader and a hot streak,
  beyond the band-blind neutralization already in place? Is there a stability/
  consistency signal (edge persistence across time-halves) worth certifying on?

**Combination questions (sub-problem 2 — the heart of "better than the best"):**
- What is the correlation structure of specialist signals? When K specialists agree,
  how independent are they really (same game? same event-day? same
  favorite-direction? herding on the same public info)? Quantify it — the
  diversification benefit is entirely governed by this.
- Does a diversified book of per-domain specialists, sized by certified shrunk
  lower-bound edge (fractional-Kelly style), achieve higher risk-adjusted return
  than the single best specialist, out-of-sample? This is the central thesis —
  test it, don't assume it.
- What is the optimal weighting? Compare, on the belief-blind gate over holdout:
  headcount (baseline) vs quality-weight vs certified-lower-bound weight vs
  log-odds opinion pool anchored on the CLOB mid vs correlation-discounted
  variants. Let the gate pick the winner; keep the winner, document the losers.
- Is agreement even the right trigger, or is a lone fresh certified specialist
  (leading the crowd, before CLV decays) the better unit — and is a certified
  specialist FADING the crowd (contrarian-in-competence) better still? The
  blueprint ships both; your research decides their relative weight and whether a
  combination dominates.
- Where does routing help: does conditioning on context (sport × band × time-to-
  resolution × favorite/dog) materially change which specialist to trust, versus a
  flat trust map? Measure the lift.

**Capture & honesty questions (sub-problems 3–4):**
- How much of the sharp's edge survives a follower's worse entry + fees + latency?
  Re-price the archive's winning specialist bets at a realistic late/worse fill and
  measure the transfer fraction. This bounds everything.
- Where should the model abstain? Characterize the precision/coverage frontier:
  the contexts where certified signal exists vs where silence is correct.

Write conclusions as falsifiable claims with the evidence and the walk-forward /
null results beside each. Where a claim fails, say so and let it reshape the build.
This research phase is where "the most optimal model" is actually decided — the
implementation phases execute what the evidence chose.

---

## 4. THE BUILD — phased, each phase green, research-informed

Implement the blueprint's spine, refined by §3's findings. Order matters: foundation
and harness before the arms that depend on them. Each phase: isolated commit, gate
green, a unit test that pins the new behavior, and a one-paragraph note in
`PROGRESS.md` (what shipped, what it proved, what's next).

- **Phase 0 — Capture margin at the arm gate.** Wire `slippage_pct + fee_pct` into
  the strategy/arm promotion margin (NOT the trader-trust verdict). Every downstream
  verdict now judged at the capturable bar. Also confirm baseline clippy cleanliness
  (H10).
- **Phase 0.5 — AS-OF walk-forward harness FIRST (moved up from old Phase 4).** Build
  `trader_slice_scores_asof(cut)` (the `_asof` variant with `resolved_at < cut` in
  both the slice surplus AND the band-blind) and the offline train/holdout + null
  (identity-shuffle, outcome-shuffle) harness. This lands **before §3 research**
  because the pre-flight (§0.5) and the identification study (H2) and the weighting
  bake-off (H1) all REQUIRE it to be leak-free. Then run the §0.5 pre-flight
  experiment and honor its decision rule before proceeding.
- **Phase 1 — Per-`(wallet, slice)` trust map (keystone).** Build `SliceTrust` /
  `SliceTrustMap` reusing `surplus_bounds` (zero new stats); compute both the
  overall trust map and the slice map from ONE `trader_slice_scores` snapshot; add
  the single `slice_trust` field to `EnrichCtx`. No arm yet; passthrough stays
  byte-identical. This is the substrate every downstream idea consumes — build it to
  be extensible (new slice kinds, new context keys) so future models plug in without
  schema churn.
- **Phase 2 — The forward-live arms the research endorsed.** At minimum the
  specialist-footprint arm (lone/fresh/certified-in-sport, leading the crowd) and
  the contrarian arm (certified specialist fading the crowd). Add the
  correlation-discounted or diversified-book aggregation IF §3 showed it beats the
  simpler arms out-of-sample. Each rides `_blind` rows, re-emits silent, joins the
  `experimental` family, default-OFF flag. Account for every added hypothesis in the
  family Bonferroni.
- **Phase 3 — CLV/line-movement lens + reflexivity & settlement guard.** Reported
  lower-variance lens beside the outcome verdict; the outcome guard and capture
  margin remain the deciders. Snapshot-density caveat handled honestly.
- **Phase 4 — (harness already built in Phase 0.5).** Use this slot instead to wire
  the CLV lens's reporting query + pre-registered evaluation points (H5) into the
  board, and to run the frozen weighting-scheme certification ONCE on holdout (H1).
- **Phase 5 — Fitted/mined models, ONLY if earned.** The edge-weighted pool with
  fitted temperature, and coalition mining, gated behind the Phase 0.5 harness.
  **Prerequisite (H8): fix `family()` to prefix-routing FIRST** — give `coalition_*`
  its own family so a dynamically-named mined arm can never fall to `"core"` and
  tighten live `strict`; add the `family("<any new tag>") != "core"` unit test.
  Expected honest NULL on coalitions at current N — build it as a correctly-judged
  instrument and document the null; do not force a pass. Skip entirely if the §0.5
  pre-flight killed the premise.

If §3 discovers a better aggregation than the blueprint's, implement THAT in Phase 2
and note the divergence in `DECISIONS.md` with the evidence that justified it.

---

## 5. CERTIFICATION & REPORT — the definition of "done well"

Honor H5 (a TRUSTED verdict is reportable only at pre-registered evaluation points —
first at N=30, then every +15 — never at the first refresh the bound clears) and H6
(report the capture-completeness transfer separately from the price haircut, and the
survivorship caveat: the forward record, not historical certification, is the
unbiased read). Produce `REPORT.md` that, per arm/model, states over event-clustered
units:
- distinct-event N; surplus over band-blind (FLB-neutralized); Bonferroni one-sided
  lower bound at the capture margin; the CLV lens bound; the outcome guard; and the
  derived verdict **TRUSTED / INDETERMINATE / AVOID**, each **vs naive count** and
  **vs market**.
- The null results (identity- and outcome-shuffle → ≈0) for every fitted/mined model.
- The walk-forward holdout surplus with CIs for fitted models; the on-board forward
  record IS the holdout for forward-live arms.
- The diversification result: does the combined book beat the single best specialist
  out-of-sample, and by how much, risk-adjusted — with the correlation structure that
  drives it.
- The accrual curve: given today's N and data-arrival rate, WHEN does each promising
  arm reach certifiability? What is the honest ETA to a defensible bet, if any?
- A crisp recommendation: which arm(s), if any, are ready to PROPOSE for alerting,
  and which need more data — with the exact flag(s) a human would flip.

An all-INDETERMINATE board with correct nulls, an honest coverage frontier, and a
credible accrual plan is a SUCCESSFUL run. A green number that can't survive the
nulls or the capture margin is a FAILED run even if it looks good.

---

## 6. FUTURE-PROOFING — build the machine, not just the model

The single most valuable durable artifact is an **extensible congregation
substrate**, so the next idea is an arm, not a rewrite:
- The slice/trust map keyed on arbitrary context tuples (sport, band, line-type,
  time-to-resolution, favorite/dog…), so new routing dimensions are additive.
- The arm seam and the report auto-including any new strategy tag without schema
  churn — a new aggregation model = one new `Enricher` + one flag + one family entry.
- The as-of harness generic over the target (outcome surplus, CLV surplus, capture
  PnL) so future certification targets reuse it.
- Every threshold (floor, margin, freshness, temperature) a named constant/flag with
  the rationale in a comment, so future tuning is legible and reversible.
Leave `DECISIONS.md` capturing every non-obvious choice and its "why", so a future
run (human or agent) resumes with full context and can extend without re-deriving.

---

## 7. AUTONOMY PROTOCOL

- Work confidence-gated: when confident, proceed; when a load-bearing choice is
  genuinely ambiguous and unrecoverable-if-wrong, record the options + your pick +
  the reasoning in `DECISIONS.md` and proceed with the reversible default rather
  than stalling. Prefer reversible, non-regressive moves.
- Checkpoint every green phase (commit + `PROGRESS.md` note). Keep the worktree
  recoverable at all times — assume interruption.
- Audit your own work as you go: after each phase, adversarially ask "where could
  this leak, overfit, or regress `strict`?" and answer it in writing before moving on.
- Escalate (stop and surface) only for: a rail in §2 you cannot satisfy; evidence
  that the whole premise is refuted (specialist certification does NOT predict
  forward edge out-of-sample); or a discovery that would change the mission. A mere
  honest NULL is NOT an escalation — it's a valid result; finish the instrument and
  report it.
- Never: touch live `strict`, enable an arm's alerting, add real-money code, weaken
  the gate to pass, or run write-capable subagents against a shared tree
  concurrently with your own git work.

## 8. DELIVERABLES

1. Working, gate-green, committed code across Phases 0–4 (Phase 5 if earned), all
   arms silent + default-OFF, `strict` byte-identical.
2. `RESEARCH.md` (§3 findings, evidence-backed), `REPORT.md` (§5 certification),
   `DECISIONS.md` (§6 rationale), `PROGRESS.md` (phase log).
3. A one-screen executive summary at the top of `REPORT.md`: the optimal model you
   arrived at, whether it beats naive count and the market today, the honest odds
   and accrual ETA, and the exact human action to promote it if/when ready.

Begin by reading `RUN-COMPLEX-CONSENSUS.md` + its FORGE_DEBATES in full, then open
`RESEARCH.md` and start §3. Take your time. Build the thing that gets better than
the best of them the only honest way — by knowing exactly who they are, where each
is genuinely sharp, how little of that is correlated, and how to weigh and combine
them so the whole is worth more than its best part.
