#!/usr/bin/env python3
"""
SELECTION-MATCHED NULL — the standing defense against the market_resid false-promote class.

A strategy's scoreboard surplus is measured against the band-matched `_blind` baseline, but a
SELECTIVE strategy can inherit "surplus" purely from the composition of what it fires on (the
population artifact that false-promoted `market_resid` before the 2026-07-01 label-permutation
refuted it). This instrument tests the SELECTION itself:

  observed  = event-clustered mean of (a − blind_edge[band]) over the strategy's resolved picks,
              a = outcome_won − AT-FIRE entry (COALESCE(initial_mean_price, mean_price)) —
              the exact statistic of consensus_scoreboard_by_strategy (consensus.rs).
  null      = the same statistic over N_PERM random selections from the `_blind` universe,
              matched to the strategy's (price-band × UTC-day) pick profile. The null carries the
              strategy's full composition; only the selection is randomized.
  p_emp     = one-sided fraction of null draws ≥ observed.

PRE-REGISTERED PROMOTION RULE (2026-07-02 run, DECISIONS.md D7): a strategy is
promotion-ELIGIBLE only if ALL of
  (a) belief-blind gate lower bound > capture margin (3%) at the ≥30 distinct-event floor
      (promotion.rs — unchanged), AND
  (b) this null gives p_emp ≤ 0.01 (with ≥1000 draws), AND
  (c) the regime table below shows regime-matched surplus > 0 in ≥2 disjoint sport-regimes.
Eligibility is necessary, not sufficient — promotion stays a deliberate human call.

Modes:
  ./selection_null.py                 # score every strategy (default 2000 draws, seed 20260702)
  ./selection_null.py --calibrate     # K2 self-test: 50 pseudo-strategies drawn FROM `_blind`
                                      # must yield ~uniform p (anti-conservative ⇒ DO NOT TRUST)
"""

import csv
import io
import random
import subprocess
import sys
from collections import defaultdict
from math import sqrt
from statistics import NormalDist

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]
N_PERM = 2000
SEED = 20260702
P_BAR = 0.01          # pre-registered rule (b)
MARGIN = 0.03         # capture margin, for the context line only
ALPHA = 0.05

# Sport-regime map — mirror of the (pre-registered) event_slug prefix mapping.
REGIMES = [
    (("btc", "eth", "sol", "xrp", "bnb", "doge", "hype", "bitcoin", "ethereum"), "crypto"),
    (("atp", "wta", "itf"), "tennis"),
    (("fifwc",), "soccer"),
    (("mlb",), "mlb"),
    (("cs",), "cs2"),
]

SQL = """
SELECT strategy, COALESCE(event_slug, condition_id) AS ev, event_slug,
       COALESCE(initial_mean_price, mean_price) AS entry,
       (outcome_won::int) AS won,
       to_char(first_detected_at AT TIME ZONE 'UTC', 'YYYY-MM-DD') AS day
FROM consensus_signals WHERE resolved
"""


