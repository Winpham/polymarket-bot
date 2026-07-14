#!/usr/bin/env python3
"""PER-ARM EXECUTION POSTURE ON US — take or make, at what price, for what net. READ-ONLY.

This is the deliverable the whole run exists for: for each arm we actually trade, the realizable
US economics, and the resulting posture. Every input is either MEASURED here or taken from our own
certified arm records — nothing is quoted from a fee table alone.

INPUTS AND WHERE THEY COME FROM
-------------------------------
gross edge      our certified arms, as ROI ON STAKE (reports/PREREG_*_favorite_v2, WEATHER-VERDICT):
                  favorite  full-book resolved ROI (taker) +2.81%; +4.17% with the liquidity gate
                  weather   day-clustered LOWER BOUND +2.89% (0.71-0.98 band, one-week caveat)
                Edge per SHARE = ROI * p, because ROI is on stake and stake per share IS p.
taker fee       us_fees: Theta*p*(1-p), Theta=0.06, confirmed on all 2,999 live markets.
maker rebate    us_fees: Theta=-0.0125 (you are paid).
maker markout   MEASURED (us_adverse_selection.py) on real identified makers, mid-referenced.
reward          MEASURED (us_reward_model.py); negligible at our size — see the verdict.

THE FINDING THIS TABLE EXISTS TO SHOW
-------------------------------------
Inside our own champion band, the fee and the edge move in OPPOSITE directions:
    edge/share = ROI * p          -- RISES with p
    fee/share  = Theta * p*(1-p)  -- PEAKS at p=0.5 and COLLAPSES toward 1.0
so the fee as a fraction of the edge falls hard as the favorite gets deeper. The band is not
economically uniform on US, and treating it as one cell leaves money on the table.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import us_fees  # noqa: E402

# Certified arm edges, as ROI on stake (our own records; see module docstring).
ARMS = {
    "favorite (full book)":      {"roi": 0.0281, "band": (0.71, 0.98)},
    "favorite (+liquidity gate)": {"roi": 0.0417, "band": (0.71, 0.98)},
    "weather 0.71-0.98 (LB)":    {"roi": 0.0289, "band": (0.71, 0.98)},
}

# MEASURED maker economics (us_adverse_selection.py, named-maker cohort = our reference class).
# markout is what a fill is worth to the resting side AFTER informed flow takes its cut. None of
# these is significantly positive once concentration is stripped out — see the verdict.
MEASURED_MARKOUT_C = {          # cents/share, 60s horizon
    "favorite 0.71-0.98": +0.39,   # leave-one-out; headline +1.00c DIES (p=0.51)
    "midrange 0.30-0.71": -0.52,   # leave-one-out; SURVIVES (p=0.005) — the one robust result
    "all bands": -0.13,            # leave-one-out; not significant (p=0.43)
}
# Reward per filled share at a realistic resting size (us_reward_model.py). Our 1,000 contracts is
# ~0.9% of a 62k-540k contract touch queue -> $0.13/hour. Rounds to zero per share; we carry it as
# 0.0 rather than pretend the published pool reaches us.
REWARD_PER_SHARE_C = 0.0

PRICES = [0.71, 0.75, 0.80, 0.85, 0.90, 0.95, 0.98]
TIERS = [(0.00, "no tier"), (0.25, "tier 25%"), (0.50, "tier 50%")]


def taker_table():
    print("=" * 100)
    print("TAKER POSTURE — the fee as a fraction of the edge, ACROSS our own champion band")
    print("=" * 100)
    for name, a in ARMS.items():
        roi = a["roi"]
        print(f"\n--- {name}   (certified ROI on stake: {roi*100:+.2f}%)")
        print(f"{'p':>6} {'edge/sh':>9} {'taker fee':>10} {'fee % of edge':>14} "
              f"{'NET no tier':>12} {'NET @25%':>10} {'NET @50%':>10}")
        best = None
        for p in PRICES:
            edge_c = roi * p * 100                       # ROI is on stake; stake/share == p
            fee_c = us_fees.taker_fee(p) * 100
            net0 = edge_c - fee_c
            net25 = edge_c - us_fees.taker_fee(p, 1.0, 0.25) * 100
            net50 = edge_c - us_fees.taker_fee(p, 1.0, 0.50) * 100
            frac = fee_c / edge_c * 100 if edge_c else float("inf")
            print(f"{p:>6.2f} {edge_c:>8.2f}c {fee_c:>9.2f}c {frac:>13.0f}% "
                  f"{net0:>11.2f}c {net25:>9.2f}c {net50:>9.2f}c")
            if best is None or net0 > best[1]:
                best = (p, net0)
        print(f"    -> fee-adjusted edge is MAXIMISED at p={best[0]:.2f} (net {best[1]:.2f}c/share)")


def maker_vs_taker():
    print()
    print("=" * 100)
    print("TAKE OR MAKE — per arm, at the realizable US economics")
    print("=" * 100)
    print("maker net = MEASURED markout + rebate + reward(measured ~0).  taker net = edge - fee.")
    print("The maker column carries NO gross edge: a resting order does not select its fills, so it")
    print("does not get to keep the arm's alpha — it gets whatever the flow hands it. That is the")
    print("whole point of measuring the markout instead of assuming the edge survives.")
    print()
    print(f"{'arm':<28}{'p':>6}{'TAKER net':>11}{'TAKER@25%':>11}{'MAKER net':>11}  posture")
    print("-" * 100)
    for name, a in ARMS.items():
        roi = a["roi"]
        for p in (0.75, 0.85, 0.95):
            edge_c = roi * p * 100
            t0 = edge_c - us_fees.taker_fee(p) * 100
            t25 = edge_c - us_fees.taker_fee(p, 1.0, 0.25) * 100
            mk = (MEASURED_MARKOUT_C["favorite 0.71-0.98"]
                  + us_fees.maker_rebate(p) * 100 + REWARD_PER_SHARE_C)
            posture = "TAKE" if t0 > mk else "make"
            print(f"{name:<28}{p:>6.2f}{t0:>10.2f}c{t25:>10.2f}c{mk:>10.2f}c  {posture}")
    print("-" * 100)
    print("The maker column is not a business: its markout is NOT significantly positive once the")
    print("top market is dropped (p=0.51), and it forfeits the arm's gross edge entirely.")


if __name__ == "__main__":
    taker_table()
    maker_vs_taker()
