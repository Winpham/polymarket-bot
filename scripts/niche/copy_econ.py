#!/usr/bin/env python3
"""
THE REAL FOLLOWER TAX -- measured from the tape, not assumed.

Every result so far subtracted a 1.3c follower tax taken from an old audit. We hold the
complete market tape, so the tax is MEASURABLE: after a roster wallet takes a fill at price p
at time t, the SUBSEQUENT FILLS IN THAT MARKET are exactly the prices we could have got.

    real_tax(D) = (mean price of fills in (t, t+D] on the same (market, outcome),
                   from OTHER wallets) - p
    edge(D)     = won - that_price          <- what WE would actually have earned

If the tax is ~1.3c the candidate edge stands. If it is 3-4c the edge dies (K1 -> STOP).
This also yields the EDGE-DECAY CURVE, which sets an executor's latency budget.

*** OPERATIONAL NOTE -- READ BEFORE EDITING THE SQL ***
The first version of this did five LEFT JOINs of the full fill tape against the signal set.
That went cartesian, OOM-ed the postgres backend, and took the LIVE bot's database down.
Never again:
  - the tape is streamed MARKET-BY-MARKET in bounded batches; nothing is joined fill-to-fill
  - every session sets a conservative work_mem and a statement_timeout, so a bad query dies
    instead of killing the server
  - lag windows are computed in numpy, not SQL
Postgres here is a PRODUCTION database. Analysis must never be able to crash it.
"""
import argparse
import csv
import io
import json
import os
import subprocess
import sys
from collections import defaultdict

import numpy as np

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]

# Guards: this DB serves the live bot. A runaway analysis query must die, not the server.
GUARD = "SET work_mem='64MB'; SET statement_timeout='180s'; "

FEES = 0.03
LAGS = [60, 300, 900, 3600, 21600]       # 1m 5m 15m 1h 6h
BATCH = 300                              # markets per round-trip
SEED = 20260714


def psql(sql):
    out = subprocess.run(PG, input=GUARD + sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr[:800])
    return list(csv.DictReader(io.StringIO(out.stdout)))


def cluster_boot(recs, n_boot=3000, seed=SEED):
    if not recs:
        return 0.0, 0.0, 0.0, 0
    by = defaultdict(list)
    for m, v in recs:
        by[m].append(v)
    k = list(by)
    s = np.array([sum(by[x]) for x in k], float)
    n = np.array([len(by[x]) for x in k], float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(k), (n_boot, len(k)))
    mu = s[idx].sum(1) / np.maximum(n[idx].sum(1), 1)
    return (float(s.sum() / n.sum()), float(np.percentile(mu, 2.5)),
            float(np.percentile(mu, 97.5)), len(k))


