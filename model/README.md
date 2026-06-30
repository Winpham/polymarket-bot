# Model artifacts (consensus cross-check arms)

This directory holds the trained models the silent cross-check arms load. It is
baked into `Dockerfile.consensus` so the running bot can find them at `model/`.
**All arms are default-OFF** — a missing file here just leaves its arm a no-op.

| File | Arm(s) | Trainer |
|------|--------|---------|
| `consensus_win.json` | `consensus_logit` | `scripts/consensus_train.py` (logistic, RobustScaler) |
| `consensus_ens.json` | `consensus_ens` | `scripts/consensus_train.py` (XGBoost, native JSON) |
| `xgb_model.json` (+ `xgb_model.scaler.json`) | `market_ml` / `market_veto` | `scripts/fetch_data.py` → `scripts/train_model.py` |
| `market_resid.json` (+ `.scaler.json`, `.resid.json`, `.meta.json`) | `market_resid` | `scripts/train_market_resid.py` (price-free XGBoost) |

## The `market_resid` arm (price-free residual)

`market_resid` is the trading-bot's market-outcome model given a *tautology-free*
shot: the price-LEVEL features are held constant at train (so the booster never
splits on price — verified), features are YES-oriented, and the arm fires on
`p_consensus − band_rate(band)` (the `_blind` base rate) instead of `p − clob_mid`,
aligning its target with the gate's surplus-over-blind. Default-OFF
(`CONSENSUS_ARM_RESID=false`); silent (`tier=Watch`); judged in the experimental
family. `.resid.json` carries `band_rates`/`global_rate` (the blind baseline) and
the baked isotonic calibration (`iso_x`/`iso_y`); `.meta.json` carries
`trained_through` (forward cutoff) and `suggested_margin` (set `CONSENSUS_ML_MARGIN`).

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
