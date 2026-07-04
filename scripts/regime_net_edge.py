#!/usr/bin/env python3
"""
NET-EDGE-AFTER-TAX PER REGIME — even if it persists, in WHICH regimes is it net-positive after the
copyability tax, and is any RECURRING regime net-positive? (PREREG §5.)

For each arm × regime (regime = sport_category × month), per event, at the AT-FIRE entry, flat-shares:
  gross      = event-clustered surplus over the matched (cat×band) blind baseline (regime_edge).
  net_taker  = gross − band_spread(band) − FOLLOWER_TAX − FEE·price   (the copy path: cross the
               spread, pay the follower lag tax + fee; band_spread + follower_tax from copyability.json).
  net_maker  = gross − FOLLOWER_TAX + adverse_selection_gap − FEE·price  (post a limit at δ=0¢ for 5m
               → no spread crossed, but suffer the measured adverse-selection gap; maker_fill_sim.json
               policy maker_+0c_5m). Carries a ~28% FILL-RATE caveat (surfaced, not hidden).
Each in BOTH fee=2%-buffer and fee=0 columns. A regime is `net_positive` iff its tax-netted
cluster-robust LB > 0 (PREREG §5; effective_n.cluster_robust, day-clustered).

Answers the honest question: a +8% gross soccer cell nets positive; a +3% gross cell under a ~5% tax
nets NEGATIVE (not bankable even if the edge is real). Reuses regime_edge (events + baseline +
cluster count) and the two tax artifacts byte-identically. Read-only, paper-only, promotes nothing.

Constants frozen in reports/PREREG_20260704T191458Z_regime_persistence.md.

Modes:
  ./regime_net_edge.py             # live gross→net_taker→net_maker per regime + net_positive flags; JSON
  ./regime_net_edge.py --selftest  # +8% gross nets positive; +3% gross under 5% tax nets negative
"""

import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import selection_null as sn        # band()
import effective_n as en          # cluster_robust()
import regime_edge as reg         # _matched_baseline, _events, _band_spreads, ARMS, Z, FOLLOWER_TAX, FEE
import regime_classify as rc

PREREG = "reports/PREREG_20260704T191458Z_regime_persistence.md"
ARMS = reg.ARMS
Z = reg.Z
FOLLOWER_TAX = reg.FOLLOWER_TAX      # 0.013
REPORT_DIR = reg.REPORT_DIR


def _maker_gaps():
    """adverse_selection_gap + fill_rate for maker_+0c_5m, both fee bases (maker_fill_sim.json)."""
    try:
        with open(os.path.join(REPORT_DIR, "maker_fill_sim.json")) as f:
            pol = json.load(f)["policies"]
        m2 = pol["fee_2pct_buffer"]["maker_+0c_5m"]
        m0 = pol["fee_zero"]["maker_+0c_5m"]
        return {"gap_fee2": float(m2["adverse_selection_gap"]), "gap_fee0": float(m0["adverse_selection_gap"]),
                "fill_rate": float(m2["fill_rate"])}
    except Exception:
        return {"gap_fee2": None, "gap_fee0": None, "fill_rate": None}


def _lb(series, ev_cl):
    """cluster-robust LB (day-clustered) of a per-event series; (mean, lb) — lb None if <2 clusters."""
    if not series:
        return None, None
    cr = en.cluster_robust(series, ev_cl)
    mean = cr["theta"] if cr else float(np.mean(list(series.values())))
    lb = mean - Z * cr["se_CR"] if cr and math.isfinite(cr["se_CR"]) else None
    return mean, lb


def _net_series(ev_subset, spreads, gaps):
    """Per-event gross + the four net variants over a set of events."""
    g, ntf2, ntf0, nmf2, nmf0 = {}, {}, {}, {}, {}
    for k, v in ev_subset.items():
        s, p, b = v["surplus"], v["entry"], sn.band(v["entry"])
        spread = spreads.get(b, 0.0)
        g[k] = s
        ntf2[k] = s - spread - FOLLOWER_TAX - 0.02 * p
        ntf0[k] = s - spread - FOLLOWER_TAX - 0.00 * p
        if gaps["gap_fee2"] is not None:
            nmf2[k] = s - FOLLOWER_TAX + gaps["gap_fee2"] - 0.02 * p
            nmf0[k] = s - FOLLOWER_TAX + gaps["gap_fee0"] - 0.00 * p
    return g, ntf2, ntf0, nmf2, nmf0


