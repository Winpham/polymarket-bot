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
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

GW = "https://gateway.polymarket.us"
PG_DSN = os.environ.get("ARCHIVE_PG_DSN", "postgresql://bot:bot@127.0.0.1:5432/polymarket")
MARKETS_PARQUET = os.path.expanduser(
    os.environ.get("US_MARKETS_PARQUET", "~/polymarket-archive/us_markets.parquet"))
UA = {"User-Agent": "research/1.0"}
WORKERS = int(os.environ.get("FAVBAND_WORKERS", "6"))
PAGE = 400
# see `upcoming`. Measured 2026-07-21: 6 pages -> 8 in-window markets, 40 -> 426, 120 -> 609 with
# the deepest hit at page -97, i.e. 120 is the first depth that actually converges.
# COST: a 120-page sweep plus the per-market book probes takes ~6 min wall clock and is I/O-bound
# on the venue (32 workers is no faster than 12), which EXCEEDS the 300s agent interval. Run it on
# >=900s until discovery is restructured — see the note in `upcoming`.
SCAN_PAGES = int(os.environ.get("FAVBAND_SCAN_PAGES", "120"))

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
RULE_VERSION = "favband-v2-2026-07-21"
# v1 (2026-07-19) accrued 78 signals and is RETAINED but not poolable with v2: it scanned only 6
# pages of the market list (~14% of the eligible universe, measured 2026-07-21) and never settled
# anything. v2 fixes discovery, settlement and event-level accounting. Selection differs, so the
# populations are not interchangeable.

# Capacity ladder. Recorded per signal, NEVER used to gate firing — so this changes what we KNOW
# about a signal, not which signals exist. Both rule versions stay comparable on the $50 basis.
SIZE_LADDER = (50.0, 100.0, 250.0, 500.0, 1000.0)

# A slug is one MARKET; a game is one EVENT. `astatc-mlb-pit-cle-2026-07-19-hr-orozco-gte1` and the
# 10 other props on that game share a settlement shock, so they are ONE independent observation.
# The retrospective clustered on this key (favband.py::event_key); the forward gate must too, or
# it counts ~4x the evidence it actually has (measured on v1: 78 signals = ~20 games).
EVENT_RE = re.compile(r"^[a-z]+-(.*?-\d{4}-\d{2}-\d{2})")


def event_key(slug: str) -> str:
    """Collapse a market slug to its GAME. Mirrors favband.py::event_key exactly."""
    m = EVENT_RE.match(slug)
    return m.group(1) if m else slug

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
-- capacity ladder: what each size would ACTUALLY cost at this decision moment. Recording only.
ALTER TABLE favband_paper_signals ADD COLUMN IF NOT EXISTS event_key   TEXT;
ALTER TABLE favband_paper_signals ADD COLUMN IF NOT EXISTS cap_ladder  JSONB;
ALTER TABLE favband_paper_signals ADD COLUMN IF NOT EXISTS settle_src  TEXT;
CREATE INDEX IF NOT EXISTS favband_signals_event ON favband_paper_signals (rule_version, event_key);
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
        "cap_ladder": json.dumps(capacity_ladder(levels, touch)),
    }, None


def capacity_ladder(levels, touch):
    """What each size on SIZE_LADDER would cost, walking this same real book.

    The certified retrospective charges the touch half-spread and the venue fee, and NOTHING for
    walking past the touch — dollar depth did not exist in the archive, so the cost of size was
    structurally invisible. This is that missing term, at every size we might want to trade.

    An unfillable size records filled < size with `exhausted: true`; it is never extrapolated.
    """
    out = {}
    for size in SIZE_LADDER:
        vwap, filled, exhausted = walk(levels, size)
        out[str(int(size))] = None if vwap is None else {
            "vwap": round(vwap, 6),
            "slip_pct": round((vwap - touch) / touch * 100.0, 4),
            "filled": round(filled, 2),
            "exhausted": bool(exhausted),
        }
    return out


