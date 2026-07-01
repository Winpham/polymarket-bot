# Model artifacts (consensus cross-check arms)

This directory holds the trained models the silent cross-check arms load. It is
baked into `Dockerfile.consensus` so the running bot can find them at `model/`.
**All arms are default-OFF** — a missing file here just leaves its arm a no-op.

| File | Arm(s) | Trainer |
|------|--------|---------|
| `consensus_win.json` | `consensus_logit` | `scripts/consensus_train.py` (logistic, RobustScaler) |
| `consensus_ens.json` | `consensus_ens` | `scripts/consensus_train.py` (XGBoost, native JSON) |
| `xgb_model.json` (+ `xgb_model.scaler.json`) | `market_ml` / `market_veto` | `scripts/fetch_data.py` → `scripts/train_model.py` |
| `market_resid.json` (+ `.scaler.json`, `.resid.json`, `.meta.json`) | `market_resid` | `scripts/train_market_resid.py` (price-LEVEL-free XGBoost) |

## The `market_resid` arm (price-LEVEL-free residual)

`market_resid` is the trading-bot's market-outcome model given a *tautology-free*
shot: the price-LEVEL features {0,8,9} are held constant at train (so the booster
never splits on price — verified), features are YES-oriented, and the arm fires on
`p_consensus − band_rate(band)` (the `_blind` base rate) instead of `p − clob_mid`,
aligning its target with the gate's surplus-over-blind. Default-OFF
(`CONSENSUS_ARM_RESID=false`); silent (`tier=Watch`); judged in the experimental
family. `.resid.json` carries `band_rates`/`global_rate` (the blind baseline) and
the baked isotonic calibration (`iso_x`/`iso_y`); `.meta.json` carries
`trained_through` (forward cutoff), `suggested_margin` (set `MARKET_RESID_MARGIN`),
and `placeholder` (a synthetic bootstrap is refused when the arm is enabled).

### "price-LEVEL-free", precisely — two verified nuances

1. **The guarantee is TRAIN-time and rests SOLELY on the booster having no split on
   {0,8,9}.** The `RobustScaler` does NOT neutralize price at inference: a
   held-constant (zero-IQR) price column gets `scale = 1`, so a live price value
   would pass straight through if the booster ever split on it. The Rust loader
   independently re-checks this (`assert_no_splits_on(&[0,8,9])`) and refuses a
   price-leaking booster — the arm is left OFF rather than judged.
2. **This is price-LEVEL-free, NOT price-free.** Only the 3 price-LEVEL indices are
   held constant. The price-SHAPE features {1,2,3,4} (`momentum_1h`, `momentum_24h`,
   `volatility_24h`, `rsi`) remain by design — all price-derived, and the closest
   residual proxies for direction. Any `market_resid` surplus is therefore only
   believable if it survives the price-SHAPE ablation (`--price-free-level shape`,
   which also holds {1,2,3,4} constant). See **Believing a surplus** below.

### Believing a surplus — the PRE-REGISTERED price-SHAPE-leakage test

**Registered before any forward verdict.** The live arm is `--price-free-level level`
(holds only the price-LEVEL indices {0,8,9} constant). Because the price-SHAPE
features {1,2,3,4} = momentum/volatility/rsi remain, a `level` surplus could be the
model shadowing price *direction* through momentum rather than finding a genuine
non-price residual. So:

> **A `market_resid` (level) surplus is believable ONLY IF the `shape` model — which
> ALSO holds {1,2,3,4} constant, i.e. fully price-blind — retains a materially
> similar surplus.** If the surplus collapses when {1,2,3,4} are held constant, it
> was price-SHAPE leakage → **report the null, do NOT promote, do NOT tune.**

Run the ablation on the same forward rows (no artifacts written):

```bash
DATABASE_URL=... python3 scripts/train_market_resid.py --source forward --compare
```

It prints, side by side for `level` and `shape`: OOF AUC, Brier, and the would-be
event-clustered arm surplus (fired where calibrated p − band_rate > 0). This is an
OFFLINE screen, not the promotion decision — the belief-blind gate (≥30 distinct
events, Bonferroni-corrected lower bound > `MARKET_RESID_MARGIN`) remains the sole
judge. The ablation only decides whether a positive gate reading is *believable* or
a price-shape artifact. The `shape` model is an analysis artifact — do NOT ship it as
a second live arm (that would raise the experimental family's Bonferroni denominator).

The committed `market_resid.*` is a **`source=synthetic` placeholder**
(`"placeholder": true`) — a non-predictive bootstrap so the arm can load; it is NOT
trained on real data. Replace it before enabling:

```bash
# Cold-start bootstrap from resolved markets (survivorship-biased), when net-reachable:
python3 scripts/train_market_resid.py --source historical --out-dir model
# Forward, survivorship-free, the bot's OWN strict-fired population (Phase 4):
DATABASE_URL=postgres://bot:bot@host:5432/polymarket \
  python3 scripts/train_market_resid.py --source forward --out-dir model
```

The gate (≥30 distinct events, Bonferroni-corrected lower bound > margin) is the
sole judge of whether the edge is real — a placeholder or a null both simply never
get promoted.

## Train the consensus-native models (from our own forward record)

Once enough `_blind` rows have resolved in Postgres:

```bash
DATABASE_URL=postgres://bot:bot@host:5432/polymarket \
  python3 scripts/consensus_train.py --out-dir model
```

`consensus_train.py` reads resolved `_blind` signals (features + `outcome_won`,
grouped by event), trains the logistic + XGBoost models with `GroupKFold(event)`
(leak-free), reports OOF AUC/Brier, and stamps `trained_through` (the forward-only
cutoff the arms honor). It also accepts `--input fixture.json` for a dry run.

## Train the imported market model

```bash
python3 scripts/fetch_data.py            # → model/training_data.json
python3 scripts/train_model.py           # → model/xgb_model.json (+ scaler)
```

## Enable the arms (deliberate, after a model exists)

Set the per-arm flags (see `.env.consensus.example`), e.g. `CONSENSUS_ARM_LOGIT=true`.
Emitted rows are **silent** (never alert) and judged by the belief-blind promotion
gate in the *experimental* family — the gate, not us, decides if an arm has edge.
