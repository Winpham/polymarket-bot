#!/usr/bin/env python3
"""
REGIME-EDGE DECOMPOSITION — the two headline reads the pooled +5% favorite number HIDES.

Per arm × regime (regime = sport_category × calendar-month, PREREG §1): event-clustered surplus over
the MATCHED (category × 5-band) blind-favorite baseline (byte-identical to softness_map.py — the
composition-trap-safe convention, NEVER a 0-baseline), the independent-cluster COUNT (the honest N,
NOT the raw signal count), a cluster-robust one-sided 95% LB (effective_n.cluster_robust), the
regime_type (regime_classify), and:

  CONCENTRATION  HHI + top-1 share of the pooled edge MASS across regimes — "is the +5% one-regime-
                 carried?" Names the single regime carrying the most, and re-reads the pooled edge
                 with that regime removed. (Expected today: heavily soccer-carried.)
  BREADTH        how many regimes have any data, split recurring vs expiring, and how many clear the
                 per-regime independent-cluster floor (PERSIST_MIN_CLUSTERS) toward the ≥2 bar.

PREREG §3 fixes Item 2 as GROSS surplus over the matched baseline. A `net_taker` column (gross −
band-spread − follower-tax − fee·price, PREREG §5) is shown INLINE for continuity, but the full
net-after-tax decomposition (taker/maker × fee) is Item 4 (regime_net_edge.py). Concentration and
breadth are read on the GROSS pooled edge (the number the owner asked about). flat-SHARES, at-fire
entry, read-only, paper-only.

Constants frozen in reports/PREREG_20260704T191458Z_regime_persistence.md.

Modes:
  ./regime_edge.py             # live per-regime table + concentration/breadth; writes JSON
  ./regime_edge.py --selftest  # soccer-only edge → high concentration; 3-recurring-regime edge → low
"""

import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import selection_null as sn            # band()
import effective_n as en              # cluster_robust() — the cluster count + CR SE (reused byte-identically)
import softness_map as smod           # fetch() (has slug/title), evk()
import regime_classify as rc          # classify_regime, is_expiring_for_verdict
from market_taxonomy import category  # matched-baseline key (softness_map convention)
from superkey import super_event      # event super-key

PREREG = "reports/PREREG_20260704T191458Z_regime_persistence.md"
ARMS = ("favorite", "proven_router")   # PREREG §3
Z = 1.96                               # PREREG §7 (mirrors persistence_tracker.Z)
MARGIN = 0.03                          # PREREG §7
CLUSTER_FLOOR = en.__dict__.get("PERSIST_MIN_CLUSTERS", 10)  # per-regime cluster floor
try:
    import persistence_tracker as _pt
    CLUSTER_FLOOR = _pt.PERSIST_MIN_CLUSTERS
except Exception:
    CLUSTER_FLOOR = 10
FOLLOWER_TAX = 0.013                   # PREREG §7 (copyability.py, cited)
FEE = 0.02                             # PREREG §7
REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")


def lb_small_cluster(theta, se_cr, G):
    """One-sided 95% lower bound with SMALL-CLUSTER t(G−1) — corrects the normal-z overstatement on
    tiny cluster counts (audit 2026-07-04; ADDENDUM 20260704T210132Z). effective_n.py's own docstring
    warns a normal-z LB on few clusters is misleading; here G is often 2–6, so t(G−1) is required. Uses
    effective_n._t_ppf at one-sided 95% (matches effective_n's alpha convention and the independent
    audit's re-derivation). Returns None for G<2 (a single cluster carries no between-cluster info)."""
    if G is None or G < 2 or se_cr is None or not math.isfinite(se_cr):
        return None
    return theta - en._t_ppf(0.95, G - 1) * se_cr


def _month(day):
    return str(day)[:7]   # YYYY-MM from a YYYY-MM-DD day string


def _band_spreads():
    """Per-band decision-time ask spread from copyability.json (cited, not re-measured). {} if absent."""
    try:
        with open(os.path.join(REPORT_DIR, "copyability.json")) as f:
            meta = json.load(f)["meta"]
        return {int(k): float(v) for k, v in meta["band_spreads"].items()}
    except Exception:
        return {}


