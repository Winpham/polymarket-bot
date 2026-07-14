#!/usr/bin/env python3
"""
THE FAVOURITE-BAND COPY EDGE: is it REAL, is it TRADEABLE, and DO WE EVEN NEED THE ROSTER?

copy_vs_blind found one cell that survives everything: band 80-100c. COPY +2.23% raw net vs a
matched BLIND baseline of -0.39% -- surplus +2.62% [+1.24,+4.00], p=0.000, 830 markets, through
Benjamini-Hochberg. That is a live edge and it contradicts "copy-trading is DEAD".

Before believing it, four questions, in the order that can kill it:

Q1  WHERE is it?  `FAVOURITES 80-100c x sports` surplus was only +0.39% (n.s.) on 196 markets --
    so the edge is NOT in sports, and 634 of the 830 markets are crypto/weather/other. Decompose
    band x niche. An edge that lives in one unexpected corner is either a real market
    inefficiency or a bug, and we do not get to guess which.

Q2  IS IT REACHABLE?  The whole thing is priced at a 5s executor lag. If the edge needs 2s it is a
    latency war we lose; if it survives to 60s+ it is operationally trivial. Decay the copy net
    across lags 2s..15m IN THE CELL.

Q3  *** DO WE NEED THE ROSTER AT ALL? ***  The event study (tax_anatomy T2) showed the price is
    ALREADY RALLYING for 15 minutes before a roster wallet buys: -6.05c at t0-15m, 0 at their fill,
    +5.5c by +6h. They are MID-WAVE, not the origin of it. So the copy signal may be nothing but a
    MOMENTUM PROXY -- "this favourite is grinding up right now". If so we can compute it OURSELVES,
    enter on OUR OWN clock, and PAY NO FOLLOWER TAX AT ALL, with unlimited capacity and no
    latency race. That would be worth vastly more than the copy edge.

        POLICY C (momentum, roster-blind): at any taker print in the band, if the price rose
        >= THRESH over the trailing WINDOW, buy at that print. No wallet is consulted. Ever.

    If C ~= COPY, the roster is a decoration on a price feature and we should delete it.
    If C << COPY, the wallets carry something momentum does not, and the tax is the price of it.

Q4  WHAT IS IT WORTH?  Signals/day and $ P&L at the $50/signal capacity ceiling
    (project-polymarket-capacity). An edge that pays $3/day is not a business.

Paired per market, market-clustered bootstrap, real fee schedule, window B (out-of-sample).

  ./favband_forensics.py --self-test
  ./favband_forensics.py
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
GUARD = "SET work_mem='64MB'; SET statement_timeout='240s'; "
BATCH = 250
SEED = 20260714

REAL_FEE_RATE = {"tennis": 0.03, "soccer": 0.03, "mlb": 0.03, "nba": 0.03, "nhl": 0.03,
                 "ufc": 0.03, "esports": 0.03, "politics": 0.04, "crypto": 0.07}
DEFAULT_FEE_RATE = 0.05
LAGS = [2, 5, 15, 30, 60, 300, 900]
STAKE = 50.0                      # project-polymarket-capacity: $50/signal comfortable

MOM_WINDOWS = [300, 900, 1800]    # trailing window for the momentum policy
MOM_THRESH = [0.01, 0.02, 0.03]   # required trailing rise


def real_fee(p, n):
    return REAL_FEE_RATE.get(n, DEFAULT_FEE_RATE) * p * (1.0 - p)


def psql(sql):
    o = subprocess.run(PG, input=GUARD + sql, capture_output=True, text=True)
    if o.returncode != 0:
        sys.exit("psql failed:\n" + o.stderr[:800])
    return list(csv.DictReader(io.StringIO(o.stdout)))


def q_lit(xs):
    return ",".join("'" + str(x).replace("'", "''") + "'" for x in xs)


def boot(vals_by_mkt, n_boot=4000, seed=SEED):
    """vals_by_mkt = [(market, value)]; resamples MARKETS."""
    if not vals_by_mkt:
        return None
    by = defaultdict(list)
    for m, v in vals_by_mkt:
        by[m].append(v)
    k = list(by)
    if len(k) < 20:
        return None
    s = np.array([sum(by[x]) for x in k], float)
    n = np.array([len(by[x]) for x in k], float)
    rng = np.random.default_rng(seed)
    i = rng.integers(0, len(k), (n_boot, len(k)))
    mu = s[i].sum(1) / np.maximum(n[i].sum(1), 1)
    return {"mean": float(s.sum() / n.sum()), "lo": float(np.percentile(mu, 2.5)),
            "hi": float(np.percentile(mu, 97.5)), "p": float((mu <= 0).mean()),
            "n": len(vals_by_mkt), "n_markets": len(k)}


def locf_price(prints, t):
    """price of the last taker print at or before t (binary search); None if none."""
    lo, hi = 0, len(prints)
    while lo < hi:
        mid = (lo + hi) // 2
        if prints[mid][0] <= t:
            lo = mid + 1
        else:
            hi = mid
    return prints[lo - 1][1] if lo else None


# --------------------------------------------------------------------------------- self-test
def self_test():
    pr = [(0.0, 0.80), (100.0, 0.83), (200.0, 0.88)]
    assert locf_price(pr, -1) is None
    assert locf_price(pr, 150) == 0.83
    assert locf_price(pr, 1e9) == 0.88
    b = boot([(f"m{i}", 0.02) for i in range(50)])
    assert abs(b["mean"] - 0.02) < 1e-9 and b["p"] == 0.0
    b2 = boot([(f"m{i}", -0.02) for i in range(50)])
    assert b2["p"] == 1.0
    assert boot([("m1", 0.1)] * 5) is None            # too few markets -> refuse to report
    assert abs(real_fee(0.9, "mlb") - 0.0027) < 1e-9
    print("self-test OK")
    return 0


# --------------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--roster", default="reports/niche/global_profit_floor20.json")
    ap.add_argument("--ranker", default="eb_shrunk")
    ap.add_argument("--out", default="reports/niche/favband_forensics.json")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test())

    R = [r for r in json.load(open(a.roster)) if r["ranker"] == a.ranker][0]["roster"]
    wallets = [w["wallet"] for w in R]
    rosterset = set(wallets)

    wfilt = ("AND h.condition_id IN (SELECT condition_id FROM ("
             "  SELECT condition_id, MAX(ts) mts FROM harvest_wm GROUP BY 1) x "
             "  WHERE x.mts > (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY mts) "
             "                 FROM (SELECT condition_id, MAX(ts) mts FROM harvest_wm "
             "                       GROUP BY 1) y))")
    sigs = psql(f"""
      WITH res AS (SELECT condition_id, outcome_index, BOOL_OR(outcome_won) won
                   FROM trader_fills WHERE resolved AND outcome_won IS NOT NULL GROUP BY 1,2),
      ok AS (SELECT condition_id, niche FROM harvest_markets WHERE NOT truncated)
      SELECT h.condition_id, h.outcome_index, h.wallet, EXTRACT(EPOCH FROM h.ts) t,
             h.price p, (r.won::int)::float8 won, ok.niche
      FROM harvest_fills h
      JOIN ok ON ok.condition_id=h.condition_id
      JOIN res r ON r.condition_id=h.condition_id AND r.outcome_index=h.outcome_index
      WHERE h.side='BUY' AND h.is_maker=false AND h.wallet IN ({q_lit(wallets)}) {wfilt};
    """)
    mkts = sorted({s["condition_id"] for s in sigs})
    print(f"{len(sigs):,} roster signals / {len(mkts):,} markets\n")

    takers, wonmap, niche_of = defaultdict(list), {}, {}
    for i in range(0, len(mkts), BATCH):
        ch = mkts[i:i + BATCH]
        for r in psql(f"""
              SELECT h.condition_id, h.outcome_index, h.wallet,
                     EXTRACT(EPOCH FROM h.ts) t, h.price p, m.niche
              FROM harvest_fills h JOIN harvest_markets m USING (condition_id)
              WHERE h.side='BUY' AND h.is_maker=false AND h.condition_id IN ({q_lit(ch)});"""):
            takers[(r["condition_id"], r["outcome_index"])].append(
                (float(r["t"]), float(r["p"]), r["wallet"]))
            niche_of[r["condition_id"]] = r["niche"]
        for r in psql(f"""
              SELECT condition_id, outcome_index, BOOL_OR(outcome_won)::int won
              FROM trader_fills WHERE resolved AND outcome_won IS NOT NULL
                AND condition_id IN ({q_lit(ch)}) GROUP BY 1,2;"""):
            wonmap[(r["condition_id"], r["outcome_index"])] = float(r["won"])
        sys.stdout.write(f"\r  {min(i+BATCH, len(mkts)):,}/{len(mkts):,}")
        sys.stdout.flush()
    for k in takers:
        takers[k].sort(key=lambda x: x[0])
    print(f"\n  taker tape {sum(len(v) for v in takers.values()):,} prints\n")

    out = {}
    FAV = lambda p: p >= 0.80          # noqa: E731  the surviving cell

    # ============================================================== Q1  band x niche
    print("=" * 94)
    print("Q1  WHERE does the favourite-band copy edge actually live?  (5s lag, raw net + surplus)")
    print("=" * 94)
    copy_by, blind_by = defaultdict(list), defaultdict(list)
    for s in sigs:
        k = (s["condition_id"], s["outcome_index"])
        t0, w0, n = float(s["t"]), s["wallet"], s["niche"]
        px = next((p for (t, p, w) in takers.get(k, []) if t >= t0 + 5 and w != w0), None)
        if px is None or not FAV(px):
            continue
        copy_by[n].append((s["condition_id"], float(s["won"]) - px - real_fee(px, n)))
    for (cid, oi), prints in takers.items():
        w = wonmap.get((cid, oi))
        if w is None:
            continue
        n = niche_of[cid]
        for (t, p, wal) in prints:
            if wal in rosterset or not FAV(p):
                continue
            blind_by[n].append((cid, w - p - real_fee(p, n)))
    print(f"{'niche @80-100c':>18s} {'COPY net':>10s} {'95% CI':>20s} {'BLIND':>8s} "
          f"{'SURPLUS':>9s} {'mkts':>6s}")
    print("-" * 94)
    out["Q1"] = {}
    for n in sorted(copy_by, key=lambda x: -len(copy_by[x])):
        bc, bb = boot(copy_by[n]), boot(blind_by.get(n, []))
        if not bc or not bb:
            continue
        star = "  <<<" if bc["lo"] > 0 else ""
        print(f"{n:>18s} {bc['mean']:>+10.4f} [{bc['lo']:+.4f},{bc['hi']:+.4f}] "
              f"{bb['mean']:>+8.4f} {bc['mean']-bb['mean']:>+9.4f} {bc['n_markets']:>6,}{star}")
        out["Q1"][n] = {"copy": bc, "blind": bb}
    print()

    # ============================================================== Q2  lag decay in the cell
    print("=" * 94)
    print("Q2  IS IT REACHABLE?  copy net in the 80-100c cell, by executor lag")
    print("=" * 94)
    print(f"{'lag':>6s} {'copy net':>10s} {'95% CI':>20s} {'p':>7s} {'n':>6s} {'mkts':>6s}")
    print("-" * 94)
    out["Q2"] = {}
    for L in LAGS:
        rows = []
        for s in sigs:
            k = (s["condition_id"], s["outcome_index"])
            t0, w0, n = float(s["t"]), s["wallet"], s["niche"]
            px = next((p for (t, p, w) in takers.get(k, []) if t >= t0 + L and w != w0), None)
            if px is None or not FAV(px):
                continue
            rows.append((s["condition_id"], float(s["won"]) - px - real_fee(px, n)))
        b = boot(rows)
        if not b:
            continue
        lab = f"{L}s" if L < 60 else f"{L//60}m"
        star = "  <<<" if b["lo"] > 0 else ""
        print(f"{lab:>6s} {b['mean']:>+10.4f} [{b['lo']:+.4f},{b['hi']:+.4f}] {b['p']:>7.3f} "
              f"{b['n']:>6,} {b['n_markets']:>6,}{star}")
        out["Q2"][L] = b
    print()

    # ============================================================== Q3  DO WE NEED THE ROSTER?
    print("=" * 94)
    print("Q3  DO WE NEED THE ROSTER AT ALL?  momentum policy -- roster-blind, tax-free")
    print("=" * 94)
    print("    buy a favourite (>=80c) at any taker print whose price rose >= THRESH over WINDOW.")
    print("    No wallet is consulted. We set our own clock, so there is NO FOLLOWER TAX.\n")
    print(f"{'window':>8s} {'thresh':>8s} {'mom net':>10s} {'95% CI':>20s} {'p':>7s} "
          f"{'n':>8s} {'mkts':>6s}")
    print("-" * 94)
    out["Q3"] = {}
    for W in MOM_WINDOWS:
        for TH in MOM_THRESH:
            rows = []
            for (cid, oi), prints in takers.items():
                w = wonmap.get((cid, oi))
                if w is None:
                    continue
                n = niche_of[cid]
                for (t, p, wal) in prints:
                    if not FAV(p):
                        continue
                    past = locf_price(prints, t - W)
                    if past is None or p - past < TH:
                        continue
                    rows.append((cid, w - p - real_fee(p, n)))
            b = boot(rows)
            if not b:
                continue
            star = "  <<<" if b["lo"] > 0 else ""
            print(f"{W//60:>6d}m {TH:>8.2f} {b['mean']:>+10.4f} [{b['lo']:+.4f},{b['hi']:+.4f}] "
                  f"{b['p']:>7.3f} {b['n']:>8,} {b['n_markets']:>6,}{star}")
            out["Q3"][f"{W}s_{TH}"] = b
    print("\n  If momentum ~= copy, the roster is DECORATION on a price feature -- and we can trade")
    print("  it ourselves at our own price, with NO tax, NO latency race, and full capacity.\n")

    # ============================================================== Q4  what is it worth
    print("=" * 94)
    print("Q4  WHAT IS IT WORTH?")
    print("=" * 94)
    ts = [float(s["t"]) for s in sigs]
    span_d = (max(ts) - min(ts)) / 86400.0
    b5 = out["Q2"].get(5)
    if b5:
        per_day = b5["n"] / span_d
        # net is per SHARE; at price p a $STAKE stake buys STAKE/p shares
        edge_per_signal = b5["mean"] * (STAKE / 0.9)
        print(f"  window B spans           {span_d:.0f} days")
        print(f"  favourite-band signals   {b5['n']:,}  ({per_day:.1f}/day)")
        print(f"  net per share            {b5['mean']:+.4f}  (LB {b5['lo']:+.4f})")
        print(f"  $ per signal @ ${STAKE:.0f}     {edge_per_signal:+.2f}   "
              f"(LB {b5['lo'] * STAKE / 0.9:+.2f})")
        print(f"  $ per day  @ ${STAKE:.0f}       {edge_per_signal * per_day:+.2f}   "
              f"(LB {b5['lo'] * STAKE / 0.9 * per_day:+.2f})")
        out["Q4"] = {"span_days": span_d, "signals_per_day": per_day,
                     "usd_per_signal": edge_per_signal,
                     "usd_per_day": edge_per_signal * per_day}
    print()

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(out, f, indent=2, default=float)
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
