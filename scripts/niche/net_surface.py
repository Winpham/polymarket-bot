#!/usr/bin/env python3
"""
THE NET SURFACE -- what a follower ACTUALLY nets, under a cost model that is MEASURED, not assumed.

The "copy-trading is DEAD" verdict (copy_econ.py) is  net = edge_at_follow_price - 0.03.
That 0.03 is not a measurement. It is `slippage(0.01) + fee(0.02)` (RESEARCH.md:24), and BOTH
terms are wrong in the same direction -- against us:

  * the 1c SLIPPAGE IS DOUBLE-COUNTED. copy_econ prices our entry at an ACTUAL FOLLOW-ON TAKER
    PRINT -- a real trade that really cleared at the ask. That price IS the slippage. Charging
    another 1c on top bills us twice for one spread.
  * the 2c FLAT FEE IS NOT THE FEE. Polymarket's real schedule (docs.polymarket.com/trading/fees,
    verified 2026-07, already encoded in scripts/fee_schedule_sensitivity.py) is
        fee_per_share = feeRate(category) * p * (1-p)      makers pay ZERO
    which at a sports market at p=0.6 is 0.03*0.6*0.4 = 0.72c, not 2c. It VANISHES at the
    extremes, and the favourite band is exactly where we trade.

So the verdict charged ~3c/share against a true cost of ~0.7c. This script recomputes the
follower's economics with the real schedule and NO phantom slippage. It is not an attempt to
rescue the strategy -- it also FIXES AN ERROR IN THE OPPOSITE DIRECTION:

  * copy_econ's entry price is the MEAN OF ALL PRINTS IN (t0, t0+L]. If our latency is L we
    CANNOT REACH the cheap prints at t0+1s. On a rising ramp that mean flatters us. The honest
    executor model is: observe their fill at t0, submit at t0+L, get filled at the FIRST TAKER
    PRINT AT OR AFTER t0+L. That is `P_at(L)`, and it is the number this script certifies on.
    The legacy mean-over-window is printed beside it so the two can be reconciled.

    net(L) = won - P_at(L) - feeRate(niche) * P_at(L) * (1 - P_at(L))

Also: a TRUE BLIND control (a random taker BUY in a RANDOM market+outcome). tax_anatomy's blind
control sampled within the OUTCOME THE ROSTER PICKED, so it inherited their selection -- it was
never blind. The contrast between the two is what attributes the tax.

Everything OUT-OF-SAMPLE (window B, roster fit on A), CIs bootstrapped CLUSTERED ON THE MARKET.
Same production-DB discipline as copy_econ: batched, guarded, numpy windows, never a fill-join.

  ./net_surface.py --self-test
  ./net_surface.py
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

LAGS = [2, 5, 15, 30, 60, 300, 900]

# docs.polymarket.com/trading/fees, verified 2026-07 (mirrors fee_schedule_sensitivity.REAL_FEE_RATE)
REAL_FEE_RATE = {"tennis": 0.03, "soccer": 0.03, "mlb": 0.03, "nba": 0.03, "nhl": 0.03,
                 "ufc": 0.03, "esports": 0.03, "politics": 0.04, "crypto": 0.07}
DEFAULT_FEE_RATE = 0.05          # econ / culture / weather / other
LEGACY_COST = 0.03               # the constant that produced "copy-trading is DEAD"


def real_fee(price, niche):
    return REAL_FEE_RATE.get(niche, DEFAULT_FEE_RATE) * price * (1.0 - price)


def psql(sql):
    out = subprocess.run(PG, input=GUARD + sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr[:800])
    return list(csv.DictReader(io.StringIO(out.stdout)))


def q_lit(xs):
    return ",".join("'" + str(x).replace("'", "''") + "'" for x in xs)


def cluster_boot(recs, n_boot=2000, seed=SEED):
    if not recs:
        return {"mean": 0.0, "lo": 0.0, "hi": 0.0, "n": 0, "n_markets": 0}
    by = defaultdict(list)
    for m, v in recs:
        by[m].append(v)
    k = list(by)
    s = np.array([sum(by[x]) for x in k], float)
    n = np.array([len(by[x]) for x in k], float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(k), (n_boot, len(k)))
    mu = s[idx].sum(1) / np.maximum(n[idx].sum(1), 1)
    return {"mean": float(s.sum() / n.sum()), "lo": float(np.percentile(mu, 2.5)),
            "hi": float(np.percentile(mu, 97.5)), "n": len(recs), "n_markets": len(k)}


def p_at(takers, t0, lag, excl_wallet):
    """THE EXECUTOR MODEL: first taker-BUY print at or after t0+lag = the price we really get."""
    for (t, px, w) in takers:
        if t >= t0 + lag and w != excl_wallet:
            return px
    return None


def p_mean(takers, t0, lag, excl_wallet):
    """LEGACY: mean of every print in (t0, t0+lag]  -- includes prints we could not have reached."""
    o = [px for (t, px, w) in takers if t0 < t <= t0 + lag and w != excl_wallet]
    return float(np.mean(o)) if o else None


# ------------------------------------------------------------------------------- self-test
def self_test():
    tk = [(0.0, 0.50, "A"), (1.0, 0.52, "B"), (10.0, 0.58, "C"), (100.0, 0.61, "D")]
    # executor model: at lag 5 we cannot have the 0.52 print at t=1 -- we get 0.58 at t=10
    assert p_at(tk, 0.0, 5, "A") == 0.58
    assert p_at(tk, 0.0, 0.5, "A") == 0.52
    assert p_at(tk, 0.0, 500, "A") is None
    assert p_at(tk, 0.0, 5, "C") == 0.61          # own-wallet excluded
    # legacy mean is CHEAPER than the executor price on a rising ramp -- the bias we are fixing
    assert p_mean(tk, 0.0, 10, "A") == (0.52 + 0.58) / 2
    assert p_mean(tk, 0.0, 10, "A") < p_at(tk, 0.0, 10, "A")

    # the fee really does vanish at the extremes, and really is far under the 2c buffer
    assert abs(real_fee(0.60, "soccer") - 0.03 * 0.6 * 0.4) < 1e-12
    assert real_fee(0.60, "soccer") < 0.02          # < the frozen buffer
    assert real_fee(0.95, "soccer") < real_fee(0.60, "soccer")
    assert real_fee(0.50, "crypto") > real_fee(0.50, "soccer")
    assert abs(real_fee(0.50, "weather") - 0.05 * 0.25) < 1e-12   # default rate

    r = cluster_boot([("m1", 0.01)] * 10 + [("m2", 0.03)] * 10, n_boot=400)
    assert r["n_markets"] == 2 and abs(r["mean"] - 0.02) < 1e-9
    print("self-test OK")
    return 0


# ------------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--roster", default="reports/niche/global_profit_floor20.json")
    ap.add_argument("--ranker", default="eb_shrunk")
    ap.add_argument("--out", default="reports/niche/net_surface.json")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test())

    R = [r for r in json.load(open(a.roster)) if r["ranker"] == a.ranker][0]["roster"]
    wallets = [w["wallet"] for w in R]
    print(f"roster: top-{len(wallets)} by {a.ranker}   (window B = OUT-OF-SAMPLE)\n")

    wfilt = ("AND h.condition_id IN (SELECT condition_id FROM ("
             "  SELECT condition_id, MAX(ts) mts FROM harvest_wm GROUP BY 1) x "
             "  WHERE x.mts > (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY mts) "
             "                 FROM (SELECT condition_id, MAX(ts) mts FROM harvest_wm "
             "                       GROUP BY 1) y))")
    sigs = psql(f"""
      WITH res AS (SELECT condition_id, outcome_index, BOOL_OR(outcome_won) won
                   FROM trader_fills WHERE resolved AND outcome_won IS NOT NULL GROUP BY 1,2),
      ok AS (SELECT condition_id, niche, n_trades FROM harvest_markets WHERE NOT truncated)
      SELECT h.condition_id, h.outcome_index, h.wallet,
             EXTRACT(EPOCH FROM h.ts) t, h.price p, h.size_usd sz,
             (r.won::int)::float8 won, ok.niche, ok.n_trades
      FROM harvest_fills h
      JOIN ok ON ok.condition_id = h.condition_id
      JOIN res r ON r.condition_id=h.condition_id AND r.outcome_index=h.outcome_index
      WHERE h.side='BUY' AND h.is_maker=false AND h.wallet IN ({q_lit(wallets)})
        {wfilt};
    """)
    print(f"{len(sigs):,} roster taker-BUY signals")
    mkts = sorted({s["condition_id"] for s in sigs})
    print(f"across {len(mkts):,} markets -- streaming\n")

    takers = defaultdict(list)
    for i in range(0, len(mkts), BATCH):
        for r in psql(f"""
              SELECT condition_id, outcome_index, wallet,
                     EXTRACT(EPOCH FROM ts) t, price p
              FROM harvest_fills
              WHERE side='BUY' AND is_maker=false
                AND condition_id IN ({q_lit(mkts[i:i+BATCH])});"""):
            takers[(r["condition_id"], r["outcome_index"])].append(
                (float(r["t"]), float(r["p"]), r["wallet"]))
        sys.stdout.write(f"\r  {min(i+BATCH, len(mkts)):,}/{len(mkts):,}")
        sys.stdout.flush()
    for k in takers:
        takers[k].sort(key=lambda x: x[0])
    print(f"\n  taker tape: {sum(len(v) for v in takers.values()):,} prints\n")

    out = {"meta": {"real_fee_rate": REAL_FEE_RATE, "default": DEFAULT_FEE_RATE,
                    "legacy_cost": LEGACY_COST, "n_signals": len(sigs)}}

    # ---------------------------------------------------------- their own price (the ceiling)
    own = [(s["condition_id"], float(s["won"]) - float(s["p"])) for s in sigs]
    b0 = cluster_boot(own)
    print("=" * 92)
    print("THE FOLLOWER'S REAL ECONOMICS   (executor model: submit at t0+lag, fill at next taker print)")
    print("=" * 92)
    print(f"{'lag':>6s} {'tax':>8s} {'gross edge':>11s} {'95% CI':>20s} "
          f"{'real fee':>9s} {'NET (real)':>11s} {'net LB':>9s} {'legacy -3c':>11s} {'n':>6s}")
    print("-" * 92)
    print(f"{'THEIRS':>6s} {'--':>8s} {b0['mean']:>+11.4f} [{b0['lo']:+.4f},{b0['hi']:+.4f}] "
          f"{'--':>9s} {'--':>11s} {'--':>9s} {'--':>11s} {b0['n']:>6,}")

    out["lags"] = {}
    per_lag_rows = {}
    for L in LAGS:
        tax, gross, net = [], [], []
        rows = []
        for s in sigs:
            key = (s["condition_id"], s["outcome_index"])
            t0, p0, w0 = float(s["t"]), float(s["p"]), s["wallet"]
            px = p_at(takers.get(key, []), t0, L, w0)
            if px is None:
                continue
            f = real_fee(px, s["niche"])
            won = float(s["won"])
            cid = s["condition_id"]
            tax.append((cid, px - p0))
            gross.append((cid, won - px))
            net.append((cid, won - px - f))
            rows.append({"cid": cid, "niche": s["niche"], "sz": float(s["sz"]),
                         "p_exec": px, "net": won - px - f, "gross": won - px,
                         "n_trades": int(s["n_trades"])})
        if len(net) < 100:
            continue
        bt, bg, bn = cluster_boot(tax), cluster_boot(gross), cluster_boot(net)
        fee_m = float(np.mean([real_fee(r["p_exec"], r["niche"]) for r in rows]))
        lab = f"{L}s" if L < 60 else f"{L//60}m"
        flag = "  <<<" if bn["lo"] > 0 else ""
        print(f"{lab:>6s} {bt['mean']:>+8.4f} {bg['mean']:>+11.4f} "
              f"[{bg['lo']:+.4f},{bg['hi']:+.4f}] {fee_m:>9.4f} {bn['mean']:>+11.4f} "
              f"{bn['lo']:>+9.4f} {bg['mean']-LEGACY_COST:>+11.4f} {bn['n']:>6,}{flag}")
        out["lags"][L] = {"tax": bt, "gross": bg, "net": bn, "mean_fee": fee_m}
        per_lag_rows[L] = rows

    print("\n  'legacy -3c' is the column that produced the DEAD verdict. 'NET (real)' is the same")
    print("  edge against the cost we actually pay. net LB>0 (marked <<<) = survives at 95%.\n")

    # ---------------------------------------------------------- the surface, at the best lag
    BEST = 5
    rows = per_lag_rows.get(BEST, [])
    if rows:
        print("=" * 92)
        print(f"THE SURFACE at a {BEST}s lag -- WHERE does the net survive?")
        print("=" * 92)

        def cells(name, keyfn, order=None):
            print(f"\n-- by {name}")
            print(f"{name:>22s} {'net':>9s} {'95% CI':>20s} {'gross':>8s} {'fee':>7s} {'n':>6s}")
            g = defaultdict(list)
            for r in rows:
                g[keyfn(r)].append(r)
            ks = order or sorted(g, key=lambda k: -len(g[k]))
            res = {}
            for k in ks:
                if k not in g or len(g[k]) < 80:
                    continue
                bb = cluster_boot([(r["cid"], r["net"]) for r in g[k]])
                gg = cluster_boot([(r["cid"], r["gross"]) for r in g[k]])
                ff = float(np.mean([real_fee(r["p_exec"], r["niche"]) for r in g[k]]))
                flag = "  <<<" if bb["lo"] > 0 else ""
                print(f"{str(k):>22s} {bb['mean']:>+9.4f} [{bb['lo']:+.4f},{bb['hi']:+.4f}] "
                      f"{gg['mean']:>+8.4f} {ff:>7.4f} {bb['n']:>6,}{flag}")
                res[str(k)] = {"net": bb, "gross": gg, "fee": ff}
            return res

        szq = np.quantile([r["sz"] for r in rows], [0, .25, .5, .75, 1.0])

        def szc(r):
            for i in range(4):
                if r["sz"] <= szq[i + 1]:
                    return f"${szq[i]:.0f}-${szq[i+1]:.0f}"
            return f"${szq[3]:.0f}+"

        out["surface"] = {
            "niche": cells("niche", lambda r: r["niche"]),
            "price band": cells("price band", lambda r: f"{int(r['p_exec']*5)*20}-{int(r['p_exec']*5)*20+20}c",
                                order=["0-20c", "20-40c", "40-60c", "60-80c", "80-100c"]),
            "their size": cells("their size", szc),
            "mkt depth": cells("mkt depth", lambda r: ("thin <200" if r["n_trades"] < 200 else
                                                       ("mid 200-1k" if r["n_trades"] < 1000
                                                        else "deep >1k")),
                               order=["thin <200", "mid 200-1k", "deep >1k"]),
        }

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(out, f, indent=2, default=float)
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
