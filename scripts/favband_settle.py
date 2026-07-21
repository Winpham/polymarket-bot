#!/usr/bin/env python3
"""
FAVBAND SETTLE — the missing leg of the forward test. READ-ONLY on the venue; writes only outcomes.

WHY THIS EXISTS
---------------
`favband_forward.py` fires signals and creates a `settled/won/settled_at` triplet, but NOTHING in
the repository ever wrote it. Found 2026-07-20: 78 signals accrued since 07-19, **0 settled**, while
77 of the 78 were already terminally resolved in the venue's own market record. The pre-registered
gate box `>= 60 settled events` could therefore never tick, no matter how long the harness ran.

That is the project's signature failure mode wearing a new hat: a harness that looks alive, logs
busily, and produces exactly zero certifying data. See the 2d17h tape outage — consumers of a dead
input report "nothing qualified", which is indistinguishable from "no edge".

WHAT IT DOES
------------
Joins pending signals to `us_markets.parquet` (the venue's own market record) and writes the
outcome. A signal is settled ONLY when the market is TERMINALLY resolved — `outcomePrices` is a
clean binary [1,0] or [0,1]. `closed=True` is NOT sufficient: a closed-but-unpriced market is left
pending, never guessed.

FAIL LOUD, NEVER CLOSED
-----------------------
Four guards, each of which EXITS rather than write a plausible-looking wrong number:
  1. provenance   — `us_markets.parquet` is a LIVE, MUTATING file. Every run stamps sha256/mtime.
  2. parse sanity — if <80% of closed markets resolve cleanly binary, the parse is broken.
  3. ORIENTATION  — if the win rate on settled signals sits far BELOW the mean entry price, we
                    bought the wrong side. This is the silent inversion that a "profitable-looking"
                    ledger would hide. Refuse to write.
  4. idempotence  — only rows with settled=false are touched; re-running never double-writes.

  ./favband_settle.py --self-test    # synthetic fixtures; no archive, no DB
  ./favband_settle.py --settle       # join + write outcomes
  ./favband_settle.py --report       # ROI at the EXECUTED vwap, stratified by market family
"""
import ast
import datetime
import hashlib
import os
import sys

import numpy as np

ARCHIVE = os.path.expanduser("~/polymarket-archive")
MK = f"{ARCHIVE}/us_markets.parquet"
PG_DSN = os.environ.get("ARCHIVE_PG_DSN", "postgresql://bot:bot@127.0.0.1:5432/polymarket")
RULE_VERSION = "favband-v1-2026-07-19"
FEE_RATE = 0.05

# A settled ledger whose win rate is this far BELOW the mean entry price is not a losing strategy,
# it is an INVERTED one. At a mean entry of ~0.88 an inverted book wins ~12% of the time.
INVERSION_MARGIN = 0.25


# --------------------------------------------------------------------------- settlement parsing
def parse_outcome_prices(op):
    """Return a list of floats, or None if unparseable. Never raises, never guesses."""
    if op is None:
        return None
    try:
        v = ast.literal_eval(op) if isinstance(op, str) else list(op)
        return [float(x) for x in v]
    except (ValueError, SyntaxError, TypeError):
        return None


def is_terminal(prices) -> bool:
    """TERMINAL = clean binary settlement. `closed=True` alone is NOT enough: the venue leaves
    closed-but-unpriced markets around, and a 0.5/0.5 or 0.97/0.03 row is a live quote, not an
    outcome. Anything that is not exactly {0,1} summing to 1 stays PENDING."""
    if prices is None or len(prices) < 2:
        return False
    if not all(abs(x) < 1e-9 or abs(x - 1.0) < 1e-9 for x in prices):
        return False
    return abs(sum(prices) - 1.0) < 1e-6


def won_side(prices, fav_side: int):
    """Did the side we bought win? None if the index is out of range (never assume)."""
    if fav_side is None or fav_side < 0 or fav_side >= len(prices):
        return None
    return abs(prices[fav_side] - 1.0) < 1e-9


