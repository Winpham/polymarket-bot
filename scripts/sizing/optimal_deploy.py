#!/usr/bin/env python3
"""
BLENDED-MEDIAN-OPTIMAL DEPLOYMENT (honest + ruin-constrained).

Finds the daily deployment fraction that maximises the BLENDED median bankroll growth (weighting
the chance the edge is fake), subject to the hard constraint P(ruin) <= RUIN_CAP even if the edge
is fake. Swept over the belief P(edge real) because that belief is an input, not a fact.

Reuses the one-factor copula sim (portfolio_corr) and terminals() (cost_of_caution). Horizon = 250
trading days (the ongoing-policy year; ruin accrues over the year, so this is the conservative
horizon for a sizing rule). rho = 0.10 (mild within-day tail correlation for ONE favorite edge;
measured within-day ICC ~0.007 ordinary, bumped for tail/upset days).

Modes: run | --selftest
"""
import json, math, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "stress"))
import portfolio_corr as pc
import cost_of_caution as coc

HORIZON = 250
RHO = 0.10
TRIALS = 25000
RUIN_CAP = 0.05
DEPLOY_GRID = [0.03, 0.05, 0.08, 0.10, 0.13, 0.16, 0.20, 0.25, 0.30, 0.40]
P_REAL = [0.3, 0.4, 0.5, 0.6, 0.7]
SEED = 20260703


def grid_stats():
    """Precompute good/fake terminal arrays per deploy (heavy step, done once)."""
    good, gmin, null, nmin = {}, {}, {}, {}
    for dep in DEPLOY_GRID:
        good[dep], gmin[dep] = coc.terminals(pc.P_GOOD, RHO, dep, HORIZON, TRIALS, SEED)
        null[dep], nmin[dep] = coc.terminals(pc.P_NULL, RHO, dep, HORIZON, TRIALS, SEED + 1)
    return good, gmin, null, nmin


def solve(good, gmin, null, nmin):
    out = {"meta": {"horizon": HORIZON, "rho": RHO, "trials": TRIALS, "ruin_cap": RUIN_CAP,
                    "deploy_grid": DEPLOY_GRID, "p_real_grid": P_REAL,
                    "roi_bet_good": pc.P_GOOD*pc.G-(1-pc.P_GOOD)*pc.L,
                    "roi_bet_null": pc.P_NULL*pc.G-(1-pc.P_NULL)*pc.L},
           "by_belief": {}, "per_deploy_ruin_if_fake": {}}
    # ruin-if-fake is belief-independent
    for dep in DEPLOY_GRID:
        out["per_deploy_ruin_if_fake"][f"{dep}"] = float(np.mean(nmin[dep] <= coc.RUIN))
    rng = np.random.default_rng(SEED + 7)
    for pr in P_REAL:
        rows = []
        for dep in DEPLOY_GRID:
            is_real = rng.random(TRIALS) < pr
            term = np.where(is_real, good[dep], null[dep])
            minf = np.where(is_real, gmin[dep], nmin[dep])
            rows.append({"deploy": dep,
                         "blended_median": float(np.median(term) - 1),
                         "blended_mean": float(term.mean() - 1),
                         "p_ruin": float(np.mean(minf <= coc.RUIN)),
                         "ruin_if_fake": out["per_deploy_ruin_if_fake"][f"{dep}"]})
        # optimum = argmax blended_median subject to ruin-if-fake <= cap
        eligible = [r for r in rows if r["ruin_if_fake"] <= RUIN_CAP]
        best = max(eligible, key=lambda r: r["blended_median"]) if eligible else None
        out["by_belief"][f"{pr}"] = {"rows": rows,
                                     "optimal_deploy": best["deploy"] if best else 0.0,
                                     "optimal_median": best["blended_median"] if best else None}
    # ROBUST recommendation: optimal at 0.5 that is also ruin-safe at 0.3 (already guaranteed by
    # the ruin-if-fake cap, which is belief-independent). Report it explicitly.
    out["recommended_deploy"] = out["by_belief"]["0.5"]["optimal_deploy"]
    out["max_ruinsafe_deploy"] = max((d for d in DEPLOY_GRID
                                      if out["per_deploy_ruin_if_fake"][f"{d}"] <= RUIN_CAP),
                                     default=0.0)
    return out


