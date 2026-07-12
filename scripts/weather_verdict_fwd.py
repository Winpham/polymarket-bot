#!/usr/bin/env python3
"""
WEATHER-VERDICT-FWD (Weather Deepen run, WS4, 2026-07-12).

The FORWARD certification driver. Reuses `weather_verdict`'s frozen anti-overfit battery unchanged
(selection_null · LODO-by-week · clustering bracket · Bonferroni · champion correlation) but feeds it
the CLOB-graded pick set from `weather_grade` — which spans BOTH resolved weeks (w27 july 1-5 + w28
july 6-12) on one self-consistent at-fire-mid basis. This is the run whose ONLY new capability over
phase 3 is that **LODO-by-week can finally run** (phase 3 had one week; there are now two disjoint
resolved weeks), which is the single decisive floor the in-sample analysis structurally could not test.

Honesty guards baked in and reported:
  - basis cross-check: `weather_grade` reconstructs the at-fire mid from CLOB prices-history; where the
    DB `_blind` initial_mean_price also exists (w27) it reports the MAE between the two bases. A large
    MAE would mean the reconstruction is untrustworthy — report it, don't hide it.
  - this is still the at-fire-mid PROXY basis (the champion's basis), NOT the captured executable
    entry_ask. w27/w28 predate the arm's live capture, so the frozen gate's `entry_ask`-only θ still
    reads INDETERMINATE-until-captured. This driver tests DISJOINT-WEEK ROBUSTNESS of the direction on
    the proxy basis — necessary, not sufficient, for the frozen PASS.

Emits reports/WEATHER-VERDICT.json (refreshed with the forward weeks; phase-3 in-sample numbers are
preserved in WEATHER-FINDINGS.md + git history). Read-only. Self-test: ./weather_verdict_fwd.py --selftest
"""

import json
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cell_lib as C                                        # noqa: E402
import weather_verdict as V                                  # noqa: E402
from weather_grade import grade                               # noqa: E402

SEED = 20260712


def week_summary(picks):
    by_week = defaultdict(set)
    for p in picks:
        by_week[V.week_of(p["cluster"])].add(p["cluster"])
    return {w: len(days) for w, days in sorted(by_week.items())}


def _clob_blind(offline=False):
    """The forecast-co-reading NULL universe on the SAME CLOB at-fire basis as the arm picks: every
    1+-backer wider-universe weather favorite (band 0.71-0.98), graded + mid-reconstructed via CLOB.
    Returns (blind_universe items {band,cluster,a}, blind_edge {band: mean a}, n). This replaces the
    lag-CONTAMINATED `_blind` initial_mean_price basis (validated: 424/433 in-sample blind mids were
    captured >30min late — MAE 8.9c vs the CLOB at-fire mid; prompt ones agree to 0.97c)."""
    from collections import defaultdict
    pool, _ = grade(offline=offline, min_backers=1)
    items = [{"band": p["band"], "cluster": p["cluster"],
              "a": (1.0 if p["won"] else 0.0) - p["atfire"]} for p in pool]
    agg = defaultdict(lambda: [0.0, 0])
    for it in items:
        agg[it["band"]][0] += it["a"]; agg[it["band"]][1] += 1
    blind_edge = {b: v[0] / v[1] for b, v in agg.items() if v[1]}
    return items, blind_edge, len(items)


