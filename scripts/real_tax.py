#!/usr/bin/env python3
"""
REAL FOLLOWER-TAX MEASUREMENT (Cycle 5, Thread T2) — replace the MODELED follower tax with a
MEASURED one from real captured entries.

Every Cycle 1-4 realizable verdict rests on a MODELED tax: our_entry = trader_price + FOLLOWER_TAX
(0.013) + band_spread(band) (copyability.py / trader_scorecard.reprice). Nobody has MEASURED it.
Dense capture (signal_price_trajectory, live since 2026-07-03 20:09) records the live best ASK on a
market over time. So for a real trader fill on a market we captured, the REAL executable entry we'd
have gotten as a follower = the earliest captured ASK on that SAME market (condition_id,outcome_index)
within the decision-lag window AFTER the fill; the REAL tax = that ask − the trader's fill price.

    trader fills at (t_f, price)  ──(we see it, act with lag)──▶  earliest captured ask in [t_f, t_f+LAG]
    REAL follower tax = captured_ask − price     (what we ACTUALLY pay above the trader)

The dense-capture ask trajectory keys to a market via consensus_signals (signal_id → condition_id,
outcome_index); because the CLV/ask is a MARKET property, the sibling-anchored path is valid for any
fill on that market — this is exactly the Cycle-2 market-key join, read-side, in the research layer.

HONESTY / POWER (this is a THIN sample — ~2.3 days of dense capture, capture bursts cluster around OUR
signal fires, so a fill only matches if it landed shortly before one of our capture bursts):
  * coverage = matched_fills / fills_on_captured_markets — reported per cell; low coverage caps trust.
  * report per (sport×band): n, coverage, REAL tax median + IQR, market-CLUSTERED mean (one market
    can't dominate), MODELED tax, and is_real < modeled.
  * event/market-cluster before believing any cell; a "win" on a handful of markets is INDETERMINATE.

Read-only, paper-only, promotes nothing, no Rust touched.
  ./real_tax.py                 # live measurement; writes reports/real_tax.json
  ./real_tax.py --selftest      # synthetic fixtures with known answers; no DB
  ./real_tax.py --lag 900       # decision-lag window seconds (default 900)
"""

import argparse
import bisect
import csv
import io
import json
import os
import subprocess
import sys
from collections import defaultdict
from statistics import median

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]
FOLLOWER_TAX = 0.013
GUARD_LO, GUARD_HI = 0.02, 0.98
DECISION_LAG = 900
DENSE_START = "2026-07-03 20:00"
REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")


