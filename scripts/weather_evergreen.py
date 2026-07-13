#!/usr/bin/env python3
"""
WEATHER-EVERGREEN (Weather Deepen run, WS3, 2026-07-12).

Weather is ONE evergreen daily venue; are there others the rank-40 gate hides? Enumerate the
recurring / daily / tournament-independent market families we track, and measure each on the LOCKED
objective (day-clustered cluster-robust realizable ROI-turn, belief-blind) at realizable entry —
reusing WS4's CLOB grader unchanged. Under-powered niches read INDETERMINATE. A second evergreen
copyable complement would be as valuable as improving weather; the honest answer may be "there isn't
one," which is itself money-saving (stops us widening into efficient coinflips).

Two-stage, cheap-first:
  1. TAXONOMY (DB only): count wider-universe (rank≤250) ≥3-backer FAVORITE-band (0.71-0.98)
     CONVERGENCE per niche. A niche with ~0 favorite convergence has no harvestable edge (its markets
     are coinflips with no favorite, or too thin) — reported and SKIPPED from grading.
  2. GRADE (CLOB, only the niches that clear a convergence-volume floor): the same day-clustered LB +
     LODO-by-week + blind-band skill as weather, via `weather_grade.grade(slug_pat=…)`.

Read-only. Emits reports/EVERGREEN-SCAN.json. Self-test: ./weather_evergreen.py --selftest
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cell_lib as C                                        # noqa: E402
import weather_verdict as V                                  # noqa: E402
from weather_grade import grade                               # noqa: E402

# recurring/daily families by slug regex; value = the pattern handed to the CLOB grader if it clears
# the convergence floor. Ordered specific→general. crypto up/down are ~0.5 coinflips (no favorite).
NICHES = [
    ("weather-hightemp", "highest-temperature"),
    ("weather-lowtemp", "lowest-temperature"),
    ("weather-precip", "rain|precipitation|snow"),
    ("weather-wind", "wind-speed|wind-in"),
    ("crypto-updown", "up-or-down"),
    ("crypto-threshold", "(bitcoin|ethereum|solana|xrp|dogecoin).*(above|below|reach|hit|dip-to)"),
]
CONV_FLOOR = 30          # need ≥30 favorite-convergence picks to bother CLOB-grading a niche


def taxonomy():
    """Wider-universe ≥3-backer favorite-band convergence count per niche (DB only, cheap)."""
    out = {}
    for name, pat in NICHES:
        rows = C.q(f"""
        WITH e AS (
          SELECT f.condition_id, f.outcome_index, LOWER(f.wallet) w, AVG(f.price) px, MIN(f.ts) ts
          FROM trader_fills f JOIN followed_traders ft ON ft.proxy_wallet=f.wallet
          WHERE f.side='BUY' AND f.ts>='{C.GO_LIVE}' AND ft.rank<=250 AND f.slug ~ '{pat}'
          GROUP BY 1,2,3),
        e1 AS (SELECT e.* FROM e WHERE NOT EXISTS
          (SELECT 1 FROM e x WHERE x.condition_id=e.condition_id AND x.w=e.w AND x.outcome_index<>e.outcome_index)),
        conv AS (SELECT condition_id, MIN(ts)::date d FROM e1 GROUP BY condition_id, outcome_index
                 HAVING count(*)>=3 AND AVG(px) BETWEEN 0.71 AND 0.98)
        SELECT count(*) picks, count(DISTINCT d) days FROM conv;
        """)
        picks = int(rows[0][0]) if rows else 0
        days = int(rows[0][1]) if rows else 0
        out[name] = {"pattern": pat, "conv_picks": picks, "conv_days": days,
                     "gradeable": picks >= CONV_FLOOR}
    return out


def measure_niche(name, pat, offline=False):
    picks, gstats = grade(offline=offline, slug_pat=pat)
    if len(picks) < 5:
        return {"niche": name, "graded": len(picks), "verdict": "INSUFFICIENT (graded<5)"}
    refined = [p for p in picks if 0.71 <= p["atfire"] < 0.90]
    def lb(ps):
        rows = [{"entry": p["atfire"], "won": p["won"], "cluster": p["cluster"],
                 "condition_id": p["condition_id"], "slug": p["slug"]} for p in ps]
        r = C.roi_lb(rows)
        return None if (r is None or r.get("lb") is None) else round(r["lb"], 4)
    # blind band edge on this niche (its own 1+-backer pool)
    pool, _ = grade(offline=offline, min_backers=1, slug_pat=pat)
    agg = defaultdict(lambda: [0.0, 0])
    for p in pool:
        agg[p["band"]][0] += (1.0 if p["won"] else 0.0) - p["atfire"]; agg[p["band"]][1] += 1
    blind = {b: v[0] / v[1] for b, v in agg.items() if v[1]}
    def skill(ps):
        if not ps:
            return None
        edge = sum((1.0 if p["won"] else 0.0) - p["atfire"] for p in ps) / len(ps)
        base = sum(blind.get(p["band"], 0.0) for p in ps) / len(ps)
        return round(edge - base, 4)
    weeks = defaultdict(set)
    for p in picks:
        weeks[V.week_of(p["cluster"])].add(p["cluster"])
    return {
        "niche": name, "graded": len(picks), "day_clusters": len({p["cluster"] for p in picks}),
        "weeks": {w: len(d) for w, d in sorted(weeks.items())},
        "full_0.71-0.98": {"LB": lb(picks), "skill_over_blind": skill(picks), "n": len(picks)},
        "refined_0.71-0.90": {"LB": lb(refined), "skill_over_blind": skill(refined), "n": len(refined),
                              "lodo_by_week": V.lodo_week(refined)},
        "verdict": ("INDETERMINATE (power) — day-clusters<20" if len({p["cluster"] for p in picks}) < 20
                    else "measured"),
    }


def build(offline=False):
    tax = taxonomy()
    graded = {}
    for name, pat in NICHES:
        if tax[name]["gradeable"]:
            graded[name] = measure_niche(name, pat, offline=offline)
    return {
        "as_of": "2026-07-12", "run": "weather deepen — WS3 (evergreen niche scan)",
        "objective": "day-clustered cluster-robust realizable ROI-turn (CLOB at-fire mid), belief-blind",
        "conv_floor_to_grade": CONV_FLOOR,
        "taxonomy": tax,
        "graded_niches": graded,
        "verdict_note": "Only niches clearing the convergence floor are CLOB-graded; the rest have no "
                        "wider-universe favorite convergence to harvest (coinflips / too thin). See "
                        "per-niche verdict; a niche is a real complement only if its realizable "
                        "belief-blind LB clears the same bar weather is held to over ≥2 disjoint weeks.",
    }


def selftest():
    ok = True
    if not any(n == "weather-lowtemp" for n, _ in NICHES):
        print("FAIL niches"); ok = False
    if CONV_FLOOR < 20:
        print("FAIL floor too low"); ok = False
    print("selftest PASS" if ok else "selftest FAIL")
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    rep = build()
    (Path(__file__).resolve().parent.parent / "reports" / "EVERGREEN-SCAN.json").write_text(
        json.dumps(rep, indent=2))
    print("wrote EVERGREEN-SCAN.json\n")
    print("taxonomy (wider-universe favorite convergence per niche):")
    for n, t in rep["taxonomy"].items():
        print(f"  {n:18} picks={t['conv_picks']:4} days={t['conv_days']:2} gradeable={t['gradeable']}")
    for n, g in rep["graded_niches"].items():
        if "full_0.71-0.98" not in g:
            print(f"\n  {n}: {g['verdict']}"); continue
        r = g["refined_0.71-0.90"]
        print(f"\n  {n}: graded={g['graded']} days={g['day_clusters']} weeks={g['weeks']}")
        print(f"    full LB {g['full_0.71-0.98']['LB']} skill {g['full_0.71-0.98']['skill_over_blind']}")
        print(f"    refined LB {r['LB']} skill {r['skill_over_blind']} "
              f"LODO {r['lodo_by_week'].get('lb_without_dominant')} | {g['verdict']}")


if __name__ == "__main__":
    main()
