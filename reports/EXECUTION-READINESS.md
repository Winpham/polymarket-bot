# EXECUTION READINESS — is this ready to trade, provably profitable, accurate, with enough edge?

**Verdict as of 2026-07-13: NO. Not ready. It is not yet PROVEN profitable, and it cannot be — the one
number that decides it has never been measured on clean data.**

This is not pessimism. Every fix required is already built; what is missing is *time on a fixed pipeline*.
Below is the exact ledger, in dependency order, with hard gates. Nothing here is a matter of opinion.

---

## A. Why it is NOT provably profitable yet (the blocker)

**The frozen gate accepts exactly one basis: `entry_ask` — the price WE actually pay.** Every other number
(sharps' fill, vote-mean, at-fire "mid") is a proxy that this run proved unreliable.

And `entry_ask` was being captured **wrong** until yesterday (D4): the decision-time lane was starved, so
captured asks averaged a **173-minute lag** and were **loser-tilted** (raw edge −1.04% vs +1.71% for clean
decision-time captures), and 69% of the weather arm's asks landed in the **dead ≥0.90 band**.

⇒ **The arm has been accruing data that could never have certified it.** The fix (commit `e74f4e7`) is on
this branch and **is not deployed**. So the clock on clean data has **not started**.

**No amount of re-analysis substitutes for this.** It is blocked on time, not on cleverness.

## B. What IS established (survived audit: control + significance + n)

| fact | n | evidence |
|---|---|---|
| copier cost ≈ **+1.14¢** (drift ~0, spread 1.2¢) | 1,351 | corroborated independently at ~2¢ |
| **capacity: $50/signal** → net **+8.6%** at the p90 (bad) book, 100% fillable | 33 live books | direct depth observation |
| `weather_fav` survives **LODO-by-week**, LB **+7.1%** at the copier price | 571 | belief-blind null p=0.0005 **+** leave-one-week-out |
| the BOOK, not the spread and not latency, is the binding constraint | — | slippage $250 = 9.5¢ ≫ spread 1.2¢ ≫ latency ~2¢ (n.s.) |

**So the edge is plausible and the size is known. What is missing is proof at OUR price.**

## C. The readiness ladder (do NOT skip a rung)

**Rung 1 — deploy the fixes. (Blocked on: human. Nothing accrues until this happens.)**
- [ ] Merge this branch → the D4 fresh-first ask capture goes live. **This starts the clock.**
- [ ] Merge/deploy the `startTs` ingestion fix (`feat/deep-universe-1000`) — steady-state coverage is
      **90%** on the busiest wallets (audited today), and the loss is *systematic* (drops the oldest
      events in a burst) ⇒ convergence can be detected late.
- [ ] Add weather to the `clob_price_tape` subscription set — **the tape has ZERO weather rows**, so our
      own live arm's realizable price is currently unmeasurable.
- [ ] (cheap, high value) `seen_at DEFAULT now()` on `trader_fills` — ingestion latency is invisible
      without it. *Needs a migration.*

**Rung 2 — accrue clean data. (Blocked on: TIME. ~2–3 weeks. No shortcut.)**
- [ ] ≥2 disjoint weeks of **decision-time** `entry_ask` captures on `weather_fav`, in the **0.71–0.90**
      band (not deep chalk).
- [ ] Gate: ask-capture p50 lag **< 15 min** (was 75 min) — verifies the D4 fix actually took.
- [ ] Gate: ≥20 day-clusters with a captured ask **and** a resolution.

**Rung 3 — re-run the frozen gate on the clean data. THE decision point.**
- [ ] θ = cluster-robust 95% LB of ROI-on-turnover **at the captured `entry_ask`**, day-clustered.
- [ ] Must clear: **LB > 0**, survives **LODO-by-week**, passes `selection_null`, and beats the champion's
      **+5.6%** floor **after** charging the measured slippage at the intended size.
- [ ] **If it fails: STOP. Retire the arm.** A failed gate here is a successful run.

**Rung 4 — resolve the question that could make all of the above moot.**
- [ ] **Do we need a sharp AT ALL?** The two nulls bracket it: **p=0.0005** vs a random-favourite pool, but
      **p≈0.5** vs a pool of favourites *one sharp already bought*. If consensus adds ~nothing over one
      sharp, and one sharp adds ~nothing over the mid-favourite **band**, then this is a standalone
      band-inefficiency rule — **and the entire copy/latency/ingestion apparatus is unnecessary.**
- [ ] It also raises the sharpest risk to the whole thesis: **if the "edge" is just the mid-favourite band,
      it may be favourite-longshot bias, not alpha.** Must be tested against a NEUTRAL-reference blind pool
      (a `ts0`-anchored pool is entry-timing-biased and will flatter us).

**Rung 5 — prove EXECUTION, not just selection. (Never yet attempted: we have never placed one order.)**
- [ ] Paper-execute at the real ask with the real $50 size, forward, and reconcile fills vs the model.
- [ ] **Our own market impact is unmeasured.** The capacity curve walks a *snapshot* book — it does not
      model us moving the price, makers pulling quotes on size, or other copiers racing us. Real capacity
      is **≤** the measured number.
- [ ] Then, and only then, the smallest real size that is worth the operational risk.

## D. Is the edge "enough"?

Honest arithmetic **if** Rung 3 passes at the measured numbers:
- $50/signal × ~20 weather signals/day ≈ **$1,000/day deployed**, at **~+8.6% ROI-on-turnover** (p90 book)
  ⇒ **on the order of $85/day gross**, before our own impact and before any operational cost.
- **But the day is ONE correlated bet** (a heat dome resolves ~20 cities together), so the variance is that
  of a single ~$1,000 position, not twenty independent ones. Expect long losing streaks at this N.

**So: the edge is thin-but-real-looking, and the CAPACITY is small.** It is not a large business. Whether
that is "enough" is your call — but it should be made with the correct number, and the correct number does
not exist until Rung 3.

## E. The standing rule (earned the hard way — four retractions in this run)

Every error in this run had the same shape: **a number computed without a control, on small n, from a
column or population that had not been validated.** Two "results" reversed sign under audit.

> **No claim ships without (a) a control/placebo arm, (b) a significance test, (c) explicit n + dispersion.
> A number without those is a hypothesis, not a result — and must never be the basis for risking money.**

**Bottom line: do not trade this yet. Deploy the fixes, let it accrue, then let the frozen gate decide —
and be genuinely willing to hear "no".**
