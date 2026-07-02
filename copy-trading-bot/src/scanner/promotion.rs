//! Belief-blind promotion gate — the thing that decides what the forward data is
//! FOR: whether a silently-tracked strategy has earned promotion to alerting.
//!
//! It is deliberately strict and pure (no DB/network). A strategy is promotable
//! only if ALL of (DECISIONS.md D7):
//!  (a) judged on **surplus over the blind baseline** (favorite-longshot-
//!      neutralized) at the **EVENT level**, the surplus's lower confidence
//!      bound clears a margin AFTER a Bonferroni correction across the live
//!      strategy family, once a distinct-EVENT floor is met. The SE deflates N
//!      to distinct **event-days** (Moulton-style full within-day correlation),
//!      so one correlated World-Cup weekend cannot clear the bar on its own;
//!  (b) the pre-registered **selection-matched null** (`scripts/selection_null.py`,
//!      (band × UTC-day)-matched draws from `_blind`) gave p ≤
//!      [`SELECTION_NULL_P_BAR`]. The null is produced OUT-OF-BAND and fed in;
//!      absent / malformed / failing ⇒ NOT promotable (fail-closed). This closes
//!      the `market_resid`-class false promote: a purely compositional arm can
//!      beat the population baseline without any selection skill.
//!
//! This is the Foresight discipline: small N is indeterminate, multiple
//! comparisons inflate false promotions, raw edge is gamed by favorites, and a
//! population baseline alone cannot rule out compositional selection effects.
//! Never promote on `edge`.
//!
//! Provenance contract (honest limits): the null p values must come from a
//! `--calibrate`-PASSING ≥1000-draw run of `scripts/selection_null.py`. Rust
//! enforces presence + the bar; it cannot verify provenance, freshness, or draw
//! count of the out-of-band run.

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

/// Default surplus margin the corrected lower bound must clear: the capture
/// cost cushion (fees + slippage, DECISIONS.md D7 rule (a)) a follower actually
/// pays. The old literal-`0.0` default certified strategies (and wallets, via
/// `trader_trust`) against a zero baseline — a false-promote class. Never
/// default this back to 0; callers with a sharper measured cost override it.
pub const DEFAULT_PROMOTION_MARGIN: f64 = 0.03;

/// Selection-matched null bar (DECISIONS.md D7 rule (b)): the empirical p from
/// the pre-registered `scripts/selection_null.py` must be ≤ this. Absent,
/// malformed, or above the bar ⇒ NOT promotable — fail-closed.
pub const SELECTION_NULL_P_BAR: f64 = 0.01;

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
            margin: DEFAULT_PROMOTION_MARGIN,
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
    /// The cluster-deflated N the SE used: distinct event-days clamped to
    /// `[1, distinct_events]` (unknown day counts degrade to 1 — fail-closed).
    pub effective_n: i64,
    /// Whether a valid selection-matched null p ≤ [`SELECTION_NULL_P_BAR`]
    /// was supplied (rule (b)). `false` blocks promotion regardless of the LB.
    pub selection_null_ok: bool,
    pub reason: String,
}

/// Parse the out-of-band selection-null feed: a `strategy=p[,strategy=p...]`
/// map. Malformed, non-finite, or out-of-`[0,1]` entries are DROPPED — never
/// defaulted — so a bad entry can only make its strategy unpromotable
/// (fail-closed), never promotable.
pub fn parse_selection_null_map(raw: &str) -> std::collections::HashMap<String, f64> {
    raw.split(',')
        .filter_map(|kv| {
            let (k, v) = kv.split_once('=')?;
            let k = k.trim();
            let p: f64 = v.trim().parse().ok()?;
            (!k.is_empty() && p.is_finite() && (0.0..=1.0).contains(&p)).then(|| (k.to_string(), p))
        })
        .collect()
}

/// The selection-null p for one strategy, read from the `SELECTION_NULL_P` env
/// var (`strategy=p,strategy=p` — the operator pastes the p_emp column of a
/// `--calibrate`-PASSING ≥1000-draw `scripts/selection_null.py` run). `None`
/// (unset var or strategy not listed) means the gate holds fail-closed. Rust
/// cannot verify the run's provenance/freshness/draw count — presence + the
/// [`SELECTION_NULL_P_BAR`] bar is what it enforces.
pub fn selection_null_p_for(strategy: &str) -> Option<f64> {
    let raw = std::env::var("SELECTION_NULL_P").ok()?;
    parse_selection_null_map(&raw).get(strategy).copied()
}

