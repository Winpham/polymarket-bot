#!/usr/bin/env python3
"""FINAL-HOUR FEED RECORDER — pairs live ESPN game state with the live US book. READ-ONLY.

Records EVERY in-progress ATP/WTA match on every poll, not only the ones that would fire. See
migrations/049_finalhour_feed_tape.sql for why (latency measurement, a free placebo arm, and
trigger re-specification without resetting the pre-registered clock).

It NEVER writes to finalhour_paper_signals and has no order path. It records what the FROZEN
trigger WOULD have done (`would_fire`, `fire_block`) without doing it.

The trigger verdict comes from finalhour_forward.match_state -- the same function the harness
uses -- so the recorder can never drift from the shipped trigger definition.

Usage:
    ./finalhour_recorder.py --once           # single poll (what launchd runs)
    ./finalhour_recorder.py --loop 60        # poll every 60s until killed
    ./finalhour_recorder.py --apply-only     # ensure schema, exit
    ./finalhour_recorder.py --status         # what has been captured so far
"""
from __future__ import annotations

import argparse
import datetime
import importlib.util
import json
import os
import sys
import time
import urllib.request

import psycopg2

PG_DSN = os.environ.get("ARCHIVE_PG_DSN", "postgresql://bot:bot@127.0.0.1:5432/polymarket")
HERE = os.path.dirname(os.path.abspath(__file__))
BAND_LO, BAND_HI = 0.65, 0.92          # frozen in PREREG v2 §5; unchanged in v3
QUOTE_FRESH_S = 600                     # the trigger's 10-minute freshness requirement

# Reuse the harness's own trigger logic rather than reimplementing it.
_spec = importlib.util.spec_from_file_location("fh", os.path.join(HERE, "finalhour_forward.py"))
fh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fh)


def espn_all_live():
    """Every IN-PROGRESS match with linescores, with the frozen trigger's verdict attached.

    DEDUPED BY espn_comp_id, ATP FIRST. ESPN cross-lists some matches on both scoreboards --
    observed 2026-07-19: comp 178657 (Darderi v Rublev, Nordea Open) appeared under BOTH atp and
    wta. That is not merely a double count: `is_bo5` is derived from WHICH feed the row came from,
    so a Grand Slam men's match seen via the wta endpoint would be scored best-of-3 and evaluated
    against the wrong near-decided rule. Iterating atp first and keeping the first sighting gives
    the correct format flag.
    """
    out, seen = [], set()
    for tour in ("atp", "wta"):
        url = f"https://site.api.espn.com/apis/site/v2/sports/tennis/{tour}/scoreboard"
        t0 = time.time()
        try:
            d = json.load(urllib.request.urlopen(url, timeout=30))
        except Exception as e:
            print(f"  espn {tour} fetch fail: {e}", file=sys.stderr)
            continue
        fetch_ms = (time.time() - t0) * 1000.0
        for ev in d.get("events", []):
            is_bo5 = (tour == "atp") and bool(ev.get("major"))
            for g in ev.get("groupings", []):
                for c in g.get("competitions", []):
                    if c.get("status", {}).get("type", {}).get("state") != "in":
                        continue
                    cs = c.get("competitors", [])
                    if len(cs) != 2:
                        continue
                    names = [x.get("athlete", {}).get("displayName", "") for x in cs]
                    ls = [[float(z.get("value", 0)) for z in x.get("linescores", [])] for x in cs]
                    if not ls[0] or not ls[1] or not all(names):
                        continue
                    cid = str(c.get("id"))
                    if cid in seen:          # cross-listed on the other scoreboard; atp wins
                        continue
                    seen.add(cid)
                    nd, lead, reason = fh.match_state(ls[0], ls[1], is_bo5)
                    out.append({
                        "feed_src": f"espn_{tour}", "comp_id": cid,
                        "tournament": ev.get("name"), "is_bo5": is_bo5, "fetch_ms": fetch_ms,
                        "names": names, "ls": ls,
                        "period": (c.get("status") or {}).get("period"),
                        "near": nd, "leader": names[lead], "state": reason,
                    })
    return out


def latest_quotes(con):
    """Most recent quote per tennis slug. Deliberately NOT filtered on freshness -- staleness is a
    measurement (quote_age_s), not a reason to drop the row."""
    cur = con.cursor()
    cur.execute("""
        SELECT DISTINCT ON (us_slug) us_slug, best_bid, best_ask, mid, spread,
               best_ask_qty, ask_qty_1c, recv_at
        FROM us_mid_tape
        WHERE (us_slug LIKE 'aec-atp-%' OR us_slug LIKE 'aec-wta-%')
              AND state='MARKET_STATE_OPEN' AND recv_at > now() - interval '2 hours'
        ORDER BY us_slug, recv_at DESC;""")
    return {r[0]: r for r in cur.fetchall()}