def _matched_baseline(blind):
    """(category × 5-band) blind-favorite baseline — byte-identical to softness_map.py:149-157."""
    base = defaultdict(list)
    for r in blind:
        base[(category(r["slug"], r["title"]), sn.band(r["entry"]))].append(r["won"] - r["entry"])
    base_cb = {k: sum(v) / len(v) for k, v in base.items()}

    def baseline(r):
        return base_cb.get((category(r["slug"], r["title"]), sn.band(r["entry"])), 0.0)
    return baseline


def _events(prows, baseline):
    """Collapse an arm's rows to per-event: gross surplus, mean entry, day, month, regime, type."""
    by_ev = defaultdict(list)
    for r in prows:
        by_ev[smod.evk(r)].append(r)
    ev = {}
    for k, rs in by_ev.items():
        s = float(np.mean([(r["won"] - r["entry"]) - baseline(r) for r in rs]))
        entry = float(np.mean([r["entry"] for r in rs]))
        day = min(str(r["day"]) for r in rs)
        r0 = rs[0]
        cat = category(r0["slug"], r0["title"])
        _, rtype = rc.classify_regime(cat, None, r0["slug"], r0["title"])
        ev[k] = {"surplus": s, "entry": entry, "day": day, "month": _month(day),
                 "regime_id": f"{cat}|{_month(day)}", "sport": cat, "regime_type": rtype}
    return ev


def _regime_read(ev_subset, spreads):
    """Gross + net_taker surplus, cluster count, CR LB over a set of events (clustered by UTC day)."""
    if not ev_subset:
        return None
    ev_s = {k: v["surplus"] for k, v in ev_subset.items()}
    ev_cl = {k: v["day"] for k, v in ev_subset.items()}
    cr = en.cluster_robust(ev_s, ev_cl)   # None for a single-event regime
    surplus = cr["theta"] if cr else float(np.mean(list(ev_s.values())))
    n_clusters = cr["G"] if cr else len({d for d in ev_cl.values()})
    lb = lb_small_cluster(surplus, cr["se_CR"] if cr else None, n_clusters)   # small-cluster t (ADDENDUM 2)
    # net_taker per event: gross − band_spread(band) − follower_tax − fee·entry (PREREG §5)
    ev_net = {}
    for k, v in ev_subset.items():
        tax = spreads.get(sn.band(v["entry"]), 0.0) + FOLLOWER_TAX + FEE * v["entry"]
        ev_net[k] = v["surplus"] - tax
    net_taker = float(np.mean(list(ev_net.values())))
    cr_n = en.cluster_robust(ev_net, ev_cl)
    net_lb = lb_small_cluster(net_taker, cr_n["se_CR"] if cr_n else None, n_clusters)
    return {"n_events": len(ev_subset), "n_clusters": n_clusters,
            "surplus": surplus, "lb": lb, "net_taker": net_taker, "net_taker_lb": net_lb,
            "mass": float(np.sum(list(ev_s.values())))}   # unnormalized surplus mass for HHI


def _hhi(shares):
    return sum(s * s for s in shares) if shares else float("nan")


