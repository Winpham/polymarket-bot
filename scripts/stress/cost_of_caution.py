#!/usr/bin/env python3
"""
COST OF CAUTION — how much profit do we miss/risk by deploying MODERATELY during the ~6-month
learning phase instead of going big now?

Two honest numbers, not one:
  (1) CONDITIONAL ON THE EDGE BEING REAL — the pure opportunity cost (what you 'gave up').
  (2) BLENDED over P(edge real) — the expected/median outcome, which weights the chance it's fake
      and the aggressive player gets wiped. This is what actually decides whether caution 'costs'.

Reuses the one-factor copula sim from portfolio_corr. Learning-phase horizon = 125 trading days
(~6 months). rho=0.2 (one correlated edge). Deploy grid {5,10,20,40}%/day.

Modes: run | --selftest
"""
import json, math, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import portfolio_corr as pc

HORIZON = 125            # ~6-month learning phase (trading days)
RHO = 0.20
DEPLOY = [0.05, 0.10, 0.20, 0.40]
TRIALS = 30000
P_REAL = [0.3, 0.5, 0.7]
SEED = 20260703
RUIN = 0.20


def terminals(p, rho, deploy, days, trials, seed):
    """Terminal bankroll multiplier array + min-fraction array (for ruin)."""
    rng = np.random.default_rng(seed)
    z_p = pc._ppf(p); sr, sr1 = math.sqrt(rho), math.sqrt(1 - rho)
    bank = np.ones(trials); minf = np.ones(trials)
    for _ in range(days):
        Z = rng.standard_normal((trials, 1)); eps = rng.standard_normal((trials, pc.N_BETS))
        Lz = sr * Z + sr1 * eps
        ret = np.where(Lz <= z_p, pc.G, -pc.L)
        bank *= np.clip(1.0 + deploy * ret.mean(axis=1), 0.0, None)
        minf = np.minimum(minf, bank)
    return bank, minf


def stats(term, minf):
    return {"median": float(np.median(term) - 1), "mean": float(term.mean() - 1),
            "p5": float(np.percentile(term, 5) - 1), "p95": float(np.percentile(term, 95) - 1),
            "p_ruin": float(np.mean(minf <= RUIN)), "p_net_neg": float(np.mean(term < 1))}


def run():
    out = {"meta": {"horizon_days": HORIZON, "rho": RHO, "deploy": DEPLOY, "trials": TRIALS,
                    "p_real_grid": P_REAL, "roi_bet_good": pc.P_GOOD*pc.G-(1-pc.P_GOOD)*pc.L,
                    "roi_bet_null": pc.P_NULL*pc.G-(1-pc.P_NULL)*pc.L},
           "conditional_real": {}, "conditional_fake": {}, "blended": {}}
    good, gmin, null, nmin = {}, {}, {}, {}
    for dep in DEPLOY:
        good[dep], gmin[dep] = terminals(pc.P_GOOD, RHO, dep, HORIZON, TRIALS, SEED)
        null[dep], nmin[dep] = terminals(pc.P_NULL, RHO, dep, HORIZON, TRIALS, SEED + 1)
        out["conditional_real"][f"{dep}"] = stats(good[dep], gmin[dep])
        out["conditional_fake"][f"{dep}"] = stats(null[dep], nmin[dep])
    for pr in P_REAL:
        out["blended"][f"{pr}"] = {}
        rng = np.random.default_rng(SEED + 99)
        for dep in DEPLOY:
            is_real = rng.random(TRIALS) < pr
            term = np.where(is_real, good[dep], null[dep])
            minf = np.where(is_real, gmin[dep], nmin[dep])
            out["blended"][f"{pr}"][f"{dep}"] = stats(term, minf)
    return out


def _pct(x):
    return f"{x:+.0%}" if abs(x) < 10 else f"{x:+.0f}x"


def _print(o):
    print(f"Learning phase = {HORIZON}d (~6mo), rho={RHO}, {pc.N_BETS} bets/day. Returns = bankroll growth over the phase.\n")
    print("=== (1) CONDITIONAL ON EDGE REAL — the opportunity cost of caution ===")
    print(f"{'deploy':>8}{'median':>10}{'p5':>9}{'p_ruin':>9}")
    for dep in DEPLOY:
        s = o["conditional_real"][f"{dep}"]
        print(f"{int(dep*100):>7}%{_pct(s['median']):>10}{_pct(s['p5']):>9}{s['p_ruin']:>9.0%}")
    print("\n=== (1b) CONDITIONAL ON EDGE FAKE — the loss you avoid by caution ===")
    print(f"{'deploy':>8}{'median':>10}{'p5':>9}{'p_ruin':>9}")
    for dep in DEPLOY:
        s = o["conditional_fake"][f"{dep}"]
        print(f"{int(dep*100):>7}%{_pct(s['median']):>10}{_pct(s['p5']):>9}{s['p_ruin']:>9.0%}")
    print("\n=== (2) BLENDED over P(edge real) — the honest expected outcome ===")
    for pr in P_REAL:
        print(f"  P(edge real)={pr}:")
        print(f"    {'deploy':>8}{'MEDIAN':>10}{'mean':>9}{'p_ruin':>9}{'p_net<0':>9}")
        for dep in DEPLOY:
            s = o["blended"][f"{pr}"][f"{dep}"]
            print(f"    {int(dep*100):>7}%{_pct(s['median']):>10}{_pct(s['mean']):>9}"
                  f"{s['p_ruin']:>9.0%}{s['p_net_neg']:>9.0%}")
        print()


def selftest():
    # more deploy -> more spread; good-world median rises with deploy
    g5, _ = terminals(pc.P_GOOD, RHO, 0.05, HORIZON, 4000, 1)
    g20, _ = terminals(pc.P_GOOD, RHO, 0.20, HORIZON, 4000, 1)
    c1 = np.median(g20) > np.median(g5)
    print(f"  good-world median rises with deploy: 20% {np.median(g20)-1:+.0%} > 5% {np.median(g5)-1:+.0%} [{'ok' if c1 else 'FAIL'}]")
    # fake-world ruin rises with deploy
    _, n5 = terminals(pc.P_NULL, RHO, 0.05, HORIZON, 4000, 2)
    _, n40 = terminals(pc.P_NULL, RHO, 0.40, HORIZON, 4000, 2)
    r5 = np.mean(n5 <= RUIN); r40 = np.mean(n40 <= RUIN)
    c2 = r40 > r5
    print(f"  fake-world ruin rises with deploy: 40% {r40:.0%} > 5% {r5:.0%} [{'ok' if c2 else 'FAIL'}]")
    ok = c1 and c2
    print("selftest:", "PASS" if ok else "FAIL"); sys.exit(0 if ok else 1)


def main():
    if "--selftest" in sys.argv:
        selftest(); return
    o = run()
    _print(o)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                           "reports", "stress", "cost_of_caution.json"), "w") as f:
        json.dump(o, f, indent=1, default=str)
    print("artifact -> reports/stress/cost_of_caution.json")


if __name__ == "__main__":
    main()
