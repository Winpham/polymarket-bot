//! WS-D — UNARMED PILOT HARNESS (default-OFF, one-approval-away, places NOTHING).
//!
//! A tiny de-levered real-money pilot is the only thing that produces genuine OUT-of-sample truth to
//! move λ off "unknown" (D18/D19). This module stands it up so it is ONE APPROVAL away — de-levered
//! sizing (WS-B's ⅟₁₂-Kelly), hard kill-switches, and CLV + honest realizable-P&L tracking — while
//! guaranteeing it can place no order without Tue's explicit arming. It is deliberately **NOT wired
//! into `live.rs`**: the running binary never calls it, so live behaviour is byte-identical. The
//! `#![allow(dead_code)]` below is that guarantee made visible — it is removed only when the harness
//! is wired, which is gated on the real-money decision (Tue's).
//!
//! Two independent locks make the place path unreachable in this build (proven in the tests):
//!   1. `OrderGate::place` refuses with `NotArmed` unless `PILOT_ARMED=1` (env) AND the master switch
//!      is on AND no kill-switch has latched.
//!   2. Even if armed, there is NO order client wired (the bot is paper-only), so `place` returns
//!      `NoPlacer` — it physically cannot submit an order in this build.
//!
//! Nothing here is invoked by the daemon. Real money awaits Tue's go.
#![allow(dead_code)]

use std::collections::HashMap;

/// Trading fee per unit staked (matches `risk_engine` / `corr_risk_engine`).
pub const FEE: f64 = 0.02;
/// WS-B pinned de-lever knee (⅟₁₂-Kelly); ⅟₁₆ is the conservative default given WS-A's low λ̂.
pub const DELEVER_K: f64 = 1.0 / 12.0;
/// Absolute per-position stake-fraction cap (belt-and-suspenders over Kelly).
pub const STAKE_FRAC_CAP: f64 = 0.05;

/// Why the pilot refused to place. Any variant means NO order was submitted.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PilotError {
    /// `PILOT_ARMED` is not set to "1" — the default state. Tue-only to change.
    NotArmed,
    /// Armed, but no order client is wired (the bot is paper-only). Places nothing regardless.
    NoPlacer,
    /// A kill-switch has latched; the pilot is halted until an explicit reset.
    Halted(HaltReason),
    /// Sizing produced a non-positive or non-finite stake — never place.
    NoStake,
}

/// A latching halt condition. Once tripped, the pilot places nothing until `reset()`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HaltReason {
    /// Cumulative realized loss on the current UTC day exceeded the day stop-loss.
    DayStopLoss,
    /// Peak-to-trough equity drawdown exceeded the ceiling.
    MaxDrawdown,
    /// The edge-degradation monitor (CLV/λ or persistence) fell below its floor.
    EdgeDegraded,
    /// The manual master switch is off.
    MasterOff,
}

/// Pilot risk configuration. All conservative by default; overridable from env when (and only when)
/// a pilot is actually stood up.
#[derive(Debug, Clone)]
pub struct PilotConfig {
    pub bankroll: f64,
    pub delever_k: f64,
    /// Halt for the day if cumulative day P&L ≤ −(day_stop_loss_frac · bankroll).
    pub day_stop_loss_frac: f64,
    /// Halt entirely if peak-to-trough drawdown ≥ max_drawdown_frac.
    pub max_drawdown_frac: f64,
    /// Halt if the live λ̂/CLV estimate falls below this floor (edge-degradation).
    pub min_lambda: f64,
    /// Master switch — must be true to place anything.
    pub master_on: bool,
}

impl Default for PilotConfig {
    fn default() -> Self {
        // Deliberately tiny + tight: a truth-generating pilot, not a profit engine.
        Self {
            bankroll: 500.0,
            delever_k: DELEVER_K,
            day_stop_loss_frac: 0.05,
            max_drawdown_frac: 0.15,
            min_lambda: 0.25,
            master_on: false,
        }
    }
}

