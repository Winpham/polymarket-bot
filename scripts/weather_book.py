#!/usr/bin/env python3
"""
WEATHER-BOOK (Weather Capitalize run, adversarial phase, 2026-07-12).

THE two questions everything now rests on, answered from the ONE source that can answer them — the
LIVE CLOB order book (`/book`). History cannot: `prices-history` is a validated MID basis
(basis_validate.py) but carries NO book, so neither the SPREAD nor the SIZE is reconstructable.

  B2 — SPREAD on the certification band. Every realizable number this run produced used a ~1.2c spread
       taken from 38 captured asks whose average price was 0.912 — DEEP CHALK, where books are tight.
       The cert band is 0.71-0.90. Mid-favorite weather is exactly where books should be THIN and WIDE.
       If the true cert-band spread is >= ~6c the edge stops clearing the champion's +5.6% floor.
  B4 — SIZE. `weather_fav_liq` (>=$1k liquidity) has captured ZERO. A fat % on unfillable size is not a
       strategy. Measure the actual dollar depth at/near the touch.

Scans OPEN weather markets, keeps those whose mid lands in the cert band, and reports the spread and
the fillable dollar depth (at the touch, and within a 1c / 2c slippage budget). Read-only; no orders.

Self-test: ./weather_book.py --selftest
"""
import json, sys, time, urllib.request, statistics as st
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cell_lib as C

CLOB = "https://clob.polymarket.com"
LO, HI = 0.71, 0.90


def _get(u):
    r = urllib.request.Request(u, headers={"User-Agent": "weather-book-readonly/1"})
    with urllib.request.urlopen(r, timeout=25) as resp:
        return json.loads(resp.read())


def depth_usd(asks, best, budget):
    """$ notional available at prices <= best+budget."""
    return sum(float(a["price"]) * float(a["size"]) for a in asks
               if float(a["price"]) <= best + budget + 1e-9)


def scan(limit_conds=1400):
    conds = [r[0] for r in C.q(f"""
        SELECT DISTINCT condition_id FROM trader_fills
        WHERE slug ~ 'highest-temperature' AND ts > now() - interval '3 days'
        LIMIT {limit_conds};""")]
    out = []
    for cid in conds:
        try:
            m = _get(f"{CLOB}/markets/{cid}")
        except Exception:
            continue
        if m.get("closed"):
            continue
        for t in m.get("tokens", []):
            tid = t.get("token_id")
            if not tid:
                continue
            time.sleep(0.05)
            try:
                b = _get(f"{CLOB}/book?token_id={tid}")
            except Exception:
                continue
            asks, bids = b.get("asks") or [], b.get("bids") or []
            if not asks or not bids:
                continue
            ba = min(float(a["price"]) for a in asks)
            bb = max(float(x["price"]) for x in bids)
            mid = (ba + bb) / 2.0
            if not (LO <= mid <= HI):
                continue
            out.append({
                "slug": m.get("market_slug", ""), "mid": round(mid, 4),
                "best_bid": round(bb, 4), "best_ask": round(ba, 4),
                "spread": round(ba - bb, 4),
                "half_spread_ask_minus_mid": round(ba - mid, 4),
                "depth_at_touch_usd": round(depth_usd(asks, ba, 0.0), 2),
                "depth_within_1c_usd": round(depth_usd(asks, ba, 0.01), 2),
                "depth_within_2c_usd": round(depth_usd(asks, ba, 0.02), 2),
            })
    return out


def build():
    rows = scan()
    if not rows:
        return {"n": 0, "verdict": "NO OPEN CERT-BAND WEATHER BOOKS FOUND"}
    sp = [r["spread"] for r in rows]
    hs = [r["half_spread_ask_minus_mid"] for r in rows]
    d1 = [r["depth_within_1c_usd"] for r in rows]
    return {
        "as_of": "2026-07-12", "run": "weather capitalize — LIVE BOOK (B2 spread + B4 size)",
        "cert_band": [LO, HI], "n_open_cert_band_books": len(rows),
        "SPREAD": {
            "median": round(st.median(sp), 4), "mean": round(st.mean(sp), 4),
            "p25": round(sorted(sp)[len(sp)//4], 4), "p75": round(sorted(sp)[3*len(sp)//4], 4),
            "min": round(min(sp), 4), "max": round(max(sp), 4),
        },
        "HALF_SPREAD_ask_minus_mid": {
            "median": round(st.median(hs), 4), "mean": round(st.mean(hs), 4),
            "note": "THIS is what a taker pays over mid — the number the realizable LB is a function of.",
        },
        "DEPTH_usd": {
            "median_at_touch": round(st.median([r["depth_at_touch_usd"] for r in rows]), 2),
            "median_within_1c": round(st.median(d1), 2),
            "median_within_2c": round(st.median([r["depth_within_2c_usd"] for r in rows]), 2),
            "frac_books_under_100usd_within_1c": round(sum(1 for x in d1 if x < 100) / len(d1), 3),
        },
        "prior_estimate_used_by_this_run": 0.0122,
        "books": sorted(rows, key=lambda r: -r["spread"])[:40],
    }


def selftest():
    asks = [{"price": "0.84", "size": "100"}, {"price": "0.85", "size": "50"}]
    if abs(depth_usd(asks, 0.84, 0.0) - 84.0) > 1e-6:
        print("FAIL depth touch"); return 1
    if abs(depth_usd(asks, 0.84, 0.01) - (84.0 + 42.5)) > 1e-6:
        print("FAIL depth 1c"); return 1
    print("selftest PASS")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    rep = build()
    (Path(__file__).resolve().parent.parent / "reports" / "WEATHER-BOOK.json").write_text(
        json.dumps(rep, indent=2))
    print(json.dumps({k: v for k, v in rep.items() if k != "books"}, indent=2))
