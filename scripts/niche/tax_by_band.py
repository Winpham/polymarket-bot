#!/usr/bin/env python3
"""
WHAT THE FOLLOWER TAX IS MADE OF -- and why it CANNOT REACH THE FAVOURITE BAND.

The headline tax (4-5c) was measured POOLED across every price. Pooling hid the mechanism.
favband_forensics found the copy net in the 80-100c band is FLAT across lags (2s: +2.87%,
30s: +3.44%, 5m: +2.72%) -- it does not decay. A tax that grows with lag CANNOT be flat in a
cell. So the tax is not a constant of the strategy. It is a function of WHERE IN THE BOOK you are.

THE HYPOTHESIS: the tax is BOUNDED BY THE DISTANCE TO THE PRICE BOUNDARY.
A price at 0.50 can run 5c against a follower in either direction -- there is room. A price at
0.95 has only 5c of headroom before it hits 1.00 and stops. Information that would move a mid-book
price 6c can only move a 95c price 5c, and usually far less, because the move is bounded by
(1 - p). So:

    tax(p)  ~  k * (1 - p)      for a BUY

If that holds, the favourite band is STRUCTURALLY TAX-IMMUNE -- not by luck, but by arithmetic --
and the "copy-trading is dead" verdict was an artifact of POOLING a cost that lives in the middle
of the book across a strategy that lives at the edge of it.

We test it three ways, because a curve that merely LOOKS like the bound is not the bound:
  A. tax by entry band, with the headroom (1-p) printed beside it
  B. the tax as a FRACTION OF HEADROOM, tax/(1-p) -- if the bound is the mechanism, this
     RATIO should be roughly FLAT across bands. A flat ratio is the signature; a rising raw tax
     with a flat ratio means the boundary, not the information, is doing the work.
  C. the SYMMETRIC control: the same test on SELL prints. If the bound is real, a SELL's tax must
     scale with p (its headroom is DOWNWARD, toward 0), i.e. the mirror image. If BUY and SELL
     both scale with (1-p), it is not a boundary effect at all -- it is something about buying.

Plus ROSTER ROBUSTNESS: the whole favourite-band result rests on one roster (eb_shrunk, floor 20).
If it only works for that one cut it is a scan artifact. Re-run the cell for every ranker x floor
we have on disk.

  ./tax_by_band.py --self-test
  ./tax_by_band.py
"""
import argparse
import csv
import glob
import io
import json
import os
import subprocess
import sys
from collections import defaultdict

import numpy as np

# -v ON_ERROR_STOP=1 IS LOAD-BEARING. Without it psql EXITS 0 ON A FAILED QUERY and hands back an
# empty CSV -- so a broken query silently becomes "0 signals" and the script cheerfully reports a
# null result. The helper inherited from copy_econ.py had this hole; a 1,109-wallet IN-list blew
# /dev/shm and this script reported "0 BUY / 0 SELL" instead of crashing. Never trust rc alone.
PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q", "-v", "ON_ERROR_STOP=1"]
# max_parallel_workers_per_gather=0: the container's /dev/shm is the Docker default 64MB, and a
# parallel scan over the 15GB tape asks for ~50MB of shared memory per gather. This DB serves the
# LIVE bot (a disk-exhaustion outage already killed it once) -- so we go single-threaded rather
# than anywhere near that ceiling. Slower, and incapable of taking production down.
GUARD = ("SET work_mem='64MB'; SET statement_timeout='240s'; "
         "SET max_parallel_workers_per_gather=0; ")
BATCH = 250
WCHUNK = 150                  # wallets per IN-list -- keeps the planner off the parallel path
SEED = 20260714
LAG = 5
MIN_MKTS = 40                 # refuse to report a cell thinner than this (esports/mlb n=22/28 burned us)

REAL_FEE_RATE = {"tennis": 0.03, "soccer": 0.03, "mlb": 0.03, "nba": 0.03, "nhl": 0.03,
                 "ufc": 0.03, "esports": 0.03, "politics": 0.04, "crypto": 0.07}
