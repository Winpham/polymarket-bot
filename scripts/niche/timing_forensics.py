#!/usr/bin/env python3
"""
IS THE ROSTER LOAD-BEARING, OR IS THE EDGE JUST *WHEN* IT BUYS?

surplus_decomp.py established two facts that together corner this question:

  1. In the 80-100c band the copy surplus (+2.62c) is NOT price composition. It is D(won) = +2.73c:
     the roster's favourites genuinely WIN MORE than blind favourites in the same markets.
  2. Match the blind print on same-market + same-outcome + same-price and the surplus is EXACTLY
     zero (D(won) = -0.0005). Degenerate -- as it must be, since won is a property of the outcome.

51,003 of 51,006 markets are BINARY. Prices sum to 1, so an >=80c print on the OTHER side cannot
exist at the same instant -- it can only exist at a DIFFERENT TIME (a lead change). Therefore:

    ==> The roster's ENTIRE win-rate edge is reachable only through WHEN it buys.

The blind leg loses because it buys favourites that were ahead at 85c and then COLLAPSED. The roster
buys later, once the favourite is real. If that is the whole story, then the roster is DECORATION and
a roster-free TIMING rule captures the same money with:
    - unlimited capacity (every market, not 7.8 signals/day)
    - no roster maintenance, no ranker, no window-A/B split
    - NO CROSS-VENUE IDENTITY PROBLEM -- it runs natively on the US book, which has no wallet history

That would be worth vastly more than the copy edge. This script decides it.

  TEST 3  time-matched blind  -- same market, same band, blind print within +/- tau of the roster's.
                                If D(won) -> 0, timing explains everything.
  TEST 4  descriptive         -- WHERE in a market's life does the roster buy, vs blind?
  TEST 5  roster-free POLICY  -- can a rule using ONLY decision-time-observable features
                                (price persistence, prints elapsed) match the roster's net?
                                Features are causal: nothing peeks at the future.

  ./timing_forensics.py --self-test
  ./timing_forensics.py
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
BATCH = 200
SEED = 20260714
LAG = 5
CACHE = "reports/niche/.timing_cache.pkl"

THETA = {"tennis": .05, "soccer": .05, "mlb": .05, "nba": .05, "nhl": .05, "ufc": .05,
         "esports": .05, "politics": .04, "crypto": .07, "weather": .05, "other": .05}
SPORTS = ("soccer", "mlb", "tennis", "esports", "nba", "nhl", "ufc")


def fee(p, niche):
    return THETA.get(niche, .05) * p * (1.0 - p)


def band(p):
    return min(int(p * 5), 4)


def psql(sql):
    o = subprocess.run(PG, input=GUARD + sql, capture_output=True, text=True)
    if o.returncode != 0:
        sys.exit("psql FAILED:\n" + o.stderr[:1200])
    return list(csv.DictReader(io.StringIO(o.stdout)))


def q_lit(xs):
    return ",".join("'" + str(x).replace("'", "''") + "'" for x in xs)


def boot(vals, n_boot=4000, seed=SEED):
    """Bootstrap the mean of per-market values."""
    a = np.array(vals, float)
    if len(a) < 20:
        return None
    rng = np.random.default_rng(seed)
    bs = a[rng.integers(0, len(a), (n_boot, len(a)))].mean(1)
    return {"mean": float(a.mean()), "lo": float(np.percentile(bs, 2.5)),
            "hi": float(np.percentile(bs, 97.5)), "p": float((bs <= 0).mean()), "n": len(a)}


# ---------------------------------------------------------------------------- self-test
def self_test():
    assert band(.85) == 4 and band(.79) == 3
    assert abs(fee(.9, "mlb") - .05 * .09) < 1e-12

    r = boot([0.03] * 100)
    assert r["mean"] == 0.03 and r["lo"] > 0 and r["p"] == 0.0

    # a null must NOT certify
    rng = np.random.default_rng(0)
    r2 = boot(list(rng.normal(0, .2, 500)))
    assert r2["lo"] < 0 < r2["hi"] and r2["p"] > .05

    # persistence feature is CAUSAL: it may only look backwards.
    # tape: price crosses 80c at t=100 and stays. At t=160 persistence must be 60s, never more.
    tape = [(0, .5), (100, .85), (130, .86), (160, .84)]
    assert _persistence(tape, 160) == 60.0
    assert _persistence(tape, 100) == 0.0
    # a dip below 80c RESETS it
    tape2 = [(0, .5), (100, .85), (130, .70), (150, .88), (200, .90)]
    assert _persistence(tape2, 200) == 50.0, "a dip below the band must reset persistence"
    print("self-test OK  (timing features are causal; no lookahead)")
    return 0


def _persistence(tape, t):
    """Seconds the price has been continuously >=0.80, as of time t. Backward-looking ONLY."""
    start = None
    for (ts, p) in tape:
        if ts > t:
            break
        if p >= 0.80:
            if start is None:
                start = ts
        else:
            start = None
    return 0.0 if start is None else float(t - start)


# ---------------------------------------------------------------------------- data
def load(roster_path, ranker):
    if os.path.exists(CACHE):
        print(f"loading cache {CACHE}")
        with open(CACHE, "rb") as f:
            return pickle.load(f)

    R = [r for r in json.load(open(roster_path)) if r["ranker"] == ranker][0]["roster"]
    wallets = [w["wallet"] for w in R]
    rosterset = set(wallets)
    wfilt = ("AND h.condition_id IN (SELECT condition_id FROM ("
             "  SELECT condition_id, MAX(ts) mts FROM harvest_wm GROUP BY 1) x "
             "  WHERE x.mts > (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY mts) "
             "                 FROM (SELECT condition_id, MAX(ts) mts FROM harvest_wm "
             "                       GROUP BY 1) y))")
    sigs = []
    for i in range(0, len(wallets), 100):
        sigs += psql(f"""
          WITH res AS (SELECT condition_id, outcome_index, BOOL_OR(outcome_won) won
                       FROM trader_fills WHERE resolved AND outcome_won IS NOT NULL GROUP BY 1,2),
          ok AS (SELECT condition_id, niche, n_trades FROM harvest_markets WHERE NOT truncated)
          SELECT h.condition_id, h.outcome_index, h.wallet,
                 EXTRACT(EPOCH FROM h.ts) t, h.price p, (r.won::int)::float8 won, ok.niche
          FROM harvest_fills h
          JOIN ok ON ok.condition_id=h.condition_id
          JOIN res r ON r.condition_id=h.condition_id AND r.outcome_index=h.outcome_index
          WHERE h.side='BUY' AND h.is_maker=false
            AND h.wallet IN ({q_lit(wallets[i:i+100])}) {wfilt};""")
    mkts = sorted({s["condition_id"] for s in sigs})
    print(f"{len(sigs):,} roster signals / {len(mkts):,} markets (window B)")

    takers, wonmap, niche_of, depth_of = defaultdict(list), {}, {}, {}
    for i in range(0, len(mkts), BATCH):
        ch = mkts[i:i + BATCH]
        for r in psql(f"""
              SELECT h.condition_id, h.outcome_index, h.wallet,
                     EXTRACT(EPOCH FROM h.ts) t, h.price p, m.niche, m.n_trades
              FROM harvest_fills h JOIN harvest_markets m USING (condition_id)
              WHERE h.side='BUY' AND h.is_maker=false
                AND h.condition_id IN ({q_lit(ch)});"""):
            takers[(r["condition_id"], r["outcome_index"])].append(
                (float(r["t"]), float(r["p"]), r["wallet"]))
            niche_of[r["condition_id"]] = r["niche"]
            depth_of[r["condition_id"]] = int(r["n_trades"])
        for r in psql(f"""
              SELECT condition_id, outcome_index, BOOL_OR(outcome_won)::int won
              FROM trader_fills WHERE resolved AND outcome_won IS NOT NULL
                AND condition_id IN ({q_lit(ch)}) GROUP BY 1,2;"""):
            wonmap[(r["condition_id"], r["outcome_index"])] = float(r["won"])
        sys.stdout.write(f"\r  tape {min(i+BATCH, len(mkts)):,}/{len(mkts):,}")
        sys.stdout.flush()
    for k in takers:
        takers[k].sort(key=lambda x: x[0])
    print(f"\n  {sum(len(v) for v in takers.values()):,} taker prints\n")
    D = (sigs, dict(takers), wonmap, niche_of, depth_of, rosterset)
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "wb") as f:
        pickle.dump(D, f)
    return D


# ---------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--roster", default="reports/niche/global_profit_floor20.json")
    ap.add_argument("--ranker", default="eb_shrunk")
    ap.add_argument("--out", default="reports/niche/timing_forensics.json")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test())

    sigs, takers, wonmap, niche_of, depth_of, rosterset = load(a.roster, a.ranker)
    out = {}

    # market clock, from the tape (descriptive use only)
    mkt_t0, mkt_t1 = {}, {}
    for (cid, oi), pr in takers.items():
        if not pr:
            continue
        mkt_t0[cid] = min(mkt_t0.get(cid, 1e18), pr[0][0])
        mkt_t1[cid] = max(mkt_t1.get(cid, 0), pr[-1][0])

    # ---- copy leg: the price we can really get
    copy_rows = []
    for s in sigs:
        cid, oi = s["condition_id"], s["outcome_index"]
        t0, w0, n = float(s["t"]), s["wallet"], s["niche"]
        px = next((p for (t, p, w) in takers.get((cid, oi), []) if t >= t0 + LAG and w != w0), None)
        tx = next((t for (t, p, w) in takers.get((cid, oi), []) if t >= t0 + LAG and w != w0), None)
        if px is None:
            continue
        dur = max(mkt_t1[cid] - mkt_t0[cid], 1.0)
        copy_rows.append({"cid": cid, "oi": oi, "niche": n, "band": band(px), "t": tx, "p": px,
                          "won": float(s["won"]), "net": float(s["won"]) - px - fee(px, n),
                          "life": (tx - mkt_t0[cid]) / dur,          # 0=open, 1=close
                          "ttr": mkt_t1[cid] - tx})                  # secs to last print
    blind_rows = []
    for (cid, oi), prints in takers.items():
        w = wonmap.get((cid, oi))
        if w is None:
            continue
        n = niche_of[cid]
        dur = max(mkt_t1[cid] - mkt_t0[cid], 1.0)
        for (t, p, wal) in prints:
            if wal in rosterset:
                continue
            blind_rows.append({"cid": cid, "oi": oi, "niche": n, "band": band(p), "t": t, "p": p,
                               "won": w, "net": w - p - fee(p, n),
                               "life": (t - mkt_t0[cid]) / dur, "ttr": mkt_t1[cid] - t})

    # ============================================================ TEST 3: TIME-MATCHED BLIND
    bl_by_mkt = defaultdict(list)
    for r in blind_rows:
        bl_by_mkt[r["cid"]].append(r)

    print("=" * 104)
    print("TEST 3 -- TIME-MATCHED BLIND   (same market, same band, blind print within +/- tau)")
    print("         If the roster's win-rate edge is really just WHEN it buys, D(won) -> 0 here.")
    print("=" * 104)
    print(f"{'cell':>22s} {'tau':>7s} {'SURPLUS':>9s} {'95% CI':>18s} {'p':>6s} | "
          f"{'D(won)':>8s} {'D(won) CI':>18s} {'mkts':>6s}")
    print("-" * 104)
    out["time_matched"] = {}
    for nm, sel in [("band 80-100c", lambda r: r["band"] == 4),
                    ("FAV 80-100 x SPORTS", lambda r: r["band"] == 4 and r["niche"] in SPORTS),
                    ("band 60-80c", lambda r: r["band"] == 3)]:
        # tau=None is the UNMATCHED control -- reproduces the headline
        for tau in (None, 7200, 1800, 300):
            pm = defaultdict(lambda: [[], []])
            for r in copy_rows:
                if not sel(r):
                    continue
                cand = [b for b in bl_by_mkt.get(r["cid"], [])
                        if sel(b) and (tau is None or abs(b["t"] - r["t"]) <= tau)]
                if not cand:
                    continue
                pm[r["cid"]][0].append(r)
                pm[r["cid"]][1].extend(cand)
            dn, dw = [], []
            for m, (A, B) in pm.items():
                if not A or not B:
                    continue
                dn.append(np.mean([x["net"] for x in A]) - np.mean([x["net"] for x in B]))
                dw.append(np.mean([x["won"] for x in A]) - np.mean([x["won"] for x in B]))
            rn, rw = boot(dn), boot(dw)
            if not rn:
                continue
            lab = "UNMATCHED" if tau is None else f"{tau//60}min"
            print(f"{nm:>22s} {lab:>7s} {rn['mean']:>+9.4f} [{rn['lo']:+.4f},{rn['hi']:+.4f}] "
                  f"{rn['p']:>6.3f} | {rw['mean']:>+8.4f} [{rw['lo']:+.4f},{rw['hi']:+.4f}] "
                  f"{rn['n']:>6,}")
            out["time_matched"][f"{nm} tau={lab}"] = {"net": rn, "won": rw}
        print()

    # ============================================================ TEST 4: WHERE DO THEY BUY?
    print("=" * 104)
    print("TEST 4 -- WHERE IN A MARKET'S LIFE DOES EACH LEG BUY?   (band 80-100c)")
    print("=" * 104)
    cf = [r for r in copy_rows if r["band"] == 4]
    bf = [r for r in blind_rows if r["band"] == 4]
    for lab, rows in (("COPY ", cf), ("BLIND", bf)):
        life = np.array([r["life"] for r in rows])
        ttr = np.array([r["ttr"] for r in rows]) / 3600.0
        won = np.array([r["won"] for r in rows])
        print(f"  {lab}  n={len(rows):>7,}  life-fraction  p25={np.percentile(life,25):.2f} "
              f"med={np.median(life):.2f} p75={np.percentile(life,75):.2f}   "
              f"hrs-to-close med={np.median(ttr):>6.1f}   WIN-RATE={won.mean():.4f}")
    out["where"] = {"copy_life_med": float(np.median([r["life"] for r in cf])),
                    "blind_life_med": float(np.median([r["life"] for r in bf])),
                    "copy_winrate": float(np.mean([r["won"] for r in cf])),
                    "blind_winrate": float(np.mean([r["won"] for r in bf]))}

    # win-rate of a BLIND favourite buy, by where in the market's life it happens
    print("\n  BLIND favourite win-rate BY LIFE-FRACTION (this is the mechanism, if it is one):")
    print(f"    {'life bucket':>14s} {'n':>9s} {'win-rate':>9s} {'mean p':>8s} {'NET/share':>10s}")
    out["blind_by_life"] = {}
    for lo, hi in [(0, .2), (.2, .4), (.4, .6), (.6, .8), (.8, 1.01)]:
        sub = [r for r in bf if lo <= r["life"] < hi]
        if len(sub) < 50:
            continue
        wr = float(np.mean([r["won"] for r in sub]))
        mp = float(np.mean([r["p"] for r in sub]))
        nt = float(np.mean([r["net"] for r in sub]))
        print(f"    {f'{lo:.1f}-{hi:.1f}':>14s} {len(sub):>9,} {wr:>9.4f} {mp:>8.4f} {nt:>+10.4f}")
        out["blind_by_life"][f"{lo:.1f}-{hi:.1f}"] = {"n": len(sub), "winrate": wr,
                                                      "mean_p": mp, "net": nt}
    print()

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(out, f, indent=2, default=float)
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