/// True only if the operator has explicitly armed the pilot via `PILOT_ARMED=1`. This is the single
/// env gate Tue controls; nothing else in the codebase sets it.
pub fn armed_from_env() -> bool {
    std::env::var("PILOT_ARMED")
        .map(|v| v == "1")
        .unwrap_or(false)
}

/// Two-outcome Kelly stake FRACTION of bankroll for buying a share at price `c` when the (calibrated,
/// conservative) win probability is `p`, de-levered by `k` and hard-capped. Mirrors
/// `risk_engine.kelly_by_band`'s exact two-outcome Kelly (`f* = p/(1+FEE) − (1−p)/r_win`).
/// Returns 0 when there is no favourable payout or no positive edge.
pub fn delevered_stake_frac(c: f64, p: f64, k: f64) -> f64 {
    if !(0.0..1.0).contains(&c) || !(0.0..=1.0).contains(&p) {
        return 0.0;
    }
    let r_win = (1.0 - c) / c - FEE;
    if r_win <= 0.0 {
        return 0.0;
    }
    let f_star = p / (1.0 + FEE) - (1.0 - p) / r_win;
    if f_star <= 0.0 || !f_star.is_finite() {
        return 0.0;
    }
    (k * f_star).clamp(0.0, STAKE_FRAC_CAP)
}

/// Realizable P&L per unit NOTIONAL for a resolved back: buy at `entry`+1¢ haircut, pay `FEE` on cost.
/// `won` in {0,1}. Matches the flat-shares realizable model used across the Python instruments.
pub fn realizable_pnl(entry: f64, won: f64, notional: f64) -> f64 {
    let e = (entry + 0.01).min(0.999);
    notional * (won - e) - FEE * notional * e
}

/// The kill-switch state machine + equity tracker. Latching: once halted it stays halted until reset.
#[derive(Debug, Clone)]
pub struct KillSwitch {
    cfg: PilotConfig,
    equity: f64,
    peak: f64,
    day_pnl: f64,
    day: String,
    lambda_est: f64,
    halted: Option<HaltReason>,
}

impl KillSwitch {
    pub fn new(cfg: PilotConfig) -> Self {
        let equity = cfg.bankroll;
        let lambda_est = cfg.min_lambda.max(0.5); // start above the floor; updated by the monitor
        let mut ks = Self {
            cfg,
            equity,
            peak: equity,
            day_pnl: 0.0,
            day: String::new(),
            lambda_est,
            halted: None,
        };
        // Safety-first: a pilot whose master switch is off is halted FROM BIRTH — the default state
        // places nothing without an explicit master_on, before any fill is ever recorded.
        ks.evaluate();
        ks
    }

    pub fn equity(&self) -> f64 {
        self.equity
    }
    pub fn halted(&self) -> Option<HaltReason> {
        self.halted
    }

    /// Feed the latest edge-degradation estimate (e.g. rolling CLV-implied λ̂ or persistence score).
    pub fn update_lambda(&mut self, lambda_est: f64) {
        self.lambda_est = lambda_est;
        self.evaluate();
    }

    /// Record a realized fill's P&L on `utc_day` (YYYY-MM-DD), updating equity/day/drawdown, then
    /// re-evaluate the halts.
    pub fn on_fill(&mut self, pnl: f64, utc_day: &str) {
        if utc_day != self.day {
            self.day = utc_day.to_string();
            self.day_pnl = 0.0;
        }
        self.equity += pnl;
        self.day_pnl += pnl;
        if self.equity > self.peak {
            self.peak = self.equity;
        }
        self.evaluate();
    }

    fn evaluate(&mut self) {
        if self.halted.is_some() {
            return; // latched
        }
        if !self.cfg.master_on {
            self.halted = Some(HaltReason::MasterOff);
        } else if self.day_pnl <= -(self.cfg.day_stop_loss_frac * self.cfg.bankroll) {
            self.halted = Some(HaltReason::DayStopLoss);
        } else if self.peak > 0.0
            && (self.peak - self.equity) / self.peak >= self.cfg.max_drawdown_frac
        {
            self.halted = Some(HaltReason::MaxDrawdown);
        } else if self.lambda_est < self.cfg.min_lambda {
            self.halted = Some(HaltReason::EdgeDegraded);
        }
    }

