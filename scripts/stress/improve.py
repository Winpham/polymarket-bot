#!/usr/bin/env python3
"""
CAN THE EDGE BE MADE BETTER? Test sizing + composition fixes at the BINDING stress (a CLEAN
world where the true edge is HALF the measured +12.5% — the honest-CI case that breaks the
current policy: ⅛-Kelly there hits DD>30% in ~44% of years). Reuses bad_life_mc verbatim.
No new modelling; just swap the policy/composition and re-measure.
"""
import copy
import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bad_life_mc as blm

SEED = 20260702
B = 5_000.0
N = 3000
CLEAN = dict(hl_mo=1e9, hc_mult=1, fill=0.0, fee_mult=1, pi_upset=0.0, upset_shock=0.2,
             drought_frac=0.0, miss=0.0, adv_sel=1.0, cohort=1.0, fire_rate=8, decaying=False)
EDGE = 0.5   # half the measured edge — the binding, plausible case


def band4_only(cal):
    """Composition fix: drop the marginal band-5, keep only the robust band-4 favorites."""
    c = copy.deepcopy(cal)
    b4 = cal["bands"][4]
    c["bands"] = {4: b4}
    c["band_keys"] = [4]
    return c


def stats(cal, rng, kelly, kmult=None, flat_frac=None):
    old = blm.KELLY_MULT
    if kmult is not None:
        blm.KELLY_MULT = kmult
    pnl, dd, mn = [], [], []
    for _ in range(N):
        r = blm.simulate_world(cal, CLEAN, rng, B, kelly=kelly, edge_mult=EDGE,
                               **({"flat_frac": flat_frac} if flat_frac else {}))
        pnl.append(r["pnl"]); dd.append(r["maxdd"]); mn.append(r["minb_frac"])
    blm.KELLY_MULT = old
    pnl, dd, mn = map(np.array, (pnl, dd, mn))
    return dict(med=float(np.median(pnl)), p_neg=float(np.mean(pnl < 0)),
                p_dd=float(np.mean(dd > blm.DD_CEIL)), p_ruin=float(np.mean(mn <= blm.RUIN_FRAC)),
                p5=float(np.percentile(pnl, 5)))


def main():
    cal = blm.calibrate()
    c4 = band4_only(cal)
    rng = np.random.default_rng(SEED)
    print(f"Binding stress: CLEAN world, TRUE edge = 50% of measured (+~6%), B=$5k, {N} worlds")
    print(f"{'policy':>34}{'med P&L':>10}{'P(net<0)':>10}{'P(DD>30%)':>11}{'P(ruin)':>9}{'p5':>9}")
    rows = [
        ("CURRENT ⅛-Kelly, both bands", cal, True, 0.125, None),
        ("1/16-Kelly, both bands", cal, True, 0.0625, None),
        ("flat-2%-of-bank, both bands", cal, False, None, 0.02),
        ("flat-shares $100, both bands", cal, False, None, None),
        ("⅛-Kelly, BAND-4 ONLY", c4, True, 0.125, None),
        ("flat-2%-of-bank, BAND-4 ONLY", c4, False, None, 0.02),
    ]
    for name, cc, k, km, ff in rows:
        try:
            s = stats(cc, np.random.default_rng(SEED), k, km, ff)
        except TypeError:
            # flat_frac not supported in this bad_life_mc build -> approximate flat-% via kelly
            s = stats(cc, np.random.default_rng(SEED), k, km, None)
            name += " (approx)"
        print(f"{name:>34}{s['med']:>+10.0f}{s['p_neg']:>10.1%}{s['p_dd']:>11.1%}"
              f"{s['p_ruin']:>9.1%}{s['p5']:>+9.0f}")
    print("\nceiling to beat: P(DD>30%) <= 10%  (the repo's own DD_CEIL_P)")


if __name__ == "__main__":
    main()
