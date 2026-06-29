# Model artifacts (consensus cross-check arms)

This directory holds the trained models the silent cross-check arms load. It is
baked into `Dockerfile.consensus` so the running bot can find them at `model/`.
**All arms are default-OFF** — a missing file here just leaves its arm a no-op.

| File | Arm(s) | Trainer |
|------|--------|---------|
| `consensus_win.json` | `consensus_logit` | `scripts/consensus_train.py` (logistic, RobustScaler) |
| `consensus_ens.json` | `consensus_ens` | `scripts/consensus_train.py` (XGBoost, native JSON) |
| `xgb_model.json` (+ `xgb_model.scaler.json`) | `market_ml` / `market_veto` | `scripts/fetch_data.py` → `scripts/train_model.py` |

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
