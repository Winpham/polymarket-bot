# GO-LIVE PRE-REGISTRATION — real money on `weather_fav`

**Frozen 2026-07-13, BEFORE any real-money decision.** Everything below is written now, while nothing is
at stake, precisely so it cannot be rationalised later when it is. **Floors may be ADDED, never loosened.**

**Current verdict: DO NOT GO LIVE.** Not because the edge looks bad — it looks plausible — but because
the number that decides it **has never been measured on clean data**, and one unresolved question could
make the entire edge a mirage. Both are fixable. Neither is fixable by more analysis of existing data.

---

## 1. THE MIRAGE RISK — the one that would actually lose money

**Open question: do we need a sharp AT ALL?**

Two `selection_null` runs bracket it, and they disagree because they use different null pools:
- vs a **random weather favourite** in the same band×day: **p = 0.0005** (consensus looks skilled)
- vs a favourite **one sharp already bought**: **p ≈ 0.5** (consensus adds ~NOTHING over a single sharp;
  the head-to-head is **+0.14pp** — nothing, while discarding 30% of the signals)

Chain that with the weather-deepen finding that a "better" sharp is no better, and the live hypothesis is:

> **The mid-favourite BAND does the work. The sharps may be adding nothing at all.**

If true, then (a) the entire copy/consensus/latency/ingestion apparatus is unnecessary, and — far more
dangerous — (b) **the "edge" may simply be favourite-longshot bias**, a well-known market artifact, in
which case it is *not alpha*, it will not survive costs, and real money loses.

**This MUST be settled before real money. It is the highest-value work outstanding.**

### The test (and why it is not trivial)

A **neutral-reference truly-blind pool**: every weather market on a day — *including ones no sharp ever
touched* — priced at a NEUTRAL reference time, band-filtered, compared against the sharp-selected subset.

- The pool is enumerable: event slugs are constructible (`highest-temperature-in-{city}-on-{month}-{day}`),
  confirmed working against Gamma.
- **The blocker is the PRICE.** Gamma returns only final prices (1/0) for closed markets. The sole
  historical source is CLOB `prices-history` — **the exact source that FAILED validation in this run**
  (`atfire_recon.py`: MAE 22¢, corr 0.20 vs real captured mids). Suspected cause is a token-index mapping
  bug in our code rather than the endpoint, but **it is unproven either way.**
- ⇒ **Step 1 is to fix and VALIDATE the historical price source** against the 85 real captured
  `entry_ask_mid` values (acceptance: MAE ≤ 3¢, |bias| ≤ 1¢, corr ≥ 0.90). **No neutral null may be run on
  an unvalidated price source** — that is how we would fool ourselves into betting real money.
- A `ts0`-anchored pool is **entry-timing-biased and will flatter us.** The reference must be neutral.

**If the sharps add nothing over the band, and the band is favourite-longshot bias: STOP. There is no
business here.** That is a completely valid, money-saving outcome.

## 2. HARD GATES — ALL must be green before one real dollar

- [ ] **G1 — clean basis.** ≥2 disjoint weeks of **decision-time** `entry_ask` captures (lag p50 < 15 min)
      in the **0.71–0.90** band, ≥20 day-clusters with a captured ask AND a resolution.
      *(Blocked: the D4 fix `e74f4e7` is NOT deployed. The clock has not started.)*
- [ ] **G2 — the gate passes at OUR price.** θ = cluster-robust 95% LB of ROI-on-turnover at the captured
      `entry_ask`, day-clustered, **> 0**, surviving **LODO-by-week**, passing `selection_null`, and
      **beating +5.6%** *after* charging measured slippage at the intended size.
- [ ] **G3 — the mirage is ruled out** (§1): the neutral-reference blind null, on a VALIDATED price source.
- [ ] **G4 — re-run post-`deep-universe`.** The `startTs` fix changes the input: we under-detected
      convergence (in-sample coverage 69–100% on the wider universe). More backers per market may change
      which markets qualify. **Re-run G2 after the re-ingest; the edge may move either way.**
- [ ] **G5 — execution proven on paper, forward.** Paper-execute at the REAL ask, at the REAL $50 size,
      and reconcile modelled fills against what the book actually gave. **We have never placed one order.**
- [ ] **G6 — legal/ToS posture settled by a human.** Not a technical gate. Market-making was killed partly
      on US-ToS grounds; automated real-money trading needs an explicit decision. **Tue's call, made BEFORE
      engineering, not after.**

## 3. RISK LIMITS (frozen now, while nothing is at stake)

Sizing is already measured (`CAPACITY-SCAN.json`), and it is **small**:

| limit | value | why |
|---|---|---|
| **per signal** | **$50** | net **+8.6%** at the p90 (bad) book, 100% fillable. $100 fails at p90 if the true edge is 9pp not 12pp. |
| **per DAY** | **$1,000** | ~20 signals × $50. **The DAY IS ONE CORRELATED BET** — a heat dome resolves ~20 cities together. This is a single ~$1k position, not 20 independent ones. |
| **daily loss cap** | **$300** | hard stop; halt for the day, no discretion. |
| **drawdown kill-switch** | **−$1,500 cumulative** | full stop, human review required to resume. |
| **max concurrent days** | 1 | never stack correlated days to chase a loss. |
| **sizing rule** | **flat SHARES, not flat $** | established; ⅛-Kelly cap. |

**Expected economics if G1–G6 all pass:** ~$1,000/day at ~+8.6% ⇒ **order of $85/day gross**, before our
own market impact (**unmeasured** — the capacity curve walks a SNAPSHOT book, so real capacity is ≤ that).
**Variance is that of one $1k bet per day: long losing streaks are EXPECTED and will be indistinguishable
from the edge being dead.** Pre-commit to the kill-switch now, because you will not want to pull it later.

**This is not a large business.** Decide whether that is worth the operational and legal risk **before**
building the order path, not after.

## 4. THE EPISTEMIC WARNING (earned, not rhetorical)

In this single run I produced **four confident, wrong results** — two of which **reversed sign** under
audit (a "catastrophic −57% at the ask" that was a filtering artifact; a "latency is the dominant cost"
that a placebo test killed at p=0.36). Every one of them looked like a finding until it was controlled.

> **RULE: no claim justifies risking money without (a) a control/placebo arm, (b) a significance test,
> (c) explicit n + dispersion.** A number without those is a hypothesis.

**Nothing in this repo currently arms real money, and nothing should until G1–G6 are green.**
