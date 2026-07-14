#!/usr/bin/env python3
"""
CAN THE EDGE BE HAD WITHOUT THE ROSTER?

blind_weighting.py proved the roster has exactly ONE edge channel. Markets are binary with
complementary prices, so at any instant both legs must buy the same outcome; hence

    D(won) | same-outcome  = +0.0000   (identically zero -- structure demands it)
    D(won) | diff-outcome  = +0.3126   (4.8% of prints, carries 100% of the effect)

==> The roster's edge is COLLAPSE AVOIDANCE. Buying a >=80c favourite only costs you when you buy
    the side that is ahead and then LOSES. The roster does not hold that bag as often.

If collapse risk is predictable from MARKET FEATURES ALONE, the roster is decoration, and we get:
  * 43,731 untruncated markets instead of the roster's 2,360   (18x the universe)
  * unlimited capacity -- not 7.8 signals/day
  * NATIVE US-BOOK EXECUTION. The US venue has no wallet history, so a roster CANNOT be built there
    retrospectively -- but a market-feature model needs no identity at all. This is the difference
    between a strategy we can run and one we can only watch.

DESIGN
  universe   sports markets (the US-tradeable set), resolved, untruncated
  unit       an OPPORTUNITY = a (market, outcome) that trades >=80c. Decision points sampled from
             its >=80c taker prints.
  label      won (0/1).   payoff: net = won - p - fee(p, niche)   [verified theta, not the typed 0.03]
  split      TRAIN = window A markets, TEST = window B markets. Disjoint by market. Same A/B split
             the roster work used, so the two are directly comparable.
  CIs        bootstrap CLUSTERED ON MARKET (never on the row -- rows within a market share a
             resolution and are not independent).

LEAKAGE DISCIPLINE (this repo has been bitten before -- see the within-match leak class)
  Every feature is computed from prints STRICTLY BEFORE the decision time, on that outcome's own
  tape. Explicitly BANNED as lookahead:
    * n_trades       -- the market's FULL print count, known only after it ends
    * life-fraction  -- needs the market's end timestamp
    * anything using max(ts) of the market
  A self-test asserts the feature builder cannot see the future.

  ./collapse_risk.py --self-test
  ./collapse_risk.py
"""
import argparse
import csv
import io
import json
import os
import pickle
import subprocess
import sys
from collections import defaultdict

import numpy as np

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "-v", "ON_ERROR_STOP=1", "--csv", "-q"]
GUARD = ("SET work_mem='64MB'; SET statement_timeout='600s'; "
         "SET max_parallel_workers_per_gather=0; ")
BATCH = 150
SEED = 20260714
CACHE = "reports/niche/.collapse_cache.pkl"

THETA = {"tennis": .05, "soccer": .05, "mlb": .05, "nba": .05, "nhl": .05, "ufc": .05,
         "esports": .05, "politics": .04, "crypto": .07, "weather": .05, "other": .05}
SPORTS = ("soccer", "mlb", "tennis", "esports", "nba", "nhl", "ufc")
NICHE_IDX = {n: i for i, n in enumerate(SPORTS)}
BAND_LO = 0.80
MAX_DP = 8                      # decision points sampled per opportunity

FEATS = ["p", "persistence", "n_prints", "elapsed", "max_p", "dd_from_max", "vol",
         "n_dips", "n_flips", "drift_15m", "drift_1h", "staleness", "mean_p_1h", "niche"]


def fee(p, n):
    return THETA.get(n, .05) * p * (1 - p)


def psql(sql):
    o = subprocess.run(PG, input=GUARD + sql, capture_output=True, text=True)
    if o.returncode != 0:
        sys.exit("psql FAILED:\n" + o.stderr[:1200])
    return list(csv.DictReader(io.StringIO(o.stdout)))


def q_lit(xs):
    return ",".join("'" + str(x).replace("'", "''") + "'" for x in xs)


