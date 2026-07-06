#!/usr/bin/env python3
"""
FIXED-% OF BANKROLL sizing sweep — the coherent policy (no flat rate, no kink, no cap).

stake = f * current_bankroll on EVERY bet, same f for every band. This is the clean version of
what kelly_eighth tried to be (kelly's only sin was deriving a 7.5% fraction for the lucky band-5).
It auto-deleverages on losses and compounds on wins; because it is purely proportional, the RISK
FRACTIONS (ruin, drawdown, P(net<0)) are BANKROLL-INDEPENDENT — the fraction f IS the risk dial.
So we report per-f, not per-bankroll (verified scale-invariant in --selftest).

Swept over the three world models (same draws as the other deliverables):
  ADVERSE / POSTERIOR / FRIENDLY. Fractions f in {1%, 2%, 3%, 5%}.

Modes: run | --selftest
"""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bad_life_mc as blm
import phase3_posterior as p3
import friendly_sensitivity as fr

SEED = 20260702
N = 6000
FRACS = [0.01, 0.02, 0.03, 0.05]
REF_BANK = 10_000.0   # arbitrary; risk fractions are scale-invariant, only $ terminal scales


def draw(model, rng):
    if model == "adverse":
        return blm.draw_world(rng), 1.0
    if model == "posterior":
        return blm.draw_world(rng), p3.draw_edge_mult(rng)[0]
    if model == "friendly":
        return fr.draw_friendly(rng), 1.0
    raise ValueError(model)


def run(n=N, seed=SEED):
    cal = blm.calibrate()
    out = {"meta": {"seed": seed, "n": n, "fracs": FRACS, "ref_bank": REF_BANK,
                    "note": "fixed-% is scale-invariant: risk fractions identical at any bankroll"},
           "results": {}}
    for model in ("adverse", "posterior", "friendly"):
        out["results"][model] = {}
        for f in FRACS:
            rng = np.random.default_rng(seed)   # same draws across fractions
            pnl, dd, mn = [], [], []
            for _ in range(n):
                w, em = draw(model, rng)
                r = blm.simulate_world(cal, w, rng, REF_BANK, edge_mult=em, flat_frac=f)
                pnl.append(r["pnl"]); dd.append(r["maxdd"]); mn.append(r["minb_frac"])
            pnl = np.array(pnl); dd = np.array(dd); mn = np.array(mn)
            out["results"][model][f"{f:.2f}"] = {
                "median_pnl_pct": float(np.median(pnl) / REF_BANK),
                "p_net_negative": float(np.mean(pnl < 0)),
                "p_maxdd_over_30pct": float(np.mean(dd > blm.DD_CEIL)),
                "p_ruin_20pct": float(np.mean(mn <= blm.RUIN_FRAC)),
                "p5_pnl_pct": float(np.percentile(pnl, 5) / REF_BANK),
                "median_maxdd": float(np.median(dd))}
    return out


def _print(o):
    print("FIXED-% OF BANKROLL sizing (scale-invariant: same risk at any $ bankroll)")
    print("P&L shown as % of starting bankroll/yr.\n")
    for model in ("adverse", "posterior", "friendly"):
        print(f"=== {model.upper()} world ===")
        print(f"{'  bet %':>8}{'medP&L%':>9}{'p5 P&L%':>9}{'P(net<0)':>9}{'P(DD>30)':>9}{'medDD':>8}{'P(ruin)':>9}")
        for f in FRACS:
            s = o["results"][model][f"{f:.2f}"]
            print(f"{f:>7.0%}{s['median_pnl_pct']:>+9.1%}{s['p5_pnl_pct']:>+9.1%}"
                  f"{s['p_net_negative']:>9.1%}{s['p_maxdd_over_30pct']:>9.1%}"
                  f"{s['median_maxdd']:>8.1%}{s['p_ruin_20pct']:>9.1%}")
        print()


def selftest():
    cal = blm.calibrate()
    # scale-invariance: fixed-% risk fractions identical at $1k and $100k (same seed draws)
    def ruin_at(B):
        rng = np.random.default_rng(7)
        mn = [blm.simulate_world(cal, blm.draw_world(rng), rng, B, flat_frac=0.03)["minb_frac"]
              for _ in range(400)]
        return np.mean(np.array(mn) <= blm.RUIN_FRAC)
    r1k, r100k = ruin_at(1_000.0), ruin_at(100_000.0)
    c1 = abs(r1k - r100k) < 0.03
    print(f"  scale-invariance: ruin@$1k {r1k:.1%} ~= ruin@$100k {r100k:.1%} [{'ok' if c1 else 'FAIL'}]")
    # higher fraction -> more ruin (monotone risk dial)
    rng = np.random.default_rng(7)
    ws = [blm.draw_world(rng) for _ in range(400)]
    def ruin_f(f):
        rng2 = np.random.default_rng(9)
        return np.mean(np.array([blm.simulate_world(cal, w, rng2, 10_000.0, flat_frac=f)["minb_frac"]
                                 for w in ws]) <= blm.RUIN_FRAC)
    lo, hi = ruin_f(0.01), ruin_f(0.05)
    c2 = hi > lo
    print(f"  monotone: ruin@5% {hi:.1%} > ruin@1% {lo:.1%} [{'ok' if c2 else 'FAIL'}]")
    ok = c1 and c2
    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    if "--selftest" in sys.argv:
        selftest(); return
    o = run()
    _print(o)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                           "reports", "stress", "frac_sizing.json"), "w") as f:
        json.dump(o, f, indent=1, default=str)
    print("artifact -> reports/stress/frac_sizing.json")


if __name__ == "__main__":
    main()
