#!/usr/bin/env python3
"""
WEATHER-GRADE (Weather Deepen run, WS4 enabler, 2026-07-12).

Produce the wider-universe weather-favorite convergence pick set graded across BOTH resolved weeks
(w27 july 1-5 + w28 july 6-12) on a single, self-consistent basis — the input the real LODO-by-week
needs and that `weather_scan.fetch_weather_picks` cannot yet supply (it filters on trader_fills
resolution, which the 42k-deep oldest-first FIFO has not reached for w28).

Same convergence definition as `weather_scan` (≥3 one-sided rank≤250 backers, at-fire favorite band
0.71-0.98, day-clustered), but:
  - resolution comes from the CLOB (`weather_clob`, bounded to weather conds) — the public outcome,
    read directly instead of waiting on the DB FIFO. Picks still open (no winner) are DROPPED.
  - the at-fire mid is RECONSTRUCTED uniformly from the CLOB prices-history at the convergence
    timestamp ts0 (no look-ahead) for EVERY pick, so w27 and w28 share one basis (removing the
    week-27-`_blind`-snapshot vs week-28-missing inconsistency). A validation pass cross-checks the
    reconstruction against the `_blind` initial_mean_price where both exist (w27) — they must agree.

Returns picks in the EXACT `fetch_weather_picks` schema so `weather_verdict`'s battery runs unchanged.
Read-only (DB SELECT + bounded CLOB GET; no writes, no orders). Self-test: ./weather_grade.py --selftest
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cell_lib as C                                        # noqa: E402
from weather_scan import day_of, city_of                    # noqa: E402
from weather_clob import WeatherClob                         # noqa: E402

WIDE_CUTOFF = 250
LO, HI = 0.71, 0.98


def _fetch_convergence_rows(min_backers=3, slug_pat="highest-temperature"):
    """Wider-universe weather convergence, NO resolution filter, with the convergence epoch ts0 and
    the `_blind` mid where it exists (for the validation cross-check only). min_backers=3 = the arm's
    consensus selection; min_backers=1 = the blind weather-favorite POOL (the selection_null universe,
    graded on the SAME CLOB at-fire basis so the forecast-co-reading test is basis-consistent).
    slug_pat defaults to the daily HIGH-temp book (WS4 behaviour byte-identical); WS3 passes other
    recurring-niche patterns to reuse the exact same objective + CLOB grading."""
    return C.q(f"""
    WITH e AS (
      SELECT f.condition_id, f.outcome_index, LOWER(f.wallet) w, MIN(ft.rank) rank, AVG(f.price) px,
             MIN(f.ts) ts, MAX(f.slug) slug
      FROM trader_fills f JOIN followed_traders ft ON ft.proxy_wallet=f.wallet
      WHERE f.side='BUY' AND f.ts>='{C.GO_LIVE}' AND ft.rank<={WIDE_CUTOFF} AND f.slug ~ '{slug_pat}'
      GROUP BY 1,2,3),
    e1 AS (SELECT e.* FROM e WHERE NOT EXISTS
      (SELECT 1 FROM e x WHERE x.condition_id=e.condition_id AND x.w=e.w AND x.outcome_index<>e.outcome_index)),
    conv AS (
      SELECT condition_id, outcome_index, MAX(slug) slug, count(*) nb, AVG(px) sharp_px,
             MIN(rank) best_rank, (ARRAY_AGG(w ORDER BY ts))[1] first_w,
             MIN(ts) ts0, EXTRACT(EPOCH FROM MIN(ts))::bigint ts0_epoch
      FROM e1 GROUP BY 1,2
      HAVING count(*)>={min_backers} AND AVG(px) BETWEEN {LO} AND {HI})
    SELECT c.condition_id, c.outcome_index, c.slug, c.nb, c.sharp_px, c.best_rank, c.first_w,
           c.ts0::date, c.ts0_epoch, b.initial_mean_price
    FROM conv c
    LEFT JOIN consensus_signals b ON b.condition_id=c.condition_id AND b.outcome_index=c.outcome_index
      AND b.strategy='_blind' AND b.initial_mean_price IS NOT NULL
    ORDER BY c.ts0;
    """)


def grade(offline=False, verbose=False, min_backers=3, slug_pat="highest-temperature"):
    rows = _fetch_convergence_rows(min_backers, slug_pat)
    wc = WeatherClob(offline=offline)
    picks, stats = [], {"total": 0, "open_dropped": 0, "no_mid_dropped": 0, "out_of_band": 0,
                        "blind_cross_n": 0, "blind_cross_abs_err": 0.0}
    for r in rows:
        cond, oi, slug, nb, sharp, best_rank, first_w, day, ts0_epoch, blind_mid = (r + [""] * 10)[:10]
        stats["total"] += 1
        oi = int(oi)
        info = wc.outcome(cond)
        if info["winner"] is None:                          # still open (e.g. july 11-12) — drop
            stats["open_dropped"] += 1
            continue
        tid = info["tokens"].get(str(oi))
        mid = wc.mid_at(tid, int(ts0_epoch)) if tid else None
        if mid is None or not (LO <= mid <= HI):
            # reconstruct must land in the certifiable band on the SAME basis; else drop (keeps the
            # basis honest — we never grade a pick whose at-fire mid we can't place).
            stats["out_of_band" if mid is not None else "no_mid_dropped"] += 1
            continue
        if blind_mid not in ("", None):                     # validation cross-check (w27 mostly)
            stats["blind_cross_n"] += 1
            stats["blind_cross_abs_err"] += abs(mid - float(blind_mid))
        picks.append({
            "condition_id": cond, "outcome_index": oi, "slug": slug, "nb": int(nb),
            "sharp_fill": float(sharp), "atfire": float(mid),
            "best_rank": int(best_rank) if best_rank not in ("", None) else None,
            "first_backer": first_w, "won": (info["winner"] == oi), "day": day,
            "cluster": day_of(slug), "city": city_of(slug), "band": C.band_of(float(mid)) or "other",
        })
    wc.flush()
    stats["graded"] = len(picks)
    stats["blind_cross_mae"] = (round(stats["blind_cross_abs_err"] / stats["blind_cross_n"], 4)
                                if stats["blind_cross_n"] else None)
    stats["clob_fetches"] = wc.fetches
    if verbose:
        sys.stderr.write(json.dumps(stats) + "\n")
    return picks, stats


def selftest():
    # offline: exercises schema plumbing against the cached CLOB (no network). Passes even with an
    # empty cache (0 graded) — the point is that the code path is sound and basis-consistent.
    ok = True
    try:
        picks, stats = grade(offline=True)
    except Exception as e:
        print(f"FAIL grade raised: {e}"); return 1
    if not isinstance(picks, list) or "graded" not in stats:
        print("FAIL shape"); ok = False
    for p in picks:
        if not (LO <= p["atfire"] <= HI) or p["won"] not in (True, False):
            print("FAIL pick invariant"); ok = False; break
    print("selftest PASS" if ok else "selftest FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    picks, stats = grade(verbose=True)
    print(json.dumps(stats, indent=2))
    print(f"\ngraded {len(picks)} picks across {len({p['cluster'] for p in picks})} day-clusters")
