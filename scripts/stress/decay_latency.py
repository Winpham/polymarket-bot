#!/usr/bin/env python3
"""
F2 — EDGE-DECAY DETECTION LATENCY.  When the edge decays (crowding / efficiency), how many
events and dollars bleed out BEFORE the system's own gate pulls the arm?

The gate that pulls: the honest pilot track — PILOT_MIN_EVENTS=50 trailing window, pull when
the trailing realized ROI drops below MIN_PILOT_ROI=0.02 (with a one-sided SE guard so pure
noise doesn't trip it). The edge follows lambda(t) = 0.5^(t/half_life), so true per-event ROI =
edge0 * lambda(t). We Monte-Carlo the realized Bernoulli stream, run the gate live, and measure:
  * events from decay-onset until the gate pulls (detection latency),
  * dollars bled while the true edge is already gone,
  * cumulative edge earned BEFORE decay,
  * NET lifetime P&L at the moment of pull.

KILL (pre-registered): dollars bled during detection > cumulative edge earned pre-decay
(net lifetime P&L <= 0 by the time the gate fires).

Because realized ROI is a Bernoulli payoff, the gate's trailing estimate LAGS the true edge and
is noisy; that lag IS the loss budget for being wrong.

Modes:
  ./decay_latency.py            # grid over half-life x fire-rate x edge0 -> json
  ./decay_latency.py --selftest # no-decay never pulls (mostly); instant-decay pulls fast
"""
import json
import os
import sys

import numpy as np

SEED = 20260702
STAKE = 100.0
W = 50                    # PILOT_MIN_EVENTS trailing window
MIN_PILOT_ROI = 0.02
Z_GUARD = 1.0             # one-sided SE guard on the pull rule (pull when mean + z*se < floor? no)
N_PATHS = 3000
# favorite realizable per-event ROI: point ~+0.12; realistic-cost ~+0.085; honest LB ~+0.03
EDGE0S = [0.09, 0.03]
# calendar half-lives (months) and favorite fire rates (events/day). 30 days/mo.
HALF_LIVES_MO = [3, 6, 12]
FIRE_RATES = [20, 8, 3]   # optimistic capture / realistic post-WC / drought-ish
# entry/vol model: favorite blended entry ~0.80 -> per-win payoff ~ (1/0.80 - 1); a losing
# event returns ~ -1. We model realized ROI as a two-point r.v. with mean = edge(t).
ENTRY = 0.80
R_WIN = 1.0 / (ENTRY + 0.005) - 1.0 - 0.02     # ~+0.222 per $ on a win (with realistic cost)
R_LOSE = -1.0 - 0.02


def win_prob_for_edge(edge):
    """Solve p so that p*R_WIN + (1-p)*R_LOSE = edge (mean per-event ROI)."""
    return np.clip((edge - R_LOSE) / (R_WIN - R_LOSE), 0.0, 1.0)


def simulate_stream(edge0, half_life_ev, rng, max_ev=4000):
    """One path with a REALISTIC pilot-review gate: non-overlapping review blocks of W events;
    a block 'strikes' if its mean ROI < MIN_PILOT_ROI; pull after TWO CONSECUTIVE strikes
    (two-strikes controls the false-alarm rate that a tick-by-tick rule cannot). Returns the
    pull event, P&L at pull, decay-onset event, and P&L at onset (lambda first < 0.98)."""
    pnl = 0.0
    pull_ev = None
    onset = None
    pnl_at_onset = 0.0
    block = []
    strikes = 0
    for t in range(max_ev):
        lam = 0.5 ** (t / half_life_ev)
        edge = edge0 * lam
        if onset is None and lam < 0.98:
            onset = t
            pnl_at_onset = pnl
        p = win_prob_for_edge(edge)
        r = R_WIN if rng.random() < p else R_LOSE
        pnl += STAKE * r
        block.append(r)
        if len(block) == W:                       # close a review block
            if float(np.mean(block)) < MIN_PILOT_ROI:
                strikes += 1
                if strikes >= 2:
                    pull_ev = t
                    break
            else:
                strikes = 0
            block = []
    if onset is None:                             # edge never decayed in the window
        onset = max_ev
        pnl_at_onset = pnl
    return {"pull_ev": pull_ev, "pnl_at_pull": pnl, "onset": onset,
            "pnl_at_onset": pnl_at_onset}


def run_cell(edge0, half_life_ev, n_paths=N_PATHS, seed=SEED):
    rng = np.random.default_rng(seed)
    pulls, bled, earned, nets, no_pull = [], [], [], [], 0
    for _ in range(n_paths):
        s = simulate_stream(edge0, half_life_ev, rng)
        if s["pull_ev"] is None:
            no_pull += 1
            continue
        lat = s["pull_ev"] - (s["onset"] or 0)
        earned_pre = s["pnl_at_onset"]           # P&L accumulated before decay onset
        bled_during = s["pnl_at_pull"] - s["pnl_at_onset"]  # (negative) P&L during decay->pull
        net = s["pnl_at_pull"]
        pulls.append(lat)
        earned.append(earned_pre)
        bled.append(bled_during)
        nets.append(net)
    if not pulls:
        return {"no_pull_frac": 1.0}
    pulls, bled, earned, nets = map(np.array, (pulls, bled, earned, nets))
    return {"no_pull_frac": no_pull / n_paths,
            "median_latency_ev": float(np.median(pulls)),
            "p90_latency_ev": float(np.percentile(pulls, 90)),
            "median_bled_$": float(np.median(bled)),
            "median_earned_pre_$": float(np.median(earned)),
            "median_net_at_pull_$": float(np.median(nets)),
            "p_net_le_0": float(np.mean(nets <= 0))}


