#!/usr/bin/env python3
"""
LATENCY-COST — does being slow actually COST us anything?

The premise under scrutiny: our detect->act path is ~10-15 min, and that "feels" far too slow. Before
building a low-latency path (a real engineering project: websocket-driven detection, a hot order path,
new failure modes), MEASURE THE THING IT WOULD BUY. The lever is only worth pulling if the price we can
buy at actually DEGRADES while we wait.

This reads the live CLOB tape (`clob_price_tape`, best_ask at ~seconds granularity) and reconstructs, for
every market the sharps converged on, the ACTUAL ask a follower would have paid at t0, +1, +5, +15, +30,
+60 minutes after the convergence instant. That IS the cost of latency, measured, per minute of delay.

  cost(t) = ask(t0 + t) - ask(t0)     -- what waiting t minutes costs a buyer, in cents

Read this against the numbers that already exist:
  - the whole spread we cross is  ~1.2c
  - slippage at $50/signal is     ~2.2c (p90)  <- the BOOK is the binding constraint
So a latency fix is only worth building if cost(15min) is material against ~1-2c. If ask(t0+15) is flat,
the delay is free and the engineering would buy accuracy, not edge.

CRITICALLY, THE MEAN IS NOT THE ANSWER. Averaging winners and losers hides the mechanism: if the price
runs away on the picks that WIN and sits still on the picks that LOSE, then a slow follower is adversely
selected even when the AVERAGE drift is zero. So every number here is also split by outcome. A flat mean
with a wide won/lost split means latency is expensive in exactly the way an average cannot see.

Read-only. Self-test: ./latency_cost.py --selftest
"""

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cell_lib as C  # noqa: E402

WIDE_CUTOFF = 250
LO, HI = 0.71, 0.90
HORIZONS = [1, 5, 15, 30, 60]      # minutes after convergence
TOL_MIN = 3                        # accept a tape tick within +/- this of the target
REPORTS = Path(__file__).resolve().parent.parent / "reports"


def fetch_curve(family_rx="temperature"):
    """For each sharp convergence, the tape's best_ask at t0 and at each horizon.

    t0 = the convergence instant (the 3rd one-sided backer's fill) — the earliest moment ANY follower,
    however fast, could possibly have known. Everything is measured relative to that, so this isolates
    latency and nothing else.
    """
    horizon_sql = ",\n".join(
        f"""(SELECT t.best_ask FROM clob_price_tape t
             WHERE t.condition_id=c.condition_id AND t.outcome_index=c.outcome_index
               AND t.best_ask IS NOT NULL
               AND t.recv_at BETWEEN c.ts0 + interval '{h} min' - interval '{TOL_MIN} min'
                                 AND c.ts0 + interval '{h} min' + interval '{TOL_MIN} min'
             ORDER BY abs(EXTRACT(EPOCH FROM (t.recv_at - (c.ts0 + interval '{h} min'))))
             LIMIT 1) AS ask_{h}"""
        for h in HORIZONS
    )
    rows = C.q(f"""
    WITH e AS (
      SELECT f.condition_id, f.outcome_index, LOWER(f.wallet) w, AVG(f.price) px, MIN(f.ts) ts,
             MAX(f.slug) slug, BOOL_OR(f.resolved) rz, BOOL_OR(f.outcome_won) won
      FROM trader_fills f JOIN followed_traders ft ON ft.proxy_wallet=f.wallet
      WHERE f.side='BUY' AND ft.rank<={WIDE_CUTOFF} AND f.slug ~ '{family_rx}'
        AND f.ts >= '2026-07-10'
      GROUP BY 1,2,3),
    e1 AS (SELECT e.* FROM e WHERE NOT EXISTS
      (SELECT 1 FROM e x WHERE x.condition_id=e.condition_id AND x.w=e.w
                           AND x.outcome_index<>e.outcome_index)),
    c AS (
      SELECT condition_id, outcome_index, MAX(slug) slug, count(*) nb, AVG(px) sharp_px,
             BOOL_OR(rz) rz, BOOL_OR(won) won,
             (ARRAY_AGG(ts ORDER BY ts))[3] AS ts0     -- the 3rd backer = the convergence instant
      FROM e1 GROUP BY 1,2
      HAVING count(*)>=3 AND AVG(px) BETWEEN {LO} AND {HI})
    SELECT c.condition_id, c.outcome_index, c.slug, c.sharp_px, c.rz, c.won, c.ts0,
      (SELECT t.best_ask FROM clob_price_tape t
        WHERE t.condition_id=c.condition_id AND t.outcome_index=c.outcome_index
          AND t.best_ask IS NOT NULL AND t.recv_at BETWEEN c.ts0 AND c.ts0 + interval '{TOL_MIN} min'
        ORDER BY t.recv_at LIMIT 1) AS ask_0,
      {horizon_sql}
    FROM c WHERE c.ts0 IS NOT NULL;
    """)
    out = []
    ncols = 8 + len(HORIZONS)   # base cols + ask_0 + one per horizon
    for r in rows:
        # psql -At drops TRAILING empty fields, and an all-NULL horizon tail is exactly that — pad, or
        # the unpack silently loses the markets with no tape coverage (the ones we most need to count).
        r = (list(r) + [None] * ncols)[:ncols]
        cond, oi, slug, px, rz, won, ts0, ask0, *hs = r
        if ask0 in (None, ""):
            continue
        rec = {"key": f"{cond}:{oi}", "slug": slug, "sharp_px": float(px),
               "resolved": rz == "t", "won": won == "t", "ask0": float(ask0)}
        for h, v in zip(HORIZONS, hs):
            rec[f"ask_{h}"] = float(v) if v not in (None, "") else None
        out.append(rec)
    return out


