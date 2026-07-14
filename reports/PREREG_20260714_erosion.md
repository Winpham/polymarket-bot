# PRE-REGISTRATION — forward decay gate for `favorite` 0.71–0.98

**Frozen:** 2026-07-14. **Author:** favorite-edge erosion forensics run.
**Status:** the champion and every incumbent are UNCHANGED by this run. Nothing promotes. Nothing arms.

---

## Why this exists

The 2026-07-09→13 softening (cumulative ROI-turn 8.4% → 7.1%) was investigated across seven axes.
**No cause was established.** The honest day-block permutation null returns BH-adjusted **p = 0.086** —
a constant +8% edge is *not* excluded — and the decisive constraint is **power**:

> Detecting a fall from **+8% → 0%** at 95% requires **~62 matches per window**.
> The recent window holds **38** (k=5) / **20** (k=3).

The in-sample data therefore **cannot** answer the question, and no exclusion may be derived from it.
Only forward accumulation can settle it. This document freezes *in advance* what will count as decay,
so that the answer cannot be fitted after the fact.

---

## The locked objective

- **Metric:** cluster-robust **ROI-on-turnover at OUR entry**, clustered at `superkey.super_event`
  (the MATCH — never `event_slug`).
- **Belief-blind:** report **surplus over `_blind`** at the same band mix, not raw ROI. A raw drop that
  is a *softness* drop is not an edge decay.
- **Price basis:** a **stationary** one. `initial_mean_price` (100% coverage every day) until ask-at-fire
  capture is live for the *whole* comparison window.
  ⚠️ **`COALESCE(entry_ask, initial_mean_price)` is FORBIDDEN for any time-comparison.** `entry_ask`
  coverage runs ~5% (06-29) → ~70% (07-13) and `entry_ask` sits *above* `initial_mean_price`; that basis
  manufactures a downward drift out of capture coverage alone.
- **Fee:** `0.03·p·(1−p)`. **Sizing:** flat shares.

## The gate

| | condition |
|---|---|
| **Baseline** | 06-29 → 07-14, 156 matches, ROI-turn **+7.1%**, belief-blind surplus **+5.4%** |
| **Minimum window** | **≥ 62 matches** (the power floor above). Do not read a verdict before this. |
| **DECAY declared** | day-block permutation test vs baseline returns **BH-adj p < 0.05** for a drop |
| **HEALTHY declared** | forward ≥62-match window holds **95% LB > 0** on belief-blind surplus |
| **INCONCLUSIVE** | anything else → keep running paper, do not act |

## The critical window

**The weeks after the World Cup final (~2026-07-19.)** The edge has *only ever* been measured on summer
tournaments (World Cup + Wimbledon). The post-tournament stretch is the **first genuine
out-of-tournament test it has ever faced** — and the real durability question, far more than the current
cold streak.

## Frozen — what may NOT be done

- ❌ **No exclusion, band change, or new arm may be derived from the 06-29→07-14 sample.** In particular:
  **tennis may not be excluded.** It failed every test (Bonferroni p = 0.100; recent 95% CI
  [−36.2%, +16.3%] *contains* the earlier +13.4%; dropping the single 07-13 slate flips it to +6.3%;
  and the non-tennis remainder has a **negative** 95% LB of −5.8%).
- ❌ No volume-floor self-suspension. Volume is **not** draining — 07-13 was the second-heaviest slate of
  the window (16 matches). The trigger does not fire.
- ❌ No finer bands, no per-sport conditioning, no liquidity floor, no past-PnL trader rank
  (all previously refuted — see the DO-NOT list in `STRATEGY-HANDOFF-favorite-consensus.md`).
- ❌ No real money. Paper only, regardless of what this gate returns.

Any future cut must be **pre-registered before its result is seen.**

## Reproduce

```bash
python3 scripts/erosion_variance_null.py --selftest && python3 scripts/erosion_variance_null.py
python3 scripts/erosion_decompose.py     --selftest && python3 scripts/erosion_decompose.py
python3 scripts/erosion_tennis_test.py
python3 scripts/erosion_action_verdict.py
```