def fetch():
    out = subprocess.run(PG + ["-f", "-"], input=SQL, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    rows = []
    for r in csv.DictReader(io.StringIO(out.stdout)):
        r["entry"] = float(r["entry"])
        r["won"] = int(r["won"])
        rows.append(r)
    return rows


def band(p):  # exact mirror of width_bucket(p, 0, 1, 5)
    if p < 0.0:
        return 0
    if p >= 1.0:
        return 6
    return int(p * 5.0) + 1


def regime(event_slug):
    s = event_slug or ""
    for prefixes, name in REGIMES:
        if s.startswith(prefixes):
            return name
    return "other"


def clustered_surplus(picks, blind_edge):
    """picks: iterable of (ev, band, a) → (event-clustered mean surplus, n_events)."""
    ev_map = defaultdict(list)
    for ev, b, a in picks:
        ev_map[ev].append(a - blind_edge.get(b, 0.0))
    if not ev_map:
        return float("nan"), 0
    means = [sum(v) / len(v) for v in ev_map.values()]
    return sum(means) / len(means), len(means)


def null_pvalue(picks_meta, blind_cells, blind_edge, rng, n_perm):
    """picks_meta: list of (cell=(band,day)). Returns (null_mean, null_sd, draws)."""
    profile = defaultdict(int)
    for cell in picks_meta:
        profile[cell] += 1
    draws = []
    for _ in range(n_perm):
        sel = []
        ok = True
        for cell, k in profile.items():
            pool = blind_cells.get(cell)
            if not pool:
                ok = False
                break
            if k > len(pool):  # tiny cell: fall back to with-replacement (documented)
                take = rng.choices(pool, k=k)
            else:
                take = rng.sample(pool, k)
            sel.extend((ev, cell[0], a) for ev, a in take)
        if not ok:
            continue
        m, _ = clustered_surplus(sel, blind_edge)
        draws.append(m)
    return draws


def main():
    calibrate = "--calibrate" in sys.argv
    rows = fetch()
    rng = random.Random(SEED)

    blind = [r for r in rows if r["strategy"] == "_blind"]
    blind_cells = defaultdict(list)   # (band, day) -> [(ev, a)]
    blind_band = defaultdict(list)
    for r in blind:
        b = band(r["entry"])
        a = r["won"] - r["entry"]
        blind_cells[(b, r["day"])].append((r["ev"], a))
        blind_band[b].append(a)
    blind_edge = {b: sum(v) / len(v) for b, v in blind_band.items()}

    if calibrate:
        # K2: pseudo-strategies sampled FROM the blind universe are true nulls by
        # construction — their p must be ~uniform. Anti-conservative ⇒ don't trust.
        ref_sizes = [30, 60, 120]
        ps = []
        for i in range(50):
            size = ref_sizes[i % len(ref_sizes)]
            pseudo = rng.sample(blind, min(size, len(blind)))
            picks = [(r["ev"], band(r["entry"]), r["won"] - r["entry"]) for r in pseudo]
            obs, _ = clustered_surplus(picks, blind_edge)
            meta = [(band(r["entry"]), r["day"]) for r in pseudo]
            draws = null_pvalue(meta, blind_cells, blind_edge, rng, 400)
            if not draws:
                continue
            p = sum(1 for x in draws if x >= obs) / len(draws)
            ps.append(p)
        lo_frac = sum(1 for p in ps if p < 0.05) / len(ps)
        mid_frac = sum(1 for p in ps if 0.1 <= p <= 0.9) / len(ps)
        verdict = "PASS" if lo_frac <= 0.20 and mid_frac >= 0.60 else "FAIL (anti-conservative — do not trust the null)"
        print(f"calibration: {len(ps)} pseudo-null strategies | p<0.05: {lo_frac:.0%} (bar ≤20%)"
              f" | p in [0.1,0.9]: {mid_frac:.0%} (bar ≥60%) → {verdict}")
        sys.exit(0 if verdict == "PASS" else 1)

    strategies = sorted({r["strategy"] for r in rows if r["strategy"] != "_blind"})
    tested = 0
    print(f"selection-matched null · {N_PERM} draws · seed {SEED} · at-fire entry · "
          f"rule: eligible ⇔ gate LB>{MARGIN:.0%} ∧ p≤{P_BAR} ∧ ≥2 regimes>0")
    print(f"{'strategy':<18} {'events':>6} {'observed':>9} {'null μ±σ':>16} {'z':>6} {'p_emp':>7}  verdict")
    results = []
    for s in strategies:
        srows = [r for r in rows if r["strategy"] == s]
        picks = [(r["ev"], band(r["entry"]), r["won"] - r["entry"]) for r in srows]
        obs, n_ev = clustered_surplus(picks, blind_edge)
        if n_ev < 10:
            print(f"{s:<18} {n_ev:>6}       —  (below 10-event readout floor)")
            continue
        tested += 1
        meta = [(band(r["entry"]), r["day"]) for r in srows]
        draws = null_pvalue(meta, blind_cells, blind_edge, rng, N_PERM)
        if len(draws) < 1000:
            print(f"{s:<18} {n_ev:>6} {obs:>+8.2%}  (null unmatchable: blind pool missing cells)")
            continue
        mu = sum(draws) / len(draws)
        sd = sqrt(sum((x - mu) ** 2 for x in draws) / (len(draws) - 1))
        z = (obs - mu) / sd if sd > 0 else float("nan")
        p = sum(1 for x in draws if x >= obs) / len(draws)
        verdict = "SELECTION-REAL" if p <= P_BAR else ("indeterminate" if p <= 0.10 else "NULL")
        results.append((s, n_ev, obs, p))
        print(f"{s:<18} {n_ev:>6} {obs:>+8.2%} {mu:>+7.2%} ±{sd:>6.2%} {z:>6.2f} {p:>7.4f}  {verdict}")
    print(f"multiplicity: {tested} strategies tested → Bonferroni-adjust p by ×{tested} before believing any single row.")

    # Rule (c): sport-regime persistence, regime×band-matched blind baseline.
    print("\nsport-regime persistence (regime-matched baseline, at-fire entry; rule (c): ≥2 regimes > 0)")
    rb_edge = defaultdict(lambda: defaultdict(list))
    for r in blind:
        rb_edge[regime(r["event_slug"])][band(r["entry"])].append(r["won"] - r["entry"])
    rb = {rg: {b: sum(v) / len(v) for b, v in bands.items()} for rg, bands in rb_edge.items()}
    print(f"{'strategy':<18} {'regime':<8} {'events':>6} {'surplus':>9}")
    for s in strategies:
        srows = [r for r in rows if r["strategy"] == s]
        if len({r["ev"] for r in srows}) < 10:
            continue
        by_reg = defaultdict(list)
        for r in srows:
            rg = regime(r["event_slug"])
            base = rb.get(rg, {}).get(band(r["entry"]))
            if base is None:
                continue
            by_reg[rg].append((r["ev"], r["won"] - r["entry"] - base))
        for rg, picks in sorted(by_reg.items(), key=lambda kv: -len(kv[1])):
            ev_map = defaultdict(list)
            for ev, srp in picks:
                ev_map[ev].append(srp)
            means = [sum(v) / len(v) for v in ev_map.values()]
            m = sum(means) / len(means)
            print(f"{s:<18} {rg:<8} {len(means):>6} {m:>+8.2%}")

    # F6 readout: flat-$ vs flat-SHARES paper P&L at the realizable entry proxy.
    print("\nsizing discipline (flat-$100 vs flat-100-shares; entry = at-fire + 1¢ haircut, fee 2%)")
    print(f"{'strategy':<18} {'bets':>5} {'flat-$ pnl':>11} {'flat-shares pnl':>16}")
    for s in strategies:
        srows = [r for r in rows if r["strategy"] == s]
        if len(srows) < 10:
            continue
        fd = fs = 0.0
        for r in srows:
            entry = min(0.999, r["entry"] + 0.01)
            roi = (r["won"] - entry) / entry - 0.02
            fd += 100.0 * roi                                   # $100 per bet
            fs += 100.0 * (r["won"] - entry) - 0.02 * 100.0 * entry  # 100 shares per bet
        print(f"{s:<18} {len(srows):>5} {fd:>+10.0f}$ {fs:>+15.0f}$")


if __name__ == "__main__":
    main()
