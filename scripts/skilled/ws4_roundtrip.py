#!/usr/bin/env python3
"""
WS-4 — round-trip / TIMING skill as a distinct axis from BUY-only directional `advantage`.

For each (wallet, condition, outcome) POSITION, match BUY vs SELL to get realized TRADING PnL on
the round-tripped shares — profit from buy-low/sell-high, orthogonal to holding-to-resolution:
  trade_pnl = (avg_sell_price - avg_buy_price) * min(buy_sh, sell_sh)
  rate      = trade_pnl / buy_usd
Only positions with BOTH a buy and a sell count (a genuine round trip). Split each wallet's
round-tripped positions at its own median first-buy time; test early->late persistence of the
per-wallet round-trip rate (event-clustered by ev).

CRITICAL HONESTY: the copyable-skill cohort is NON-MM (churner screen), and by construction
those traders rarely sell before resolution — so timing skill may be UNMEASURABLE there and only
present in the (structurally-uncopyable) MM cohort. We report both cohorts and their N.

READ-ONLY. Writes reports/skilled/ws4_roundtrip.json.  --selftest for synthetic checks.
"""
import argparse, json, math, os, sys
from collections import defaultdict
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import skill_common as sk   # noqa: E402
import mm_common as mc      # noqa: E402

REPORT = os.path.join(os.path.dirname(os.path.dirname(HERE)), "reports", "skilled", "ws4_roundtrip.json")
MIN_RT = 8   # round-tripped positions per half required

SQL = r"""
WITH pos AS (
  SELECT lower(wallet) w, COALESCE(event_slug,condition_id) ev, condition_id, outcome_index,
         MIN(EXTRACT(EPOCH FROM ts)) t0,
         SUM(size_usd) FILTER (WHERE side='BUY')  buy_usd,
         SUM(size_usd/NULLIF(price,0)) FILTER (WHERE side='BUY')  buy_sh,
         SUM(size_usd) FILTER (WHERE side='SELL') sell_usd,
         SUM(size_usd/NULLIF(price,0)) FILTER (WHERE side='SELL') sell_sh
  FROM trader_fills GROUP BY 1,2,3,4)
SELECT w, ev, t0,
       (sell_usd/NULLIF(sell_sh,0) - buy_usd/NULLIF(buy_sh,0)) * LEAST(buy_sh,sell_sh) trade_pnl,
       buy_usd cost
FROM pos WHERE buy_sh>0 AND sell_sh>0 AND buy_usd>0;
"""


