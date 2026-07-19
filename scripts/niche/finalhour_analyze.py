#!/usr/bin/env python3
"""FINAL-HOUR FEED TAPE ANALYSIS — turns the paired (game-state x book) series into the numbers
PREREG v3 actually gates on. READ-ONLY; computes nothing into any ledger.

Four questions, in the order they can kill the arm:

  1. FUNNEL -- of every near-decided observation, how many survive each gate? This yields the FIRE
     RATE, which sets the calendar. v3 needs >=250 gate-eligible events; at an unmeasured fire rate
     that is somewhere between weeks and never, and the funnel is the only thing that tells us which.

  2. BAND OCCUPANCY AT TRIGGER -- the existential question. The edge was measured in [0.65,0.92],
     but if 'near-decided' states systematically price ABOVE 0.92 then the trigger and the band are
     MUTUALLY EXCLUSIVE and the test can never accrue. That is not a tuning problem, it is a
     falsification: the state we can detect is not the state where the edge lives.

  3. LATENESS -- for each match, the price trajectory around the FIRST near-decided poll. If the
     book has already re-rated before ESPN publishes the state, we are late BY CONSTRUCTION and
     there is no trade at any size. lambda is ~0 by -45min, so this is first-order.

  4. PLACEBO -- non-near-decided observations in the same band, carried through the same cost path.
     A cost-model error hits both arms equally, so only the DIFFERENCE is evidence.

Usage:  ./finalhour_analyze.py [--hours N]
"""
from __future__ import annotations

import argparse
import os

import psycopg2

PG_DSN = os.environ.get("ARCHIVE_PG_DSN", "postgresql://bot:bot@127.0.0.1:5432/polymarket")
BAND_LO, BAND_HI = 0.65, 0.92


