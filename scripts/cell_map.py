#!/usr/bin/env python3
"""
CELL-MAP (Generalize-the-Band-Strategy, phase 1, 2026-07-11).

Enumerate the cell space = (category × sport/discipline × price-band × trader-cohort) and flag
per-cell POWER *before* any edge is measured, so an under-powered cell reads INDETERMINATE — never
"best" or "worst". Emits reports/CELL-MAP.json.

Two source families (the realizability split is the whole story):
  A. LIVE favorite arm — carries a leak-free `entry_ask`, so its cells are REALIZABLY measurable.
     Sliced category × band and category × champion-pool (0.71-0.98).
  B. REPLAY cohorts — favorite-band consensus replayed from `trader_fills` under wider eligibility
     rank-bands (top40 / 41-100 / 101-250 / wide 1-250). These never ran live, so their only
     realizable entry is `clob_price_tape` (≈72h retained) → duration-capped by construction.

A cell must clear ALL of: ≥20 match-clusters (volume), ≥7 active days (duration), ≥2 disjoint
non-expiring regimes. Match-clustering is at the super-key (a best-of-3's map/series markets are
ONE bet), NEVER event_slug (leg-piling manufactures false power — soccer's 136 picks are ~17 matches).

Self-test:  ./cell_map.py --selftest
Live:       ./cell_map.py
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cell_lib as C                                    # noqa: E402
from superkey import super_event                        # noqa: E402


def fetch_live_favorite():
    """Champion arm resolved picks with a realizable entry_ask, all bands/categories."""
    rows = C.q(f"""
    SELECT condition_id, outcome_index, COALESCE(event_slug,'') , COALESCE(slug,''),
           entry_ask, outcome_won, first_detected_at::date
    FROM consensus_signals
    WHERE strategy='favorite' AND resolved AND outcome_won IS NOT NULL
      AND entry_ask IS NOT NULL AND entry_ask BETWEEN 0.55 AND 0.999;
    """)
    out = []
    for r in rows:
        r = (r + [""] * 7)[:7]
        cond, oi, es, slug, ask, won, day = r
        out.append({"condition_id": cond, "outcome_index": int(oi), "event_slug": es, "slug": slug,
                    "entry": float(ask), "won": won == "t", "day": day,
                    "category": C.category(es, slug), "band": C.band_of(float(ask))})
    return out


def fetch_replay_cohort(lo_rank, hi_rank):
    """Replay the favorite-band consensus under an eligibility-rank cohort [lo,hi]: outcomes with
    ≥3 distinct one-sided backers (wallets in the cohort) converging within 48h, resolved, band
    0.55-0.98. Carries the sharp (directional) entry, the convergence ts, resolution, and any
    realizable tape_ask at/after convergence. This is exactly soft_market_edge.fetch_soft_picks
    generalized off the esports/wide filter to an arbitrary rank cohort across ALL categories."""
    rows = C.q(f"""
    WITH e AS (
      SELECT f.condition_id, f.outcome_index, LOWER(f.wallet) w, MIN(f.ts) ts, AVG(f.price) px,
             MAX(COALESCE(f.event_slug,'')) event_slug, MAX(COALESCE(f.slug,'')) slug,
             BOOL_OR(f.resolved) rz, BOOL_OR(f.outcome_won) won
      FROM trader_fills f
      JOIN followed_traders ft ON ft.proxy_wallet=f.wallet
      WHERE f.side='BUY' AND f.ts>='{C.GO_LIVE}' AND ft.rank BETWEEN {lo_rank} AND {hi_rank}
      GROUP BY 1,2,3),
    e1 AS (SELECT e.* FROM e WHERE NOT EXISTS
      (SELECT 1 FROM e x WHERE x.condition_id=e.condition_id AND x.w=e.w AND x.outcome_index<>e.outcome_index)),
    conv AS (
      SELECT condition_id, outcome_index, MAX(event_slug) event_slug, MAX(slug) slug,
             COUNT(*) nb, AVG(px) sharp_entry,
             (ARRAY_AGG(ts ORDER BY ts))[3] conv_ts,
             BOOL_OR(rz) rz, BOOL_OR(won) won
      FROM e1 GROUP BY 1,2
      HAVING COUNT(*)>=3 AND (ARRAY_AGG(ts ORDER BY ts))[3] - MIN(ts) <= interval '48 hours')
    SELECT c.condition_id, c.outcome_index, c.event_slug, c.slug, c.nb,
           c.sharp_entry, c.conv_ts, c.won,
           (SELECT best_ask FROM clob_price_tape cp
             WHERE cp.condition_id=c.condition_id AND cp.outcome_index=c.outcome_index
               AND cp.best_ask IS NOT NULL AND cp.recv_at >= c.conv_ts
             ORDER BY cp.recv_at LIMIT 1) tape_ask
    FROM conv c
    WHERE c.sharp_entry BETWEEN 0.55 AND 0.98 AND c.rz AND c.won IS NOT NULL;
    """)
    out = []
    for r in rows:
        r = (r + [""] * 9)[:9]
        cond, oi, es, slug, nb, sharp, cts, won, tape = r
        sharp = float(sharp)
        out.append({"condition_id": cond, "outcome_index": int(oi), "event_slug": es, "slug": slug,
                    "nb": int(nb), "sharp_entry": sharp, "day": (cts or "")[:10],
                    "won": won == "t", "tape_ask": float(tape) if tape not in ("", None) else None,
                    "category": C.category(es, slug), "band": C.band_of(sharp)})
    return out


def summarize(rows, entry_key, realizable_key=None):
    """Bucket rows into a cell record: counts + power flags. realizable_key names the field that
    makes a pick realizably-priced (entry_ask for live; tape_ask for replay); None ⇒ all rows count."""
    if realizable_key is None:
        real = rows
    else:
        real = [r for r in rows if r.get(realizable_key) is not None]
    pf = C.power_flags([{**r, "entry": r.get(entry_key)} for r in real]) if real else \
        {"n_matches": 0, "active_days": 0, "n_regimes_over_subfloor": 0, "regimes": [],
         "meets_volume_floor": False, "meets_duration_floor": False, "meets_regime_floor": False,
         "regime_clusters": {}}
    powered = pf["meets_volume_floor"] and pf["meets_duration_floor"] and pf["meets_regime_floor"]
    return {
        "n_picks_total": len(rows),
        "n_picks_realizable": len(real),
        "realizable_coverage_pct": round(100.0 * len(real) / len(rows), 1) if rows else None,
        "power": pf,
        "power_flag": "POWERED" if powered else "INDETERMINATE",
    }


def build():
    live = fetch_live_favorite()
    cohorts = {name: fetch_replay_cohort(lo, hi) for name, lo, hi in C.COHORTS}

    report = {
        "as_of": "2026-07-11",
        "run": "generalize-band-strategy phase 1 (cell map + power flags)",
        "objective": "cluster-robust LB of realizable copyable ROI-turn @ match super-key; "
                     "beat/complement champion favorite 0.71-0.98. Win-rate + total-P&L are DIAGNOSTIC ONLY.",
        "floors": {"volume_match_clusters": C.VOL_FLOOR, "duration_active_days": C.DUR_FLOOR_DAYS,
                   "regimes": C.REGIME_FLOOR, "regime_subfloor_clusters": C.REGIME_SUBFLOOR},
        "realizability_note":
            "clob_price_tape retains ~72h → any REPLAY cohort's realizable (tape_ask) coverage is "
            "duration-capped and reads INDETERMINATE by construction. Only the LIVE favorite arm "
            "(leak-free entry_ask) yields a durable realizable measurement; it is top-40-cohort-only "
            "(consensus_eligible == rank≤40, verified). This is the binding data limitation the run inherits.",
        "A_live_favorite_realizable": {},
        "B_replay_cohorts_directional_and_tape": {},
        "coverage_overview": {},
    }

    # A. live favorite grid: category × band, category × champion-pool, and the pooled champion.
    live_grid = {}
    by_cat = defaultdict(list)
    for r in live:
        by_cat[r["category"]].append(r)
    for cat, rs in sorted(by_cat.items()):
        live_grid[cat] = {"_all_bands": summarize(rs, "entry")}
        for bname, lo, hi in C.BANDS:
            cell = [r for r in rs if lo <= r["entry"] < hi or (hi >= 0.98 and r["entry"] >= 0.98 and bname == "e_90_98")]
            if cell:
                live_grid[cat][bname] = summarize(cell, "entry")
        champ = [r for r in rs if C.CHAMP_LO <= r["entry"] <= C.CHAMP_HI]
        if champ:
            live_grid[cat]["champion_pool_71_98"] = summarize(champ, "entry")
    # the pooled champion across all categories (the incumbent to beat)
    champ_all = [r for r in live if C.CHAMP_LO <= r["entry"] <= C.CHAMP_HI]
    live_grid["_CHAMPION_POOLED_71_98"] = summarize(champ_all, "entry")
    report["A_live_favorite_realizable"] = live_grid

    # B. replay cohorts: cohort × category at the champion band, directional + tape-realizable.
    cohort_grid = {}
    for name, rowset in cohorts.items():
        champ_band = [r for r in rowset if r["band"] in ("c_71_82", "d_82_90", "e_90_98")]
        by_cat = defaultdict(list)
        for r in champ_band:
            by_cat[r["category"]].append(r)
        cg = {"_all_categories": {
            "directional": summarize(champ_band, "sharp_entry"),
            "tape_realizable": summarize(champ_band, "sharp_entry", realizable_key="tape_ask")}}
        for cat, rs in sorted(by_cat.items()):
            if len(rs) >= 5:
                cg[cat] = {"directional": summarize(rs, "sharp_entry"),
                           "tape_realizable": summarize(rs, "sharp_entry", realizable_key="tape_ask")}
        cohort_grid[name] = cg
    report["B_replay_cohorts_directional_and_tape"] = cohort_grid

    report["coverage_overview"] = {
        "live_favorite_realizable_picks": len(live),
        "live_favorite_realizable_matches": C.power_flags(
            [{**r, "entry": r["entry"]} for r in live])["n_matches"],
        "champion_pooled_71_98": report["A_live_favorite_realizable"]["_CHAMPION_POOLED_71_98"],
        "replay_top40_picks": len(cohorts["top40"]),
        "replay_wide_1_250_picks": len(cohorts["wide_1_250"]),
        "tape_window_days": 3,
        "powered_live_cells": sorted(
            f"{cat}/{b}" for cat, cells in live_grid.items() if isinstance(cells, dict)
            for b, v in cells.items() if isinstance(v, dict) and v.get("power_flag") == "POWERED"),
    }
    return report


def selftest():
    ok = True
    # category classifier traps
    checks = [("atp-a-b-2026-07-01", "tennis"), ("fifwc-x-y-2026-07-01", "soccer"),
              ("co-a-b-2026-07-01", "esports"), ("dota2-a-2026-07-01", "esports"),
              ("btc-updown-5m-1", "crypto"), ("will-x-happen", "nonsport")]
    for s, want in checks:
        if C.category(s) != want:
            print(f"FAIL category({s})={C.category(s)} want {want}"); ok = False
    # band classifier
    if not (C.band_of(0.75) == "c_71_82" and C.band_of(0.95) == "e_90_98" and C.band_of(0.60) == "a_55_65"):
        print("FAIL band_of"); ok = False
    # power_flags: 1 match, 1 day → not powered
    r1 = [{"entry": 0.8, "won": True, "event_slug": "atp-a-b-2026-07-01", "slug": "atp-a-b-2026-07-01-a",
           "condition_id": "c1", "day": "2026-07-01"}]
    if C.power_flags(r1)["meets_volume_floor"]:
        print("FAIL power under-vol"); ok = False
    # leg-piling guard: 30 markets of ONE match = 1 cluster, not 30
    piled = [{"entry": 0.8, "won": True, "event_slug": "fifwc-a-b-2026-07-01",
              "slug": f"fifwc-a-b-2026-07-01-m{i}", "condition_id": f"c{i}", "day": "2026-07-01"}
             for i in range(30)]
    if C.power_flags(piled)["n_matches"] != 1:
        print(f"FAIL leg-piling: {C.power_flags(piled)['n_matches']}"); ok = False
    # regime_key: two disjoint tennis weeks = 2 regimes
    rk1 = C.regime_key("atp-a-b-2026-07-01", "x")
    rk2 = C.regime_key("atp-a-b-2026-07-20", "x")
    if rk1 == rk2:
        print(f"FAIL regime_key weeks: {rk1}=={rk2}"); ok = False
    print("selftest PASS" if ok else "selftest FAIL")
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    rep = build()
    outp = Path(__file__).resolve().parent.parent / "reports" / "CELL-MAP.json"
    outp.write_text(json.dumps(rep, indent=2))
    print(f"wrote {outp}")
    print("powered live cells:", rep["coverage_overview"]["powered_live_cells"])
    print("champion pooled 0.71-0.98:", json.dumps(
        rep["A_live_favorite_realizable"]["_CHAMPION_POOLED_71_98"], indent=2))


if __name__ == "__main__":
    main()
