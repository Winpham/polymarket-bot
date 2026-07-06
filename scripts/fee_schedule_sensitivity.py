#!/usr/bin/env python3
"""
FEE-SCHEDULE SENSITIVITY — does the REAL Polymarket 2026 taker-fee schedule (not the frozen 2%
buffer) change the net-after-tax bankability verdict, and is the MAKER path the only configuration
whose cluster-robust lower bound clears zero?

WHY (post-hoc, NOT a pre-registration change): the frozen instruments (regime_net_edge, copyability)
use FEE = 0.02·price — a deliberately CONSERVATIVE buffer, pre-registered in
reports/PREREG_20260704T191458Z_regime_persistence.md. Polymarket's real taker fee (verified
2026-07 from docs.polymarket.com/trading/fees) is  fee = shares · feeRate · p · (1−p)  with feeRate
by category (sports 0.03, politics 0.04, econ/other 0.05, crypto 0.07; world/geopolitics 0). That
real fee is SMALLER than the buffer at favorite prices and MAKERS PAY ZERO (plus a 20–25% rebate).
Silently swapping the frozen number for a smaller one that flatters the strategy is exactly the
goalpost-move the pre-registration exists to block — so this is a SEPARATE sensitivity read, printed
side-by-side, that leaves the frozen instruments untouched and asks one honest question:

    under the real fee, does any NET_POSITIVE flag flip that the 2% buffer didn't?

For the favorite arm, per (sport|month) regime + pooled, at at-fire entry, flat-shares, over the
MATCHED (category×band) blind baseline (reg._matched_baseline — byte-identical), it reports GROSS and:
  net_taker_buffer  = gross − band_spread − follower_tax − 0.02·p        (frozen; the pessimistic bound)
  net_taker_real    = gross − band_spread − follower_tax − feeRate(c)·p·(1−p)   (real schedule)
  net_taker_zero    = gross − band_spread − follower_tax − 0             (fee floor = generous taker)
  net_maker_real    = gross − follower_tax + adverse_sel_gap − 0         (maker: no spread, no fee;
                      rebate = UNMODELED upside; carries the ~28% FILL-RATE caveat from maker_fill_sim)
each with a day-clustered cluster-robust LB (small-cluster t(G−1), reg.lb_small_cluster) and a
net_positive = LB>0 flag. Read-only, paper-only, promotes nothing, edits no frozen artifact.

  ./fee_schedule_sensitivity.py             # live per-regime table + verdict; writes JSON
  ./fee_schedule_sensitivity.py --selftest  # real fee < buffer at favorite prices; maker beats taker;
                                            #   zero-fee taker still can't rescue a spread-dominated cell
"""

import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import selection_null as sn          # band()
import effective_n as en             # cluster_robust()
import regime_edge as reg            # _matched_baseline, _events, _band_spreads, ARMS, lb_small_cluster, REPORT_DIR
import regime_net_edge as rne        # _maker_gaps (adverse-selection gap + fill rate)

# Polymarket 2026 taker feeRate by our taxonomy category (docs.polymarket.com/trading/fees,
# verified 2026-07). Sports 0.03; politics 0.04; econ/culture/weather/other 0.05; crypto 0.07;
# world/geopolitics fee-free (none of our sports categories are geopolitical — fifwc = World Cup =
# a SPORTS market, so soccer stays 0.03). Makers pay 0 in every category (+ 20–25% rebate).
REAL_FEE_RATE = {
    "tennis": 0.03, "soccer": 0.03, "mlb": 0.03, "nfl/cfb": 0.03,
    "nba/cbb": 0.03, "nhl": 0.03, "wnba": 0.03, "esports": 0.03,
    "politics/elections": 0.04,
    "econ/other": 0.05, "other": 0.05,
    "crypto": 0.07,
}
DEFAULT_FEE_RATE = 0.05
FOLLOWER_TAX = reg.FOLLOWER_TAX      # 0.013
BUFFER_FEE = 0.02                    # the frozen pre-registered buffer (for the side-by-side)
REPORT_DIR = reg.REPORT_DIR


def real_taker_fee(price, cat):
    """Per-share taker fee under the real schedule: feeRate(category)·p·(1−p)."""
    return REAL_FEE_RATE.get(cat, DEFAULT_FEE_RATE) * price * (1.0 - price)


def _lb(series, ev_cl):
    """Day-clustered cluster-robust mean + small-cluster-t LB (reg.lb_small_cluster). LB None for G<2."""
    if not series:
        return None, None
    cr = en.cluster_robust(series, ev_cl)
    mean = cr["theta"] if cr else float(np.mean(list(series.values())))
    G = cr["G"] if cr else len({d for d in ev_cl.values()})
    lb = reg.lb_small_cluster(mean, cr["se_CR"] if cr else None, G)
    return mean, lb


