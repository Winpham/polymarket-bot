#!/usr/bin/env python3
"""
WEATHER-LATENCY (Weather Deepen run, WS1, 2026-07-12).

Answer ONE question with data: "is the ~10-15 min housekeeping capture cadence good enough, or is
the realizable weather edge decaying inside the capture window?" The live `weather_fav` arm now
captures the executable `entry_ask` (paired with the same-pass mid `entry_ask_mid`) — the copyable
price weather has NEVER had. This instrument meters:

  1. capture lag  = entry_ask_at - first_detected_at  (detection -> first executable observation).
  2. spread tax   = entry_ask - entry_ask_mid  (contemporaneous /book ask over /markets mid, same
                    housekeeping pass ~sub-second apart — the genuine thin-book bid-ask half-spread,
                    NOT drift).
  3. adverse drift = entry_ask_mid - sharp_px  (how far the mid moved ABOVE the sharps' fill by the
                    time we first observe it — the cost of arriving `lag` minutes late).
  4. executable haircut = entry_ask - sharp_px  (spread + drift: what a follower ACTUALLY pays over
                    the sharps' own fill at OUR realizable ask). The forward-unknown the arm exists
                    to resolve.
  5. does lag CAUSE cost? corr(lag, spread) and corr(lag, drift). If ~0, capturing earlier does NOT
                    materially improve the realizable ask — the cadence is NOT the binding constraint
                    and capture-at-detection is not worth building. If strongly positive, it is.

Realized within-window edge decay (won - entry as a function of lag) needs RESOLVED captured signals;
weather_fav captures are days-fresh (july 12-14 markets), so that read is emitted as PENDING with the
re-run hook. Everything here is READ-ONLY (SELECT on consensus_signals / trader_fills; no writes, no
orders, no pipeline change). Emits reports/WEATHER-LATENCY.json. Self-test: ./weather_latency.py --selftest
"""

import json
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cell_lib as C                                    # noqa: E402

WIDE_CUTOFF = 250


def fetch_captures():
    """Live weather_fav signals that captured an executable entry_ask, joined to the sharps' own
    mean fill on the same (condition, outcome). One row per captured signal."""
    rows = C.q(f"""
    WITH cap AS (
      SELECT s.condition_id, s.outcome_index, s.slug, s.entry_ask, s.entry_ask_mid,
             s.initial_market_price,
             EXTRACT(EPOCH FROM (s.entry_ask_at - s.first_detected_at))/60.0 lag_min,
             (s.entry_ask_mid = s.initial_market_price) AS decision_pass
      FROM consensus_signals s
      WHERE s.strategy='weather_fav' AND s.entry_ask IS NOT NULL AND s.entry_ask_mid IS NOT NULL),
    sharp AS (
      SELECT f.condition_id, f.outcome_index, AVG(f.price) sharp_px, count(*) nfills
      FROM trader_fills f JOIN followed_traders ft ON ft.proxy_wallet=f.wallet
      WHERE f.side='BUY' AND ft.rank<={WIDE_CUTOFF} AND f.slug ~ 'highest-temperature'
      GROUP BY 1,2)
    SELECT c.condition_id, c.outcome_index, c.slug, c.entry_ask, c.entry_ask_mid,
           c.lag_min, c.decision_pass, s.sharp_px, s.nfills
    FROM cap c LEFT JOIN sharp s USING (condition_id, outcome_index);
    """)
    out = []
    for r in rows:
        cond, oi, slug, ask, mid, lag, dpass, sharp, nfills = (r + [""] * 9)[:9]
        out.append({
            "condition_id": cond, "outcome_index": int(oi), "slug": slug,
            "entry_ask": float(ask), "entry_ask_mid": float(mid), "lag_min": float(lag),
            "decision_pass": dpass == "t",
            "sharp_px": float(sharp) if sharp not in ("", None) else None,
            "band": C.band_of(float(mid)) or "other",
        })
    return out


def _corr(xs, ys):
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 3:
        return None
    xs2, ys2 = zip(*pairs)
    n = len(pairs)
    mx, my = sum(xs2) / n, sum(ys2) / n
    sxx = sum((x - mx) ** 2 for x in xs2)
    syy = sum((y - my) ** 2 for y in ys2)
    if sxx == 0 or syy == 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in pairs)
    return round(sxy / (sxx ** 0.5 * syy ** 0.5), 3)


