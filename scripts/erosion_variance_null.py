#!/usr/bin/env python3
"""
PHASE A -- rule out VARIANCE before telling any causal story.

The observation to explain: cumulative ROI-on-turnover slid 8.4% -> 7.1% over the last ~5 days,
with 07-12 (-8.5%) and 07-13 (-2.8%) the visible down days.

The null we must kill first: the edge is CONSTANT at its full-sample level, and the recent
window is a cold streak drawn from the same match-level distribution.

Two nulls, both respecting the match as the unit of risk (superkey clustering):
  (1) MATCH permutation  -- matches exchangeable across time. Preserves within-match leg
      correlation (legs are already collapsed into the match). Ignores slate/day correlation.
  (2) DAY-BLOCK permutation -- whole days exchangeable (EXACT enumeration over C(16,k) day
      splits when feasible). Preserves intra-day/slate correlation, which is the honest,
      CONSERVATIVE null: a bad slate day is one draw, not 20.

Statistic: ROI-on-turnover(recent) - ROI-on-turnover(earlier), turnover-weighted at the match
level. One-sided (we are testing for a DROP), so p = P(perm diff <= observed diff).

Also reported: the same test on the BELIEF-BLIND SURPLUS (skill = favorite - _blind at the same
band mix), because a raw-ROI drop that is really a softness drop is not an edge decay.

Windows tested: last 3/4/5/7 days. That is 4 windows x 2 nulls x 2 metrics = 16 tests;
Benjamini-Hochberg is applied over the family and reported alongside raw p.

Read-only. Emits reports/EROSION-VARIANCE-NULL.json.
  --selftest exercises the estimator on synthetic constant-edge and true-decay series.
"""

import itertools
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import erosion_lib as E  # noqa: E402

RNG_SEED = 20260714
N_PERM = 20000


def _roi(units):
    """units: list of (pnl, turnover) match tuples -> ROI-on-turnover."""
    tt = sum(u[1] for u in units)
    return (sum(u[0] for u in units) / tt) if tt else 0.0


def observed_and_null(units_by_day, days, k, rng, n_perm=N_PERM):
    """units_by_day: {day: [(pnl,turn),...]}. Split last k days = recent.
    Returns dict with observed diff, match-permutation p, day-block permutation p."""
    recent_days = days[-k:]
    early_days = days[:-k]
    rec = [u for d in recent_days for u in units_by_day[d]]
    ear = [u for d in early_days for u in units_by_day[d]]
    if not rec or not ear:
        return None
    obs = _roi(rec) - _roi(ear)

    # --- (1) MATCH permutation: shuffle match->window labels, keep counts fixed
    allu = ear + rec
    n_rec = len(rec)
    arr = np.array(allu, dtype=float)  # (N,2) pnl,turn
    hits = 0
    for _ in range(n_perm):
        idx = rng.permutation(len(arr))
        r = arr[idx[:n_rec]]
        e = arr[idx[n_rec:]]
        d = (r[:, 0].sum() / r[:, 1].sum()) - (e[:, 0].sum() / e[:, 1].sum())
        if d <= obs + 1e-12:
            hits += 1
    p_match = (hits + 1) / (n_perm + 1)

    # --- (2) DAY-BLOCK permutation: which k of the N days are "recent"? exact if feasible
    n_days = len(days)
    combos = list(itertools.combinations(range(n_days), k))
    exact = len(combos) <= 50000
    if not exact:
        combos = [tuple(rng.choice(n_days, k, replace=False)) for _ in range(n_perm)]
    hits = 0
    for c in combos:
        cs = set(c)
        r = [u for i, d in enumerate(days) if i in cs for u in units_by_day[d]]
        e = [u for i, d in enumerate(days) if i not in cs for u in units_by_day[d]]
        if not r or not e:
            continue
        if (_roi(r) - _roi(e)) <= obs + 1e-12:
            hits += 1
    p_day = (hits + 1) / (len(combos) + 1)

    return {
        "k_days": k,
        "recent_days": recent_days,
        "n_matches_recent": len(rec),
        "n_matches_earlier": len(ear),
        "roi_recent": _roi(rec),
        "roi_earlier": _roi(ear),
        "observed_diff": obs,
        "p_match_perm": p_match,
        "p_dayblock_perm": p_day,
        "dayblock_exact": exact,
        "n_dayblock_combos": len(combos),
    }


def bh(pvals):
    """Benjamini-Hochberg adjusted p-values, order preserved."""
    n = len(pvals)
    order = sorted(range(n), key=lambda i: pvals[i])
    adj = [0.0] * n
    prev = 1.0
    for rank, i in enumerate(reversed(order), start=1):
        j = n - rank + 1  # BH rank of this p in ascending order
        val = min(prev, pvals[i] * n / j)
        adj[i] = val
        prev = val
    return adj


def build_units(rows, basis="imp", metric="raw"):
    """metric 'raw'  -> match (pnl, turnover) on the favorite arm.
       metric 'skill'-> match (pnl - blind_expected*turnover, turnover): belief-blind SURPLUS.
       Returns ({day: [(pnl,turn)]}, sorted_days)."""
    ls = E.legs(rows, basis=basis)
    blind, nb = E.blind_edge_by_band(rows, basis=basis)
    mday = E.match_day(ls)
    from collections import defaultdict
    agg = defaultdict(lambda: [0.0, 0.0])
    for l in ls:
        g, t = E.pnl(l)
        if metric == "skill":
            b = min(int(l["p"] * nb), nb - 1)
            g -= blind.get(b, 0.0) * t  # subtract the structural/softness component
        agg[l["key"]][0] += g
        agg[l["key"]][1] += t
    by_day = defaultdict(list)
    for k, v in agg.items():
        by_day[mday[k]].append((v[0], v[1]))
    days = sorted(by_day)
    return dict(by_day), days