def roi_at_executed(entry_vwap: float, fee_per_share, won: bool) -> float:
    """ROI per dollar staked at the price we ACTUALLY walked the book to.

    Buy `1/px` shares for $1. A winner pays $1/share and the venue takes its taker fee per share.
    A loser is a total loss of the stake. No imputation, no assumed spread — `entry_vwap` already
    contains the spread we paid."""
    fee = 0.0 if fee_per_share is None else float(fee_per_share)
    if not won:
        return -1.0
    return (1.0 - entry_vwap - fee) / entry_vwap


# --------------------------------------------------------------------------- provenance
def snapshot_provenance() -> dict:
    if not os.path.exists(MK):
        sys.exit(f"FATAL: {MK} missing — cannot settle. The market record IS the settlement source.")
    st = os.stat(MK)
    h = hashlib.sha256()
    with open(MK, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    mtime = datetime.datetime.fromtimestamp(st.st_mtime, datetime.timezone.utc)
    age_h = (datetime.datetime.now(datetime.timezone.utc) - mtime).total_seconds() / 3600
    return {"sha256_16": h.hexdigest()[:16], "mtime": mtime.isoformat(timespec="seconds"),
            "bytes": st.st_size, "age_h": age_h}


# --------------------------------------------------------------------------- family labelling
def family_of(market_type) -> str:
    """The forward harness has NO market-type filter, so it trades whatever is in the band. The
    retrospective study that produced the +1.52% was dominated by TEAM/MATCH markets. Labelling the
    family is what makes the mismatch visible instead of silently averaged away."""
    s = str(market_type or "").lower()
    if not s or s == "nan" or s == "none":
        return "UNKNOWN"
    return "PLAYER_PROP" if "player" in s else "TEAM_MATCH"


# --------------------------------------------------------------------------- settle
def settle(dry: bool = False) -> int:
    import pandas as pd
    import psycopg2

    prov = snapshot_provenance()
    print(f"  SNAPSHOT {prov['sha256_16']}  mtime {prov['mtime']}  {prov['bytes']:,}B  "
          f"age {prov['age_h']:.1f}h  (this file MUTATES)")
    if prov["age_h"] > 48:
        print(f"  WARN: market record is {prov['age_h']:.0f}h stale — recent games may not be "
              f"resolved yet. Settling only what IS terminal.")

    df = pd.read_parquet(MK, columns=["slug", "outcomePrices", "closed", "sportsMarketType"])
    df = df.drop_duplicates("slug")

    # guard 2 — parse sanity on the CLOSED population.
    # Sampled: `ast.literal_eval` over ~200k rows costs minutes and buys no extra confidence.
    # A 5,000-row sample bounds the terminal rate to well inside the 80% threshold.
    closed = df[df.closed.astype(str) == "True"]
    if len(closed):
        probe = closed if len(closed) <= 5000 else closed.sample(5000, random_state=17)
        terminal_rate = probe.outcomePrices.apply(
            lambda x: is_terminal(parse_outcome_prices(x))).mean()
        if terminal_rate < 0.80:
            sys.exit(f"FATAL: only {terminal_rate:.1%} of CLOSED markets resolve cleanly binary — "
                     "the settlement parse is probably broken. Refusing to settle.")
        print(f"  settlement parse: {terminal_rate:.1%} of {len(probe):,} sampled closed markets terminal  OK")

    with psycopg2.connect(PG_DSN) as con:
        with con.cursor() as cur:
            cur.execute("ALTER TABLE favband_paper_signals "
                        "ADD COLUMN IF NOT EXISTS market_type TEXT, "
                        "ADD COLUMN IF NOT EXISTS market_family TEXT")
            cur.execute("SELECT id, us_slug, fav_side, entry_vwap, fee_per_share "
                        "FROM favband_paper_signals "
                        "WHERE rule_version=%s AND COALESCE(settled,false)=false", (RULE_VERSION,))
            pending = cur.fetchall()
    print(f"  pending signals: {len(pending)}")
    if not pending:
        print("  nothing to settle.")
        return 0

    rec = df.set_index("slug")[["outcomePrices", "sportsMarketType"]].to_dict("index")
    updates, unmatched, not_terminal, bad_side = [], 0, 0, 0
    for sid, slug, fav_side, vwap, fee in pending:
        row = rec.get(slug)
        if row is None:
            unmatched += 1
            continue
        prices = parse_outcome_prices(row["outcomePrices"])
        if not is_terminal(prices):
            not_terminal += 1
            continue
        w = won_side(prices, fav_side)
        if w is None:
            bad_side += 1
            continue
        updates.append((bool(w), str(row["sportsMarketType"]),
                        family_of(row["sportsMarketType"]), sid, vwap, fee))

    print(f"  resolvable now : {len(updates)}")
    print(f"    not in market record : {unmatched}")
    print(f"    not yet terminal     : {not_terminal}   (left PENDING, never guessed)")
    print(f"    fav_side out of range: {bad_side}")
    if not updates:
        print("  nothing terminal yet.")
        return 0

    # guard 3 — ORIENTATION. An inverted ledger looks like a strategy; it is a wiring bug.
    wins = np.array([u[0] for u in updates], dtype=float)
    pxs = np.array([float(u[4]) for u in updates], dtype=float)
    win_rate, mean_px = wins.mean(), pxs.mean()
    print(f"  orientation check: win rate {win_rate:.3f} vs mean entry price {mean_px:.3f}")
    if win_rate < mean_px - INVERSION_MARGIN:
        sys.exit(f"FATAL: win rate {win_rate:.3f} is {mean_px - win_rate:.3f} BELOW the mean entry "
                 f"price {mean_px:.3f}. We are almost certainly settling the WRONG SIDE "
                 f"(orientation inverted). Refusing to write.")

    if dry:
        print("  [dry-run] nothing written")
        return len(updates)

    with psycopg2.connect(PG_DSN) as con:
        with con.cursor() as cur:
            cur.executemany(
                "UPDATE favband_paper_signals SET settled=true, won=%s, settled_at=now(), "
                "market_type=%s, market_family=%s WHERE id=%s AND COALESCE(settled,false)=false",
                [(u[0], u[1], u[2], u[3]) for u in updates])
    print(f"  SETTLED {len(updates)} signals")
    return len(updates)


# --------------------------------------------------------------------------- report
def cluster_boot(roi: np.ndarray, groups: np.ndarray, n: int = 8000, seed: int = 17):
    """Bootstrap CLUSTERED on the event. Sibling markets of one game are correlated; an unclustered
    CI on them is too narrow, which is how a coin flip starts looking significant."""
    rng = np.random.default_rng(seed)
    uniq = np.unique(groups)
    idx = {g: np.where(groups == g)[0] for g in uniq}
    out = np.empty(n)
    for i in range(n):
        pick = rng.choice(uniq, len(uniq), replace=True)
        sel = np.concatenate([idx[g] for g in pick])
        out[i] = roi[sel].mean()
    return float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))