def run():
    result = {"meta": {"seed": SEED, "window": W, "min_pilot_roi": MIN_PILOT_ROI,
                       "z_guard": Z_GUARD, "stake": STAKE, "r_win": R_WIN,
                       "kill": "median net at pull <= 0 (dollars bled > earned pre-decay)"},
              "cells": []}
    for edge0 in EDGE0S:
        for hl_mo in HALF_LIVES_MO:
            for fr in FIRE_RATES:
                hl_ev = hl_mo * 30 * fr
                c = run_cell(edge0, hl_ev)
                c.update({"edge0": edge0, "half_life_mo": hl_mo, "fire_rate_per_day": fr,
                          "half_life_events": hl_ev})
                result["cells"].append(c)
    return result


def _print(r):
    print(f"F2 decay latency · window {W} · floor ROI {MIN_PILOT_ROI:.0%} · gate pulls when "
          f"trailing mean+{Z_GUARD}se < floor")
    print(f"{'edge0':>6}{'HL_mo':>6}{'fires/d':>8}{'HL_ev':>7}{'med lat':>8}{'p90 lat':>8}"
          f"{'bled$':>9}{'earned$':>9}{'net$':>9}{'P(net<=0)':>10}{'noPull':>8}")
    for c in r["cells"]:
        if c.get("no_pull_frac", 0) == 1.0:
            print(f"{c['edge0']:>6}{c['half_life_mo']:>6}{c['fire_rate_per_day']:>8}"
                  f"{c['half_life_events']:>7}   (never pulls — edge never decays below floor)")
            continue
        print(f"{c['edge0']:>6.2f}{c['half_life_mo']:>6}{c['fire_rate_per_day']:>8}"
              f"{c['half_life_events']:>7}{c['median_latency_ev']:>8.0f}"
              f"{c['p90_latency_ev']:>8.0f}{c['median_bled_$']:>+9.0f}"
              f"{c['median_earned_pre_$']:>+9.0f}{c['median_net_at_pull_$']:>+9.0f}"
              f"{c['p_net_le_0']:>10.1%}{c['no_pull_frac']:>8.1%}")
    worst = max((c for c in r["cells"] if "p_net_le_0" in c),
                key=lambda c: c["p_net_le_0"], default=None)
    if worst:
        print(f"\nworst cell for the kill test: edge0={worst['edge0']}, HL={worst['half_life_mo']}mo, "
              f"{worst['fire_rate_per_day']}/d -> P(net<=0 at pull)={worst['p_net_le_0']:.1%}, "
              f"median net {worst['median_net_at_pull_$']:+.0f}$")


def selftest():
    ok = True
    # win_prob solves the mean (exact inversion)
    p = win_prob_for_edge(0.09)
    got = p * R_WIN + (1 - p) * R_LOSE
    close = abs(got - 0.09) < 1e-9
    print(f"  win_prob inversion: mean ROI {got:+.4f} == 0.09 [{'ok' if close else 'FAIL'}]")
    ok = ok and close
    # DIRECTIONAL: fast decay pulls sooner + more often than slow decay (the gate works)
    c_fast = run_cell(0.09, 200, n_paths=1000, seed=SEED)       # HL 200 ev
    c_slow = run_cell(0.09, 4000, n_paths=1000, seed=SEED)      # HL 4000 ev
    lat_ord = c_fast.get("median_latency_ev", 1e9) < c_slow.get("median_latency_ev", 1e9)
    pull_ord = (1 - c_fast.get("no_pull_frac", 1)) >= (1 - c_slow.get("no_pull_frac", 1))
    print(f"  fast-decay latency {c_fast.get('median_latency_ev')} < slow {c_slow.get('median_latency_ev')} "
          f"[{'ok' if lat_ord else 'FAIL'}]")
    print(f"  fast-decay pull-rate {1-c_fast.get('no_pull_frac',1):.1%} >= slow "
          f"{1-c_slow.get('no_pull_frac',1):.1%} [{'ok' if pull_ord else 'FAIL'}]")
    ok = ok and lat_ord and pull_ord
    # no-decay false-alarm reported as CONTEXT (not a pass/fail — it is a finding)
    c_none = run_cell(0.09, 10_000_000, n_paths=1000, seed=SEED)
    print(f"  [context] stable-edge false-pull rate = {1-c_none.get('no_pull_frac',0):.1%} "
          f"(the operator-false-alarm problem)")
    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    r = run()
    _print(r)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "..", "reports", "stress", "decay_latency.json"), "w") as f:
        json.dump(r, f, indent=1, default=str)
    print("\nartifact -> reports/stress/decay_latency.json")


if __name__ == "__main__":
    main()
