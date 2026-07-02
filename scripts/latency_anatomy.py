#!/usr/bin/env python3
"""
DETECTION-LATENCY ANATOMY (truth-audit attack B): how much edge dies between a sharp's fill and
our detection, is faster polling worth anything, and does latency-sensitivity threaten the edge?

The vote atoms carry each backer's FILL `ts`; `first_detected_at` is our detection. The TRIGGERING
fill is the last atom at/before detection:  latency = first_detected_at − max(ts ≤ detection).
(Atoms accumulate POST-detection fills too, so the ≤detection filter is essential — without it the
"last fill" leaks future rows and latency goes negative.)

The three time-anatomy numbers, reconciled:
  • structural follower tax   — `capture_lag = initial_market_price − at-fire mean` (the price move
    from the sharps' fill to our first observable mid; speed cannot recover it). D11: +2.1¢ favorite.
  • detection latency         — measured here (median, p90), poll-cadence-bounded (~2 min).
  • post-detection decay      — D11 `decay_analysis.py`: NO material decay <30 min after detection.

The load-bearing test: within the poll-recoverable window (latency ≤ 120 s), does event-clustered
surplus DECLINE from the fastest to the slowest latency quartile? Regime-controlled (surplus is
already blind-band-matched; we additionally demean within regime). If flat ⇒ faster polling recovers
~0; the answer to "is a 10 s poll worth it" is the fast−slow surplus gap (0 if not significant).

Self-test:  ./latency_anatomy.py --self-test   (injected decay-with-latency detected; flat fixture flat)
Live:       ./latency_anatomy.py
"""

import csv
import io
import random
import subprocess
import sys
from collections import defaultdict

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from superkey import super_event  # noqa: E402

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]
SEED = 20260702
N_PERM = 5000
POLL_WINDOW = 120  # seconds — the cadence-bounded window a faster poll could recover

SQL = """
WITH atoms AS (
  SELECT cs.id, cs.strategy, cs.event_slug, cs.slug, cs.condition_id,
         cs.is_sports, extract(epoch FROM cs.first_detected_at) AS det,
         COALESCE(cs.initial_mean_price, cs.mean_price) AS entry,
         (cs.outcome_won::int) AS won,
         cs.initial_market_price - COALESCE(cs.initial_mean_price, cs.mean_price) AS cap_lag,
         (a->>'ts')::bigint AS fill_ts
  FROM consensus_signals cs, jsonb_array_elements(cs.observed_votes) a
  WHERE cs.resolved AND cs.strategy IN ('favorite','elite_fresh_fav','_blind')
)
SELECT id, strategy, event_slug, slug, condition_id, entry, won, cap_lag,
       det, max(fill_ts) FILTER (WHERE fill_ts <= det) AS last_trig
FROM atoms GROUP BY id, strategy, event_slug, slug, condition_id, entry, won, cap_lag, det
"""

REGIMES = [(("btc", "eth", "sol", "xrp", "bnb", "doge", "bitcoin", "ethereum"), "crypto"),
           (("atp", "wta", "itf"), "tennis"), (("fifwc",), "soccer"),
           (("mlb",), "mlb"), (("cs",), "cs2")]


def regime(slug):
    s = slug or ""
    for pre, name in REGIMES:
        if s.startswith(pre):
            return name
    return "other"


def band(p):
    if p < 0:
        return 0
    if p >= 1:
        return 6
    return int(p * 5) + 1


