#!/usr/bin/env python3
"""
PHASE 3 — CONFRONT THE TINY-N PROBLEM HONESTLY.

The composite bad_life_mc.py stresses execution / decay / upset / cost CONDITIONAL on the
observed per-band edge being REAL (edge_mult defaults to 1.0 = the full +12.5% point estimate).
But Phase 0 established the load-bearing fact: the generalization lower bound on favorite's edge,
given G~=4 independent day-blocks, is UNBOUNDED BELOW (df=3 small-sample t LB ~= -8.2%). So a
large share of "it works" is ASSUMED, not supported.

This script re-runs the recommended policy with the true edge DRAWN FROM ITS POSTERIOR, not the
point value, and reports what fraction of favorable outcomes survive once we stop pretending the
4-day point estimate is the truth.

Posterior (honest, small-sample):
  true_surplus ~ point + SE * t(df=3)         # fat-tailed, matches Phase-0 df=3 LB
  point = +12.5% (observed favorite surplus vs blind)
  SE chosen so one-sided 5% LB = -8.2% (Phase 0):  SE = (12.5-(-8.2)) / t_{.95,3=2.353} = 8.8pp
  edge_mult = clip(true_surplus / point, -1.5, 2.0)   # <0 => genuinely adverse edge

We also report the SUPPORTED-vs-ASSUMED decomposition and the expected forward wait to the
go-live gate (N>=50/arm AND >=5 regimes), which is the real cost of finding out.

Modes:
  ./phase3_posterior.py            # -> reports/stress/phase3_posterior.json
  ./phase3_posterior.py --selftest
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bad_life_mc as blm

SEED = 20260702
N_WORLDS = 6000
POINT = 0.125            # observed favorite surplus vs blind
LB_DF3 = -0.082         # Phase-0 honest df=3 one-sided 5% LB
T_95_DF3 = 2.353
SE = (POINT - LB_DF3) / T_95_DF3   # ~= 0.088
DF = 3


def draw_edge_mult(rng):
    """True edge drawn from the fat-tailed small-sample posterior; expressed as a multiplier on
    the observed per-band raw edge."""
    t = rng.standard_t(DF)
    true_surplus = POINT + SE * t
    return float(np.clip(true_surplus / POINT, -1.5, 2.0)), true_surplus


def run(n_worlds=N_WORLDS, seed=SEED):
    cal = blm.calibrate()
    rng = np.random.default_rng(seed)
    # posterior over the edge itself (independent of operational world)
    surpluses = []
    # policy outcomes: flat-SHARES (the recommended real-money policy per risk constitution)
    res = {B: {"pnl": [], "dd": [], "min": []} for B in blm.BANKROLLS}
    neg_edge_worlds = 0
    for i in range(n_worlds):
        w = blm.draw_world(rng)
        em, surplus = draw_edge_mult(rng)
        surpluses.append(surplus)
        if em <= 0:
            neg_edge_worlds += 1
        for B in blm.BANKROLLS:
            r = blm.simulate_world(cal, w, rng, B, kelly=False, edge_mult=em)
            res[B]["pnl"].append(r["pnl"])
            res[B]["dd"].append(r["maxdd"])
            res[B]["min"].append(r["minb_frac"])
    surpluses = np.array(surpluses)
    out = {"meta": {"seed": seed, "n_worlds": n_worlds, "point": POINT, "SE": SE, "df": DF,
                    "policy": "flat_shares_capped", "posterior": "true=point+SE*t(df=3)"},
           "posterior_edge": {
               "mean_true_surplus": float(surpluses.mean()),
               "p_edge_le_0": float(np.mean(surpluses <= 0)),
               "p_edge_le_3pct": float(np.mean(surpluses <= 0.03)),
               "q05": float(np.percentile(surpluses, 5)),
               "q50": float(np.percentile(surpluses, 50)),
               "q95": float(np.percentile(surpluses, 95))},
           "by_bankroll": {}}
    for B in blm.BANKROLLS:
        pnl = np.array(res[B]["pnl"]); dd = np.array(res[B]["dd"]); mn = np.array(res[B]["min"])
        out["by_bankroll"][str(int(B))] = {
            "median_pnl": float(np.median(pnl)),
            "p_net_negative_12mo": float(np.mean(pnl < 0)),
            "p5_pnl": float(np.percentile(pnl, 5)),
            "worst_decile_terminal": float(np.percentile(pnl, 10) + B),
            "p_maxdd_over_30pct": float(np.mean(dd > blm.DD_CEIL)),
            "p_ruin_20pct": float(np.mean(mn <= blm.RUIN_FRAC))}
    return out


def forward_wait():
    """Expected calendar wait to the go-live gate (N>=50/arm AND >=5 distinct regimes).
    Fire-rate bound vs regime bound. Numbers grounded in Phase-0 observed rates."""
    fav_per_day = 72 / 4          # 72 distinct-entry favorite events over 4 active-tournament days
    post_wc = {"optimistic_8_per_day": 8, "central_4_per_day": 4, "drought_2_per_day": 2}
    n_weeks = {}
    for label, rate in post_wc.items():
        # need 50 events; but the BINDING gate is >=5 regimes. Currently 2 real regimes
        # (tennis, soccer) + 2 lucky N<10 slivers. New regimes appear only as new sport
        # seasons/tournaments open -> calendar-bound, not fire-bound.
        weeks_for_N = 50 / (rate * 7)
        n_weeks[label] = round(weeks_for_N, 1)
    return {"fav_events_per_day_observed": fav_per_day,
            "weeks_to_N50_by_rate": n_weeks,
            "binding_constraint": "5 distinct regimes, NOT event count",
            "regimes_now": "2 established (tennis, soccer) + 2 lucky N<10 slivers (mlb, other)",
            "regime_wait_note": ("new regimes accrue only as new sport seasons open; reaching 5 "
                                 "ESTABLISHED regimes is calendar-bound, plausibly 2-6 months "
                                 "spanning multiple sport seasons, and is INDETERMINATE from 4 days")}


def _print(o):
    pe = o["posterior_edge"]
    print("PHASE 3 — EDGE DRAWN FROM POSTERIOR (not point estimate)")
    print(f"  posterior true surplus: q05={pe['q05']:+.1%} q50={pe['q50']:+.1%} q95={pe['q95']:+.1%}")
    print(f"  P(true edge <= 0) = {pe['p_edge_le_0']:.1%}   P(true edge <= +3%) = {pe['p_edge_le_3pct']:.1%}")
    print(f"\n  flat-SHARES policy, edge ~ posterior:")
    print(f"  {'bankroll':>10}{'medP&L':>10}{'P(net<0)':>10}{'P(DD>30%)':>11}{'P(ruin)':>9}{'p5 P&L':>10}")
    for B, s in o["by_bankroll"].items():
        print(f"  {'$'+B:>10}{s['median_pnl']:>+10.0f}{s['p_net_negative_12mo']:>10.1%}"
              f"{s['p_maxdd_over_30pct']:>11.1%}{s['p_ruin_20pct']:>9.1%}{s['p5_pnl']:>+10.0f}")
    fw = o["forward_wait"]
    print(f"\n  forward wait to gate: {fw['weeks_to_N50_by_rate']}  (binding: {fw['binding_constraint']})")


def selftest():
    ok = True
    rng = np.random.default_rng(SEED)
    ms = [draw_edge_mult(rng)[1] for _ in range(20000)]
    ms = np.array(ms)
    # posterior mean ~ point
    c1 = abs(ms.mean() - POINT) < 0.01
    print(f"  posterior mean {ms.mean():+.3f} ~= point {POINT} [{'ok' if c1 else 'FAIL'}]")
    # material mass below zero (the whole point)
    p0 = np.mean(ms <= 0)
    c2 = 0.05 < p0 < 0.30
    print(f"  P(edge<=0) = {p0:.1%} in (5%,30%) [{'ok' if c2 else 'FAIL'}]")
    # df=3 one-sided 5% quantile ~ Phase-0 LB (-8.2%), fat tails
    q05 = np.percentile(ms, 5)
    c3 = q05 < -0.05
    print(f"  posterior q05 {q05:+.1%} < -5% (LB unbounded below) [{'ok' if c3 else 'FAIL'}]")
    ok = c1 and c2 and c3
    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    if "--selftest" in sys.argv:
        selftest(); return
    o = run()
    o["forward_wait"] = forward_wait()
    _print(o)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "..", "reports", "stress", "phase3_posterior.json"), "w") as f:
        json.dump(o, f, indent=1, default=str)
    print("\nartifact -> reports/stress/phase3_posterior.json")


if __name__ == "__main__":
    main()