# ---------------------------------------------------------------------------- features
def featurize(tape, i, niche):
    """tape = [(t,p)] sorted ascending for ONE outcome. i = index of the decision print.
    Uses ONLY tape[:i+1]. Nothing after i is readable -- enforced by the self-test."""
    t, p = tape[i]
    hist = tape[:i + 1]
    ps = np.array([x[1] for x in hist], float)
    ts = np.array([x[0] for x in hist], float)

    # persistence: seconds continuously >= BAND_LO
    start = None
    for (tt, pp) in hist:
        if pp >= BAND_LO:
            if start is None:
                start = tt
        else:
            start = None
    persistence = 0.0 if start is None else t - start

    max_p = float(ps.max())
    elapsed = float(t - ts[0])
    recent = ps[-30:]
    vol = float(recent.std()) if len(recent) > 2 else 0.0
    # times it fell OUT of the favourite band, and times it crossed the 50c line (lead changes)
    n_dips = int(np.sum((ps[:-1] >= BAND_LO) & (ps[1:] < BAND_LO))) if len(ps) > 1 else 0
    n_flips = int(np.sum((ps[:-1] >= .5) != (ps[1:] >= .5))) if len(ps) > 1 else 0

    def px_ago(sec):
        j = np.searchsorted(ts, t - sec)
        j = min(max(j, 0), len(ps) - 1)
        return float(ps[j])

    m1h = ts >= (t - 3600)
    return [p, persistence, float(len(hist)), elapsed, max_p, max_p - p, vol,
            float(n_dips), float(n_flips), p - px_ago(900), p - px_ago(3600),
            float(t - ts[-2]) if len(ts) > 1 else 0.0,
            float(ps[m1h].mean()) if m1h.any() else p,
            float(NICHE_IDX.get(niche, -1))]


def boot_by_market(rows, key="net", n_boot=3000, seed=SEED):
    """Bootstrap CLUSTERED ON MARKET. rows = [(cid, value)]."""
    by = defaultdict(list)
    for cid, v in rows:
        by[cid].append(v)
    mkts = list(by)
    if len(mkts) < 20:
        return None
    means = np.array([np.mean(by[m]) for m in mkts], float)
    rng = np.random.default_rng(seed)
    bs = means[rng.integers(0, len(means), (n_boot, len(means)))].mean(1)
    return {"mean": float(means.mean()), "lo": float(np.percentile(bs, 2.5)),
            "hi": float(np.percentile(bs, 97.5)), "p": float((bs <= 0).mean()),
            "n_markets": len(mkts), "n_rows": len(rows)}


# ---------------------------------------------------------------------------- self-test
def self_test():
    # THE LEAK TEST: mutating the FUTURE of the tape must not change the features.
    tape = [(0, .5), (100, .85), (200, .86), (300, .84), (400, .95), (500, .10)]
    f_now = featurize(tape, 2, "soccer")
    tape_alt = tape[:3] + [(300, .01), (400, .01), (500, .01)]   # future rewritten to a collapse
    f_alt = featurize(tape_alt, 2, "soccer")
    assert f_now == f_alt, "FEATURE BUILDER IS LEAKING THE FUTURE"

    # persistence is backward-looking and a dip resets it
    t2 = [(0, .5), (100, .85), (130, .70), (150, .88), (200, .90)]
    assert featurize(t2, 4, "mlb")[FEATS.index("persistence")] == 50.0
    assert featurize(t2, 4, "mlb")[FEATS.index("n_dips")] == 1

    # lead changes counted
    t3 = [(0, .4), (10, .6), (20, .3), (30, .9)]
    assert featurize(t3, 3, "mlb")[FEATS.index("n_flips")] == 3

    # drawdown from the running max
    t4 = [(0, .95), (10, .85)]
    assert abs(featurize(t4, 1, "mlb")[FEATS.index("dd_from_max")] - .10) < 1e-9

    assert abs(fee(.9, "soccer") - .05 * .09) < 1e-12

    # market-clustered bootstrap: 100 rows in ONE market must NOT look like 100 independent rows
    r_one = boot_by_market([("m", 0.05)] * 100 + [(f"x{i}", 0.0) for i in range(20)])
    assert r_one["n_markets"] == 21, "clustering must collapse a market to one unit"
    print("self-test OK  (no lookahead; bootstrap clusters on market)")
    return 0