def selftest():
    rng = np.random.default_rng(1)
    ok = True
    # A) constant edge, no decay -> p should be uniform-ish, NOT small
    days = [f"d{i:02d}" for i in range(16)]
    ubd = {d: [(rng.normal(0.08, 0.35), 1.0) for _ in range(12)] for d in days}
    r = observed_and_null(ubd, days, 4, rng, n_perm=2000)
    if r["p_match_perm"] < 0.02:
        print(f"  FAIL: constant-edge series flagged as decay (p={r['p_match_perm']:.3f})")
        ok = False
    else:
        print(f"  ok: constant-edge null not rejected (p_match={r['p_match_perm']:.3f})")
    # B) genuine decay: last 4 days edge -0.25 -> p SHOULD be small
    ubd2 = {d: [(rng.normal(0.08 if i < 12 else -0.25, 0.35), 1.0) for _ in range(12)]
            for i, d in enumerate(days)}
    r2 = observed_and_null(ubd2, days, 4, rng, n_perm=2000)
    if r2["p_match_perm"] > 0.05:
        print(f"  FAIL: true decay NOT detected (p={r2['p_match_perm']:.3f})")
        ok = False
    else:
        print(f"  ok: true decay detected (p_match={r2['p_match_perm']:.4f})")
    # C) BH monotone + bounded
    a = bh([0.01, 0.04, 0.2, 0.9])
    if not all(0 <= x <= 1 for x in a) or a != sorted(a):
        print(f"  FAIL: BH not monotone/bounded: {a}")
        ok = False
    else:
        print(f"  ok: BH adjust monotone+bounded {['%.3f' % x for x in a]}")
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        sys.exit(selftest())

    rng = np.random.default_rng(RNG_SEED)
    rows = E.fetch()
    results = {"basis": "imp", "note": "stationary price source on 100% of legs, all 16 days",
               "tests": [], "daily": {}}

    for metric in ("raw", "skill"):
        ubd, days = build_units(rows, basis="imp", metric=metric)
        results["daily"][metric] = {
            d: {"matches": len(ubd[d]), "roi": _roi(ubd[d])} for d in days
        }
        for k in (3, 4, 5, 7):
            r = observed_and_null(ubd, days, k, rng)
            if r:
                r["metric"] = metric
                results["tests"].append(r)

    # multiplicity across the whole family (both nulls, both metrics, 4 windows)
    fam = []
    for t in results["tests"]:
        fam.append(("match", t["metric"], t["k_days"], t["p_match_perm"]))
        fam.append(("dayblock", t["metric"], t["k_days"], t["p_dayblock_perm"]))
    adj = bh([f[3] for f in fam])
    results["family"] = [
        {"null": f[0], "metric": f[1], "k_days": f[2], "p_raw": f[3], "p_bh": a}
        for f, a in zip(fam, adj)
    ]
    results["n_tests_in_family"] = len(fam)
    results["min_p_raw"] = min(f[3] for f in fam)
    results["min_p_bh"] = min(adj)

    # HEADLINE uses the DAY-BLOCK null only. The match-permutation null treats each match as
    # exchangeable and so ignores slate/day correlation -- it is ANTI-CONSERVATIVE here (a
    # single bad slate is ~20 correlated matches, not 20 independent draws) and would
    # overstate significance. Day-block is the honest null; we gate on it.
    db = [(t["metric"], t["k_days"], t["p_dayblock_perm"]) for t in results["tests"]]
    db_adj = bh([x[2] for x in db])
    results["dayblock_family"] = [
        {"metric": m, "k_days": k, "p_raw": p, "p_bh": a}
        for (m, k, p), a in zip(db, db_adj)
    ]
    results["dayblock_min_p_raw"] = min(x[2] for x in db)
    results["dayblock_min_p_bh"] = min(db_adj)
    results["variance_ruled_out"] = bool(results["dayblock_min_p_bh"] < 0.05)
    results["headline_null"] = "dayblock"

    os.makedirs("reports", exist_ok=True)
    with open("reports/EROSION-VARIANCE-NULL.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"{'metric':6s} {'k':>2s} {'M_rec':>5s} {'ROI_rec':>8s} {'ROI_ear':>8s} "
          f"{'diff':>7s} {'p_match':>8s} {'p_dayblk':>8s}")
    for t in results["tests"]:
        print(f"{t['metric']:6s} {t['k_days']:2d} {t['n_matches_recent']:5d} "
              f"{100*t['roi_recent']:7.1f}% {100*t['roi_earlier']:7.1f}% "
              f"{100*t['observed_diff']:6.1f}% {t['p_match_perm']:8.3f} {t['p_dayblock_perm']:8.3f}")
    print(f"\nfull family of {results['n_tests_in_family']} tests | min raw p={results['min_p_raw']:.3f} "
          f"| min BH-adj p={results['min_p_bh']:.3f}")
    print("HEADLINE = day-block null (match-perm ignores slate correlation -> anti-conservative):")
    for r in results["dayblock_family"]:
        print(f"  {r['metric']:6s} k={r['k_days']:2d}  p_raw={r['p_raw']:.3f}  p_BH={r['p_bh']:.3f}")
    print(f"  min day-block BH-adj p = {results['dayblock_min_p_bh']:.3f}")
    print(f"VARIANCE RULED OUT (day-block, BH): {results['variance_ruled_out']}")
    print("-> reports/EROSION-VARIANCE-NULL.json")


if __name__ == "__main__":
    main()