DEFAULT_FEE_RATE = 0.05
BANDS = [(0.0, .2), (.2, .4), (.4, .6), (.6, .8), (.8, .9), (.9, 1.01)]
BANDL = ["0-20c", "20-40c", "40-60c", "60-80c", "80-90c", "90-100c"]


def real_fee(p, n):
    return REAL_FEE_RATE.get(n, DEFAULT_FEE_RATE) * p * (1.0 - p)


def bandix(p):
    for i, (lo, hi) in enumerate(BANDS):
        if lo <= p < hi:
            return i
    return len(BANDS) - 1


def psql(sql):
    o = subprocess.run(PG, input=GUARD + sql, capture_output=True, text=True)
    if o.returncode != 0:
        sys.exit("psql failed:\n" + o.stderr[:800])
    return list(csv.DictReader(io.StringIO(o.stdout)))


def q_lit(xs):
    return ",".join("'" + str(x).replace("'", "''") + "'" for x in xs)


def boot(rows, n_boot=3000, seed=SEED, min_mkts=MIN_MKTS):
    if not rows:
        return None
    by = defaultdict(list)
    for m, v in rows:
        by[m].append(v)
    k = list(by)
    if len(k) < min_mkts:
        return None
    s = np.array([sum(by[x]) for x in k], float)
    n = np.array([len(by[x]) for x in k], float)
    rng = np.random.default_rng(seed)
    i = rng.integers(0, len(k), (n_boot, len(k)))
    mu = s[i].sum(1) / np.maximum(n[i].sum(1), 1)
    return {"mean": float(s.sum() / n.sum()), "lo": float(np.percentile(mu, 2.5)),
            "hi": float(np.percentile(mu, 97.5)), "p": float((mu <= 0).mean()),
            "n": len(rows), "n_markets": len(k)}