# ---------------------------------------------------------------------------- data
def build(limit_mkts):
    if os.path.exists(CACHE):
        print(f"loading cache {CACHE}")
        with open(CACHE, "rb") as f:
            return pickle.load(f)

    # window split: median of each market's LAST harvest ts  (same split the roster work used)
    # harvest_wm.ts is NUMERIC (an epoch), not a timestamp -- do not EXTRACT from it.
    split = float(psql("SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY mts) s "
                       "FROM (SELECT condition_id, MAX(ts) mts "
                       "FROM harvest_wm GROUP BY 1) y;")[0]["s"])
    mk = psql(f"""
        SELECT m.condition_id, m.niche, w.mts
        FROM harvest_markets m
        JOIN (SELECT condition_id, MAX(ts) mts FROM harvest_wm GROUP BY 1) w USING (condition_id)
        WHERE NOT m.truncated AND m.niche IN ({q_lit(SPORTS)})
        ORDER BY m.condition_id
        {'LIMIT ' + str(limit_mkts) if limit_mkts else ''};""")
    print(f"{len(mk):,} sports markets   split@{split:.0f}")
    niche_of = {r["condition_id"]: r["niche"] for r in mk}
    win_of = {r["condition_id"]: ("B" if float(r["mts"]) > split else "A") for r in mk}
    mkts = [r["condition_id"] for r in mk]

    rows, rng = [], np.random.default_rng(SEED)
    for i in range(0, len(mkts), BATCH):
        ch = mkts[i:i + BATCH]
        tape = defaultdict(list)
        for r in psql(f"""
              SELECT condition_id, outcome_index, EXTRACT(EPOCH FROM ts) t, price p
              FROM harvest_fills
              WHERE side='BUY' AND is_maker=false AND condition_id IN ({q_lit(ch)});"""):
            tape[(r["condition_id"], r["outcome_index"])].append((float(r["t"]), float(r["p"])))
        won = {}
        for r in psql(f"""
              SELECT condition_id, outcome_index, BOOL_OR(outcome_won)::int w
              FROM trader_fills WHERE resolved AND outcome_won IS NOT NULL
                AND condition_id IN ({q_lit(ch)}) GROUP BY 1,2;"""):
            won[(r["condition_id"], r["outcome_index"])] = float(r["w"])

        for k, tp in tape.items():
            if k not in won or len(tp) < 5:
                continue
            tp.sort()
            cand = [j for j, (t, p) in enumerate(tp) if p >= BAND_LO]
            if not cand:
                continue
            pick = cand if len(cand) <= MAX_DP else list(
                rng.choice(cand, MAX_DP, replace=False))
            cid, oi = k
            n = niche_of[cid]
            for j in sorted(pick):
                f = featurize(tp, j, n)
                p = tp[j][1]
                rows.append({"cid": cid, "oi": oi, "niche": n, "win": win_of[cid],
                             "x": f, "y": won[k], "p": p,
                             "net": won[k] - p - fee(p, n)})
        sys.stdout.write(f"\r  {min(i+BATCH, len(mkts)):,}/{len(mkts):,} markets  "
                         f"{len(rows):,} rows")
        sys.stdout.flush()
    print()
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "wb") as f:
        pickle.dump(rows, f)
    return rows


