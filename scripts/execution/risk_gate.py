#!/usr/bin/env python3
"""
PRE-TRADE RISK GATE — the pure function between a model signal and a real order.

Nothing about the edge matters if a single bad night can ruin the bankroll. This is the last line of
defence: a deterministic, side-effect-free decision that every candidate order must pass. It encodes
the constraints the research earned:

  * 1/8-KELLY sizing (drawdown_kelly: full-Kelly f*=0.556 is reckless — 16% ruin; 1/8 = 0.069 gives
    0% modelled ruin). Size = fraction of bankroll on capital-at-risk, per signal.
  * PER-EVENT exposure cap. The unit of risk is the GAME (project-polymarket-correlated-risk): a
    game's submarkets resolve together, so exposure is capped PER EVENT, not per order.
  * ABSOLUTE size ladder ($50 comfortable / $100 ceiling / $250 hard stop —
    project-polymarket-capacity). No single order exceeds the ceiling; none ever exceeds the stop.
  * PRICE-BAND guard. Only 0.80-0.98. Below 0.80 the model isn't trained; above 0.98 the edge and the
    fee both vanish and slippage dominates.
  * DAILY LOSS LIMIT (circuit breaker). If realised P&L today <= -limit, halt for the day.
  * KILL SWITCH. A single global flag disables all trading, no exceptions.
  * MODEL PROVENANCE. Refuse any signal not produced by the frozen, pre-registered model hash.

This module has NO I/O, NO order path, NO network. It returns a decision; the caller executes (or,
for now, paper-logs). Fully unit-tested — a risk gate you can't trust is worse than none.

  ./risk_gate.py --self-test
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

FROZEN_MODEL_SHA = "ff23718d558ff0a1"     # PREREG_20260715 — refuse anything else


@dataclass(frozen=True)
class RiskConfig:
    kill_switch: bool = False              # global halt
    kelly_fraction: float = 0.069          # 1/8-Kelly (drawdown_kelly)
    bankroll: float = 1000.0               # USD
    max_order_usd: float = 50.0            # start comfortable
    hard_stop_usd: float = 250.0           # never exceed, any path
    per_event_cap_usd: float = 100.0       # total at-risk per GAME
    price_min: float = 0.80
    price_max: float = 0.98
    min_ev: float = 0.01                   # pre-reg primary gate
    daily_loss_limit_usd: float = 150.0    # circuit breaker
    allowed_niches: tuple = ("soccer", "tennis", "esports", "ufc")
    require_model_sha: str = FROZEN_MODEL_SHA


@dataclass
class PortfolioState:
    realized_pnl_today: float = 0.0        # negative = losses
    event_exposure: dict = field(default_factory=dict)   # event_key -> USD at risk already


@dataclass(frozen=True)
class Signal:
    us_slug: str
    event_key: str
    niche: str
    ask: float                             # the price we'd pay (taker)
    ev: float                              # model EV at that ask
    model_sha: str


@dataclass(frozen=True)
class Decision:
    approved: bool
    size_usd: float
    reason: str


def kelly_size(ev: float, ask: float, cfg: RiskConfig) -> float:
    """1/8-Kelly stake in USD. For a binary at price=ask, the model's EV per share is `ev`; the
    capital at risk per share is `ask`. Kelly fraction of bankroll scaled by edge/odds, then the
    1/8 haircut. Bounded by the config's absolute ladder. Conservative by construction."""
    if ask <= 0 or ask >= 1:
        return 0.0
    # edge as a fraction of capital-at-risk; Kelly-lite f* ~ edge / (odds); we already hold a
    # measured 1/8-Kelly fraction, so scale the bankroll allocation by (ev/ask) capped at 1.
    edge_frac = max(0.0, min(1.0, ev / ask))
    raw = cfg.bankroll * cfg.kelly_fraction * edge_frac
    return float(max(0.0, min(raw, cfg.max_order_usd)))


