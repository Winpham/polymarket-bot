#!/usr/bin/env python3
"""
WEATHER-SCAN (Weather Edge Refinement run, phases 1-2, 2026-07-11).

Give the daily-weather cell the SAME rigorous, belief-blind treatment the champion `favorite`
0.71-0.98 got. Map the weather cell space + measure the edge on the LOCKED objective, DAY-clustered
(cross-city same-day temperature is correlated — a heat dome resolves 20 cities "hot favorite"
together, so the honest independent unit is the resolution DAY, never the city-market).

Two price bases (the copyability story):
  atfire_mid = COALESCE(initial_mean_price, mean_price) on the `_blind` weather signal for the SAME
               (condition, outcome) — the CLOB mid ~10-15 min post-convergence, present on the FULL
               weather-favorite population (unbiased sample), the champion's realizable-PROXY basis and
               a fast-copier's fill. PRIMARY.
  sharp_fill = the wider-universe (rank<=250) backers' own mean fill — DIRECTIONAL ceiling (context).
The gap (atfire_mid - sharp_fill) is the copyability haircut: ~0 ⇒ the edge is copyable-in-principle;
the executable ASK spread on thin weather books stays the FORWARD unknown the shadow arm captures.

Belief-blind SKILL = surplus over the `_blind` weather favorite at the same band (both at atfire_mid).
A weather cell whose edge ≈ its blind baseline is riding structure/forecastability, not consensus skill.

Emits reports/WEATHER-MAP.json (power flags) + reports/WEATHER-EDGE.json (edge, ranked).
CERTIFIES nothing. Self-test: ./weather_scan.py --selftest
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cell_lib as C                                    # noqa: E402

WIDE_CUTOFF = 250
LO, HI = 0.71, 0.98
# Both weather families share the slug shape `<family>-in-<city>-on-<day>`.
_CITY = re.compile(r"(?:highest|lowest)-temperature-in-([a-z-]+?)-on-")
# The market FAMILY under measurement (slug regex). Set via set_family(); defaults to the
# incumbent highest-temperature branch so every existing caller behaves EXACTLY as before.
FAMILY = "highest-temperature"
_DAY = re.compile(r"(on-[a-z]+-\d+)")


def set_family(regex):
    """Point the instrument at ONE evergreen market family (e.g. 'lowest-temperature').

    Each family is a SEPARATE branch with its own book, its own optimization and its own frozen
    gate — never a blended `temperature` filter, because high- and low-temperature markets have
    different mechanisms (the casual crowd prices highs about right but MIS-prices lows)."""
    global FAMILY
    FAMILY = regex


def city_of(slug):
    m = _CITY.search(slug or "")
    return m.group(1) if m else "?"


def day_of(slug):
    m = _DAY.search(slug or "")
    return m.group(1) if m else "?"


def fetch_weather_picks():
    """Family-scoped (see set_family): wider-universe convergence on THIS family's favorites."""
    """Wider-universe (rank<=250) weather-favorite convergence (>=3 one-sided backers, band, resolved),
    joined to the `_blind` at-fire mid for the SAME (condition,outcome). One row per (condition,outcome)."""
    rows = C.q(f"""
    WITH e AS (
      SELECT f.condition_id, f.outcome_index, LOWER(f.wallet) w, MIN(ft.rank) rank, AVG(f.price) px,
             MIN(f.ts) ts, MAX(f.slug) slug, BOOL_OR(f.resolved) rz, BOOL_OR(f.outcome_won) won
      FROM trader_fills f JOIN followed_traders ft ON ft.proxy_wallet=f.wallet
      WHERE f.side='BUY' AND f.ts>='{C.GO_LIVE}' AND ft.rank<={WIDE_CUTOFF} AND f.slug ~ '{FAMILY}'
      GROUP BY 1,2,3),
    e1 AS (SELECT e.* FROM e WHERE NOT EXISTS
      (SELECT 1 FROM e x WHERE x.condition_id=e.condition_id AND x.w=e.w AND x.outcome_index<>e.outcome_index)),
    conv AS (
      SELECT condition_id, outcome_index, MAX(slug) slug, count(*) nb, AVG(px) sharp_px,
             MIN(rank) best_rank, (ARRAY_AGG(w ORDER BY ts))[1] first_w, BOOL_OR(rz) rz, BOOL_OR(won) won,
             MIN(ts) ts0
      FROM e1 GROUP BY 1,2
      HAVING count(*)>=3 AND AVG(px) BETWEEN {LO} AND {HI})
    SELECT c.condition_id, c.outcome_index, c.slug, c.nb, c.sharp_px, c.best_rank, c.first_w, c.won,
           b.initial_mean_price, c.ts0::date
    FROM conv c
    JOIN consensus_signals b ON b.condition_id=c.condition_id AND b.outcome_index=c.outcome_index
      AND b.strategy='_blind'
    WHERE c.rz AND c.won IS NOT NULL AND b.initial_mean_price IS NOT NULL;
    """)
    out = []
    for r in rows:
        cond, oi, slug, nb, sharp, best_rank, first_w, won, atfire, day = (r + [""] * 10)[:10]
        atfire = float(atfire)
        out.append({
            "condition_id": cond, "outcome_index": int(oi), "slug": slug, "nb": int(nb),
            "sharp_fill": float(sharp), "atfire": atfire, "best_rank": int(best_rank) if best_rank else None,
            "first_backer": first_w, "won": won == "t", "day": day,
            "cluster": day_of(slug), "city": city_of(slug), "band": C.band_of(atfire) or "other",
        })
    return out


