#!/usr/bin/env python3
"""
PERSISTENCE TRACKER — the leakage-free forward go/no-go the D17 wall is actually waiting on.

D17 named the binding wall: not the surplus SE, but OUT-OF-SAMPLE persistence — does favorite's
edge hold on independent clusters it was NOT discovered on, especially in NEW regimes (the post-WC
MLB bridge → the sharp fall markets)? This instrument operationalizes exactly that. It splits the
record at a CUTOFF into IN-sample (discovery) and OUT-of-sample (forward), and reads the edge on
the OUT rows ONLY — a genuinely leakage-free forward test — using the reconciled convention from
effective_n.py (cluster-robust SE + an explicit independent-cluster-COUNT floor, NOT a day-deflated
SE). It is the TEMPORAL complement to entry-15's sport_edge_tracker (which asks the SPATIAL
question: does skill survive where market softness ≈ 0).

Verdict logic (frozen):
  * OUT clusters < PERSIST_MIN_CLUSTERS  → PENDING (the accrual wall; report how many more days).
  * else cluster-robust LB(OUT surplus) > margin → PERSISTS (forward-certified on unseen clusters).
  * else OUT upper bound < 0             → REFUTED (the edge decayed out of sample).
  * else                                 → INDETERMINATE (accrued but inconclusive).
Plus a regime breakdown: OUT surplus per regime, flagging regimes NOT present in-sample (does the
edge hold where it is genuinely new — the transfer question).

As the stream accrues, re-run with a rolling cutoff; today (4 days) it reads PENDING by
construction, which is the honest state. Read-only, paper-only. Reuses selection_null (fetch/band/
regime/blind edge), effective_n (cluster_robust), portfolio_concentration (match key) byte-identically.

Modes:
  ./persistence_tracker.py                 # live; default cutoff = median UTC day; writes JSON
  ./persistence_tracker.py --cutoff DATE   # ISO date; OUT = rows on/after DATE
  ./persistence_tracker.py --selftest      # persisting vs decaying out-sample must verdict correctly
"""

import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import selection_null as sn
import effective_n as en
import portfolio_concentration as pc

ANCHOR = "favorite"
MARGIN = 0.03
PERSIST_MIN_CLUSTERS = 10       # independent OUT-of-sample day-clusters a forward read needs (D17-a)
Z = 1.96


def fav_events(rows=None):
    """Per-(match)-event favorite surplus with day + regime labels (match-key clustering)."""
    if rows is None:
        rows = sn.fetch()
    blind_band = defaultdict(list)
    for r in rows:
        if r["strategy"] == "_blind":
            blind_band[sn.band(r["entry"])].append(r["won"] - r["entry"])
    blind_edge = {b: sum(v) / len(v) for b, v in blind_band.items()}
    fav = [r for r in rows if r["strategy"] == ANCHOR]
    ev = defaultdict(list)
    for r in fav:
        # match key strips the market-type suffix (portfolio_concentration), so sub-markets of one
        # game collapse — the honest event unit (truth-audit E).
        k = pc.match_key(r["event_slug"], r["ev"])
        ev[k].append(r)
    out = {}
    for k, rs in ev.items():
        s = float(np.mean([(r["won"] - r["entry"]) - blind_edge.get(sn.band(r["entry"]), 0.0) for r in rs]))
        day = min(str(r["day"]) for r in rs)
        es = next((r["event_slug"] for r in rs if r["event_slug"]), rs[0]["ev"])
        out[k] = {"surplus": s, "day": day, "regime": sn.regime(es)}
    return out


def read_window(ev_subset):
    """Surplus + cluster-robust LB over a set of events, clustered by day (independent unit)."""
    if not ev_subset:
        return {"n_events": 0, "n_clusters": 0, "surplus": None, "lb": None, "hi": None,
                "regimes": {}}
    ev_s = {k: v["surplus"] for k, v in ev_subset.items()}
    ev_cl = {k: v["day"] for k, v in ev_subset.items()}
    cr = en.cluster_robust(ev_s, ev_cl)
    surplus = cr["theta"]
    lb = surplus - Z * cr["se_CR"] if cr and math.isfinite(cr["se_CR"]) else None
    hi = surplus + Z * cr["se_CR"] if cr and math.isfinite(cr["se_CR"]) else None
    by_reg = defaultdict(list)
    for k, v in ev_subset.items():
        by_reg[v["regime"]].append(v["surplus"])
    regimes = {rg: {"n": len(xs), "surplus": float(np.mean(xs))} for rg, xs in by_reg.items()}
    return {"n_events": len(ev_subset), "n_clusters": cr["G"] if cr else 0,
            "surplus": surplus, "lb": lb, "hi": hi, "regimes": regimes}


def verdict(out):
    if out["n_clusters"] < PERSIST_MIN_CLUSTERS:
        return "PENDING", (f"only {out['n_clusters']} independent OUT-of-sample clusters "
                           f"(< {PERSIST_MIN_CLUSTERS} floor) — need "
                           f"~{PERSIST_MIN_CLUSTERS - out['n_clusters']} more days of forward firing")
    if out["lb"] is not None and out["lb"] > MARGIN:
        return "PERSISTS", f"OUT-of-sample cluster-robust LB {out['lb']:+.2%} > {MARGIN:.0%} on unseen clusters"
    if out["hi"] is not None and out["hi"] < 0:
        return "REFUTED", f"OUT-of-sample upper bound {out['hi']:+.2%} < 0 — the edge decayed out of sample"
    return "INDETERMINATE", "accrued past the floor but the OUT-of-sample LB does not clear the margin"