    pub fn reset(&mut self) {
        self.halted = None;
    }
}

/// A proposed pilot order (paper representation). `notional` is the de-levered stake in $.
#[derive(Debug, Clone)]
pub struct PilotOrder {
    pub condition_id: String,
    pub outcome_index: i32,
    pub price: f64,
    pub notional: f64,
}

/// The order gate — the ONLY path that could place, and it is locked shut. There is no order client
/// (the bot is paper-only), so even an armed, un-halted gate returns `NoPlacer`.
pub struct OrderGate<'a> {
    armed: bool,
    ks: &'a KillSwitch,
}

impl<'a> OrderGate<'a> {
    pub fn new(ks: &'a KillSwitch) -> Self {
        Self {
            armed: armed_from_env(),
            ks,
        }
    }

    /// Test-only constructor to exercise the armed branch without touching process env.
    #[cfg(test)]
    fn with_armed(ks: &'a KillSwitch, armed: bool) -> Self {
        Self { armed, ks }
    }

    /// Attempt to place. In this build it can NEVER succeed: unarmed ⇒ NotArmed; halted ⇒ Halted;
    /// armed ⇒ NoPlacer (no order client is wired). Returns Ok only if a real placer is ever added
    /// AND Tue arms AND no kill-switch has latched — none of which hold in this build.
    pub fn place(&self, order: &PilotOrder) -> Result<(), PilotError> {
        if !self.armed {
            return Err(PilotError::NotArmed);
        }
        if let Some(reason) = self.ks.halted() {
            return Err(PilotError::Halted(reason));
        }
        if !order.notional.is_finite() || order.notional <= 0.0 {
            return Err(PilotError::NoStake);
        }
        // Armed, un-halted, positive stake — and STILL no order client exists. Places nothing.
        Err(PilotError::NoPlacer)
    }
}

/// Running CLV + honest realizable-P&L tracker for the pilot's fills. Reconciles paper vs would-be
/// real (identical while paper).
#[derive(Debug, Default, Clone)]
pub struct PilotLedger {
    pub n_fills: u64,
    pub clv_sum: f64,
    pub realizable_pnl: f64,
    pub by_day: HashMap<String, f64>,
}

impl PilotLedger {
    /// Record a resolved fill. `entry` = at-fire price, `close` = last pre-resolution mid (CLV close),
    /// `won` in {0,1}, `notional` = staked $.
    pub fn record(&mut self, entry: f64, close: f64, won: f64, notional: f64, utc_day: &str) {
        self.n_fills += 1;
        self.clv_sum += close - entry;
        let pnl = realizable_pnl(entry, won, notional);
        self.realizable_pnl += pnl;
        *self.by_day.entry(utc_day.to_string()).or_insert(0.0) += pnl;
    }