def q_lit(xs):
    return ",".join("'" + str(x).replace("'", "''") + "'" for x in xs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--roster", default="reports/niche/global_profit_floor20.json")
    ap.add_argument("--ranker", default="eb_shrunk")
    ap.add_argument("--out", default="reports/niche")
    ap.add_argument("--window", choices=["all", "B"], default="B",
                    help="B = OUT-OF-SAMPLE only. The roster was SELECTED on window A, so "
                         "A signals are contaminated by that selection and would inflate "
                         "the edge. Default B.")
    a = ap.parse_args()

    R = [r for r in json.load(open(a.roster)) if r["ranker"] == a.ranker][0]["roster"]
    wallets = [w["wallet"] for w in R]
    wl = q_lit(wallets)
    print(f"roster: top-{len(wallets)} by {a.ranker}")

    # 1. the SIGNALS: roster wallets crossing the spread to BUY (what we would copy)
    # window B = the later half of markets, disjoint from the window the roster was fit on
    wfilt = ("" if a.window == "all" else
             "AND h.condition_id IN (SELECT condition_id FROM ("
             "  SELECT condition_id, MAX(ts) mts FROM harvest_wm GROUP BY 1) x "
             "  WHERE x.mts > (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY mts) "
             "                 FROM (SELECT condition_id, MAX(ts) mts FROM harvest_wm "
             "                       GROUP BY 1) y))")
    sigs = psql(f"""
      WITH res AS (SELECT condition_id, outcome_index, BOOL_OR(outcome_won) won
                   FROM trader_fills WHERE resolved AND outcome_won IS NOT NULL GROUP BY 1,2),
      ok AS (SELECT condition_id FROM harvest_markets WHERE NOT truncated)
      SELECT h.condition_id, h.outcome_index, h.wallet,
             EXTRACT(EPOCH FROM h.ts) t, h.price p, h.size_usd sz,
             (r.won::int)::float8 won
      FROM harvest_fills h
      JOIN ok USING (condition_id)
      JOIN res r ON r.condition_id=h.condition_id AND r.outcome_index=h.outcome_index
      WHERE h.side='BUY' AND h.is_maker=false AND h.wallet IN ({wl})
        {wfilt};
    """)
    print(f"{len(sigs):,} taker-BUY signals from the roster")

    by_mkt = defaultdict(list)
    for s in sigs:
        by_mkt[s["condition_id"]].append(s)
    mkts = list(by_mkt)
    print(f"across {len(mkts):,} markets -- streaming the tape in batches of {BATCH}\n")

    # 2. the TAPE for those markets only, streamed in bounded batches (never a fill-to-fill join)
    tape = defaultdict(list)          # (cid, oidx) -> [(t, price, wallet)]
    for i in range(0, len(mkts), BATCH):
        chunk = mkts[i:i + BATCH]
        for r in psql(f"""
              SELECT condition_id, outcome_index, wallet,
                     EXTRACT(EPOCH FROM ts) t, price p
              FROM harvest_fills
              WHERE side='BUY' AND condition_id IN ({q_lit(chunk)});"""):
            tape[(r["condition_id"], r["outcome_index"])].append(
                (float(r["t"]), float(r["p"]), r["wallet"]))
    for k in tape:
        tape[k].sort(key=lambda x: x[0])
    print(f"tape loaded: {sum(len(v) for v in tape.values()):,} fills\n")

    # 3. for each signal, the price WE could have got at t+D (other wallets' fills only)
    own = [(s["condition_id"], float(s["won"]) - float(s["p"])) for s in sigs]
    m0, lo0, hi0, _ = cluster_boot(own)
    print(f"{'entry':>13s} {'real tax':>10s} {'gross edge':>12s} {'95% CI':>21s} "
          f"{'net of 3% fees':>15s}   n")
    print("-" * 88)
    print(f"{'THEIR price':>13s} {'--':>10s} {m0:+12.4f} [{lo0:+.4f},{hi0:+.4f}] "
          f"{m0 - FEES:+15.4f}   {len(own):,}")

    out = {"their_price": {"edge": m0, "ci": [lo0, hi0], "n": len(own)}, "lags": {}}
    for L in LAGS:
        taxes, edges = [], []
        for s in sigs:
            key = (s["condition_id"], s["outcome_index"])
            t0, p0, w0 = float(s["t"]), float(s["p"]), s["wallet"]
            fol = [px for (t, px, w) in tape.get(key, [])
                   if t0 < t <= t0 + L and w != w0]        # SELF-EXCLUDED
            if not fol:
                continue                                    # no print => we could not have traded
            our_px = float(np.mean(fol))
            taxes.append((s["condition_id"], our_px - p0))
            edges.append((s["condition_id"], float(s["won"]) - our_px))
        if len(edges) < 50:
            print(f"{L//60:>11d}m   (only {len(edges)} signals had a follow-on print)")
            continue
        t_m, _, _, _ = cluster_boot(taxes)
        e_m, e_lo, e_hi, nclu = cluster_boot(edges)
        lab = f"{L//60}m" if L < 3600 else f"{L//3600}h"
        print(f"{lab:>13s} {t_m:+10.4f} {e_m:+12.4f} [{e_lo:+.4f},{e_hi:+.4f}] "
              f"{e_m - FEES:+15.4f}   {len(edges):,}")
        out["lags"][L] = {"tax": t_m, "edge": e_m, "ci": [e_lo, e_hi],
                          "net": e_m - FEES, "n": len(edges), "n_markets": nclu}

    print("\nK1: a live executor can realistically act within ~1-5 min. If net <= 0 there,")
    print("    the candidate is DEAD regardless of how good their own edge looks.")
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "copy_econ.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(f"wrote {a.out}/copy_econ.json")


if __name__ == "__main__":
    main()
