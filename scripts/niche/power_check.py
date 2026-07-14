#!/usr/bin/env python3
"""
IS THE NULL REAL, OR ARE WE JUST UNDERPOWERED? -- the decisive diagnostic.

Every negative result invites the same objection: "you just didn't have enough data per
trader." This settles it.

If copyable skill EXISTS but is estimated noisily, then measuring each wallet on MORE
markets must sharpen the estimate, and the A->B rank correlation MUST RISE with per-wallet
N. (Classic attenuation: observed rho ~ true_rho * reliability, and reliability grows with
N.) If instead rho stays pinned near zero no matter how much history each wallet has, then
there is no signal being estimated -- the null is REAL, not a power artifact.

We also report, per stratum, the DETECTABLE EFFECT SIZE (the market-clustered CI
half-width on the top-50's out-of-sample surplus). The key question is not "is the CI wide"
but "is it narrower than the edge we would need to make money" -- a bankable copy edge must
clear roughly the 3% capture cost (1% slippage + 2% fee) on top of the 1.3c follower tax
already subtracted. If the undetectable region lies entirely BELOW the profitable region,
then the null is decision-complete: anything we cannot see is also anything we cannot bank.
"""
import statistics
import subprocess
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from rankers import (load, is_mm, spearman_ci, cluster_boot,  # noqa: E402
                     TAX, N_FLOOR_SPLIT)

BANKABLE = 0.03      # capture cost floor: a copy edge below this cannot be banked
STRATA = [(8, 14), (15, 24), (25, 49), (50, 10_000)]


def main():
    recs = load()
    niches = sorted({nz for (_, nz) in recs})
    print("ATTENUATION TEST -- does rank correlation RISE with per-wallet N?")
    print("(if skill is real but noisy it must; if it stays ~0, the null is real)\n")

    for nz in niches:
        mkt_ts = {}
        for (w, x), mk in recs.items():
            if x != nz:
                continue
            for m in mk:
                mkt_ts[m["mkt"]] = max(mkt_ts.get(m["mkt"], 0.0), m["ts"])
        if not mkt_ts:
            continue
        cut = sorted(mkt_ts.values())[len(mkt_ts) // 2]
        win_A = {k for k, v in mkt_ts.items() if v <= cut}

        pool = {}
        for (w, x), mk in recs.items():
            if x != nz or is_mm(mk):
                continue
            A = [m for m in mk if m["mkt"] in win_A]
            B = [m for m in mk if m["mkt"] not in win_A]
            if len(A) >= N_FLOOR_SPLIT and len(B) >= N_FLOOR_SPLIT:
                pool[w] = (A, B)
        if len(pool) < 50:
            continue

        print(f"{'='*80}\nNICHE: {nz}   ({len(pool)} testable wallets)")
        print(f"{'markets in A':>14s} {'wallets':>8s} {'rho(A,B)':>20s} "
              f"{'top-N B-surplus':>16s} {'CI half-width':>14s}  detectable?")
        print("-" * 80)
        for lo_n, hi_n in STRATA:
            sub = {w: v for w, v in pool.items() if lo_n <= len(v[0]) <= hi_n}
            if len(sub) < 30:
                print(f"{lo_n:>6d}-{hi_n if hi_n<9999 else '+':<7} {len(sub):>8d}   "
                      f"(too few wallets)")
                continue
            xs = [statistics.fmean([m["surplus"] for m in A]) for A, B in sub.values()]
            ys = [statistics.fmean([m["surplus"] - TAX for m in B]) for A, B in sub.values()]
            rho, rlo, rhi = spearman_ci(xs, ys)
            ranked = sorted(sub.items(), key=lambda kv: statistics.fmean(
                [m["surplus"] for m in kv[1][0]]), reverse=True)
            top = ranked[:min(50, max(10, len(ranked) // 4))]
            br = [(m["mkt"], m["surplus"] - TAX) for _, (A, B) in top for m in B]
            obs, clo, chi, nclu = cluster_boot(br)
            half = (chi - clo) / 2
            print(f"{lo_n:>6d}-{hi_n if hi_n<9999 else '+':<7} {len(sub):>8d} "
                  f"{rho:+.3f} [{rlo:+.2f},{rhi:+.2f}] {obs:+15.4f} {half:>13.4f}  "
                  f"{'YES: could see a 3% edge' if half < BANKABLE else 'no: 3% edge unresolvable'}")
        print()

    print("=" * 80)
    print("READING THIS TABLE")
    print("  rho RISING with N          => skill is real, we were just noisy  -> keep digging")
    print("  rho FLAT at ~0 across N    => there is no signal to estimate     -> the null is REAL")
    print("  CI half-width < 3%         => we had the power to see a bankable edge and did not")


if __name__ == "__main__":
    main()