/// Decide whether a strategy is promotable from its forward record.
/// `n_strategies` is the size of the live family (Bonferroni denominator);
/// `distinct_days` is the distinct-event-DAY count that deflates the SE's N
/// (within-day correlation); `selection_null_p` is the out-of-band
/// selection-matched null (rule (b)) — `None` ⇒ hold, fail-closed.
/// The reason names the FIRST binding failure; the lower bound is always
/// computed once past the event floor (surfaces honestly even on hold).
pub fn promotion_verdict(
    distinct_events: i64,
    distinct_days: i64,
    surplus: Option<f64>,
    surplus_sd: Option<f64>,
    n_strategies: usize,
    selection_null_p: Option<f64>,
    p: &PromotionParams,
) -> PromotionVerdict {
    // Effective N: full within-day-correlation (Moulton-style) bound. Clamping
    // low means a missing/zero day count degrades to 1 (SE = sd — essentially
    // never promotes); clamping high keeps it an N-DEFLATION only.
    let effective_n = distinct_days.clamp(1, distinct_events.max(1));
    let selection_null_ok = selection_null_p
        .is_some_and(|q| q.is_finite() && (0.0..=1.0).contains(&q) && q <= SELECTION_NULL_P_BAR);
    let Some(surplus) = surplus else {
        return PromotionVerdict {
            promotable: false,
            lower_bound: None,
            effective_n,
            selection_null_ok,
            reason: "no resolved events yet".into(),
        };
    };
    if distinct_events < p.min_events {
        return PromotionVerdict {
            promotable: false,
            lower_bound: None,
            effective_n,
            selection_null_ok,
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
    let se = sd / (effective_n as f64).sqrt();
    let lower_bound = surplus - z * se;
    // Rule (b) is a REQUIRED precondition: surplus-over-population-baseline
    // alone can never promote. Checked before the margin so the reason names
    // the missing null even when the LB looks strong.
    if !selection_null_ok {
        let reason = match selection_null_p {
            None => format!(
                "hold: selection-matched null missing (run scripts/selection_null.py and feed \
                 SELECTION_NULL_P; fail-closed) — lower bound {:+.1}% not sufficient alone",
                lower_bound * 100.0
            ),
            Some(q) if !q.is_finite() || !(0.0..=1.0).contains(&q) => {
                format!("hold: selection null p invalid ({q}); treated as missing (fail-closed)")
            }
            Some(q) => format!(
                "hold: selection null p={:.4} > {} (surplus not distinguishable from a \
                 selection-matched blind draw)",
                q, SELECTION_NULL_P_BAR
            ),
        };
        return PromotionVerdict {
            promotable: false,
            lower_bound: Some(lower_bound),
            effective_n,
            selection_null_ok,
            reason,
        };
    }
    let promotable = lower_bound > p.margin;
    let reason = if promotable {
        format!(
            "PROMOTABLE: surplus {:+.1}% (corrected lower bound {:+.1}% > margin {:+.1}%) over {} events / {} event-days (effective N {}), selection null p={:.4} ≤ {}",
            surplus * 100.0,
            lower_bound * 100.0,
            p.margin * 100.0,
            distinct_events,
            distinct_days,
            effective_n,
            selection_null_p.unwrap_or(f64::NAN),
            SELECTION_NULL_P_BAR
        )
    } else {
        format!(
            "hold: lower bound {:+.1}% ≤ margin {:+.1}% (surplus {:+.1}%, N={} events over {} event-days, effective N {})",
            lower_bound * 100.0,
            p.margin * 100.0,
            surplus * 100.0,
            distinct_events,
            distinct_days,
            effective_n
        )
    };
    PromotionVerdict {
        promotable,
        lower_bound: Some(lower_bound),
        effective_n,
        selection_null_ok,
        reason,
    }
}

/// Two-sided Bonferroni-corrected confidence interval on a surplus, reusing the
/// gate's exact z/SE machinery (so `probit` stays private to this module).
/// `distinct_events` is the caller's DE-CORRELATED N: `trader_trust` passes a
/// day-deflated effective N; `honest.rs`'s pilot path deliberately keeps its
/// event-level N (its thresholds are pre-registered separately). The lower
/// bound equals `promotion_verdict`'s lower bound for the same effective N —
/// the Trusted test uses `lo > margin`; the Avoid test uses `hi < 0`.
/// `n_comparisons` is the Bonferroni denominator (the wallet's slice count,
/// when used for trader trust).
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

    /// A passing selection-null reading (well below the 0.01 bar).
    const NULL_PASS: Option<f64> = Some(0.001);

    #[test]
    fn default_margin_is_the_capture_cushion_not_zero() {
        // The margin-0.0 default was the false-promote bug: certifying against
        // a literal-zero baseline. The default must carry the real cost margin.
        let p = PromotionParams::default();
        assert_eq!(p.margin, DEFAULT_PROMOTION_MARGIN);
        assert!(p.margin > 0.0, "default margin must never be 0 again");
    }

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
        // The lower bound matches promotion_verdict's lower bound exactly when
        // days == events (no clustering deflation).
        let v = promotion_verdict(40, 40, Some(0.08), Some(0.10), 5, NULL_PASS, &p);
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
        let v = promotion_verdict(
            10,
            10,
            Some(0.20),
            Some(0.05),
            13,
            NULL_PASS,
            &PromotionParams::default(),
        );
        assert!(!v.promotable);
        assert!(v.reason.contains("need 20 more"));
    }

    #[test]
    fn strong_surplus_enough_events_promotes() {
        // GENUINE case: 40 events over 40 distinct days, surplus +8%, tight sd
        // 4%, null passed → LB ≈ +6.3% clears the 3% capture margin even after
        // Bonferroni across 13 strategies.
        let v = promotion_verdict(
            40,
            40,
            Some(0.08),
            Some(0.04),
            13,
            NULL_PASS,
            &PromotionParams::default(),
        );
        assert!(v.promotable, "{}", v.reason);
        assert!(v.lower_bound.unwrap() > DEFAULT_PROMOTION_MARGIN);
        assert_eq!(v.effective_n, 40);
        assert!(v.selection_null_ok);
    }

    #[test]
    fn surplus_straddling_zero_holds() {
        // surplus +2% but noisy (sd 20%) over 40 events → lower bound < 0 → hold.
        let v = promotion_verdict(
            40,
            40,
            Some(0.02),
            Some(0.20),
            13,
            NULL_PASS,
            &PromotionParams::default(),
        );
        assert!(!v.promotable);
        assert!(v.lower_bound.unwrap() < 0.0);
    }

    #[test]
    fn more_strategies_make_promotion_harder() {
        // Same record, more comparisons → stricter z → lower bound shrinks.
        let p = PromotionParams::default();
        let few = promotion_verdict(40, 40, Some(0.06), Some(0.06), 2, NULL_PASS, &p);
        let many = promotion_verdict(40, 40, Some(0.06), Some(0.06), 50, NULL_PASS, &p);
        assert!(few.lower_bound.unwrap() > many.lower_bound.unwrap());
    }

    // --- The false-promote class this hardening closes ---

    #[test]
    fn null_absent_rejects_even_with_strong_lower_bound() {
        // FALSE-PROMOTE (a1): a record whose LB comfortably clears the margin —
        // it WOULD have promoted on surplus-over-population-baseline alone —
        // must hold when the selection-matched null was never produced.
        let v = promotion_verdict(
            40,
            40,
            Some(0.08),
            Some(0.04),
            13,
            None,
            &PromotionParams::default(),
        );
        assert!(!v.promotable, "{}", v.reason);
        assert!(
            v.lower_bound.unwrap() > DEFAULT_PROMOTION_MARGIN,
            "proves this case would have passed the old surplus-only gate"
        );
        assert!(!v.selection_null_ok);
        assert!(v.reason.contains("selection"), "{}", v.reason);
    }

    #[test]
    fn null_failing_or_invalid_rejects_and_boundary_is_pinned() {
        // FALSE-PROMOTE (a2): same strong record, but the null says the surplus
        // is indistinguishable from a selection-matched blind draw.
        let p = PromotionParams::default();
        let with = |q: Option<f64>| promotion_verdict(40, 40, Some(0.08), Some(0.04), 13, q, &p);
        assert!(!with(Some(0.02)).promotable, "p above the bar rejects");
        // Boundary pinned: exactly-at-bar passes (≤), just-above rejects.
        assert!(with(Some(0.010)).promotable);
        assert!(!with(Some(0.011)).promotable);
        // Malformed readings are treated as MISSING, never as passing.
        assert!(!with(Some(f64::NAN)).promotable);
        assert!(!with(Some(1.5)).promotable);
        assert!(!with(Some(-0.1)).promotable);
    }

    #[test]
    fn correlated_weekend_rejected_spread_days_accepted() {
        // FALSE-PROMOTE (a3): 40 "events" packed into 2 correlated event-days
        // (one World-Cup weekend) — effective N 2 blows up the SE, LB ≈ +0.5%
        // < 3% margin ⇒ hold. The IDENTICAL stats over 40 distinct days pass:
        // the deflation discriminates, it doesn't blanket-reject.
        let p = PromotionParams::default();
        let clustered = promotion_verdict(40, 2, Some(0.08), Some(0.04), 13, NULL_PASS, &p);
        assert!(!clustered.promotable, "{}", clustered.reason);
        assert_eq!(clustered.effective_n, 2);
        assert!(clustered.lower_bound.unwrap() < DEFAULT_PROMOTION_MARGIN);
        let spread = promotion_verdict(40, 40, Some(0.08), Some(0.04), 13, NULL_PASS, &p);
        assert!(spread.promotable, "{}", spread.reason);
    }

    #[test]
    fn genuine_case_still_promotes() {
        // (b): real surplus (+12%, sd 6%), 60 events over 30 distinct days,
        // null passed → LB ≈ +9.1% > 3% ⇒ the gate still discriminates.
        let v = promotion_verdict(
            60,
            30,
            Some(0.12),
            Some(0.06),
            13,
            NULL_PASS,
            &PromotionParams::default(),
        );
        assert!(v.promotable, "{}", v.reason);
        assert_eq!(v.effective_n, 30);
    }

    #[test]
    fn margin_zero_regression_hairline_surplus_rejected() {
        // (c): a strategy that beats the baseline by a hair (LB ≈ +1.3% > 0)
        // with no cost cushion — EXACTLY what the old margin-0.0 default
        // certified — must now hold.
        let v = promotion_verdict(
            60,
            60,
            Some(0.02),
            Some(0.02),
            13,
            NULL_PASS,
            &PromotionParams::default(),
        );
        let lb = v.lower_bound.unwrap();
        assert!(
            lb > 0.0 && lb <= DEFAULT_PROMOTION_MARGIN,
            "the case the old gate promoted: lb={lb}"
        );
        assert!(!v.promotable, "{}", v.reason);
        assert!(v.reason.contains("margin"), "{}", v.reason);
    }

    #[test]
    fn effective_n_clamps_fail_closed() {
        let p = PromotionParams::default();
        // Unknown/zero day count degrades to effective N 1 (SE = sd) — a strong
        // record cannot promote on an unknown clustering structure.
        let unknown = promotion_verdict(40, 0, Some(0.08), Some(0.04), 13, NULL_PASS, &p);
        assert_eq!(unknown.effective_n, 1);
        assert!(!unknown.promotable, "{}", unknown.reason);
        // More days than events (impossible upstream) clamps to events — the
        // day count can only DEFLATE N, never inflate it.
        let over = promotion_verdict(40, 100, Some(0.08), Some(0.04), 13, NULL_PASS, &p);
        assert_eq!(over.effective_n, 40);
    }

    // --- The out-of-band null feed parser (pure; env read is a thin wrapper) ---

    #[test]
    fn null_map_parses_valid_entries() {
        let m = parse_selection_null_map("strict=0.001, favorite=0.02,elite_fresh_fav=0.0");
        assert_eq!(m.len(), 3);
        assert_eq!(m["strict"], 0.001);
        assert_eq!(m["favorite"], 0.02);
        assert_eq!(m["elite_fresh_fav"], 0.0);
    }

    #[test]
    fn null_map_drops_malformed_entries_but_keeps_siblings() {
        let m = parse_selection_null_map("strict=0.001,garbage,elite=abc,=0.5,ok=0.5");
        assert_eq!(m.len(), 2, "{m:?}");
        assert_eq!(m["strict"], 0.001);
        assert_eq!(m["ok"], 0.5);
    }

    #[test]
    fn null_map_drops_out_of_range_and_non_finite() {
        // A dropped entry means "missing" downstream — fail-closed, never a pass.
        let m = parse_selection_null_map("a=1.5,b=-0.1,c=NaN,d=inf,e=0.01");
        assert_eq!(m.len(), 1, "{m:?}");
        assert_eq!(m["e"], 0.01);
    }
}
