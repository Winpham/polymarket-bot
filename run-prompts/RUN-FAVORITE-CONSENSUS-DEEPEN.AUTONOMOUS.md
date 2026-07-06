# RUN — Favorite-Consensus: Deepen, Re-verify, Diversify (AUTONOMOUS long-run)

> Paste as a fresh long-running Claude Code session in `~/polymarket-bot`. Self-contained.
> Read `run-prompts/README.md` §"Shared workflow", `REFINED-STRATEGY.md`, and `DATA-MODEL.md` first.
> This is a **research + hardening** run, not a ship-features run. Paper-only. No real money, ever.

---

## 0. One-paragraph mission

We now have materially more data than when the favorite-consensus findings were last written
(top-~250 leaderboard universe instead of a handful of backers/signal, and more days of forward
accrual past the World Cup weekend). **Re-run our favorite-consensus findings on the fuller data,
then try to make the strategy richer, more profitable, and more reliable — but only keep complexity
that survives the belief-blind gate.** The binding question is unchanged: **does the favorite edge
persist out-of-sample across non-soccer regimes, and how much of it is actually copyable at our price?**
Reliability comes from **regime SUPPLY + abstention**, not from threshold-tuning. Deliver an updated,
adversarially-verified findings doc and a verdict per hypothesis (certified / indeterminate-by-power /
refuted), each with its lower-bound number.

## 1. Where we are (the seed findings you are updating)

All prior numbers are from **~2.4 days = one FIFA World Cup weekend (~89% soccer)** — nothing certified.
- Edge = **consensus on FAVORITES**, not blind-tailing. Consensus favorites beat blindly betting
  favorites at the same price by **+10.8pp @ 0.6–0.8** and **+5.9pp @ 0.8–1.0** (information, not just
  favorite-longshot bias). Blind-tailing everyone LOSES (~−0.3% after costs).
- Drop <45¢ longshots → strict favorites **+5.9% CLV / +9.2% realizable, 75% wr (n=408)**.
  Longshots are structurally overpriced and consensus-on-longshots lost hard. **SKIP <45¢.**
- **flat-SHARES, NEVER flat-$** (flat-$ = −$4,584 / P(ruin) 45.6%; the −16% ledger was a longshot×flat-$ artifact).
- **The real lever = TRADER SELECTION and it PERSISTS.** Within-trader H1→H2 copy-return corr **0.338**;
  H1≥10%-edge traders delivered **+16.2% forward**. This became the deployed `proven_router` arm.
- **Proven-router honest read after adversarial verify: ~+5.3% cohort surplus (LB −9.8%), permutation
  null p=0.034, SOCCER-CARRIED (+14%, 62ev).** Below the p≤0.01 bar. Provable copyable floor = **B_LB +3.4%**
  (best copyable wallet `0x99e42eb9` at our repriced entry, Bonferroni) — already in the follow-set.
- **Regime-persistence verdict: SOCCER-ARTIFACT** — 57% of edge mass in expiring regimes; **0/4 recurring
  regimes clear the 10-cluster floor**; MLB + NBA/CBB July cells are net-positive-after-tax → the accrual targets.
- Binding measurement gap = **COPYABILITY TAX** (their fill price vs ours after the move); needs
  `DENSE_CAPTURE` / `signal_price_trajectory` — was 0 rows, now accruing.

**Step 0 of your run: re-establish the CURRENT data inventory** (do NOT trust the numbers above as live).
Count: followed/scored wallets, resolved favorite fills, distinct events, distinct days, and the
sport/regime breakdown, split soccer vs non-soccer. Report the deltas vs the seed. Everything downstream
is conditioned on this inventory.

## 2. The one rule that governs this whole run (read twice)

**Added complexity is a HYPOTHESIS to be killed at the gate, not a feature to ship.** We have repeatedly
paid for "make it more complex": scaling by consensus strength (~8.4%, no lift), best-backer rank
(top10≈top50, no lift), and the N² relational layer (data-starved, overfit, certified 0). A richer model
earns its place **only if it beats the simpler consensus baseline at the belief-blind bar on held-out,
event-clustered, disjoint-regime data.** Otherwise you delete it and say so. "More profitable and reliable"
= a *higher lower bound on realizable, copyable, out-of-sample edge* — never a higher paper headline
(those are mirages we have already debunked: "top traders +80%" = cherry-pick; +4.8% maker = 2 bugs;
+10.2% router = within-event leak).

