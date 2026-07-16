#!/usr/bin/env python3
"""
TEST 4 (subpopulation): does copying a CLEANER ROSTER produce lambda > 0?

The collapse cache already IS the MM-screened directional taker cohort (is_maker=false BUY,
>=80c) at the aggregate, and its lambda is 0.000. This asks the narrower question the brief
poses: restrict the copy signal to the churn/MM-screened DIRECTIONAL roster wallets (the ones
roster.py surfaced with maker_frac<0.1 -- the cleanest cohort the persistence machinery could
find) and to the CLV-persistent slice, then measure the forward-CLV lambda the same way.

  entry   = the roster wallet's own BUY taker fill price (>=80c)
  close   = the market's closing line = last non-degenerate print of the tape (in [.02,.98])
            -- the repo's canonical CLV closing line (rankers.py), forward of typical entries
  surplus = won - entry            CLV = close - entry           lambda = mean_CLV / mean_surplus
  clustered on MARKET (the inference unit); window-B (OOS) split at the roster-selection cut.

If copying the clean roster carried information the market later confirms, CLV lower-bound > 0.

  ./intl_roster_lambda.py --self-test
  ./intl_roster_lambda.py
"""
import argparse
import csv
import io
import os
import pickle
import subprocess
import sys
from collections import defaultdict

import numpy as np

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "-v", "ON_ERROR_STOP=1", "--csv", "-q"]
GUARD = "SET work_mem='128MB'; SET statement_timeout='600s'; SET max_parallel_workers_per_gather=4; "
SEED = 20260714
SPLIT_EPOCH = 1783311884            # median last-harvest ts (harvest_wm), = collapse A/B boundary
GUARD_LO, GUARD_HI = 0.02, 0.98
BAND_LO = 0.80
THETA = {"tennis": .05, "soccer": .05, "mlb": .05, "nba": .05, "nhl": .05, "ufc": .05,
         "esports": .05, "politics": .04, "crypto": .07, "weather": .05, "other": .05}


def fee(p, n):
    return THETA.get(n, .05) * p * (1 - p)


def psql(sql):
    o = subprocess.run(PG, input=GUARD + sql, capture_output=True, text=True)
    if o.returncode != 0:
        sys.exit("psql FAILED:\n" + o.stderr[:1500])
    return list(csv.DictReader(io.StringIO(o.stdout)))


def q_lit(xs):
    return ",".join("'" + str(x).replace("'", "''") + "'" for x in xs)


def lam_ci(pairs, seed=SEED, n_boot=4000):
    """pairs = [(cid, surplus, clv)] -> market-clustered lambda + CLV CI + p(CLV<=0)."""
    by = defaultdict(lambda: {"s": [], "c": []})
    for cid, s, c in pairs:
        by[cid]["s"].append(s)
        by[cid]["c"].append(c)
    mk = list(by)
    if len(mk) < 20:
        return None
    s_m = np.array([np.mean(by[m]["s"]) for m in mk])
    c_m = np.array([np.mean(by[m]["c"]) for m in mk])
    mean_s, mean_c = float(s_m.mean()), float(c_m.mean())
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(mk), (n_boot, len(mk)))
    c_bs = c_m[idx].mean(1)
    s_bs = s_m[idx].mean(1)
    lam_bs = np.clip(c_bs / np.maximum(s_bs, 1e-9), 0, 1)
    lam = max(0.0, min(1.0, mean_c / mean_s)) if mean_s > 0 else float("nan")
    return {"n_markets": len(mk), "n_fills": len(pairs), "mean_surplus": mean_s, "mean_clv": mean_c,
            "clv_lo": float(np.percentile(c_bs, 2.5)), "clv_hi": float(np.percentile(c_bs, 97.5)),
            "clv_p": float((c_bs <= 0).mean()), "lam": lam,
            "lam_lo": float(np.percentile(lam_bs, 2.5)), "lam_hi": float(np.percentile(lam_bs, 97.5))}


def report(tag, r):
    if not r:
        print(f"{tag:>26s}   -- too few markets --")
        return
    print(f"{tag:>26s}  mk={r['n_markets']:>5d} fills={r['n_fills']:>6d}  "
          f"surplus={r['mean_surplus']*100:+.2f}c  CLV={r['mean_clv']*100:+.2f}c "
          f"[{r['clv_lo']*100:+.2f},{r['clv_hi']*100:+.2f}] p(CLV<=0)={r['clv_p']:.3f}  "
          f"lam={r['lam']:.3f} [{r['lam_lo']:.3f},{r['lam_hi']:.3f}]  "
          f">> {'INFO (CLV LB>0)' if r['clv_lo'] > 0 else 'variance (CLV CI incl 0)'}")