def wilson(k: int, n: int, z: float = 1.96):
    """Wilson interval on a proportion. Unlike the bootstrap it stays honest at k==n."""
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    den = 1 + z * z / n
    ctr = (p + z * z / (2 * n)) / den
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return float(ctr - half), float(min(1.0, ctr + half))


def zero_loss_check(sub, label: str) -> bool:
    """THE ARTIFACT GUARD. A bootstrap cannot resample a loss it has never seen. On a subset with
    zero losing events the CI collapses to the dispersion of WINNING PAYOUTS — it stops measuring
    uncertainty about the edge and starts measuring price dispersion, which is tiny. That is how a
    slice of 13 games produced "+14.32% [+12.72%, +16.03%]" and looked like the best result in the
    project's history. It is the same defect as the retracted "0% chance of a losing year".

    Returns True when the subset is UNINTERPRETABLE and prints the honest interval instead."""
    n_ev = sub.event.nunique()
    losses = int((~sub.won.astype(bool)).sum())
    if losses > 0 or n_ev == 0:
        return False
    px = float(sub.entry_vwap.mean())
    fee = FEE_RATE * px * (1 - px)
    lo_w, hi_w = wilson(n_ev, n_ev)
    roi_lo = lo_w * (1 - px - fee) / px - (1 - lo_w)
    breakeven_loss_rate = 1 - px
    rule_of_three = min(1.0, 3.0 / n_ev)   # the approximation degenerates below n=3; a rate > 100%
                                           # is not a bound, it is nonsense in the output
    print(f"    ⚠ {label}: ZERO losses in {n_ev} events — the bootstrap CI is an ARTIFACT.")
    print(f"      Rule of three: true loss rate could be {rule_of_three:.1%}; breakeven needs "
          f"< {breakeven_loss_rate:.1%}.")
    print(f"      Honest ROI lower bound (Wilson on events): {roi_lo * 100:+.1f}%  "
          f"{'— CANNOT exclude a losing strategy' if roi_lo < 0 else ''}")
    return True