def poll_once(con, yes_map):
    matches = espn_all_live()
    if not matches:
        print("  no in-progress matches")
        return 0
    quotes = latest_quotes(con)
    cur = con.cursor()
    n = fired = 0
    for m in matches:
        # DATE-BOUND, both-players-distinct matching. Loose matching mapped live matches onto
        # months-old markets with the wrong opponent (see match_market docstring).
        today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        slug, yes_player = fh.match_market(m["names"], yes_map, on_date=today)
        leader_is_yes = (len(fh.name_toks(yes_player) & fh.name_toks(m["leader"])) >= 1
                         if yes_player else None)

        q = quotes.get(slug) if slug else None
        bid = ask = mid = spr = aq = a1c = recv = age = None
        if q:
            _, bid, ask, mid, spr, aq, a1c, recv = q
            cur.execute("SELECT EXTRACT(EPOCH FROM (now() - %s));", (recv,))
            age = float(cur.fetchone()[0])

        # What the FROZEN trigger would do -- evaluated, never acted on.
        block = None
        if not m["near"]:
            block = "not_near"
        elif slug is None:
            block = "no_slug"
        elif q is None or ask is None:
            block = "no_quote"
        elif age is not None and age > QUOTE_FRESH_S:
            block = "stale_quote"
        elif not leader_is_yes:
            block = "orientation"
        elif not (BAND_LO <= float(ask) <= BAND_HI):
            block = "band"
        would = block is None
        fired += would

        cur.execute("""
            INSERT INTO finalhour_feed_tape
              (fetch_ms, feed_src, espn_comp_id, tournament, is_bo5, player_a, player_b,
               linescore_a, linescore_b, period, near_decided, leader_name, feed_state,
               us_slug, yes_player, leader_is_yes, best_bid, best_ask, mid, spread,
               best_ask_qty, ask_qty_1c, quote_recv_at, quote_age_s, would_fire, fire_block)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);""",
            (m["fetch_ms"], m["feed_src"], m["comp_id"], m["tournament"], m["is_bo5"],
             m["names"][0], m["names"][1], json.dumps(m["ls"][0]), json.dumps(m["ls"][1]),
             m["period"], m["near"], m["leader"], m["state"], slug, yes_player, leader_is_yes,
             bid, ask, mid, spr, aq, a1c, recv, age, would, block))
        n += 1
    con.commit()
    print(f"  recorded {n} live matches ({fired} would_fire, "
          f"{sum(1 for m in matches if m['near'])} near-decided)")
    return n


def status(con):
    cur = con.cursor()
    cur.execute("""SELECT count(*), count(DISTINCT espn_comp_id), min(poll_ts), max(poll_ts),
                          count(*) FILTER (WHERE near_decided), count(*) FILTER (WHERE would_fire)
                   FROM finalhour_feed_tape;""")
    r = cur.fetchone()
    print(f"feed tape: {r[0]} rows, {r[1]} distinct matches")
    print(f"  window: {r[2]} .. {r[3]}")
    print(f"  near-decided rows: {r[4]}   would_fire rows: {r[5]}")
    cur.execute("""SELECT coalesce(fire_block,'(would fire)'), count(*) FROM finalhour_feed_tape
                   GROUP BY 1 ORDER BY 2 DESC;""")
    print("  fire blockers:")
    for k, v in cur.fetchall():
        print(f"    {k:14s} {v}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", type=int, default=0, help="seconds between polls")
    ap.add_argument("--apply-only", action="store_true")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()

    con = psycopg2.connect(PG_DSN)
    with open(os.path.join(HERE, "..", "..", "migrations", "049_finalhour_feed_tape.sql")) as f:
        con.cursor().execute(f.read())
    con.commit()
    if a.apply_only:
        print("schema applied")
        return
    if a.status:
        status(con)
        return

    yes_map = fh.load_us_yes_players()
    print(f"orientation loaded for {len(yes_map)} tennis markets")
    if a.loop:
        while True:
            poll_once(con, yes_map)
            time.sleep(a.loop)
    else:
        poll_once(con, yes_map)


if __name__ == "__main__":
    main()
