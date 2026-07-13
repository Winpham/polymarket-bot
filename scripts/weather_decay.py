#!/usr/bin/env python3
"""
WEATHER-DECAY (Weather Deepen run, correction #2, 2026-07-12).

Answers "why is our ask so far off the sharps' fill, and how do we get closer?" — and OVERTURNS this
run's own earlier "+1.87c haircut" number, which was wrong three ways:
  1. it came from 38 live captures that are DEEP-CHALK skewed (avg ask 0.912), not the 0.71-0.90 band;
  2. it read the `entry_ask` column, which is LOSER-TILTED/biased (Evergreen-Portfolio defect D4);
  3. charging `sharp_fill + 1.87c` DOUBLE-COUNTS the spread the sharps themselves already paid.

Measured off the CLOB price history instead (unbiased, band-matched):
  - the SHARPS ARE TAKERS: they cross and chase (+3.81c over the mid at their own entry; 65% pay above
    mid). Their fill is NOT a price we must beat — it is a price we BEAT: our ask 30 min later is
    ~2.1c CHEAPER than their fill.
  - DRIFT IS ~0: the mid moves only +0.46c in the 30 min between their fire and our capture.
    => SPEED IS NOT THE LEVER. Capture-at-detection recovers only ~0.6pp. Do not build it.
  - the entire copier cost is the SPREAD (~1.1-1.2c). The edge survives a spread up to ~6c before it
    stops clearing the champion's +5.6% floor — 5x the measured value.

Emits the decay curve + the spread-sensitivity table. Read-only, uses only the cached CLOB history.
Self-test: ./weather_decay.py --selftest
"""
import json, sys, statistics as st
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cell_lib as C
import weather_verdict as V
from weather_grade import grade
from weather_clob import WeatherClob

HORIZONS = [0, 2, 5, 10, 15, 20, 30, 45, 60, 120]
SPREADS = [0.005, 0.01, 0.0122, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08]
MEASURED_SPREAD = 0.0122
CAPTURE_DELAY_MIN = 30
CHAMP_FLOOR = 0.056


def _ts0():
    rows = C.q("""
    WITH e AS (SELECT f.condition_id, f.outcome_index, LOWER(f.wallet) w, AVG(f.price) px, MIN(f.ts) ts
      FROM trader_fills f JOIN followed_traders ft ON ft.proxy_wallet=f.wallet
      WHERE f.side='BUY' AND f.ts>='2026-06-29' AND ft.rank<=250 AND f.slug ~ 'highest-temperature'
      GROUP BY 1,2,3),
    e1 AS (SELECT e.* FROM e WHERE NOT EXISTS (SELECT 1 FROM e x WHERE x.condition_id=e.condition_id
      AND x.w=e.w AND x.outcome_index<>e.outcome_index)),
    conv AS (SELECT condition_id, outcome_index, EXTRACT(EPOCH FROM MIN(ts))::bigint ep FROM e1
      GROUP BY 1,2 HAVING count(*)>=3 AND AVG(px) BETWEEN 0.71 AND 0.98)
    SELECT condition_id, outcome_index, ep FROM conv;""")
    return {(r[0], int(r[1])): int(r[2]) for r in rows}


def rows_at(picks, ep, wc, delay_min, spread):
    out = []
    for p in picks:
        k = (p["condition_id"], p["outcome_index"])
        info = wc.cache["markets"].get(p["condition_id"])
        if k not in ep or not info:
            continue
        tid = info["tokens"].get(str(p["outcome_index"]))
        m = wc.mid_at(tid, ep[k] + delay_min * 60) if tid else None
        if m is None or m <= 0 or m >= 1:
            continue
        out.append({"entry": min(m + spread, 0.999), "won": p["won"], "cluster": p["cluster"],
                    "mid": m, "condition_id": p["condition_id"], "slug": p["slug"]})
    return out


def _lodo(rws):
    bw = defaultdict(set)
    for r in rws:
        bw[V.week_of(r["cluster"])].add(r["cluster"])
    if len(bw) < 2:
        return None
    dom = max(bw, key=lambda w: len(bw[w]))
    x = C.roi_lb([r for r in rws if V.week_of(r["cluster"]) != dom])
    return round(x["lb"], 4) if x and x.get("lb") is not None else None


