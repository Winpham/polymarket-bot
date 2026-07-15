#!/usr/bin/env python3
"""
IS THE COLLAPSE EDGE BROAD, OR ONE-SPORT-CARRIED?  (the favorite_v2 trap)

favorite_v2's +7.63% died as a coverage artifact: it was tennis/Wimbledon-carried and failed the
repo's "certifies in >=2 non-soccer regimes at power" durability bar (project-polymarket-garbage-
policy). Any new favourite edge must clear that same bar or it is the same trap wearing new clothes.

This trains the collapse-risk model (window A) and evaluates it PER NICHE on window B, EVENT-clustered.
A real mechanism has STRUCTURE (works where price-path momentum is informative, fails where it isn't);
a scan artifact is uniformly positive.

  ./per_sport_durability.py --self-test
  ./per_sport_durability.py
"""
import argparse
import csv
import io
import pickle
import re
import subprocess
import sys
from collections import defaultdict

import numpy as np

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "-v", "ON_ERROR_STOP=1", "--csv", "-q"]
CACHE = "reports/niche/.collapse_cache.pkl"
SEED = 20260714
THETA = {"tennis": .05, "soccer": .05, "mlb": .05, "nba": .05, "nhl": .05, "ufc": .05,
         "esports": .05, "crypto": .07, "weather": .05, "other": .05}
DATE_RE = re.compile(r"^(.*?\d{4}-\d{2}-\d{2})")
TRADEABLE = ("soccer", "tennis", "esports", "ufc")


def fee(p, n):
    return THETA.get(n, .05) * p * (1 - p)


def psql(s):
    o = subprocess.run(PG, input="SET max_parallel_workers_per_gather=0; " + s,
                       capture_output=True, text=True)
    if o.returncode != 0:
        sys.exit("psql FAILED:\n" + o.stderr[:800])
    return list(csv.DictReader(io.StringIO(o.stdout)))


def qlit(xs):
    return ",".join("'" + x + "'" for x in xs)


def event_key(slug, cid):
    if not slug:
        return cid
    m = DATE_RE.match(slug)
    return m.group(1) if m else cid


def clustered_roi(rws, evk, nb=4000):
    by = defaultdict(list)
    for cid, net, pr in rws:
        by[evk(cid)].append((net, pr))
    cl = list(by)
    if len(cl) < 15:
        return None
    roi = np.array([sum(x[0] for x in by[c]) / sum(x[1] for x in by[c]) for c in cl], float)
    rng = np.random.default_rng(SEED)
    bs = roi[rng.integers(0, len(cl), (nb, len(cl)))].mean(1)
    return {"roi": float(roi.mean()), "lo": float(np.percentile(bs, 2.5)),
            "hi": float(np.percentile(bs, 97.5)), "p": float((bs <= 0).mean()), "n_ev": len(cl)}


def self_test():
    assert event_key("cs2-bhe-keyd-2026-07-08-map-handicap-away-1pt5", "x") == "cs2-bhe-keyd-2026-07-08"
    r = clustered_roi([(f"g{i}", .05, .85) for i in range(40)], lambda c: c)
    assert abs(r["roi"] - .05 / .85) < 1e-6 and r["lo"] > 0
    print("self-test OK")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test())
    from sklearn.ensemble import HistGradientBoostingClassifier

    rows = pickle.load(open(CACHE, "rb"))
    A = [r for r in rows if r["win"] == "A"]
    B = [r for r in rows if r["win"] == "B"]
    Xa = np.array([r["x"] for r in A]); ya = np.array([r["y"] for r in A])
    Xb = np.array([r["x"] for r in B])
    clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.06, max_leaf_nodes=15,
                                         min_samples_leaf=80, l2_regularization=1.0,
                                         random_state=0).fit(Xa, ya)
    pw = clf.predict_proba(Xb)[:, 1]
    ev = np.array([pw[i] - B[i]["p"] - fee(B[i]["p"], B[i]["niche"]) for i in range(len(B))])

    cids = sorted({r["cid"] for r in B})
    slug = {}
    for i in range(0, len(cids), 400):
        for r in psql(f"SELECT condition_id,slug FROM harvest_markets "
                      f"WHERE condition_id IN ({qlit(cids[i:i+400])});"):
            slug[r["condition_id"]] = r["slug"]
    evk = lambda c: event_key(slug.get(c), c)

    def sel(niches, thr):
        return [(B[i]["cid"], B[i]["net"], B[i]["p"]) for i in range(len(B))
                if B[i]["niche"] in niches and ev[i] > thr]

    print(f"{'niche':>10s} {'ungated ROI':>24s} | {'MODEL EV>0.01':>30s} {'signals':>8s}")
    print("-" * 82)
    working = []
    for n in ["mlb", "soccer", "tennis", "esports", "nba", "ufc", "nhl"]:
        u = clustered_roi(sel({n}, -9), evk)
        m = clustered_roi(sel({n}, 0.01), evk)
        us = f"{u['roi']*100:+.2f}% [{u['lo']*100:+.1f},{u['hi']*100:+.1f}] {u['n_ev']}ev" if u else "-- thin --"
        ms = f"{m['roi']*100:+.2f}% [{m['lo']*100:+.1f},{m['hi']*100:+.1f}] p={m['p']:.3f} {m['n_ev']}ev" if m else "-- thin --"
        print(f"{n:>10s} {us:>24s} | {ms:>30s} {len(sel({n},0.01)):>8,}")
        if m and m["p"] < 0.05 and m["roi"] > 0:
            working.append(n)
    nonsoccer = [n for n in working if n != "soccer"]
    print(f"\n  certifies (p<0.05, ROI>0) in: {working}")
    print(f"  NON-SOCCER regimes at power: {nonsoccer}  "
          f"=> favorite_v2's '>=2 non-soccer' durability bar "
          f"{'CLEARED' if len(nonsoccer) >= 2 else 'NOT met'}")

    print("\n=== REFINED headline: tradeable subset (drop the dead mlb/nba) ===")
    for thr in (0.00, 0.01, 0.03):
        m = clustered_roi(sel(set(TRADEABLE), thr), evk)
        print(f"  MODEL EV>{thr:+.2f}: {m['roi']*100:+.2f}% ROI "
              f"[{m['lo']*100:+.1f},{m['hi']*100:+.1f}] p={m['p']:.3f}  "
              f"{len(sel(set(TRADEABLE), thr)):,} signals / {m['n_ev']:,} events")
    u = clustered_roi(sel(set(TRADEABLE), -9), evk)
    print(f"  ungated: {u['roi']*100:+.2f}% ROI [{u['lo']*100:+.1f},{u['hi']*100:+.1f}]  "
          f"{u['n_ev']:,} events")


if __name__ == "__main__":
    main()
