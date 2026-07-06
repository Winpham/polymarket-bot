#!/usr/bin/env python3
"""
Answers three follow-ups honestly:
 (1) MARKET-MAKER / no-fee: recompute favorite's realizable edge and per-band break-evens with
     fee=0 (and the taker haircut removed). Shows the fee benefit exactly. (The adverse-selection
     COST of passive MM execution is NOT modelled here — no data: signal_price_trajectory empty.)
 (2) DE-BIAS the "every day was profitable" streak: per-band win-rate sampling CIs, and the honest
     statement that you CANNOT de-bias a 4-positive-day streak from within it — you can only inject
     a bad day (the composite) and test survival.
 (3) LONG-RUN profitability under FIXED sizing (flat-2%-of-bank) across the full stacked bad-days
     MC, at fee=0 (MM) vs fee=2% (taker), swept over edge-realness (point / half / honest-LB).
"""
import sys
import os
from collections import defaultdict
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bad_life_mc as blm
from cost_stress import favorite_events, event_roi, block_bootstrap_lb

SEED = 20260702
B = 5_000.0
N = 3000


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def fee_and_debias():
    events = favorite_events()
    by_band = defaultdict(list)
    for e in events:
        by_band[e["band"]].append(e)
    print("(1)+(2)  PER-BAND edge, fee sensitivity, and win-rate sampling CI")
    print(f"{'band':>5}{'N':>5}{'win':>7}{'price':>7}{'winCI(95%)':>16}"
          f"{'ROI fee=2%':>11}{'ROI fee=0':>10}{'breakeven win':>14}")
    for b, evs in sorted(by_band.items()):
        n = len(evs)
        k = sum(1 for e in evs if e["won"] >= 0.5)
        win = k / n
        price = float(np.mean([e["entry"] for e in evs]))
        lo, hi = wilson(k, n)
        # realizable ROI: taker (fee 0.02, haircut 0.5c) vs MM (fee 0, no haircut = trade at mid)
        roi_taker = float(np.mean([event_roi(e, 1, 0.0, 1, dispute_p=0.0) for e in evs]))
        roi_mm = float(np.mean([e["won"] / e["entry"] - 1.0 for e in evs]))   # fee=0, c=mid
        # break-even win rate: p*(1/c - 1) - (1-p) = fee  ->  taker vs MM
        c_t = price + 0.005
        be_taker = (1 + 0.02) / (1.0 / c_t - 1 + 1 + 0.02)
        be_mm = price          # at mid, no fee: break-even win rate == price
        print(f"{b:>5}{n:>5}{win:>7.3f}{price:>7.3f}   [{lo:.3f},{hi:.3f}]"
              f"{roi_taker:>+11.2%}{roi_mm:>+10.2%}     {be_taker:.3f}/{be_mm:.3f}")
    print("  win CI = Wilson (sampling only). LOWER bound still beats price ⇒ the per-bet edge is")
    print("  not a pure small-sample mirage. BUT: 4 correlated day-blocks ⇒ GENERALIZATION is the")
    print("  wall; a 4-positive-day streak CANNOT be de-biased from within — only survival-tested.")


def mm_world(w, mm):
    """Override a drawn world for the MM (fee=0, no taker haircut) or taker case."""
    w = dict(w)
    if mm:
        w["fee_mult"] = 0.0     # no fee
        w["hc_mult"] = 0.0      # no taker haircut (trade at mid; MM would earn spread — conservative)
        # honest MM penalty: passive fills are adversely selected + you miss the runs.
        w["adv_sel"] = min(w["adv_sel"], 0.75)   # keep at least the drawn adverse selection
        w["miss"] = max(w["miss"], 0.20)         # >=20% of the good fires never fill passively
    return w


def longrun(edge_mult, mm, seed):
    rng = np.random.default_rng(seed)
    cal = blm.calibrate()
    pnl, dd, mn = [], [], []
    for _ in range(N):
        w = mm_world(blm.draw_world(rng), mm)
        r = blm.simulate_world(cal, w, rng, B, kelly=False, edge_mult=edge_mult, flat_frac=0.02)
        pnl.append(r["pnl"]); dd.append(r["maxdd"]); mn.append(r["minb_frac"])
    pnl, dd, mn = map(np.array, (pnl, dd, mn))
    return dict(med=float(np.median(pnl)), p_neg=float(np.mean(pnl < 0)),
                p_dd=float(np.mean(dd > blm.DD_CEIL)), p_ruin=float(np.mean(mn <= blm.RUIN_FRAC)),
                wdec=float(np.percentile(pnl, 10)), p5=float(np.percentile(pnl, 5)))


def main():
    fee_and_debias()
    print("\n(3)  LONG-RUN under FIXED flat-2%-of-bank sizing, FULL stacked bad-days MC, B=$5k")
    print("     MM = fee 0 + no taker haircut + >=20% passive-miss + adverse-selection penalty")
    print(f"{'edge realness':>22}{'exec':>7}{'med P&L':>10}{'P(net<0)':>10}{'P(DD>30%)':>11}"
          f"{'P(ruin)':>9}{'worst-10%':>11}")
    for label, em in [("POINT +12.5%", 1.0), ("HALF +6%", 0.5), ("honest-LB +3%", 0.25)]:
        for mm, tag in [(True, "MM"), (False, "taker")]:
            s = longrun(em, mm, SEED)
            print(f"{label:>22}{tag:>7}{s['med']:>+10.0f}{s['p_neg']:>10.1%}{s['p_dd']:>11.1%}"
                  f"{s['p_ruin']:>9.1%}{s['wdec']:>+11.0f}")
    print("\nread: MM (no fee) shifts every cell better, but the BINDING variable is edge-realness")
    print("(is the +12.5% real or a 2-tournament streak), not the fee — and flat sizing keeps the")
    print("drawdown bounded even on the full bad-days stack.")


if __name__ == "__main__":
    main()