## 3. The belief-blind gate (SOLE judge — pre-register BEFORE you look)

Before any modeling, write a pre-registration file (`reports/PREREG_<ts>_favconsensus_deepen.md`) with
**frozen thresholds**, mirroring `scripts/asof_preflight.py`. A hypothesis is CERTIFIED only if ALL hold:
1. **As-of & leak-free** — features known at bet time only; split by **WHOLE EVENTS** (the within-event
   leak dropped router persistence 0.21→0.094 — never split rows within an event).
2. **Event-clustered** surplus-over-blind at the event grain (day-clustered SE where days are the block).
3. **Bonferroni lower bound > 3%** margin after the copyability tax, corrected for every arm/cell tested.
4. **≥30 independent events** in the cell (report N_eff, not raw N).
5. **Persistent across ≥2 DISJOINT regimes** (e.g. clears on soccer AND on ≥1 non-soccer sport, or on two
   non-overlapping time blocks). Soccer-only = NOT certified, by rule.
6. **Permutation / label-shuffle null p ≤ 0.01** (beats the shuffle-invariance trap that refuted market_resid).
Anything positive-but-failing = **INDETERMINATE-BY-POWER** (name the failing gate + the LB), not "promising."
Anything that flips sign under the null = **REFUTED**. Log all three honestly.

## 4. Directions to explore — ranked by expected payoff (do them in this order; stop each at its gate)

**A. Re-verify the core on the fuller data (do FIRST, it may move everything).**
Re-run the favorite-consensus surplus-over-blind, the band decomposition (confirm/refute the 60–80¢
sweet spot), the flat-shares vs flat-$ sign, and the longshot block — now on top-250 × more days. Report
whether the +5.9/+10.8pp survives with the bigger universe and post-WC days. This is the honest baseline
every richer model must beat.

**B. Regime diversification — the BINDING path to reliability (highest value).**
The reliability problem is that we can't be all-days-profitable at 2–5 events/day; the fix is **SUPPLY**.
Build/extend a per-(sport × price-band × time-block) cell scoreboard with the full gate applied per cell.
Ask: which non-soccer regimes (MLB, NBA/CBB, tennis, esports) now have enough resolved events to certify,
and do any clear lo>3% on a disjoint cut? A single *additional* certified non-soccer cell is worth more
than any sizing tweak. Also implement/measure **abstention** (skip low-confidence days/cells) and show
whether it raises the LB and the fraction of positive days without threshold-mining.

