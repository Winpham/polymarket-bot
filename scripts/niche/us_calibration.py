#!/usr/bin/env python3
"""
IS THE US VENUE MISPRICED AT A FAIR ENTRY?  (mapper-free efficiency test of the book we trade)

Phase 2 measured US favourites "overpriced 6.4pp" using the FIRST >=0.80 cross as the entry — a
self-selected, transient-spike-biased point (the >=0.95 band winning only 56% was the tell). This
removes that bias: it samples each US market's price at a CONTROLLED horizon before resolution
(nearest print to last_print - {1h,3h,6h}) and compares to the OFFICIAL DMR outcome. A reliability
curve + Brier over MANY markets is the fundamental efficiency test: if a thin US book systematically
misprices, that is a real, natively-tradeable, mapper-free edge; if the curve is on the diagonal, the
US venue is efficient at a fair entry and Phase 2's number was partly entry-timing.

Then it prices the tradeable version: at each fair snapshot, the EV-maximising side (YES if
p<win-implied, else NO=1-p) net of the US taker fee + a spread haircut, event-clustered, standing bar.

DATA: ~/polymarket-archive/us_time_sales/*.parquet (price paths) + us_daily_market_report (official
settlement). Curated to standard liquid game markets (exotics excluded), aec/tc/etc winner universe.

  ./us_calibration.py --self-test
  ./us_calibration.py --from 2026-06-24 --to 2026-07-13
"""
import argparse
import glob
import io
import os
import subprocess
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import us_native_backtest as U  # grade_niche, is_exotic, event_key, event_date, fee_us  # noqa

ARCHIVE = U.ARCHIVE
PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "-v", "ON_ERROR_STOP=1", "--csv", "-q"]
GUARD = "SET max_parallel_workers_per_gather=0; SET statement_timeout='600s'; "


def psql(sql):
    import csv
    o = subprocess.run(PG, input=GUARD + sql, capture_output=True, text=True)
    if o.returncode != 0:
        sys.exit("psql FAILED:\n" + o.stderr[:1500])
    return list(csv.DictReader(io.StringIO(o.stdout)))


def dmr_settlements():
    rows = psql("SELECT symbol, settlement_price FROM us_daily_market_report "
                "WHERE business_date = maturity_date AND settlement_price IN (0,1);")
    return {r["symbol"]: float(r["settlement_price"]) for r in rows}


def price_at(path, t_target):
    """path=[(t,p)] ascending. Return the price of the last print at/before t_target (the info a
    trader would have then). None if no print at/before t_target."""
    lo, hi, best = 0, len(path) - 1, None
    # linear is fine (paths are short after curation); keep it obvious
    for (t, p) in path:
        if t <= t_target:
            best = p
        else:
            break
    return best


def boot_events(vals_by_ev, n_boot=4000, seed=20260715):
    keys = list(vals_by_ev)
    if len(keys) < 20:
        return None
    m = np.array([np.mean(vals_by_ev[k]) for k in keys], float)
    rng = np.random.default_rng(seed)
    bs = m[rng.integers(0, len(m), (n_boot, len(m)))].mean(1)
    return {"mean": float(m.mean()), "lo": float(np.percentile(bs, 2.5)),
            "hi": float(np.percentile(bs, 97.5)), "p_le0": float((bs <= 0).mean()), "n": len(keys)}