def event_key(slug: str) -> str:
    """Strip the trailing per-market suffix so sibling props of one game cluster together."""
    parts = str(slug).split("-")
    return "-".join(parts[:4]) if len(parts) >= 4 else str(slug)


def report():
    import pandas as pd
    import psycopg2

    with psycopg2.connect(PG_DSN) as con:
        d = pd.read_sql("SELECT us_slug, fired_at, game_start, lead_min, entry_vwap, spread, "
                        "touch_usd, slip_pct, fee_per_share, settled, won, market_type, "
                        "market_family FROM favband_paper_signals WHERE rule_version=%s",
                        con, params=(RULE_VERSION,))
    n = len(d)
    s = d[d.settled.fillna(False)].copy()
    print("=" * 78)
    print(f"FAVBAND FORWARD — SETTLED LEDGER  (rule {RULE_VERSION})")
    print("=" * 78)
    print(f"  signals fired : {n}")
    print(f"  settled       : {len(s)}   won: {int(s.won.sum()) if len(s) else 0}")
    if not len(s):
        print("\n  Nothing settled. k=0.")
        return

    s["roi"] = [roi_at_executed(v, f, bool(w))
                for v, f, w in zip(s.entry_vwap, s.fee_per_share, s.won)]
    s["event"] = s.us_slug.map(event_key)
    s["day"] = pd.to_datetime(s.fired_at, utc=True).dt.date

    lo, hi = cluster_boot(s.roi.values, s.event.values)
    print(f"\n  ROI at the EXECUTED vwap : {s.roi.mean() * 100:+.2f}%   "
          f"[{lo * 100:+.2f}%, {hi * 100:+.2f}%]  (event-clustered)")
    print(f"  win rate {s.won.mean():.3f}   mean entry {s.entry_vwap.mean():.4f}   "
          f"events {s.event.nunique()}   days {s.day.nunique()}")

    zero_loss_check(s, "overall")

    print("\n  BY MARKET FAMILY — the population question:")
    for fam, g in s.groupby(s.market_family.fillna("UNKNOWN")):
        flo, fhi = cluster_boot(g.roi.values, g.event.values) if g.event.nunique() > 1 else (
            float("nan"), float("nan"))
        print(f"    {fam:<12} n={len(g):<4} events={g.event.nunique():<4} "
              f"roi={g.roi.mean() * 100:+7.2f}%  [{flo * 100:+.2f}%, {fhi * 100:+.2f}%]")
        zero_loss_check(g, fam)

    print("\n  BY MARKET TYPE:")
    for mt, g in s.groupby(s.market_type.fillna("unknown")):
        print(f"    {mt:<34} n={len(g):<4} roi={g.roi.mean() * 100:+7.2f}%  "
              f"win={g.won.mean():.3f}")

    print("\n  PRE-REGISTERED GATE (nothing is certified until ALL are ticked):")
    # The pre-registration says EVENTS, not signals. 77 sibling props of 15 baseball games carry
    # roughly 15 independent draws, not 77 — the siblings share a game, a pitcher and a park.
    # Counting signals here would tick the box on a fifth of the required evidence.
    n_events = s.event.nunique()
    # Likewise "competitions" means distinct LEAGUES. Five `baseball_player_*` market types are one
    # competition (MLB) wearing five names; counting types would flatter this by 5x.
    leagues = s.us_slug.map(lambda x: str(x).split("-")[1] if len(str(x).split("-")) > 1 else "?")
    n_leagues = leagues.nunique()
    ok_n, ok_lb = n_events >= 60, lo > 0
    weeks = pd.to_datetime(s.fired_at, utc=True).dt.isocalendar().week.nunique()
    print(f"    [{'x' if ok_n else ' '}] >= 60 settled EVENTS            "
          f"({n_events}/60)   [{len(s)} signals over {n_events} games]")
    print(f"    [{'x' if ok_lb else ' '}] ROI lower bound > 0 at executed vwap  (LB {lo * 100:+.2f}%)")
    print(f"    [{'x' if n_leagues >= 2 else ' '}] >= 2 distinct competitions      "
          f"({n_leagues}: {', '.join(sorted(leagues.unique())[:6])})")
    print(f"    [{'x' if weeks >= 2 else ' '}] >= 2 disjoint weeks             ({weeks})")
    print("\n  A positive mean is not a result. Until every box is ticked: k=0.")
    print(f"  Effective sample is {n_events} games, not {len(s)} signals — sibling props of one "
          f"game\n  share a pitcher, a park and an umpire. The clustered CI above already "
          f"reflects that.")

    # ---- when will this actually know anything?
    ev_roi = s.groupby("event").roi.mean()
    if len(ev_roi) >= 3:
        sd = float(ev_roi.std(ddof=1))
        rate = n_events / max(s.day.nunique(), 1)
        print(f"\n  TIME TO AN ANSWER  (per-event sd {sd * 100:.1f}pp, "
              f"{rate:.1f} events/day observed)")
        for edge in (0.015, 0.03, 0.045):
            need = (1.96 * sd / edge) ** 2
            print(f"    a true edge of {edge * 100:>4.1f}% needs ~{need:>6,.0f} events "
                  f"= ~{need / max(rate, 1e-9):>4,.0f} days before the CI clears zero")
        print("    Plan against the SMALL edge. If the truth is the retrospective +1.5%, this is a")
        print("    months-long measurement — and stopping early on a good week is how it goes wrong.")

    print("\n  ⚠ POPULATION WARNING")
    fam_mix = s.market_family.fillna("UNKNOWN").value_counts(normalize=True)
    prop_share = float(fam_mix.get("PLAYER_PROP", 0.0))
    if prop_share > 0.20:
        print(f"    {prop_share:.0%} of settled signals are PLAYER PROPS, a family that did not "
              f"exist\n    before 2026-05-13. The retrospective +1.52% was measured on a "
              f"TEAM/MATCH-dominated\n    universe. This forward ledger is NOT a replication of "
              f"that result — it is a\n    measurement of a DIFFERENT market. Report them "
              f"separately or not at all.")