**C. Trader-selection routing, enriched (the proven lever — deepen it, don't replace it).**
The scorecard is the right adaptivity (frozen procedure, moving data — do NOT build an online/fitted learner;
that is the refuted market_resid class on ~47 correlated days). Candidate enrichments, each gated:
regime-conditional scorecards (a wallet proven in soccer ≠ proven in MLB), conviction/size-weighting
(their >$10k fills were +8.7% vs +2.1% for <$100 — follow size, not every fill), and
survivorship-corrected forward reads (use the `CAPTURE_DROPPED` recovered fills; never read forward on a
set that stops capturing at leaderboard deactivation). Keep the UNION MM-exclusion (two detectors disagree
on ~26 wallets).

**D. Relational consensus layer — the likely real prize, now maybe feasible.**
Pairwise affinity / conditional accuracy ("A is right when B agrees", co-agreement lift over marginal
consensus). This was data-starved at ~3 backers/signal and overfit. With top-250 + more days, test whether
a *low-parameter* version (shrunk, top-K co-signers only, heavily regularized) beats plain rank-weighted
consensus at the gate. **Hard guard:** N² params on correlated data overfit — pre-register the parameter
budget, hold out whole events, and if it doesn't beat simple consensus on the held-out disjoint cut,
**kill it and report the negative.**

**E. Copyability tax, measured forward (the realizable-edge closer).**
Use `signal_price_trajectory` / `DENSE_CAPTURE` (now accruing) to measure the real entry slippage between
the sharp's fill and ours after the move, by band and sport. Convert every "source edge" above into a
**realizable** edge net of the measured tax. Remember: the **2% fee in repo models is a conservative BUFFER,
not a posted charge** (≈0 on most markets) — do not book it as recoverable without live-fill verification.

## 5. Hard constraints (non-negotiable)

- **Paper-only. No real money. No touching the live alert path** (alerts stay OFF / fail-closed for any new
  arm). New strategy arms are measurement instruments, not deployed signals, unless a separate explicit
  Tue-approved deploy step is reached.
- **Cost-zero / Max-subscription only.** Do NOT set or use `ANTHROPIC_API_KEY`. Do NOT spawn child `claude`
  processes. Models: Opus preferred, Sonnet minimum for anything reasoning-heavy — never Haiku.
- **Coordination + isolation (this session WILL edit code and run scripts).** Deploy branch is `main` and
  **auto-deploys on HEAD advance** — so work in a **git worktree**, never on `main` directly. From the
  winmon repo the toolkit is `coord/newchat.sh <slug> "<area>"` → work in `wt/<slug>/`; ship via
  `coord/merge.sh <slug>`. If working purely inside `~/polymarket-bot`, still branch into a worktree and
  keep any new arm alert-OFF. Never bump the winmon→brainstem pointer from here.
- **Adversarial verification is mandatory and SEPARATE from generation.** After any positive result, run an
  independent verify pass (isolated agent / fresh script) whose job is to REFUTE it: check for the leak
  classes above, re-cluster, re-null, recompute the Bonferroni LB. A single-pass positive is untrustworthy
  until it survives this. Default to "refuted/indeterminate" under uncertainty.
- **Self-testing instruments.** Every new script has a self-test (reuse `selection_null.py` /
  `asof_preflight.py` machinery). Reproduce the DODGE map / null baselines as sanity checks.
- **No migration-number collisions** — concurrent chats have caused these; if you add a migration, take the
  next free number and note it. Prefer read-only instruments over schema changes.

## 6. Suggested run shape (Forge discipline, ~multi-hour autonomous)

1. **Inventory (§Step 0)** → 2. **Pre-register frozen gate (§3)** → 3. **Re-verify core (§4A)** →
4. **Build the per-cell regime scoreboard + abstention (§4B)** → 5. **Enrich routing (§4C)** →
6. **Relational hypothesis, gated + guarded (§4D)** → 7. **Copyability tax forward (§4E)** →
8. **Adversarial verify pass over EVERY positive** → 9. **Synthesize.**
Checkpoint after each stage: write intermediate findings to `reports/` so a reap/kill is salvageable
(long background runs get reaped — persist as you go, don't hold results only in context).

## 7. Deliverables

- **`REFINED-STRATEGY.md` updated** (living doc) with the re-verified numbers and every verdict, dated,
  with the seed numbers preserved for diff.
- **A dated final report** `reports/FAVCONSENSUS-DEEPEN_<date>.md`: per-hypothesis verdict
  (CERTIFIED / INDETERMINATE-BY-POWER / REFUTED) + its lower bound + which gate it cleared/failed +
  the data inventory deltas. Lead with the honest headline, not the best paper number.
- **New instrument scripts** (self-tested) for the regime scoreboard, abstention, relational test, and
  tax-adjusted realizable edge — committed on the worktree branch, arms alert-OFF.
- **A 5-dimension self-audit** (novelty / rigor / leak-safety / realizability / reliability) and a
  **≤10-line memory-update note** for the [[project-polymarket-refined-strategy]] and
  [[project-polymarket-consensus]] memory files (what changed, what certified, what got refuted).
- **An explicit "what to accrue next" line** — the specific regimes/cells that are power-limited and how
  many more events/days close them.

## 8. Anti-patterns — do NOT do these (we have already paid for each)

- ❌ Threshold-tuning to manufacture positive days (arithmetically impossible at 2–5 events/day; needs SUPPLY).
- ❌ Trusting any single-pass "positive" (2-bug maker, within-event-leak router, cherry-pick "+80%").
- ❌ flat-$ sizing, or including <45¢ longshots.
- ❌ Splitting rows within an event (within-event leak).
- ❌ An online/fitted ML router on correlated days (refuted market_resid class) — the frozen scorecard IS
  the adaptivity.
- ❌ Reading forward on a wallet set that stops capturing at deactivation (survivorship bias up).
- ❌ Shipping any richer model that doesn't beat simple consensus at the gate — kill it and report the negative.
- ❌ Real money, live-alert changes, `ANTHROPIC_API_KEY`, child `claude` spawns, editing `main` directly.
