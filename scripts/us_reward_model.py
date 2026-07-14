#!/usr/bin/env python3
"""LIQUIDITY-REWARD CAPTURE MODEL — what the subsidy ACTUALLY pays us. READ-ONLY.

THE ONLY REASON THE KILLED MAKING THESIS IS REOPENED
----------------------------------------------------
On intl, a resting quote earned the spread and paid adverse selection, and the arithmetic was
$0-falsified at 13x hazard/reward. US adds an object intl never had: a FILL-INDEPENDENT subsidy.
The Liquidity Incentive Program pays for resting near the touch WHETHER OR NOT YOU FILL. If the
per-second reward exceeds the expected adverse-selection loss on the fraction that does fill,
making is positive even against sharp flow. This module prices that.

THE VENUE'S ACTUAL SCORING RULE (docs.polymarket.us/incentives/liquidity, verified)
----------------------------------------------------------------------------------
    score = discountFactor ^ (ticks from best price) * size
    - snapshotted EVERY SECOND; bid side and ask side each normalized to 1.0 per snapshot
    - pool split PRO-RATA by score share across the period; one-sided resting is eligible
    - targetSize is a QUALIFICATION THRESHOLD (accumulate from the best price outward until it is
      met; orders beyond it score zero), not a per-trader cap

TWO MEASURED FACTS MAKE THIS BRUTAL, AND THEY ARE THE HEART OF THE VERDICT
-------------------------------------------------------------------------
1. The tick is 0.001 venue-wide (3,998/3,999 markets) but 93.2% of real quotes sit on WHOLE CENTS.
   So an order one CENT off the touch is TEN TICKS away and scores df^10 = 0.3^10 = 0.000006 --
   ZERO. THE SUBSIDY IS ONLY PAID AT THE TOUCH. You cannot collect it from a safe distance: the
   place that pays the reward is exactly the place that gets picked off. The subsidy does not buy
   you a hiding spot; it pays you to stand in the line of fire.
2. Because scoring is exponential in ticks, a competitor can outbid you by ONE TICK (0.1c) and cut
   your score to 30% of theirs. Reward share is not defensible for a tenth of a cent.

Consequently the score at the touch dominates everything behind it, and our share collapses to a
queue-share problem:

    our_share(side) ~= our_size / (our_size + size_at_best_price)

which we can MEASURE, because us_mid_tape records best_bid_qty / best_ask_qty for the reward
universe. This is the pro-rata DENOMINATOR that a bare pool figure hides.

THE PAYOUT RATE (and the one honest uncertainty we cannot close without a key)
-----------------------------------------------------------------------------
    pool_per_market_per_second = reward_pool / (n_markets_in_program * period_seconds)
    reward_rate($/s)           = pool_per_market_per_second * (share_bid + share_ask) / 2

`period_seconds` is the program's published window. For 'live' programs the window spans the whole
tournament (e.g. World Cup: 288h), and we CANNOT observe from outside whether score accrues across
that entire window or only during live play. That is a ~7x swing in the payout rate, so we report
BOTH bounds and never quietly pick the flattering one:
    WINDOW  (conservative): score accrues every second the market is open across the full window.
    LIVE-ONLY (optimistic): score accrues only during live game-time (assumed LIVE_HOURS/game).
Closing this needs the authenticated GET /v1/incentives/earnings for our own account -- i.e. Tue's
API key. Until then it stays a stated bound, not a number we pretend to know.

Nothing here is realized income. A pool is a published schedule; our share is an estimate against
competitors whose identity we never see and whose size we only observe.

Usage:
    python3 scripts/us_reward_model.py --sizes 250,1000,5000
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys

import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import us_fees  # noqa: E402

PG_DSN = os.environ.get("ARCHIVE_PG_DSN", "postgresql://bot:bot@127.0.0.1:5432/polymarket")

# For the LIVE-ONLY bound: assumed hours of live play per event in a 'live' program's window.
# Declared, not hidden, because the whole optimistic bound rests on it.
LIVE_HOURS_PER_EVENT = 2.5
DEFAULT_WINDOW_H = 288.0        # fallback when a program publishes no end (e.g. open-ended MLB)


def load_programs(con, limit=12):
    """Active programs ranked by pool per market — the only ranking that means anything (a
    $15,000 PGA pool across 1,172 markets is $13/market and is not a business)."""
    with con.cursor() as cur:
        cur.execute("""
            WITH latest AS (
                SELECT DISTINCT ON (us_slug, program_id)
                       us_slug, program_id, reward_pool, target_size, discount_factor,
                       period, status, starts_at, ends_at
                  FROM us_incentive_program
              ORDER BY us_slug, program_id, fetched_at DESC
            )
            SELECT program_id, MAX(reward_pool), MAX(target_size), MAX(discount_factor),
                   MAX(period), MIN(starts_at), MAX(ends_at), COUNT(DISTINCT us_slug),
                   ARRAY_AGG(DISTINCT us_slug)
              FROM latest
             WHERE status = 'active' AND reward_pool IS NOT NULL
          GROUP BY program_id
          ORDER BY MAX(reward_pool) / NULLIF(COUNT(DISTINCT us_slug), 0) DESC
             LIMIT %s
        """, (limit,))
        cols = ["program_id", "pool", "target_size", "discount_factor", "period",
                "starts_at", "ends_at", "n_markets", "slugs"]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def touch_depth(con, slugs):
    """Observed resting size AT THE BEST PRICE — the pro-rata denominator. Everything deeper in
    the book scores ~0 (df^10), so the touch queue is the entire competition."""
    with con.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*),
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY best_bid_qty),
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY best_ask_qty),
                   AVG(best_bid_qty), AVG(best_ask_qty),
                   percentile_cont(0.25) WITHIN GROUP (ORDER BY best_bid_qty),
                   percentile_cont(0.75) WITHIN GROUP (ORDER BY best_bid_qty)
              FROM us_mid_tape
             WHERE us_slug = ANY(%s) AND best_bid_qty IS NOT NULL AND best_ask_qty IS NOT NULL
        """, (list(slugs),))
        r = cur.fetchone()
    if not r or not r[0]:
        return None
    return {"n_snapshots": r[0], "med_bid_qty": r[1], "med_ask_qty": r[2],
            "avg_bid_qty": r[3], "avg_ask_qty": r[4], "q25_bid": r[5], "q75_bid": r[6]}


