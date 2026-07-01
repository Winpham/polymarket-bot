//! Conservative, belief-blind **pilot go/no-go** for the honest realizable P&L
//! tracker. A strategy is pilot-ready ONLY if, judged on its execution-aware
//! honest ROI (CLV − haircut, event-clustered), the Bonferroni-corrected lower
//! confidence bound clears a positive threshold AND it persists across distinct
//! day-regimes AND there is enough market liquidity to place a minimum stake.
//!
//! This is deliberately strict and pure (no DB/network): a false GO risks real
//! money, so the default is HOLD. It reuses the belief-blind gate's exact z/SE
//! machinery (`promotion::surplus_bounds`, so `probit` stays private there) — the
//! only new logic here is the multi-regime persistence + liquidity floor.

use crate::scanner::promotion::{PromotionParams, surplus_bounds};

/// Per-strategy inputs to the pilot verdict (all read-only measurements).
#[derive(Debug, Clone)]
pub struct PilotInputs {
    /// Event-clustered honest ROI (net of haircut + fee). `None` → nothing resolved.
    pub honest_roi: Option<f64>,
    /// Std-dev of per-EVENT honest ROI. `None`/0 with <2 events (widens nothing —
    /// treated as a tiny floor by `surplus_bounds`, so small N still can't pass).
    pub honest_roi_sd: Option<f64>,
    /// Distinct resolved EVENTS — the de-correlated sample size.
    pub distinct_events: i64,
    /// Distinct day-regimes with a POSITIVE honest ROI.
    pub regimes_positive: i64,
    /// Distinct day-regimes observed.
    pub regimes_total: i64,
    /// Median liquidity proxy (median sharp $) — capacity to place a stake.
    pub median_sharp_usd: Option<f64>,
    /// Size of the Bonferroni family this strategy is corrected within.
    pub n_family: usize,
}

/// Tunable GO thresholds (sourced from config; conservative by default).
#[derive(Debug, Clone)]
pub struct PilotThresholds {
    /// Corrected honest-ROI lower bound the strategy must clear (execution-aware).
    pub min_pilot_roi: f64,
    /// Distinct-EVENT floor.
    pub min_events: i64,
    /// Absolute floor on positive day-regimes.
    pub min_regimes: i64,
    /// Fraction of day-regimes that must be positive.
    pub regime_frac: f64,
    /// Liquidity floor (median sharp $).
    pub min_liquidity_usd: f64,
    /// Family-wise significance before Bonferroni splitting.
    pub alpha: f64,
}

impl Default for PilotThresholds {
    fn default() -> Self {
        Self {
            min_pilot_roi: 0.02,
            min_events: 50,
            min_regimes: 5,
            regime_frac: 0.7,
            min_liquidity_usd: 2000.0,
            alpha: 0.05,
        }
    }
}

/// The pilot verdict: GO only if EVERY conservative condition holds.
#[derive(Debug, Clone)]
pub struct PilotVerdict {
    pub go: bool,
    /// Bonferroni-corrected one-sided lower bound on honest ROI (`None` if unscored).
    pub corrected_lower_bound: Option<f64>,
    /// The BINDING reason (why HOLD), or the passing summary (why GO).
    pub reason: String,
}

/// Required positive day-regimes: `max(ceil(frac × total), min_regimes)`. With no
/// regimes observed yet the requirement is at least the absolute floor (so an
/// empty record can never pass).
pub fn required_regimes(regimes_total: i64, th: &PilotThresholds) -> i64 {
    let by_frac = (th.regime_frac * regimes_total as f64).ceil() as i64;
    by_frac.max(th.min_regimes)
}