    pub fn mean_clv(&self) -> f64 {
        if self.n_fills == 0 {
            0.0
        } else {
            self.clv_sum / self.n_fills as f64
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn armed_config() -> PilotConfig {
        PilotConfig {
            master_on: true,
            ..PilotConfig::default()
        }
    }

    #[test]
    fn place_refuses_when_unarmed() {
        // The core unreachability proof: default (unarmed) gate refuses, no matter the order.
        let ks = KillSwitch::new(armed_config());
        let gate = OrderGate::with_armed(&ks, false);
        let order = PilotOrder {
            condition_id: "c".into(),
            outcome_index: 0,
            price: 0.8,
            notional: 10.0,
        };
        assert_eq!(gate.place(&order), Err(PilotError::NotArmed));
    }

    #[test]
    fn place_refuses_even_when_armed_no_placer() {
        // Second lock: even armed + un-halted + positive stake, there is no order client → NoPlacer.
        let mut cfg = armed_config();
        cfg.min_lambda = 0.0; // keep edge monitor from latching in this unit
        let mut ks = KillSwitch::new(cfg);
        ks.update_lambda(1.0);
        assert_eq!(ks.halted(), None);
        let gate = OrderGate::with_armed(&ks, true);
        let order = PilotOrder {
            condition_id: "c".into(),
            outcome_index: 0,
            price: 0.8,
            notional: 10.0,
        };
        assert_eq!(gate.place(&order), Err(PilotError::NoPlacer));
    }

    #[test]
    fn armed_gate_still_blocked_by_halt() {
        let ks = KillSwitch::new(PilotConfig::default()); // master_off by default → latches MasterOff
        let gate = OrderGate::with_armed(&ks, true);
        let order = PilotOrder {
            condition_id: "c".into(),
            outcome_index: 0,
            price: 0.8,
            notional: 10.0,
        };
        assert_eq!(
            gate.place(&order),
            Err(PilotError::Halted(HaltReason::MasterOff))
        );
    }

    #[test]
    fn day_stop_loss_latches() {
        let mut ks = KillSwitch::new(armed_config());
        // day_stop = 5% of 500 = 25. One −30 fill trips it, and it stays latched.
        ks.on_fill(-30.0, "2026-07-03");
        assert_eq!(ks.halted(), Some(HaltReason::DayStopLoss));
        ks.on_fill(100.0, "2026-07-03"); // a win does not un-latch
        assert_eq!(ks.halted(), Some(HaltReason::DayStopLoss));
    }

    #[test]
    fn max_drawdown_halts() {
        let mut cfg = armed_config();
        cfg.day_stop_loss_frac = 1.0; // disable day stop so we isolate drawdown
        let mut ks = KillSwitch::new(cfg);
        ks.on_fill(100.0, "2026-07-03"); // peak 600
        ks.on_fill(-95.0, "2026-07-04"); // equity 505, dd = 95/600 = 15.8% ≥ 15%
        assert_eq!(ks.halted(), Some(HaltReason::MaxDrawdown));
    }

    #[test]
    fn edge_degradation_halts() {
        let mut ks = KillSwitch::new(armed_config());
        ks.update_lambda(0.10); // below min_lambda 0.25
        assert_eq!(ks.halted(), Some(HaltReason::EdgeDegraded));
    }

    #[test]
    fn master_off_halts_by_default() {
        let ks = KillSwitch::new(PilotConfig::default());
        assert_eq!(ks.halted(), Some(HaltReason::MasterOff));
    }

    #[test]
    fn delevered_stake_is_twelfth_kelly() {
        // c=0.8, p=0.85: r_win=(0.2/0.8)-0.02=0.23; f*=0.85/1.02 - 0.15/0.23 = 0.8333-0.6522=0.1812.
        // ⅟₁₂ · 0.1812 = 0.01510, under the 5% cap.
        let f = delevered_stake_frac(0.8, 0.85, DELEVER_K);
        assert!((f - 0.01510).abs() < 1e-4, "got {f}");
        // no edge (p ≤ c after fee) ⇒ 0
        assert_eq!(delevered_stake_frac(0.8, 0.80, DELEVER_K), 0.0);
        // full Kelly is capped
        assert!(delevered_stake_frac(0.5, 0.99, 1.0) <= STAKE_FRAC_CAP + 1e-12);
    }

    #[test]
    fn realizable_pnl_matches_model() {
        assert!((realizable_pnl(0.80, 1.0, 100.0) - 17.38).abs() < 1e-6);
        assert!((realizable_pnl(0.80, 0.0, 100.0) - (-82.62)).abs() < 1e-6);
    }

    #[test]
    fn ledger_tracks_clv_and_pnl() {
        let mut led = PilotLedger::default();
        led.record(0.80, 0.82, 1.0, 100.0, "2026-07-03");
        led.record(0.70, 0.74, 1.0, 100.0, "2026-07-03");
        assert_eq!(led.n_fills, 2);
        assert!((led.mean_clv() - 0.03).abs() < 1e-9); // (0.02 + 0.04)/2
        assert!(led.realizable_pnl > 0.0);
    }
}