def _read(ev_subset, spreads, gaps):
    ev_cl = {k: v["day"] for k, v in ev_subset.items()}
    g, ntf2, ntf0, nmf2, nmf0 = _net_series(ev_subset, spreads, gaps)
    gm, glb = _lb(g, ev_cl)
    out = {"n_events": len(ev_subset), "n_clusters": len({d for d in ev_cl.values()}),
           "gross": gm, "gross_lb": glb}
    for name, series in (("net_taker_fee2", ntf2), ("net_taker_fee0", ntf0),
                         ("net_maker_fee2", nmf2), ("net_maker_fee0", nmf0)):
        if not series:
            out[name] = None
            out[name + "_lb"] = None
            out[name + "_positive"] = None
            continue
        m, lb = _lb(series, ev_cl)
        out[name] = m
        out[name + "_lb"] = lb
        out[name + "_positive"] = (lb is not None and lb > 0)   # PREREG §5: net_positive iff LB>0
    return out


def analyze(rows, spreads=None, gaps=None):
    if spreads is None:
        spreads = reg._band_spreads()
    if gaps is None:
        gaps = _maker_gaps()
    blind = [r for r in rows if r["strategy"] == "_blind"]
    baseline = reg._matched_baseline(blind)
    out = {"meta": {"prereg": PREREG, "z": Z, "follower_tax": FOLLOWER_TAX,
                    "band_spreads": {str(k): v for k, v in sorted(spreads.items())},
                    "maker": gaps}, "arms": {}}
    for arm in ARMS:
        prows = [r for r in rows if r["strategy"] == arm]
        ev = reg._events(prows, baseline)
        if not ev:
            out["arms"][arm] = {"n_events": 0, "note": "no resolved data (arm empty)"}
            continue
        pooled = _read(ev, spreads, gaps)
        by_reg = defaultdict(dict)
        for k, v in ev.items():
            by_reg[v["regime_id"]][k] = v
        regimes = {}
        for rid, sub in by_reg.items():
            r = _read(sub, spreads, gaps)
            rt = next(iter(sub.values()))["regime_type"]
            r["regime_type"] = rt
            r["recurring"] = not rc.is_expiring_for_verdict(rt)
            regimes[rid] = r
        rec_netpos = [rid for rid, r in regimes.items()
                      if r["recurring"] and r.get("net_taker_fee2_positive")]
        out["arms"][arm] = {"n_events": pooled["n_events"], "pooled": pooled, "regimes": regimes,
                            "recurring_net_positive_taker_fee2": sorted(rec_netpos),
                            "n_recurring_net_positive": len(rec_netpos)}
    return out


def _f(x, spec="+.2%"):
    return "   n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else format(x, spec)


def run_live():
    rows = reg.smod.fetch()
    res = analyze(rows)
    gaps = res["meta"]["maker"]
    print("NET-EDGE-AFTER-TAX PER REGIME · gross → net_taker → net_maker · flat-shares · at-fire entry")
    print(f"  frozen: {PREREG} · follower_tax {FOLLOWER_TAX:+.1%} · maker δ0/5m adverse-gap "
          f"{_f(gaps['gap_fee2'],'+.2%')} (fill ~{_f(gaps['fill_rate'],'.0%')} — CAVEAT)\n")
    for arm in ARMS:
        a = res["arms"][arm]
        if a.get("n_events", 0) == 0:
            print(f"── {arm}: {a.get('note','no data')} ──\n")
            continue
        p = a["pooled"]
        print(f"── {arm} · {a['n_events']} events · POOLED gross {_f(p['gross'])} → "
              f"net_taker(fee2) {_f(p['net_taker_fee2'])} [LB {_f(p['net_taker_fee2_lb'])}] → "
              f"net_maker(fee2) {_f(p['net_maker_fee2'])} ──")
        hdr = (f"   {'regime':<24}{'type':>5}{'ev':>4}{'gross':>8}{'netTk2':>8}{'netTk0':>8}"
               f"{'netMk2':>8}{'netMk0':>8}{'  net+?':>8}")
        print(hdr)
        for rid in sorted(a["regimes"], key=lambda r: -(a["regimes"][r]["gross"] or -9)):
            r = a["regimes"][rid]
            tag = "REC" if r["recurring"] else "exp"
            netpos = "TAKER+" if r.get("net_taker_fee2_positive") else (
                "maker+" if r.get("net_maker_fee2_positive") else "—")
            print(f"   {rid:<24}{tag:>5}{r['n_events']:>4}{_f(r['gross']):>8}{_f(r['net_taker_fee2']):>8}"
                  f"{_f(r['net_taker_fee0']):>8}{_f(r['net_maker_fee2']):>8}{_f(r['net_maker_fee0']):>8}{netpos:>8}")
        nrp = a["recurring_net_positive_taker_fee2"]
        print(f"   RECURRING regimes net-positive after taker tax (LB>0, fee2): {nrp or 'NONE'} "
              f"({a['n_recurring_net_positive']} — need ≥2 for PERSISTS-NET)\n")
    out = os.path.join(REPORT_DIR, "regime_net_edge.json")
    with open(out, "w") as f:
        json.dump(res, f, indent=1, default=str)
    print(f"artifact → reports/regime_net_edge.json")
    return res


