#!/usr/bin/env python3
"""
CAPACITY CURVE (harden-edge, P2) — the taker-path copyability ceiling.

Complementary to maker-copy G3 (does NOT re-derive fills; consumes its verdict + the existing
maker_capacity_fulltape.json / copyability.json). G3 + G2/G2b already characterized the MAKER path
(thin, adverse, coverage-biased flow; capture fraction needs forward paper-quoting). This adds the one
thing no prior artifact isolated: the NATIVE per-signal size — how much the backing sharps themselves
hold — which bounds how much we can copy at our own price before we STOP being a price-taker and
BECOME the dominant flow (at which point the edge measured at flat-$100 no longer applies).

native_size(signal) = initial_total_usd = aggregate USD the tracked backers hold at fire.
our_share(S)        = S / native_size  (what fraction of the native position our stake would be).
For a stake S we report the distribution of our_share across favorite signals and the fraction of
signals where we stay a "small copy" (our_share ≤ threshold). This is an OPTIMISTIC ceiling: it uses
the sharks' full ACCUMULATED position (much of it entered earlier/cheaper), not the marginal ask
liquidity at our entry in the 5-min window — which the full-tape flow ceiling (coverage-biased low,
$4–45/signal on reachable markets) shows is far thinner. Real taker impact at size needs order-book
depth we do not have historically (same wall G3 hit). So the TRUE capacity is BELOW this curve.

Read-only, paper-only, promotes nothing, no capital. DB via docker exec (same as selection_null.py).
"""
import json
import os
import subprocess
import sys

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q", "-c"]
REPORT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "reports", "capacity_curve_harden.json")

SQL = """
SELECT initial_total_usd
FROM consensus_signals
WHERE strategy='favorite' AND outcome_won IS NOT NULL
  AND initial_mean_price BETWEEN 0.65 AND 0.98
  AND initial_total_usd IS NOT NULL AND initial_total_usd > 0;
"""

STAKES = [100, 250, 500, 1000, 2500, 5000, 10000]
# our_share thresholds: below SMALL we are plausibly a passive copy; above LARGE we ARE the flow.
SMALL, LARGE = 0.10, 0.50


def q(sql):
    out = subprocess.run(PG + [sql], capture_output=True, text=True, check=True).stdout
    rows = [r for r in out.strip().splitlines()[1:] if r]
    return [float(r) for r in rows]


def pct(xs, p):
    xs = sorted(xs)
    if not xs:
        return None
    i = min(len(xs) - 1, int(p * len(xs)))
    return xs[i]


def main():
    native = q(SQL)
    n = len(native)
    curve = []
    for S in STAKES:
        shares = [S / v for v in native]
        frac_small = sum(1 for s in shares if s <= SMALL) / n
        frac_large = sum(1 for s in shares if s >= LARGE) / n
        curve.append({
            "stake_usd": S,
            "median_our_share": round(pct(shares, 0.5), 4),
            "p90_our_share": round(pct(shares, 0.9), 4),
            "frac_signals_small_copy_le10pct": round(frac_small, 3),
            "frac_signals_we_are_the_flow_ge50pct": round(frac_large, 3),
        })
    out = {
        "meta": {
            "universe": "favorite arm, resolved, price 0.65-0.98",
            "n_signals": n,
            "native_size": "initial_total_usd (aggregate tracked-backer holdings at fire)",
            "small_threshold": SMALL, "large_threshold": LARGE,
            "OPTIMISTIC_CEILING": ("uses full ACCUMULATED sharp position, not marginal ask liquidity; "
                                   "full-tape flow ceiling is far thinner ($4-45/signal reachable, "
                                   "coverage-biased low). TRUE taker capacity is BELOW this curve."),
            "native_pctiles": {p: round(pct(native, x)) for p, x in
                               (("p25", .25), ("median", .5), ("p75", .75), ("p90", .9))},
        },
        "curve": curve,
    }
    json.dump(out, open(REPORT, "w"), indent=1)
    print(f"favorite native per-signal size (n={n}): "
          f"p25 ${out['meta']['native_pctiles']['p25']:,} · "
          f"median ${out['meta']['native_pctiles']['median']:,} · "
          f"p90 ${out['meta']['native_pctiles']['p90']:,}")
    print("\nstake   median_our_share  p90_our_share  %small(≤10%)  %we-are-flow(≥50%)")
    for c in curve:
        print(f"${c['stake_usd']:>6}      {c['median_our_share']*100:6.1f}%        "
              f"{c['p90_our_share']*100:7.1f}%      {c['frac_signals_small_copy_le10pct']*100:5.1f}%        "
              f"{c['frac_signals_we_are_the_flow_ge50pct']*100:5.1f}%")
    print(f"\nwrote {REPORT}")


if __name__ == "__main__":
    main()
