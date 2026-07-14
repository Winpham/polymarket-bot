#!/usr/bin/env python3
"""US-VENUE INCENTIVE-PROGRAM FETCHER — the real per-market reward parameters. READ-ONLY.

Pulls the PUBLIC, unauthenticated incentives endpoint

    GET https://api.prod.polymarketexchange.com/v1/incentives?statuses=active

and snapshots each market's actual `rewardPool` / `targetSize` / `discountFactor` / `period` into
`us_incentive_program` (migration 048). This is the ground truth for the liquidity-reward model:
the run brief's "$75k/game" style figures are event-level sums, while the venue pays PER MARKET
and splits PRO-RATA. Measured 2026-07-14: 2,400 active markets, median pool $500, max $14,000.

A pool is a CEILING on total payout, never our income — our share is pool * our_score/total_score,
and the denominator comes from observed near-touch depth (us_mid_tape). Nothing here is realized
money; this table just stops us from inventing the numerator.

Also exposes the reward universe to other sidecars:
    from us_incentives import top_reward_slugs
    top_reward_slugs(n=300)   -> the n richest active reward markets (what us_mid_tape tracks)

DEFAULT-OFF: no committed launch unit. Never trades.

Usage:
    python3 scripts/us_incentives.py --once            # one snapshot
    python3 scripts/us_incentives.py --loop 900        # refresh every 15 min (pools change)
    python3 scripts/us_incentives.py --apply-only
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from datetime import datetime, timezone

import psycopg2
from psycopg2.extras import execute_values

API = os.environ.get("US_INCENTIVES_API",
                     "https://api.prod.polymarketexchange.com/v1/incentives")
PG_DSN = os.environ.get("ARCHIVE_PG_DSN",
                        "postgresql://bot:bot@127.0.0.1:5432/polymarket")
UA = os.environ.get("US_WS_UA",
                    "polymarket-bot-research/1.0 (KYC customer; tue.w.pham@gmail.com)")

_MIG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "migrations", "048_us_incentive_program.sql")


def ensure_schema(con) -> None:
    with open(_MIG) as f:
        sql = f.read()
    with con.cursor() as cur:
        cur.execute(sql)
    con.commit()


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fetch_programs(status="active"):
    """Page the endpoint to exhaustion. Returns flat rows (one per market x timePeriod)."""
    rows, token, pages = [], "", 0
    while pages < 40:                       # bound: 40 x 200 = 8k markets, well past the 2.4k seen
        url = f"{API}?pageSize=200&statuses={status}" + (f"&pageToken={token}" if token else "")
        d = _get(url)
        for pr in d.get("programs") or []:
            slug = pr.get("marketSlug")
            for tp in pr.get("timePeriods") or []:
                rows.append((
                    slug, tp.get("programId"), tp.get("programType"),
                    tp.get("rewardPool"), tp.get("targetSize"), tp.get("discountFactor"),
                    tp.get("period"), tp.get("status"),
                    tp.get("start"), tp.get("end"), tp.get("createdAt"),
                ))
        token = d.get("nextPageToken") or ""
        pages += 1
        if not token:
            break
    return rows


_INSERT = """
    INSERT INTO us_incentive_program
        (us_slug, program_id, program_type, reward_pool, target_size, discount_factor,
         period, status, starts_at, ends_at, created_at_venue)
    VALUES %s
    ON CONFLICT DO NOTHING
"""


def snapshot(con, status="active"):
    rows = fetch_programs(status)
    with con.cursor() as cur:
        execute_values(cur, _INSERT, rows, page_size=500)
        new = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    con.commit()
    pools = [r[3] for r in rows if r[3] is not None]
    pools.sort()
    med = pools[len(pools) // 2] if pools else 0
    print(f"{datetime.now(timezone.utc):%H:%M:%S} incentives: {len(rows)} program rows "
          f"({len({r[0] for r in rows})} markets), {new} new/changed; "
          f"pool sum=${sum(pools):,.0f} median=${med:,.0f} max=${max(pools) if pools else 0:,.0f}",
          flush=True)
    return len(rows), new


def top_reward_slugs(n=300, con=None):
    """The n richest ACTIVE reward markets, ranked by POOL PER MARKET.

    Ranking by raw `reward_pool` would be flatly wrong, and wrong by ~300x. `reward_pool` is a
    PROGRAM-level figure, constant across every market the program covers (verified: it has
    exactly one distinct value per program_id), and the program's pool is split across all of
    them. So the money a resting order can actually reach in a given market is

        pool_per_market = reward_pool / (# markets in that program)

    and that number is brutally uneven:
        worldcup_moneyline_live  $24,700 /    6 markets = $4,117/market   <- worth resting in
        pga_round_1              $15,000 / 1172 markets =    $13/market   <- worth nothing
    A raw-pool ranking would put PGA's $15,000 ABOVE the World Cup's rich, concentrated book and
    point the tape at 1,172 markets paying pennies. Diffuse pools are the trap; concentrated ones
    are the whole opportunity.

    (This is still a CEILING per market — it is then split pro-rata against every other resting
    trader, whose size we observe as near-touch depth in us_mid_tape and whose identity we never
    see. A pool is a schedule, not income.)
    """
    owned = con is None
    con = con or psycopg2.connect(PG_DSN)
    try:
        with con.cursor() as cur:
            cur.execute("""
                WITH latest AS (
                    SELECT DISTINCT ON (us_slug, program_id)
                           us_slug, program_id, reward_pool, status
                      FROM us_incentive_program
                  ORDER BY us_slug, program_id, fetched_at DESC
                ), spread AS (            -- how thin is each program's pool spread?
                    SELECT program_id, COUNT(DISTINCT us_slug) AS n_markets
                      FROM latest WHERE status = 'active'
                  GROUP BY program_id
                )
                SELECT l.us_slug, MAX(l.reward_pool / NULLIF(s.n_markets, 0)) AS per_market
                  FROM latest l
                  JOIN spread s USING (program_id)
                 WHERE l.status = 'active' AND l.reward_pool IS NOT NULL
              GROUP BY l.us_slug
              ORDER BY per_market DESC
                 LIMIT %s
            """, (n,))
            return [r[0] for r in cur.fetchall()]
    finally:
        if owned:
            con.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", type=int, default=0, help="seconds between refreshes")
    ap.add_argument("--status", default="active", help="active | pending | closed")
    ap.add_argument("--apply-only", action="store_true")
    a = ap.parse_args()

    con = psycopg2.connect(PG_DSN)
    ensure_schema(con)
    if a.apply_only:
        con.close()
        print("us_incentive_program schema applied.", flush=True)
        return
    try:
        while True:
            try:
                snapshot(con, a.status)
            except Exception as e:                                  # noqa: BLE001
                con.rollback()
                print(f"  incentives fetch failed: {type(e).__name__}: {str(e)[:90]}", flush=True)
            if not a.loop:
                break
            time.sleep(a.loop)
    finally:
        con.close()


if __name__ == "__main__":
    main()