def analyze(rows, spreads=None):
    if spreads is None:
        spreads = _band_spreads()
    blind = [r for r in rows if r["strategy"] == "_blind"]
    baseline = _matched_baseline(blind)
    out = {"arms": {}, "meta": {"cluster_floor": CLUSTER_FLOOR, "margin": MARGIN, "z": Z,
                                "band_spreads": {str(k): v for k, v in sorted(spreads.items())},
                                "follower_tax": FOLLOWER_TAX, "fee": FEE, "prereg": PREREG}}
    for arm in ARMS:
        prows = [r for r in rows if r["strategy"] == arm]
        ev = _events(prows, baseline)
        if not ev:
            out["arms"][arm] = {"n_events": 0, "note": "no resolved data (arm empty)"}
            continue
        pooled = _regime_read(ev, spreads)
        # per (sport|month) regime
        by_reg = defaultdict(dict)
        for k, v in ev.items():
            by_reg[v["regime_id"]][k] = v
        regimes = {}
        for rid, sub in by_reg.items():
            r = _regime_read(sub, spreads)
            r["sport"] = next(iter(sub.values()))["sport"]
            r["regime_type"] = next(iter(sub.values()))["regime_type"]
            r["recurring"] = not rc.is_expiring_for_verdict(r["regime_type"])
            r["clears_floor"] = r["n_clusters"] >= CLUSTER_FLOOR
            regimes[rid] = r
        # EDGE concentration on GROSS surplus mass (share of |contribution| to the pooled edge —
        # measured at the honest EVENT grain, so one game = one event regardless of sub-market count).
        masses = {rid: r["mass"] for rid, r in regimes.items()}
        total_abs = sum(abs(m) for m in masses.values()) or 1.0
        shares = {rid: abs(m) / total_abs for rid, m in masses.items()}
        hhi = _hhi(list(shares.values()))
        top_rid = max(shares, key=shares.get) if shares else None
        top_share = shares.get(top_rid, float("nan"))
        # the direct SOCCER-ARTIFACT test: share of |edge mass| carried by EXPIRING regimes.
        exp_mass = sum(abs(regimes[rid]["mass"]) for rid in regimes if not regimes[rid]["recurring"])
        expiring_edge_share = exp_mass / total_abs
        # WHICH expiring sport carries it (audit fix 2026-07-04): the "SOCCER-ARTIFACT" label is a
        # frozen verdict-ladder rung, but by EDGE MASS the carrier is tennis/Wimbledon, not soccer —
        # "soccer" only leads on CAPITAL exposure. Surface the split so the label isn't misleading.
        exp_by_sport = defaultdict(float)
        for rid, rr in regimes.items():
            if not rr["recurring"]:
                exp_by_sport[rr["sport"]] += abs(rr["mass"])
        tot_exp = sum(exp_by_sport.values()) or 1.0
        expiring_by_sport = {sp: m / tot_exp for sp, m in sorted(exp_by_sport.items(), key=lambda kv: -kv[1])}
        top_expiring_sport = next(iter(expiring_by_sport), None)
        # pooled edge with the top regime removed
        ev_ex = {k: v for k, v in ev.items() if v["regime_id"] != top_rid}
        pooled_ex_top = _regime_read(ev_ex, spreads) if ev_ex else None
        # EXPOSURE (capital) concentration at the SIGNAL grain, by sport — reconciles the
        # "soccer-carried" prior (bet volume), distinct from the edge-estimate concentration above.
        sig_by_sport = defaultdict(int)
        for r in prows:
            sig_by_sport[category(r["slug"], r["title"])] += 1
        tot_sig = sum(sig_by_sport.values()) or 1
        exp_shares = {sp: n / tot_sig for sp, n in sig_by_sport.items()}
        exp_top_sport = max(exp_shares, key=exp_shares.get) if exp_shares else None
        # breadth
        rec = [rid for rid, r in regimes.items() if r["recurring"]]
        exp = [rid for rid, r in regimes.items() if not r["recurring"]]
        rec_cleared = [rid for rid in rec if regimes[rid]["clears_floor"]]
        out["arms"][arm] = {
            "n_events": pooled["n_events"], "n_clusters": pooled["n_clusters"],
            "pooled_surplus": pooled["surplus"], "pooled_lb": pooled["lb"],
            "pooled_net_taker": pooled["net_taker"], "pooled_net_taker_lb": pooled["net_taker_lb"],
            "regimes": regimes,
            "concentration": {"hhi": hhi, "eff_regimes": (1.0 / hhi) if hhi and hhi > 0 else None,
                              "top_regime": top_rid, "top_share": top_share,
                              "top_is_expiring": (not regimes[top_rid]["recurring"]) if top_rid else None,
                              "expiring_edge_mass_share": expiring_edge_share,
                              "expiring_by_sport": expiring_by_sport, "top_expiring_sport": top_expiring_sport,
                              "pooled_ex_top_surplus": pooled_ex_top["surplus"] if pooled_ex_top else None},
            "exposure": {"grain": "signal/capital", "by_sport_share": exp_shares,
                         "top_sport": exp_top_sport,
                         "top_sport_share": exp_shares.get(exp_top_sport, float("nan"))},
            "breadth": {"n_regimes": len(regimes), "n_recurring": len(rec), "n_expiring": len(exp),
                        "recurring_cleared": len(rec_cleared), "cluster_floor": CLUSTER_FLOOR,
                        "recurring_ids": sorted(rec), "expiring_ids": sorted(exp)},
        }
    return out


def _fmt(x, spec="+.2%"):
    return "   n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else format(x, spec)


