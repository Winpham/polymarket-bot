# RUN-D — Deferred arms (Bayesian anchor + import-model collapse-probe)

> ⚠️ **Do NOT build yet.** Run this only after RUN-A/B have accrued real forward data and there's a concrete
> reason (e.g. `ml_top` shows promise and you want an anchored variant, or you want to confirm the market-model
> null on this data). Both designers ranked these LOW expected ROI. Land them one at a time, behind the RUN-B
> enricher seam (each is one new file + one `registry()` line). Read `FORGE_PLAN_LEVERS.md` (Deferred section).

## D1 — Bayesian-anchor arm (`bayes_top`)
**Idea:** prior = the live CLOB mid of the fired outcome (already captured as `initial_market_price`, or fetch
once per fired market with `fetch_clob_market`); evidence = consensus conviction mapped to a likelihood ratio
(monotone in `net_quality`, confidence from price coherence) [+ the ML LR from RUN-B if present]; combine via
`bayesian_update` → posterior; emit `bayes_top` only when the posterior still beats the mid by a margin.
**Prereq:** move `trading-bot/src/bayesian.rs` → `common/src/model/bayesian.rs` (pure fns; re-export so
trading-bot is unbroken — see FORGE_PLAN_LEVERS PREP-A). Then `scanner/enrich/bayes.rs` + one `registry()` line.
**Owned files:** `common/src/model/bayesian.rs` (+ mod re-export), `trading-bot/src/main.rs`+`model/mod.rs`
(re-export), `scanner/enrich/bayes.rs`, the one `registry()` line.
**Honest expectation:** a selection filter on `strict` picks; the gate judges its surplus. Likely marginal.

## D2 — Import-model collapse-probe (`cml_*`) — only if cheap
**Idea:** a clearly-labelled SECOND silent probe that imports the repo's market-outcome model
(`MarketFeatures` + pure-Rust `XgbModel`) to confirm — on THIS data — the Foresight null that a generic
market-prediction model doesn't beat the line. Per fired market it costs 1 Gamma + 1 CLOB-mid + 1
prices-history fetch (bounded by distinct fired markets, throttled like housekeeping).
**Prereq:** move `trading-bot/src/model/xgb.rs` → `common/src/model/xgb.rs` (re-export); produce a trained
`model/xgb_model.json` via `scripts/fetch_data.py` + `scripts/train_model.py`; add `fetch_price_history` free fn
to `common/src/data/models.rs`; config `XGB_MODEL_PATH`.
**Owned files:** `common/src/model/xgb.rs` (+ re-export), `common/src/data/models.rs` (fetch_price_history),
`scripts/`, `model/`, `scanner/enrich/import_model.rs`, the one `registry()` line, config.
**Honest expectation:** ≈0 surplus (documented null). Build only as a cheap confirmation, never on the critical
path; if standing up the artifact is non-trivial, skip it.

## Both
- Each arm is SILENT (`alerting=false`), judged only on surplus-over-blind by the gate.
- Each new arm raises the gate's Bonferroni denominator for ALL strategies. If the arm count grows past ~4–5,
  first implement the **family split** (FORGE_PLAN_LEVERS.md §"Bonferroni family split") so experimental arms
  don't tighten `strict`'s own promotion bar.
- Follow `run-prompts/README.md` workflow (worktree, gate, safe merge, default-off).
