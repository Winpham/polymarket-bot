// features lives in polymarket-common; re-export for local use. The `xgb` and
// `bayesian` models also moved to polymarket-common (Phase 1) — the trading bot
// doesn't call `xgb` directly, so it's reached via `polymarket_common::model::xgb`
// when needed rather than re-exported here (an unused re-export warns in a bin).
pub use polymarket_common::model::features;

pub mod sidecar;