/// Decide whether a strategy is pilot-ready. Pure + unit-tested. Conservative:
/// any failing condition ⇒ HOLD with the binding reason; a false GO is the costly
/// error, so we default to HOLD.
pub fn pilot_verdict(inp: &PilotInputs, th: &PilotThresholds) -> PilotVerdict {
    let Some(honest_roi) = inp.honest_roi else {
        return PilotVerdict {
            go: false,
            corrected_lower_bound: None,
            reason: "no resolved events with a captured pre-resolution price yet".into(),
        };
    };

    // Corrected one-sided lower bound — the belief-blind gate's exact machinery.
    let params = PromotionParams {
        min_events: th.min_events,
        margin: th.min_pilot_roi,
        alpha: th.alpha,
    };
    let (lower_bound, _upper) = surplus_bounds(
        inp.distinct_events,
        honest_roi,
        inp.honest_roi_sd,
        inp.n_family,
        &params,
    );
    let lb = Some(lower_bound);

    // Evaluate every condition; report the FIRST binding failure (conservative).
    if inp.distinct_events < th.min_events {
        return PilotVerdict {
            go: false,
            corrected_lower_bound: lb,
            reason: format!(
                "N={} events < floor {} (need {} more)",
                inp.distinct_events,
                th.min_events,
                th.min_events - inp.distinct_events
            ),
        };
    }
    if lower_bound <= th.min_pilot_roi {
        return PilotVerdict {
            go: false,
            corrected_lower_bound: lb,
            reason: format!(
                "corrected honest-ROI lower bound {:+.1}% ≤ pilot bar {:+.1}% (honest ROI {:+.1}%, N={})",
                lower_bound * 100.0,
                th.min_pilot_roi * 100.0,
                honest_roi * 100.0,
                inp.distinct_events
            ),
        };
    }
    let need = required_regimes(inp.regimes_total, th);
    if inp.regimes_positive < need {
        return PilotVerdict {
            go: false,
            corrected_lower_bound: lb,
            reason: format!(
                "regime persistence {}/{} positive < required {} — not persistent across regimes",
                inp.regimes_positive, inp.regimes_total, need
            ),
        };
    }
    let liq = inp.median_sharp_usd.unwrap_or(0.0);
    if liq < th.min_liquidity_usd {
        return PilotVerdict {
            go: false,
            corrected_lower_bound: lb,
            reason: format!(
                "liquidity ${:.0} < floor ${:.0} — too thin to place a minimum stake",
                liq, th.min_liquidity_usd
            ),
        };
    }

    PilotVerdict {
        go: true,
        corrected_lower_bound: lb,
        reason: format!(
            "GO: corrected honest-ROI lower bound {:+.1}% > {:+.1}% over {} events, \
             {}/{} regimes positive, liquidity ${:.0}",
            lower_bound * 100.0,
            th.min_pilot_roi * 100.0,
            inp.distinct_events,
            inp.regimes_positive,
            inp.regimes_total,
            liq,
        ),
    }
}

/// Capacity sizing: the stake we could deploy before the edge erodes, and the
/// resulting working-capital / projected-weekly figures. All paper.
#[derive(Debug, Clone, Copy)]
pub struct Capacity {
    pub suggested_stake: f64,
    pub working_capital: f64,
    pub projected_weekly: f64,
}