def evaluate(sig: Signal, state: PortfolioState, cfg: RiskConfig) -> Decision:
    """The gate. Deterministic, side-effect-free. Every check can only REDUCE or REFUSE."""
    # 0. kill switch — absolute
    if cfg.kill_switch:
        return Decision(False, 0.0, "kill_switch_engaged")
    # 1. provenance — never trade a non-frozen model's signal
    if sig.model_sha != cfg.require_model_sha:
        return Decision(False, 0.0, f"model_sha_mismatch:{sig.model_sha}")
    # 2. universe
    if sig.niche not in cfg.allowed_niches:
        return Decision(False, 0.0, f"niche_not_allowed:{sig.niche}")
    # 3. price band
    if not (cfg.price_min <= sig.ask <= cfg.price_max):
        return Decision(False, 0.0, f"price_out_of_band:{sig.ask:.3f}")
    # 4. EV gate
    if sig.ev < cfg.min_ev:
        return Decision(False, 0.0, f"ev_below_min:{sig.ev:.4f}")
    # 5. daily circuit breaker
    if state.realized_pnl_today <= -abs(cfg.daily_loss_limit_usd):
        return Decision(False, 0.0, "daily_loss_limit_hit")
    # 6. size it (1/8-Kelly), then apply caps
    size = kelly_size(sig.ev, sig.ask, cfg)
    if size <= 0:
        return Decision(False, 0.0, "kelly_size_zero")
    # 7. per-event exposure cap (the game is the unit of risk)
    already = state.event_exposure.get(sig.event_key, 0.0)
    room = cfg.per_event_cap_usd - already
    if room <= 0:
        return Decision(False, 0.0, f"event_cap_full:{sig.event_key}")
    size = min(size, room)
    # 8. absolute hard stop — belt and suspenders (should already be under max_order)
    size = min(size, cfg.hard_stop_usd)
    if size < 1.0:
        return Decision(False, 0.0, "size_below_min_ticket")
    return Decision(True, round(size, 2), "approved")


# ---------------------------------------------------------------------------- tests
def self_test():
    cfg = RiskConfig()
    ok = Signal("atp-a-b-2026-07-15-x", "atp-a-b-2026-07-15", "tennis", 0.88, 0.03,
                FROZEN_MODEL_SHA)

    # happy path approves with a sane, capped size
    d = evaluate(ok, PortfolioState(), cfg)
    assert d.approved and 0 < d.size_usd <= cfg.max_order_usd, d

    # kill switch refuses everything
    assert not evaluate(ok, PortfolioState(), RiskConfig(kill_switch=True)).approved

    # wrong model hash is refused (provenance)
    bad = Signal(ok.us_slug, ok.event_key, ok.niche, ok.ask, ok.ev, "deadbeefdeadbeef")
    assert not evaluate(bad, PortfolioState(), cfg).approved

    # niche not allowed
    mlb = Signal("mlb-a-b-2026-07-15", "mlb-a-b-2026-07-15", "mlb", 0.88, 0.03, FROZEN_MODEL_SHA)
    assert evaluate(mlb, PortfolioState(), cfg).reason.startswith("niche_not_allowed")

    # price band: below 0.80 and above 0.98 both refused
    assert not evaluate(Signal("s", "e", "tennis", 0.70, 0.03, FROZEN_MODEL_SHA),
                        PortfolioState(), cfg).approved
    assert not evaluate(Signal("s", "e", "tennis", 0.99, 0.03, FROZEN_MODEL_SHA),
                        PortfolioState(), cfg).approved

    # EV below min refused
    assert not evaluate(Signal("s", "e", "tennis", 0.88, 0.005, FROZEN_MODEL_SHA),
                        PortfolioState(), cfg).approved

    # daily loss limit halts
    hit = PortfolioState(realized_pnl_today=-cfg.daily_loss_limit_usd)
    assert evaluate(ok, hit, cfg).reason == "daily_loss_limit_hit"

    # per-event cap: a game already at the cap gets refused; partially-used gets the remainder
    full = PortfolioState(event_exposure={ok.event_key: cfg.per_event_cap_usd})
    assert evaluate(ok, full, cfg).reason.startswith("event_cap_full")
    partial = PortfolioState(event_exposure={ok.event_key: cfg.per_event_cap_usd - 5})
    dp = evaluate(ok, partial, cfg)
    assert dp.approved and dp.size_usd <= 5.0, dp

    # size never exceeds the ceiling even with a huge edge/bankroll
    big = RiskConfig(bankroll=1_000_000, max_order_usd=50)
    d2 = evaluate(Signal("s", "e", "tennis", 0.85, 0.5, FROZEN_MODEL_SHA), PortfolioState(), big)
    assert d2.size_usd <= 50.0, d2

    # size scales DOWN with a thinner edge
    thin = evaluate(Signal("s", "e", "tennis", 0.88, 0.012, FROZEN_MODEL_SHA),
                    PortfolioState(), cfg)
    fat = evaluate(Signal("s", "e", "tennis", 0.88, 0.05, FROZEN_MODEL_SHA),
                   PortfolioState(), cfg)
    assert thin.size_usd < fat.size_usd, (thin, fat)

    # monotonic: a hard stop is never breached even if max_order is misconfigured high
    weird = RiskConfig(bankroll=10_000, max_order_usd=10_000, hard_stop_usd=250,
                       per_event_cap_usd=10_000)
    d3 = evaluate(Signal("s", "e", "tennis", 0.85, 0.9, FROZEN_MODEL_SHA), PortfolioState(), weird)
    assert d3.size_usd <= 250.0, d3

    print("self-test OK  (kill-switch, provenance, band, EV, daily-limit, event-cap, "
          "Kelly-sizing, hard-stop — all enforced)")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test())
    ap.print_help()
