#!/usr/bin/env python3
"""
RELATIONAL / BLOC STRUCTURE PROBES (deep-pool edge run, Phase 4 — stretch).

Three belief-blind probes over the 280-trader fill archive. Every one is a
HYPOTHESIS judged against a permutation/selection null with event clustering —
expect most to be INDETERMINATE BY POWER, and say so. Nothing here ships a
signal; a probe that certifies becomes a CANDIDATE for a future forward arm.

PRE-REGISTERED (2026-07-02, before looking):
  P1  Co-movement pair surplus: trader pairs that repeatedly take the SAME side
      of the same market within 6h. H: the shared picks of high-co-movement
      pairs carry positive advantage surplus over the band-blind baseline.
      Null: advantage of randomly-relabeled picks matched by (band × day).
      Floor: pair needs ≥20 shared distinct events; ≥30 events pooled over the
      qualifying pairs for the aggregate verdict.
  P2  Deep-leader timing premium: strict signals where a gate-ready deep trader
      entered the same (market, outcome) BEFORE detection. H: the deep leader's
      entry price beats the mid we captured at detection (premium = p0_signal −
      p_deep_first > 0) — i.e. acting on the deep leader's flow would enter
      cheaper than acting on the signal. CONTROL: the same premium measured
      from the FIRST WHALE backer's fill (whales lead the signal by
      construction; the deep premium must beat the whale premium to mean
      anything). Event-clustered, sign test + mean gap.
  P3  Dumb-bloc feasibility: how many traders carry an AVOID-grade forward
      record (upper bound < 0 proxy: surplus < −5% at ≥30 events)? A fade-the-
      bloc arm needs ≥3 such traders co-siding; below that it is STRUCTURALLY
      NULL — report the count honestly, build nothing.

READ-ONLY; run against a restored snapshot:  PG_CONTAINER=pg-report ./scripts/relational_probes.py
"""

import csv
import io
import os
import random
import subprocess
import sys
from collections import defaultdict
from statistics import NormalDist

PG_CONTAINER = os.environ.get("PG_CONTAINER", "pg-report")
PG = ["docker", "exec", "-i", PG_CONTAINER,
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]
SEED = 20260702
N_PERM = 1000
PAIR_FLOOR = 20
EVENT_FLOOR = 30


