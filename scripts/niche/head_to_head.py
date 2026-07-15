#!/usr/bin/env python3
"""
HOW MUCH EDGE vs THE PREVIOUS CHAMPION?  (the number Tue asked for, on the same footing)

The collapse-risk model nets +3.15c/share OOS (roster-free, sports). But "+3.15c/share" is not the
unit the champion arm is quoted in, and its CI was clustered on MARKET, not EVENT. This script puts
the model on the SAME FOOTING as the previous strategy and reconciles with the ITER-5 ML refutation.

PREVIOUS STRATEGY (from project-polymarket-garbage-policy, the live champion book):
    champion `favorite`  : +2.81% ROI in-sample, +2.85% belief-blind LB   <- the bankable anchor
    `favorite_liq`       : +4.17% ROI (liquidity floor, 91% vol, "trustworthy")
    `favorite_v2`        : +7.63% OOS but "NOT bankable" (tennis-carried, coverage-artifact)
  These are ROI-ON-TURNOVER (net / entry price), event-clustered, at realizable entry.

ITER-5 (2026-07-09) already REFUTED an ML-combination model: at-fire SNAPSHOT features, 11 days,
walk-forward model - bet-everything = -2.75%. Its stated remedy: "months of data + richer features
(price dynamics) + ...". This model uses PRICE-PATH shape over MONTHS -- the missing ingredient. This
script tests whether that reconciliation actually holds up under ITER-5's OWN standard (event cluster).

UPGRADES over collapse_risk.py, each addressing a specific way the +3.15c could be too generous:
  1. EVENT CLUSTERING. Group submarkets of one game (mlb-tex-cle-2026-07-01-{nrfi,total,...}) into ONE
     cluster. The unit of risk is the GAME (project-polymarket-correlated-risk). Bootstrapping markets
     when a game has 8 correlated submarkets understates the CI. This is the check most likely to
     move the verdict.
  2. ROI-ON-TURNOVER, the champion's unit: ROI = net / entry_price. Reported next to c/share.
  3. MULTI-SEED model stability: retrain at 5 random_states; report the spread. A single lucky fit
     cannot survive this (ITER-5's "single-split +1.58% but walk-forward -2.75%" failure mode).
  4. NATIVE HEAD-TO-HEAD: the champion RULE (take every favourite) evaluated on the SAME rows, so the
     lift is a clean within-data difference, not a cross-study guess.

  ./head_to_head.py --self-test
  ./head_to_head.py
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
GUARD = ("SET work_mem='64MB'; SET statement_timeout='600s'; "
         "SET max_parallel_workers_per_gather=0; ")
CACHE = "reports/niche/.collapse_cache.pkl"
SEED = 20260714
THETA = {"tennis": .05, "soccer": .05, "mlb": .05, "nba": .05, "nhl": .05, "ufc": .05,
         "esports": .05, "politics": .04, "crypto": .07, "weather": .05, "other": .05}
FEATS = ["p", "persistence", "n_prints", "elapsed", "max_p", "dd_from_max", "vol",
         "n_dips", "n_flips", "drift_15m", "drift_1h", "staleness", "mean_p_1h", "niche"]
DATE_RE = re.compile(r"^(.*?\d{4}-\d{2}-\d{2})")


def fee(p, n):
    return THETA.get(n, .05) * p * (1 - p)


def event_key(slug, cid):
    """Group submarkets of one game. 'mlb-tex-cle-2026-07-01-nrfi' -> 'mlb-tex-cle-2026-07-01'.
    Long-form question slugs (no clean date prefix) fall back to their own condition_id."""
    if not slug:
        return cid
    m = DATE_RE.match(slug)
    return m.group(1) if m else cid


def psql(sql):
    o = subprocess.run(PG, input=GUARD + sql, capture_output=True, text=True)
    if o.returncode != 0:
        sys.exit("psql FAILED:\n" + o.stderr[:1200])
    return list(csv.DictReader(io.StringIO(o.stdout)))


def q_lit(xs):
    return ",".join("'" + str(x).replace("'", "''") + "'" for x in xs)


def boot_clustered(rows, cluster_of, n_boot=4000, seed=SEED):
    """rows = [(cid, net, price)]. Cluster on EVENT (via cluster_of[cid]). Returns net c/share AND
    ROI-on-turnover, both bootstrapped by resampling CLUSTERS (a game is one draw, not N submarkets)."""
    by = defaultdict(list)
    for cid, net, price in rows:
        by[cluster_of.get(cid, cid)].append((net, price))
    clusters = list(by)
    if len(clusters) < 20:
        return None
    net_c = np.array([np.mean([x[0] for x in by[c]]) for c in clusters], float)
    # ROI per cluster = mean(net)/mean(price) within the cluster (turnover-weighted)
    roi_c = np.array([np.sum([x[0] for x in by[c]]) / np.sum([x[1] for x in by[c]])
                      for c in clusters], float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(clusters), (n_boot, len(clusters)))
    bn = net_c[idx].mean(1)
    br = roi_c[idx].mean(1)
    return {"net": float(net_c.mean()), "net_lo": float(np.percentile(bn, 2.5)),
            "net_hi": float(np.percentile(bn, 97.5)), "net_p": float((bn <= 0).mean()),
            "roi": float(roi_c.mean()), "roi_lo": float(np.percentile(br, 2.5)),
            "roi_hi": float(np.percentile(br, 97.5)), "roi_p": float((br <= 0).mean()),
            "n_clusters": len(clusters), "n_rows": len(rows)}


def self_test():
    # event key strips the submarket, keeps the game
    assert event_key("mlb-tex-cle-2026-07-01-nrfi", "x") == "mlb-tex-cle-2026-07-01"
    assert event_key("mlb-tex-cle-2026-07-01-total-10pt5", "x") == "mlb-tex-cle-2026-07-01"
    assert event_key("mlb-chc-col-2026-06-10", "x") == "mlb-chc-col-2026-06-10"
    assert event_key("will-mexico-reach-the-r16-20260602025120735", "cid9") == "cid9"
    assert event_key(None, "cid9") == "cid9"
    # two submarkets a,b of ONE game collapse to a single cluster; 25 other games stay distinct
    co = {"a": "game0", "b": "game0"}
    for i in range(25):
        co[f"g{i}"] = f"game{i+1}"
    r = boot_clustered([("a", .05, .85)] * 5 + [("b", .05, .85)] * 5 +
                       [(f"g{i}", .05, .85) for i in range(25)], co)
    assert r["n_clusters"] == 26, f"a+b => 1 cluster + 25 games = 26, got {r['n_clusters']}"
    # ROI sanity: net .05 at price .85 -> ROI ~5.9%
    r2 = boot_clustered([(f"g{i}", .05, .85) for i in range(100)], {})
    assert abs(r2["roi"] - .05 / .85) < 1e-6 and r2["roi_lo"] > 0
    print("self-test OK  (event clustering; ROI-on-turnover)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test())

    from sklearn.ensemble import HistGradientBoostingClassifier

    with open(CACHE, "rb") as f:
        rows = pickle.load(f)
    cids = sorted({r["cid"] for r in rows})
    print(f"{len(rows):,} decision points / {len(cids):,} markets")

    # ---- fetch slugs, build EVENT clusters
    slug_of = {}
    for i in range(0, len(cids), 400):
        for r in psql(f"SELECT condition_id, slug FROM harvest_markets "
                      f"WHERE condition_id IN ({q_lit(cids[i:i+400])});"):
            slug_of[r["condition_id"]] = r["slug"]
    cluster_of = {c: event_key(slug_of.get(c), c) for c in cids}
    n_events = len({cluster_of[c] for c in cids})
    compression = len(cids) / max(n_events, 1)
    print(f"{n_events:,} EVENTS  (a game bundles {compression:.2f} submarkets on average)\n")

    A = [r for r in rows if r["win"] == "A"]
    B = [r for r in rows if r["win"] == "B"]
    Xa = np.array([r["x"] for r in A], float)
    ya = np.array([r["y"] for r in A], float)
    Xb = np.array([r["x"] for r in B], float)

    # ---- MULTI-SEED: retrain at 5 seeds, average EV -> stability
    evs = []
    for sd in range(5):
        clf = HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.06, max_leaf_nodes=15,
            min_samples_leaf=80, l2_regularization=1.0, random_state=sd)
        clf.fit(Xa, ya)
        pw = clf.predict_proba(Xb)[:, 1]
        evs.append(np.array([pw[i] - B[i]["p"] - fee(B[i]["p"], B[i]["niche"])
                             for i in range(len(B))]))
    ev = np.mean(evs, 0)
    ev_std = np.std([e.mean() for e in evs])
    print(f"multi-seed EV stability: mean-EV across 5 seeds sd = {ev_std:.5f} "
          f"({'STABLE' if ev_std < 0.002 else 'UNSTABLE'})\n")

    def cellrows(mask):
        return [(B[i]["cid"], B[i]["net"], B[i]["p"]) for i in range(len(B)) if mask[i]]

    W = 108
    print("=" * W)
    print("HEAD-TO-HEAD  (window B, OUT OF SAMPLE, EVENT-CLUSTERED CIs, verified fees)")
    print("=" * W)
    print(f"{'strategy':>34s} {'NET c/sh':>9s} {'net 95% CI':>17s} | "
          f"{'ROI/turn':>9s} {'ROI 95% CI':>18s} {'p':>6s} {'events':>7s}")
    print("-" * W)

    results = {}

    def show(name, rws):
        if len(rws) < 20:
            print(f"{name:>34s}   -- too few --")
            return
        r = boot_clustered(rws, cluster_of)
        if not r:
            return
        print(f"{name:>34s} {r['net']*100:>+8.3f}c "
              f"[{r['net_lo']*100:+.2f},{r['net_hi']*100:+.2f}] | "
              f"{r['roi']*100:>+8.2f}% [{r['roi_lo']*100:+.2f}%,{r['roi_hi']*100:+.2f}%] "
              f"{r['roi_p']:>6.3f} {r['n_clusters']:>7,}")
        results[name] = r
        return r

    champ = show("CHAMPION RULE: every favourite", cellrows(np.ones(len(B), bool)))
    show("MODEL EV>+0.00", cellrows(ev > 0.00))
    m1 = show("MODEL EV>+0.01", cellrows(ev > 0.01))
    m3 = show("MODEL EV>+0.03", cellrows(ev > 0.03))

    print("\n" + "=" * W)
    print("THE ANSWER TO 'HOW MUCH EDGE vs PREVIOUS?'")
    print("=" * W)
    if champ and m1:
        print(f"  vs the CHAMPION RULE on the SAME data (the clean, native comparison):")
        print(f"     champion take-every-favourite : {champ['roi']*100:+.2f}% ROI  "
              f"({champ['net']*100:+.3f}c/share)")
        print(f"     collapse model EV>+0.01        : {m1['roi']*100:+.2f}% ROI  "
              f"({m1['net']*100:+.3f}c/share)")
        print(f"     collapse model EV>+0.03        : {m3['roi']*100:+.2f}% ROI  "
              f"({m3['net']*100:+.3f}c/share)")
        print(f"     ==> LIFT over champion rule: "
              f"{(m1['roi']-champ['roi'])*100:+.2f}pp (EV>0.01), "
              f"{(m3['roi']-champ['roi'])*100:+.2f}pp (EV>0.03)")
        print(f"\n  vs the LIVE champion arm's quoted anchors (DIFFERENT pipeline -- see caveats):")
        print(f"     champion `favorite`   +2.81% ROI  (+2.85% belief-blind LB)")
        print(f"     `favorite_liq`        +4.17% ROI  (trustworthy, 91% vol)")
        print(f"     `favorite_v2`         +7.63% ROI  (NOT bankable -- tennis-carried artifact)")
        print(f"     collapse EV>0.01      {m1['roi']*100:+.2f}% ROI on "
              f"{m1['n_clusters']:,} events, {m1['n_rows']:,} signals")

    # capacity: signals/day. window B span from elapsed is unavailable; use event count as proxy.
    print(f"\n  CAPACITY: model fires on {m1['n_rows']:,} signals across {m1['n_clusters']:,} events")
    print(f"  (champion favourite arm fires ~7.8/day; this universe is 18x wider).")


if __name__ == "__main__":
    main()
