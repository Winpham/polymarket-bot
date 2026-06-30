//! Belief-blind promotion gate — the thing that decides what the forward data is
//! FOR: whether a silently-tracked strategy has earned promotion to alerting.
//!
//! It is deliberately strict and pure (no DB/network). A strategy is promotable
//! only if, judged on **surplus over the blind baseline** (favorite-longshot-
//! neutralized) at the **EVENT level** (cluster-robust), the surplus's lower
//! confidence bound clears a margin AFTER a Bonferroni correction across the live
//! strategy family — and only once a distinct-EVENT floor is met. This is the
//! Foresight discipline: small N is indeterminate, multiple comparisons inflate
//! false promotions, and raw edge is gamed by favorites. Never promote on `edge`.

/// Inverse standard-normal CDF (probit) via Acklam's rational approximation.
/// Accurate to ~1e-9 in the central region — ample for confidence z-values.
/// Constants are the published Acklam coefficients (kept verbatim).
#[allow(clippy::excessive_precision)]
fn probit(p: f64) -> f64 {
    if p <= 0.0 {
        return f64::NEG_INFINITY;
    }
    if p >= 1.0 {
        return f64::INFINITY;
    }
    const A: [f64; 6] = [
        -3.969683028665376e+01,
        2.209460984245205e+02,
        -2.759285104469687e+02,
        1.383577518672690e+02,
        -3.066479806614716e+01,
        2.506628277459239e+00,
    ];
    const B: [f64; 5] = [
        -5.447609879822406e+01,
        1.615858368580409e+02,
        -1.556989798598866e+02,
        6.680131188771972e+01,
        -1.328068155288572e+01,
    ];
    const C: [f64; 6] = [
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e+00,
        -2.549732539343734e+00,
        4.374664141464968e+00,
        2.938163982698783e+00,
    ];
    const D: [f64; 4] = [
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e+00,
        3.754408661907416e+00,
    ];
    let plow = 0.02425;
    let phigh = 1.0 - plow;
    if p < plow {
        let q = (-2.0 * p.ln()).sqrt();
        (((((C[0] * q + C[1]) * q + C[2]) * q + C[3]) * q + C[4]) * q + C[5])
            / ((((D[0] * q + D[1]) * q + D[2]) * q + D[3]) * q + 1.0)
    } else if p <= phigh {
        let q = p - 0.5;
        let r = q * q;
        (((((A[0] * r + A[1]) * r + A[2]) * r + A[3]) * r + A[4]) * r + A[5]) * q
            / (((((B[0] * r + B[1]) * r + B[2]) * r + B[3]) * r + B[4]) * r + 1.0)
    } else {
        let q = (-2.0 * (1.0 - p).ln()).sqrt();
        -(((((C[0] * q + C[1]) * q + C[2]) * q + C[3]) * q + C[4]) * q + C[5])
            / ((((D[0] * q + D[1]) * q + D[2]) * q + D[3]) * q + 1.0)
    }
}

/// Tunable promotion thresholds.
#[derive(Debug, Clone)]
pub struct PromotionParams {
    /// Minimum distinct resolved EVENTS before a strategy is even considered.
    pub min_events: i64,
    /// Surplus margin the lower bound must clear (e.g. fees/slippage cushion).
    pub margin: f64,
    /// Family-wise significance before Bonferroni splitting across strategies.
    pub alpha: f64,
}

impl Default for PromotionParams {
    fn default() -> Self {
        Self {
            min_events: 30,
            margin: 0.0,
            alpha: 0.05,
        }
    }
}

/// The gate's verdict for one strategy.
#[derive(Debug, Clone)]
pub struct PromotionVerdict {
    pub promotable: bool,
    /// Bonferroni-corrected one-sided lower confidence bound on surplus.
    pub lower_bound: Option<f64>,
    pub reason: String,
}

/// Decide whether a strategy is promotable from its forward record.
/// `n_strategies` is the size of the live family (Bonferroni denominator).
pub fn promotion_verdict(
    distinct_events: i64,
    surplus: Option<f64>,
    surplus_sd: Option<f64>,
    n_strategies: usize,
    p: &PromotionParams,
) -> PromotionVerdict {
    let Some(surplus) = surplus else {
        return PromotionVerdict {
            promotable: false,
            lower_bound: None,
            reason: "no resolved events yet".into(),
        };
    };
    if distinct_events < p.min_events {
        return PromotionVerdict {
            promotable: false,
            lower_bound: None,
            reason: format!(
                "N={} events < floor {} (need {} more)",
                distinct_events,
                p.min_events,
                p.min_events - distinct_events
            ),
        };
    }
    let sd = surplus_sd.unwrap_or(0.0).max(1e-9);
    // Bonferroni: split alpha across the live family, one-sided.
    let alpha_corr = (p.alpha / n_strategies.max(1) as f64).clamp(1e-6, 0.5);
    let z = probit(1.0 - alpha_corr);
    let se = sd / (distinct_events as f64).sqrt();
    let lower_bound = surplus - z * se;
    let promotable = lower_bound > p.margin;
    let reason = if promotable {
        format!(
            "PROMOTABLE: surplus {:+.1}% (corrected lower bound {:+.1}% > margin {:+.1}%) over {} events",
            surplus * 100.0,
            lower_bound * 100.0,
            p.margin * 100.0,
            distinct_events
        )
    } else {
        format!(
            "hold: lower bound {:+.1}% ≤ margin {:+.1}% (surplus {:+.1}%, N={})",
            lower_bound * 100.0,
            p.margin * 100.0,
            surplus * 100.0,
            distinct_events
        )
    };
    PromotionVerdict {
        promotable,
        lower_bound: Some(lower_bound),
        reason,
    }
}