def q(cur, sql, args=()):
    cur.execute(sql, args)
    return cur.fetchall()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=0, help="restrict to the last N hours (0 = all)")
    a = ap.parse_args()
    where = "WHERE poll_ts > now() - interval '%d hours'" % a.hours if a.hours else ""

    con = psycopg2.connect(PG_DSN)
    cur = con.cursor()

    span = q(cur, f"SELECT min(poll_ts), max(poll_ts), count(*), count(DISTINCT espn_comp_id) "
                  f"FROM finalhour_feed_tape {where};")[0]
    if not span[2]:
        print("feed tape is empty")
        return
    hrs = (span[1] - span[0]).total_seconds() / 3600.0
    print(f"window {span[0]:%Y-%m-%d %H:%M} .. {span[1]:%H:%M}Z  ({hrs:.1f}h)  "
          f"{span[2]} rows, {span[3]} matches\n")

    # ---- 1. FUNNEL (per distinct match, not per row: rows repeat every poll) ----
    print("1. FIRE FUNNEL  (distinct matches reaching each stage)")
    rows = q(cur, f"""
        SELECT count(DISTINCT espn_comp_id) FILTER (WHERE TRUE),
               count(DISTINCT espn_comp_id) FILTER (WHERE near_decided),
               count(DISTINCT espn_comp_id) FILTER (WHERE near_decided AND us_slug IS NOT NULL),
               count(DISTINCT espn_comp_id) FILTER (WHERE near_decided AND leader_is_yes),
               count(DISTINCT espn_comp_id) FILTER (WHERE near_decided AND leader_is_yes
                                                     AND best_ask IS NOT NULL),
               count(DISTINCT espn_comp_id) FILTER (WHERE would_fire)
        FROM finalhour_feed_tape {where};""")[0]
    labels = ["live matches seen", "reached near-decided", "  ...mapped to a US market",
              "  ...leader IS the long side", "  ...had a live quote", "  ...WOULD FIRE (in band)"]
    for lab, v in zip(labels, rows):
        print(f"   {lab:34s} {v}")
    if hrs > 0:
        print(f"   => fire rate: {rows[5]/hrs:.2f} / hour  ({rows[5]/hrs*24:.1f} / day)")
        if rows[5]:
            print(f"   => 250 events at this rate: {250/(rows[5]/hrs*24):.0f} days")
        else:
            print("   => 250 events at this rate: NEVER (no fires observed)")

    # ---- 2. BAND OCCUPANCY AT TRIGGER ----
    print("\n2. WHERE THE BOOK PRICES A NEAR-DECIDED FAVOURITE  (leader IS long side, quote present)")
    r = q(cur, f"""
        SELECT count(*),
               count(*) FILTER (WHERE best_ask > %s),
               count(*) FILTER (WHERE best_ask BETWEEN %s AND %s),
               count(*) FILTER (WHERE best_ask < %s),
               round(min(best_ask)::numeric,3),
               round((percentile_cont(0.5) WITHIN GROUP (ORDER BY best_ask))::numeric,3),
               round(max(best_ask)::numeric,3)
        FROM finalhour_feed_tape {where or 'WHERE TRUE'}
          AND near_decided AND leader_is_yes AND best_ask IS NOT NULL;""",
          (BAND_HI, BAND_LO, BAND_HI, BAND_LO))[0]
    n = r[0]
    if not n:
        print("   no observations yet")
    else:
        print(f"   observations: {n}   ask min/median/max: {r[4]} / {r[5]} / {r[6]}")
        print(f"     ABOVE {BAND_HI} (already re-rated): {r[1]}  ({100*r[1]/n:.0f}%)")
        print(f"     IN BAND [{BAND_LO},{BAND_HI}]        : {r[2]}  ({100*r[2]/n:.0f}%)")
        print(f"     BELOW {BAND_LO}                     : {r[3]}  ({100*r[3]/n:.0f}%)")
        if r[2] == 0 and n >= 20:
            print("   !! NO near-decided observation has EVER been in band. If this holds, the")
            print("      trigger and the band are MUTUALLY EXCLUSIVE and the arm is falsified as")
            print("      specified -- the detectable state is not the state where the edge lives.")

    # ---- 3. LATENESS: price around the first near-decided sighting ----
    print("\n3. LATENESS  (ask at each match's FIRST near-decided poll vs its own earlier prices)")
    lat = q(cur, f"""
        WITH firsts AS (
          SELECT espn_comp_id, min(poll_ts) AS t0
          FROM finalhour_feed_tape {where or 'WHERE TRUE'} AND near_decided AND leader_is_yes
          GROUP BY 1)
        SELECT f.espn_comp_id,
               (SELECT round(best_ask::numeric,3) FROM finalhour_feed_tape x
                 WHERE x.espn_comp_id=f.espn_comp_id AND x.poll_ts=f.t0
                   AND x.best_ask IS NOT NULL LIMIT 1) AS ask_at_trigger,
               (SELECT round(best_ask::numeric,3) FROM finalhour_feed_tape x
                 WHERE x.espn_comp_id=f.espn_comp_id AND x.poll_ts < f.t0 - interval '10 minutes'
                   AND x.best_ask IS NOT NULL ORDER BY x.poll_ts DESC LIMIT 1) AS ask_10m_before
        FROM firsts f ORDER BY 1;""")
    shown = 0
    for cid, at, before in lat:
        if at is None or before is None:
            continue
        shown += 1
        print(f"   match {cid}: ask 10m before = {before}   at trigger = {at}   "
              f"move = {float(at)-float(before):+.3f}")
    if not shown:
        print("   (not enough paired history yet — needs matches observed >10 min pre-trigger)")
    else:
        print("   A large POSITIVE move means the book re-rated BEFORE we could act: we are late.")

    # ---- 4. PLACEBO ----
    print("\n4. PLACEBO ARM  (NOT near-decided, same band, same book)")
    p = q(cur, f"""
        SELECT count(*), count(DISTINCT espn_comp_id)
        FROM finalhour_feed_tape {where or 'WHERE TRUE'}
          AND NOT near_decided AND leader_is_yes
          AND best_ask BETWEEN %s AND %s;""", (BAND_LO, BAND_HI))[0]
    print(f"   in-band non-triggered observations: {p[0]} across {p[1]} matches")
    print("   (these settle alongside the live arm; a cost-model error moves BOTH, so only the")
    print("    difference is evidence — PREREG v3 §6.1)")


if __name__ == "__main__":
    main()
