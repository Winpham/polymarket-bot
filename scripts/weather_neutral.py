#!/usr/bin/env python3
"""
WEATHER-NEUTRAL (real-money prep, 2026-07-13). THE decisive test before any money.

Everything this project has measured on weather is anchored to a SHARP's first-buy time (`ts0`). That
is entry-timing-biased by construction (guard B5): if sharps buy transient dips, every price we derive
flatters us. And every number rests on 13 consecutive JULY days — one season, one regime.

This instrument removes BOTH at once by pricing the favorite at a NEUTRAL REFERENCE TIME — a fixed lead
before the market's own resolution — with NO sharp, no consensus, no trader involvement of any kind:

    for every weather market: favorite = the outcome trading >0.5 at (end - LEAD hours)
    keep those priced in the cert band; grade by the CLOB winner; ask ONE question:
        does a 0.71-0.90 weather favorite win MORE than its price implies?

That question is the whole thesis, stripped of the copy apparatus:
  - If YES, the edge is FAVOURITE-LONGSHOT BIAS in weather — real, tradeable WITHOUT sharps, higher
    capacity (every market, not just the ones a sharp touched), and the entire consensus machinery is
    dead weight (consistent with: null p~0.5, specialists +2.1pp, B3 +0.14pp).
  - If NO, the July edge was an artifact of sharp-anchored entry timing and MUST NOT be traded.

It also splits by MONTH, so the out-of-season question ("13 days, all summer") finally gets an answer:
summer highs are easy to forecast; winter/shoulder seasons are not. If the edge is summer-only, sizing
it year-round would be a slow bleed.

Read-only. No orders. Self-test: ./weather_neutral.py --selftest
"""
import json, sys, statistics as st
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cell_lib as C
from weather_clob import WeatherClob

LEAD_HOURS = 12           # neutral reference: 12h before the market's own end. No sharp anchoring.
LO, HI = 0.71, 0.90


def all_weather_conds():
    return C.q("""
    SELECT DISTINCT condition_id, MAX(slug) slug FROM trader_fills
    WHERE slug ~ 'highest-temperature' GROUP BY condition_id;""")


def build(offline=False, lead_hours=LEAD_HOURS):
    import datetime as dt
    wc = WeatherClob(offline=offline)
    rows = all_weather_conds()
    picks, no_end, no_hist, open_n = [], 0, 0, 0
    for cond, slug in [(r[0], r[1]) for r in rows]:
        info = wc.outcome(cond)
        if info.get("winner") is None:
            open_n += 1
            continue
        end = info.get("end_iso")
        if not end:
            no_end += 1
            continue
        try:
            t_end = dt.datetime.fromisoformat(end.replace("Z", "+00:00")).timestamp()
        except Exception:
            no_end += 1
            continue
        t_ref = int(t_end - lead_hours * 3600)
        # price EVERY outcome at the neutral reference; the favorite is whichever trades >0.5.
        best = None
        for oi, tid in info["tokens"].items():
            p = wc.mid_at(tid, t_ref)
            if p is None:
                continue
            if p > 0.5 and (best is None or p > best[1]):
                best = (int(oi), p)
        if best is None:
            no_hist += 1
            continue
        oi, px = best
        if not (LO <= px <= HI):
            continue
        mon = (slug or "")
        import re
        m = re.search(r"on-([a-z]+)-(\d+)", mon)
        month = m.group(1) if m else "?"
        day = f"{month}-{m.group(2)}" if m else "?"
        picks.append({"condition_id": cond, "slug": slug, "entry": px,
                      "won": info["winner"] == oi, "cluster": day, "month": month})
    wc.flush()

    def cell(ps, label):
        if len(ps) < 5:
            return {"label": label, "n": len(ps), "verdict": "INSUFFICIENT"}
        wr = st.mean([1.0 if p["won"] else 0.0 for p in ps])
        px = st.mean([p["entry"] for p in ps])
        r = C.roi_lb([{"entry": p["entry"], "won": p["won"], "cluster": p["cluster"],
                       "condition_id": p["condition_id"], "slug": p["slug"]} for p in ps])
        return {"label": label, "n": len(ps), "day_clusters": len({p["cluster"] for p in ps}),
                "mean_price": round(px, 4), "win_rate": round(wr, 4),
                "edge_pp": round((wr - px) * 100, 2),
                "roi_turn_point": None if not r else round(r["point"], 4),
                "roi_turn_LB": None if not r or r.get("lb") is None else round(r["lb"], 4)}

    by_month = defaultdict(list)
    for p in picks:
        by_month[p["month"]].append(p)
    july = [p for p in picks if p["month"] == "july"]
    pre = [p for p in picks if p["month"] != "july"]
    return {
        "as_of": "2026-07-13", "run": "weather NEUTRAL-reference blind pool (no sharps, no ts0)",
        "lead_hours": lead_hours, "cert_band": [LO, HI],
        "coverage": {"conds": len(rows), "still_open": open_n, "no_end_date": no_end,
                     "no_history": no_hist, "cert_band_picks": len(picks)},
        "THE_QUESTION": "does a 0.71-0.90 weather favorite, priced at a NEUTRAL time with NO sharp "
                        "involved, win more than its price implies?",
        "ALL": cell(picks, "ALL months"),
        "JULY_in_sample": cell(july, "july (the in-sample regime)"),
        "PRE_JULY_out_of_season": cell(pre, "feb-june (OUT OF SEASON — the transfer test)"),
        "by_month": {m: cell(ps, m) for m, ps in sorted(by_month.items())},
        "read": "if the neutral-reference edge is ~0, the July numbers were sharp-anchored entry-timing "
                "artifacts and MUST NOT be traded. If it is strongly positive, the edge is FAVOURITE-"
                "LONGSHOT BIAS: tradeable WITHOUT sharps, at higher capacity, and the consensus "
                "machinery is dead weight.",
    }


def selftest():
    ok = LEAD_HOURS > 0 and LO < HI
    print("selftest PASS" if ok else "selftest FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    rep = build()
    (Path(__file__).resolve().parent.parent / "reports" / "WEATHER-NEUTRAL.json").write_text(
        json.dumps(rep, indent=2))
    print("coverage:", json.dumps(rep["coverage"]))
    for k in ("ALL", "JULY_in_sample", "PRE_JULY_out_of_season"):
        c = rep[k]
        if c.get("verdict"):
            print(f"\n{c['label']}: {c['verdict']} (n={c['n']})"); continue
        print(f"\n{c['label']}: n={c['n']} days={c['day_clusters']}")
        print(f"   mean price {c['mean_price']}  win rate {c['win_rate']}  EDGE {c['edge_pp']:+.2f}pp")
        print(f"   ROI-turn point {c['roi_turn_point']}  LB {c['roi_turn_LB']}")
