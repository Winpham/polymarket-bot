#!/usr/bin/env python3
"""
WEATHER-VERDICT (Weather Edge Refinement run, phase 3, 2026-07-11).

The anti-overfit battery on the weather cell, DAY-clustered. Emits reports/WEATHER-VERDICT.json.

The decisive test is `selection_null` — the FORECAST-CO-READING guard. Weather is highly
forecastable public info; if the wider-universe "consensus" is just several bots reading the same
NOAA/ECMWF model and betting the market favorite, the selected picks are no better than a random
weather favorite at the same (band × day) and the surplus is a composition artifact (p high). Only a
LOW p means the sharps' SELECTION adds real skill over the blind weather favorite.

Battery: selection_null (p≤0.01, ≥1000 draws) · LODO-by-week (drop the dominant calendar week) ·
time-split OOS (early/late days) · Bonferroni over cells · copyability haircut (phase 2, ≈0) ·
champion day-level correlation (a complement must be low-correlated). Read-only; certifies nothing.

Self-test: ./weather_verdict.py --selftest
"""

import json
import math
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cell_lib as C                                    # noqa: E402
from weather_scan import fetch_weather_picks, fetch_blind_weather, day_of, city_of  # noqa: E402
from weather_regions import region                                                  # noqa: E402

SEED = 20260711
N_PERM = 2000
_MONTHS = {"jan": 0, "feb": 31, "mar": 59, "apr": 90, "may": 120, "jun": 151,
           "jul": 181, "aug": 212, "sep": 243, "oct": 273, "nov": 304, "dec": 334}


def week_of(day_stem):
    """ISO-ish week bucket from an 'on-<month>-<dd>' stem (dateless weather slug)."""
    m = re.search(r"on-([a-z]+)-(\d+)", day_stem or "")
    if not m:
        return "?"
    doy = _MONTHS.get(m.group(1)[:3], 0) + int(m.group(2))
    return f"w{doy // 7:02d}"


def clustered_surplus(items, blind_edge):
    """items: (day_cluster, band, a). Day-clustered mean of (a - blind_edge[band])."""
    ev = defaultdict(list)
    for cl, b, a in items:
        ev[cl].append(a - blind_edge.get(b, 0.0))
    if not ev:
        return float("nan")
    return sum(sum(v) / len(v) for v in ev.values()) / len(ev)


def selection_null(picks, blind_universe, blind_edge, rng, n_perm=N_PERM):
    """FORECAST-CO-READING guard. Observed = picks' day-clustered surplus over blind; null = random
    weather favorites from `_blind` matched to the picks' (band × day) profile. p = frac(null ≥ obs)."""
    # only picks whose at-fire band has a blind pool (0.71-0.98) can be matched — restrict to those
    # so the (band × day) profile is coverable (else every draw fails and p is undefined).
    inband = {b["band"] for b in blind_universe}
    picks = [p for p in picks if p["band"] in inband]
    obs = clustered_surplus([(p["cluster"], p["band"], (1.0 if p["won"] else 0.0) - p["atfire"])
                             for p in picks], blind_edge)
    cells = defaultdict(list)
    for b in blind_universe:
        cells[(b["band"], b["cluster"])].append((b["cluster"], b["band"], b["a"]))
    profile = defaultdict(int)
    for p in picks:
        profile[(p["band"], p["cluster"])] += 1
    ge = draws = 0
    for _ in range(n_perm):
        sel, ok = [], True
        for cell, k in profile.items():
            pool = cells.get(cell)
            if not pool:
                ok = False
                break
            sel.extend(rng.choices(pool, k=k) if k > len(pool) else rng.sample(pool, k))
        if not ok:
            continue
        draws += 1
        if clustered_surplus(sel, blind_edge) >= obs:
            ge += 1
    p = (ge + 1) / (draws + 1) if draws else None
    return {"observed_surplus": round(obs, 4), "p_emp": None if p is None else round(p, 4),
            "draws": draws, "pass_p01": (p is not None and p <= 0.01),
            "note": None if draws >= 1000 else "INSUFFICIENT matched draws (<1000)"}


def rows_atfire(picks):
    return [{"entry": p["atfire"], "won": p["won"], "cluster": p["cluster"],
             "condition_id": p["condition_id"], "slug": p["slug"]} for p in picks]


def clustering_bracket(picks):
    """Independent-N bracket: pure-DAY (over-conservative — lumps independent continents) vs
    (synoptic-region × DAY) (recovers spatial independence; may over-count temporal independence
    within one persistent week). The true LB lies between; report both, never one inflated number."""
    day_rows = rows_atfire(picks)
    reg_rows = [{**r, "cluster": region(p["city"]) + "|" + p["cluster"]}
                for r, p in zip(day_rows, picks)]
    dl, rl = C.roi_lb(day_rows), C.roi_lb(reg_rows)
    return {
        "day_clustered_LB": None if (dl is None or dl.get("lb") is None) else round(dl["lb"], 4),
        "day_clusters": None if dl is None else dl.get("G_clusters"),
        "region_day_LB": None if (rl is None or rl.get("lb") is None) else round(rl["lb"], 4),
        "region_day_clusters": None if rl is None else rl.get("G_clusters"),
        "note": "temporal caveat unchanged — all clusters within one calendar week (july 2-8); "
                "region-day recovers SPATIAL independence only, LODO-by-week still impossible.",
    }


