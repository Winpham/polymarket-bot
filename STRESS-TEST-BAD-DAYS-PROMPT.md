# Autonomous prompt — "Bad Days": can this system actually lose, and is it worth the risk?

> **How to run.** Paste this whole file as the task for a fresh Claude Code session opened in
> `~/polymarket-bot`, or dispatch it:
> `claude -p "$(cat ~/polymarket-bot/STRESS-TEST-BAD-DAYS-PROMPT.md)"`
> It is a long, self-directed run. Work autonomously to a finished risk memo; only stop for a
> decision that is genuinely Tue's (e.g. "commit real money — yes/no").

---

## 0. Your mission (read this twice)

You are **not** here to confirm the system works. You are a hostile risk officer whose bonus
depends on finding the **realistic path to disappointment or ruin** before real money does.

The consensus-alert engine currently has two "certified-eligible" arms — `favorite`
(LB +3.3% over blind, N≈92) and `elite_fresh_fav` (LB +4.8%, N≈38) — that survived a
selection-null permutation test (p=0.0000), an at-fire entry gate (D6), and a
belief-blind promotion gate (D7). Everything is **paper-only**; real money is gated on
N≥50 per arm and ≥5 regimes post-Wimbledon.

The question Tue actually needs answered is blunt:

> Over a **long** horizon (assume 1–3 years, hundreds of slates, multiple sport seasons),
> in a **realistic** world that is *not* all good days — edges decay, costs drift, favorites
> get upset in clusters, the data pipeline misses fires, the leaderboard cohort regresses —
> does this system stay **reliably** and **diversely** profitable enough to be **worth the
> risk of real capital**? Or does a normal bad run make it a coin-flip (or worse) dressed up
> as an edge?

Produce an honest **go / no-go / not-yet risk memo** with numbers, not vibes. You are
authorized — expected — to conclude **"not worth it"** or **"not yet"** if that is where the
evidence points. A sycophantic "looks great" is a failure of this task.

### The one fact that dominates everything
The entire evidentiary base is **~4 days of live data** — one World-Cup weekend plus part of
one Wimbledon fortnight. `portfolio_concentration.py` exists precisely because N_eff is tiny
and CIs are wide. **Therefore you cannot answer the mission by bootstrapping the observed
record alone** — the record is too short to have *contained* a real bad regime. Empirical
bootstrap tells you about variance *within the good days you happened to see*. The mission
requires you to **inject failure the record has not yet shown** and ask whether the sizing
policy, the caps, and the adaptive overlay survive it. Treat "we haven't seen a bad regime
yet" as the central danger, not as reassurance.

---

## 1. Hard ground rules (do not violate)

- **Cost-zero.** Max subscription only. Never set or use `ANTHROPIC_API_KEY`. Do not spawn
  child `claude` processes. Reasoning is analysis-heavy — use your own Opus-level reasoning;
  no Fable needed.
- **Paper-only, read-only against reality.** Read the live Postgres
  (`docker exec polymarket-bot-postgres-1 psql -U bot -d polymarket --csv -c "…"`) and the
  frozen `reports/*.json`. **Never** write to the live DB, **never** mutate `honest_paper_ledger`,
  **never** place or simulate a real order.
- **Never edit an applied migration** (even a comment) — it re-checksums and crash-loops the
  app. Migrations are immutable. Same for any file the running daemon reads live.
- **Isolate your work.** Put every scratch script and artifact under `scripts/stress/` and
  `reports/stress/`. Do not touch `main`'s behavior. If you write code, it is analysis code
  that runs offline. Don't disturb the running daemon or the coordination of other repos.
- **Reuse, don't rebuild.** The repo already ships block-bootstrap MC (`risk_engine.py`),
  ICC/N_eff/HHI (`portfolio_concentration.py`), permutation nulls (`selection_null.py`),
  a 5-attack adversarial battery (`adversarial_battery.py`), within-signal decay
  (`decay_analysis.py`), the MATCH-clustering primitive (`superkey.py`), and the adaptive
  state machine (`map_state.py` / `map_checkpoint.py`). Extend these; every new script gets a
  `--selftest` that exits non-zero on failure, matching house style.
- **Honesty over completeness.** If a scenario is untestable on this data, say so and mark it
  INDETERMINATE-BY-POWER — do not manufacture a number. Distinguish "refuted," "survived,"
  and "unknown." Wide CIs are a finding, not an embarrassment to hide.

---

## 2. Establish the ice you're standing on (Phase 0)