def fetch():
    out = subprocess.run(PG + ["-c", SQL.replace("\n", " ")], capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    rows = []
    for r in csv.DictReader(io.StringIO(out.stdout)):
        r["entry"] = float(r["entry"])
        r["won"] = int(r["won"])
        r["det"] = float(r["det"])
        r["last_trig"] = float(r["last_trig"]) if r["last_trig"] else None
        r["cap_lag"] = float(r["cap_lag"]) if r["cap_lag"] else None
        rows.append(r)
    return rows


def clustered_mean(pairs):
    """pairs: (ev, value) → event-clustered mean, n_events."""
    ev = defaultdict(list)
    for e, v in pairs:
        ev[e].append(v)
    if not ev:
        return float("nan"), 0
    means = [sum(v) / len(v) for v in ev.values()]
    return sum(means) / len(means), len(means)


def perm_gap(fast, slow, rng, n_perm=N_PERM):
    """One-sided permutation p that fast surplus − slow surplus > observed, event-clustered."""
    gf, _ = clustered_mean([(e, v) for e, v in fast])
    gs, _ = clustered_mean([(e, v) for e, v in slow])
    obs = gf - gs
    pooled = fast + slow
    nf = len(fast)
    ge = 0
    for _ in range(n_perm):
        rng.shuffle(pooled)
        pf, ps = pooled[:nf], pooled[nf:]
        d = clustered_mean(pf)[0] - clustered_mean(ps)[0]
        if d >= obs:
            ge += 1
    return obs, ge / n_perm


def run_live():
    rows = fetch()
    blind = [r for r in rows if r["strategy"] == "_blind"]
    blind_band = defaultdict(list)
    for r in blind:
        blind_band[band(r["entry"])].append(r["won"] - r["entry"])
    blind_edge = {b: sum(v) / len(v) for b, v in blind_band.items()}

    for strat in ("favorite", "elite_fresh_fav"):
        srows = [r for r in rows if r["strategy"] == strat and r["last_trig"] is not None]
        lat = [(r["det"] - r["last_trig"]) for r in srows]
        lat = [x for x in lat if x >= 0]
        lat.sort()
        n = len(lat)
        med = lat[n // 2] if n else float("nan")
        p90 = lat[int(n * 0.9)] if n else float("nan")
        caps = [r["cap_lag"] for r in srows if r["cap_lag"] is not None]
        cap_mean = sum(caps) / len(caps) if caps else float("nan")
        print(f"\n=== {strat} · {n} signals with a pre-detection triggering fill ===")
        print(f"  detection latency (fill→detect): median {med:.0f}s · p90 {p90:.0f}s "
              f"(poll cadence ~120s; tail = consensus formed from older positions)")
        print(f"  structural follower tax (capture_lag = first mid − at-fire entry): {cap_mean:+.4f} "
              f"(= {cap_mean*100:+.1f}¢; speed cannot recover this)")

        # poll-recoverable window: latency ≤ 120s. Regime-demeaned surplus vs latency quartiles.
        win = [r for r in srows if 0 <= (r["det"] - r["last_trig"]) <= POLL_WINDOW]
        # regime-demean the blind-band surplus
        reg_vals = defaultdict(list)
        recs = []
        for r in win:
            surplus = (r["won"] - r["entry"]) - blind_edge.get(band(r["entry"]), 0.0)
            rg = regime(r["slug"] or r["event_slug"])
            reg_vals[rg].append(surplus)
            recs.append((r, surplus, rg))
        reg_mean = {rg: sum(v) / len(v) for rg, v in reg_vals.items()}
        # split by median latency within the window
        recs.sort(key=lambda t: t[0]["det"] - t[0]["last_trig"])
        if len(recs) < 8:
            print(f"  poll-window (≤{POLL_WINDOW}s) signals: {len(recs)} — too few for a latency split")
            continue
        mid = len(recs) // 2
        evk = lambda r: super_event(r["event_slug"], r["slug"]) or r["condition_id"]  # noqa: E731
        fast = [(evk(r), s - reg_mean[rg]) for r, s, rg in recs[:mid]]
        slow = [(evk(r), s - reg_mean[rg]) for r, s, rg in recs[mid:]]
        gf, nf = clustered_mean(fast)
        gs, ns = clustered_mean(slow)
        rng = random.Random(SEED)
        gap, p = perm_gap(fast, slow, rng)
        lat_fast = recs[mid - 1][0]["det"] - recs[mid - 1][0]["last_trig"]
        print(f"  poll-window (≤{POLL_WINDOW}s): {len(recs)} signals; fast half (≤{lat_fast:.0f}s) "
              f"regime-demeaned surplus {gf:+.2%} ({nf} ev) vs slow half {gs:+.2%} ({ns} ev)")
        print(f"  fast − slow gap = {gap:+.2%}, permutation p = {p:.4f}  "
              f"→ {'faster polling would recover this' if p <= 0.05 else 'NO latency sensitivity in-window — faster polling recovers ~0'}")
        print(f"  ANSWER: a 10s poll (vs ~120s) would plausibly recover ≈ "
              f"{max(0.0, gap)*100:.1f} pts of surplus" + ("" if p <= 0.05 else " (not distinguishable from 0)"))


# --- self-test -------------------------------------------------------------------------------
def _self_test():
    ok = True
    rng = random.Random(3)
    # injected decay: fast events surplus ~+0.20, slow ~−0.05, distinct evs
    fast = [(f"f{i}", 0.20) for i in range(20)]
    slow = [(f"s{i}", -0.05) for i in range(20)]
    gap, p = perm_gap(fast, slow, rng, n_perm=3000)
    c1 = gap > 0.2 and p <= 0.05
    ok = ok and c1
    print(f"  [{'ok' if c1 else 'FAIL'}] injected decay: gap={gap:+.2f} p={p:.4f} (want gap>0.2, p≤0.05)")
    # flat: both halves same distribution
    rng2 = random.Random(4)
    f2 = [(f"a{i}", (i % 2) * 0.1) for i in range(20)]
    s2 = [(f"b{i}", (i % 2) * 0.1) for i in range(20)]
    gap2, p2 = perm_gap(f2, s2, rng2, n_perm=3000)
    c2 = abs(gap2) < 1e-9 and p2 > 0.05
    ok = ok and c2
    print(f"  [{'ok' if c2 else 'FAIL'}] flat: gap={gap2:+.2f} p={p2:.4f} (want gap≈0, p>0.05)")
    # clustered_mean collapse
    m, nev = clustered_mean([("a", 1.0), ("a", 0.0), ("b", 1.0)])
    c3 = nev == 2 and abs(m - 0.75) < 1e-9
    ok = ok and c3
    print(f"  [{'ok' if c3 else 'FAIL'}] clustered_mean: {nev} evs mean={m:.3f} (want 2, 0.750)")
    print("SELF-TEST", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(0 if _self_test() else 1)
    sys.exit(run_live())