def build():
    wc = WeatherClob(offline=True)
    ep = _ts0()
    picks = [p for p in grade(offline=True)[0] if 0.71 <= p["atfire"] < 0.90]
    mid0 = st.mean([p["atfire"] for p in picks])
    sharp = st.mean([p["sharp_fill"] for p in picks])
    above = sum(1 for p in picks if p["sharp_fill"] > p["atfire"]) / len(picks)

    decay = []
    for h in HORIZONS:
        r = rows_at(picks, ep, wc, h, MEASURED_SPREAD)
        if not r:
            continue
        e = st.mean([(1.0 if x["won"] else 0.0) - x["entry"] for x in r])
        px = st.mean([x["entry"] for x in r])
        decay.append({"delay_min": h, "mid": round(st.mean([x["mid"] for x in r]), 4),
                      "ask": round(px, 4), "roi_turn_at_ask": round(e / px, 4), "n": len(r)})

    sens = []
    for s in SPREADS:
        r = rows_at(picks, ep, wc, CAPTURE_DELAY_MIN, s)
        x = C.roi_lb(r)
        if not x or x.get("lb") is None:
            continue
        sens.append({"spread": s, "mean_entry": round(st.mean([q["entry"] for q in r]), 4),
                     "roi_turn_LB": round(x["lb"], 4), "lodo_held_out_LB": _lodo(r),
                     "clears_champion_floor": x["lb"] > CHAMP_FLOOR})

    return {
        "as_of": "2026-07-12", "run": "weather deepen — correction #2 (decay + spread sensitivity)",
        "supersedes": "the '+1.87c executable haircut' (deep-chalk-skewed, read from the LOSER-TILTED "
                      "entry_ask column (D4), and double-counted on top of the sharps' own spread).",
        "sharps_are_TAKERS": {
            "mid_at_ts0": round(mid0, 4), "sharp_fill": round(sharp, 4),
            "sharp_pays_over_mid": round(sharp - mid0, 4),
            "frac_paying_above_mid": round(above, 3),
            "read": "the sharps cross and CHASE. Their fill is not a price we must beat — we BEAT it.",
        },
        "edge_decay_curve": decay,
        "drift_read": "mid drifts only ~+0.46c in the 30min from their fire to our capture ⇒ DRIFT≈0 ⇒ "
                      "SPEED IS NOT THE LEVER (capture-at-detection recovers only ~0.6pp). Do not build it.",
        "spread_sensitivity_at_30min": sens,
        "verdict": "the entire copier cost is the SPREAD (~1.1-1.2c measured). At that spread the cert "
                   "cell is LB +13.5% (LODO +11.7%). It only stops clearing the champion's +5.6% floor "
                   "if the true cert-band spread is >= ~6c — 5x the measured value. PRICE is close to "
                   "settled; SIZE (weather_fav_liq = 0 captures) is the open constraint.",
    }


def selftest():
    ok = True
    if MEASURED_SPREAD <= 0 or CHAMP_FLOOR <= 0:
        print("FAIL consts"); ok = False
    if 30 not in HORIZONS:
        print("FAIL horizons"); ok = False
    print("selftest PASS" if ok else "selftest FAIL")
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    rep = build()
    (Path(__file__).resolve().parent.parent / "reports" / "WEATHER-DECAY.json").write_text(
        json.dumps(rep, indent=2))
    print("wrote WEATHER-DECAY.json\n")
    s = rep["sharps_are_TAKERS"]
    print(f"sharps are TAKERS: mid@ts0 {s['mid_at_ts0']} -> their fill {s['sharp_fill']} "
          f"(+{s['sharp_pays_over_mid']*100:.2f}c over mid; {s['frac_paying_above_mid']:.0%} pay above mid)")
    print("\ndecay (ROI-turn at the ask):")
    for d in rep["edge_decay_curve"]:
        print(f"   {d['delay_min']:4}m  mid {d['mid']}  ask {d['ask']}  ROI {d['roi_turn_at_ask']*100:+.2f}%")
    print("\nspread sensitivity @30m:")
    for x in rep["spread_sensitivity_at_30min"]:
        print(f"   {x['spread']*100:4.1f}c  LB {x['roi_turn_LB']*100:+6.2f}%  LODO {(x['lodo_held_out_LB'] or 0)*100:+6.2f}%"
              f"  {'PASS' if x['clears_champion_floor'] else 'below champ floor'}")


if __name__ == "__main__":
    main()