def self_test():
    assert bandix(0.0) == 0 and bandix(0.85) == 4 and bandix(0.95) == 5 and bandix(1.0) == 5
    b = boot([(f"m{i}", 0.03) for i in range(60)])
    assert abs(b["mean"] - 0.03) < 1e-9
    assert boot([(f"m{i}", 0.03) for i in range(10)]) is None      # thin cell -> refuse
    print("self-test OK")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--out", default="reports/niche/tax_by_band.json")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test())

    rosters = {}
    for f in sorted(glob.glob("reports/niche/global_profit_floor*.json")):
        floor = os.path.basename(f).replace("global_profit_floor", "").replace(".json", "")
        for e in json.load(open(f)):
            rosters[(e["ranker"], floor)] = [w["wallet"] for w in e["roster"]]
    print(f"{len(rosters)} rosters on disk (ranker x floor)\n")

    MAIN = ("eb_shrunk", "20")
    wallets = rosters[MAIN]
    allw = sorted({w for ws in rosters.values() for w in ws})

    wfilt = ("AND h.condition_id IN (SELECT condition_id FROM ("
             "  SELECT condition_id, MAX(ts) mts FROM harvest_wm GROUP BY 1) x "
             "  WHERE x.mts > (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY mts) "
             "                 FROM (SELECT condition_id, MAX(ts) mts FROM harvest_wm "
             "                       GROUP BY 1) y))")

    # every roster's signals (BUY and SELL -- C needs the mirror), in WALLET CHUNKS so the planner
    # never goes parallel on the 15GB tape
    sigs = []
    for i in range(0, len(allw), WCHUNK):
        sigs += psql(f"""
          WITH res AS (SELECT condition_id, outcome_index, BOOL_OR(outcome_won) won
                       FROM trader_fills WHERE resolved AND outcome_won IS NOT NULL GROUP BY 1,2),
          ok AS (SELECT condition_id, niche FROM harvest_markets WHERE NOT truncated)
          SELECT h.condition_id, h.outcome_index, h.wallet, h.side,
                 EXTRACT(EPOCH FROM h.ts) t, h.price p, (r.won::int)::float8 won, ok.niche
          FROM harvest_fills h
          JOIN ok ON ok.condition_id=h.condition_id
          JOIN res r ON r.condition_id=h.condition_id AND r.outcome_index=h.outcome_index
          WHERE h.is_maker=false AND h.wallet IN ({q_lit(allw[i:i+WCHUNK])}) {wfilt};
        """)
        sys.stdout.write(f"\r  signals: {min(i+WCHUNK, len(allw))}/{len(allw)} wallets")
        sys.stdout.flush()
    print()
    buys = [s for s in sigs if s["side"] == "BUY"]
    sells = [s for s in sigs if s["side"] == "SELL"]
    mkts = sorted({s["condition_id"] for s in sigs})
    print(f"{len(buys):,} BUY / {len(sells):,} SELL signals across {len(mkts):,} markets\n")

    tk_buy, tk_sell = defaultdict(list), defaultdict(list)
    for i in range(0, len(mkts), BATCH):
        for r in psql(f"""
              SELECT condition_id, outcome_index, wallet, side,
                     EXTRACT(EPOCH FROM ts) t, price p
              FROM harvest_fills
              WHERE is_maker=false AND condition_id IN ({q_lit(mkts[i:i+BATCH])});"""):
            k = (r["condition_id"], r["outcome_index"])
            (tk_buy if r["side"] == "BUY" else tk_sell)[k].append(
                (float(r["t"]), float(r["p"]), r["wallet"]))
        sys.stdout.write(f"\r  {min(i+BATCH, len(mkts)):,}/{len(mkts):,}")
        sys.stdout.flush()
    for d in (tk_buy, tk_sell):
        for k in d:
            d[k].sort(key=lambda x: x[0])
    print("\n")

    def follow(tape, s, lag=LAG):
        t0, w0 = float(s["t"]), s["wallet"]
        return next((p for (t, p, w) in tape.get((s["condition_id"], s["outcome_index"]), [])
                     if t >= t0 + lag and w != w0), None)

    out = {}
    main_set = set(wallets)

    # ================================================== A + B: tax by band, and tax / headroom
    print("=" * 100)
    print("A+B  THE TAX BY BAND -- and the tax as a FRACTION OF THE HEADROOM (1-p)")
    print("=" * 100)
    print(f"{'entry band':>12s} {'headroom':>9s} {'TAX':>8s} {'95% CI':>19s} "
          f"{'TAX/HEADROOM':>13s} {'copy net':>9s} {'net LB':>8s} {'mkts':>6s}")
    print("-" * 100)
    out["by_band"] = {}
    # BAND ON p0 = THEIR ENTRY PRICE, never on the price we end up paying. Banding on the
    # EXECUTION price conditions on the move having already happened -- it sorts the biggest
    # up-moves into the top band and manufactures a huge "tax" there (the first cut of this
    # printed tax/headroom = 4.27 at 90-100c, which is not a finding, it is the bug).
    # p0 is also what a copier actually observes at decision time.
    for bi in range(len(BANDS)):
        tax, net, head = [], [], []
        for s in buys:
            if s["wallet"] not in main_set:
                continue
            p0 = float(s["p"])
            if bandix(p0) != bi:
                continue
            px = follow(tk_buy, s)
            if px is None:
                continue
            cid, n = s["condition_id"], s["niche"]
            tax.append((cid, px - p0))
            net.append((cid, float(s["won"]) - px - real_fee(px, n)))
            head.append(1.0 - p0)
        bt, bn = boot(tax), boot(net)
        if not bt:
            continue
        hm = float(np.mean(head))
        ratio = bt["mean"] / hm if hm > 0 else float("nan")
        star = "  <<<" if bn and bn["lo"] > 0 else ""
        print(f"{BANDL[bi]:>12s} {hm:>9.3f} {bt['mean']:>+8.4f} "
              f"[{bt['lo']:+.4f},{bt['hi']:+.4f}] {ratio:>13.3f} "
              f"{bn['mean']:>+9.4f} {bn['lo']:>+8.4f} {bt['n_markets']:>6,}{star}")
        out["by_band"][BANDL[bi]] = {"tax": bt, "net": bn, "headroom": hm, "ratio": ratio}
    print("\n  A ROUGHLY FLAT 'TAX/HEADROOM' COLUMN IS THE SIGNATURE: the tax is not a constant")
    print("  cost of following -- it is a FIXED FRACTION OF THE ROOM THE PRICE HAS LEFT TO MOVE.")
    print("  At 90-100c there is almost no room, so there is almost no tax. Structural, not luck.\n")

    # ================================================== C: the SELL mirror
    print("=" * 100)
    print("C  THE MIRROR TEST -- a SELL's headroom runs DOWN (toward 0), so its tax must scale with p")
    print("=" * 100)
    print(f"{'entry band':>12s} {'headroom(p)':>12s} {'SELL tax':>9s} {'95% CI':>19s} "
          f"{'TAX/HEADROOM':>13s} {'mkts':>6s}")
    print("-" * 100)
    out["sell_mirror"] = {}
    for bi in range(len(BANDS)):
        tax, head = [], []
        for s in sells:
            if s["wallet"] not in main_set:
                continue
            p0 = float(s["p"])
            if bandix(p0) != bi:          # band on THEIR price, same reason as above
                continue
            px = follow(tk_sell, s)
            if px is None:
                continue
            # a SELLER is hurt when the price FALLS: their tax is (their price - our price)
            tax.append((s["condition_id"], p0 - px))
            head.append(p0)               # a seller's headroom runs DOWN, toward 0: it is p
        bt = boot(tax)
        if not bt:
            continue
        hm = float(np.mean(head))
        print(f"{BANDL[bi]:>12s} {hm:>12.3f} {bt['mean']:>+9.4f} "
              f"[{bt['lo']:+.4f},{bt['hi']:+.4f}] {bt['mean']/hm if hm > 0 else 0:>13.3f} "
              f"{bt['n_markets']:>6,}")
        out["sell_mirror"][BANDL[bi]] = {"tax": bt, "headroom": hm}
    print("\n  If a SELL's tax scales with p while a BUY's scales with (1-p), the BOUNDARY is doing")
    print("  the work -- the tax is the price's room to run, not a cost of being second.\n")

    # ================================================== ROSTER ROBUSTNESS
    print("=" * 100)
    print("ROSTER ROBUSTNESS -- does the 80-100c cell survive EVERY ranker x floor, or just ours?")
    print("=" * 100)
    print(f"{'ranker':>18s} {'floor':>6s} {'copy net @80-100c':>18s} {'95% CI':>20s} "
          f"{'p':>7s} {'mkts':>6s}")
    print("-" * 100)
    out["robustness"] = {}
    for (rk, fl), ws in sorted(rosters.items()):
        wset = set(ws)
        rows = []
        for s in buys:
            if s["wallet"] not in wset:
                continue
            px = follow(tk_buy, s)
            if px is None or px < 0.80:
                continue
            rows.append((s["condition_id"],
                         float(s["won"]) - px - real_fee(px, s["niche"])))
        b = boot(rows)
        if not b:
            continue
        star = "  <<<" if b["lo"] > 0 else ""
        me = "  (MAIN)" if (rk, fl) == MAIN else ""
        print(f"{rk:>18s} {fl:>6s} {b['mean']:>+18.4f} [{b['lo']:+.4f},{b['hi']:+.4f}] "
              f"{b['p']:>7.3f} {b['n_markets']:>6,}{star}{me}")
        out["robustness"][f"{rk}_{fl}"] = b
    print()

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(out, f, indent=2, default=float)
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