def fetch_blind_weather():
    """`_blind` weather favorite baseline mean(won-atfire) per band (the softness/forecastability floor)."""
    rows = C.q(f"""
    SELECT COALESCE(initial_mean_price, mean_price) e, outcome_won
    FROM consensus_signals
    WHERE strategy='_blind' AND resolved AND outcome_won IS NOT NULL AND slug ~ '{FAMILY}'
      AND COALESCE(initial_mean_price, mean_price) BETWEEN {LO} AND {HI};
    """)
    agg = defaultdict(lambda: [0.0, 0])
    for r in rows:
        e, won = float(r[0]), r[1] == "t"
        b = C.band_of(e)
        agg[b][0] += (1.0 if won else 0.0) - e
        agg[b][1] += 1
    return {b: (v[0] / v[1], v[1]) for b, v in agg.items() if v[1]}


def measure(picks, label, blind, basis="atfire"):
    """Day-clustered objective on ONE basis. picks carry 'cluster'=resolution day."""
    rows = [{"entry": p[basis], "won": p["won"], "cluster": p["cluster"],
             "condition_id": p["condition_id"], "slug": p["slug"]} for p in picks]
    if len(rows) < 2:
        return {"label": label, "n_picks": len(rows), "verdict": "INSUFFICIENT"}
    lb = C.roi_lb(rows)
    boot = C.bootstrap_lb(rows)
    days = {p["cluster"] for p in picks}
    cities = {p["city"] for p in picks}
    # belief-blind skill (at-fire basis), pooled over the cell's band mix
    num = den = 0.0
    for p in picks:
        b = blind.get(p["band"])
        if b:
            num += b[0]; den += 1
    blind_edge = num / den if den else None
    cell_edge = sum((1.0 if p["won"] else 0.0) - p["atfire"] for p in picks) / len(picks)
    # concentration: top-city and top-first-backer share of picks
    by_city = defaultdict(int)
    by_w = defaultdict(int)
    for p in picks:
        by_city[p["city"]] += 1
        by_w[p["first_backer"]] += 1
    top_city_share = max(by_city.values()) / len(picks)
    top_wallet_share = max(by_w.values()) / len(picks)
    return {
        "label": label, "basis": basis, "n_picks": len(rows),
        "roi_turn_point": None if lb is None else round(lb["point"], 4),
        "roi_turn_LB": None if (lb is None or lb.get("lb") is None) else round(lb["lb"], 4),
        "bootstrap_LB": None if boot is None else round(boot["lb"], 4),
        "day_clusters": len(days), "n_cities": len(cities),
        "win_rate_diag": round(C.win_rate(rows), 3),
        "mean_edge_atfire": round(cell_edge, 4),
        "blind_baseline": None if blind_edge is None else round(blind_edge, 4),
        "skill_over_blind": None if blind_edge is None else round(cell_edge - blind_edge, 4),
        "top_city_share_diag": round(top_city_share, 3),
        "top_firstbacker_share_diag": round(top_wallet_share, 3),
        "meets_volume_floor": len(days) >= C.VOL_FLOOR,
        "meets_duration_floor": len(days) >= C.DUR_FLOOR_DAYS,
        "verdict": ("INDETERMINATE (volume<20 day-clusters=%d)" % len(days)) if len(days) < C.VOL_FLOOR
                   else ("POSITIVE_LB" if (lb and lb.get("lb") and lb["lb"] > 0) else "NON_POSITIVE_LB"),
    }