def split_and_read(ev, cutoff):
    in_ev = {k: v for k, v in ev.items() if v["day"] < cutoff}
    out_ev = {k: v for k, v in ev.items() if v["day"] >= cutoff}
    in_read = read_window(in_ev)
    out_read = read_window(out_ev)
    in_regimes = set(in_read["regimes"])
    out_read["new_regimes"] = sorted(set(out_read["regimes"]) - in_regimes)
    vd, why = verdict(out_read)
    return {"cutoff": cutoff, "in_sample": in_read, "out_of_sample": out_read,
            "verdict": vd, "why": why}


def run_live(cutoff=None):
    ev = fav_events()
    days = sorted({v["day"] for v in ev.values()})
    if cutoff is None:
        cutoff = days[len(days) // 2] if len(days) > 1 else days[0]
    res = split_and_read(ev, cutoff)
    print(f"PERSISTENCE TRACKER · anchor={ANCHOR} · record days {days[0]}→{days[-1]} · "
          f"cutoff {cutoff} (OUT = on/after) · floor {PERSIST_MIN_CLUSTERS} independent clusters\n")
    for label, w in (("IN-sample (discovery)", res["in_sample"]), ("OUT-of-sample (forward)", res["out_of_sample"])):
        s = "n/a" if w["surplus"] is None else f"{w['surplus']:+.2%}"
        lb = "n/a" if w["lb"] is None else f"{w['lb']:+.2%}"
        print(f"  {label:<26} events {w['n_events']:>3} · clusters {w['n_clusters']:>2} · surplus {s} · cluster-robust LB {lb}")
        for rg, rv in sorted(w["regimes"].items(), key=lambda kv: -kv[1]["n"]):
            new = " (NEW regime — transfer test)" if rg in res["out_of_sample"].get("new_regimes", []) and label.startswith("OUT") else ""
            print(f"      {rg:<8} n={rv['n']:>3} surplus {rv['surplus']:+.2%}{new}")
    print(f"\n  VERDICT: {res['verdict']} — {res['why']}")
    if res["verdict"] == "PENDING":
        print("  (This is the honest current state on a 4-day record. Re-run with a rolling cutoff as the")
        print("   post-WC stream accrues; it flips to PERSISTS/REFUTED once ≥10 independent forward clusters exist —")
        print("   the number system_readiness.py dates. The MLB/other regimes are the live transfer test.)")
    return res


# ---------------------------------------------------------------------------------------
def _synth(kind, seed=42):
    """Synthetic favorite events across 20 days. IN = days 0-9, OUT = days 10-19.
      persist : OUT surplus stays ~+0.12 → PERSISTS.
      decay   : OUT surplus ~0 → INDETERMINATE/REFUTED.
      thin    : only 4 days total → PENDING."""
    rng = np.random.default_rng(seed)
    ev = {}
    ndays = 4 if kind == "thin" else 20
    for d in range(ndays):
        out_side = d >= (ndays // 2)
        for j in range(12):
            if kind == "persist":
                s = 0.12 + rng.normal(0, 0.05)
            elif kind == "decay":
                s = (0.12 if not out_side else -0.01) + rng.normal(0, 0.05)
            else:  # thin
                s = 0.12 + rng.normal(0, 0.05)
            ev[f"{kind}-{d}-{j}"] = {"surplus": float(s), "day": f"2026-08-{d+1:02d}",
                                     "regime": ("mlb" if out_side else "soccer")}
    return ev


def selftest():
    ok = True
    cut = "2026-08-11"   # OUT = days 10..19
    for kind, want in (("persist", "PERSISTS"), ("decay", ("REFUTED", "INDETERMINATE")), ("thin", "PENDING")):
        ev = _synth(kind)
        r = split_and_read(ev, cut if kind != "thin" else "2026-08-03")
        got = r["verdict"]
        good = (got == want) if isinstance(want, str) else (got in want)
        ok = ok and good
        outw = r["out_of_sample"]
        s_str = "n/a" if outw["surplus"] is None else f"{outw['surplus']:+.2%}"
        lb_str = "n/a" if outw["lb"] is None else f"{outw['lb']:+.2%}"
        print(f"  [{'ok' if good else 'FAIL'}] {kind}: OUT clusters {outw['n_clusters']}, "
              f"surplus {s_str}, LB {lb_str} → {got} (want {want})")

    # NEW-regime detection: persist synth has soccer in-sample, mlb out-of-sample.
    ev = _synth("persist")
    r = split_and_read(ev, cut)
    c_new = "mlb" in r["out_of_sample"]["new_regimes"]
    ok = ok and c_new
    print(f"  [{'ok' if c_new else 'FAIL'}] new-regime detection: OUT new_regimes={r['out_of_sample']['new_regimes']} (want mlb)")

    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    cutoff = None
    if "--cutoff" in sys.argv:
        cutoff = sys.argv[sys.argv.index("--cutoff") + 1]
    res = run_live(cutoff)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports", "persistence_tracker.json")
    with open(out, "w") as f:
        json.dump(res, f, indent=1, default=str)
    print("\nartifact → reports/persistence_tracker.json")


if __name__ == "__main__":
    main()
