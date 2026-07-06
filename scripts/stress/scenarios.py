#!/usr/bin/env python3
"""
F1 (thin-edge variance) + PHASE 3 (tiny-N honesty) scenarios, built on bad_life_mc.simulate_world.

F1: a CLEAN world (no decay/upset/cost/miss) with the base edge scaled by edge_mult -> how much
    of the outcome is pure variance even when the edge is real but small (+3%)?
PHASE 3: the composite MC re-run with the base edge drawn per-world from favorite's ACTUAL wide
    posterior (not the point estimate), because every parameter is fit on ~4 days / G=4 clusters.
    Two posteriors: OPTIMISTIC (cluster-robust gate-z, se/point~0.26) and HONEST (small-cluster
    t, df=3, 5th-pct ~ the -8% LB). Shows what fraction of "it works" is assumed, not supported.

Modes:
  ./scenarios.py            # -> reports/stress/scenarios.json
  ./scenarios.py --selftest # edge_mult monotone in P&L; negative posterior mass raises P(net<0)
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bad_life_mc as blm

SEED = 20260702
B = 5_000.0
N = 2000
CLEAN = dict(hl_mo=1e9, hc_mult=1, fill=0.0, fee_mult=1, pi_upset=0.0, upset_shock=0.2,
             drought_frac=0.0, miss=0.0, adv_sel=1.0, cohort=1.0, fire_rate=8, decaying=False)


def clean_edge_sweep(cal, rng):
    """F1: clean world, edge scaled. edge_mult 0.25 ~ +3% true edge."""
    out = {}
    for em in [1.0, 0.5, 0.25]:
        pnl, dd, mn = [], [], []
        for _ in range(N):
            r = blm.simulate_world(cal, CLEAN, rng, B, kelly=True, edge_mult=em)
            pnl.append(r["pnl"]); dd.append(r["maxdd"]); mn.append(r["minb_frac"])
        pnl, dd, mn = map(np.array, (pnl, dd, mn))
        # measure the realized per-$ edge in a no-cost single-bet sense for labelling
        out[f"edge_mult_{em}"] = {
            "median_pnl": float(np.median(pnl)),
            "p_net_negative_12mo": float(np.mean(pnl < 0)),
            "p_maxdd_over_30pct": float(np.mean(dd > blm.DD_CEIL)),
            "p_ruin": float(np.mean(mn <= blm.RUIN_FRAC)),
            "p5_pnl": float(np.percentile(pnl, 5))}
    return out


def posterior_composite(cal, rng, sigma, label, n=N):
    """Phase 3: full composite draws PLUS a per-world base-edge multiplier ~ N(1, sigma),
    clipped at [-1, 3] (edge can be zero or negative — the tiny-N reality)."""
    pnl, dd, mn, neg_edge = [], [], [], 0
    for _ in range(n):
        w = blm.draw_world(rng)
        em = float(np.clip(rng.normal(1.0, sigma), -1.0, 3.0))
        if em <= 0:
            neg_edge += 1
        r = blm.simulate_world(cal, w, rng, B, kelly=True, edge_mult=em)
        pnl.append(r["pnl"]); dd.append(r["maxdd"]); mn.append(r["minb_frac"])
    pnl, dd, mn = map(np.array, (pnl, dd, mn))
    return {"label": label, "sigma": sigma,
            "frac_worlds_edge_nonpositive": neg_edge / n,
            "median_pnl": float(np.median(pnl)),
            "p_net_negative_12mo": float(np.mean(pnl < 0)),
            "p_maxdd_over_30pct": float(np.mean(dd > blm.DD_CEIL)),
            "p_ruin": float(np.mean(mn <= blm.RUIN_FRAC)),
            "p5_pnl": float(np.percentile(pnl, 5)),
            "worst_decile_terminal": float(np.percentile(pnl, 10) + B)}


def _stats(cal, w, rng, n, kelly=True):
    pnl, dd, mn = [], [], []
    for _ in range(n):
        r = blm.simulate_world(cal, w, rng, B, kelly=kelly)
        pnl.append(r["pnl"]); dd.append(r["maxdd"]); mn.append(r["minb_frac"])
    pnl, dd, mn = map(np.array, (pnl, dd, mn))
    return {"median_pnl": float(np.median(pnl)), "p_net_negative": float(np.mean(pnl < 0)),
            "p_maxdd_over_30pct": float(np.mean(dd > blm.DD_CEIL)),
            "p_ruin": float(np.mean(mn <= blm.RUIN_FRAC)), "p5_pnl": float(np.percentile(pnl, 5))}


def decompose(cal, rng, n=N):
    """Attribute P(net<0) to each failure factor in isolation (each = CLEAN + one factor at its
    typical/mean level), then the typical-all and kelly-vs-flat comparison."""
    typ = {
        "clean": CLEAN,
        "cost_typical(2x hc,1c)": dict(CLEAN, hc_mult=2, fill=0.01),
        "cohort_0.7": dict(CLEAN, cohort=0.7),
        "adv_sel_0.75": dict(CLEAN, adv_sel=0.75),
        "decay_6mo": dict(CLEAN, hl_mo=6, decaying=True),
        "upset_0.125x0.225": dict(CLEAN, pi_upset=0.125, upset_shock=0.225),
        "miss_0.2": dict(CLEAN, miss=0.2),
        "drought_0.2": dict(CLEAN, drought_frac=0.2),
        "ALL_typical": dict(hl_mo=6, hc_mult=2, fill=0.01, fee_mult=1, pi_upset=0.125,
                            upset_shock=0.225, drought_frac=0.2, miss=0.2, adv_sel=0.75,
                            cohort=0.7, fire_rate=8, decaying=True)}
    out = {k: _stats(cal, w, rng, n) for k, w in typ.items()}
    # kelly vs flat under ALL_typical
    out["ALL_typical_FLAT_shares"] = _stats(cal, typ["ALL_typical"], rng, n, kelly=False)
    return out


def run():
    cal = blm.calibrate()
    rng = np.random.default_rng(SEED)
    result = {"meta": {"seed": SEED, "bankroll": B, "n": N,
                       "note": "F1 clean-edge variance + factor decomposition + Phase-3 posterior"}}
    result["factor_decomposition"] = decompose(cal, rng)
    result["F1_clean_edge_sweep"] = clean_edge_sweep(cal, rng)
    # Phase 3 posteriors: point-estimate surplus +12.5%; se_CR_day 0.032 (gate-z, optimistic);
    # honest small-cluster df=3 CI 5th-pct ~ -8% -> sigma ~ (1 - (-8/12.5))/1.645 ~ 1.0.
    result["Phase3_posterior"] = {
        "point_estimate_baseline": posterior_composite(cal, rng, 1e-6, "point (sigma~0)"),
        "optimistic_gate_z": posterior_composite(cal, rng, 0.26, "cluster-robust gate-z se/point"),
        "honest_small_cluster": posterior_composite(cal, rng, 1.00, "small-cluster t df=3 (LB -8%)")}
    return result


def _print(r):
    print("FACTOR DECOMPOSITION (each factor alone at typical level; kelly_eighth_capped, B=$5k)")
    print(f"{'factor':>28}{'med P&L':>10}{'P(net<0)':>10}{'P(DD>30%)':>11}{'P(ruin)':>9}")
    for k, s in r["factor_decomposition"].items():
        print(f"{k:>28}{s['median_pnl']:>+10.0f}{s['p_net_negative']:>10.1%}"
              f"{s['p_maxdd_over_30pct']:>11.1%}{s['p_ruin']:>9.1%}")
    print()
    print("F1 — CLEAN-WORLD edge sweep (no decay/upset/cost; pure variance), B=$5k")
    print(f"{'edge_mult':>12}{'med P&L':>10}{'P(net<0)':>10}{'P(DD>30%)':>11}{'P(ruin)':>9}{'p5 P&L':>10}")
    for k, s in r["F1_clean_edge_sweep"].items():
        em = k.split("_")[-1]
        print(f"{em:>12}{s['median_pnl']:>+10.0f}{s['p_net_negative_12mo']:>10.1%}"
              f"{s['p_maxdd_over_30pct']:>11.1%}{s['p_ruin']:>9.1%}{s['p5_pnl']:>+10.0f}")
    print("  (edge_mult 0.25 ~ the honest +3% LB edge; 1.0 = measured +12.5% point)")
    print("\nPHASE 3 — composite with base edge drawn from favorite's posterior (tiny-N honesty)")
    print(f"{'posterior':>34}{'edge<=0 frac':>13}{'med P&L':>10}{'P(net<0)':>10}"
          f"{'P(DD>30%)':>11}{'P(ruin)':>9}")
    for k, s in r["Phase3_posterior"].items():
        print(f"{s['label']:>34}{s['frac_worlds_edge_nonpositive']:>13.1%}"
              f"{s['median_pnl']:>+10.0f}{s['p_net_negative_12mo']:>10.1%}"
              f"{s['p_maxdd_over_30pct']:>11.1%}{s['p_ruin']:>9.1%}")


def selftest():
    ok = True
    cal = blm.calibrate()
    rng = np.random.default_rng(SEED)
    # monotone: more edge -> more P&L in a clean world
    ms = [np.median([blm.simulate_world(cal, CLEAN, rng, B, kelly=True, edge_mult=em)["pnl"]
                     for _ in range(150)]) for em in (0.25, 0.5, 1.0)]
    mono = ms[0] < ms[1] < ms[2]
    print(f"  clean P&L monotone in edge: {[f'{x:+.0f}' for x in ms]} [{'ok' if mono else 'FAIL'}]")
    ok = ok and mono
    # mechanical: wider posterior sigma puts MORE mass on non-positive edge (the tiny-N reality)
    pt = posterior_composite(cal, rng, 1e-6, "pt", n=600)
    hon = posterior_composite(cal, rng, 1.0, "hon", n=600)
    more_neg = hon["frac_worlds_edge_nonpositive"] > pt["frac_worlds_edge_nonpositive"]
    print(f"  honest posterior edge<=0 frac {hon['frac_worlds_edge_nonpositive']:.1%} > point "
          f"{pt['frac_worlds_edge_nonpositive']:.1%} [{'ok' if more_neg else 'FAIL'}]")
    ok = ok and more_neg
    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    r = run()
    _print(r)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "..", "reports", "stress", "scenarios.json"), "w") as f:
        json.dump(r, f, indent=1, default=str)
    print("\nartifact -> reports/stress/scenarios.json")


if __name__ == "__main__":
    main()