# --------------------------------------------------------------------------- self-test
def self_test() -> int:
    # ---- terminal detection
    assert is_terminal([1.0, 0.0]), "clean binary is terminal"
    assert is_terminal([0.0, 1.0]), "clean binary is terminal"
    assert not is_terminal([0.5, 0.5]), "a live quote is NOT settlement"
    assert not is_terminal([0.97, 0.03]), "a near-certain quote is NOT settlement"
    assert not is_terminal(None), "missing prices are not settlement"
    assert not is_terminal([1.0]), "a one-sided row is not settlement"
    assert not is_terminal([1.0, 1.0]), "prices that do not sum to 1 are not settlement"

    # ---- parsing: the venue ships these as a JSON-ish STRING
    assert parse_outcome_prices('["1", "0"]') == [1.0, 0.0], "string form parses"
    assert parse_outcome_prices('["0.5", "0.5"]') == [0.5, 0.5], "string form parses"
    assert parse_outcome_prices("garbage") is None, "garbage returns None, never raises"
    assert parse_outcome_prices(None) is None, "None returns None"

    # ---- orientation: buying side 1 when side 1 won is a WIN
    assert won_side([0.0, 1.0], 1) is True, "side-1 favourite that resolved 1 is a win"
    assert won_side([0.0, 1.0], 0) is False, "side-0 on a side-1 winner is a loss"
    assert won_side([1.0, 0.0], 0) is True, "side-0 favourite that resolved 1 is a win"
    assert won_side([1.0, 0.0], 5) is None, "out-of-range side is never assumed"

    # ---- ROI: a winner at 0.90 with zero fee returns 1/9; a loser is -100%
    assert abs(roi_at_executed(0.90, 0.0, True) - (0.10 / 0.90)) < 1e-12, "winner ROI"
    assert roi_at_executed(0.90, 0.0, False) == -1.0, "a loser loses the whole stake"
    # the fee is per SHARE and must reduce the winner's return
    assert roi_at_executed(0.90, 0.0045, True) < roi_at_executed(0.90, 0.0, True), "fee bites"
    # a favourite bought AT fair value returns ~0 in expectation
    p = 0.88
    ev = p * roi_at_executed(p, 0.0, True) + (1 - p) * roi_at_executed(p, 0.0, False)
    assert abs(ev) < 1e-12, f"a fairly-priced favourite must have EV 0, got {ev}"

    # ---- family labelling
    assert family_of("baseball_player_home_runs") == "PLAYER_PROP", "props detected"
    assert family_of("baseball_team_full_game_winner") == "TEAM_MATCH", "team detected"
    assert family_of("tennis_match_winner") == "TEAM_MATCH", "match winner is team side"
    assert family_of(None) == "UNKNOWN", "missing type is UNKNOWN, never assumed"

    # ---- clustered bootstrap must be WIDER than an unclustered one on correlated siblings
    rng = np.random.default_rng(3)
    ev_ids = np.repeat(np.arange(40), 5)             # 40 events x 5 perfectly-correlated siblings
    base = rng.normal(0, 1, 40)
    roi = np.repeat(base, 5)
    clo, chi = cluster_boot(roi, ev_ids, n=1500)
    ulo, uhi = cluster_boot(roi, np.arange(len(roi)), n=1500)
    assert (chi - clo) > (uhi - ulo) * 1.5, \
        f"clustered CI must be much wider on correlated siblings: {chi - clo:.3f} vs {uhi - ulo:.3f}"

    # ---- Wilson stays honest where the bootstrap lies: k == n must NOT give a point interval
    lo_w, hi_w = wilson(13, 13)
    assert lo_w < 0.80, f"13/13 wins must leave real downside, got lower bound {lo_w:.3f}"
    assert hi_w <= 1.0, "a proportion cannot exceed 1"
    assert wilson(50, 100)[0] < 0.5 < wilson(50, 100)[1], "symmetric case brackets the estimate"

    # ---- the zero-loss guard must FIRE on an all-winners subset and stay quiet otherwise
    import pandas as pd
    allwin = pd.DataFrame({"won": [True] * 6, "entry_vwap": [0.88] * 6,
                           "event": [f"g{i}" for i in range(6)]})
    assert zero_loss_check(allwin, "fixture-allwin") is True, "must fire when there are no losses"
    mixed = allwin.copy()
    mixed.loc[0, "won"] = False
    assert zero_loss_check(mixed, "fixture-mixed") is False, "must stay quiet once a loss exists"

    # ---- event_key must group siblings of one game together
    a = event_key("aec-mlb-nyy-bos-2026-07-19-player-hits-judge")
    b = event_key("aec-mlb-nyy-bos-2026-07-19-player-hr-judge")
    assert a == b, f"sibling props of one game must share an event key: {a} vs {b}"

    print("self-test: all assertions passed")
    return 0


def main() -> int:
    args = set(sys.argv[1:])
    if "--self-test" in args:
        return self_test()
    if "--settle" in args:
        settle(dry="--dry-run" in args)
        print()
        report()
        return 0
    if "--report" in args:
        report()
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
