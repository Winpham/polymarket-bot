#!/usr/bin/env python3
"""
DEEP-SHARP EDGE THESIS (deep-pool edge run, Phase 1) — pre-registered instrument.

THE QUESTION (profit MARGIN): do signals co-backed by DEEP sharps (rank past the
voting cutoff — small, capital-efficient traders who don't move the book) give a
FOLLOWER more *realizable* edge than whale-only signals, after the capture
haircut?  Deep traders' fills are captured but do NOT vote, so co-backing is a
free observational label on the live `strict` stream — measuring it changes
nothing live.

PRE-REGISTERED (2026-07-02, BEFORE looking at any split):
  Hypothesis H1 : deep-sharp-co-backed strict signals have realizable honest ROI
                  ≥ whale-only strict signals (one-sided), event-clustered.
  Population    : resolved `strict` signals with a pre-resolution price capture
                  (initial_market_price IS NOT NULL), restricted to signals first
                  detected AFTER deep capture began (MIN deep fill ts) — before
                  that, no signal COULD be labeled deep-backed (composition guard).
  Label         : deep-backed ⇔ ≥1 deep trader BUY fill on the same
                  (condition_id, outcome_index) with fill ts ≤ the signal's
                  first_detected_at and within the 48h window before it —
                  decision-time discipline: the follower could have known.
  Tier A (PRIMARY, certifiable)  : deep = CERTIFIED sharps (gate-Trusted
                  `trust_verdict`, the belief-blind gate). Fed via --certified
                  (one wallet per line, lower-cased) — produced by the Rust
                  report harness `report_deep_sharp_pass`. NO certified sharp ⇒
                  the primary answer is a STRUCTURAL NULL (N=0), reported as such.
  Tier B (EXPLORATORY, non-certifiable): deep = gate-READY (≥30 distinct resolved
                  BUY events). This tier can NEVER promote anything — it exists to
                  read the direction early and honestly, clearly labeled.
  Metric        : honest realizable ROI per event = AVG over the event of
                  (won − entry)/entry − FEE, entry = COALESCE(entry_ask, p0 + HAIRCUT)
                  — the EXACT formula of honest_pnl_by_strategy (consensus.rs).
                  Secondary: CLV share (won − p0), N events.
  Test          : gap = mean_ev(deep-backed) − mean_ev(whale-only); permutation
                  null = the same gap under N_PERM random relabelings of which
                  events are "deep-backed", stratified by (price-band × UTC-day)
                  so market mix and time are carried by the null; one-sided
                  p_emp = frac(null ≥ observed).
  Liquidity     : the same gap within total_usd halves (median split) — a
                  thin-market edge you can't fill is not edge.
  Verdict rule  : the thesis is SUPPORTED only if Tier A has ≥30 deep-backed
                  events AND gap > 0 with p_emp ≤ 0.05 AND the gap does not
                  invert in the high-liquidity half. Anything less: INDETERMINATE
                  (by power or by structure), reported honestly. Tier B can only
                  ever be "suggestive", never "supported".

READ-ONLY. Run against a RESTORED SNAPSHOT (never prod):
  PG_CONTAINER=pg-report ./scripts/deep_edge_thesis.py [--certified file]
"""

import argparse
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

N_PERM = 2000
SEED = 20260702
HAIRCUT = 0.01   # mirrors EXEC_HAIRCUT default
FEE = 0.02       # mirrors FEE_PCT default
WINDOW_H = 48    # consensus window
GATE_READY_EVENTS = 30

