# Phase 0 — the ice we're standing on (stress-test baseline)

**Run:** 2026-07-02 · hostile-risk-officer stress test (`STRESS-TEST-BAD-DAYS-PROMPT.md`).
Paper-only, read-only on the live DB, all artifacts under `reports/stress/` + `scripts/stress/`.
Nothing here changes live behavior, the ledger, or any migration.

This document is the **denominator** for every later claim: exactly how thin the evidence is.

---

## 0.1 The one fact that dominates everything

The entire evidentiary base is **4 calendar days** (2026-06-29 → 2026-07-02) of live capture,
and the **forward-sealed** honest paper ledger is **~1 day** (first favorite bet 2026-07-01
19:36 UTC). Within those 4 days **every event-day was net-positive for favorite** (win-rates by
day: 0.900, 0.862, 0.953, 1.000). There is **no losing slate in the record.** Therefore:

> P(profit)=100% in `risk_engine.json` is **not** a probability of profit. It is the block
> bootstrap faithfully reporting that resampling a record with no losing slate cannot produce a
> losing path. **The record is too short to have *contained* a bad regime.** Empirical bootstrap
> of this record measures variance *within the good days we happened to see* — it cannot answer
> the mission. The mission requires **injecting failure the record has not yet shown.**

## 0.2 Certified-eligible arms (from `consensus_signals`, at-fire entry, event-clustered)

| arm | resolved events | distinct-w/-entry | regimes>0 | surplus vs `_blind` | realizable ROI (ledger) |
|---|---:|---:|---:|---:|---:|
| **favorite** | 97 | 72 | 4/4 | **+12.46%** | +$580.90 / 36 bets |
| **elite_fresh_fav** | 40 | 28 | 3 | +10.47% | +$117.60 / 14 bets |

`elite_fresh_fav` is **100% nested inside favorite** (`portfolio_concentration`: shared 40/40,
adds **0** independent events). **The "two winners" are one bet stream.** Treat the certified
surface as a **single arm** (favorite) for all risk purposes; elite_fresh_fav is favorite wearing
a second name (this is F5's finding, pre-confirmed by the concentration report).

## 0.3 Effective sample size — the nominal N is a mirage

`favorite`, from `reports/effective_n.json` and `portfolio_concentration.json`:

| grain | N_eff | # independent clusters (G) | notes |
|---|---:|---:|---|
| event (ICC≈0) | 72 | — | in-sample ICC_slate 0.008 ≈ 0 → events look independent *within sample* |
| slate | 92 [49, 97] | 15 slates | block-bootstrap 95% floor 49 |
| regime | 49.8 | 4 regimes | |
| cluster-robust, day grain | 58.6 | **G = 4 days** | the binding constraint |
| cluster-robust, tournament grain | 179 | G = 6 | grain-arbitrary; flatters |

**The load-bearing number is G ≈ 4 independent day-blocks (or ~2 tournament cycles).** No SE
re-derivation can shortcut it. The surplus **lower bound** depends entirely on which grain you
believe:

| lower-bound estimator | favorite LB | reading |
|---|---:|---|
| `honest.rs` event-N (ICC=0) | **+4.7%** | assumes events independent — optimistic |
| cluster-robust day, gate-z | +3.9% | ignores small-cluster d.o.f. |
| cluster-robust tournament, gate-z | +7.6% | grain-arbitrary flatter |
| **cluster-robust day, small-sample t (df=3)** | **−8.2%** | **honest given only 4 blocks** |
| `board.rs` day-N (ICC=1) | −20.3% | falsified mechanism (assumes ICC=1) |

> **The honest lower bound on favorite's edge, given 4 independent day-blocks, includes deeply
> negative values (−8.2% at df=3).** The point estimate (+12.5%) is strong and positive in 4/4
> disjoint regimes, but the *generalization* CI is not bounded above zero. Status: **promising
> but unproven** — real edge, well-pinned in-sample, blocked by too few independent blocks.

## 0.4 Concentration / diversity — is it one bet or many?

- **Tournament HHI 0.378 ≈ 2.6 effective tournaments.** Top tournament (`tennis-slam` = Wimbledon)
  holds **53%** of gross profit. Add ~17% WC soccer → **~70% of profit from two tournaments that
  both expire within weeks.**
- Regime split (favorite): tennis **48 ev** (+11.4%), soccer **34 ev / 10 w-entry** (+6.9%),
  **mlb 9 ev (+22.6%)**, **other 6 ev / 5 (+15.7%)**. The "4 positive regimes" leans on **mlb (9
  events, 100% win) and other (5–6 events, 100% win)** — two N<10 perfect-record slivers that
  are almost certainly small-sample luck, not established regimes. The real weight is **tennis +
  soccer** (~82 of 97 events).

## 0.5 The full arm family (the F3 multiplicity denominator)

15 non-blind strategies have been scored against `_blind`. Forward honest-ledger P&L:

| positive | favorite +$581 · elite_fresh_fav +$118 (nested) |
|---|---|
| **negative** | trust_weighted −$53 · nonsports −$102 · tight_cluster −$104 · elite_gated −$530 · longshot −$1,172 · sports_only −$1,612 · strict −$1,714 · count −$1,714 · whales −$1,714 · fresh2h −$1,833 · **loose −$5,353** |

**Of the whole family, exactly one independent arm (favorite) is positive; its nested child is the
only other.** Every broad-consensus arm bleeds. This is the multiplicity backdrop: the search
tried ~15 arms and kept the one that worked. F3 must ask whether one survivor out of ~15 is
distinguishable from chance. (Counterweight, tested in F3: favorite's selection-null p=0.0000
survives even ×15 Bonferroni — but its *nested* sibling must not be counted as a second success.)

## 0.6 What Phase 0 establishes

1. **N_eff is not the story; G≈4 independent blocks is.** The generalization LB is unbounded below.
2. **There is one edge, not two** (elite_fresh_fav ⊂ favorite).
3. **Profit is ~70% two expiring tournaments**; the 4-regime breadth is 2 real + 2 lucky slivers.
4. **No losing slate exists in the record** → the bootstrap cannot price a bad day → we must
   inject one. That is Phases 1–4.

Every later number inherits this ice. Wide CIs below are a **finding**, not a defect to hide.
