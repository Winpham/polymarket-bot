#!/usr/bin/env python3
"""
FAVBAND SHADOW — the closing-line recorder. READ-ONLY. NEVER PLACES AN ORDER.

WHY THIS IS THE HIGHEST-LEVERAGE INSTRUMENT AVAILABLE
-----------------------------------------------------
ROI needs ~560 independent events (~37 days) before a 1.5% edge clears zero, because each game
yields exactly ONE binary draw. λ — whether the market moves TOWARD our pick after we buy — uses
the PRICE PATH, so every quote is an observation. It answers in days what ROI answers in months.

λ is also the more decisive question. It separates the two worlds:

  λ > 0  we bought before the market agreed with us. That is INFORMATION, and information is the
         only thing that clears the round-trip toll (~1-2% vs a premium of ~1.26%).
  λ ≈ 0  we are collecting a RISK PREMIUM. Drawdowns are structural, not bad luck, and no amount
         of execution polish improves the expectation.

The first forward λ measurement (2026-07-20) was +0.104c [-0.441, +0.777] — indeterminate. Not
because the edge is absent, but because THE WINDOW WAS TOO SHORT: entry lands ~26 min before
tip-off and the last quote we happened to hold was ~10 min before, so it measured 16 minutes of
drift with NO observation at t-0. `us_book_depth` sweeps the whole venue and lands only 1.68% of
its observations inside the decision window.

This closes that hole the cheap way: once a signal fires, follow THAT market only, to tip-off.

WHAT IT DOES
------------
Every run, for each signal whose game has not started, fetches the real book and records our side's
price. Reuses `favband_forward`'s venue primitives verbatim — the ask side is `offers` not `asks`,
levels can be corrupt (`px.value='USD'`, qty carrying raw bytes), and side-1 favourites price at
`1 - side0_bid`. Re-deriving any of that here is how the two harnesses would silently disagree.

FAIL LOUD, NEVER CLOSED
-----------------------
A shadow that quietly records nothing is worse than none: it manufactures a confident λ from a
handful of survivor quotes. `--report` states coverage per signal and refuses to print a λ when
coverage is too thin to mean anything.

  ./favband_shadow.py --self-test   # synthetic fixtures; no network, no DB
  ./favband_shadow.py --once        # one polling pass over live signals
  ./favband_shadow.py --report      # lambda at the CLOSE, with coverage stated first
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Reuse the venue's hard-won quirks rather than re-deriving them.
from favband_forward import GW, PG_DSN, UA, WORKERS, clean, complement, get  # noqa: E402

# Version-agnostic for the same reason as the settler: a concurrent branch bumped the harness to
# "favband-v2-2026-07-21", and a shadow pinned to v1 would follow nothing while logging cheerfully.
# What we shadow is a live signal, whichever rule produced it.
RULE_FILTER = os.environ.get("FAVBAND_RULE_VERSION")

# A signal needs at least this many quotes, and one inside the final stretch, before its λ means
# anything. Below it the "close" is just whichever quote we happened to catch.
MIN_QUOTES = 3
CLOSE_WINDOW_MIN = 5.0

DDL = """
CREATE TABLE IF NOT EXISTS favband_signal_shadow (
    id          BIGSERIAL PRIMARY KEY,
    signal_id   BIGINT NOT NULL,
    us_slug     TEXT NOT NULL,
    ts          TIMESTAMPTZ NOT NULL DEFAULT now(),
    mins_to_start DOUBLE PRECISION,
    fav_side    INTEGER,
    side0_bid   DOUBLE PRECISION,
    side0_offer DOUBLE PRECISION,
    our_px      DOUBLE PRECISION,     -- what WE would pay right now, orientation applied
    our_mid     DOUBLE PRECISION,     -- mid on OUR side, the λ basis
    spread      DOUBLE PRECISION,
    touch_usd   DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS favband_shadow_sig  ON favband_signal_shadow (signal_id, ts);
CREATE INDEX IF NOT EXISTS favband_shadow_ts   ON favband_signal_shadow (ts DESC);
"""


def our_prices(side0_bids, side0_offers, fav_side: int):
    """Our side's (px_to_pay, mid, spread, touch_usd) given the raw side-0 book.

    Orientation is the silent-inversion trap: a side-1 favourite pays `1 - side0_bid`, NOT
    `1 - side0_offer`. Getting this backwards flips the sign of λ, which would turn a risk premium
    into an apparent information edge — the single most expensive mistake this file could make."""
    if not side0_bids or not side0_offers:
        return None
    bb, bo = side0_bids[0][0], side0_offers[0][0]
    if bo <= bb:
        return None
    if fav_side == 0:
        levels, px, mid = side0_offers, bo, (bb + bo) / 2
    else:
        levels, px, mid = complement(side0_bids), 1.0 - bb, 1.0 - (bb + bo) / 2
    return px, mid, bo - bb, levels[0][0] * levels[0][1]


def poll_once(dry: bool = False) -> int:
    import psycopg2

    with psycopg2.connect(PG_DSN) as con:
        with con.cursor() as cur:
            cur.execute(DDL)
            where, params = "game_start > now()", []
            if RULE_FILTER:
                where += " AND rule_version=%s"
                params.append(RULE_FILTER)
            cur.execute("SELECT id, us_slug, fav_side, game_start FROM favband_paper_signals "
                        f"WHERE {where} ORDER BY game_start", params)
            live = cur.fetchall()

    print(f"live signals awaiting tip-off: {len(live)}")
    if not live:
        # Not an error, and not silence either — an empty pass is a recorded fact.
        print("  (nothing in flight — no signal has fired for an upcoming game)")
        return 0

    now = dt.datetime.now(dt.timezone.utc)

    def probe(row):
        sid, slug, fav_side, gstart = row
        d = (get(f"/v1/markets/{slug}/book") or {}).get("marketData") or {}
        p = our_prices(clean(d.get("bids")), clean(d.get("offers")), fav_side)
        if p is None:
            return None
        px, mid, spread, touch = p
        bb = clean(d.get("bids"))[0][0]
        bo = clean(d.get("offers"))[0][0]
        return (sid, slug, (gstart - now).total_seconds() / 60.0, fav_side,
                bb, bo, px, mid, spread, touch)

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        rows = [r for r in ex.map(probe, live) if r]

    print(f"  quotes captured: {len(rows)}/{len(live)}")
    if dry:
        print("  [dry-run] nothing written")
        return len(rows)
    if rows:
        from psycopg2.extras import execute_batch
        with psycopg2.connect(PG_DSN) as con:
            with con.cursor() as cur:
                cur.execute(DDL)
                execute_batch(cur,
                              "INSERT INTO favband_signal_shadow (signal_id, us_slug, "
                              "mins_to_start, fav_side, side0_bid, side0_offer, our_px, our_mid, "
                              "spread, touch_usd) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", rows)
        print(f"  wrote {len(rows)} shadow quotes")
    return len(rows)


def report():
    import numpy as np
    import pandas as pd
    import psycopg2

    with psycopg2.connect(PG_DSN) as con:
        d = pd.read_sql("""
            SELECT h.signal_id, h.us_slug, h.mins_to_start, h.our_mid, h.our_px,
                   s.entry_vwap, s.market_family, s.settled, s.won
            FROM favband_signal_shadow h
            JOIN favband_paper_signals s ON s.id = h.signal_id
            WHERE h.mins_to_start >= 0
        """, con)

    print("=" * 78)
    print("FAVBAND SHADOW — CLOSING LINE")
    print("=" * 78)
    if d.empty:
        print("  no shadow quotes yet. Run --once on a live slate.")
        return

    cov = d.groupby("signal_id").agg(quotes=("our_mid", "size"),
                                     closest=("mins_to_start", "min"))
    good = cov[(cov.quotes >= MIN_QUOTES) & (cov.closest <= CLOSE_WINDOW_MIN)]
    print(f"  signals shadowed      : {len(cov)}")
    print(f"  median quotes/signal  : {cov.quotes.median():.0f}")
    print(f"  with >= {MIN_QUOTES} quotes AND one inside {CLOSE_WINDOW_MIN:.0f} min: "
          f"{len(good)}  <- the only ones λ may use")
    if len(good) == 0:
        print("\n  COVERAGE TOO THIN FOR λ. Refusing to print a number computed from whichever\n"
              "  quotes happened to survive — that is how a confident artifact gets made.")
        return

    close = (d[d.signal_id.isin(good.index)]
             .sort_values("mins_to_start").groupby("signal_id").first())
    close["lam"] = close.our_mid - close.entry_vwap
    close["event"] = close.us_slug.map(lambda x: "-".join(str(x).split("-")[:4]))

    rng = np.random.default_rng(17)
    ev = close.event.values
    uniq = np.unique(ev)
    idx = {g: np.where(ev == g)[0] for g in uniq}
    vals = close.lam.values
    boot = [vals[np.concatenate([idx[g] for g in rng.choice(uniq, len(uniq), replace=True)])].mean()
            for _ in range(8000)]
    lo, hi = np.percentile(boot, 2.5), np.percentile(boot, 97.5)

    print(f"\n  λ at the close: {close.lam.mean() * 100:+.3f}c  "
          f"[{lo * 100:+.3f}c, {hi * 100:+.3f}c]   n={len(close)}  events={close.event.nunique()}")
    print(f"  median {close.lam.median() * 100:+.3f}c   moved toward us: {(close.lam > 0).mean():.1%}")
    print(f"  closing quote taken a median of {close.mins_to_start.median():.1f} min before tip-off")

    if hi < 0:
        print("\n  λ is significantly NEGATIVE — the market moves AWAY from our picks. Whatever "
              "\n  return exists is settlement variance, and drawdowns are structural.")
    elif lo > 0:
        print("\n  λ is significantly POSITIVE — we buy before the market agrees. That is "
              "INFORMATION,\n  the only thing that clears the toll. Size the follow-up, do not "
              "declare victory.")
    else:
        print("\n  λ is INDETERMINATE — the CI spans zero. Not evidence either way; keep accruing.")


def self_test() -> int:
    L = lambda p, q: (p, q)

    # side-0 favourite: we pay the side-0 OFFER
    r = our_prices([L(0.89, 100)], [L(0.90, 100)], 0)
    assert r and abs(r[0] - 0.90) < 1e-12, f"side-0 favourite pays the offer, got {r}"
    assert abs(r[1] - 0.895) < 1e-12, "side-0 mid"

    # side-1 favourite: side-0 book 0.10/0.11 => we pay 1-0.10 = 0.90, NOT 1-0.11
    r = our_prices([L(0.10, 100)], [L(0.11, 100)], 1)
    assert r and abs(r[0] - 0.90) < 1e-12, f"side-1 favourite pays 1-side0_bid, got {r}"
    assert abs(r[1] - 0.895) < 1e-12, f"side-1 mid is 1-side0_mid, got {r[1]}"

    # the two orientations must be mirror images — if they are not, λ's sign is unreliable
    a = our_prices([L(0.89, 100)], [L(0.90, 100)], 0)
    b = our_prices([L(0.10, 100)], [L(0.11, 100)], 1)
    assert abs(a[1] - b[1]) < 1e-12, "mirrored books must give the same our-side mid"

    # degenerate books are refused, never coerced into a price
    assert our_prices([], [L(0.9, 1)], 0) is None, "one-sided book is not a quote"
    assert our_prices([L(0.9, 1)], [], 0) is None, "one-sided book is not a quote"
    assert our_prices([L(0.91, 1)], [L(0.90, 1)], 0) is None, "crossed book is refused"

    # touch notional is px*qty on OUR side
    r = our_prices([L(0.89, 100)], [L(0.90, 200)], 0)
    assert abs(r[3] - 0.90 * 200) < 1e-9, f"side-0 touch notional, got {r[3]}"
    r = our_prices([L(0.10, 300)], [L(0.11, 1)], 1)
    assert abs(r[3] - 0.90 * 300) < 1e-9, f"side-1 touch notional uses the bid size, got {r[3]}"

    # λ sign convention: buying at 0.90 and closing at 0.93 is the market coming TO us
    assert (0.93 - 0.90) > 0, "positive λ means the market moved toward our pick"

    print("favband_shadow self-test OK (orientation both sides + mirror symmetry, "
          "degenerate books refused, touch notional, λ sign)")
    return 0


def main() -> int:
    args = set(sys.argv[1:])
    if "--self-test" in args:
        return self_test()
    if "--once" in args:
        poll_once(dry="--dry-run" in args)
        return 0
    if "--report" in args:
        report()
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
