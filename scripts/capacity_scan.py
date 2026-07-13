#!/usr/bin/env python3
"""
CAPACITY-SCAN — how much can we actually tail before we eat our own edge?

WHY THIS HAS NEVER BEEN ANSWERED (a fifth data gap, found 2026-07-12):
We have NEVER recorded order-book DEPTH. `common/src/data/models.rs::BookLevel` deserializes only
`price` — the `size` field is DROPPED at the type level — so `fetch_best_ask` keeps the best ask price
and throws the available size away. `clob_price_tape` stores best_bid/best_ask PRICES with no sizes
(`last_size` is a trade size, not resting depth). So the question "how many dollars can we put on a
signal before we walk up the book" is UNANSWERABLE from our history, and capacity has stood as the one
explicitly UNPROVEN limit ("weather_fav_liq has captured 0 — thin books; size UNPROVEN").

This measures it LIVE instead: for currently-OPEN markets that the sharps have converged on, pull the
real `/book` and walk the ask ladder.

THE ECONOMICS WE ARE TESTING (all per $1 of stake, on the 0.71-0.90 certification band):
  gross selection edge  ~ +12pp     (the sharps' pick, day-clustered)
  spread (we cross)     ~ -1.2c     (measured: ask - mid)
  slippage(S)           ~ -?        (THIS SCRIPT: walking the ladder for stake S)
  => net(S) = gross - spread - slippage(S)
Capacity = the largest S at which net(S) still clears a chosen floor WITH MARGIN. We report the whole
curve, not one number, because the honest answer is a size at which you keep most of the edge, not the
size at which the edge hits zero (that one has no safety margin at all).

HONEST SCOPE — what this does NOT capture:
  * MARKET IMPACT / refill. Walking a snapshot book charges you today's resting liquidity. It does NOT
    model the price moving against you as you buy repeatedly, other copiers racing you, or makers
    pulling quotes when they see size. Real capacity is therefore <= this number, never more.
  * A snapshot is one instant. Depth varies with time-to-resolution.
  So treat the output as an UPPER BOUND on capacity, and size well inside it.

Read-only, no DB writes. Self-test: ./capacity_scan.py --selftest
"""

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cell_lib as C  # noqa: E402

CLOB = "https://clob.polymarket.com"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) polymarket-bot/capacity-scan"
WIDE_CUTOFF = 250
LO, HI = 0.71, 0.90               # the certification band — the only one that matters
GROSS_EDGE = 0.12                 # ~+12pp day-clustered selection edge (sharps' fill)
LADDER = [25, 50, 100, 250, 500, 1000, 2500, 5000, 10000]   # stake $ per signal
REPORTS = Path(__file__).resolve().parent.parent / "reports"


def _get(url, retries=3):
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(0.4 * (a + 1))
        except Exception:
            time.sleep(0.4 * (a + 1))
    return None


def walk_asks(asks, stake_usd):
    """Buy `stake_usd` by walking the ask ladder. Returns (vwap, filled_usd, levels_eaten).

    Each level is (price, size_shares); cost of a level = price * size. We consume levels cheapest-first
    until the stake is spent. If the whole visible book is thinner than the stake, we report what we
    COULD fill — a partial fill is the honest answer, never a pretend fill at the last price.
    """
    # Bound prices to (0,1] exactly as the Rust `best_ask_price` does — a level outside that range is
    # unusable, and silently treating it as real would understate slippage.
    levels = sorted(
        ((float(p), float(s)) for p, s in asks if 0.0 < float(p) <= 1.0 and float(s) > 0),
        key=lambda x: x[0],
    )
    spent = shares = 0.0
    eaten = 0
    for price, size in levels:
        if spent >= stake_usd:
            break
        level_cost = price * size
        take = min(level_cost, stake_usd - spent)
        spent += take
        shares += take / price
        eaten += 1
    if shares <= 0:
        return None, 0.0, 0
    return spent / shares, spent, eaten


def fetch_open_converged(family_rx, since="2026-07-05"):
    """Markets in this family the sharps CONVERGED on (>=3 one-sided backers, band) — we take whatever
    is still open, since only an open book has depth to measure."""
    rows = C.q(f"""
    WITH e AS (
      SELECT f.condition_id, f.outcome_index, LOWER(f.wallet) w, AVG(f.price) px, MAX(f.slug) slug
      FROM trader_fills f JOIN followed_traders ft ON ft.proxy_wallet=f.wallet
      WHERE f.side='BUY' AND f.ts>='{since}' AND ft.rank<={WIDE_CUTOFF} AND f.slug ~ '{family_rx}'
      GROUP BY 1,2,3)
    SELECT condition_id, outcome_index, MAX(slug), AVG(px), count(*)
    FROM e GROUP BY 1,2
    HAVING count(*)>=3 AND AVG(px) BETWEEN {LO} AND {HI};
    """)
    return [{"cond": r[0], "oi": int(r[1]), "slug": r[2], "sharp_px": float(r[3])} for r in rows]


