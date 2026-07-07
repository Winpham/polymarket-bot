#!/usr/bin/env python3
"""
DISCOVER — behavioral expansion beyond the leaderboard (escapes the winner's-curse survivor pool).

Our tracked universe is 100% leaderboard = wallets selected BY PAST PnL (the exact source of the
curse). This finds new candidates the opposite way: wallets that CO-TRADE OUR MARKETS, surfaced
from the full public tape (data-api /trades, which exposes proxyWallet). We rank candidates by
BEHAVIORAL OVERLAP with our markets — NOT by their PnL — MM-lock them by churn, and count the
CLV-event supply they would add (the accrual accelerant for certification).

Bounded + throttled (respect the data-api limit; back off on error). Read-only, silent: writes a
candidate report only. Does NOT touch followed_traders or the live poll — turning candidates into
tracked wallets is a separate, deliberate deploy step for Tue.

  ./discover.py --markets 100 --pages 3      # scan 100 recent resolved markets, 3 tape pages each
  ./discover.py --selftest
"""
import argparse, json, os, sys, time, urllib.request
from collections import defaultdict
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import mm_common as mc      # noqa: E402

REPORT = os.path.join(os.path.dirname(os.path.dirname(HERE)), "reports", "specialize", "discover.json")
TRADES_URL = "https://data-api.polymarket.com/trades?market={cid}&limit=500&offset={off}"
SLEEP = 0.25


def _get(url, tries=5):
    """GET with backoff on 429/403/5xx/transient (data-api burst-throttles)."""
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.load(r)
        except Exception as e:
            last = e
            time.sleep(0.6 * (k + 1))
    raise last


def recent_markets(n):
    """Most recent resolved condition_ids our fleet traded (with fleet coverage stats)."""
    rows = mc.q(f"""
      SELECT condition_id, max(ts) mx, count(*) our_fills
      FROM trader_fills WHERE resolved AND is_sports AND condition_id IS NOT NULL
      GROUP BY 1 ORDER BY mx DESC LIMIT {int(n)}
    """)
    return [(r[0]) for r in rows if r and r[0]]


def tracked_wallets():
    return {r[0] for r in mc.q("SELECT DISTINCT lower(proxy_wallet) FROM followed_traders")}


def run(n_markets, pages):
    cids = recent_markets(n_markets)
    tracked = tracked_wallets()
    # per discovered wallet: markets overlapped, buy/sell shares (for churn MM-lock), n_fills
    wmk = defaultdict(set); buy_sh = defaultdict(float); sell_sh = defaultdict(float)
    nf = defaultdict(int)
    errors = 0; scanned = 0
    for cid in cids:
        try:
            off = 0
            for _ in range(pages):
                batch = _get(TRADES_URL.format(cid=cid, off=off))
                if not batch:
                    break
                for t in batch:
                    w = str(t.get("proxyWallet", "")).lower()
                    if not w:
                        continue
                    sh = float(t["size"])          # data-api size is SHARES
                    if t["side"] == "BUY":
                        buy_sh[w] += sh
                    else:
                        sell_sh[w] += sh
                    wmk[w].add(cid); nf[w] += 1
                off += 500
                time.sleep(SLEEP)
            scanned += 1
        except Exception:
            errors += 1
    # candidate = NOT tracked, non-MM by lifetime churn (2*min/(sum) on shares), overlaps >=2 markets
    def churn(w):
        b, s = buy_sh[w], sell_sh[w]
        return (2 * min(b, s) / (b + s)) if (b + s) > 0 else 0.0
    cand = []
    for w in wmk:
        if w in tracked:
            continue
        ch = churn(w)
        cand.append({"wallet": w, "overlap_markets": len(wmk[w]), "fills_seen": nf[w],
                     "churn": round(ch, 3), "is_mm": ch >= 0.70})
    cand.sort(key=lambda c: c["overlap_markets"], reverse=True)
    non_mm = [c for c in cand if not c["is_mm"]]
    multi = [c for c in non_mm if c["overlap_markets"] >= 2]
    return {
        "markets_scanned": scanned, "markets_requested": n_markets, "pages_per_market": pages,
        "fetch_errors": errors, "tracked_wallets": len(tracked),
        "distinct_wallets_seen": len(wmk),
        "new_candidates_total": len(cand),
        "new_candidates_non_mm": len(non_mm),
        "new_candidates_non_mm_multi_market": len(multi),
        "mm_locked_out": len(cand) - len(non_mm),
        "note": ("behavioral (co-trade) discovery — NOT past-PnL ranked; silent candidate pool, "
                 "no live-poll change. Overlap>=2 = co-trades multiple of our markets."),
        "top_candidates": multi[:30],
    }


def selftest():
    # churn math
    b, s = 100.0, 100.0
    assert abs(2*min(b, s)/(b+s) - 1.0) < 1e-9
    b, s = 100.0, 0.0
    assert 2*min(b, s)/(b+s) == 0.0
    print("selftest OK")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--markets", type=int, default=100)
    ap.add_argument("--pages", type=int, default=3)
    a = ap.parse_args()
    if a.selftest:
        selftest(); sys.exit(0)
    res = run(a.markets, a.pages)
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w") as f:
        json.dump(res, f, indent=2, default=str)
    print(json.dumps(res, indent=2, default=str))
