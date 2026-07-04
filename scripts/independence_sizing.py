#!/usr/bin/env python3
"""
WITHIN-DAY EFFECTIVE-INDEPENDENCE SIZING CHECK (Item 6, STRETCH — REPORT-ONLY; builds/deploys nothing).

Validates the sizing thesis DIRECTLY: the risk policy deploys ≤13%/day spread flat-shares across the
day's markets, which ASSUMES those markets are independent bets. They are not — same-game sub-markets
(exact-score / more-markets / totals of ONE match) and same-slate games move together. This measures
the ACTUAL same-day cross-market correlation and reports, per day:

  nominal   = # resolved favorite signals that day (what a naive per-market split treats as independent).
  matches   = # distinct games (portfolio_concentration.match_key collapses one game's sub-markets).
  N_eff     = nominal / design-effect, design-effect = 1 + (m̄−1)·ICC, ICC = within-match correlation of
              the advantage residual (portfolio_concentration.icc_oneway / n_eff — reused byte-identically).

Then: is the 13%/day deploy cap sized to N_eff (true independence) or to the nominal market count? If
nominal/N_eff ≫ 1, spreading 13% across `nominal` markets OVER-states diversification by that factor —
the realized per-independent-bet exposure is 13%/N_eff, not 13%/nominal. This is the "size the GAME,
not the market" finding (correlated-risk memory) measured on the live record.

REPORT-ONLY: emits a recommendation, changes no sizing, arms nothing. Read-only, paper-only.

Modes:
  ./independence_sizing.py             # per-day nominal vs N_eff + the deploy-cap read; writes JSON
  ./independence_sizing.py --selftest  # all-same-game day → N_eff≈1; all-distinct-games → N_eff≈nominal
"""

import json
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import selection_null as sn              # fetch(), band(), regime()
import portfolio_concentration as pc    # match_key, build_baseline, icc_oneway, n_eff (reused byte-identically)

PREREG = "reports/PREREG_20260704T191458Z_regime_persistence.md"
DEPLOY_CAP = 0.13        # the risk policy's per-day deploy cap (13%/day), stated in the run brief
ARM = "favorite"
REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")


def _neff_from_groups(groups, nominal, matches):
    """N_eff = nominal / DE (within-match ICC), clamped to [matches, nominal]. matches when ICC
    unestimable (<2 groups)."""
    if matches < 2 or nominal < 2:
        return float(matches), float("nan"), (nominal / matches if matches else float("nan"))
    icc, m_bar, k, ntot = pc.icc_oneway(groups)
    ne, de = pc.n_eff(ntot, m_bar, icc)
    return min(max(ne, float(matches)), float(nominal)), icc, de


def day_independence(rows_day, baseline):
    """nominal, matches, N_eff for one day's favorite signals, at TWO grains. Independent bets lie
    in [matches, nominal]: sub-markets of ONE game are NOT independent bets. Two ICC grains (mirrors
    portfolio_concentration icc vs icc_raw):
      EDGE   = advantage residual (a − matched-blind edge) — independence of the EDGE reads.
      P&L    = raw advantage (won − entry) — independence of the DOLLAR SWINGS the drawdown/ruin math
               sees; sub-markets of one game resolve together, so this is the SIZING-relevant grain.
    The deploy-cap read uses the P&L grain (the 'size the GAME' correlated-risk finding)."""
    resid = defaultdict(list)   # match_key -> [edge residuals]
    raw = defaultdict(list)     # match_key -> [raw advantage]
    for r in rows_day:
        mk = pc.match_key(r["event_slug"], r["ev"])
        resid[mk].append(r["won"] - r["entry"] - baseline(r))
        raw[mk].append(r["won"] - r["entry"])
    nominal = len(rows_day)
    matches = len(resid)
    ne_edge, icc_edge, _ = _neff_from_groups(list(resid.values()), nominal, matches)
    ne_pnl, icc_pnl, de_pnl = _neff_from_groups(list(raw.values()), nominal, matches)
    return {"nominal": nominal, "matches": matches,
            "icc_edge": icc_edge, "n_eff_edge": ne_edge,
            "icc_pnl": icc_pnl, "n_eff_pnl": ne_pnl, "n_eff": ne_pnl}