def _agg(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    return {
        "n": len(vals), "mean": round(st.mean(vals), 4),
        "median": round(st.median(vals), 4),
        "min": round(min(vals), 4), "max": round(max(vals), 4),
        "p90": round(sorted(vals)[min(len(vals) - 1, int(0.9 * len(vals)))], 4),
    }


def build():
    caps = fetch_captures()
    liq = C.q("SELECT count(*) FROM consensus_signals WHERE strategy='weather_fav_liq' "
              "AND entry_ask IS NOT NULL;")
    liq_captures = int(liq[0][0]) if liq else 0

    spread = [c["entry_ask"] - c["entry_ask_mid"] for c in caps]
    lag = [c["lag_min"] for c in caps]
    drift = [c["entry_ask_mid"] - c["sharp_px"] for c in caps if c["sharp_px"] is not None]
    haircut = [c["entry_ask"] - c["sharp_px"] for c in caps if c["sharp_px"] is not None]
    with_sharp = [c for c in caps if c["sharp_px"] is not None]

    # per-band spread (thin-book tax is band-dependent — deep chalk near 1.0 has a tighter book)
    by_band = {}
    for b in sorted({c["band"] for c in caps}):
        sub = [c for c in caps if c["band"] == b]
        by_band[b] = {
            "n": len(sub),
            "spread": _agg([c["entry_ask"] - c["entry_ask_mid"] for c in sub]),
            "haircut_vs_sharp": _agg([c["entry_ask"] - c["sharp_px"] for c in sub
                                      if c["sharp_px"] is not None]),
        }

    corr_lag_spread = _corr(lag, spread)
    corr_lag_drift = _corr([c["lag_min"] for c in with_sharp], drift)

    # verdict on capture-at-detection: only worth building if lag CAUSES realizable cost.
    lag_causes_cost = (
        (corr_lag_spread is not None and corr_lag_spread > 0.3) or
        (corr_lag_drift is not None and corr_lag_drift > 0.3)
    )
    verdict = ("CAPTURE-AT-DETECTION WARRANTED — lag correlates with realizable cost"
               if lag_causes_cost else
               "CAPTURE-AT-DETECTION NOT WARRANTED — lag is uncorrelated with spread/drift; the "
               "binding realizable constraint is the bid-ask SPREAD + thin-book SIZE, not cadence")

    return {
        "as_of": "2026-07-12", "run": "weather deepen — WS1 (capture cadence & latency)",
        "question": "is the ~10-15 min housekeeping cadence good enough, or does the realizable "
                    "weather edge decay inside the capture window?",
        "n_captures": len(caps),
        "n_with_sharp_join": len(with_sharp),
        "weather_fav_liq_captures": liq_captures,
        "capture_lag_min": _agg(lag),
        "spread_ask_minus_mid": _agg(spread),
        "adverse_drift_mid_minus_sharp": _agg(drift),
        "executable_haircut_ask_minus_sharp": _agg(haircut),
        "corr_lag_vs_spread": corr_lag_spread,
        "corr_lag_vs_drift": corr_lag_drift,
        "by_band": by_band,
        "capture_pass_mix": {
            "decision_pass": sum(1 for c in caps if c["decision_pass"]),
            "lagged_pass": sum(1 for c in caps if not c["decision_pass"]),
        },
        "realized_within_window_decay": {
            "status": "PENDING — needs RESOLVED captured signals (weather_fav captures are days-fresh, "
                      "july 12-14 markets unresolved). Re-run this instrument as they resolve to read "
                      "(won - entry_ask) vs lag.",
        },
        "verdict": verdict,
        "notes": [
            "entry_ask & entry_ask_mid are captured on the SAME housekeeping pass (/book ask + "
            "/markets mid, ~sub-second apart) so spread is the true contemporaneous half-spread, "
            "NOT drift.",
            "weather_fav_liq (the $1k-liquidity twin) captured %d — thin weather books are the "
            "binding SIZE constraint; a fat %% on unfillable size is not a strategy." % liq_captures,
            "captures skew high-price (fresh july 12-14 markets, many deep chalk) — the haircut here "
            "is a FIRST read, not the 0.71-0.90 cert-cell number; re-run as the cert-cell band "
            "captures accrue.",
        ],
    }


def selftest():
    ok = True
    a = _agg([1.0, 2.0, 3.0])
    if a["median"] != 2.0 or a["n"] != 3:
        print("FAIL agg"); ok = False
    if _corr([1, 2, 3], [2, 4, 6]) != 1.0:
        print("FAIL corr"); ok = False
    if _agg([]) is not None:
        print("FAIL empty"); ok = False
    print("selftest PASS" if ok else "selftest FAIL")
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    rep = build()
    out = Path(__file__).resolve().parent.parent / "reports" / "WEATHER-LATENCY.json"
    out.write_text(json.dumps(rep, indent=2))
    print("wrote WEATHER-LATENCY.json\n")
    print(json.dumps({k: rep[k] for k in (
        "n_captures", "capture_lag_min", "spread_ask_minus_mid",
        "adverse_drift_mid_minus_sharp", "executable_haircut_ask_minus_sharp",
        "corr_lag_vs_spread", "corr_lag_vs_drift", "weather_fav_liq_captures", "verdict")}, indent=2))


if __name__ == "__main__":
    main()
