# Forge debates — exploit the trading-bot ML (`market_resid`)

Compressed record: both designs, verification findings against the real code, and the synthesis
decisions + rationale. Backs `RUN-TRADING-BOT-EXPLOIT.md` + `FORGE_PLAN_TRADING_BOT.md`.

## The question
Turn the repo's dormant 29-feature market-outcome XGBoost (`MarketFeatures` + pure-Rust `XgbModel`,
`model/` empty) into a genuine, gate-judged profit edge on the consensus copy-trading bot — judged
ONLY by the belief-blind promotion gate, never refused on prior. Overturn the `RUN-D`/`FORGE_PLAN_
LEVERS` "known-null, ≈0, build only as cheap confirmation" framing.

## Designer A (Direct) — train the historical 29-feature model
GAP-3 YES-orient first (mid-anchor + orient `p_yes→p_cons`). GAP-1: train via
`fetch_data.py→train_model.py`, commit `model/xgb_model.json`. GAP-2: price-free by forcing
`yes_price=0` at train+infer (RobustScaler scale→0, Rust guard), new `arm_market_nlp` firing on
`p_consensus − clob_mid`; add `market_nlp`/`market_nlp_nonsports` segment tags; keep `market_ml` as a
documented control. GAP-5: export an isotonic `.calib.json`, add a Rust `Isotonic`. GAP-7: GroupKFold.

## Designer B (Rethink) — predict the residual
Price-anchored model is dead on arrival (`p−clob_mid` ≈0 by construction). Predict the RESIDUAL on
price-free features; fire on `p − band_rate[band]` (baked from `_blind`), NOT `clob_mid`. Build a
forward 29-feature `market_feature_log` (migration 028) and forward-calibrate on it. ONE arm
(`market_resid`); add `predict_prob_pricefree` + `price_free_idx` + `pg_width_bucket5` + `apply_iso`
in Rust. Do NOT enable `market_ml`. No segment fleet.

## Verification findings (against the real code)
1. **`XgbModel` already in `common/`** — RUN-D's "move xgb.rs" prereq is DONE. JSON schema
   (xgb.rs:161-194), positional indexing (`features.get`, :137), scaler `scale==0⇒0.0` (:56-60), raw
   sigmoid / no calibration (:116) all verified.
2. **Feature indices verified** (to_vec, features.rs:104): price-level = {0 yes_price, 8 price_change_1d,
   9 price_change_1w}; `rsi`=4, `is_crypto`=7, `is_sports`=12; 29 total. B's index claims correct.
3. **`pg_width_bucket5` matches** `width_bucket(mean_price,0,1,5)` (consensus.rs:489) algebraically;
   float-boundary risk → add a Postgres-parity test.
4. **B oversold "surplus EQUALS the model's target."** Gate subtracts `blind_edge[band]=AVG(won−mean_
   price)`, arm uses `band_rate=AVG(won)`; *aligned*, not identical. Kept the residual target,
   corrected the claim to "the sharper, tautology-free test; the gate stays the independent judge."
5. **B's inference masking is risky + unnecessary** (the biggest change). Positional `XgbModel`:
   training on dropped columns re-indexes to 27-wide and mis-aligns the 29-length inference vector.
   A's **constant-column-at-train** mechanism makes XGBoost emit no splits on price indices ⇒ stock
   `predict_prob` is price-free with zero new inference primitive. Dropped `predict_prob_pricefree` /
   `price_free_idx`.
6. **`market_ml` as an enabled control costs a Bonferroni slot** — `board.rs:154-179` counts
   rows-present per family. An OFF arm is free; an enabled one tightens `market_resid`'s bar for no
   info. ⇒ keep `market_ml` defined + default-OFF, NOT enabled; document the tautology analytically.
7. **GAP-3/5/7 all confirmed real** (build_market_features token-by-outcome_index :690; isotonic fit
   but unexported :553/:608; TimeSeriesSplit :320 with `market_ids` already threaded :539). Migration
   next number = 028.
8. **Cold-start is real:** B's forward log needs ~30 forward strict-fired resolved events before any
   forward artifact; A can bootstrap from historical immediately, but that population is general +
   survivorship-filtered (≠ strict-fired).

## Synthesis decisions
- **Spine = B** (price-free residual-over-`band_rate`, forward `market_feature_log`, forward
  calibration, ONE arm `market_resid`).
- **Price-freeness = A** (constant columns at train); **drop B's masking** (finding 5).
- **Cold-start = A** (historical `--source historical` bootstrap, labeled, superseded at ≥30 events by
  `--source forward`).
- **`market_ml` = kept-defined, default-OFF, NOT enabled** (finding 6); tautology documented.
- **Arm count enabled = 1**; segment arms deferred to ≤1 pre-registered `market_resid_nonsport`.
- **Framing corrected** (finding 4): residual target is *aligned with* the gate, not identical; the
  gate is the sole judge; a clean forward null is an HONEST verdict, not the old artifact.
- Shared, both designers agreed: GAP-3 first, GroupKFold-by-event, forward-only guard, isotonic baked
  as JSON applied in Rust, default-OFF silent arms, lean Bonferroni family.

## Phase list (final)
0. GAP-3 YES-orientation (no config). 1. Forward `market_feature_log` (migration 028, ship first).
2. Rust primitives (`band_rate`/`apply_iso`/`pg_width_bucket5`, tested). 3. `market_resid` arm +
`train_market_resid.py` (price-free, GroupKFold, forward-calib) + cold-start bake. 4. Forward retrain
+ enable; gate decides.