Before breaking anything, document the real evidentiary base — this frames every later claim.

1. Pull current certified state per arm from `consensus_signals` (event-clustered on
   `COALESCE(event_slug, condition_id)`): N events, N distinct regimes, realized surplus vs
   `_blind`, and the **corrected lower bound** the promotion gate uses
   (`promotion::surplus_bounds`). Refresh `reports/risk_engine.json`,
   `reports/portfolio_concentration.json`, and the honest ledger stats.
2. Report the **effective** sample size, not the nominal one: N_eff after ICC at MATCH /
   SLATE / REGIME grain, and `1/HHI` effective buckets by regime, event-day, tournament.
   State the widest 95% CI on each arm's edge. If N_eff for `elite_fresh_fav` is in the
   teens, say so in bold.
3. Write down, explicitly, the **calendar span** of the data and which sports/tournaments it
   covers. This is the denominator for "how much have we actually observed."

Deliverable: `reports/stress/00-baseline.md` — "here is exactly how thin the ice is."

---

## 3. The failure taxonomy (Phase 1)

For each failure mode below: (a) state the **mechanism** in one sentence, (b) say **how you'll
simulate it** with named machinery, (c) pre-register a **kill-criterion** — the numeric result
that would count as "this failure mode alone makes it not worth the risk." Pre-registering
before running is mandatory (it's the anti-p-hacking discipline this repo already uses).

**F1 — Thin-edge variance (the edge is real but small, and variance dominates a human).**
Even a true +3% edge produces long red stretches. Extend `risk_engine.py` horizons to
1–3 years of slates. Report: longest losing streak (events and calendar weeks), max
time-underwater, P(ledger net-negative at 3/6/12 months | edge is genuinely +3%), and the
peak-to-trough drawdown distribution under `kelly_eighth_capped` and `flat_shares_capped`.
The point: would a normal person conclude "it's broken" and quit during a stretch that a true
edge produces anyway?

**F2 — Edge decay to zero (efficiency catches up / the trade gets crowded).**
Use the built-in `edge_mult λ` stress path in `risk_engine.py` (`won_eff = c + λ·(won − c)`,
output key `edge_stress`). Sweep λ ∈ {1.0, 0.75, 0.5, 0.25, 0.0}. Then go further than the
script does: model **λ as a declining function of time** (edge intact at go-live, half-life
of e.g. 3/6/12 months). Critical output = **detection latency**: given the promotion/honest
gate thresholds (`MIN_PILOT_ROI 0.02`, `PILOT_MIN_EVENTS 50`, selection-null p≤0.01), how many
events and how many dollars bleed out *before the system's own gate would pull the arm*? That
gap is the loss budget for being wrong. Kill-criterion candidate: detection latency costs more
than the cumulative edge earned before decay.

**F3 — Null-edge survivor (multiplicity / the market_resid trap, generalized).**
The certified winners survived one selection-null. But **count the full family of arms ever
tested** — every `StrategyDef` in `default_portfolio()`, `trust_arms()`, `retuned_arm()`, plus
any refuted/parked ones (market_resid, congregation, longshot, etc.). Estimate the effective
family-wise error rate. Re-run `selection_null.py` and the full `adversarial_battery.py` (F1–F5
attacks), then simulate the certification pipeline end-to-end on **synthetic-null / label-
permuted** data across the *whole* search and measure how often *some* arm emerges "certified-
eligible" by chance. Recall the market_resid lesson: a +30% "surplus" was a baseline artifact
that a 0-baseline gate false-promoted. Kill-criterion: a null world produces a
certified-looking winner at a rate that makes the two real winners unremarkable.

**F4 — Costs worse than modeled (the +EV is only +EV on paper).**
After CLV−haircut, *only* favorite-tilted strategies are +EV, and the margin is thin. Current
constants: `FEE_PCT 0.02`, `EXEC_HAIRCUT 0.01` (Rust) / 0.005 (Python). Stress: sweep haircut
and fee up 2×–5×. Add a **liquidity-limited fill model** specific to Polymarket — on the
favorite side (price band 0.80–0.97) the book is thin at the exact odds you want, so model
partial fills and worse-than-mid execution; add resolution/dispute risk as a small
probability of a graded-loss even on a "won" market. Question: does `favorite` stay above the
0.03 promotion margin once execution is realistic? Kill-criterion: favorite's corrected LB
goes ≤0 under a 2× haircut + adverse-fill model.

**F5 — Correlated bad days (no diversification when you need it).**
Concentration analysis already found `elite_fresh_fav ⊂ favorite` (adds ~0 diversification) —
on a bad slate most of your bets are *the same bet*. Use the block bootstrap's
`(regime × UTC-day)` blocks, but **inject an upset-heavy regime the record has not seen**: a
tournament/period where favorites underperform their price (a realistic sports phenomenon —
Cinderella runs, high-variance formats, motivated underdogs). Report worst single slate loss,
worst week, and worst month at the recommended sizing, and how those scale with per-slate and
per-regime caps (`CAP_MAX_PER_SLATE`, `CAP_REGIME_FRAC`, `CAP_STOP_LOSS_UNITS`). Kill-criterion:
a plausible upset cluster breaches the drawdown ceiling (`DD_CEIL 0.30`) more than
`DD_CEIL_P 0.10` of the time.

**F6 — Regime shift / sport drought (the edge is regime-conditional and the regime changes).**
The edge was certified on tennis + World Cup + MLB. Simulate the calendar moving to a regime
where either (a) no markets qualify (drought → no fires → opportunity cost, or pressure to
loosen filters and bet worse), or (b) the favorite bias is absent/reversed. Then test the
**adaptive overlay's reflexes**: run `map_state.py` / `map_checkpoint.py --selftest`-style
scenarios where a cell flips from winning to losing and measure DODGE latency and THRASH
behavior. Does the state machine pull out fast enough, or does it either lag (bleeding) or
thrash (whipsawing in and out)? Kill-criterion: overlay's regime-change response is slower
than F2's loss budget, i.e. adaptivity doesn't actually save you.

**F7 — Signal-source regression (the leaderboard cohort was lucky, not skilled).**
The signal is "follow consensus among top leaderboard traders." Top-N traders in one period
are partly *lucky* and regress. Model turnover in `followed_traders` and ask: how much of the
measured edge is attributable to a cohort that won't persist? Split-half persistence across
time (adversarial_battery F3) and a cohort-reshuffle simulation. Kill-criterion: edge does not
persist out-of-cohort, i.e. you're chasing last period's luck.

**F8 — Operational failure & adverse selection (you don't get the fills you backtested).**
Capture-LEAD misses mean firing late at a drifted line → CLV negative, and worse, **adverse
selection**: the good lines get taken first, so the fires you *successfully* capture are
systematically the *leftover worse* ones. Also model: daemon wedge (there's precedent — an
audit-log cross-process race once wedged the daemon), autoupdater deploying stale `main`,
leaderboard API staleness/pagination gaps, migration-number collisions from concurrent work.
Use `signal_price_trajectory` (dense ~45s post-fire mids) to quantify how much edge is lost per
minute of delay (this is `decay_analysis.py`'s follower-tax vs delay-decay split). Inject an
X% missed-fire rate with an adverse-selection bias on captured fills. Kill-criterion: realized
edge after realistic capture failures + adverse selection falls below the promotion margin.

---

## 4. The composite "realistic bad life" simulation (Phase 2 — the core deliverable)

Isolated scenarios flatter the system. A real 1–3 year run has **several** of these happening
**at once and partially**. Build a scenario generator (`scripts/stress/bad_life_mc.py`, with
`--selftest`) that draws a **world** and runs the *actual* sizing policy through it:

- A **world** = (edge-multiplier path λ(t) drawn from intact → decaying), (cost level drawn
  from modeled → 2–3× worse), (a regime sequence over a plausible sport calendar including at
  least one upset-heavy stretch and one drought), (an operational-failure/adverse-selection
  rate), and (the leaderboard-cohort persistence factor from F7).
- Run the recommended policy end-to-end through each world: `kelly_eighth_capped` sizing,
  flat-SHARES not flat-$, all caps active, and the adaptive overlay making DODGE/PRIORITIZE
  decisions with its real latency. Monte Carlo over ≥10k worlds (reuse `risk_engine.py`'s
  `N_PATHS`, block structure, and RNG seed discipline — seed constant for reproducibility).
- Report the **full outcome distribution, tail included**:
  - P(net negative after 12 months) at bankrolls {1k, 5k, 25k};
  - median and worst-decile terminal bankroll; P(ruin at 20%); P(maxDD > 30%);
  - longest underwater stretch in calendar weeks;
  - and the human factor: **P(a reasonable operator pulls the plug mid-run** because the paper
    ledger looks dead for K consecutive weeks**), and whether pulling the plug then would have
    been correct** (edge truly gone) **or a false alarm** (edge intact, just variance). This
    false-alarm-vs-true-kill matrix is what separates "risky but survivable" from "unrunnable
    by a human."

The composite result — not any single scenario — is the answer to the mission.

---

## 5. Confront the tiny-N problem honestly (Phase 3)

Quantify how much of any "it works" conclusion is **supported** vs **assumed**:

- Given current fire rates per regime, how many **calendar weeks of real forward paper data**
  are needed to reach the go-live gate (N≥50 per arm, ≥5 regimes)? What's the expected wait?
- What fraction of the composite-MC's favorable outcomes depend on parameters (edge size,
  haircut, cohort persistence) that are currently **point-estimated from ~4 days**? Redo the
  composite MC with those parameters drawn from their **actual wide posteriors** (wide CIs from
  Phase 0), not point values. The honest answer to "is it worth the risk" may be **"unknown
  until N — and here is the expected cost, in time and paper-loss variance, of finding out."**
  That is a legitimate, valuable conclusion. State it plainly if true.

---

## 6. Adversarial self-review (Phase 4 — don't skip)

Before writing the verdict, red-team **your own stress test**. Spawn an independent skeptic
pass (a fresh reasoning pass, stance = "this stress test went easy on the system") that hunts
for: optimistic assumptions you slipped in, a failure mode from §3 you under-modeled,
bootstrap that leaked good-day structure into "bad" worlds, a cap that only works because the
tiny record never stressed it, or a kill-criterion you set too lenient. Fix what it finds and
re-run. Loop until the skeptic can't find a soft spot. A sycophantic self-review is worse than
none — reward the skeptic for real holes.

---

## 7. Verdict & deliverables (Phase 5)

Write `reports/stress/VERDICT.md` and a dated entry under `reports/entries/`. Include:

1. **Bottom line, first line, unhedged:** GO / NO-GO / NOT-YET, at what bankroll, under what
   guardrails. If NOT-YET, state the specific N / regimes / forward-weeks that would flip it.
2. **Ranked failure table:** each F1–F8 by (plausibility × expected damage), with its
   pre-registered kill-criterion and PASS / FAIL / INDETERMINATE-BY-POWER verdict.
3. **Drawdown / ruin table:** per policy × horizon × stress level (from the composite MC).
4. **Detection-latency table:** for edge decay, dollars bled before the gate pulls the arm.
5. **Guardrail spec** (concrete, implementable): max exposure per slate/regime/bankroll,
   stop-loss units, per-regime min-N before real money, an automatic decay-pull trigger, a
   cost-drift monitor, and a live CLV / adverse-selection monitor with a numeric alarm.
6. **The honest "worth it?" paragraph:** is the edge diverse enough (or is it one favorite bet
   wearing two names)? Reliable enough to survive a normal bad year? Is the expected return
   *net of realistic costs and the cost of the learning period* worth the tail risk and the
   operator attention? Be willing to say the juice isn't worth the squeeze.

### Pre-registered "NOT worth the risk" triggers (decide these BEFORE running §4)
Conclude NO-GO (or NOT-YET pending fixes) if **any** hold under the composite realistic-bad MC:
- P(net negative after 12 months at recommended sizing) **> 35%**; or
- P(drawdown > 30% of bankroll) **> 10%** (the repo's own `DD_CEIL_P`); or
- `favorite`'s corrected LB goes **≤ 0** under a 2× haircut + adverse-fill model (F4); or
- edge-decay **detection latency** costs more than the cumulative edge earned pre-decay (F2); or
- the two winners are **not distinguishable from the multiplicity null** once the full arm
  family is counted (F3); or
- the "reasonable operator pulls the plug" event is a **false alarm** in a majority of worlds
  where the edge was actually intact (§4) — i.e. the strategy is real but **unrunnable by a
  human**.

---

## 8. When done

- Print a tight summary to the terminal: the one-line verdict, the ranked failure table, and
  the three numbers that most drove the verdict.
- Leave all artifacts under `reports/stress/`; do not merge anything to `main` behavior or
  touch the live ledger.
- Note for memory (Tue will decide whether to save): update the polymarket-consensus memory
  with the verdict, the binding failure mode, and the guardrail spec — honestly, including any
  INDETERMINATE-BY-POWER results.

Remember the whole point: **find the realistic way this loses.** If you can't find one after
genuinely trying, that itself is the finding — but you must have genuinely tried.
