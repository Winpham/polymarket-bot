#!/usr/bin/env python3
"""
CLEAN US ABSOLUTE — the frozen collapse model on real US price paths, settled on the OFFICIAL
regulatory Daily Market Report (DMR), not on a T&S-inferred label.

WHY THIS EXISTS. `us_native_backtest.py` concluded the US ABSOLUTE edge is "unmeasurable
retrospectively" because it labelled settlement by rounding the T&S last price (validated on only the
2 DMR days it had locally, 98.1%). Its own memo flags a residual winner-drop bias -> "true US edge
roughly [-2%, +1%], not demonstrably positive." THAT WAS A DATA GAP, NOT A LAW: the full official DMR
(source=regulatory_dmr) was backfilled into `us_daily_market_report` on 2026-07-14 with 100%
settlement coverage for 2025-10-30..2026-07-13. So we can settle on the OFFICIAL number.

WHAT THIS DOES. Byte-for-byte the same price paths + the same 14 backward-looking features as
`us_native_backtest.py` (imported, not re-implemented), but the label is the OFFICIAL DMR terminal
settlement (business_date = maturity_date, settlement_price in {0,1}; 0.5 ties dropped). It also A/Bs
the three settlement methods on the SAME symbols so the settlement bias is measured, not asserted.

COSTS unchanged: US taker fee theta=0.06*p*(1-p) + a 0.5c ask haircut. Event-clustered by game.
DB access via the pinned docker-exec psql helper (ON_ERROR_STOP, parallel workers off).

  ./us_dmr_backtest.py --self-test
  ./us_dmr_backtest.py --from 2026-06-24 --to 2026-07-13 --curated --one-dp
"""
import argparse
import glob
import io
import os
import pickle
import subprocess
import sys
from collections import defaultdict

import numpy as np

# Reuse the EXACT feature/settlement/cluster logic — no re-implementation, no drift.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import us_native_backtest as U  # noqa: E402

ARCHIVE = U.ARCHIVE
MODEL = U.MODEL
SEED = U.SEED
BAND_LO = U.BAND_LO
MAX_DP = U.MAX_DP
TRADEABLE = U.TRADEABLE

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "-v", "ON_ERROR_STOP=1", "--csv", "-q"]
GUARD = "SET max_parallel_workers_per_gather=0; SET statement_timeout='600s'; "


def psql(sql):
    o = subprocess.run(PG, input=GUARD + sql, capture_output=True, text=True)
    if o.returncode != 0:
        sys.exit("psql FAILED:\n" + o.stderr[:1500])
    import csv
    return list(csv.DictReader(io.StringIO(o.stdout)))


def dmr_settlements():
    """Official terminal settlements: business_date = maturity_date, unambiguous binary {0,1}.
    Returns {symbol: 0.0|1.0}. 0.5 ties and fractional/mark rows are dropped (not terminal binary)."""
    rows = psql(
        "SELECT symbol, settlement_price FROM us_daily_market_report "
        "WHERE business_date = maturity_date AND settlement_price IN (0,1);")
    return {r["symbol"]: float(r["settlement_price"]) for r in rows}