def _net_variants(ev_subset, spreads, gap):
    """Per-event gross + the four net series (taker buffer/real/zero, maker real)."""
    g, tb, tr, tz, mk = {}, {}, {}, {}, {}
    for k, v in ev_subset.items():
        s, p, cat, b = v["surplus"], v["entry"], v["sport"], sn.band(v["entry"])
        spread = spreads.get(b, 0.0)
        g[k] = s
        tb[k] = s - spread - FOLLOWER_TAX - BUFFER_FEE * p
        tr[k] = s - spread - FOLLOWER_TAX - real_taker_fee(p, cat)
        tz[k] = s - spread - FOLLOWER_TAX - 0.0
        mk[k] = s - FOLLOWER_TAX + (gap if gap is not None else 0.0) - 0.0   # maker: no spread, no fee
    return g, tb, tr, tz, mk


def _read(ev_subset, spreads, gap):
    ev_cl = {k: v["day"] for k, v in ev_subset.items()}
    g, tb, tr, tz, mk = _net_variants(ev_subset, spreads, gap)
    out = {"n_events": len(ev_subset), "n_clusters": len({d for d in ev_cl.values()})}
    for name, series in (("gross", g), ("net_taker_buffer", tb), ("net_taker_real", tr),
                         ("net_taker_zero", tz), ("net_maker_real", mk)):
        m, lb = _lb(series, ev_cl)
        out[name] = m
        out[name + "_lb"] = lb
        out[name + "_positive"] = (lb is not None and lb > 0)
    return out


def analyze(rows, spreads=None, gap=None):
    if spreads is None:
        spreads = reg._band_spreads()
    if gap is None:
        g2 = rne._maker_gaps()
        gap = g2.get("gap_fee2")   # adverse-selection gap is fee-independent (a win-rate delta)
    blind = [r for r in rows if r["strategy"] == "_blind"]
    baseline = reg._matched_baseline(blind)
    prows = [r for r in rows if r["strategy"] == "favorite"]
    ev = reg._events(prows, baseline)
    out = {"meta": {"real_fee_rate": REAL_FEE_RATE, "buffer_fee": BUFFER_FEE,
                    "follower_tax": FOLLOWER_TAX, "adverse_sel_gap": gap,
                    "band_spreads": {str(k): v for k, v in sorted(spreads.items())},
                    "note": "post-hoc sensitivity; frozen instruments untouched; maker rebate UNMODELED upside"},
           "arms": {}}
    if not ev:
        out["arms"]["favorite"] = {"n_events": 0}
        return out
    pooled = _read(ev, spreads, gap)
    by_reg = defaultdict(dict)
    for k, v in ev.items():
        by_reg[v["regime_id"]][k] = v
    regimes = {}
    for rid, sub in by_reg.items():
        r = _read(sub, spreads, gap)
        r["regime_type"] = next(iter(sub.values()))["regime_type"]
        regimes[rid] = r
    # the honest headline: does REAL flip a positive the BUFFER missed? is MAKER the only clearer?
    flips = [rid for rid, r in regimes.items()
             if r["net_taker_real_positive"] and not r["net_taker_buffer_positive"]]
    taker_zero_clears = [rid for rid, r in regimes.items() if r["net_taker_zero_positive"]]
    maker_clears = [rid for rid, r in regimes.items() if r["net_maker_real_positive"]]
    out["arms"]["favorite"] = {"pooled": pooled, "regimes": regimes,
                               "real_flips_a_buffer_negative": sorted(flips),
                               "taker_zerofee_clears": sorted(taker_zero_clears),
                               "maker_clears": sorted(maker_clears)}
    return out


def _f(x, spec="+.2%"):
    return "   n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else format(x, spec)


def _flag(r, key):
    lb = r.get(key + "_lb")
    return f"{_f(r.get(key))}{'✓' if r.get(key + '_positive') else ' '}"