def run_live():
    rows = smod.fetch()
    res = analyze(rows)
    days = sorted({r["day"] for r in rows if r["strategy"] == "favorite"})
    print("REGIME-EDGE DECOMPOSITION · per sport×month regime · matched (cat×band) baseline · flat-shares")
    print(f"  frozen: {PREREG} · record {len(days)}d {days[0]}→{days[-1]} · cluster floor {CLUSTER_FLOOR}\n")
    for arm in ARMS:
        a = res["arms"][arm]
        if a.get("n_events", 0) == 0:
            print(f"── {arm}: {a.get('note', 'no data')} ──\n")
            continue
        print(f"── {arm} · pooled surplus {a['pooled_surplus']:+.2%} (LB {_fmt(a['pooled_lb'])}) over "
              f"{a['n_events']} events / {a['n_clusters']} day-clusters · net_taker {a['pooled_net_taker']:+.2%} ──")
        hdr = f"   {'regime (sport|month)':<24}{'type':>10}{'ev':>4}{'clus':>5}{'surplus':>9}{'CR LB':>9}{'net_taker':>10}"
        print(hdr)
        for rid in sorted(a["regimes"], key=lambda r: -a["regimes"][r]["mass"]):
            r = a["regimes"][rid]
            tag = "REC" if r["recurring"] else "exp"
            floor = "✓" if r["clears_floor"] else " "
            print(f"   {rid:<24}{r['regime_type']:>10}{r['n_events']:>4}{r['n_clusters']:>4}{floor}"
                  f"{_fmt(r['surplus']):>9}{_fmt(r['lb']):>9}{_fmt(r['net_taker']):>10}  [{tag}]")
        c = a["concentration"]; b = a["breadth"]; ex = a["exposure"]
        print(f"   EDGE CONCENTRATION (event grain): HHI {c['hhi']:.3f} (≈{_fmt(c['eff_regimes'],'.1f')} eff regimes) · "
              f"top '{c['top_regime']}' = {c['top_share']:.0%}{' [EXPIRING]' if c['top_is_expiring'] else ' [recurring]'}")
        comp = " · ".join(f"{sp} {sh:.0%}" for sp, sh in list(c.get("expiring_by_sport", {}).items())[:3])
        print(f"                  EXPIRING regimes carry {c['expiring_edge_mass_share']:.0%} of edge mass "
              f"(the direct soccer-artifact test) · pooled edge minus top regime: {_fmt(c['pooled_ex_top_surplus'])}")
        print(f"                  ↳ expiring edge-mass by sport: {comp}  ← '{c.get('top_expiring_sport')}' actually "
              f"carries it (the 'SOCCER-ARTIFACT' label reflects CAPITAL, not edge mass)")
        print(f"   EXPOSURE (capital, signal grain): top sport '{ex['top_sport']}' = {ex['top_sport_share']:.0%} of BETS "
              f"— the 'soccer-carried' prior lives HERE, not in the event-grain edge")
        print(f"   BREADTH: {b['n_regimes']} regimes ({b['n_recurring']} recurring / {b['n_expiring']} expiring) · "
              f"recurring clearing {CLUSTER_FLOOR}-cluster floor: {b['recurring_cleared']}/{b['n_recurring']} "
              f"(toward ≥2 bar)\n")
    # honest headline shape
    fav = res["arms"].get("favorite", {})
    if fav.get("n_events"):
        c = fav["concentration"]; ex = fav["exposure"]; b = fav["breadth"]
        shape = "expiring-carried" if c["expiring_edge_mass_share"] >= 0.5 else "spread across regimes"
        print(f"read: favorite EDGE (event grain) is {shape} — expiring regimes carry "
              f"{c['expiring_edge_mass_share']:.0%} of edge mass; top single regime '{c['top_regime']}' "
              f"{c['top_share']:.0%}. CAPITAL is {ex['top_sport_share']:.0%} '{ex['top_sport']}' (the soccer prior).")
        print(f"      BINDING today: {b['recurring_cleared']}/{b['n_recurring']} recurring regimes clear the "
              f"{CLUSTER_FLOOR}-cluster floor (need ≥2 non-expiring) → the accrual wall, not the point estimate.")
    out = os.path.join(REPORT_DIR, "regime_edge.json")
    with open(out, "w") as f:
        json.dump(res, f, indent=1, default=str)
    print(f"\nartifact → reports/regime_edge.json")
    return res


# --------------------------------------------------------------------------------------------
def _mk(strategy, disc, i, entry, won, day, deriv=False):
    base = f"{disc}-x{i}-y{i}-{day}"
    slug = base + ("-total-5pt5" if deriv else "")
    title = "O/U 5.5" if deriv else "X vs Y"
    return dict(strategy=strategy, event_slug=base, slug=slug, title=title,
                condition_id=slug, entry=entry, won=won, day=day)