def summarize(recs, label):
    print(f"\n=== {label}  (n={len(recs)} convergences with a tape ask at t0)")
    if not recs:
        print("  no tape coverage — cannot measure")
        return {}
    print(f"{'wait':>6} {'n':>5} {'cost mean':>10} {'cost p50':>9} {'cost p90':>9}  "
          f"{'cost|WON':>9} {'cost|LOST':>10}")
    curve = {}
    for h in HORIZONS:
        d = [(r[f"ask_{h}"] - r["ask0"], r) for r in recs if r.get(f"ask_{h}") is not None]
        if not d:
            continue
        costs = [x for x, _ in d]
        won = [x for x, r in d if r["resolved"] and r["won"]]
        lost = [x for x, r in d if r["resolved"] and not r["won"]]
        s = sorted(costs)
        q = lambda a, f: a[min(int(f * len(a)), len(a) - 1)] if a else float("nan")  # noqa: E731
        row = {
            "n": len(costs),
            "mean": round(statistics.fmean(costs), 4),
            "p50": round(q(s, .5), 4),
            "p90": round(q(s, .9), 4),
            "cost_if_won": round(statistics.fmean(won), 4) if won else None,
            "cost_if_lost": round(statistics.fmean(lost), 4) if lost else None,
        }
        curve[h] = row
        cw = f"{row['cost_if_won']*100:>8.2f}¢" if row["cost_if_won"] is not None else "       —"
        cl = f"{row['cost_if_lost']*100:>9.2f}¢" if row["cost_if_lost"] is not None else "        —"
        print(f"{h:>4}m {row['n']:>6} {row['mean']*100:>9.2f}¢ {row['p50']*100:>8.2f}¢ "
              f"{row['p90']*100:>8.2f}¢ {cw} {cl}")
    return curve


def selftest():
    ok = True
    recs = [
        # price RUNS AWAY on winners (+4c), SITS STILL on losers (0c): mean is a misleading +2c
        {"ask0": 0.80, "ask_15": 0.84, "resolved": True, "won": True},
        {"ask0": 0.80, "ask_15": 0.80, "resolved": True, "won": False},
    ]
    for h in HORIZONS:
        for r in recs:
            r.setdefault(f"ask_{h}", None)
    recs[0]["ask_15"], recs[1]["ask_15"] = 0.84, 0.80
    c = summarize(recs, "selftest (adverse-selection shape)")
    if 15 not in c:
        print("FAIL no curve"); ok = False
    else:
        if abs(c[15]["mean"] - 0.02) > 1e-9:
            print(f"FAIL mean {c[15]['mean']}"); ok = False
        # The whole point: the split must expose what the mean hides.
        if abs(c[15]["cost_if_won"] - 0.04) > 1e-9 or abs(c[15]["cost_if_lost"] - 0.0) > 1e-9:
            print("FAIL won/lost split must separate"); ok = False
    print("latency_cost selftest: PASS" if ok else "latency_cost selftest: FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", default="temperature")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        raise SystemExit(selftest())
    recs = fetch_curve(a.family)
    curve = summarize(recs, f"LATENCY COST — family ~{a.family}")
    print("\nBenchmarks to judge against: spread we cross ~1.2¢ | slippage @$50 ~2.2¢ (p90).")
    print("If cost(15m) is small vs those, LATENCY IS NOT THE BINDING CONSTRAINT and a low-latency")
    print("path buys accuracy, not edge. Check cost|WON separately: a flat MEAN with a big won/lost")
    print("split means slow followers are adversely selected in a way the average cannot show.")
    (REPORTS / "LATENCY-COST.json").write_text(
        json.dumps({"family": a.family, "n": len(recs), "curve": curve}, indent=2))
    print("\nwrote LATENCY-COST.json")


if __name__ == "__main__":
    main()