def q(sql):
    out = subprocess.run(PG + ["-f", "-"], input=sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    return list(csv.DictReader(io.StringIO(out.stdout)))


def band(p):
    """width_bucket(p,0,1,5) — matches trader_scorecard.band / the Rust re-scorer."""
    return min(int(p * 5) + 1, 5) if p < 1.0 else 6


def fetch_band_spreads():
    rows = q("""
      SELECT width_bucket(initial_mean_price, 0.0, 1.0, 5) AS band,
             AVG(GREATEST(entry_ask - entry_ask_mid, 0)) AS spread
      FROM consensus_signals
      WHERE entry_ask IS NOT NULL AND entry_ask_mid IS NOT NULL AND entry_ask_at IS NOT NULL
        AND EXTRACT(EPOCH FROM (entry_ask_at - first_detected_at)) <= 900
      GROUP BY 1""")
    return {int(r["band"]): float(r["spread"]) for r in rows if r["spread"]}


def modeled_tax(b, spreads):
    return FOLLOWER_TAX + spreads.get(b, 0.0)


def fetch_askpts():
    """Market (condition_id,outcome_index) -> sorted [(ts_epoch, ask)] from dense capture, guarded."""
    rows = q(f"""
      SELECT s.condition_id AS c, s.outcome_index AS o,
             EXTRACT(EPOCH FROM t.ts) AS ts, t.ask AS ask
      FROM signal_price_trajectory t JOIN consensus_signals s ON s.id=t.signal_id
      WHERE t.ask IS NOT NULL AND t.ask BETWEEN {GUARD_LO} AND {GUARD_HI}""")
    by = defaultdict(list)
    for r in rows:
        by[(r["c"], r["o"])].append((float(r["ts"]), float(r["ask"])))
    for k in by:
        by[k].sort()
    return by


def fetch_fills(captured_keys):
    """Resolved BUY fills on captured markets, post dense-start, in-band. One row per fill."""
    rows = q(f"""
      WITH capmkt AS (
        SELECT DISTINCT s.condition_id, s.outcome_index
        FROM signal_price_trajectory t JOIN consensus_signals s ON s.id=t.signal_id
        WHERE t.ask IS NOT NULL AND t.ask BETWEEN {GUARD_LO} AND {GUARD_HI})
      SELECT lower(tf.wallet) AS wallet, tf.condition_id AS c, tf.outcome_index AS o,
             COALESCE(tf.sport,'other') AS sport, tf.price AS price,
             EXTRACT(EPOCH FROM tf.ts) AS ts
      FROM trader_fills tf JOIN capmkt m
        ON m.condition_id=tf.condition_id AND m.outcome_index=tf.outcome_index
      WHERE tf.side='BUY' AND tf.resolved AND tf.outcome_won IS NOT NULL
        AND tf.ts >= '{DENSE_START}' AND tf.price >= {GUARD_LO} AND tf.price < {GUARD_HI}""")
    return rows


def match_ask(askpts, key, t_f, lag):
    """Earliest captured ask on the market with ts in [t_f, t_f+lag] (the follower's fill)."""
    pts = askpts.get(key)
    if not pts:
        return None
    ts_list = [p[0] for p in pts]
    i = bisect.bisect_left(ts_list, t_f)
    if i < len(pts) and pts[i][0] <= t_f + lag:
        return pts[i][1]
    return None


def iqr(vals):
    if not vals:
        return (None, None)
    sv = sorted(vals)
    n = len(sv)
    return (sv[max(0, int(0.25 * n) - 0)], sv[min(n - 1, int(0.75 * n))])


def run(lag=DECISION_LAG):
    spreads = fetch_band_spreads()
    askpts = fetch_askpts()
    fills = fetch_fills(set(askpts.keys()))

    # per-fill real tax; bucket by (sport, band) and remember market cluster key
    cells = defaultdict(lambda: {"n": 0, "matched": [], "clust": defaultdict(list)})
    per_band = defaultdict(lambda: {"n": 0, "matched": [], "clust": defaultdict(list)})
    overall = {"n": 0, "matched": [], "clust": defaultdict(list)}
    for f in fills:
        price = float(f["price"])
        b = band(price)
        if b not in (1, 2, 3, 4, 5):
            continue
        key = (f["c"], f["o"])
        ask = match_ask(askpts, key, float(f["ts"]), lag)
        sport = f["sport"]
        for agg, ck in ((cells[(sport, b)], key), (per_band[b], key), (overall, key)):
            agg["n"] += 1
            if ask is not None:
                tax = ask - price
                agg["matched"].append(tax)
                agg["clust"][ck].append(tax)

    def summarize(agg, b):
        m = agg["matched"]
        cov = (len(m) / agg["n"]) if agg["n"] else 0.0
        clust_means = [sum(v) / len(v) for v in agg["clust"].values()]
        mt = modeled_tax(b, spreads) if b else None
        real_med = median(m) if m else None
        lo, hi = iqr(m)
        clust_mean = (sum(clust_means) / len(clust_means)) if clust_means else None
        return {
            "n_fills": agg["n"], "n_matched": len(m), "coverage": round(cov, 4),
            "n_markets": len(agg["clust"]),
            "real_tax_median": round(real_med, 4) if real_med is not None else None,
            "real_tax_iqr": [round(lo, 4), round(hi, 4)] if m else [None, None],
            "real_tax_pooled_mean": round(sum(m) / len(m), 4) if m else None,
            "real_tax_market_clustered_mean": round(clust_mean, 4) if clust_mean is not None else None,
            "modeled_tax": round(mt, 4) if mt is not None else None,
            "real_lt_modeled_median": (real_med < mt) if (real_med is not None and mt is not None) else None,
            "real_lt_modeled_clustered": (clust_mean < mt) if (clust_mean is not None and mt is not None) else None,
        }

    cell_out = {}
    for (sport, b), agg in sorted(cells.items()):
        cell_out[f"{sport}|b{b}"] = {"sport": sport, "band": b, **summarize(agg, b)}
    band_out = {f"b{b}": summarize(agg, b) for b, agg in sorted(per_band.items())}
    overall_all = summarize(overall, None)
    # overall modeled tax = fill-weighted average modeled tax over matched bands (context only)
    band_mt = {b: modeled_tax(b, spreads) for b in per_band}
    tot_matched = sum(len(a["matched"]) for a in per_band.values())
    if tot_matched:
        mt_fillwt = sum(band_mt[b] * len(a["matched"]) for b, a in per_band.items()) / tot_matched
        overall_all["modeled_tax_fillwt"] = round(mt_fillwt, 4)
        cm = overall_all["real_tax_market_clustered_mean"]
        pm = overall_all["real_tax_pooled_mean"]
        overall_all["real_lt_modeled_clustered"] = (cm < mt_fillwt) if cm is not None else None
        overall_all["real_lt_modeled_pooled"] = (pm < mt_fillwt) if pm is not None else None

    out = {
        "meta": {"follower_tax_const": FOLLOWER_TAX, "decision_lag_s": lag,
                 "dense_start": DENSE_START, "guard": [GUARD_LO, GUARD_HI],
                 "band_spreads_modeled": {str(k): round(v, 4) for k, v in sorted(spreads.items())},
                 "modeled_tax_by_band": {str(k): round(modeled_tax(k, spreads), 4)
                                         for k in sorted(band_mt)},
                 "posture": "PAPER-ONLY, read-only, nothing promoted, no Rust",
                 "method": "REAL tax = earliest captured ASK on same market in [fill_ts, fill_ts+lag] "
                           "minus trader fill price; market-key join (Cycle-2 fix), research-layer."},
        "overall": overall_all,
        "by_band": band_out,
        "by_sport_band": cell_out,
    }
    os.makedirs(REPORT_DIR, exist_ok=True)
    path = os.path.join(REPORT_DIR, "real_tax.json")
    with open(path, "w") as fh:
        json.dump(out, fh, indent=2)
    _print(out)
    print(f"\nwrote {path}")
    return out


def _print(out):
    print("=" * 96)
    print("REAL FOLLOWER-TAX MEASUREMENT (T2) · earliest captured ASK in [fill, fill+lag] − trader price")
    print("=" * 96)
    o = out["overall"]
    print(f"OVERALL: {o['n_matched']}/{o['n_fills']} fills matched "
          f"(coverage {o['coverage']:.1%}) across {o['n_markets']} markets")
    print(f"  REAL tax  median {o['real_tax_median']}  IQR {o['real_tax_iqr']}  "
          f"pooled-mean {o['real_tax_pooled_mean']}  mkt-clustered-mean {o['real_tax_market_clustered_mean']}")
    print(f"  MODELED tax (fill-wt) {o.get('modeled_tax_fillwt')}   "
          f"→ real < modeled (clustered)? {o.get('real_lt_modeled_clustered')}")
    print("-" * 96)
    print(f"{'cell':<10}{'n':>7}{'cov':>7}{'mkts':>6}{'realMed':>9}{'realIQR':>18}"
          f"{'clustMean':>11}{'modeled':>9}{'real<mod':>10}")
    print("BY BAND (pooled across sports):")
    for k, c in out["by_band"].items():
        iqrs = f"[{c['real_tax_iqr'][0]},{c['real_tax_iqr'][1]}]"
        print(f"  {k:<8}{c['n_fills']:>7}{c['coverage']*100:>6.0f}%{c['n_markets']:>6}"
              f"{str(c['real_tax_median']):>9}{iqrs:>18}{str(c['real_tax_market_clustered_mean']):>11}"
              f"{str(c['modeled_tax']):>9}{str(c['real_lt_modeled_clustered']):>10}")
    print("BY SPORT×BAND (cells with n_matched>0):")
    for k, c in out["by_sport_band"].items():
        if c["n_matched"] == 0:
            continue
        iqrs = f"[{c['real_tax_iqr'][0]},{c['real_tax_iqr'][1]}]"
        print(f"  {k:<8}{c['n_fills']:>7}{c['coverage']*100:>6.0f}%{c['n_markets']:>6}"
              f"{str(c['real_tax_median']):>9}{iqrs:>18}{str(c['real_tax_market_clustered_mean']):>11}"
              f"{str(c['modeled_tax']):>9}{str(c['real_lt_modeled_clustered']):>10}")
    print("-" * 96)


def selftest():
    ok = True
    # Fixture: one market m with ask points at t=100(ask .82), t=400(.83), t=2000(.90).
    askpts = {("m", 0): [(100.0, 0.82), (400.0, 0.83), (2000.0, 0.90)]}
    # fill at t=50 price .80 -> earliest ask >=50 within 900 is t=100 ask .82 -> tax +.02
    a = match_ask(askpts, ("m", 0), 50.0, 900)
    t1 = (a == 0.82)
    # fill at t=150 price .80 -> earliest >=150 is t=400 (.83) within 900 -> tax +.03
    b = match_ask(askpts, ("m", 0), 150.0, 900)
    t2 = (b == 0.83)
    # fill at t=900 -> next ask t=2000 is 1100s away > 900 -> no match
    c = match_ask(askpts, ("m", 0), 900.0, 900)
    t3 = (c is None)
    # missing market -> None
    t4 = (match_ask(askpts, ("z", 0), 100.0, 900) is None)
    for nm, cond in (("earliest-in-window", t1), ("skip-to-next-in-window", t2),
                     ("outside-window-None", t3), ("missing-market-None", t4)):
        print(f"  [{'ok' if cond else 'FAIL'}] {nm}")
        ok = ok and cond
    # modeled_tax = 0.013 + spread
    mt = modeled_tax(3, {3: 0.0278})
    t5 = abs(mt - 0.0408) < 1e-9
    print(f"  [{'ok' if t5 else 'FAIL'}] modeled_tax band3 = {mt:.4f} (0.013+0.0278)")
    ok = ok and t5
    # iqr sanity
    lo, hi = iqr([0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08])
    t6 = lo <= 0.03 and hi >= 0.06
    print(f"  [{'ok' if t6 else 'FAIL'}] iqr [{lo},{hi}]")
    ok = ok and t6
    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--lag", type=int, default=DECISION_LAG)
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    run(lag=args.lag)


if __name__ == "__main__":
    main()
