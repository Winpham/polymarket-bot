#!/usr/bin/env python3
"""
GUARDRAIL RE-RUN — ruin numbers under FLAT-$100 + 2%-of-bankroll per-bet CAP.

The stress test's ruin came from sizing (⅛-Kelly stakes ~7.5%/bet on the lucky band-5) and from
flat $100 on a small bankroll (10% of $1k per bet). The recommended guardrail is:
  stake = min($100, 0.02 * bankroll)
i.e. flat $100 while the bankroll is >= $5k, else auto-deleveraged to 2% of it (a $1k bank bets
$20, not $100). This script re-runs the SAME calibrated worlds through that capped policy and puts
it beside the original ⅛-Kelly and uncapped-flat numbers so the improvement is visible.

Three world models (identical draws to the earlier deliverables):
  ADVERSE   = draw_world (composite realistic-bad), edge at point
  POSTERIOR = draw_world + edge drawn from the fat-tailed df=3 posterior (edge might be ~0)
  FRIENDLY  = draw_friendly (mild everything), edge at point

Modes: run | --selftest
"""
import json, os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bad_life_mc as blm
import phase3_posterior as p3
import friendly_sensitivity as fr

SEED = 20260702
N = 4000
CAP = 0.02
POLICIES = {
    "kelly_eighth":   dict(kelly=True,  cap_frac=None),   # original recommended
    "flat_uncapped":  dict(kelly=False, cap_frac=None),   # flat $100, no cap
    "flat_2pct_cap":  dict(kelly=False, cap_frac=CAP),    # THE GUARDRAIL
}


def draw(model, rng):
    """Return (world, edge_mult) for a model."""
    if model == "adverse":
        return blm.draw_world(rng), 1.0
    if model == "posterior":
        return blm.draw_world(rng), p3.draw_edge_mult(rng)[0]
    if model == "friendly":
        return fr.draw_friendly(rng), 1.0
    raise ValueError(model)


def run(n=N, seed=SEED):
    cal = blm.calibrate()
    out = {"meta": {"seed": seed, "n": n, "cap_frac": CAP, "bankrolls": blm.BANKROLLS,
                    "stake": blm.STAKE}, "results": {}}
    for model in ("adverse", "posterior", "friendly"):
        out["results"][model] = {}
        for pol, kw in POLICIES.items():
            rng = np.random.default_rng(seed)   # SAME draws across policies -> apples-to-apples
            acc = {B: {"pnl": [], "dd": [], "min": []} for B in blm.BANKROLLS}
            for _ in range(n):
                w, em = draw(model, rng)
                for B in blm.BANKROLLS:
                    r = blm.simulate_world(cal, w, rng, B, edge_mult=em, **kw)
                    acc[B]["pnl"].append(r["pnl"]); acc[B]["dd"].append(r["maxdd"])
                    acc[B]["min"].append(r["minb_frac"])
            out["results"][model][pol] = {}
            for B in blm.BANKROLLS:
                pnl = np.array(acc[B]["pnl"]); dd = np.array(acc[B]["dd"]); mn = np.array(acc[B]["min"])
                out["results"][model][pol][str(int(B))] = {
                    "median_pnl": float(np.median(pnl)),
                    "p_net_negative": float(np.mean(pnl < 0)),
                    "p_maxdd_over_30pct": float(np.mean(dd > blm.DD_CEIL)),
                    "p_ruin_20pct": float(np.mean(mn <= blm.RUIN_FRAC)),
                    "p5_pnl": float(np.percentile(pnl, 5))}
    return out


def _print(o):
    for model in ("adverse", "posterior", "friendly"):
        print(f"\n=== {model.upper()} world ===")
        print(f"{'policy':>16}{'bank':>8}{'medP&L':>9}{'P(net<0)':>9}{'P(DD>30)':>9}{'P(ruin)':>9}{'p5':>9}")
        for pol in POLICIES:
            for B in ("1000", "5000", "25000"):
                s = o["results"][model][pol][B]
                star = "  <=GUARDRAIL" if pol == "flat_2pct_cap" and B in ("5000", "25000") else ""
                print(f"{pol:>16}{'$'+B:>8}{s['median_pnl']:>+9.0f}{s['p_net_negative']:>9.1%}"
                      f"{s['p_maxdd_over_30pct']:>9.1%}{s['p_ruin_20pct']:>9.1%}{s['p5_pnl']:>+9.0f}{star}")


def selftest():
    cal = blm.calibrate()
    rng = np.random.default_rng(SEED)
    w = blm.draw_world(rng)
    # cap must bind at $1k (2% = $20 < $100) -> smaller stakes -> LESS ruin than uncapped flat
    ru_cap, ru_unc = [], []
    for _ in range(300):
        ww = blm.draw_world(rng)
        ru_cap.append(blm.simulate_world(cal, ww, rng, 1000.0, kelly=False, cap_frac=CAP)["minb_frac"])
        ru_unc.append(blm.simulate_world(cal, ww, rng, 1000.0, kelly=False, cap_frac=None)["minb_frac"])
    p_cap = np.mean(np.array(ru_cap) <= blm.RUIN_FRAC)
    p_unc = np.mean(np.array(ru_unc) <= blm.RUIN_FRAC)
    c1 = p_cap < p_unc
    print(f"  $1k ruin: capped {p_cap:.1%} < uncapped {p_unc:.1%} [{'ok' if c1 else 'FAIL'}]")
    # at $25k the cap (2%=$500>$100) NEVER binds -> identical to uncapped flat
    a = blm.simulate_world(cal, w, np.random.default_rng(1), 25000.0, kelly=False, cap_frac=CAP)["pnl"]
    b = blm.simulate_world(cal, w, np.random.default_rng(1), 25000.0, kelly=False, cap_frac=None)["pnl"]
    c2 = abs(a - b) < 1e-6
    print(f"  $25k capped==uncapped (cap never binds): {c2} [{'ok' if c2 else 'FAIL'}]")
    ok = c1 and c2
    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    if "--selftest" in sys.argv:
        selftest(); return
    o = run()
    _print(o)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                           "reports", "stress", "guardrail_ruin.json"), "w") as f:
        json.dump(o, f, indent=1, default=str)
    print("\nartifact -> reports/stress/guardrail_ruin.json")


if __name__ == "__main__":
    main()
