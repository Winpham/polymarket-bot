#!/usr/bin/env python3
"""
PORTFOLIO SIZING vs CORRELATION — "can we diversify across markets/lines to get the edge without
ruin or correlated loss?"

The whole dream lives or dies on ONE number: the correlation between your simultaneous bets. This
one-factor Gaussian-copula simulator makes correlation rho the dial and sweeps how much of the
bankroll you can safely deploy per day. It answers, quantitatively:
  - if your lines are UNCORRELATED (different edges/markets that fail at different times) you can
    deploy a lot, compound hard, and ruin stays ~0  -> the goal, achievable.
  - if they're really ONE edge wearing many tickets (high tail rho) more deployment just buys ruin.

Model: N simultaneous bets/day, each staked f = D/N of START-OF-DAY bankroll (D = total daily
deployment). Each bet wins w.p. p; outcomes share a daily common factor giving pairwise
correlation rho (one-factor copula: L_i = sqrt(rho)*Z_day + sqrt(1-rho)*eps_i, win iff L_i<=z_p).
Priced at c=0.85 (heavy-favorite band), fee included. GOOD-edge world p=0.90 (~+3.9% ROI/bet);
NO-edge world p=0.85 (costs -> -2%/bet). 250 trading days, fully vectorized over trials.

Modes: run | --selftest
"""
import json, math, os, sys
import numpy as np

C = 0.85                      # entry price (heavy-favorite band)
FEE = 0.02
G = 1.0 / C - 1.0 - FEE       # gross return on a WIN (per $ staked)
L = 1.0 + FEE                 # loss on a LOSS (per $ staked)
P_GOOD, P_NULL = 0.90, 0.85   # true win prob: real +edge vs no-edge (fair price)
N_BETS = 10                   # simultaneous markets/lines per day
DAYS = 250
TRIALS = 20000
RUIN = 0.20
DD_CEIL = 0.30
SEED = 20260703
RHOS = [0.0, 0.05, 0.20, 0.50]
DEPLOY = [0.05, 0.10, 0.20, 0.40]   # total fraction of bankroll deployed per day


