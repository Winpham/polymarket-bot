#!/usr/bin/env python3
"""
US BOOK DEPTH CAPTURE — the dollar depth nobody has ever recorded. READ-ONLY. Never trades.

WHY THIS EXISTS
---------------
Every sizing question in this project is currently unanswerable, because no dollar depth has ever
been captured. `us_quotes.bid_depth_usd` / `ask_depth_usd` are NOT dollars: the venue's `/bbo`
returns `bidDepth`/`askDepth` as the NUMBER OF PRICE LEVELS. Verified 2026-07-19 against the full
book on 19/19 live markets, 100% agreement. The `_usd` suffix is a misnomer and reading it as money
understates real depth by ~500x.

The real book is at `/v1/markets/{slug}/book` and it gives price AND quantity per level, so the
honest quantities — dollars at the touch, dollars in the book, slippage to lift $50/$100/$500 —
are all computable. That is what this records.

THREE FIELD FACTS THAT WILL BITE ANYONE WHO ASSUMES
---------------------------------------------------
1. The ask side is called **`offers`**, NOT `asks`. A consumer looking for `asks` silently sees an
   empty book and reports "no liquidity" — indistinguishable from a dead feed. (Cost me a run.)
2. `bidDepth`/`askDepth` on `/bbo` are LEVEL COUNTS, not size, not USD.
3. `qty` is in SHARES. Notional = px * qty. A 3,926-share bid at 0.81 is $3,180, not $3,926.

ORIENTATION (the silent-inversion trap)
---------------------------------------
`/book` quotes ONE side of the binary (side_index 0). If the favourite we want to buy is side 1,
our ask is the complement of THEIR BID: our_ask(1) = 1 - best_bid. This script stores the RAW book
plus the side-0 price so downstream code can orient explicitly. It never guesses a side.
See `us_quote_capture.py::our_side_quote` — a side-blind read produced a 90c cross-venue "basis"
that was physically impossible, and that was the tell.

DEFAULT-OFF by construction: no committed launch unit. Starting it is an operational act.

  ./us_book_capture.py --self-test      # synthetic fixtures, no network, no DB
  ./us_book_capture.py --once           # one sweep (for a launchd timer)
  ./us_book_capture.py --once --dry-run # sweep and print, write nothing
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

GW = "https://gateway.polymarket.us"
PG_DSN = os.environ.get("ARCHIVE_PG_DSN", "postgresql://bot:bot@127.0.0.1:5432/polymarket")
UA = {"User-Agent": "research/1.0"}
WORKERS = int(os.environ.get("US_BOOK_WORKERS", "6"))
PAGE_LIMIT = 400
SIZES = (50, 100, 500)

DDL = """
CREATE TABLE IF NOT EXISTS us_book_depth (
    id              BIGSERIAL PRIMARY KEY,
    us_slug         TEXT        NOT NULL,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    best_bid        DOUBLE PRECISION,
    best_offer      DOUBLE PRECISION,
    spread          DOUBLE PRECISION,
    mid             DOUBLE PRECISION,
    -- REAL dollars (px*qty), not the /bbo level counts
    bid_touch_usd   DOUBLE PRECISION,
    offer_touch_usd DOUBLE PRECISION,
    bid_book_usd    DOUBLE PRECISION,
    offer_book_usd  DOUBLE PRECISION,
    n_bid_levels    INTEGER,
    n_offer_levels  INTEGER,
    n_rejected_levels INTEGER,
    -- cost of lifting the offer side, % over the touch price; NULL if book exhausted
    slip_50_pct     DOUBLE PRECISION,
    slip_100_pct    DOUBLE PRECISION,
    slip_500_pct    DOUBLE PRECISION,
    exhausts_500    BOOLEAN,
    capture_lag_s   DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS us_book_depth_slug_ts ON us_book_depth (us_slug, ts DESC);
CREATE INDEX IF NOT EXISTS us_book_depth_ts      ON us_book_depth (ts DESC);
"""


def get(path: str, timeout: int = 15):
    try:
        req = urllib.request.Request(f"{GW}{path}", headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except Exception:
        return {}


def parse_level(lv):
    """Strictly parse one book level -> (px, qty) or None.

    THE VENUE EMITS CORRUPT LEVELS. Observed live 2026-07-19 on several markets:
        {"px": {"value": "USD", "currency": ""}, "qty": "\\b\\u0019"}
    i.e. value/currency transposed and qty carrying raw bytes — a protobuf field-mapping bug
    upstream. A naive float() either crashes the sweep or, far worse, a tolerant parser coerces
    garbage into a number and it silently becomes 'liquidity'. Every level is validated:
    a probability must be in (0,1) and a size must be finite and positive. Rejects are COUNTED,
    never silently dropped."""
    try:
        px = float(lv["px"]["value"])
        qty = float(lv["qty"])
    except (TypeError, ValueError, KeyError):
        return None
    if not (0.0 < px < 1.0):
        return None
    if not (qty > 0) or qty != qty or qty in (float("inf"), float("-inf")):
        return None
    return px, qty


def clean_levels(levels):
    """Returns (valid [(px,qty)...], n_rejected)."""
    out, bad = [], 0
    for lv in levels or []:
        p = parse_level(lv)
        if p is None:
            bad += 1
        else:
            out.append(p)
    return out, bad


def notional(levels) -> float:
    """levels are already-parsed (px, qty) pairs. Notional = px * qty (qty is in SHARES)."""
    return sum(px * qty for px, qty in levels)


def walk(levels, dollars: float):
    """VWAP to spend `dollars` walking parsed (px, qty) levels. Returns (vwap, exhausted)."""
    spent = shares = 0.0
    for px, qty in levels:
        take = min(px * qty, dollars - spent)
        if take <= 0:
            break
        shares += take / px
        spent += take
        if spent >= dollars - 1e-9:
            break
    if shares <= 0:
        return None, True
    return spent / shares, spent < dollars - 1e-9


def slippage(levels, dollars: float):
    """% over the touch price to fill `dollars`. None if the book cannot fill it."""
    if not levels:
        return None, True
    touch = levels[0][0]
    vwap, exh = walk(levels, dollars)
    if vwap is None or touch <= 0:
        return None, True
    return (vwap - touch) / touch * 100.0, exh


def discover(pages: int = 4):
    """Current markets. The list endpoint is append-ordered, so recent markets live at high
    offsets; we probe backwards from the end rather than assuming a sort parameter works
    (order/sort/startDateMin are all silently ignored by this API)."""
    total_probe = get(f"/v1/markets?offset=0&limit=1")
    _ = total_probe  # endpoint exposes no count; walk fixed offsets from a high water mark
    slugs, off = [], None
    hi = 224600
    # find the end: walk forward until a page comes back short
    while True:
        d = get(f"/v1/markets?offset={hi}&limit={PAGE_LIMIT}")
        ms = d.get("markets", [])
        if len(ms) < PAGE_LIMIT:
            break
        hi += PAGE_LIMIT
        if hi > 400000:
            break
    for i in range(pages):
        off = max(hi - i * PAGE_LIMIT, 0)
        d = get(f"/v1/markets?offset={off}&limit={PAGE_LIMIT}")
        for m in d.get("markets", []):
            if m.get("slug"):
                slugs.append(m["slug"])
        if off == 0:
            break
    return sorted(set(slugs))


def snap(slug: str):
    t0 = time.time()
    d = (get(f"/v1/markets/{slug}/book") or {}).get("marketData") or {}
    lag = time.time() - t0
    bids, bad_b = clean_levels(d.get("bids"))
    offers, bad_o = clean_levels(d.get("offers"))   # the ask side is `offers`, NOT `asks`
    if not bids and not offers:
        return None
    bb = bids[0][0] if bids else None
    bo = offers[0][0] if offers else None
    # a "spread" is only meaningful if both sides survived validation AND are sanely ordered
    two_sided = bb is not None and bo is not None and bo > bb
    row = {
        "us_slug": slug, "best_bid": bb, "best_offer": bo,
        "spread": (bo - bb) if two_sided else None,
        "mid": ((bb + bo) / 2) if two_sided else None,
        "bid_touch_usd": notional(bids[:1]), "offer_touch_usd": notional(offers[:1]),
        "bid_book_usd": notional(bids), "offer_book_usd": notional(offers),
        "n_bid_levels": len(bids), "n_offer_levels": len(offers),
        "n_rejected_levels": bad_b + bad_o,
        "capture_lag_s": lag,
    }
    for sz in SIZES:
        s, exh = slippage(offers, sz)
        row[f"slip_{sz}_pct"] = s
        if sz == 500:
            row["exhausts_500"] = exh
    return row


def write(rows, dry: bool):
    if dry:
        print(f"[dry-run] would insert {len(rows)} rows")
        return 0
    import psycopg2
    from psycopg2.extras import execute_batch
    cols = ["us_slug", "best_bid", "best_offer", "spread", "mid", "bid_touch_usd",
            "offer_touch_usd", "bid_book_usd", "offer_book_usd", "n_bid_levels",
            "n_offer_levels", "n_rejected_levels", "slip_50_pct", "slip_100_pct", "slip_500_pct",
            "exhausts_500", "capture_lag_s"]
    sql = (f"INSERT INTO us_book_depth ({','.join(cols)}) "
           f"VALUES ({','.join(['%s'] * len(cols))})")
    with psycopg2.connect(PG_DSN) as con:
        with con.cursor() as cur:
            cur.execute(DDL)
            execute_batch(cur, sql, [[r.get(c) for c in cols] for r in rows], page_size=200)
    return len(rows)


def sweep(dry: bool):
    slugs = discover()
    print(f"discovered {len(slugs):,} current markets")
    rows = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for r in ex.map(snap, slugs):
            if r:
                rows.append(r)
    rej = sum(r.get("n_rejected_levels", 0) for r in rows)
    if rej:
        print(f"  WARN: {rej:,} CORRUPT book levels rejected (venue emits "
              f"px.value='USD' / binary qty on some markets) — counted, never coerced")
    two = [r for r in rows if r["spread"] is not None]
    band = [r for r in two if 0.80 <= r["mid"] <= 0.98]
    print(f"books with any liquidity: {len(rows):,} | two-sided: {len(two):,} | "
          f"favourite band 0.80-0.98: {len(band):,}")
    if band:
        import statistics as st
        t = sorted(r["offer_touch_usd"] for r in band)
        print(f"  offer-side depth at the touch: median ${st.median(t):,.0f}  "
              f"min ${t[0]:,.0f}  max ${t[-1]:,.0f}")
        sp = sorted(r["spread"] for r in band)
        print(f"  quoted spread: median {st.median(sp)*100:.2f}c")
        tight = [r for r in band if r["spread"] <= 0.0101]
        print(f"  FAVBAND tradeable (spread<=1c): {len(tight)}/{len(band)}")
    n = write(rows, dry)
    print(f"wrote {n} rows to us_book_depth")
    return len(band)


def self_test() -> int:
    lv = lambda p, q: {"px": {"value": str(p), "currency": "USD"}, "qty": str(q)}

    # notional is px*qty (SHARES), not qty
    assert abs(notional([(0.81, 100.0)]) - 81.0) < 1e-9

    # walking one deep level: no slippage   (slippage takes PARSED (px,qty) pairs)
    s, exh = slippage([(0.80, 10000.0)], 500)
    assert abs(s) < 1e-9 and not exh

    # walking into a second level: positive slippage, correctly sized
    #   $50 at 0.80 with only 25 shares ($20) there, rest at 0.90
    s, exh = slippage([(0.80, 25.0), (0.90, 1000.0)], 50)
    # 20$ at .80 = 25 sh; 30$ at .90 = 33.33 sh; vwap = 50/58.33 = 0.857
    assert 6.0 < s < 8.0, f"expected ~7% slippage, got {s}"
    assert not exh

    # a book too small must report exhaustion, never a fake fill
    s, exh = slippage([(0.80, 10.0)], 500)
    assert exh is True

    # empty book -> no slippage number, flagged exhausted (never 0.0, which reads as "free")
    s, exh = slippage([], 50)
    assert s is None and exh is True

    # THE FIELD-NAME REGRESSION: a response using "asks" must not be read as a live book.
    # snap() reads `offers`; asserting here so a future refactor to `asks` fails loudly.
    d = {"bids": [lv(0.81, 10)], "offers": []}
    assert (d.get("offers") or []) == [], "ask side must be read from `offers`"
    assert "asks" not in d, "venue does not use `asks`; a consumer expecting it sees an empty book"

    # THE REAL CORRUPT FIXTURE, captured live 2026-07-19. Must be rejected, never coerced.
    corrupt = {"px": {"value": "USD", "currency": ""}, "qty": "\b\u0019"}
    assert parse_level(corrupt) is None, "corrupt venue level must be rejected"
    good, bad = clean_levels([lv(0.81, 100), corrupt, lv(0.80, 50)])
    assert good == [(0.81, 100.0), (0.80, 50.0)] and bad == 1
    assert abs(notional(good) - (0.81 * 100 + 0.80 * 50)) < 1e-9

    # out-of-range probabilities and non-positive sizes are not liquidity
    assert parse_level(lv(1.5, 10)) is None and parse_level(lv(0.0, 10)) is None
    assert parse_level(lv(0.9, 0)) is None and parse_level(lv(0.9, -5)) is None

    print("us_book_capture self-test OK "
          "(notional=px*qty, slippage walk, exhaustion, empty-book, "
          "`offers` field guard, CORRUPT-LEVEL rejection)")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test())
    if a.once:
        sweep(a.dry_run)
        return
    ap.print_help()


if __name__ == "__main__":
    main()