def self_test():
    # closing-line lambda: entry .85, close .95, won 1 -> surplus .15, clv .10, lambda ~ .667
    r = lam_ci([("m%d" % i, 0.15, 0.10) for i in range(30)])
    assert abs(r["lam"] - 0.6667) < 1e-3, r["lam"]
    assert r["clv_lo"] > 0
    # pure variance: clv 0 -> lambda 0, clv CI includes 0
    r2 = lam_ci([(f"m{i}", 0.15, 0.0) for i in range(30)])
    assert r2["lam"] == 0.0 and r2["clv_lo"] <= 0
    print("self-test OK (closing-line lambda + market clustering)")
    return 0


def build_pairs(wallets):
    """lambda clusters on MARKET and uses per-market means, so we aggregate the roster's fills to
    per-(market,outcome) mean entry price directly in SQL (no per-fill transfer), then join the
    forward closing line + settled outcome. entry_b = mean entry among window-B (OOS) fills only."""
    wl = list(wallets)
    # per (cid, oi): mean entry among roster BUY taker >=80c fills, all-window and window-B
    agg = {}
    CH = 50
    for i in range(0, len(wl), CH):
        ch = wl[i:i + CH]
        for r in psql(f"""
            SELECT condition_id, outcome_index,
                   AVG(price) me_all,
                   AVG(price) FILTER (WHERE ts > to_timestamp({SPLIT_EPOCH})) me_b,
                   COUNT(*) n_all,
                   COUNT(*) FILTER (WHERE ts > to_timestamp({SPLIT_EPOCH})) n_b
            FROM harvest_fills
            WHERE side='BUY' AND is_maker=false AND price >= {BAND_LO}
              AND wallet IN ({q_lit(ch)})
            GROUP BY 1,2;"""):
            k = (r["condition_id"], r["outcome_index"])
            me_all, na = float(r["me_all"]), int(r["n_all"])
            me_b = float(r["me_b"]) if r["me_b"] not in (None, "") else None
            nb = int(r["n_b"]) if r["n_b"] not in (None, "") else 0
            if k in agg:                       # merge same (cid,oi) across wallet chunks
                p = agg[k]
                tot = p["n_all"] + na
                p["me_all"] = (p["me_all"] * p["n_all"] + me_all * na) / tot
                p["n_all"] = tot
                if me_b is not None:
                    tb = p["n_b"] + nb
                    p["me_b"] = ((p["me_b"] or 0) * p["n_b"] + me_b * nb) / tb if tb else None
                    p["n_b"] = tb
            else:
                agg[k] = {"me_all": me_all, "n_all": na, "me_b": me_b, "n_b": nb}
        sys.stdout.write(f"\r  aggregated wallets {min(i+CH,len(wl))}/{len(wl)}  "
                         f"({len(agg):,} market-outcomes)")
        sys.stdout.flush()
    print()
    cids = sorted({k[0] for k in agg})
    print(f"  {len(cids):,} distinct markets touched by the roster")
    # closing line + outcome per (cid, oi)
    close, won = {}, {}
    CH2 = 150
    for i in range(0, len(cids), CH2):
        ch = cids[i:i + CH2]
        for r in psql(f"""
            SELECT condition_id, outcome_index,
                   (ARRAY_AGG(price ORDER BY ts DESC)
                    FILTER (WHERE price BETWEEN {GUARD_LO} AND {GUARD_HI}))[1] cl
            FROM harvest_fills WHERE condition_id IN ({q_lit(ch)})
            GROUP BY 1,2;"""):
            if r["cl"] not in (None, ""):
                close[(r["condition_id"], r["outcome_index"])] = float(r["cl"])
        for r in psql(f"""
            SELECT condition_id, outcome_index, BOOL_OR(outcome_won)::int w
            FROM trader_fills WHERE resolved AND outcome_won IS NOT NULL
              AND condition_id IN ({q_lit(ch)}) GROUP BY 1,2;"""):
            won[(r["condition_id"], r["outcome_index"])] = float(r["w"])
        sys.stdout.write(f"\r  closing lines {min(i+CH2,len(cids)):,}/{len(cids):,}")
        sys.stdout.flush()
    print()
    allp, oosp = [], []
    for k, p in agg.items():
        if k not in won or k not in close:
            continue
        cid = k[0]
        cl, w = close[k], won[k]
        allp.append((cid, w - p["me_all"], cl - p["me_all"]))
        if p["me_b"] is not None and p["n_b"] > 0:
            oosp.append((cid, w - p["me_b"], cl - p["me_b"]))
    return allp, oosp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test())
    wl = pickle.load(open("/tmp/roster_wallets.pkl", "rb"))
    print(f"copying {len(wl)} MM-screened directional roster wallets (maker_frac<0.1)\n")
    allp, oosp = build_pairs(wl)
    print("\n" + "=" * 118)
    print("LAMBDA — copying the cleaner roster (forward closing-line CLV, market-clustered)")
    print("=" * 118)
    report("ALL fills", lam_ci(allp))
    report("OOS (window B only)", lam_ci(oosp))


if __name__ == "__main__":
    sys.exit(main())