# One query: every resolved strict signal in the post-deep-capture era, with its
# deep co-backers (Tier B membership computed in SQL; Tier A checked in Python
# against the --certified list). LEFT JOIN LATERAL keeps whale-only signals.
SQL = f"""
WITH deep AS (
    SELECT LOWER(proxy_wallet) AS w
    FROM followed_traders
    WHERE active AND source = 'leaderboard' AND NOT consensus_eligible
),
deep_ready AS (
    SELECT tf.wallet AS w
    FROM trader_fills tf JOIN deep d ON d.w = tf.wallet
    WHERE tf.resolved AND tf.side = 'BUY'
    GROUP BY tf.wallet
    HAVING COUNT(DISTINCT COALESCE(tf.event_slug, tf.condition_id)) >= {GATE_READY_EVENTS}
),
era AS (
    SELECT MIN(tf.ts) AS t0 FROM trader_fills tf JOIN deep d ON d.w = tf.wallet
)
SELECT cs.id, COALESCE(cs.event_slug, cs.condition_id) AS ev,
       cs.condition_id, cs.outcome_index,
       (cs.outcome_won::int) AS won,
       cs.initial_market_price AS p0,
       COALESCE(cs.entry_ask, cs.initial_market_price + {HAIRCUT}) AS entry,
       cs.total_usd,
       to_char(cs.first_detected_at AT TIME ZONE 'UTC', 'YYYY-MM-DD') AS day,
       COALESCE(bk.wallets, '') AS deep_backers
FROM consensus_signals cs, era
LEFT JOIN LATERAL (
    SELECT string_agg(DISTINCT tf.wallet, ' ') AS wallets
    FROM trader_fills tf
    JOIN deep_ready dr ON dr.w = tf.wallet
    WHERE tf.condition_id = cs.condition_id
      AND tf.outcome_index = cs.outcome_index
      AND tf.side = 'BUY'
      AND tf.ts <= cs.first_detected_at
      AND tf.ts >= cs.first_detected_at - INTERVAL '{WINDOW_H} hours'
) bk ON TRUE
WHERE cs.strategy = 'strict' AND cs.resolved
  AND cs.initial_market_price IS NOT NULL
  AND cs.first_detected_at >= era.t0
"""