# ------------------------------------------------------------------ scanning
def find_end() -> int:
    """Offset of the last page. The list endpoint exposes no count and silently ignores
    order/sort/startDateMin, so the end must be probed. Exponential probe + binary search:
    ~20 requests instead of the ~99 a linear walk from a hardcoded 224600 now costs (and that
    constant drifts further out of date every day the venue lists markets)."""
    lo, hi = 0, PAGE
    while len(get(f"/v1/markets?offset={hi}&limit={PAGE}").get("markets", [])) == PAGE:
        lo, hi = hi, hi * 2
        if hi > 4_000_000:
            break
    while lo + PAGE < hi:                                  # binary search the short page
        mid = ((lo + hi) // 2 // PAGE) * PAGE
        if len(get(f"/v1/markets?offset={mid}&limit={PAGE}").get("markets", [])) == PAGE:
            lo = mid
        else:
            hi = mid
    return lo


def upcoming(window_min: int = 240, pages: int = SCAN_PAGES):
    """Markets whose game starts inside the next `window_min` minutes.

    COVERAGE IS THE BINDING CONSTRAINT, and it was silently broken. The list is append-ordered by
    creation, NOT by start time, so markets for an imminent game are scattered arbitrarily deep:
    measured 2026-07-21, the last 6 pages held 3 of 22+ in-window markets (<=14%), and the deepest
    page probed still held 4. v1 scanned exactly those 6 pages, so it never saw ~86% of its own
    universe — which is why accrual collapsed from 77 signals on day 1 to 1 on day 2.

    Coverage is now reported, and a hit on the LAST page scanned raises the alarm rather than
    quietly returning a short list — a truncated universe must never look like a quiet day.

    KNOWN LIMITATION (not fixed here). This re-walks the entire tail of an append-only list on
    every single scan to rediscover a set that barely changes, which is why a converged sweep
    costs ~6 min. The right shape is a persisted slug -> gameStartTime index, refreshed deeply
    every ~30 min, with the 60s loop probing books only for markets inside the lead window. That
    decouples discovery cost from decision latency. Doing it here would have meant shipping a new
    storage layer inside a bug fix.

    ALSO UNRESOLVED: `get()` swallows every exception and returns {}. Under throttling a page is
    indistinguishable from a genuinely empty one, so both this sweep and `find_end`'s binary
    search would silently under-discover. That is the fail-CLOSED pattern this project has been
    bitten by twice; it deserves its own fix.
    """
    end = find_end()
    now = dt.datetime.now(dt.timezone.utc)
    offsets = [max(end - i * PAGE, 0) for i in range(pages)]
    offsets = sorted(set(offsets), reverse=True)

    def page(off):
        found = []
        for m in get(f"/v1/markets?offset={off}&limit={PAGE}").get("markets", []):
            gs = m.get("gameStartTime") or m.get("endDate")
            if not gs or not m.get("slug"):
                continue
            try:
                t = dt.datetime.fromisoformat(gs.replace("Z", "+00:00"))
            except ValueError:
                continue
            lead = (t - now).total_seconds() / 60
            if LEAD_MIN_MIN <= lead <= window_min:
                found.append((m["slug"], t, lead))
        return off, found

    out, deepest = [], -1
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for i, (off, found) in enumerate(ex.map(page, offsets)):
            if found:
                deepest = max(deepest, i)
            out.extend(found)
    print(f"  discovery: end~{end}, scanned {len(offsets)} pages "
          f"({len(offsets) * PAGE:,} markets), deepest in-window hit at page -{deepest}")
    if deepest >= len(offsets) - 2 and offsets[-1] > 0:
        print(f"  !! COVERAGE WARNING: in-window markets found at the edge of the scan window. "
              f"Raise FAVBAND_SCAN_PAGES above {pages} — the universe is being truncated.")
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

    signals, skips, skip_rows = [], {}, []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for slug, gstart, lead, sig, reason in ex.map(probe, cands):
            if sig and lead <= LEAD_MAX_MIN:
                sig.update({"us_slug": slug, "game_start": gstart, "lead_min": lead,
                            "event_key": event_key(slug)})
                signals.append(sig)
                continue
            why = "too_early" if sig else reason
            skips[why] = skips.get(why, 0) + 1
            # Persist the NEAR MISSES only. `outside_band` is the universe filter — ~78% of all
            # skips and uninteresting per-slug — so it is counted, not stored. Everything else is
            # a market we were willing to trade and DECLINED, which is the funnel that decides
            # whether a dead feed is masquerading as "no edge".
            if why != "outside_band":
                skip_rows.append((slug, why, f"lead={lead:.1f}m"))

    print(f"QUALIFYING SIGNALS: {len(signals)}")
    print(f"  skips: {skips}")
    for s in signals[:10]:
        print(f"   {s['us_slug'][:44]:<44} side{s['fav_side']} "
              f"vwap {s['entry_vwap']:.4f} spread {s['spread']*100:.1f}c "
              f"slip {s['slip_pct']:.2f}% touch ${s['touch_usd']:,.0f} "
              f"lead {s['lead_min']:.0f}m")
    if dry:
        print("  [dry-run] nothing written")
    else:
        # ALWAYS write, even with zero signals. A sweep that qualifies nothing is the single most
        # important row in the ledger: it is the difference between "the market offered nothing"
        # and "our feed was dead". 300 of the first 331 sweeps qualified nothing and recorded
        # NOTHING — the funnel for those sweeps existed only in a log file.
        write(signals, skip_rows)
        print(f"  wrote {len(signals)} signals, {len(skip_rows)} near-miss skips")
    return len(signals), skips


def write(signals, skip_rows):
    import psycopg2
    from psycopg2.extras import execute_batch
    cols = ["rule_version", "us_slug", "game_start", "lead_min", "fav_side", "side0_bid",
            "side0_offer", "entry_vwap", "touch_px", "spread", "slip_pct", "touch_usd",
            "book_usd", "stake_usd", "filled_usd", "fee_per_share", "event_key", "cap_ladder"]
    sql = (f"INSERT INTO favband_paper_signals ({','.join(cols)}) "
           f"VALUES ({','.join(['%s']*len(cols))}) ON CONFLICT DO NOTHING")
    with psycopg2.connect(PG_DSN) as con:
        with con.cursor() as cur:
            cur.execute(DDL)
            if signals:
                execute_batch(cur, sql, [[RULE_VERSION] + [s.get(c) for c in cols[1:]]
                                         for s in signals])
            if skip_rows:
                execute_batch(cur,
                              "INSERT INTO favband_paper_skips (rule_version, us_slug, reason, "
                              "detail) VALUES (%s,%s,%s,%s)",
                              [(RULE_VERSION, s, r, d) for s, r, d in skip_rows])


def settle_and_report(*, report_only: bool = False):
    """Delegate to favband_settle.py — the settlement + scoring leg.

    Settlement deliberately lives in its own instrument rather than here. It has a different
    trust model: this file only ever READS the venue and writes what it observed, while the
    settler WRITES outcomes and must refuse to do so when the join looks inverted. Keeping the
    scoring guards in one audited place beats a second, subtly-different copy.
    """
    import subprocess
    cmd = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "favband_settle.py")]
    cmd.append("--report" if report_only else "--settle")
    return subprocess.call(cmd)


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

    # ---- event_key collapses every prop on a game to ONE independent observation
    assert event_key("astatc-mlb-pit-cle-2026-07-19-hr-orozco-gte1") == "mlb-pit-cle-2026-07-19"
    assert (event_key("astatc-mlb-pit-cle-2026-07-19-hr-orozco-gte1")
            == event_key("astatc-mlb-pit-cle-2026-07-19-hits-stekwa-gte3")), \
        "two props on the SAME game must share one event key or the gate counts 2x the evidence"
    assert event_key("mlb-lad-nyy-2026-07-19") != event_key("mlb-lad-nyy-2026-07-20")
    assert event_key("not-a-slug") == "not-a-slug"          # degrades to itself, never crashes

    # ---- the capacity ladder must price size honestly, and admit when it cannot fill
    lad = capacity_ladder([L(0.90, 100), L(0.95, 1e6)], 0.90)   # $90 at 0.90, then a wall at 0.95
    assert lad["50"]["slip_pct"] == 0.0 and not lad["50"]["exhausted"], "$50 fits inside the touch"
    assert lad["500"]["slip_pct"] > 0, "$500 must walk past the touch and cost more"
    assert lad["50"]["vwap"] < lad["500"]["vwap"] <= 0.95, "cost must be monotone in size"
    thin = capacity_ladder([L(0.90, 10)], 0.90)                  # only $9 in the whole book
    assert thin["50"]["exhausted"] and thin["50"]["filled"] < 50, \
        "an unfillable size must be marked exhausted, NEVER extrapolated into a fantasy fill"

    # ---- scoring lives in favband_settle.py; this file must not grow a second copy of it
    assert "cluster_roi" not in globals(), \
        "scoring was moved to favband_settle.py — two implementations WILL diverge"

    # ---- the single-instance lock: a 6-min sweep on a 5-min timer must not stack
    import tempfile
    lp = os.path.join(tempfile.mkdtemp(), "t.lock")
    with SingleInstance(lp) as first:
        assert first is not None, "the first holder must acquire"
        with SingleInstance(lp) as second:
            assert second is None, "a second concurrent scan MUST be refused, not run"
    assert not os.path.exists(lp), "the lock must be released on clean exit"
    # a lock held by a pid that no longer exists is stale, NOT a permanent wedge
    with open(lp, "w") as f:
        f.write("999999999")
    with SingleInstance(lp) as reclaimed:
        assert reclaimed is not None, "a stale lock from a dead pid must be reclaimed"

    print("favband_forward self-test OK (orientation BOTH sides + inversion guard, band, "
          "spread, depth-skip, slippage, fee schedule, complement involution, event_key "
          "collapsing, capacity ladder incl. exhaustion)")
    return 0