def run_live():
    rows = reg.smod.fetch()
    res = analyze(rows)
    a = res["arms"]["favorite"]
    if not a.get("pooled"):
        print("no favorite events"); return res
    p = a["pooled"]
    print("FEE-SCHEDULE SENSITIVITY · favorite arm · real Polymarket 2026 taker fee vs frozen 2% buffer")
    print("  (frozen instruments untouched · maker fee=0 + rebate UNMODELED · ✓ = cluster-robust LB>0)\n")
    print(f"── POOLED · {p['n_events']} events / {p['n_clusters']} day-clusters ──")
    print(f"   gross            {_f(p['gross'])}  (LB {_f(p['gross_lb'])})")
    print(f"   net_taker buffer {_flag(p,'net_taker_buffer')}  (LB {_f(p['net_taker_buffer_lb'])})   ← frozen/pessimistic")
    print(f"   net_taker REAL   {_flag(p,'net_taker_real')}  (LB {_f(p['net_taker_real_lb'])})   ← real schedule")
    print(f"   net_taker zero   {_flag(p,'net_taker_zero')}  (LB {_f(p['net_taker_zero_lb'])})   ← fee floor (generous)")
    print(f"   net_maker REAL   {_flag(p,'net_maker_real')}  (LB {_f(p['net_maker_real_lb'])})   ← maker (no spread/fee)\n")
    hdr = (f"   {'regime':<22}{'ev':>4}{'clus':>5}{'gross':>9}{'tk_buf':>9}{'tk_real':>9}"
           f"{'tk_zero':>9}{'mk_real':>9}")
    print(hdr)
    for rid in sorted(a["regimes"], key=lambda r: -(a["regimes"][r]["gross"] or -9)):
        r = a["regimes"][rid]
        print(f"   {rid:<22}{r['n_events']:>4}{r['n_clusters']:>5}{_f(r['gross']):>9}"
              f"{_flag(r,'net_taker_buffer'):>10}{_flag(r,'net_taker_real'):>10}"
              f"{_flag(r,'net_taker_zero'):>10}{_flag(r,'net_maker_real'):>10}")
    print("-" * 78)
    print(f"   real fee flips a buffer-negative to positive?  {a['real_flips_a_buffer_negative'] or 'NO — none'}")
    print(f"   taker clears even at ZERO fee (regimes):        {a['taker_zerofee_clears'] or 'NONE'}")
    print(f"   maker path clears (regimes):                    {a['maker_clears'] or 'NONE'}")
    pooled_verdict = ("MAKER-ONLY" if p["net_maker_real_positive"] and not p["net_taker_real_positive"]
                      else "TAKER-CLEARS" if p["net_taker_real_positive"] else "NOTHING-CLEARS")
    print(f"\n   POOLED verdict: {pooled_verdict} — "
          + ("the real fee sharpens the taker point estimate but the binding constraint is the SPREAD + "
             "small-cluster power, not the fee; the only LB>0 config is the maker path (fill-rate caveat)."
             if pooled_verdict == "MAKER-ONLY" else
             "read the flags above."))
    out = os.path.join(REPORT_DIR, "fee_schedule_sensitivity.json")
    with open(out, "w") as f:
        json.dump(res, f, indent=1, default=str)
    print(f"\nartifact → reports/fee_schedule_sensitivity.json")
    return res


# --------------------------------------------------------------------------------------------
def _selftest():
    ok = True
    # (1) at a favorite price the real sports fee is well below the 2% buffer.
    p = 0.82
    real = real_taker_fee(p, "mlb")          # 0.03·0.82·0.18 ≈ 0.00443
    buf = BUFFER_FEE * p                      # 0.0164
    c1 = real < buf and abs(real - 0.03 * 0.82 * 0.18) < 1e-9
    ok = ok and c1
    print(f"  [{'ok' if c1 else 'FAIL'}] real sports fee @0.82 = {real:.4f} < 2% buffer {buf:.4f}")

    # (2) crypto costs more than sports (0.07 vs 0.03); fee peaks at p=0.5, shrinks toward extremes.
    c2 = (real_taker_fee(0.82, "crypto") > real_taker_fee(0.82, "mlb")
          and real_taker_fee(0.5, "mlb") > real_taker_fee(0.82, "mlb"))
    ok = ok and c2
    print(f"  [{'ok' if c2 else 'FAIL'}] crypto>{'sports'} and fee(0.5)>fee(0.82) (p(1−p) shape)")

    # (3) a spread-dominated cell: gross 3% at price 0.75 (band 4), 5¢ spread — even ZERO fee can't
    #     rescue the taker (3 − 5 − 1.3 − 0 = −3.3%), but the maker (no spread) does far better.
    spreads = {4: 0.05}
    days = ["2026-07-01", "2026-07-02", "2026-07-03"]
    ev = {}
    i = 0
    for d in days:
        for _ in range(6):
            ev[f"e{i}"] = {"surplus": 0.03, "entry": 0.75, "day": d, "sport": "mlb",
                           "regime_type": "recurring"}
            i += 1
    r = _read(ev, spreads, gap=-0.0069)
    c3 = (r["net_taker_zero"] < 0 and not r["net_taker_zero_positive"]
          and r["net_maker_real"] > r["net_taker_real"])
    ok = ok and c3
    print(f"  [{'ok' if c3 else 'FAIL'}] spread-dominated: taker_zero {_f(r['net_taker_zero'])} still <0 "
          f"(fee isn't the killer); maker {_f(r['net_maker_real'])} > taker_real {_f(r['net_taker_real'])}")

    # (4) real fee sits BETWEEN buffer and zero for the taker (monotone in fee).
    c4 = r["net_taker_zero"] >= r["net_taker_real"] >= r["net_taker_buffer"]
    ok = ok and c4
    print(f"  [{'ok' if c4 else 'FAIL'}] taker net monotone: zero {_f(r['net_taker_zero'])} ≥ real "
          f"{_f(r['net_taker_real'])} ≥ buffer {_f(r['net_taker_buffer'])}")

    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        run_live()
