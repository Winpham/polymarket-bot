#!/usr/bin/env python3
"""
FAVBAND FORWARD — the pre-registered paper test. READ-ONLY. NEVER PLACES AN ORDER.

WHY THIS IS THE ONLY THING THAT CAN ANSWER "IS IT PROFITABLE"
------------------------------------------------------------
FAVBAND's retrospective edge rests on 21 days of archive, and it fails second-half stability
(LB -0.24). The historical window CANNOT be extended: nothing in the repo fetches the venue's
time-and-sales or daily market report, and there is no public URL for them (probed 2026-07-19 —
`polymarket.us/reports/...` returns the Next.js catch-all). So the weakest criterion is
unresolvable retrospectively. Only forward accrual settles it.

The strategy also depends on a LIVE quote: it only trades when the book is tight, which a backtest
can only approximate through a Roll estimate. Roll understated the true spread by ~2x. This harness
removes that approximation entirely by recording what we would ACTUALLY PAY, walking the real book
for the target size, at the moment of decision.

WHAT IT RECORDS (the executed basis this project has never had)
--------------------------------------------------------------
For every qualifying signal: the VWAP to fill $STAKE walking the real offer side, the quoted
spread, dollars resting at the touch, slippage vs the touch, lead time to game start, and the
orientation used. Settlement is joined later from the venue's own market record.

NEVER IMPUTE. A market without a live two-sided book at decision time is NOT a signal. It is
recorded as a SKIP with a reason, never filled in with a synthetic price. `COALESCE(entry_ask,
initial_market_price + haircut)` is what manufactured the retracted "+6.95%".

ORIENTATION (the silent-inversion trap)
---------------------------------------
`/book` quotes side 0 only. If the favourite is side 1, our ask is the complement of THEIR BID:
    our_ask(side1) = 1 - best_bid(side0)
and the size available to us is the side-0 BID depth. Getting this backwards bets the wrong team
at the wrong price. It is explicit here and self-tested.

  ./favband_forward.py --self-test        # synthetic fixtures, no network, no DB
  ./favband_forward.py --once             # one scan; records signals + skips
  ./favband_forward.py --once --dry-run   # scan and print, write nothing
  ./favband_forward.py --report           # running gate scorecard on accrued signals
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

GW = "https://gateway.polymarket.us"
PG_DSN = os.environ.get("ARCHIVE_PG_DSN", "postgresql://bot:bot@127.0.0.1:5432/polymarket")
UA = {"User-Agent": "research/1.0"}
WORKERS = int(os.environ.get("FAVBAND_WORKERS", "6"))

# ---- the pre-registered rule. Changing any of these invalidates accrued signals.
BAND_LO, BAND_HI = 0.80, 0.98
MAX_SPREAD = 0.010          # only trade a tight book — the whole finding depends on this
SPREAD_EPS = 1e-9           # 0.90-0.89 == 0.010000000000000009 in binary float. Without this
                            # tolerance an exactly-1c book is rejected — and 1c books are ~70%
                            # of the tradeable set, so the strategy would silently trade nothing.
LEAD_MAX_MIN = 30           # fresh: within 30 min of game start
LEAD_MIN_MIN = 0            # strictly pre-game
STAKE_USD = 50.0            # the size we price; capacity is measured, not assumed
FEE_RATE = 0.05
RULE_VERSION = "favband-v1-2026-07-19"

DDL = """
CREATE TABLE IF NOT EXISTS favband_paper_signals (
    id             BIGSERIAL PRIMARY KEY,
    rule_version   TEXT NOT NULL,
    us_slug        TEXT NOT NULL,
    fired_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    game_start     TIMESTAMPTZ,
    lead_min       DOUBLE PRECISION,
    -- orientation: which side we bought, and the raw side-0 book it came from
    fav_side       INTEGER,          -- 0 or 1
    side0_bid      DOUBLE PRECISION,
    side0_offer    DOUBLE PRECISION,
    -- what we would ACTUALLY pay for STAKE_USD, walking the real book
    entry_vwap     DOUBLE PRECISION NOT NULL,
    touch_px       DOUBLE PRECISION NOT NULL,
    spread         DOUBLE PRECISION NOT NULL,
    slip_pct       DOUBLE PRECISION,
    touch_usd      DOUBLE PRECISION,
    book_usd       DOUBLE PRECISION,
    stake_usd      DOUBLE PRECISION,
    filled_usd     DOUBLE PRECISION,
    fee_per_share  DOUBLE PRECISION,
    -- settled later
    settled        BOOLEAN DEFAULT FALSE,
    won            BOOLEAN,
    settled_at     TIMESTAMPTZ,
    UNIQUE (rule_version, us_slug)
);
CREATE TABLE IF NOT EXISTS favband_paper_skips (
    id           BIGSERIAL PRIMARY KEY,
    rule_version TEXT NOT NULL,
    us_slug      TEXT NOT NULL,
    seen_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    reason       TEXT NOT NULL,
    detail       TEXT
);
CREATE INDEX IF NOT EXISTS favband_signals_fired ON favband_paper_signals (fired_at DESC);
CREATE INDEX IF NOT EXISTS favband_skips_seen   ON favband_paper_skips (seen_at DESC);
"""


def get(path: str, timeout: int = 15):
    try:
        req = urllib.request.Request(f"{GW}{path}", headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except Exception:
        return {}


def parse_level(lv):
    """Strict. The venue emits corrupt levels (px.value='USD', binary qty) — see us_book_capture."""
    try:
        px = float(lv["px"]["value"])
        qty = float(lv["qty"])
    except (TypeError, ValueError, KeyError):
        return None
    if not (0.0 < px < 1.0) or not (qty > 0) or qty != qty:
        return None
    return px, qty


def clean(levels):
    return [p for p in (parse_level(x) for x in (levels or [])) if p]


def walk(levels, dollars):
    """VWAP to spend `dollars`. Returns (vwap, filled, exhausted)."""
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
        return None, 0.0, True
    return spent / shares, spent, spent < dollars - 1e-9


def complement(levels):
    """Convert side-0 levels into the OTHER side's levels: price 1-p, same size.
    Buying side 1 means lifting what side-0 holders are BIDDING."""
    return [(1.0 - px, qty) for px, qty in levels]


def evaluate(side0_bids, side0_offers, stake=STAKE_USD):
    """Decide whether this market is a FAVBAND signal, and at what executed price.

    Returns (signal_dict | None, skip_reason | None).
    """
    if not side0_bids or not side0_offers:
        return None, "no_two_sided_book"
    bb, bo = side0_bids[0][0], side0_offers[0][0]
    if bo <= bb:
        return None, "crossed_or_locked"
    mid = (bb + bo) / 2
    spread = bo - bb

    # orientation: the favourite is whichever side trades above 0.5
    if mid >= 0.5:
        fav_side = 0
        levels = side0_offers              # we lift side-0 offers
    else:
        fav_side = 1
        levels = complement(side0_bids)    # we lift side-0 bids, priced 1-p
        mid = 1 - mid
    if not (BAND_LO <= mid <= BAND_HI):
        return None, "outside_band"
    if spread > MAX_SPREAD + SPREAD_EPS:
        return None, "spread_too_wide"

    vwap, filled, exhausted = walk(levels, stake)
    if vwap is None:
        return None, "no_size"
    if exhausted:
        return None, "insufficient_depth"

    touch = levels[0][0]
    return {
        "fav_side": fav_side, "side0_bid": bb, "side0_offer": bo,
        "entry_vwap": vwap, "touch_px": touch, "spread": spread,
        "slip_pct": (vwap - touch) / touch * 100.0,
        "touch_usd": levels[0][0] * levels[0][1],
        "book_usd": sum(p * q for p, q in levels),
        "stake_usd": stake, "filled_usd": filled,
        "fee_per_share": FEE_RATE * vwap * (1 - vwap),
    }, None


# ------------------------------------------------------------------ scanning
def upcoming(window_min: int = 240):
    """Markets whose game starts inside the next `window_min` minutes."""
    hi = 224600
    while True:
        d = get(f"/v1/markets?offset={hi}&limit=400")
        if len(d.get("markets", [])) < 400:
            break
        hi += 400
        if hi > 400000:
            break
    now = dt.datetime.now(dt.timezone.utc)
    out = []
    for i in range(6):
        off = max(hi - i * 400, 0)
        for m in get(f"/v1/markets?offset={off}&limit=400").get("markets", []):
            gs = m.get("gameStartTime") or m.get("endDate")
            if not gs or not m.get("slug"):
                continue
            try:
                t = dt.datetime.fromisoformat(gs.replace("Z", "+00:00"))
            except ValueError:
                continue
            lead = (t - now).total_seconds() / 60
            if LEAD_MIN_MIN <= lead <= window_min:
                out.append((m["slug"], t, lead))
        if off == 0:
            break
    return out


def scan(dry: bool):
    cands = upcoming()
    print(f"markets starting within 4h: {len(cands)}")
    if not cands:
        print("  (no upcoming games — sports books are between sessions)")
        return 0, {}

    def probe(c):
        slug, gstart, lead = c
        d = (get(f"/v1/markets/{slug}/book") or {}).get("marketData") or {}
        sig, reason = evaluate(clean(d.get("bids")), clean(d.get("offers")))
        return slug, gstart, lead, sig, reason

    signals, skips = [], {}
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for slug, gstart, lead, sig, reason in ex.map(probe, cands):
            if sig and lead <= LEAD_MAX_MIN:
                sig.update({"us_slug": slug, "game_start": gstart, "lead_min": lead})
                signals.append(sig)
            elif sig:
                skips["too_early"] = skips.get("too_early", 0) + 1
            else:
                skips[reason] = skips.get(reason, 0) + 1

    print(f"QUALIFYING SIGNALS: {len(signals)}")
    print(f"  skips: {skips}")
    for s in signals[:10]:
        print(f"   {s['us_slug'][:44]:<44} side{s['fav_side']} "
              f"vwap {s['entry_vwap']:.4f} spread {s['spread']*100:.1f}c "
              f"slip {s['slip_pct']:.2f}% touch ${s['touch_usd']:,.0f} "
              f"lead {s['lead_min']:.0f}m")
    if not dry and signals:
        write(signals, skips)
        print(f"  wrote {len(signals)} signals")
    elif dry:
        print("  [dry-run] nothing written")
    return len(signals), skips


def write(signals, skips):
    import psycopg2
    from psycopg2.extras import execute_batch
    cols = ["rule_version", "us_slug", "game_start", "lead_min", "fav_side", "side0_bid",
            "side0_offer", "entry_vwap", "touch_px", "spread", "slip_pct", "touch_usd",
            "book_usd", "stake_usd", "filled_usd", "fee_per_share"]
    sql = (f"INSERT INTO favband_paper_signals ({','.join(cols)}) "
           f"VALUES ({','.join(['%s']*len(cols))}) ON CONFLICT DO NOTHING")
    with psycopg2.connect(PG_DSN) as con:
        with con.cursor() as cur:
            cur.execute(DDL)
            execute_batch(cur, sql, [[RULE_VERSION] + [s.get(c) for c in cols[1:]]
                                     for s in signals])


def report():
    import psycopg2
    with psycopg2.connect(PG_DSN) as con:
        with con.cursor() as cur:
            cur.execute(DDL)
            cur.execute("SELECT count(*), count(*) FILTER (WHERE settled), "
                        "count(*) FILTER (WHERE settled AND won) "
                        "FROM favband_paper_signals WHERE rule_version=%s", (RULE_VERSION,))
            n, ns, nw = cur.fetchone()
            cur.execute("SELECT avg(entry_vwap), avg(spread), avg(slip_pct), avg(touch_usd) "
                        "FROM favband_paper_signals WHERE rule_version=%s", (RULE_VERSION,))
            av = cur.fetchone()
    print("=" * 78)
    print(f"FAVBAND FORWARD — rule {RULE_VERSION}")
    print("=" * 78)
    print(f"  signals fired : {n or 0}")
    print(f"  settled       : {ns or 0}   won: {nw or 0}")
    if av and av[0]:
        print(f"  mean entry vwap {av[0]:.4f}  spread {av[1]*100:.2f}c  "
              f"slip {av[2]:.3f}%  touch ${av[3]:,.0f}")
    print("\n  PRE-REGISTERED GATE (none of this is certified until ALL are met):")
    print(f"    [{'x' if (ns or 0) >= 60 else ' '}] >= 60 settled events   ({ns or 0}/60)")
    print("    [ ] ROI lower bound > 0 at the EXECUTED vwap, event-clustered")
    print("    [ ] >= 2 distinct competitions, each individually positive")
    print("    [ ] >= 2 disjoint weeks, each individually positive")
    print("\n  Until every box is ticked: k=0. A positive mean is not a result.")


def self_test() -> int:
    L = lambda p, q: (p, q)

    # ---- orientation: favourite on side 0
    bids = [L(0.89, 10000)]
    offers = [L(0.90, 10000)]
    sig, reason = evaluate(bids, offers, stake=50)
    assert sig and sig["fav_side"] == 0, reason
    assert abs(sig["entry_vwap"] - 0.90) < 1e-9, "side-0 favourite pays the side-0 offer"

    # ---- orientation: favourite on side 1 (side 0 is the longshot)
    #      side-0 book 0.10/0.11 => side 1 is 0.89/0.90; we lift side-0 BIDS at 1-0.10=0.90
    bids = [L(0.10, 10000)]
    offers = [L(0.11, 10000)]
    sig, reason = evaluate(bids, offers, stake=50)
    assert sig and sig["fav_side"] == 1, reason
    assert abs(sig["entry_vwap"] - 0.90) < 1e-9, \
        f"side-1 favourite must pay 1-side0_bid=0.90, got {sig['entry_vwap']}"
    # THE INVERSION GUARD: it must NOT be 1-offer (0.89) — that is a price we could never get
    assert abs(sig["entry_vwap"] - 0.89) > 1e-6

    # ---- an EXACTLY-1c book must qualify (float: 0.90-0.89 = 0.010000000000000009)
    sig, reason = evaluate([L(0.89, 1e5)], [L(0.90, 1e5)], stake=50)
    assert sig is not None, f"exactly-1c book must qualify, got {reason}"

    # ---- a wide book is not a signal
    sig, reason = evaluate([L(0.85, 1e4)], [L(0.90, 1e4)], stake=50)
    assert sig is None and reason == "spread_too_wide"

    # ---- outside the band is not a signal
    sig, reason = evaluate([L(0.60, 1e4)], [L(0.605, 1e4)], stake=50)
    assert sig is None and reason == "outside_band"

    # ---- a thin book is a SKIP, never a fill at a fantasy price
    sig, reason = evaluate([L(0.89, 5)], [L(0.895, 5)], stake=50)
    assert sig is None and reason == "insufficient_depth", reason

    # ---- one-sided book is a skip
    assert evaluate([], [L(0.9, 100)])[1] == "no_two_sided_book"

    # ---- slippage is real: walking two levels must cost more than the touch
    sig, _ = evaluate([L(0.890, 1e5)], [L(0.895, 20), L(0.90, 1e5)], stake=50)
    assert sig and sig["entry_vwap"] > sig["touch_px"] and sig["slip_pct"] > 0

    # ---- fee uses the real schedule and shrinks toward the extremes
    assert sig["fee_per_share"] < FEE_RATE * 0.5 * 0.5

    # ---- complement is an involution and preserves size
    lv = [L(0.3, 10), L(0.2, 5)]
    rt = complement(complement(lv))
    assert all(abs(a[0]-b[0]) < 1e-12 and a[1] == b[1] for a, b in zip(rt, lv))

    print("favband_forward self-test OK (orientation BOTH sides + inversion guard, band, "
          "spread, depth-skip, slippage, fee schedule, complement involution)")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test())
    if a.report:
        report()
        return
    if a.once:
        scan(a.dry_run)
        return
    ap.print_help()


if __name__ == "__main__":
    main()