def analyze(rows):
    blind = [r for r in rows if r["strategy"] == "_blind"]
    baseline = pc.build_baseline(blind) if blind else (lambda r: 0.0)
    fav = [r for r in rows if r["strategy"] == ARM]
    by_day = defaultdict(list)
    for r in fav:
        by_day[r["day"]].append(r)
    days = {}
    for d, rd in sorted(by_day.items()):
        days[d] = day_independence(rd, baseline)
    # aggregate: mean nominal, mean N_eff, and the pooled inflation factor.
    if days:
        nom = np.array([v["nominal"] for v in days.values()], float)
        neff = np.array([v["n_eff"] for v in days.values()], float)
        infl = float(np.mean(nom / np.maximum(neff, 1e-9)))
        med_infl = float(np.median(nom / np.maximum(neff, 1e-9)))
        mean_nom, mean_neff = float(nom.mean()), float(neff.mean())
    else:
        infl = med_infl = mean_nom = mean_neff = float("nan")
    # deploy-cap read: exposure per independent bet if sized to nominal vs N_eff.
    per_nominal = DEPLOY_CAP / mean_nom if mean_nom else float("nan")
    per_neff = DEPLOY_CAP / mean_neff if mean_neff else float("nan")
    return {"meta": {"prereg": PREREG, "arm": ARM, "deploy_cap": DEPLOY_CAP},
            "days": days,
            "aggregate": {"mean_nominal_per_day": mean_nom, "mean_neff_per_day": mean_neff,
                          "mean_inflation_factor": infl, "median_inflation_factor": med_infl,
                          "exposure_per_bet_if_sized_to_nominal": per_nominal,
                          "exposure_per_bet_if_sized_to_neff": per_neff}}


def _rec(agg):
    infl = agg["median_inflation_factor"]
    if infl != infl:
        return "INDETERMINATE — no data"
    if infl >= 1.5:
        return (f"SIZE TO N_eff: the deploy cap is spread across ~{agg['mean_nominal_per_day']:.0f} nominal "
                f"markets/day but only ~{agg['mean_neff_per_day']:.1f} are independent (median inflation "
                f"{infl:.1f}×). Realized per-independent-bet exposure is {agg['exposure_per_bet_if_sized_to_neff']:.1%} "
                f"(not {agg['exposure_per_bet_if_sized_to_nominal']:.1%}). RECOMMEND: govern the 13%/day cap by "
                f"N_eff (flat-shares per GAME, not per market) — the 'size the GAME' correlated-risk finding, "
                f"measured. REPORT-ONLY; no sizing changed.")
    return (f"cap ≈ well-sized: median inflation {infl:.1f}× (< 1.5) — nominal and N_eff are close on this "
            f"record. Re-check as multi-game slates grow. REPORT-ONLY.")


def run_live():
    rows = sn.fetch()
    res = analyze(rows)
    agg = res["aggregate"]
    print("WITHIN-DAY EFFECTIVE-INDEPENDENCE SIZING CHECK · REPORT-ONLY (deploys nothing) · arm=favorite")
    print(f"  frozen refs: {PREREG} · deploy cap {DEPLOY_CAP:.0%}/day · match_key + icc/n_eff reused from "
          f"portfolio_concentration\n")
    print("N_eff at TWO grains — EDGE (residual) vs P&L (raw advantage, the sizing-relevant swing grain)\n")
    hdr = (f"{'day':<12}{'nominal':>8}{'matches':>8}{'ICC_pnl':>9}{'Neff_pnl':>9}{'Neff_edge':>10}{'infl×(pnl)':>11}")
    print(hdr); print("-" * len(hdr))
    for d, v in res["days"].items():
        infl = v["nominal"] / max(v["n_eff_pnl"], 1e-9)
        icc = v["icc_pnl"]
        icc_s = "  n/a" if icc != icc else f"{icc:>9.3f}"
        print(f"{d:<12}{v['nominal']:>8}{v['matches']:>8}{icc_s}{v['n_eff_pnl']:>9.1f}{v['n_eff_edge']:>10.1f}{infl:>11.1f}")
    print("-" * len(hdr))
    print(f"aggregate: mean {agg['mean_nominal_per_day']:.0f} nominal/day → {agg['mean_neff_per_day']:.1f} "
          f"independent/day (median inflation {agg['median_inflation_factor']:.1f}×)")
    print(f"deploy-cap exposure per independent bet: {agg['exposure_per_bet_if_sized_to_nominal']:.1%} "
          f"(if sized to nominal) vs {agg['exposure_per_bet_if_sized_to_neff']:.1%} (if sized to N_eff)")
    print(f"\nRECOMMENDATION: {_rec(agg)}")
    out = os.path.join(REPORT_DIR, "independence_sizing.json")
    res["recommendation"] = _rec(agg)
    with open(out, "w") as f:
        json.dump(res, f, indent=1, default=str)
    print(f"\nartifact → reports/independence_sizing.json")
    return res