/// `suggested_stake = min(flat_stake, capacity_frac × median $)`;
/// `working_capital ≈ bets_per_day × (avg_hours_to_resolve/24) × suggested_stake`;
/// `projected_weekly = bets_per_day × 7 × suggested_stake × honest_roi`.
pub fn capacity(
    flat_stake: f64,
    capacity_frac: f64,
    median_sharp_usd: Option<f64>,
    bets_per_day: Option<f64>,
    avg_hours_to_resolve: Option<f64>,
    honest_roi: Option<f64>,
) -> Capacity {
    let cap = capacity_frac * median_sharp_usd.unwrap_or(0.0);
    let suggested_stake = flat_stake.min(cap).max(0.0);
    let bpd = bets_per_day.unwrap_or(0.0);
    let hold_days = avg_hours_to_resolve.unwrap_or(0.0) / 24.0;
    let working_capital = bpd * hold_days * suggested_stake;
    let projected_weekly = bpd * 7.0 * suggested_stake * honest_roi.unwrap_or(0.0);
    Capacity {
        suggested_stake,
        working_capital,
        projected_weekly,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn strong() -> PilotInputs {
        // +8% honest ROI, tight sd, 60 events, 6/7 regimes positive, deep liquidity.
        PilotInputs {
            honest_roi: Some(0.08),
            honest_roi_sd: Some(0.06),
            distinct_events: 60,
            regimes_positive: 6,
            regimes_total: 7,
            median_sharp_usd: Some(8000.0),
            n_family: 6,
        }
    }

    #[test]
    fn strong_consistent_strategy_earns_go() {
        let v = pilot_verdict(&strong(), &PilotThresholds::default());
        assert!(v.go, "{}", v.reason);
        assert!(v.corrected_lower_bound.unwrap() > 0.02);
    }

    #[test]
    fn same_edge_one_regime_holds() {
        // Identical event-level edge but concentrated in ONE regime → HOLD.
        let mut inp = strong();
        inp.regimes_positive = 1;
        inp.regimes_total = 6;
        let v = pilot_verdict(&inp, &PilotThresholds::default());
        assert!(!v.go);
        assert!(
            v.reason.contains("regime persistence 1/6"),
            "reason: {}",
            v.reason
        );
    }

    #[test]
    fn below_event_floor_holds() {
        let mut inp = strong();
        inp.distinct_events = 20;
        let v = pilot_verdict(&inp, &PilotThresholds::default());
        assert!(!v.go);
        assert!(v.reason.contains("need 30 more"), "reason: {}", v.reason);
    }

    #[test]
    fn thin_liquidity_holds() {
        let mut inp = strong();
        inp.median_sharp_usd = Some(500.0);
        let v = pilot_verdict(&inp, &PilotThresholds::default());
        assert!(!v.go);
        assert!(v.reason.contains("too thin"), "reason: {}", v.reason);
    }

    #[test]
    fn noisy_edge_lower_bound_holds() {
        // +2% honest ROI but noisy → corrected LB ≤ pilot bar → HOLD.
        let mut inp = strong();
        inp.honest_roi = Some(0.02);
        inp.honest_roi_sd = Some(0.30);
        let v = pilot_verdict(&inp, &PilotThresholds::default());
        assert!(!v.go);
        assert!(v.reason.contains("lower bound"), "reason: {}", v.reason);
    }

    #[test]
    fn corrected_bound_tightens_with_family_size() {
        let mut few = strong();
        few.n_family = 2;
        let mut many = strong();
        many.n_family = 50;
        let vf = pilot_verdict(&few, &PilotThresholds::default());
        let vm = pilot_verdict(&many, &PilotThresholds::default());
        assert!(
            vf.corrected_lower_bound.unwrap() > vm.corrected_lower_bound.unwrap(),
            "more comparisons ⇒ stricter z ⇒ lower bound shrinks"
        );
    }

    #[test]
    fn required_regimes_uses_max_of_frac_and_floor() {
        let th = PilotThresholds::default();
        // 10 regimes × 0.7 = 7 > floor 5.
        assert_eq!(required_regimes(10, &th), 7);
        // 3 regimes × 0.7 = ceil(2.1)=3, but floor 5 dominates.
        assert_eq!(required_regimes(3, &th), 5);
    }

    #[test]
    fn capacity_caps_at_liquidity_fraction() {
        // median $1000 × 5% = $50 < flat $100 → stake capped at $50.
        let c = capacity(100.0, 0.05, Some(1000.0), Some(4.0), Some(12.0), Some(0.08));
        assert!((c.suggested_stake - 50.0).abs() < 1e-9);
        // working capital = 4 bets/day × 0.5 day hold × $50 = $100.
        assert!((c.working_capital - 100.0).abs() < 1e-6);
        // projected/week = 4 × 7 × $50 × 0.08 = $112.
        assert!((c.projected_weekly - 112.0).abs() < 1e-6);
    }
}
