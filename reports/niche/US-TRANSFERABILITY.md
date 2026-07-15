# US-price transferability of the collapse model — plausible, fee-covered, NOT yet validated

**2026-07-15. Branch `feat/copy-edge-hardening`. Paper/analysis only.**
Every collapse-model number is on the **international** tape. Tue executes on **Polymarket US**. This
records what is and is not established about the transfer, without overclaiming.

## What IS established
1. **Execution cost is survivable** (`/tmp/haircut.py`, folded into the report). Applying an added ask
   haircut on top of the real taker print — because we *add* size live — the tradeable-subset edge holds:
   0.5¢ → +3.58%/+5.08%; 1.0¢ (median US spread) → +3.02%/+4.51%; 2.0¢ (stress) → +1.90%/+4.51%.
   Break-even is well past 2¢. This defuses the ITER-5 failure mode ("arms lost to execution cost").
2. **The US taker fee is inside that envelope.** US θ=0.06·p·(1−p) ≈ 0.5–0.9¢ at favourite prices —
   far below the ~2¢+ the edge tolerates. Fee is not the risk.
3. **US sports-favourite depth covers our size** (`project-polymarket-us-venue`, `us_book_sampler`):
   $50–$250 clips fill at ~0¢ slip, ~$2.5k at the touch.
4. **Settlement is identical by construction** — a US contract resolves on the same real-world event
   as its intl twin.

## What is NOT established (the honest gap)
**The cross-venue basis is median-tight but tail-noisy.** On the favourite band (intl ask ≥ 0.80),
`cross_venue_basis` (n=3,507, non-placebo, mapped):
- median |basis| = **0.80¢**, mean |basis| = **2.43¢**, p90 = **5.0¢**, corr(us,intl) = **0.63**.
- signed intl−us in the 0.8–1.0 band = **+3 to +4¢** (US favourites trade *cheaper* — a tailwind).

So the *typical* contract is aligned inside one tick, and the mispricing that exists favours a US
buyer — but a fat tail of ~5¢ disagreements means the model's **price-path features would compute
differently on some US contracts**, and its selection would not transfer identically. A median-tight,
tail-noisy basis is exactly the pattern that looks fine on average and bites in the tail.

## Verdict
The port is **plausible and fee/depth-covered, but NOT validated.** The basis cannot stand in for a
native test. Two ways to close it, in order of rigor:
1. **US-native backtest** — run `us_regulatory_backfill.py` to load DMR settlements
   (`us_daily_market_report`, currently 0 rows here), rebuild the backward-looking features from
   `us_mid_tape` (2.3M rows), settle on the DMR, price at US θ + the 0.5¢ ask haircut. External data
   dependency (polymarketexchange.com DMR CSVs).
2. **Forward paper test at real US prices** — the live `us_trade_tape` is now accruing; entry at the
   real forward US print, model for selection, forward settlement for the label. Identical-footing,
   US-native, no lookahead. This resolves the port AND the cross-pipeline comparability in one
   experiment. See the pre-registration.