def fill_flow(con, slugs):
    """Contracts/hour that TRADE in these markets, and the maker-side markout that actually
    applies HERE (not the venue-wide average). The reward is only worth what it pays NET of what
    the fills it drags in cost us."""
    with con.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*), COALESCE(SUM(quantity), 0), AVG(price),
                   EXTRACT(EPOCH FROM (MAX(trade_time) - MIN(trade_time)))
              FROM us_trade_tape
             WHERE us_slug = ANY(%s)
        """, (list(slugs),))
        n, qty, px, span = cur.fetchone()
    if not n or not span or span <= 0:
        return None
    return {"prints": n, "contracts": float(qty), "avg_price": float(px or 0),
            "span_s": float(span), "contracts_per_hour": float(qty) * 3600.0 / float(span)}


def model(con, sizes, markout_c, rebate_override=None):
    """markout_c = MEASURED maker markout in cents/share (from us_adverse_selection.py), i.e. what
    a fill is actually worth to the resting side once informed flow has taken its cut."""
    progs = load_programs(con)
    out = []
    for p in progs:
        depth = touch_depth(con, p["slugs"])
        flow = fill_flow(con, p["slugs"])
        if not depth:
            continue

        # payout rate bounds (see module docstring — we do not get to pick one)
        if p["starts_at"] and p["ends_at"]:
            window_h = max((p["ends_at"] - p["starts_at"]).total_seconds() / 3600.0, 1.0)
        else:
            window_h = DEFAULT_WINDOW_H
        live_h = LIVE_HOURS_PER_EVENT if p["period"] == "live" else window_h
        per_mkt_window = p["pool"] / (p["n_markets"] * window_h * 3600.0)   # $/s/market
        per_mkt_live = p["pool"] / (p["n_markets"] * max(live_h, 0.1) * 3600.0)

        px = (flow or {}).get("avg_price") or 0.5
        rebate_c = (rebate_override if rebate_override is not None
                    else us_fees.maker_rebate(min(max(px, 0.02), 0.98)) * 100)

        rows = []
        for S in sizes:
            # Our share of each side's touch queue. We JOIN the best price (the only place the
            # subsidy pays); competitors at that price are the observed touch depth.
            share_bid = S / (S + (depth["med_bid_qty"] or 0.0)) if S > 0 else 0.0
            share_ask = S / (S + (depth["med_ask_qty"] or 0.0)) if S > 0 else 0.0
            share = (share_bid + share_ask) / 2.0

            rw_window = per_mkt_window * share * 3600.0        # $/hour, conservative bound
            rw_live = per_mkt_live * share * 3600.0            # $/hour, optimistic bound

            # Fills we drag in by standing at the touch: our queue share of the traded flow.
            cph = (flow or {}).get("contracts_per_hour", 0.0)
            filled_per_h = cph * share
            # Net from fills: the MEASURED markout plus the maker rebate, per share.
            fill_pnl_h = filled_per_h * (markout_c + rebate_c) / 100.0     # $/hour

            rows.append({
                "size": S, "share_of_touch": share,
                "reward_per_h_window": rw_window, "reward_per_h_live": rw_live,
                "filled_contracts_per_h": filled_per_h,
                "fill_pnl_per_h": fill_pnl_h,
                "net_per_h_window": rw_window + fill_pnl_h,
                "net_per_h_live": rw_live + fill_pnl_h,
                # the term net_edge() wants: subsidy expressed per SHARE FILLED
                "reward_per_filled_share_c_window": (rw_window / filled_per_h * 100.0)
                if filled_per_h > 0.01 else None,
                "reward_per_filled_share_c_live": (rw_live / filled_per_h * 100.0)
                if filled_per_h > 0.01 else None,
            })

        out.append({"program": p["program_id"], "pool": p["pool"], "n_markets": p["n_markets"],
                    "pool_per_market": p["pool"] / p["n_markets"],
                    "discount_factor": p["discount_factor"], "target_size": p["target_size"],
                    "period": p["period"], "window_h": window_h,
                    "depth": depth, "flow": flow, "avg_price": px,
                    "rebate_c": rebate_c, "markout_c": markout_c, "sizes": rows})
    return out


def report(res, sizes):
    print("=" * 100)
    print("LIQUIDITY-REWARD CAPTURE — what the subsidy pays a resting order, against REAL depth")
    print("=" * 100)
    print("score = df^(ticks from best) * size. Tick=0.001 but 93% of quotes sit on whole cents,")
    print("so 1 cent off the touch = 10 ticks = df^10 ~ 0. THE SUBSIDY ONLY PAYS AT THE TOUCH —")
    print("the exact place adverse selection lives. There is no safe distance that still earns.")
    print()
    for r in res:
        if not r["flow"]:
            continue
        d, f = r["depth"], r["flow"]
        print(f"--- {r['program']}  pool ${r['pool']:,.0f} / {r['n_markets']} markets "
              f"= ${r['pool_per_market']:,.0f}/market   df={r['discount_factor']} "
              f"target={r['target_size']:,.0f}  period={r['period']} ({r['window_h']:.0f}h)")
        print(f"    touch depth (median): bid {d['med_bid_qty']:,.0f} / ask {d['med_ask_qty']:,.0f}"
              f" contracts  (n={d['n_snapshots']} snapshots)")
        print(f"    traded flow: {f['contracts_per_hour']:,.0f} contracts/hour "
              f"(avg px {f['avg_price']:.3f}, {f['prints']} prints over {f['span_s']/60:.0f} min)")
        print(f"    maker economics per filled share: markout {r['markout_c']:+.3f}c "
              f"+ rebate {r['rebate_c']:+.3f}c = {r['markout_c']+r['rebate_c']:+.3f}c")
        print(f"    {'rest':>7} {'queue%':>8} {'reward $/h':>22} {'fills/h':>9} "
              f"{'fill P&L $/h':>13} {'NET $/h':>22}")
        print(f"    {'':>7} {'':>8} {'window':>10}{'live-only':>12} {'':>9} {'':>13} "
              f"{'window':>10}{'live-only':>12}")
        for s in r["sizes"]:
            print(f"    {s['size']:>7,} {s['share_of_touch']:>7.1%} "
                  f"{s['reward_per_h_window']:>10.2f}{s['reward_per_h_live']:>12.2f} "
                  f"{s['filled_contracts_per_h']:>9,.0f} {s['fill_pnl_per_h']:>+13.2f} "
                  f"{s['net_per_h_window']:>+10.2f}{s['net_per_h_live']:>+12.2f}")
        print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", default="250,1000,5000")
    ap.add_argument("--markout", type=float, default=-0.10,
                    help="MEASURED maker markout, cents/share (us_adverse_selection.py)")
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    sizes = [int(s) for s in a.sizes.split(",") if s.strip()]

    con = psycopg2.connect(PG_DSN)
    try:
        res = model(con, sizes, a.markout)
    finally:
        con.close()
    report(res, sizes)
    if a.json:
        with open(a.json, "w") as f:
            json.dump(res, f, indent=1, default=str)
        print(f"wrote {a.json}")


if __name__ == "__main__":
    main()