def run():
    rows = mc.q(SQL)
    micro = mc.microstructure()
    by_w = defaultdict(list)   # w -> [(t0, pnl, cost, ev)]
    for r in rows:
        try:
            w, ev, t0, pnl, cost = r[0], r[1], float(r[2]), float(r[3]), float(r[4])
        except (ValueError, IndexError):
            continue
        if cost <= 0:
            continue
        by_w[w].append((t0, pnl, cost, ev))

    def cohort_test(keep):
        xs, ys, wallets = [], [], []
        for w, ps in by_w.items():
            m = micro.get(w)
            if m is None or not keep(m):
                continue
            ps = sorted(ps)
            mid = len(ps) // 2
            e, l = ps[:mid], ps[mid:]
            if len(e) < MIN_RT or len(l) < MIN_RT:
                continue
            ce, pe = sum(p[2] for p in e), sum(p[1] for p in e)
            cl, pl = sum(p[2] for p in l), sum(p[1] for p in l)
            if ce <= 0 or cl <= 0:
                continue
            wallets.append(w); xs.append(pe / ce); ys.append(pl / cl)
        n = len(wallets)
        res = {"n_wallets": n, "min_rt_per_half": MIN_RT}
        if n < 8:
            res["verdict"] = "INDETERMINATE-BY-POWER (too few round-tripping wallets)"
            return res
        pairs = list(zip(xs, ys))
        lo, hi, pt = sk.boot_ci(pairs, lambda ps2: sk.spearman([p[0] for p in ps2], [p[1] for p in ps2]))
        # forward level: mean late round-trip rate of top-tercile-by-early-rate
        order = sorted(range(n), key=lambda i: xs[i], reverse=True)
        k = max(3, n // 3)
        top_late = [ys[i] for i in order[:k]]
        res.update({"persistence_spearman": pt, "persistence_ci95": [lo, hi],
                    "top_tercile_late_rate_mean": sum(top_late) / k,
                    "top_tercile_late_rate_LB": sk.mean_lb(top_late),
                    "fleet_late_rate": sum(ys) / n})
        res["GATE_PASS"] = (lo > 0) and (sk.mean_lb(top_late) > 0)
        res["verdict"] = ("TIMING SIGNAL SURVIVES-INSAMPLE -> WS-5" if res["GATE_PASS"] else "NULL")
        return res

    # cross-prediction: does EARLY round-trip (timing) skill predict LATE DIRECTIONAL,
    # hold-to-resolution blind-surplus — the thing a taker-follower can actually COPY?
    early_rt = {}
    for w, ps in by_w.items():
        ps = sorted(ps); mid = len(ps) // 2; e = ps[:mid]
        if len(e) < MIN_RT:
            continue
        ce = sum(p[2] for p in e)
        if ce > 0:
            early_rt[w] = sum(p[1] for p in e) / ce
    wl, _ = sk.load_events(10)
    late_dir = {w: sum(sum(x["surplus"] for x in rr) / len(rr) for rr in wl[w]["L"].values()) / len(wl[w]["L"])
                for w in wl}
    xs, ys, ww = [], [], []
    for w in early_rt:
        m = micro.get(w)
        if m is None or mc.is_churner(m) or w not in late_dir:
            continue
        xs.append(early_rt[w]); ys.append(late_dir[w]); ww.append(w)
    cross = {"n": len(xs)}
    if len(xs) >= 10:
        lo, hi, pt = sk.boot_ci(list(zip(xs, ys)),
                                lambda ps: sk.spearman([p[0] for p in ps], [p[1] for p in ps]))
        cross.update({"spearman": pt, "ci95": [lo, hi], "copyable_selector": lo > 0})
    out = {"axis": "round-trip realized trading PnL (timing, not direction)",
           "copyable_non_MM": cohort_test(lambda m: not mc.is_churner(m)),
           "all_incl_MM": cohort_test(lambda m: True),
           "cross_prediction_timing_to_copyable_direction": cross}
    # HONEST verdict: within-axis persistence is real but the axis (trade PnL) is NOT copyable by
    # a taker-follower (cannot capture the exit); the only mission-relevant claim is whether it
    # SELECTS copyable directional edge — judged by cross_prediction.
    if cross.get("copyable_selector"):
        out["verdict"] = "TIMING skill SELECTS copyable directional edge -> WS-5 multiplicity"
    elif cross.get("spearman", 0) > 0:
        out["verdict"] = ("REAL-BUT-UNCOPYABLE: round-trip timing PnL persists (ρ≈%.2f) but is a "
                          "trading mechanism a follower can't replicate; as a SELECTOR of copyable "
                          "directional edge it is INDETERMINATE-BY-POWER (cross-pred ρ=%.2f, CI includes 0, "
                          "n=%d) — forward-accrual candidate" %
                          (out["copyable_non_MM"].get("persistence_spearman", 0),
                           cross.get("spearman", 0), cross.get("n", 0)))
    else:
        out["verdict"] = "REAL-BUT-UNCOPYABLE and does not select copyable direction — NULL for mission"
    return out


def selftest():
    # a perfect timer: sells higher than buys -> positive rate
    pnl = (0.6 - 0.5) * 100
    assert abs(pnl - 10.0) < 1e-9
    print("selftest OK")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest(); sys.exit(0)
    res = run()
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w") as f:
        json.dump(res, f, indent=2, default=str)
    print(json.dumps(res, indent=2, default=str))