def _print(o):
    print(f"OPTIMAL DEPLOYMENT — blended median, ruin-if-fake capped at {int(RUIN_CAP*100)}% "
          f"(horizon {HORIZON}d, rho {RHO})")
    print(f"good edge {o['meta']['roi_bet_good']:+.1%}/bet, fake {o['meta']['roi_bet_null']:+.1%}/bet\n")
    print("ruin-if-EDGE-FAKE by deployment (the hard constraint):")
    print("  " + "  ".join(f"{int(d*100)}%:{o['per_deploy_ruin_if_fake'][f'{d}']:.0%}" for d in DEPLOY_GRID))
    print(f"  -> max ruin-safe deployment = {int(o['max_ruinsafe_deploy']*100)}%/day\n")
    for pr in P_REAL:
        b = o["by_belief"][f"{pr}"]
        opt = b["optimal_deploy"]
        print(f"P(edge real)={pr}:  OPTIMAL = {int(opt*100)}%/day  (blended median "
              f"{b['optimal_median']:+.0%}/yr)" if b["optimal_median"] is not None else
              f"P(edge real)={pr}:  no ruin-safe deployment")
    print(f"\n>>> RECOMMENDED (optimal at P=0.5, ruin-safe at all beliefs): "
          f"{int(o['recommended_deploy']*100)}%/day <<<")


def selftest():
    # small-grid sanity: ruin-if-fake monotone increasing in deploy
    _, _, _, nmin = ({d: None for d in [0.05, 0.40]} for _ in range(4))
    _, n5 = coc.terminals(pc.P_NULL, RHO, 0.05, HORIZON, 4000, 1)
    _, n40 = coc.terminals(pc.P_NULL, RHO, 0.40, HORIZON, 4000, 1)
    r5, r40 = np.mean(n5 <= coc.RUIN), np.mean(n40 <= coc.RUIN)
    c1 = r40 > r5
    print(f"  ruin-if-fake: 40% {r40:.0%} > 5% {r5:.0%} [{'ok' if c1 else 'FAIL'}]")
    # optimum at low belief must be <= optimum at high belief (more faith -> deploy more)
    g = {d: coc.terminals(pc.P_GOOD, RHO, d, HORIZON, 4000, 1) for d in [0.05, 0.20]}
    n = {d: coc.terminals(pc.P_NULL, RHO, d, HORIZON, 4000, 2) for d in [0.05, 0.20]}
    def med(pr, d):
        rng = np.random.default_rng(3); m = rng.random(4000) < pr
        return np.median(np.where(m, g[d][0], n[d][0]))
    c2 = med(0.7, 0.20) >= med(0.3, 0.20)   # higher belief -> 20% looks better
    print(f"  belief monotonicity: median@P.7 {med(0.7,0.20)-1:+.0%} >= @P.3 {med(0.3,0.20)-1:+.0%} [{'ok' if c2 else 'FAIL'}]")
    ok = c1 and c2
    print("selftest:", "PASS" if ok else "FAIL"); sys.exit(0 if ok else 1)


def main():
    if "--selftest" in sys.argv:
        selftest(); return
    good, gmin, null, nmin = grid_stats()
    o = solve(good, gmin, null, nmin)
    _print(o)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                           "reports", "sizing", "optimal_deploy.json"), "w") as f:
        json.dump(o, f, indent=1, default=str)
    print("\nartifact -> reports/sizing/optimal_deploy.json")


if __name__ == "__main__":
    main()