# --------------------------------------------------------------------------------------------
def _selftest():
    ok = True
    base = lambda r: 0.0

    def mk(match, i, won):
        slug = f"{match}-sub{i}"
        return {"strategy": "favorite", "ev": slug, "event_slug": f"{match}-2026-07-01",
                "entry": 0.75, "won": won, "day": "2026-07-01"}

    # (1) heavy sub-market stacking: 2 games × 6 sub-markets each, sub-markets within a game share
    #     the game outcome (ICC≈1) → N_eff ≈ matches = 2, NOT nominal = 12.
    rng = np.random.default_rng(7)
    stacked = []
    for g in ("fifwc-bra-jpn", "fifwc-arg-ger"):
        w = int(rng.random() < 0.75)
        stacked += [mk(g, i, w) for i in range(6)]   # identical outcome within game ⇒ ICC=1
    d1 = day_independence(stacked, base)
    c1 = d1["matches"] == 2 and d1["n_eff"] <= 3.0 and d1["nominal"] == 12
    ok = ok and c1
    print(f"  [{'ok' if c1 else 'FAIL'}] sub-market-stacked day: nominal {d1['nominal']}, matches {d1['matches']}, "
          f"N_eff {d1['n_eff']:.1f} (≈2, not 12)")

    # (2) all-distinct-games day: 12 different matches, independent outcomes → N_eff ≈ nominal.
    dist = []
    for g in range(12):
        dist.append({"strategy": "favorite", "ev": f"m{g}", "event_slug": f"mlb-t{g}-u{g}-2026-07-01",
                     "entry": 0.75, "won": int(rng.random() < 0.75), "day": "2026-07-01"})
    d2 = day_independence(dist, base)
    c2 = d2["matches"] == 12 and d2["n_eff"] >= 0.7 * d2["nominal"]
    ok = ok and c2
    print(f"  [{'ok' if c2 else 'FAIL'}] all-distinct-games day: matches {d2['matches']}, "
          f"N_eff {d2['n_eff']:.1f}/{d2['nominal']} (≈nominal)")

    # (3) ordering: same-game N_eff < distinct-game N_eff.
    c3 = d1["n_eff"] < d2["n_eff"]
    ok = ok and c3
    print(f"  [{'ok' if c3 else 'FAIL'}] N_eff ordering: same-game {d1['n_eff']:.1f} < distinct {d2['n_eff']:.1f}")

    # (4) recommendation fires SIZE-TO-N_eff on a high-inflation aggregate.
    agg = {"median_inflation_factor": 4.0, "mean_nominal_per_day": 20, "mean_neff_per_day": 5,
           "exposure_per_bet_if_sized_to_neff": 0.026, "exposure_per_bet_if_sized_to_nominal": 0.0065}
    c4 = "SIZE TO N_eff" in _rec(agg)
    ok = ok and c4
    print(f"  [{'ok' if c4 else 'FAIL'}] high-inflation → SIZE-TO-N_eff recommendation")

    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        run_live()