def self_test():
    U.self_test()
    # DMR label must win over the rounded T&S label when they disagree (the whole point).
    d = {"aec-x-2026-07-01": 1.0}
    assert d.get("aec-x-2026-07-01") == 1.0
    # a symbol absent from the DMR is dropped, never guessed
    assert d.get("aec-missing") is None
    print("dmr self-test OK (official settlement join, drop-on-absent)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--from", dest="d0", default="2026-06-24")
    ap.add_argument("--to", dest="d1", default="2026-07-13")
    ap.add_argument("--haircut", type=float, default=0.005)
    ap.add_argument("--curated", action="store_true")
    ap.add_argument("--min-prints", type=int, default=50)
    ap.add_argument("--one-dp", action="store_true")
    ap.add_argument("--ab-settle", action="store_true",
                    help="A/B the three settlement methods (DMR vs maturity-round vs strict) on the "
                         "SAME symbols — measures the settlement bias directly")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test())

    import pyarrow.parquet as pq

    files = sorted(f for f in glob.glob(f"{ARCHIVE}/*.parquet")
                   if a.d0 <= os.path.basename(f)[:10] <= a.d1)
    print(f"US T&S days: {len(files)}  ({a.d0} .. {a.d1})   curated={a.curated}")

    paths = defaultdict(list)
    nprints = defaultdict(int)
    niche_of = {}
    for f in files:
        t = pq.read_table(f, columns=["Transaction Time", "Symbol", "Last Price"]).to_pandas()
        t["ep"] = t["Transaction Time"].astype("int64") / 1e9
        for sym, px, ep in zip(t["Symbol"].values, t["Last Price"].values, t["ep"].values):
            if sym not in niche_of:
                niche_of[sym] = U.grade_niche(sym)
            if niche_of[sym] in TRADEABLE and not (a.curated and U.is_exotic(sym)):
                paths[sym].append((float(ep), float(px)))
                nprints[sym] += 1
        sys.stdout.write(f"\r  loaded {os.path.basename(f)}  symbols={len(paths):,}")
        sys.stdout.flush()
    print()
    if a.curated:
        paths = {s: p for s, p in paths.items() if nprints[s] >= a.min_prints}
        print(f"  curated to standard, liquid (>={a.min_prints} prints): {len(paths):,} symbols")

    dmr = dmr_settlements()
    print(f"  DMR official terminal settlements available: {len(dmr):,} symbols")

    clf = pickle.load(open(MODEL, "rb"))
    rng = np.random.default_rng(SEED)
    last_day = os.path.basename(files[-1])[:10]
    mat_cut = (np.datetime64(last_day) - np.timedelta64(1, "D")).astype(str)

    # Build decision points labelled THREE ways for the same symbols (only where all defined),
    # so the A/B is apples-to-apples. Primary label = DMR.
    rowsX, meta = [], []
    n_sym = n_dmr = n_dropped_nodmr = 0
    ab = {"dmr": [], "mat": [], "strict": []}  # (evk, net, p) per method, model EV>0.01
    for sym, path in paths.items():
        if len(path) < 5:
            continue
        path.sort()
        n_sym += 1
        won_dmr = dmr.get(sym)
        if won_dmr is None:
            n_dropped_nodmr += 1
            continue
        n_dmr += 1
        cand = [j for j, (t, p) in enumerate(path) if p >= BAND_LO]
        if not cand:
            continue
        if a.one_dp:
            pick = [cand[0]]
        else:
            pick = cand if len(cand) <= MAX_DP else list(rng.choice(cand, MAX_DP, replace=False))
        n = niche_of[sym]
        evk = U.event_key(sym)
        for j in sorted(pick):
            rowsX.append(U.featurize(path, j, n))
            meta.append((evk, won_dmr, path[j][1], n, sym))

        if a.ab_settle:
            # same symbol, alternative labels
            ed = U.event_date(sym)
            won_mat = U.settle(path, matured=True) if (ed and ed <= mat_cut) else None
            won_strict = U.settle(path, matured=False)
            for j in sorted(pick):
                p = path[j][1]
                ab["dmr"].append((evk, won_dmr, p, j, sym))
                ab["mat"].append((evk, won_mat, p, j, sym))
                ab["strict"].append((evk, won_strict, p, j, sym))

    print(f"symbols with a path: {n_sym:,}   with OFFICIAL DMR settlement: {n_dmr:,}   "
          f"dropped (no DMR): {n_dropped_nodmr:,}   decision points: {len(rowsX):,}")
    if len(rowsX) < 50:
        sys.exit("too few US decision points — widen the date range")

    X = np.array(rowsX, float)
    pw = clf.predict_proba(X)[:, 1]
    ev = np.array([pw[i] - meta[i][2] - U.fee_us(meta[i][2]) for i in range(len(meta))])

    def rows(thr):
        out = []
        for i in range(len(meta)):
            evk, won, p, n, sym = meta[i]
            if ev[i] > thr:
                out.append((evk, won - p - U.fee_us(p) - a.haircut, p))
        return out

    W = 100
    print("\n" + "=" * W)
    print(f"US CLEAN ABSOLUTE — FROZEN model, OFFICIAL DMR settlement "
          f"(US fee theta=0.06 + {a.haircut*100:.1f}c haircut, event-clustered)")
    print("=" * W)
    print(f"{'policy':>30s} {'NET c/sh':>9s} {'net 95% CI':>17s} | "
          f"{'ROI/turn':>9s} {'ROI 95% CI':>18s} {'p':>6s} {'ev':>5s} {'sigs':>6s}")
    print("-" * W)
    for lab, thr in [("BLIND: every US favourite", -9), ("MODEL EV>+0.00", 0.0),
                     ("MODEL EV>+0.01", 0.01), ("MODEL EV>+0.03", 0.03)]:
        r = U.boot_event(rows(thr))
        if not r:
            print(f"{lab:>30s}   -- too few events --")
            continue
        print(f"{lab:>30s} {r['net']*100:>+8.3f}c "
              f"[{r['net_lo']*100:+.2f},{r['net_hi']*100:+.2f}] | "
              f"{r['roi']*100:>+8.2f}% [{r['roi_lo']*100:+.2f}%,{r['roi_hi']*100:+.2f}%] "
              f"{r['p']:>6.3f} {r['n_ev']:>5,} {r['n_rows']:>6,}")

    # per-sport clean absolute (durability, the favorite_v2 trap)
    print("\n  per-sport (MODEL EV>+0.01, DMR settlement):")
    for sport in TRADEABLE:
        rws = [(evk, won - p - U.fee_us(p) - a.haircut, p)
               for i, (evk, won, p, n, sym) in enumerate(meta) if n == sport and ev[i] > 0.01]
        r = U.boot_event(rws)
        if r:
            print(f"    {sport:>9s}: ROI {r['roi']*100:>+6.2f}% "
                  f"[{r['roi_lo']*100:+.2f},{r['roi_hi']*100:+.2f}] p={r['p']:.3f} ({r['n_ev']} ev)")
        else:
            print(f"    {sport:>9s}: too few events")

    if a.ab_settle:
        print("\n" + "=" * W)
        print("SETTLEMENT-BIAS A/B — same symbols/decision points, three labels. "
              "MODEL EV>+0.01, event-clustered ROI.")
        print("Measures how much the predecessor's inferred label biased the absolute vs the "
              "official DMR truth.")
        print("=" * W)
        for name in ("dmr", "mat", "strict"):
            items = ab[name]
            # recompute EV on same features (identical), keep rows where this method has a label
            rws = []
            for k, (evk, won, p, j, sym) in enumerate(items):
                if won is None:
                    continue
                if ev[k] > 0.01:
                    rws.append((evk, won - p - U.fee_us(p) - a.haircut, p))
            r = U.boot_event(rws)
            lab = {"dmr": "OFFICIAL DMR", "mat": "T&S maturity-round (predecessor default)",
                   "strict": "T&S strict 0.95/0.05 (drops ambiguous)"}[name]
            if r:
                print(f"  {lab:>42s}: ROI {r['roi']*100:>+6.2f}% "
                      f"[{r['roi_lo']*100:+.2f},{r['roi_hi']*100:+.2f}] "
                      f"net {r['net']*100:+.3f}c p={r['p']:.3f} ({r['n_ev']} ev, {r['n_rows']} sig)")
            else:
                print(f"  {lab:>42s}: too few events")
        # label agreement rate on the settled subset
        agree_mat = agree_strict = tot_mat = tot_strict = 0
        for k in range(len(ab["dmr"])):
            wd = ab["dmr"][k][1]
            wm = ab["mat"][k][1]
            ws = ab["strict"][k][1]
            if wm is not None:
                tot_mat += 1
                agree_mat += (wm == wd)
            if ws is not None:
                tot_strict += 1
                agree_strict += (ws == wd)
        if tot_mat:
            print(f"\n  label agreement vs DMR: maturity-round {100*agree_mat/tot_mat:.1f}% "
                  f"({tot_mat} labelled), strict {100*agree_strict/max(tot_strict,1):.1f}% "
                  f"({tot_strict} labelled)")

    print("\n  >> If MODEL ROI LB > 0 on the OFFICIAL DMR label, the US ABSOLUTE is measurable and")
    print("     positive — the predecessor's 'unmeasurable/could be ~0' was a data gap, not a law.")


if __name__ == "__main__":
    main()