def book_for(p):
    mkt = _get(f"{CLOB}/markets/{p['cond']}")
    if not mkt or mkt.get("closed"):
        return None                      # closed book has no depth to buy into
    toks = mkt.get("tokens") or []
    if p["oi"] >= len(toks):
        return None
    tid = toks[p["oi"]].get("token_id")
    if not tid:
        return None
    bk = _get(f"{CLOB}/book?token_id={tid}")
    if not bk:
        return None
    asks = [(lv.get("price"), lv.get("size")) for lv in (bk.get("asks") or [])
            if lv.get("price") and lv.get("size")]
    if not asks:
        return None
    return asks


def selftest():
    ok = True
    # Ladder: 100 shares @0.80 then 100 @0.85. $80 fits entirely in level 1 -> vwap 0.80, 1 level.
    asks = [("0.80", "100"), ("0.85", "100")]
    v, sp, n = walk_asks(asks, 80)
    if not (abs(v - 0.80) < 1e-9 and n == 1):
        print(f"FAIL walk level-1: {v} {n}"); ok = False
    # $165 = all of L1 ($80) + $85 of L2 -> vwap between .80 and .85, 2 levels
    v, sp, n = walk_asks(asks, 165)
    if not (0.80 < v < 0.85 and n == 2 and abs(sp - 165) < 1e-6):
        print(f"FAIL walk level-2: {v} {sp} {n}"); ok = False
    # Book thinner than the stake -> PARTIAL fill, never a pretend fill
    v, sp, n = walk_asks(asks, 10_000)
    if abs(sp - (0.80 * 100 + 0.85 * 100)) > 1e-6:
        print(f"FAIL partial fill must cap at book size: {sp}"); ok = False
    # Cheapest-first regardless of input order
    v2, _, _ = walk_asks([("0.85", "100"), ("0.80", "100")], 80)
    if abs(v2 - 0.80) > 1e-9:
        print("FAIL walk must sort cheapest-first"); ok = False
    # Degenerate / empty
    if walk_asks([], 100)[0] is not None:
        print("FAIL empty book"); ok = False
    if walk_asks([("0", "5"), ("1.5", "5")], 10)[0] is not None:
        print("FAIL must reject out-of-range prices"); ok = False
    print("capacity_scan selftest: PASS" if ok else "capacity_scan selftest: FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--families", default="highest-temperature,fifwc,mlb,atp,wta")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        raise SystemExit(selftest())

    rep = {"as_of": "2026-07-12", "band": [LO, HI], "gross_edge_assumed": GROSS_EDGE,
           "caveat": "UPPER BOUND — snapshot depth only; no market impact, refill, or copier race.",
           "families": {}}

    for fam in a.families.split(","):
        picks = fetch_open_converged(fam)
        if not picks:
            print(f"{fam:22} no OPEN converged markets right now — depth unmeasurable")
            rep["families"][fam] = {"open_markets": 0, "verdict": "no open book to measure"}
            continue
        with ThreadPoolExecutor(8) as ex:
            books = list(ex.map(book_for, picks))
        got = [(p, b) for p, b in zip(picks, books) if b]
        if not got:
            print(f"{fam:22} {len(picks)} converged but 0 open books")
            rep["families"][fam] = {"open_markets": 0, "verdict": "no open book to measure"}
            continue

        print(f"\n=== {fam}   ({len(got)} open converged books sampled)")
        print(f"{'stake $':>8} {'slippage¢':>10} {'fillable%':>10} {'net edge':>9}  verdict")
        curve = {}
        for stake in LADDER:
            slips, fills = [], []
            for p, asks in got:
                best = min(float(x[0]) for x in asks)
                vwap, spent, _ = walk_asks(asks, stake)
                if vwap is None:
                    continue
                slips.append(vwap - best)          # slippage = what walking the ladder costs
                fills.append(spent / stake)        # 1.0 = fully fillable at this size
            if not slips:
                continue
            slip = statistics.median(slips)
            fillable = statistics.median(fills)
            # Net edge per $1: gross - spread(1.2c) - slippage. Charge UNFILLED stake as no-edge, not
            # as a loss — you simply don't get that exposure.
            net = (GROSS_EDGE - 0.012 - slip)
            verdict = ("comfortable" if net > 0.08 and fillable > 0.99 else
                       "thinning" if net > 0.05 and fillable > 0.95 else
                       "MARGINAL" if net > 0.02 else "EDGE GONE")
            curve[stake] = {"slippage": round(slip, 4), "fillable": round(fillable, 3),
                            "net_edge": round(net, 4), "verdict": verdict}
            print(f"{stake:>8} {slip*100:>10.2f} {fillable*100:>9.0f}% {net*100:>8.1f}%  {verdict}")
        rep["families"][fam] = {"open_markets": len(got), "curve": curve}

    (REPORTS / "CAPACITY-SCAN.json").write_text(json.dumps(rep, indent=2))
    print("\nwrote CAPACITY-SCAN.json")


if __name__ == "__main__":
    main()
