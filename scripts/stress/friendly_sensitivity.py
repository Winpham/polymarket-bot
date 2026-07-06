#!/usr/bin/env python3
"""
PHASE 4 CRUX — the H1 fairness check.

The composite/posterior use an adverse MEDIAN world (cohort~0.7, adv_sel~0.75). The obvious
rebuttal: "you only fail because you assumed a mean world." This script calls the SAME calibrated
simulator with a deliberately FRIENDLY world distribution — mild costs, high cohort & adverse-
selection persistence, rare shallow upsets, edge at the POINT estimate (mult=1, no posterior
downdraw) — and asks whether the pre-registered triggers STILL fire. If they do, the verdict is
STRUCTURAL (sizing + tiny-N), not an artifact of pessimistic world assumptions.

flat-SHARES (the risk-constitution policy). Modes: run | --selftest
"""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bad_life_mc as blm

SEED = 20260702
N = 6000


def draw_friendly(rng):
    return dict(
        hl_mo=(rng.choice([12, 1e9]) if rng.random() < 0.3 else 1e9),  # decay rare, slow
        hc_mult=rng.choice([1, 1, 2]),           # costs mostly as-modeled
        fill=rng.choice([0.0, 0.0, 0.01]),
        fee_mult=1,
        pi_upset=rng.uniform(0.03, 0.10),        # upsets rare
        upset_shock=rng.uniform(0.10, 0.20),     # and shallow
        drought_frac=rng.uniform(0.0, 0.15),
        miss=rng.uniform(0.0, 0.15),             # good capture
        adv_sel=rng.uniform(0.85, 1.0),          # little adverse selection
        cohort=rng.uniform(0.75, 1.0),           # cohort mostly persists
        fire_rate=rng.choice([3, 8]),
        decaying=False)


def run(n=N, seed=SEED, edge_mult=1.0):
    cal = blm.calibrate()
    rng = np.random.default_rng(seed)
    res = {B: {"pnl": [], "dd": [], "min": []} for B in blm.BANKROLLS}
    for _ in range(n):
        w = draw_friendly(rng)
        for B in blm.BANKROLLS:
            r = blm.simulate_world(cal, w, rng, B, kelly=False, edge_mult=edge_mult)
            res[B]["pnl"].append(r["pnl"]); res[B]["dd"].append(r["maxdd"]); res[B]["min"].append(r["minb_frac"])
    out = {"meta": {"seed": seed, "n": n, "policy": "flat_shares", "world": "FRIENDLY",
                    "edge_mult": edge_mult}, "by_bankroll": {}}
    for B in blm.BANKROLLS:
        pnl = np.array(res[B]["pnl"]); dd = np.array(res[B]["dd"]); mn = np.array(res[B]["min"])
        out["by_bankroll"][str(int(B))] = {
            "median_pnl": float(np.median(pnl)),
            "p_net_negative_12mo": float(np.mean(pnl < 0)),
            "p_maxdd_over_30pct": float(np.mean(dd > blm.DD_CEIL)),
            "p_ruin_20pct": float(np.mean(mn <= blm.RUIN_FRAC)),
            "p5_pnl": float(np.percentile(pnl, 5))}
    return out


def _print(o):
    print(f"FRIENDLY-WORLD sensitivity (flat-shares, edge_mult={o['meta']['edge_mult']}) — does it STILL fail?")
    print(f"  {'bankroll':>10}{'medP&L':>10}{'P(net<0)':>10}{'P(DD>30%)':>11}{'P(ruin)':>9}{'p5':>10}")
    for B, s in o["by_bankroll"].items():
        print(f"  {'$'+B:>10}{s['median_pnl']:>+10.0f}{s['p_net_negative_12mo']:>10.1%}"
              f"{s['p_maxdd_over_30pct']:>11.1%}{s['p_ruin_20pct']:>9.1%}{s['p5_pnl']:>+10.0f}")


def selftest():
    o = run(n=400)
    ok = all(0.0 <= o["by_bankroll"][b]["p_net_negative_12mo"] <= 1.0 for b in o["by_bankroll"])
    # friendly world should be BETTER than the full adverse composite's 85% at $5k
    better = o["by_bankroll"]["5000"]["p_net_negative_12mo"] < 0.85
    print(f"  friendly P(net<0)@5k = {o['by_bankroll']['5000']['p_net_negative_12mo']:.1%} < 0.85 [{'ok' if better else 'FAIL'}]")
    print("selftest:", "PASS" if (ok and better) else "FAIL"); sys.exit(0 if (ok and better) else 1)


def main():
    if "--selftest" in sys.argv:
        selftest(); return
    o = run()
    _print(o)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                           "reports", "stress", "friendly_sensitivity.json"), "w") as f:
        json.dump(o, f, indent=1, default=str)
    print("\nartifact -> reports/stress/friendly_sensitivity.json")


if __name__ == "__main__":
    main()