def self_test():
    p = [(0, .5), (100, .7), (200, .8), (300, .95)]
    assert price_at(p, 150) == .7 and price_at(p, 250) == .8 and price_at(p, 99) == .5
    assert price_at(p, -1) is None
    r = boot_events({f"e{i}": [0.02] for i in range(30)})
    assert r and abs(r["mean"] - 0.02) < 1e-9
    print("self-test OK (price_at snapshot, event bootstrap)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--from", dest="d0", default="2026-06-24")
    ap.add_argument("--to", dest="d1", default="2026-07-13")
    ap.add_argument("--min-prints", type=int, default=50)
    ap.add_argument("--haircut", type=float, default=0.005, help="spread/exec haircut per share")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test())

    import pyarrow.parquet as pq
    files = sorted(f for f in glob.glob(f"{ARCHIVE}/*.parquet")
                   if a.d0 <= os.path.basename(f)[:10] <= a.d1)
    dmr = dmr_settlements()
    print(f"US T&S days: {len(files)}   DMR official settlements: {len(dmr):,}")

    paths = defaultdict(list)
    niche_of = {}
    for f in files:
        t = pq.read_table(f, columns=["Transaction Time", "Symbol", "Last Price"]).to_pandas()
        t["ep"] = t["Transaction Time"].astype("int64") / 1e9
        for sym, px, ep in zip(t["Symbol"].values, t["Last Price"].values, t["ep"].values):
            if sym not in niche_of:
                niche_of[sym] = U.grade_niche(sym)
            if niche_of[sym] in U.TRADEABLE and not U.is_exotic(sym):
                paths[sym].append((float(ep), float(px)))
    paths = {s: sorted(p) for s, p in paths.items() if len(p) >= a.min_prints and s in dmr}
    print(f"curated, DMR-settled markets: {len(paths):,}\n")

    for horizon_h in (1, 3, 6):
        H = horizon_h * 3600
        # fair snapshot: the price H seconds before the market's LAST print (~ resolution)
        snaps = []  # (sym, ev, niche, price, won)
        for sym, p in paths.items():
            t_last = p[-1][0]
            px = price_at(p, t_last - H)
            if px is None or not (0.02 <= px <= 0.98):
                continue
            snaps.append((sym, U.event_key(sym), niche_of[sym], px, dmr[sym]))
        if len(snaps) < 100:
            print(f"horizon −{horizon_h}h: too few snapshots ({len(snaps)})")
            continue

        prices = np.array([s[3] for s in snaps])
        wons = np.array([s[4] for s in snaps])
        brier_price = float(np.mean((prices - wons) ** 2))
        print("=" * 92)
        print(f"US CALIBRATION at a FAIR entry: price −{horizon_h}h before resolution   "
              f"({len(snaps):,} markets)   price-Brier {brier_price:.4f}")
        print("=" * 92)
        print(f"  {'price band':>12s} {'n':>5s} {'mean_price':>10s} {'win_rate':>9s} "
              f"{'gap(win−price)':>15s}  {'read':>18s}")
        for lo, hi in [(0.02, .2), (.2, .35), (.35, .5), (.5, .65), (.65, .8), (.8, .9), (.9, .98)]:
            m = [(s[3], s[4]) for s in snaps if lo <= s[3] < hi]
            if len(m) < 15:
                continue
            mp = np.mean([x[0] for x in m])
            wr = np.mean([x[1] for x in m])
            gap = wr - mp
            read = "underpriced(buy YES)" if gap > 0.02 else ("overpriced(fade)" if gap < -0.02 else "fair")
            print(f"  [{lo:.2f},{hi:.2f}) {len(m):>5d} {mp:>10.4f} {wr:>9.4f} {gap:>+15.4f}  {read:>18s}")

        # tradeable: at each snapshot pick the +EV side vs the price, net of fee+haircut, event-clustered
        by_ev = defaultdict(list)
        for sym, ev, n, px, won in snaps:
            # YES: pay px, receive won ; NO: pay 1-px, receive 1-won
            net_yes = won - px - U.fee_us(px) - a.haircut
            net_no = (1 - won) - (1 - px) - U.fee_us(1 - px) - a.haircut
            # trade the side the *price itself* implies is a longshot is NOT allowed (that's hindsight);
            # a real policy needs a signal. Here we report the ORACLE upper bound (best side) AND the two
            # fixed policies (always-YES, always-fade-favourite) so the reader sees what's structural.
            by_ev[("oracle", ev)].append(max(net_yes, net_no))
            by_ev[("buy_underdog" if px < 0.5 else "buy_favourite", ev)].append(net_yes)
        for pol in ("buy_favourite", "buy_underdog", "oracle"):
            vbe = defaultdict(list)
            for (p_, ev), vs in by_ev.items():
                if p_ == pol:
                    vbe[ev].extend(vs)
            r = boot_events(vbe)
            if r:
                tag = {"buy_favourite": "buy every favourite (p>=.5 side)",
                       "buy_underdog": "buy every underdog (p<.5 side)",
                       "oracle": "ORACLE best side (hindsight upper bound)"}[pol]
                print(f"    {tag:>42s}: net {r['mean']*100:>+6.3f}c/sh "
                      f"[{r['lo']*100:+.2f},{r['hi']*100:+.2f}] p(<=0)={r['p_le0']:.3f} ({r['n']} ev)")
        print()


if __name__ == "__main__":
    main()