def fetch():
    out = subprocess.run(PG + ["-f", "-"], input=SQL, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    rows = []
    for r in csv.DictReader(io.StringIO(out.stdout)):
        r["won"] = int(r["won"])
        r["p0"] = float(r["p0"])
        r["entry"] = float(r["entry"])
        r["total_usd"] = float(r["total_usd"] or 0.0)
        r["deep_backers"] = set(r["deep_backers"].split()) if r["deep_backers"] else set()
        rows.append(r)
    return rows


def band(p):  # exact mirror of width_bucket(p, 0, 1, 5)
    if p < 0.0:
        return 0
    if p >= 1.0:
        return 6
    return int(p * 5) + 1


def hroi(r):
    return (r["won"] - r["entry"]) / r["entry"] - FEE if r["entry"] else 0.0


def clv(r):
    return r["won"] - r["p0"]


def by_event(rows):
    """Event-cluster first (the within-match leak fix): per-event mean of each
    metric, plus the event's deep-backed label (any signal row backed ⇒ backed)."""
    ev = defaultdict(lambda: {"hroi": [], "clv": [], "backed": False,
                              "band": None, "day": None, "usd": 0.0})
    for r in rows:
        e = ev[r["ev"]]
        e["hroi"].append(hroi(r))
        e["clv"].append(clv(r))
        e["backed"] = e["backed"] or bool(r["deep_backers"])
        e["band"] = band(r["p0"])       # representative (first row's band)
        e["day"] = e["day"] or r["day"]
        e["usd"] = max(e["usd"], r["total_usd"])
    out = []
    for k, e in ev.items():
        out.append({
            "ev": k,
            "hroi": sum(e["hroi"]) / len(e["hroi"]),
            "clv": sum(e["clv"]) / len(e["clv"]),
            "backed": e["backed"],
            "stratum": (e["band"], e["day"]),
            "usd": e["usd"],
        })
    return out


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def sd(xs):
    if len(xs) < 2:
        return float("nan")
    m = mean(xs)
    return (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


def gap_of(events, labels=None):
    """deep-backed mean − whale-only mean of event honest ROI. `labels` overrides
    the backed flags (for permutation draws)."""
    a, b = [], []
    for i, e in enumerate(events):
        backed = labels[i] if labels is not None else e["backed"]
        (a if backed else b).append(e["hroi"])
    if not a or not b:
        return None
    return mean(a) - mean(b)


def permutation_p(events, observed, rng):
    """Stratified label permutation: shuffle which events are 'backed' WITHIN each
    (band × day) stratum, keeping the per-stratum backed count — the null carries
    the full market/time composition, only the selection is randomized."""
    strata = defaultdict(list)
    for i, e in enumerate(events):
        strata[e["stratum"]].append(i)
    base = [e["backed"] for e in events]
    ge = 0
    valid = 0
    for _ in range(N_PERM):
        labels = list(base)
        for idxs in strata.values():
            vals = [labels[i] for i in idxs]
            rng.shuffle(vals)
            for i, v in zip(idxs, vals):
                labels[i] = v
        g = gap_of(events, labels)
        if g is None:
            continue
        valid += 1
        if g >= observed:
            ge += 1
    if valid == 0:
        return None, 0
    return (ge + 1) / (valid + 1), valid


def report_tier(name, events, rng, certifiable):
    n_backed = sum(1 for e in events if e["backed"])
    n_only = len(events) - n_backed
    print(f"\n=== Tier {name}: {n_backed} deep-backed / {n_only} whale-only events ===")
    if n_backed == 0:
        print("STRUCTURAL NULL: no deep-backed events in this tier — "
              "no comparison is possible yet. This is the honest answer today.")
        return
    a = [e["hroi"] for e in events if e["backed"]]
    b = [e["hroi"] for e in events if not e["backed"]]
    ac = [e["clv"] for e in events if e["backed"]]
    bc = [e["clv"] for e in events if not e["backed"]]
    obs = gap_of(events)
    print(f"honest ROI  deep-backed {mean(a):+.4f} (sd {sd(a):.4f}, N={len(a)}) "
          f"vs whale-only {mean(b):+.4f} (sd {sd(b):.4f}, N={len(b)})")
    print(f"CLV share   deep-backed {mean(ac):+.4f} vs whale-only {mean(bc):+.4f}")
    print(f"gap (deep − whale) = {obs:+.4f}")
    p, valid = permutation_p(events, obs, rng)
    if p is None:
        print("permutation null: degenerate (a stratum holds all backed labels)")
    else:
        print(f"permutation p_emp (one-sided, {valid} valid draws) = {p:.4f}")

    # Liquidity control: median split on the event's max total_usd.
    usds = sorted(e["usd"] for e in events)
    med = usds[len(usds) // 2]
    for label, sel in (("low-liquidity", lambda e: e["usd"] <= med),
                       ("high-liquidity", lambda e: e["usd"] > med)):
        sub = [e for e in events if sel(e)]
        g = gap_of(sub)
        nb = sum(1 for e in sub if e["backed"])
        if g is None:
            print(f"  {label}: no comparison (backed N={nb} of {len(sub)})")
        else:
            print(f"  {label}: gap {g:+.4f} (backed N={nb} of {len(sub)})")

    floor_ok = n_backed >= 30
    p_ok = p is not None and p <= 0.05
    pos = obs > 0
    if certifiable:
        if floor_ok and p_ok and pos:
            print("VERDICT: SUPPORTED (pending the high-liquidity non-inversion check above)")
        elif not floor_ok:
            print(f"VERDICT: INDETERMINATE BY POWER (backed events {n_backed} < 30)")
        else:
            print("VERDICT: NOT SUPPORTED on this window")
    else:
        print("(exploratory tier — direction only, can never certify or promote)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--certified", help="file of certified deep-sharp wallets (one per line)")
    args = ap.parse_args()
    certified = set()
    if args.certified:
        with open(args.certified) as f:
            certified = {ln.strip().lower() for ln in f if ln.strip()}

    rows = fetch()
    if not rows:
        sys.exit("no resolved strict signals in the post-deep-capture era")
    print(f"population: {len(rows)} resolved strict signal rows "
          f"(post-deep-capture era) from container '{PG_CONTAINER}'")
    print(f"certified deep sharps supplied: {len(certified)}")

    rng = random.Random(SEED)

    # Tier A: certified only — relabel each row's backed set to certified∩backers.
    rows_a = [dict(r, deep_backers=r["deep_backers"] & certified) for r in rows]
    report_tier("A (PRIMARY — certified sharps)", by_event(rows_a), rng, certifiable=True)

    # Tier B: gate-ready (the SQL's deep_ready membership, as fetched).
    report_tier("B (EXPLORATORY — gate-ready ≥30 ev)", by_event(rows), rng, certifiable=False)


if __name__ == "__main__":
    main()