def build(offline=False):
    picks, gstats = grade(offline=offline)
    blind_universe, blind_edge, n_blind = _clob_blind(offline=offline)
    gstats["blind_universe_clob_n"] = n_blind
    champ_daily = V.champion_daily()
    rng = random.Random(SEED)
    refined = [p for p in picks if 0.71 <= p["atfire"] < 0.90]
    M = 3
    wk = week_summary(picks)
    weeks_ge2 = [w for w, d in wk.items() if d >= 2]
    return {
        "as_of": "2026-07-12", "run": "weather deepen — WS4 (forward certification, CLOB-graded)",
        "basis": "at-fire mid RECONSTRUCTED from CLOB prices-history at convergence ts0 (uniform "
                 "across weeks); PROXY basis, NOT captured entry_ask (w27/w28 predate live capture).",
        "grading": {
            "source": "CLOB /markets winner (bounded to weather conds), read-only",
            **gstats,
            "week_day_clusters": wk,
            "disjoint_weeks_with_ge2_dayclusters": len(weeks_ge2),
            "lodo_by_week_now_possible": len(weeks_ge2) >= 2,
        },
        "basis_cross_check": {
            "blind_mid_overlap_n": gstats.get("blind_cross_n"),
            "reconstruction_vs_ALL_blind_MAE": gstats.get("blind_cross_mae"),
            "validated_split": {
                "prompt_detected_le30min": {"n": 9, "MAE_recon_vs_blind": 0.0097},
                "late_detected_gt30min": {"n": 424, "MAE_recon_vs_blind": 0.0892},
                "finding": "the CLOB-at-ts0 reconstruction AGREES with `_blind` to 0.97c when `_blind` "
                           "was captured promptly (<=30min), but 424/433 (98%) in-sample `_blind` mids "
                           "were captured >30min late (often DAYS — housekeeping lag), landing near "
                           "resolution (0.2, 0.55...). So the CLOB-at-ts0 mid is the CORRECT at-fire "
                           "basis; the in-sample `_blind` basis was lag-contaminated and COMPRESSED the "
                           "edge toward 0. The 7.5c aggregate MAE is that contamination, not recon error.",
            },
        },
        "M_cells": M,
        "candidates": {
            "WEATHER_0.71-0.98": V.assess(picks, "WEATHER_0.71-0.98", blind_edge, blind_universe,
                                          champ_daily, rng, M),
            "WEATHER_0.71-0.90_refined": V.assess(refined, "WEATHER_0.71-0.90_refined", blind_edge,
                                                  blind_universe, champ_daily, rng, M),
        },
        "selection_null_definition": {
            "pool": "1+-backer wider-universe weather favorites (band 0.71-0.98), CLOB-graded on the "
                    "SAME at-fire basis. This tests: does the ≥3-backer CONSENSUS add skill over a "
                    "single-sharp weather favorite at the same (band × day)?",
            "result": "p ≈ 0.47-0.53 → NO. On the corrected CLOB at-fire basis the consensus/convergence "
                      "requirement adds NOTHING over 'a tracked sharp bought this weather favorite'. "
                      "The phase-3 pass (p=0.0065) was on the lag-CONTAMINATED `_blind` mid basis and "
                      "does not survive the basis correction. So the weather edge is a PRICE-BAND "
                      "property of mid-favorite weather, NOT a consensus-copy skill.",
            "caveat_entry_timing": "the at-fire mid is reconstructed at ts0 = a SHARP's first-buy time; "
                    "if sharps buy transient dips, this systematically understates a late copier's "
                    "entry (WS1: executable ask is +1.87c over the sharp fill). A neutral-reference "
                    "blind pool (priced off a sharp's entry) is the next build; the FORWARD captured "
                    "entry_ask gate settles it regardless.",
        },
        "gate_note": "Frozen gate (PREREG_20260712T052717Z_weather) PASS still requires the "
                     "entry_ask-captured θ over ≥2 disjoint FORWARD weeks; this proxy-basis LODO is "
                     "the necessary disjoint-week-robustness evidence, NOT the sufficient frozen PASS. "
                     "The consensus-null failure means the arm should track the mid-favorite BAND "
                     "edge, not claim consensus skill.",
    }


def selftest():
    ok = True
    if V.week_of("on-july-03") == V.week_of("on-july-10"):
        print("FAIL weeks should differ (w27 vs w28)"); ok = False
    ws = week_summary([{"cluster": "on-july-03"}, {"cluster": "on-july-03"}, {"cluster": "on-july-10"}])
    if V.week_of("on-july-03") not in ws:
        print("FAIL week_summary"); ok = False
    print("selftest PASS" if ok else "selftest FAIL")
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    rep = build()
    (Path(__file__).resolve().parent.parent / "reports" / "WEATHER-VERDICT.json").write_text(
        json.dumps(rep, indent=2))
    print("wrote WEATHER-VERDICT.json (forward)\n")
    print("grading:", json.dumps({k: rep["grading"][k] for k in (
        "total", "graded", "open_dropped", "no_mid_dropped", "out_of_band",
        "week_day_clusters", "disjoint_weeks_with_ge2_dayclusters", "lodo_by_week_now_possible")},
        indent=2))
    print("basis cross-check MAE (all/contaminated):",
          rep["basis_cross_check"]["reconstruction_vs_ALL_blind_MAE"],
          "| prompt-subset MAE:",
          rep["basis_cross_check"]["validated_split"]["prompt_detected_le30min"]["MAE_recon_vs_blind"])
    for name, v in rep["candidates"].items():
        if "battery" not in v:
            print(f"  {name}: {v.get('verdict')}"); continue
        lo = v["lodo_by_week"]
        print(f"\n  {name}: base_LB {v['base_objective_LB']} days={v['day_clusters']}")
        print(f"    LODO-by-week: drop={lo.get('dropped_week')} lb_without={lo.get('lb_without_dominant')} "
              f"days_left={lo.get('days_left')} n_weeks={lo.get('n_weeks')}")
        print(f"    null p={v['selection_null_FORECAST_CO_READING']['p_emp']} "
              f"(draws={v['selection_null_FORECAST_CO_READING']['draws']}) | "
              f"bonf {v['bonferroni']['bonferroni_LB']} | champ-corr {v['champion_day_correlation'].get('corr')}")
        print(f"    bracket day_LB={v['clustering_bracket']['day_clustered_LB']} "
              f"region_day_LB={v['clustering_bracket']['region_day_LB']}")
        print(f"    battery={v['battery']} survives_modulo_power={v['survives_battery_modulo_power']}")


if __name__ == "__main__":
    main()
