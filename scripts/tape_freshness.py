#!/usr/bin/env python3
"""TAPE FRESHNESS — is the forward tape actually accruing? Shout if not.

WHY THIS EXISTS (2026-07-14, and it is not hypothetical)
-------------------------------------------------------
Postgres was DOWN for ~2 hours. The host disk hit 96%, the Docker VM's filesystem remounted
read-only, and the database died. The whole time, `docker ps` reported the container:

        polymarket-bot-postgres-1   Up 19 hours (healthy)

The healthcheck LIED, the bot could not write, and NOTHING NOTICED. The at-fire US quote
capture had gone live that same day -- and it CANNOT BE BACKFILLED. Every minute of that
outage is a minute of forward evidence that can never be recovered.

This is the same lesson `archive-watchdog.sh` was written for ("silence read as health"),
on a different surface. That watchdog asks "is the sealed archive fresh?". Nothing asked
"is the LIVE TAPE still moving?" -- so nobody knew it had stopped.

THE POINT, AND IT IS A GATE-A POINT
-----------------------------------
GATE A's entire premise is "the tapes accrue; forward data is now cheap." A 30-day forward
window with a silent multi-hour hole in it IS NOT A FORWARD WINDOW -- and the hole is
invisible after the fact, because a gap in an append-only tape looks exactly like a quiet
market. The brief's Hard Rule 2 is "fail closed on stale data." It was never implemented.
This implements it.

WHAT IT DOES NOT DO
-------------------
It does not restart anything, it does not delete anything, and it does not trade. It asks
one question per tape and reports. `--halt-on-stale` additionally writes the executor's
halt latch, so a stale tape stops the arm rather than trading blind (Hard Rule 2). That
flag is OFF by default: today there is no executor to halt.

Usage:
    python3 scripts/tape_freshness.py                # report; exit 1 if anything is stale
    python3 scripts/tape_freshness.py --json         # machine-readable
    python3 scripts/tape_freshness.py --halt-on-stale  # + latch us_exec_halts (when it exists)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

import psycopg2

PG_DSN = os.environ.get("ARCHIVE_PG_DSN", "postgresql://bot:bot@127.0.0.1:5432/polymarket")

# (table, timestamp column, max staleness in MINUTES, why it matters)
#
# The thresholds are deliberately LOOSE -- generous multiples of each writer's real cadence.
# A watchdog that cries wolf gets disarmed by its owner, and a disarmed watchdog is exactly
# the state we were in this morning. These catch an OUTAGE, not a slow hour.
TAPES = [
    ("us_quotes", "ts", 30,
     "the at-fire US ask. Written by a 120s launchd sweep. CANNOT BE BACKFILLED -- this is "
     "the basis GATE A scores on."),
    ("clob_price_tape", "recv_at", 30,
     "the intl live tape. Self-prunes at 72h, so a stall is history being destroyed on a clock."),
    ("consensus_signals", "first_detected_at", 360,
     "the signal ledger itself. 6h, because signals are genuinely bursty (0 on a quiet slate)."),
    ("trader_fills", "ts", 120,
     "the copy-trading fill tape -- the substrate every arm is derived from."),
]


def check(cur, table, col, max_min):
    try:
        cur.execute(f"SELECT count(*), max({col}) FROM {table}")
        n, newest = cur.fetchone()
    except Exception as e:                       # a missing table is a real finding, not a crash
        return {"table": table, "ok": False, "error": str(e).strip()[:120], "age_min": None}
    if newest is None:
        return {"table": table, "ok": False, "error": "EMPTY", "age_min": None, "rows": n}
    age = (dt.datetime.now(dt.timezone.utc) - newest).total_seconds() / 60.0
    return {"table": table, "ok": age <= max_min, "age_min": round(age, 1),
            "max_min": max_min, "rows": n, "newest": newest.isoformat()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--halt-on-stale", action="store_true",
                    help="latch us_exec_halts (Hard Rule 2). No-op until the executor exists.")
    a = ap.parse_args()

    try:
        con = psycopg2.connect(PG_DSN, connect_timeout=10)
    except Exception as e:
        # THE CASE THAT ACTUALLY HAPPENED. The DB is unreachable and `docker ps` says "healthy".
        out = {"ok": False, "fatal": "DATABASE UNREACHABLE", "detail": str(e).strip()[:200]}
        print(json.dumps(out) if a.json else
              f"STALE/FATAL: DATABASE UNREACHABLE -- {out['detail']}\n"
              f"  (this is exactly the 2026-07-14 outage: docker ps reported 'healthy' throughout)")
        sys.exit(1)

    cur = con.cursor()
    results = [check(cur, t, c, m) for t, c, m, _ in TAPES]
    why = {t: w for t, _, _, w in TAPES}
    stale = [r for r in results if not r["ok"]]

    if a.json:
        print(json.dumps({"ok": not stale, "tapes": results}, indent=2))
    else:
        for r in results:
            if r["ok"]:
                print(f"  OK    {r['table']:20} {r['age_min']:>6.1f} min old  ({r['rows']:,} rows)")
            elif r.get("error"):
                print(f"  STALE {r['table']:20} {r['error']}")
            else:
                print(f"  STALE {r['table']:20} {r['age_min']:>6.1f} min old "
                      f"(limit {r['max_min']})  <-- {why[r['table']]}")

    if stale and a.halt_on_stale:
        try:
            cur.execute("""INSERT INTO us_exec_halts (venue, arm, reason, detail, halted_by)
                           VALUES ('us','__master__','DataStale',%s,'auto:tape_freshness')
                           ON CONFLICT DO NOTHING""",
                        (json.dumps({"stale": [r["table"] for r in stale]}),))
            con.commit()
            print("\n  HALTED the US arm (DataStale). A bot that cannot see the market must not trade.")
        except Exception as e:
            con.rollback()
            print(f"\n  (us_exec_halts not present yet -- no executor to halt: {str(e).strip()[:60]})")

    con.close()
    sys.exit(1 if stale else 0)


if __name__ == "__main__":
    main()
