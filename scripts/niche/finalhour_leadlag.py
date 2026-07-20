#!/usr/bin/env python3
"""LEAD-LAG PROBE — does the BOOK move before or after ESPN publishes the score?

This is the question that decides whether ANY engineering can help. The trigger fires ~10 minutes
after the book has already re-rated, and 10 minutes is far too large to be a polling or execution
artifact (60s polling is ~1% of it). So the lateness has one of two structural causes, with
OPPOSITE implications:

  (A) OUR TRIGGER FIRES ON THE WRONG STATE. ESPN publishes promptly, the book follows, but
      "near-decided" (1 set + 3-game lead) simply OCCURS later than the window the edge lives in.
      => Fixable, and not with faster code: fire on an earlier game state.

  (B) THE BOOK ALREADY KNOWS. Price moves BEFORE the feed publishes, because someone is watching
      the match itself. => Unfixable at any speed. No language, colocation or feed upgrade recovers
      information that is in the price before the source emits it.

METHOD. Poll ESPN fast (default 5s) and timestamp each LINESCORE CHANGE to that resolution. Then
pull the us_mid_tape book path (~1s) around each change and locate when the price actually moved.
  price moves BEFORE the score appears  -> (B), the book leads the feed
  price moves AFTER  the score appears  -> (A), we are just triggering too late

It also measures ESPN'S OWN granularity: if changes only ever surface on ~60s boundaries, the feed
itself is the bottleneck and polling faster buys nothing — worth knowing before optimising anything.

READ-ONLY. Writes nothing. Bounded by --minutes.

Usage:  ./finalhour_leadlag.py --minutes 20 --interval 5
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from collections import defaultdict

import psycopg2

PG_DSN = os.environ.get("ARCHIVE_PG_DSN", "postgresql://bot:bot@127.0.0.1:5432/polymarket")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}


def poll():
    """{comp_id: (names, linescores, tournament)} for in-progress matches."""
    out = {}
    for tour in ("atp", "wta"):
        url = f"https://site.api.espn.com/apis/site/v2/sports/tennis/{tour}/scoreboard"
        try:
            d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20))
        except Exception:
            continue
        for ev in d.get("events", []):
            for g in ev.get("groupings", []):
                for c in g.get("competitions", []):
                    if c.get("status", {}).get("type", {}).get("state") != "in":
                        continue
                    cs = c.get("competitors", [])
                    if len(cs) != 2:
                        continue
                    cid = str(c.get("id"))
                    if cid in out:
                        continue
                    names = [x.get("athlete", {}).get("displayName", "") for x in cs]
                    ls = [[float(z.get("value", 0)) for z in x.get("linescores", [])] for x in cs]
                    if ls[0] and ls[1]:
                        out[cid] = (names, ls, ev.get("name"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=int, default=20)
    ap.add_argument("--interval", type=float, default=5.0)
    a = ap.parse_args()

    print(f"probing ESPN every {a.interval}s for {a.minutes} min ...")
    prev, changes = {}, []
    t_end = time.time() + a.minutes * 60
    n_polls = 0
    while time.time() < t_end:
        t = time.time()
        cur = poll()
        n_polls += 1
        for cid, (names, ls, tour) in cur.items():
            if cid in prev and prev[cid][1] != ls:
                changes.append({"t": t, "cid": cid, "names": names,
                                "before": prev[cid][1], "after": ls, "tour": tour})
                print(f"  [{time.strftime('%H:%M:%S', time.gmtime(t))}] {cid} "
                      f"{prev[cid][1]} -> {ls}")
        prev = cur
        time.sleep(max(0.0, a.interval - (time.time() - t)))

    print(f"\npolls: {n_polls}   linescore changes captured: {len(changes)}")
    if not changes:
        print("no changes observed — run during a busier window")
        return

    # ESPN's own granularity: gaps between successive changes on the SAME match.
    per = defaultdict(list)
    for c in changes:
        per[c["cid"]].append(c["t"])
    gaps = [round(b - a_, 1) for ts in per.values() for a_, b in zip(ts, ts[1:])]
    if gaps:
        gaps.sort()
        print(f"gaps between successive changes (same match): min {gaps[0]}s  "
              f"median {gaps[len(gaps)//2]}s  max {gaps[-1]}s")
        print("  (if these cluster on ~60s multiples, ESPN itself is the bottleneck)")

    # Lead-lag against the book.
    con = psycopg2.connect(PG_DSN)
    cur = con.cursor()
    cur.execute("""SELECT us_slug, espn_comp_id FROM finalhour_feed_tape
                   WHERE us_slug IS NOT NULL GROUP BY 1,2;""")
    slug_of = {cid: slug for slug, cid in cur.fetchall()}

    print("\nLEAD-LAG around each score change (book path +/-120s):")
    lead = lag = flat = 0
    for c in changes:
        slug = slug_of.get(c["cid"])
        if not slug:
            continue
        cur.execute("""SELECT EXTRACT(EPOCH FROM recv_at), best_ask FROM us_mid_tape
                       WHERE us_slug=%s AND best_ask IS NOT NULL
                         AND recv_at BETWEEN to_timestamp(%s) AND to_timestamp(%s)
                       ORDER BY recv_at;""", (slug, c["t"] - 120, c["t"] + 120))
        path = cur.fetchall()
        if len(path) < 4:
            continue
        base = float(path[0][1])
        final = float(path[-1][1])
        if abs(final - base) < 0.015:
            flat += 1
            continue
        # when did the book cover HALF of its total move?
        half = base + (final - base) / 2.0
        t_half = next((float(ts) for ts, px in path
                       if (float(px) >= half if final > base else float(px) <= half)), None)
        if t_half is None:
            continue
        d = t_half - c["t"]
        tag = "BOOK LEADS" if d < -2 else ("book lags" if d > 2 else "~simultaneous")
        lead += d < -2
        lag += d > 2
        print(f"  {c['cid']}  move {base:.2f}->{final:.2f}  half-move at {d:+.0f}s vs score  [{tag}]")

    print(f"\n  book leads feed: {lead}   book lags feed: {lag}   no material move: {flat}")
    print("  BOOK LEADS  => (B) unfixable at any speed; the price knows before the feed emits.")
    print("  book lags   => (A) the feed is usable; we are triggering on too late a game state.")


if __name__ == "__main__":
    main()
