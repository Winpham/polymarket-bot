# PROPOSAL (pre-registration amendment) — relax/drop the `round_trip_rate` MM axis

**Status: PROPOSAL, NOT APPLIED. Requires Tue's sign-off** (amends the frozen constants in
`reports/PREREG_2026-07-04T094304Z_proven_router.md`; the proven-router thresholds were deliberately
pre-registered to prevent post-hoc tuning, so this change must be an explicit, dated amendment, not
an autonomous edit). Paper-only arm; `PROVEN_ROUTER` default OFF; fully reversible.

## The change
MM screen in `refresh_router_followset` (`consensus.rs:1649-1651`) and `trader_scorecard.is_mm`:

```
  from:  round_trip_rate < 0.30  AND  two_sided_rate < 0.25  AND  sell_buy_ratio < 0.50
  to:    round_trip_rate < 0.50  AND  two_sided_rate < 0.25  AND  sell_buy_ratio < 0.50
```
(i.e. relax the round-trip cutoff 0.30 → 0.50; the `two_sided`/`sell_buy` axes and the
`trader_type='bot'` union are unchanged. Dropping round_trip entirely performs equivalently.)

## Evidence (`scripts/mm_screen_effect.py`, D29 addendum, this record 2026-07-04)

Measured on the DOWNSTREAM profit proxy — forward (H2) copy-return of the H1≥10% cohort, the wallets
the arm actually follows:

| screen | H1→H2 corr | n | **cohort fwd-H2** | cohort n |
|---|---|---|---|---|
| no screen | +0.291 | 201 | **+0.004** | 57 |
| current 0.30/0.25/0.50 | +0.194 | 103 | **+0.043** | 36 |
| **relax round_trip → 0.50** | +0.210 | 121 | **+0.045** | 40 |
| drop round_trip | +0.207 | 125 | +0.042 | 41 |
| two_sided only (drop rt AND sb) | +0.204 | 133 | +0.029 | 45 |

1. **The screen is profit-accretive and must stay:** it ~10×'s the cohort forward-return (+0.004
   unscreened → +0.043) by keeping arbers out of the copy cohort. Do NOT drop the screen.
2. **`round_trip` is a false-positive generator:** relaxing 0.30→0.50 recovers ~18 copyable
   directional traders (n 103→121) while the cohort forward-return holds/improves (+0.043→+0.045).
   Tier-1 corroborates: all 11 labeled-human false positives fired on `round_trip≥0.30` — directional
   bettors who sell to lock profit, not MMs. Buy-both-hold arbers hold both legs and read LOW
   round-trip, so the axis adds no MM discrimination (Tier-1 AUC 0.265, below 0.5).
3. **Keep `sell_buy`:** dropping it too (`two_sided only`) lowers the cohort return (+0.029) — it
   pulls real weight; only `round_trip` is pure false-positive.

## Honesty caveats (why this is a proposal, not an auto-applied edit)
- In-sample, single 4-day live record; the +0.045 vs +0.043 gap is within noise (cohort n≈40). The
  case is **strict-dominance / no-downside + mechanistic**, not a proven profit jump.
- Amends a pre-registered constant → integrity requires a dated amendment + sign-off, and ideally
  re-confirmation on forward data (`mm_screen_effect.py` re-runs on demand as the record accrues).
- Recommended gate before applying: re-run `mm_screen_effect.py` on ≥1 additional independent
  forward week; apply only if relax-round_trip still ≥ current on the cohort forward-return.