# ---------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="reports/niche/collapse_risk.json")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test())

    from sklearn.ensemble import HistGradientBoostingClassifier

    rows = build(a.limit)
    A = [r for r in rows if r["win"] == "A"]
    B = [r for r in rows if r["win"] == "B"]
    print(f"\nTRAIN (window A): {len(A):,} decision points / "
          f"{len({r['cid'] for r in A}):,} markets")
    print(f"TEST  (window B): {len(B):,} decision points / "
          f"{len({r['cid'] for r in B}):,} markets")
    base_rate = np.mean([r["y"] for r in B])
    print(f"  window-B favourite win-rate (take-all): {base_rate:.4f}\n")

    Xa = np.array([r["x"] for r in A], float)
    ya = np.array([r["y"] for r in A], float)
    Xb = np.array([r["x"] for r in B], float)

    clf = HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.06, max_leaf_nodes=15,
        min_samples_leaf=80, l2_regularization=1.0, random_state=SEED)
    clf.fit(Xa, ya)
    pw = clf.predict_proba(Xb)[:, 1]

    # the model's EV per share, at the price actually on offer
    ev = np.array([pw[i] - B[i]["p"] - fee(B[i]["p"], B[i]["niche"]) for i in range(len(B))])

    out = {"meta": {"train_rows": len(A), "test_rows": len(B),
                    "test_markets": len({r['cid'] for r in B}),
                    "base_winrate": float(base_rate), "features": FEATS}}

    W = 98
    print("=" * W)
    print("POLICY COMPARISON  (window B, OUT OF SAMPLE, market-clustered CIs, verified fees)")
    print("=" * W)
    print(f"{'policy':>34s} {'NET c/share':>12s} {'95% CI':>20s} {'p':>6s} "
          f"{'entries':>8s} {'mkts':>6s}")
    print("-" * W)

    res = {}

    def report(name, mask):
        sel = [(B[i]["cid"], B[i]["net"]) for i in range(len(B)) if mask[i]]
        if len(sel) < 20:
            print(f"{name:>34s}   -- too few entries --")
            return
        r = boot_by_market(sel)
        if not r:
            return
        print(f"{name:>34s} {r['mean']:>+12.4f} [{r['lo']:+.4f},{r['hi']:+.4f}] "
              f"{r['p']:>6.3f} {r['n_rows']:>8,} {r['n_markets']:>6,}")
        res[name] = r

    report("BLIND: take every favourite", np.ones(len(B), bool))
    for thr in (0.00, 0.01, 0.02, 0.03):
        report(f"MODEL: EV > {thr:+.2f}", ev > thr)
    # a naive persistence rule, to see if the model is really needed
    pers = np.array([r["x"][FEATS.index("persistence")] for r in B])
    ndip = np.array([r["x"][FEATS.index("n_dips")] for r in B])
    report("NAIVE: persistence > 30min", pers > 1800)
    report("NAIVE: no dips out of band", ndip == 0)
    report("NAIVE: persist>30m AND no dips", (pers > 1800) & (ndip == 0))

    out["policies"] = res

    # ---- does the model actually rank collapse risk? (AUC on the test window)
    from sklearn.metrics import roc_auc_score
    yb = np.array([r["y"] for r in B], float)
    auc = float(roc_auc_score(yb, pw))
    print(f"\n  model AUC on window B = {auc:.4f}   (0.5 = no skill)")
    out["auc"] = auc

    # calibration: does predicted win-prob beat the PRICE as an estimate of truth?
    pxs = np.array([r["p"] for r in B], float)
    bs_model = float(np.mean((pw - yb) ** 2))
    bs_price = float(np.mean((pxs - yb) ** 2))
    print(f"  Brier: model {bs_model:.5f}  vs  MARKET PRICE {bs_price:.5f}   "
          f"({'MODEL BEATS THE MARKET' if bs_model < bs_price else 'market wins'})")
    out["brier"] = {"model": bs_model, "price": bs_price}

    imp = sorted(zip(FEATS, clf.feature_importances_ if hasattr(clf, "feature_importances_")
                     else [0] * len(FEATS)), key=lambda x: -x[1])[:6] \
        if hasattr(clf, "feature_importances_") else []
    if imp:
        print("  top features: " + ", ".join(f"{k}" for k, _ in imp))

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(out, f, indent=2, default=float)
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