# --------------------------------------------------------------------------------------------
def _selftest():
    ok = True
    spreads = {5: 0.05, 4: 0.05, 3: 0.05}   # a punishing 5¢ spread band
    gaps = {"gap_fee2": -0.0069, "gap_fee0": -0.0069, "fill_rate": 0.28}
    days = ["2026-07-01", "2026-07-02", "2026-07-03"]

    def ev_set(gross, entry, n_per_day=6):
        ev = {}
        i = 0
        for d in days:
            for _ in range(n_per_day):
                ev[f"e{i}"] = {"surplus": gross, "entry": entry, "day": d, "month": "2026-07",
                               "regime_id": "mlb|2026-07", "sport": "mlb", "regime_type": "recurring"}
                i += 1
        return ev

    # (1) +8% gross at price 0.75 (band 4), 5¢ spread: net_taker = 8 − 5 − 1.3 − 2·0.75 = +0.2% → LB>0 (tight fixture) → net-positive.
    r1 = _read(ev_set(0.08, 0.75), spreads, gaps)
    c1 = r1["net_taker_fee2_positive"] is True
    ok = ok and c1
    print(f"  [{'ok' if c1 else 'FAIL'}] +8% gross under 5¢ spread → net_taker(fee2) {_f(r1['net_taker_fee2'])} "
          f"LB {_f(r1['net_taker_fee2_lb'])} positive={r1['net_taker_fee2_positive']}")

    # (2) +3% gross at price 0.75, 5¢ spread: net_taker = 3 − 5 − 1.3 − 1.5 = −4.8% → NEGATIVE (not bankable).
    r2 = _read(ev_set(0.03, 0.75), spreads, gaps)
    c2 = (r2["net_taker_fee2"] < 0) and (r2["net_taker_fee2_positive"] is False)
    ok = ok and c2
    print(f"  [{'ok' if c2 else 'FAIL'}] +3% gross under 5¢ spread → net_taker(fee2) {_f(r2['net_taker_fee2'])} "
          f"→ NOT bankable (positive={r2['net_taker_fee2_positive']})")

    # (3) maker beats taker when the spread is wide (no spread crossed): net_maker > net_taker.
    c3 = r2["net_maker_fee2"] > r2["net_taker_fee2"]
    ok = ok and c3
    print(f"  [{'ok' if c3 else 'FAIL'}] maker path avoids the 5¢ spread: net_maker {_f(r2['net_maker_fee2'])} "
          f"> net_taker {_f(r2['net_taker_fee2'])}")

    # (4) fee=0 column ≥ fee=2% column (fee only subtracts).
    c4 = r1["net_taker_fee0"] >= r1["net_taker_fee2"] and r1["net_maker_fee0"] >= r1["net_maker_fee2"]
    ok = ok and c4
    print(f"  [{'ok' if c4 else 'FAIL'}] fee=0 ≥ fee=2% (taker & maker)")

    # (5) empty arm graceful
    res = analyze([{"strategy": "_blind", "slug": "mlb-a-b-2026-07-01", "title": "A vs B",
                    "event_slug": "mlb-a-b-2026-07-01", "condition_id": "x", "entry": 0.75, "won": 1,
                    "day": "2026-07-01"}], spreads=spreads, gaps=gaps)
    c5 = res["arms"]["proven_router"]["n_events"] == 0
    ok = ok and c5
    print(f"  [{'ok' if c5 else 'FAIL'}] empty arm → n_events 0 (graceful)")

    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        run_live()