def build():
    picks = fetch_weather_picks()
    blind = fetch_blind_weather()
    cells = []
    cells.append(measure(picks, "WEATHER_all_0.71-0.98", blind, "atfire"))
    cells.append(measure(picks, "WEATHER_all_0.71-0.98_sharpfill", blind, "sharp_fill"))
    for bname, lo, hi in [("b_71_82", 0.71, 0.82), ("c_82_90", 0.82, 0.90), ("d_90_98", 0.90, 0.999)]:
        sub = [p for p in picks if lo <= p["atfire"] < hi or (hi >= 0.99 and p["atfire"] >= 0.98)]
        if len(sub) >= 5:
            cells.append(measure(sub, f"WEATHER_band_{bname}", blind, "atfire"))

    hair = (sum(p["atfire"] - p["sharp_fill"] for p in picks) / len(picks)) if picks else None
    ncity = len({p["city"] for p in picks})
    map_report = {
        "as_of": "2026-07-11", "run": "weather edge refinement — phase 1 (map + power)",
        "cluster_unit": "resolution DAY (cross-city same-day temp correlated; city-market over-counts)",
        "coverage": {
            "consensus_picks": len(picks),
            "day_clusters": len({p["cluster"] for p in picks}),
            "distinct_cities": ncity,
            "bands": {b: sum(1 for p in picks if p["band"] == b) for b in sorted({p["band"] for p in picks})},
            "copyability_haircut_atfire_minus_sharp": None if hair is None else round(hair, 4),
        },
        "power_note": f"only {len({p['cluster'] for p in picks})} independent day-clusters — below the "
                      f"20-cluster volume floor; weather is EVERGREEN so this accrues daily forward.",
    }
    edge_report = {
        "as_of": "2026-07-11", "run": "weather edge refinement — phase 2 (edge)",
        "objective": "day-clustered cluster-robust 95% LB of realizable-proxy (at-fire mid) ROI-turn",
        "blind_baseline_by_band": {b: {"edge": round(e, 4), "n": n} for b, (e, n) in blind.items()},
        "cells": cells,
        "headline": next((c for c in cells if c["label"] == "WEATHER_all_0.71-0.98"), None),
    }
    return map_report, edge_report


def selftest():
    ok = True
    if city_of("highest-temperature-in-nyc-on-july-11") != "nyc":
        print("FAIL city"); ok = False
    if day_of("highest-temperature-in-nyc-on-july-11") != "on-july-11":
        print("FAIL day"); ok = False
    # day-clustering: 20 cities same day = 1 cluster
    picks = [{"atfire": 0.8, "sharp_fill": 0.8, "won": True, "cluster": "on-july-11",
              "condition_id": f"c{i}", "slug": f"highest-temperature-in-city{i}-on-july-11",
              "city": f"city{i}", "band": "c_82_90", "first_backer": "w"} for i in range(20)]
    m = measure(picks, "t", {"c_82_90": (0.02, 100)})
    if m["day_clusters"] != 1:
        print(f"FAIL day-cluster: {m['day_clusters']}"); ok = False
    print("selftest PASS" if ok else "selftest FAIL")
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    mp, ed = build()
    base = Path(__file__).resolve().parent.parent / "reports"
    (base / "WEATHER-MAP.json").write_text(json.dumps(mp, indent=2))
    (base / "WEATHER-EDGE.json").write_text(json.dumps(ed, indent=2))
    print("wrote WEATHER-MAP.json + WEATHER-EDGE.json\n")
    print("coverage:", json.dumps(mp["coverage"], indent=2))
    print("\n=== cells (day-clustered) ===")
    for c in ed["cells"]:
        print(f"  {c['label']}: LB {c.get('roi_turn_LB')} pt {c.get('roi_turn_point')} "
              f"boot {c.get('bootstrap_LB')} | days={c.get('day_clusters')} skill {c.get('skill_over_blind')} "
              f"| topcity {c.get('top_city_share_diag')} | {c.get('verdict')}")


if __name__ == "__main__":
    main()