def _selftest():
    import random
    rng = random.Random(7)
    ok = True

    # (1) SOCCER-ONLY edge: favorite surplus lives entirely in fifwc (expiring); other cells ~0.
    #     → high concentration, top regime expiring.
    rows = []
    days = ["2026-07-01", "2026-07-02", "2026-07-03"]
    for day in days:
        for i in range(60):
            rows.append(_mk("_blind", "fifwc", i, 0.75, int(rng.random() < 0.75), day))
            rows.append(_mk("_blind", "mlb", 1000 + i, 0.75, int(rng.random() < 0.75), day))
        for i in range(200, 240):
            rows.append(_mk("favorite", "fifwc", i, 0.75, int(rng.random() < 0.93), day))  # +edge
        for i in range(300, 340):
            rows.append(_mk("favorite", "mlb", i, 0.75, int(rng.random() < 0.75), day))     # no edge
    r1 = analyze(rows, spreads={})
    fav = r1["arms"]["favorite"]
    c1 = fav["concentration"]["top_is_expiring"] and fav["concentration"]["top_share"] >= 0.6
    ok = ok and c1
    print(f"  [{'ok' if c1 else 'FAIL'}] soccer-only edge → top '{fav['concentration']['top_regime']}' "
          f"share {fav['concentration']['top_share']:.0%} expiring={fav['concentration']['top_is_expiring']} "
          f"(HHI {fav['concentration']['hhi']:.2f})")

    # (2) edge spread across 3 RECURRING regimes (mlb, nba/cbb, nhl) → low concentration.
    rows2 = []
    for day in days:
        for disc, off in (("mlb", 0), ("nba", 1000), ("nhl", 2000)):
            for i in range(60):
                rows2.append(_mk("_blind", disc, off + i, 0.75, int(rng.random() < 0.75), day))
            for i in range(off + 5000, off + 5040):
                rows2.append(_mk("favorite", disc, i, 0.75, int(rng.random() < 0.90), day))  # equal +edge
    r2 = analyze(rows2, spreads={})
    fav2 = r2["arms"]["favorite"]
    c2 = (fav2["concentration"]["top_share"] < 0.5) and (fav2["breadth"]["n_recurring"] >= 3) \
        and fav2["breadth"]["n_expiring"] == 0
    ok = ok and c2
    print(f"  [{'ok' if c2 else 'FAIL'}] 3-recurring-regime edge → top share {fav2['concentration']['top_share']:.0%} "
          f"<50%, {fav2['breadth']['n_recurring']} recurring / {fav2['breadth']['n_expiring']} expiring")

    # (3) cluster count = independent day-clusters, not signal count (honest N).
    reg0 = next(iter(fav2["regimes"].values()))
    c3 = reg0["n_clusters"] <= len(days) and reg0["n_events"] > reg0["n_clusters"]
    ok = ok and c3
    print(f"  [{'ok' if c3 else 'FAIL'}] cluster count {reg0['n_clusters']} ≤ {len(days)} days < "
          f"{reg0['n_events']} events (day-clustered N, not signal count)")

    # (4) empty arm handled (proven_router-like) → n_events 0, no crash.
    c4 = r1["arms"]["proven_router"]["n_events"] == 0
    ok = ok and c4
    print(f"  [{'ok' if c4 else 'FAIL'}] empty arm → n_events 0 (graceful)")

    # (5) small-cluster t: G=2 uses t(1)≈6.31 (much wider than z=1.96); G<2 → None (ADDENDUM 2).
    lb_g2 = lb_small_cluster(0.10, 0.02, 2)     # 0.10 − t(1)·0.02, flips negative
    lb_g6 = lb_small_cluster(0.10, 0.02, 6)     # 0.10 − t(5)·0.02 ≈ +0.060
    exp_g2 = 0.10 - en._t_ppf(0.95, 1) * 0.02
    c5 = (lb_g2 is not None and abs(lb_g2 - exp_g2) < 1e-9 and lb_g2 < 0 < lb_g6
          and lb_small_cluster(0.1, 0.02, 1) is None)
    ok = ok and c5
    print(f"  [{'ok' if c5 else 'FAIL'}] small-cluster t: G=2 LB {lb_g2:+.3f} (t(1)≈6.31 ≫ z, flips neg) < "
          f"G=6 LB {lb_g6:+.3f}; G<2→None")

    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        run_live()