/// Two-sided Bonferroni-corrected confidence interval on a surplus, reusing the
/// gate's exact z/SE machinery (so `probit` stays private to this module). The
/// lower bound equals `promotion_verdict`'s lower bound for the same inputs —
/// the Trusted test uses `lo > margin`; the symmetric Avoid test uses
/// `hi < -margin`. `n_comparisons` is the Bonferroni denominator (the wallet's
/// slice count, when used for trader trust).
// Consumed by `scanner::trader_trust` (Phase 3 surfacing wires the call sites).
#[allow(dead_code)]
pub fn surplus_bounds(
    distinct_events: i64,
    surplus: f64,
    surplus_sd: Option<f64>,
    n_comparisons: usize,
    p: &PromotionParams,
) -> (f64, f64) {
    let sd = surplus_sd.unwrap_or(0.0).max(1e-9);
    let alpha_corr = (p.alpha / n_comparisons.max(1) as f64).clamp(1e-6, 0.5);
    let z = probit(1.0 - alpha_corr);
    let se = sd / (distinct_events.max(1) as f64).sqrt();
    (surplus - z * se, surplus + z * se) // (lower, upper)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn surplus_bounds_lo_le_hi_and_tighten_with_events() {
        let p = PromotionParams::default();
        let (lo, hi) = surplus_bounds(40, 0.08, Some(0.10), 5, &p);
        assert!(lo < hi, "interval is ordered");
        assert!(
            (((lo + hi) / 2.0) - 0.08).abs() < 1e-9,
            "centered on surplus"
        );
        // More events ⇒ smaller SE ⇒ tighter interval (lo rises).
        let (lo_more, _) = surplus_bounds(400, 0.08, Some(0.10), 5, &p);
        assert!(lo_more > lo, "more events tighten the lower bound");
        // The lower bound matches promotion_verdict's lower bound exactly.
        let v = promotion_verdict(40, Some(0.08), Some(0.10), 5, &p);
        assert!(
            (lo - v.lower_bound.unwrap()).abs() < 1e-12,
            "lo == gate lower bound"
        );
    }

    #[test]
    fn probit_known_quantiles() {
        assert!((probit(0.975) - 1.959963985).abs() < 1e-4);
        assert!((probit(0.95) - 1.644853627).abs() < 1e-4);
        assert!((probit(0.5)).abs() < 1e-6);
    }

    #[test]
    fn below_event_floor_never_promotes() {
        let v = promotion_verdict(10, Some(0.20), Some(0.05), 13, &PromotionParams::default());
        assert!(!v.promotable);
        assert!(v.reason.contains("need 20 more"));
    }

    #[test]
    fn strong_surplus_enough_events_promotes() {
        // 40 events, surplus +8%, tight sd 4% → lower bound clears 0 even after
        // Bonferroni across 13 strategies.
        let v = promotion_verdict(40, Some(0.08), Some(0.04), 13, &PromotionParams::default());
        assert!(v.promotable, "{}", v.reason);
        assert!(v.lower_bound.unwrap() > 0.0);
    }

    #[test]
    fn surplus_straddling_zero_holds() {
        // surplus +2% but noisy (sd 20%) over 40 events → lower bound < 0 → hold.
        let v = promotion_verdict(40, Some(0.02), Some(0.20), 13, &PromotionParams::default());
        assert!(!v.promotable);
        assert!(v.lower_bound.unwrap() < 0.0);
    }

    #[test]
    fn more_strategies_make_promotion_harder() {
        // Same record, more comparisons → stricter z → lower bound shrinks.
        let few = promotion_verdict(40, Some(0.06), Some(0.06), 2, &PromotionParams::default());
        let many = promotion_verdict(40, Some(0.06), Some(0.06), 50, &PromotionParams::default());
        assert!(few.lower_bound.unwrap() > many.lower_bound.unwrap());
    }
}