def lodo_week(picks):
    by_week = defaultdict(list)
    for p in picks:
        by_week[week_of(p["cluster"])].append(p)
    weeks_over_2days = [w for w, ps in by_week.items() if len({p["cluster"] for p in ps}) >= 2]
    if len(weeks_over_2days) < 2:
        # THE single-window risk: all data in one calendar week ⇒ the leave-one-week-out
        # jackknife cannot run. Consecutive days also share weather regimes, so the effective
        # independent-N is well below the day count. This is the tennis-one-Wimbledon trap.
        return {"dropped_week": None, "lb_without_dominant": None, "n_weeks_over_2days": len(weeks_over_2days),
                "note": "SINGLE-WINDOW: <2 weeks with ≥2 day-clusters — LODO-by-week IMPOSSIBLE; "
                        "the edge is one consecutive-day window (regime-correlated), uncertifiable until "
                        "disjoint weeks accrue"}
    dom = max(by_week, key=lambda w: len({p["cluster"] for p in by_week[w]}))
    rest = [p for p in picks if week_of(p["cluster"]) != dom]
    lb = C.roi_lb(rows_atfire(rest))
    return {"dropped_week": dom, "n_weeks": len(by_week),
            "lb_without_dominant": None if (lb is None or lb.get("lb") is None) else round(lb["lb"], 4),
            "days_left": len({p["cluster"] for p in rest})}


