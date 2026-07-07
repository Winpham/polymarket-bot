#!/usr/bin/env python3
"""Item 9 (offline) — backfill signal_price_trajectory from clob_price_tape.

Closes the GAP-2 trajectory-coarseness hole WITHOUT any live path: for each
favorite/dense-tracked signal, insert trajectory points at the grid using the
best_ask recorded in `clob_price_tape`, anchored on the signal's `first_detected_at`
(the sharp's fire clock). Uses the existing insert_trajectory_point shape
(migration 034): (signal_id, secs_after_fire, mid, ask, n_backers).

The dense_capture task samples at ~45s anchored on signal-fire and caps 40/tick,
leaving the 1–120s window empty. The tape holds every top-of-book move at 1 Hz, so
this backfill fills the grid the live sampler could never resolve — unconditionally,
no FK gymnastics, no strict-byte-identity risk.

Read tape + signals from Postgres; write trajectory points. --self-test is offline.
"""
import argparse
import json
import subprocess
import sys
from bisect import bisect_right

PG_CONTAINER = "polymarket-bot-postgres-1"
GRID = [1, 5, 15, 30, 60, 120, 300, 900]
TOL_S = 30
DEFAULT_STRATEGIES = ("favorite", "strict", "elite_fresh_fav")


def psql(sql, want_rows=True):
    out = subprocess.run(
        ["docker", "exec", PG_CONTAINER, "psql", "-U", "bot", "-d", "polymarket",
         "-tAF", "\x1f", "-v", "ON_ERROR_STOP=1", "-c", sql],
        capture_output=True, text=True, timeout=300)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip())
    return out.stdout if want_rows else None


def nearest_le(ticks, target):
    """last (t, bid, ask) with t <= target within TOL_S. ticks: sorted [(t,bid,ask)]."""
    if not ticks:
        return None
    times = [t for t, _, _ in ticks]
    i = bisect_right(times, target) - 1
    if i < 0:
        return None
    t, bid, ask = ticks[i]
    if target - t > TOL_S:
        return None
    return bid, ask


def grid_points(fire_ts, ticks):
    """[(secs, mid, ask)] for grid points that have a tape tick within TOL."""
    out = []
    for s in GRID:
        r = nearest_le(ticks, fire_ts + s)
        if r is None:
            continue
        bid, ask = r
        mid = (bid + ask) / 2 if (bid is not None and ask is not None) else ask
        out.append((s, mid, ask))
    return out


def backfill(strategies, limit, dry_run):
    strat_list = ",".join(f"'{s}'" for s in strategies)
    sigs = [ln.split("\x1f") for ln in psql(
        "SELECT id, condition_id, outcome_index, extract(epoch from first_detected_at), "
        "COALESCE(n_backers,0) FROM consensus_signals "
        f"WHERE strategy IN ({strat_list}) AND condition_id IS NOT NULL "
        f"ORDER BY first_detected_at DESC LIMIT {int(limit)}"
    ).splitlines() if ln.strip()]
    print(f"[backfill] {len(sigs)} signals", file=sys.stderr)

    inserted = 0
    filled_signals = 0
    for sid, cond, oidx, fire_s, nb in sigs:
        fire_ts = float(fire_s)
        oidx = int(oidx)
        ticks_raw = psql(
            "SELECT extract(epoch from COALESCE(exch_ts,recv_at)), best_bid, best_ask "
            "FROM clob_price_tape "
            f"WHERE condition_id='{cond}' AND outcome_index={oidx} "
            f"AND COALESCE(exch_ts,recv_at) BETWEEN to_timestamp({fire_ts-60}) "
            f"AND to_timestamp({fire_ts+960}) ORDER BY 1")
        ticks = []
        for ln in ticks_raw.splitlines():
            if not ln.strip():
                continue
            t, bid, ask = ln.split("\x1f")
            ticks.append((float(t), float(bid) if bid else None, float(ask) if ask else None))
        pts = grid_points(fire_ts, ticks)
        if pts:
            filled_signals += 1
        for secs, mid, ask in pts:
            if not dry_run:
                psql("INSERT INTO signal_price_trajectory "
                     "(signal_id, secs_after_fire, mid, ask, n_backers) "
                     f"VALUES ({int(sid)}, {secs}, "
                     f"{'NULL' if mid is None else mid}, {'NULL' if ask is None else ask}, {int(nb)})",
                     want_rows=False)
            inserted += 1
    print(f"[backfill] {filled_signals}/{len(sigs)} signals had tape; "
          f"{inserted} trajectory points {'(dry-run)' if dry_run else 'inserted'}", file=sys.stderr)
    return {"signals": len(sigs), "filled": filled_signals, "points": inserted}


def self_test():
    # synthetic tape: ask rises from 0.60; fire at t0. grid points recover asks.
    t0 = 1_000_000.0
    ticks = [(t0 + s, 0.59 + 0.0001 * s, 0.60 + 0.0001 * s) for s in range(-10, 950, 2)]
    pts = grid_points(t0, ticks)
    got = {s: round(ask, 4) for s, _mid, ask in pts}
    assert got[1] == round(0.60 + 0.0001 * 1, 4) or abs(got[1] - 0.6001) < 0.001, got
    assert got[900] == round(0.60 + 0.0001 * 900, 4), got.get(900)
    assert len(pts) == len(GRID), f"expected all grid points, got {len(pts)}"
    # a tape gap: last tick at t0+5 covers grid points up to +TOL_S (step function),
    # so {1,5,15,30} are filled and 60+ (gap >30s) are dropped.
    sparse = [(t0 + s, 0.59, 0.60) for s in (-5, 0, 5)]  # only near fire
    sp = grid_points(t0, sparse)
    assert {s for s, _, _ in sp} == {1, 5, 15, 30}, {s for s, _, _ in sp}
    print("SELF-TEST PASS: grid recovers asks anchored on fire_ts; "
          "step-function fill within TOL; later gaps → dropped points")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--strategies", nargs="*", default=list(DEFAULT_STRATEGIES))
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return
    print(json.dumps(backfill(args.strategies, args.limit, args.dry_run)))


if __name__ == "__main__":
    main()
