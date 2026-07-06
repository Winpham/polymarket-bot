# PRE-REGISTRATION SEAL — FORWARD-TRACK INSTRUMENT (beat-best-trader, Cycle 6)

**SEAL (UTC): 2026-07-06T06:25:17Z** · branch `run/beat-best-trader` · PAPER-ONLY · promotes NOTHING ·
arms NOTHING · no Rust/migration change · DB read-only · cost-zero (Max-only).

This document is **frozen at the seal timestamp above**. It freezes the candidate plays, the exact
eligibility screen, the success metric, and the full GO gate. The forward-track instrument
(`scripts/forward_track.py`) evaluates ONLY rows with `first_seen ≥ SEAL` (forward-only; no peeking at
pre-seal data). Nothing here may be re-tuned to pass; a change to any floor is a NEW seal with a new
timestamp. If any play ever clears EVERY gate the instrument raises **GO-CANDIDATE → ESCALATE TO HUMAN**
(it never auto-promotes/arms — a GO on thin data is more likely a bug than an edge; we demand the months).

> **Why this run goes dormant here.** Five cycles established: reliability *persists* out-of-sample
> (ρ=0.22, belief-blind, n-strata-confirmed); the best *realizable* play is tailing the single best
> reliable trader, NOT a diversified book (the book adds drawdown per return at our price); the real
> follower tax is ~1.0¢ band-aware (the modeled 2.9¢ was too harsh — a partial modeling artifact); real
> λ̂=0.136 (CI-lo 0.065, far below the 0.25 edge-reality floor → the favorite surplus is still mostly
> longshot bias, not information); and **nothing clears the belief-blind gate on the current ~5-day
> record**. The ONE remaining lever is forward accrual over months of independent non-soccer regimes.
> This seal freezes the candidates so that lever can be pulled unattended.

---

## 0. Candidate plays (FROZEN wallets — pinned, no re-selection forward)

Tue's Cycle-6 refinement re-ranks candidates under an **anti-longshot / reliability-of-source** screen
and **high-volume + long-term** floors (§1). Named metrics below are the their-price → corrected-tax
(~1.0¢ band-aware) realizable ROI, %longshot (share of events priced < 0.35), and n_events used to
re-rank; they are provenance for the freeze, not forward results.

| play | name | wallet | role | n_ev | %LS | corrected-tax ROI |
|---|---|---|---|---|---|---|
| **PLAY-A** | **master-wuji** | `0x96a3a4d0f0a91074a43ce8dc39d1f092a717d944` | single-best reliable **TAIL** (high-vol, low-longshot) — the best realizable play across all 5 cycles | 103 | 19% | +12.4% |
| **PLAY-B** | **DaBossHogg** | `0x6157d529ae129fe08f22a27ed42e741d2eaa9fb4` | best high-volume **LOW-longshot** alternative — highest volume of any name (282 ev), near-zero longshot (2%), steady; the purest durable-skill diversifier on the reliability-of-source axis | 282 | 2% | +4.4% |
| **PLAY-C** | **equal-weight survivor BOOK** | {master-wuji, acorp, Sportbetting76, DaBossHogg} | the diversification benchmark PLAY-A must beat / be beaten by; equal-weight because Cycle-4 proved equal wins OOS (covariance methods collapse to equal on near-disjoint days) | — | — | — |

**PLAY-C book members** (flat / equal weight):
- master-wuji `0x96a3a4d0f0a91074a43ce8dc39d1f092a717d944` (103 ev, 19% LS, +12.4%)
- acorp `0x99e42eb9038705165b22f821e27659c1dc41e4c4` (131 ev, 21% LS, +14.3%)
- Sportbetting76 `0xe5241830e8876c115d7dc8311ad9f43d85fdd34f` (128 ev, 31% LS, +19.1%)
- DaBossHogg `0x6157d529ae129fe08f22a27ed42e741d2eaa9fb4` (282 ev, 2% LS, +4.4%)

**PLAY-B selection rationale (frozen):** PLAY-B is defined as *"the best high-volume LOW-longshot
alternative to the PLAY-A tail."* DaBossHogg maximizes exactly that axis — it is simultaneously the
**highest-volume** (282 ev, 2.7× any other survivor) and the **lowest-longshot** (2%) name, i.e. the most
durable-skill / least-luck source in the pool. acorp (+14.3% ROI, 131 ev, 21% LS) is the documented
runner-up but sits in the same higher-longshot/return profile as PLAY-A, so it diversifies the
*reliability-of-source* axis less; it is retained inside PLAY-C. Choosing DaBossHogg as PLAY-B gives the
cleanest A-vs-B contrast: high-ROL-longshot tail (A) vs high-volume near-zero-longshot workhorse (B).

**EXCLUDED from candidates (with reason — the screen working, not a false negative):**
- **Villson** `0xdc40c985...` — **57 events**, fails the ≥100 high-volume floor (§1.2). It was only ever
  admitted when Cycle-4 widened into the longshot band; under the frozen screen it is OUT.
- **djokowin** `0x1420b746...` — **53% longshot**, fails the ≤40% longshot-exposure cap (§1.1). Its ROI
  swings +1.2% → +16.0% between old/new tax — the longshot signature Tue wants OUT.
- **pfk.bgd** `0x92d8a88f...` — **58% longshot**, +64.7% new-tax ROI — the archetype of "abnormally high
  margin from recent longshot success." Fails the longshot cap; excluded.

---

## 1. FROZEN ELIGIBILITY SCREEN (all conditions; event-clustered at THEIR price unless noted)

A wallet is eligible iff it clears **every** condition. The plays above already clear it on the pre-seal
record; forward, the instrument RE-CHECKS eligibility on the accrued (post-seal) record and drops any
play that stops clearing it (with the failing condition named).