def time_split(picks):
    days = sorted({p["cluster"] for p in picks}, key=week_of)
    if len(days) < 4:
        return {"note": f"only {len(days)} day-clusters — split not meaningful"}
    mid = days[len(days) // 2]
    order = {d: i for i, d in enumerate(days)}
    early = [p for p in picks if order[p["cluster"]] < len(days) // 2]
    late = [p for p in picks if order[p["cluster"]] >= len(days) // 2]
    le, ll = C.roi_lb(rows_atfire(early)), C.roi_lb(rows_atfire(late))
    g = lambda x: None if (x is None or x.get("lb") is None) else round(x["lb"], 4)
    return {"early_LB": g(le), "late_LB": g(ll), "split_at": mid}


def bonferroni_lb(picks, m):
    lb = C.roi_lb(rows_atfire(picks), alpha=0.05 / m)
    return {"alpha_adj": round(0.05 / m, 4), "m": m,
            "bonferroni_LB": None if (lb is None or lb.get("lb") is None) else round(lb["lb"], 4)}


def daily_returns(rows):
    num, den = defaultdict(float), defaultdict(float)
    for r in rows:
        num[r["day"]] += C.pnl(r["entry"], r["won"])
        den[r["day"]] += r["entry"]
    return {d: num[d] / den[d] for d in num if den[d] > 0}


def champion_daily():
    """Champion favorite 0.71-0.98 at-fire daily ROI-turn, keyed by calendar date."""
    rows = C.q(f"""
    SELECT first_detected_at::date, COALESCE(initial_mean_price,mean_price) e, outcome_won
    FROM consensus_signals
    WHERE strategy='favorite' AND resolved AND outcome_won IS NOT NULL
      AND COALESCE(initial_mean_price,mean_price) BETWEEN 0.71 AND 0.98;
    """)
    return daily_returns([{"day": r[0], "entry": float(r[1]), "won": r[2] == "t"} for r in rows])


def fetch_blind_universe():
    rows = C.q(f"""
    SELECT COALESCE(initial_mean_price,mean_price) e, outcome_won, slug, first_detected_at::date
    FROM consensus_signals
    WHERE strategy='_blind' AND resolved AND outcome_won IS NOT NULL AND slug ~ 'highest-temperature'
      AND COALESCE(initial_mean_price,mean_price) BETWEEN 0.71 AND 0.98;
    """)
    out = []
    for r in rows:
        e = float(r[0])
        out.append({"band": C.band_of(e) or "other", "cluster": day_of(r[2]),
                    "a": (1.0 if r[1] == "t" else 0.0) - e, "day": r[3]})
    return out


def correlation(a_rows, b_daily):
    """Day-level ROI correlation between the weather cell and the champion. a_rows use calendar day."""
    a_daily = daily_returns([{"day": r["day"], "entry": r["entry"], "won": r["won"]} for r in a_rows])
    common = sorted(set(a_daily) & set(b_daily))
    if len(common) < 3:
        return {"n_common_days": len(common), "corr": None, "note": "<3 shared calendar days"}
    xa = [a_daily[d] for d in common]
    xb = [b_daily[d] for d in common]
    ma, mb = sum(xa) / len(xa), sum(xb) / len(xb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(xa, xb))
    va = sum((x - ma) ** 2 for x in xa)
    vb = sum((y - mb) ** 2 for y in xb)
    if va <= 0 or vb <= 0:
        return {"n_common_days": len(common), "corr": None, "note": "zero variance"}
    return {"n_common_days": len(common), "corr": round(cov / math.sqrt(va * vb), 3)}


def assess(picks, label, blind_edge, blind_universe, champ_daily, rng, m):
    if len(picks) < 5:
        return {"label": label, "n_picks": len(picks), "verdict": "INSUFFICIENT"}
    base = C.roi_lb(rows_atfire(picks))
    base_lb = None if (base is None or base.get("lb") is None) else round(base["lb"], 4)
    lo = lodo_week(picks)
    ts = time_split(picks)
    bf = bonferroni_lb(picks, m)
    sn = selection_null(picks, blind_universe, blind_edge, rng)
    # correlation vs champion needs calendar day on the weather rows
    aw = [{"day": p["day"], "entry": p["atfire"], "won": p["won"]} for p in picks]
    corr = correlation(aw, champ_daily)
    passes = {
        "base_LB_positive": base_lb is not None and base_lb > 0,
        "lodo_week_survives": lo["lb_without_dominant"] is not None and lo["lb_without_dominant"] > 0,
        "bonferroni_positive": bf["bonferroni_LB"] is not None and bf["bonferroni_LB"] > 0,
        "selection_null_p01": sn["pass_p01"],
    }
    return {
        "label": label, "n_picks": len(picks), "day_clusters": len({p["cluster"] for p in picks}),
        "base_objective_LB": base_lb, "clustering_bracket": clustering_bracket(picks),
        "lodo_by_week": lo, "time_split": ts, "bonferroni": bf,
        "selection_null_FORECAST_CO_READING": sn,
        "champion_day_correlation": corr,
        "battery": passes,
        "survives_battery_modulo_power": all(passes.values()),
        "power_note": "day-clusters < 20 volume floor ⇒ INDETERMINATE regardless; the battery tests "
                      "whether the DIRECTION is real signal or a 7-day/forecast artifact.",
    }


def build():
    picks = fetch_weather_picks()
    blind_by_band = fetch_blind_weather()
    blind_edge = {b: e for b, (e, _n) in blind_by_band.items()}
    blind_universe = fetch_blind_universe()
    champ_daily = champion_daily()
    rng = random.Random(SEED)
    refined = [p for p in picks if 0.71 <= p["atfire"] < 0.90]   # a-priori: drop dead 0.90+ chalk
    M = 3
    return {
        "as_of": "2026-07-11", "run": "weather edge refinement — phase 3 (anti-overfit battery)",
        "cluster_unit": "resolution DAY (conservative — also lumps weather-independent global cities)",
        "M_cells": M,
        "candidates": {
            "WEATHER_0.71-0.98": assess(picks, "WEATHER_0.71-0.98", blind_edge, blind_universe,
                                        champ_daily, rng, M),
            "WEATHER_0.71-0.90_refined": assess(refined, "WEATHER_0.71-0.90_refined", blind_edge,
                                                blind_universe, champ_daily, rng, M),
        },
    }


def selftest():
    ok = True
    if week_of("on-july-11") != week_of("on-july-13"):
        print(f"FAIL week same: {week_of('on-july-11')} {week_of('on-july-13')}"); ok = False
    if week_of("on-july-04") == week_of("on-july-20"):
        print("FAIL week diff"); ok = False
    # clustered_surplus: 2 days, known
    s = clustered_surplus([("d1", "x", 0.1), ("d1", "x", 0.1), ("d2", "x", 0.2)], {})
    if abs(s - 0.15) > 1e-9:
        print(f"FAIL clustered_surplus {s}"); ok = False
    print("selftest PASS" if ok else "selftest FAIL")
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    rep = build()
    (Path(__file__).resolve().parent.parent / "reports" / "WEATHER-VERDICT.json").write_text(
        json.dumps(rep, indent=2))
    print("wrote WEATHER-VERDICT.json\n")
    for name, v in rep["candidates"].items():
        if "battery" not in v:
            print(f"  {name}: {v['verdict']}"); continue
        print(f"  {name}: LB {v['base_objective_LB']} days={v['day_clusters']} | "
              f"LODO-wk {v['lodo_by_week']['lb_without_dominant']} | "
              f"null p={v['selection_null_FORECAST_CO_READING']['p_emp']} | "
              f"bonf {v['bonferroni']['bonferroni_LB']} | champ-corr {v['champion_day_correlation'].get('corr')}")
        print(f"      battery={v['battery']} -> survives_modulo_power={v['survives_battery_modulo_power']}")


if __name__ == "__main__":
    main()