def q(sql):
    out = subprocess.run(PG + ["-f", "-"], input=sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    return list(csv.DictReader(io.StringIO(out.stdout)))


def band(p):
    return min(int(p * 5) + 1, 6) if p >= 0 else 0


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


# --- P1: co-movement pair surplus -------------------------------------------
def probe1(rng):
    print("\n=== P1 co-movement pair surplus ===")
    # Resolved BUY fills of tracked leaderboard traders, with advantage.
    rows = q("""
SELECT tf.wallet, COALESCE(tf.event_slug, tf.condition_id) AS ev, tf.condition_id,
       tf.outcome_index, tf.price, tf.advantage,
       EXTRACT(EPOCH FROM tf.ts) AS ts,
       to_char(tf.ts AT TIME ZONE 'UTC', 'YYYY-MM-DD') AS day
FROM trader_fills tf
JOIN followed_traders ft ON LOWER(ft.proxy_wallet) = tf.wallet
WHERE ft.source = 'leaderboard' AND tf.resolved AND tf.side = 'BUY'
  AND tf.advantage IS NOT NULL
""")
    for r in rows:
        r["price"], r["advantage"], r["ts"] = float(r["price"]), float(r["advantage"]), float(r["ts"])

    # Band-blind baseline over the whole resolved population (the archive's own
    # favorite-longshot-neutralizer — same construction as trader_slice_scores).
    blind = defaultdict(list)
    for r in rows:
        blind[band(r["price"])].append(r["advantage"])
    blind = {b: mean(v) for b, v in blind.items()}

    # First fill per (wallet, market, outcome) — laddering counts once.
    first = {}
    for r in sorted(rows, key=lambda x: x["ts"]):
        first.setdefault((r["wallet"], r["condition_id"], r["outcome_index"]), r)

    # Pair co-movements within 6h on the same (market, outcome).
    by_mkt = defaultdict(list)
    for r in first.values():
        by_mkt[(r["condition_id"], r["outcome_index"])].append(r)
    pair_events = defaultdict(set)
    for fills in by_mkt.values():
        fills.sort(key=lambda x: x["ts"])
        for i, a in enumerate(fills):
            for b in fills[i + 1:]:
                if b["ts"] - a["ts"] > 6 * 3600:
                    break
                pair_events[tuple(sorted((a["wallet"], b["wallet"])))].add(a["ev"])

    hot = {p: evs for p, evs in pair_events.items() if len(evs) >= PAIR_FLOOR}
    print(f"pairs with ≥{PAIR_FLOOR} shared events (≤6h apart): {len(hot)}")
    if not hot:
        print("P1: INDETERMINATE BY POWER — no pair reaches the shared-event floor.")
        return

    # Surplus of the union of qualifying pairs' shared events, event-clustered.
    shared_evs = set().union(*hot.values())
    ev_surplus = defaultdict(list)
    for r in first.values():
        if r["ev"] in shared_evs:
            ev_surplus[r["ev"]].append(r["advantage"] - blind.get(band(r["price"]), 0.0))
    series = [mean(v) for v in ev_surplus.values()]
    if len(series) < EVENT_FLOOR:
        print(f"P1: INDETERMINATE BY POWER — {len(series)} shared events < {EVENT_FLOOR}.")
        return
    obs = mean(series)

    # Null: same-size random event sets drawn from the full resolved event pool,
    # matched by (band × day) profile of the shared set.
    all_ev = defaultdict(list)  # stratum -> [ev-mean surplus]
    ev_all = defaultdict(list)
    ev_strat = {}
    for r in first.values():
        ev_all[r["ev"]].append(r["advantage"] - blind.get(band(r["price"]), 0.0))
        ev_strat.setdefault(r["ev"], (band(r["price"]), r["day"]))
    for ev, vals in ev_all.items():
        all_ev[ev_strat[ev]].append(mean(vals))
    profile = defaultdict(int)
    for ev in ev_surplus:
        profile[ev_strat[ev]] += 1
    ge = 0
    draws = 0
    for _ in range(N_PERM):
        drawn = []
        ok = True
        for st, k in profile.items():
            pool = all_ev.get(st, [])
            if len(pool) < k:
                ok = False
                break
            drawn.extend(rng.sample(pool, k))
        if not ok:
            continue
        draws += 1
        if mean(drawn) >= obs:
            ge += 1
    p = (ge + 1) / (draws + 1) if draws else None
    print(f"P1: {len(hot)} qualifying pairs · {len(series)} shared events · "
          f"surplus {obs:+.4f} · p_emp={p if p is None else f'{p:.4f}'} ({draws} draws)")
    print("P1 verdict:", "CANDIDATE (needs forward confirmation + gate)" if p is not None and p <= 0.01 and obs > 0.03
          else "NULL / INDETERMINATE — co-moving picks are not distinguishable from a matched blind draw")


# --- P2: deep-leader timing premium ------------------------------------------
def probe2():
    print("\n=== P2 deep-leader timing premium (vs whale-lead control) ===")
    rows = q("""
WITH deep AS (
    SELECT LOWER(proxy_wallet) AS w FROM followed_traders
    WHERE active AND source='leaderboard' AND NOT consensus_eligible
),
deep_ready AS (
    SELECT tf.wallet AS w FROM trader_fills tf JOIN deep d ON d.w = tf.wallet
    WHERE tf.resolved AND tf.side='BUY'
    GROUP BY tf.wallet
    HAVING COUNT(DISTINCT COALESCE(tf.event_slug, tf.condition_id)) >= 30
),
hot AS (
    SELECT LOWER(proxy_wallet) AS w FROM followed_traders
    WHERE active AND source='leaderboard' AND consensus_eligible
)
SELECT COALESCE(cs.event_slug, cs.condition_id) AS ev,
       cs.initial_market_price AS p0,
       dl.p AS deep_price, wl.p AS whale_price
FROM consensus_signals cs
LEFT JOIN LATERAL (
    SELECT tf.price AS p FROM trader_fills tf JOIN deep_ready dr ON dr.w = tf.wallet
    WHERE tf.condition_id = cs.condition_id AND tf.outcome_index = cs.outcome_index
      AND tf.side='BUY' AND tf.ts <= cs.first_detected_at
      AND tf.ts >= cs.first_detected_at - INTERVAL '48 hours'
    ORDER BY tf.ts ASC LIMIT 1) dl ON TRUE
LEFT JOIN LATERAL (
    SELECT tf.price AS p FROM trader_fills tf JOIN hot h ON h.w = tf.wallet
    WHERE tf.condition_id = cs.condition_id AND tf.outcome_index = cs.outcome_index
      AND tf.side='BUY' AND tf.ts <= cs.first_detected_at
      AND tf.ts >= cs.first_detected_at - INTERVAL '48 hours'
    ORDER BY tf.ts ASC LIMIT 1) wl ON TRUE
WHERE cs.strategy='strict' AND cs.resolved AND cs.initial_market_price IS NOT NULL
""")
    deep_prem, whale_prem = defaultdict(list), defaultdict(list)
    for r in rows:
        p0 = float(r["p0"])
        if r["deep_price"]:
            deep_prem[r["ev"]].append(p0 - float(r["deep_price"]))
        if r["whale_price"]:
            whale_prem[r["ev"]].append(p0 - float(r["whale_price"]))
    d = [mean(v) for v in deep_prem.values()]
    w = [mean(v) for v in whale_prem.values()]
    if len(d) < EVENT_FLOOR:
        print(f"P2: INDETERMINATE BY POWER — deep-led events {len(d)} < {EVENT_FLOOR}.")
        return
    dpos = sum(1 for x in d if x > 0)
    # Sign-test z for premium > 0 (binomial normal approx).
    z = (dpos - len(d) / 2) / (len(d) ** 0.5 / 2)
    p = 1 - NormalDist().cdf(z)
    print(f"deep-led events {len(d)}: premium {mean(d):+.4f} (positive {dpos}/{len(d)}, sign-test p={p:.4f})")
    print(f"whale-lead control ({len(w)} events): premium {mean(w):+.4f}")
    verdict = ("CANDIDATE timing edge — deep premium exceeds whale control; needs a forward, "
               "decision-time arm + gate" if p <= 0.01 and w and mean(d) > mean(w)
               else "NULL / INDETERMINATE — no deep timing premium beyond the whale-lead control")
    print("P2 verdict:", verdict)


# --- P3: dumb-bloc feasibility ------------------------------------------------
def probe3():
    print("\n=== P3 dumb-bloc (fade) feasibility ===")
    rows = q("""
WITH adv AS (
    SELECT tf.wallet, COALESCE(tf.event_slug, tf.condition_id) AS ev,
           AVG(tf.advantage) AS a
    FROM trader_fills tf
    JOIN followed_traders ft ON LOWER(ft.proxy_wallet) = tf.wallet
    WHERE ft.source='leaderboard' AND tf.resolved AND tf.side='BUY'
      AND tf.advantage IS NOT NULL
    GROUP BY tf.wallet, ev
)
SELECT wallet, COUNT(*) AS n, AVG(a) AS s FROM adv GROUP BY wallet
HAVING COUNT(*) >= 30 AND AVG(a) < -0.05
""")
    print(f"traders with ≥30 events and raw advantage < −5%: {len(rows)}")
    if len(rows) < 3:
        print("P3 verdict: STRUCTURALLY NULL — fewer than 3 fade candidates; a "
              "co-siding dumb bloc cannot exist. Build nothing.")
    else:
        print("P3 verdict: candidates exist — a fade-bloc arm would still need "
              "the full belief-blind gate (this count is raw advantage, not the "
              "band-neutralized AVOID verdict).")


def main():
    rng = random.Random(SEED)
    print(f"relational probes over container '{PG_CONTAINER}' (read-only)")
    probe1(rng)
    probe2()
    probe3()
    print("\nStanding discipline: any CANDIDATE above is a hypothesis for a "
          "forward silent arm — nothing here alerts, promotes, or bets.")


if __name__ == "__main__":
    main()