def _ppf(p):
    """Acklam inverse-normal (enough precision for thresholds)."""
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    cc = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
          -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    pl = 0.02425
    if p < pl:
        q = math.sqrt(-2 * math.log(p))
        return (((((cc[0]*q+cc[1])*q+cc[2])*q+cc[3])*q+cc[4])*q+cc[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p <= 1 - pl:
        q = p - 0.5; r = q*q
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    q = math.sqrt(-2 * math.log(1 - p))
    return -(((((cc[0]*q+cc[1])*q+cc[2])*q+cc[3])*q+cc[4])*q+cc[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)


def simulate(p, rho, deploy, trials=TRIALS, days=DAYS, n=N_BETS, seed=SEED):
    """Return dict of outcome stats over `trials` one-year paths."""
    rng = np.random.default_rng(seed)
    z_p = _ppf(p)
    sr, sr1 = math.sqrt(rho), math.sqrt(1.0 - rho)
    bank = np.ones(trials)
    peak = np.ones(trials)
    maxdd = np.zeros(trials)
    minfrac = np.ones(trials)
    for _ in range(days):
        Z = rng.standard_normal((trials, 1))
        eps = rng.standard_normal((trials, n))
        Lz = sr * Z + sr1 * eps
        win = Lz <= z_p
        ret = np.where(win, G, -L)               # (trials, n)
        day_mult = 1.0 + deploy * ret.mean(axis=1)   # stake f=deploy/n each -> deploy*mean(ret)
        day_mult = np.clip(day_mult, 0.0, None)
        bank *= day_mult
        peak = np.maximum(peak, bank)
        dd = np.where(peak > 0, (peak - bank) / peak, 0.0)
        maxdd = np.maximum(maxdd, dd)
        minfrac = np.minimum(minfrac, bank)
    return {
        "median_return": float(np.median(bank) - 1.0),
        "p5_return": float(np.percentile(bank, 5) - 1.0),
        "p_ruin": float(np.mean(minfrac <= RUIN)),
        "p_maxdd_over_30": float(np.mean(maxdd > DD_CEIL)),
        "p_net_negative": float(np.mean(bank < 1.0))}


def run():
    out = {"meta": {"c": C, "fee": FEE, "p_good": P_GOOD, "p_null": P_NULL, "n_bets": N_BETS,
                    "days": DAYS, "trials": TRIALS, "rhos": RHOS, "deploy": DEPLOY,
                    "roi_per_bet_good": P_GOOD*G - (1-P_GOOD)*L,
                    "roi_per_bet_null": P_NULL*G - (1-P_NULL)*L}, "good": {}, "null": {}}
    for world, p in (("good", P_GOOD), ("null", P_NULL)):
        for rho in RHOS:
            for dep in DEPLOY:
                out[world][f"rho{rho}_dep{dep}"] = simulate(p, rho, dep)
    return out


def _print(o):
    print(f"ROI/bet: good {o['meta']['roi_per_bet_good']:+.1%}, null {o['meta']['roi_per_bet_null']:+.1%}"
          f"  ({N_BETS} bets/day, priced {C}, {DAYS}d)\n")
    for world in ("good", "null"):
        tag = "GOOD edge (+3.9%/bet)" if world == "good" else "NO edge (-2%/bet)"
        print(f"===== {tag} =====")
        print(f"{'corr rho':>9} | " + " ".join(f"deploy {int(d*100):>2}%/day" for d in DEPLOY))
        for rho in RHOS:
            cells = []
            for dep in DEPLOY:
                s = o[world][f"rho{rho}_dep{dep}"]
                if world == "good":
                    cells.append(f"{s['median_return']:>+6.0%} r{s['p_ruin']:>4.0%}")
                else:
                    cells.append(f"{s['median_return']:>+6.0%} r{s['p_ruin']:>4.0%}")
            print(f"{rho:>9.2f} | " + "   ".join(cells))
        print("  (each cell: median 1-yr return  r=P(ruin))\n")


def selftest():
    ok = True
    # copula induces the target win prob and correlation
    rng = np.random.default_rng(1)
    z_p = _ppf(0.90)
    Z = rng.standard_normal((40000, 1)); eps = rng.standard_normal((40000, 2))
    rho = 0.5
    Lz = math.sqrt(rho)*Z + math.sqrt(1-rho)*eps
    win = Lz <= z_p
    p_emp = win.mean()
    c1 = abs(p_emp - 0.90) < 0.01
    print(f"  copula win-rate {p_emp:.3f} ~= 0.90 [{'ok' if c1 else 'FAIL'}]")
    corr_emp = np.corrcoef(win[:, 0].astype(float), win[:, 1].astype(float))[0, 1]
    c2 = corr_emp > 0.15                      # positive, materially correlated at rho=0.5
    print(f"  induced outcome corr {corr_emp:.2f} > 0.15 at rho=0.5 [{'ok' if c2 else 'FAIL'}]")
    # monotonicity: at fixed deploy, higher rho -> higher ruin (good world)
    lo = simulate(P_GOOD, 0.0, 0.20, trials=4000)["p_ruin"]
    hi = simulate(P_GOOD, 0.50, 0.20, trials=4000)["p_ruin"]
    c3 = hi >= lo
    print(f"  ruin rises with corr: rho0.5 {hi:.1%} >= rho0 {lo:.1%} [{'ok' if c3 else 'FAIL'}]")
    # null world loses money even uncorrelated
    c4 = simulate(P_NULL, 0.0, 0.10, trials=4000)["p_net_negative"] > 0.6
    print(f"  no-edge world loses even at rho=0 [{'ok' if c4 else 'FAIL'}]")
    ok = c1 and c2 and c3 and c4
    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    if "--selftest" in sys.argv:
        selftest(); return
    o = run()
    _print(o)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                           "reports", "stress", "portfolio_corr.json"), "w") as f:
        json.dump(o, f, indent=1, default=str)
    print("artifact -> reports/stress/portfolio_corr.json")


if __name__ == "__main__":
    main()