### 1.0 Base directional / profit-source screen (from `reliability_score.py`, carried forward)
- **Relaxed round-trip MM screen τ_rt = 0.50** (vs the frozen 0.30): admit directional wallets, exclude
  arbers / pure market-makers. Other microstructure screens frozen (TSR 0.25, SBR 0.50). Not a bot.
- **Profit-source = directional net-maker**: strength/skill must come from prediction (calibration gap),
  not two-sided rebate capture. MM-flagged and bot-flagged wallets are excluded.
- Positive calibration gap at their price; per-wallet **belief-blind skill null** p ≤ 0.05 (H0: each fill
  ~ Bernoulli(its fill price) ⇒ cal_gap null-mean = 0 exactly); ≥ 2 positive disjoint sports.

### 1.1 ANTI-LONGSHOT / RELIABILITY-OF-SOURCE filter (NEW — Tue, Cycle 6)
Exclude wallets whose profitability is driven by longshot luck rather than durable skill. **Longshot band
= entry price < 0.35**, event-clustered, at their price.
- **(a) Longshot-exposure cap:** exclude if **share of events with entry price < 0.35 is ≥ 40%**.
  (Data: pfk.bgd 58% LS, djokowin 53% LS — both excluded; survivors 2–31% LS.)
- **(b) Drop-best-events robustness:** remove the wallet's **top 3 winning events** (by realized P&L
  contribution). If realizable ROI at the corrected (~1.0¢ band-aware) tax **flips ≤ 0**, the wallet is
  longshot/luck-driven ⇒ exclude. Reliability must survive removal of its best hits.
- **(c) Longshot-stripped profitability:** with all longshot (price < 0.35) events **removed**, the
  wallet must remain **profitable at the corrected tax** (realizable ROI > 0).

### 1.2 HIGH-VOLUME + LONG-TERM floors (NEW — Tue, Cycle 6; raised from the old 30/50)
- **Volume:** ≥ **100** distinct resolved events (was 30).
- **Span:** ≥ **20** distinct active days (long active span, not a hot streak).
- **Sustained (not recent-only):** realizable ROI at the corrected tax is **positive in BOTH time-halves**
  of the wallet's active span (early-half and late-half each > 0), i.e. profitability is sustained across
  the span, not carried by a recent burst.

---

## 2. SUCCESS METRIC (frozen)

**Realizable Calmar** = mean-day-return ÷ max-drawdown of the equity curve, computed at the **MEASURED
band-aware follower tax (~1.0¢)** — Win #1 baked in: use the per-band measured tax from
`reports/real_tax.json` (market-clustered mean per band; fall back to `FOLLOWER_TAX = 0.013` only for a
band with no measured tax). **Do NOT use the old flat 0.013 reprice.** Flat-SHARES, event-clustered at
`COALESCE(event_slug, condition_id)`, **out-of-sample = forward-only** (all rows `first_seen ≥ SEAL`).
Siblings reported for robustness: MAR (total/maxDD), return/CVaR₅. Distinguish their-price (skill) vs
our-price (realizable) everywhere.

---

## 3. FULL GATE (a play is GO-CANDIDATE iff ALL hold, forward-only)

All checks on the forward (post-seal) record only. Evaluated in order; the FIRST failing check is the
binding constraint reported per play.

1. **Power:** ≥ **30** distinct forward resolved events (for the play / book).
2. **Realizable edge exists:** forward realizable Calmar at the measured tax is **positive**.
3. **Beats a RANDOM equal-size book, belief-blind:** on realizable Calmar, weighting held equal so only
   SELECTION differs, **p ≤ 0.01**.
4. **Beats the single-best benchmark:** realizable Calmar > the best single reliable trader's realizable
   Calmar (the PLAY-A bar; a book must beat the tail, not just a random book).
5. **selection_null p ≤ 0.01 with `--calibrate` PASS** (the null must be trustworthy).
6. **promotion_verdict:** ≥ 30 events, Bonferroni-adjusted, **day-deflated** SE, **LB > 0.03**.
7. **pilot_verdict:** **LB > 0.02**, ≥ **50** events, ≥ **5** positive regimes, ≥ **70%** positive,
   liquidity ≥ **$2000**.
8. **Persistence across ≥ 2 DISJOINT NON-SOCCER sport-regimes** (the SOCCER-ARTIFACT lesson — soccer
   alone NEVER counts; a regime = sport × calendar-month, non-expiring).
9. **Edge-reality:** real **λ̂ CI-lower ≥ 0.25** (front-running / information, not longshot bias).

**Forward-only guard:** every row filtered `first_seen ≥ 2026-07-06T06:25:17Z`. No pre-seal data enters
any gate computation.

**Escalation:** any play clearing checks 1–9 ⇒ STATUS = **GO-CANDIDATE** + a loud
**"ESCALATE TO HUMAN — do NOT auto-promote/arm"** banner. A GO on thin data is treated as a probable bug;
promotion/arming remains a human decision (Tue) behind the standing 4 GO gates.

---

## 4. Expected state at seal + horizon

At the seal, forward events ≈ 0, so every play is expected to report **INDETERMINATE-BY-POWER** (first
binding failure = power/accrual, check 1 / check 8), NOT a GO. The **binding constraint is the accrual
horizon**: independent non-soccer regime persistence over **MONTHS** (esports / NFL Sept / NBA Oct). The
instrument is designed to sit unattended and accrue; re-run periodically (weekly) with NO code change.

*Sealed by the Cycle-6 forward-track build. Frozen. Read-only, paper-only, nothing promoted, nothing
armed, no Rust touched.*