class SingleInstance:
    """Refuse to start if a previous scan is still running.

    A converged 120-page sweep takes ~6 min, which is LONGER than the 300s agent interval it
    inherited. Without this, every cycle stacks another concurrent scan on the venue and the
    machine, and they all write the same rows — the failure gets worse the healthier the sweep is.
    Making the scan safe at ANY interval is a property of the program, not of the plist: the
    correct interval is now a tuning choice rather than a correctness requirement.

    Uses O_EXCL + the pid so a crash cannot wedge the loop forever: a lock whose pid is gone is
    stale and gets reclaimed, which matters because this project has been bitten by exactly the
    opposite failure (a wedged daemon holding a lock nobody could clear).
    """

    def __init__(self, path="/tmp/favband_forward.lock"):
        self.path, self.fd = path, None

    def __enter__(self):
        for _ in range(2):
            try:
                self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
                os.write(self.fd, str(os.getpid()).encode())
                return self
            except FileExistsError:
                try:
                    pid = int(open(self.path).read().strip() or 0)
                except (ValueError, OSError):
                    pid = 0
                alive = False
                if pid > 0:
                    try:
                        os.kill(pid, 0)          # signal 0 == liveness probe, does not kill
                        alive = True
                    except ProcessLookupError:
                        alive = False
                    except PermissionError:
                        alive = True             # exists but not ours
                if alive:
                    print(f"  another scan is still running (pid {pid}) — skipping this cycle. "
                          f"A converged sweep takes ~6min; the interval may be too short.")
                    return None
                print(f"  reclaiming a stale lock from dead pid {pid}")
                try:
                    os.unlink(self.path)
                except FileNotFoundError:
                    pass
        return None

    def __exit__(self, *exc):
        if self.fd is not None:
            os.close(self.fd)
            try:
                os.unlink(self.path)
            except FileNotFoundError:
                pass
        return False


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--settle", action="store_true", help="delegates to favband_settle.py")
    ap.add_argument("--report", action="store_true", help="delegates to favband_settle.py")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test())
    if a.report:
        sys.exit(settle_and_report(report_only=True))
    if a.settle:
        sys.exit(settle_and_report())
    if a.once:
        with SingleInstance() as lock:
            if lock is None:
                return
            scan(a.dry_run)
            if not a.dry_run:
                # settle every cycle: an unsettled signal certifies nothing, and v1 accrued for
                # two days without one because settlement was never on the loop.
                settle_and_report()
        return
    ap.print_help()


if __name__ == "__main__":
    main()
