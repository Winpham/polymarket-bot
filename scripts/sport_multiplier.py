#!/usr/bin/env python3
"""
SPORT MULTIPLIER → reports/kernel_gate.json — the belief-blind per-sport size gate.

Collapses "condition the system per sport" into a per-cell SIZE COEFFICIENT the
`decide()` kernel already multiplies by (`m_sport`). Conditioning becomes "bet 0
on soccer-skill (soft World-Cup artifact), full on MLB-skill (real, near-efficient)
ONCE it proves durable" — with NO new Rust arm, no new signal rows.

A sport earns `m_sport = 1.0` ONLY if it clears the FULL belief-blind gate — the
standing defense against the `market_resid` false-promote class. ALL of:
  (a) N ≥ N_FLOOR (20) distinct events,
  (b) selection-matched null p ≤ 0.01 with ≥ MIN_DRAWS (1000) matched draws
      (`selection_null` machinery — isolates SELECTION skill from composition),
  (c) ≥ 2 NON-EXPIRING time-regimes with positive event-clustered surplus
      (World Cup / Wimbledon are pre-registered EXPIRING → excluded → those
      sports score 0 regimes today; this is the persistence wall),
  (d) Bonferroni-corrected (×#sports tested) lower bound, K_POOL=40 partial-
      pooling-shrunk, still > 0.
Any failure → 0.0. Unlisted sports are fail-closed 0.0 in the kernel itself.

CLASSIFIER ALIGNMENT (load-bearing): sports are keyed by `kernel_sport()`, an
EXACT mirror of Rust `scanner::decide::sport_of` (event_slug-first, 6-way
crypto/tennis/soccer/mlb/cs2/other) — so every emitted key is one the kernel can
look up. Certifying in a finer partition than the kernel sizes in would silently
fail-closed a real edge.

readiness_fraction (Item 3): read from reports/clv_lambda_marketkey.json.
  edge_reality INDETERMINATE (coverage < 50% OR verdict INDETERMINATE) → 0.0 (k=0)
  MET (coverage ≥ 50% AND λ CI lower > 0)                              → 1.0
  NOT_MET                                                              → 0.0
Today: coverage ≈ 20% < 50% → INDETERMINATE → 0.0. The sized book runs an
unconditioned k=0 SHADOW; the kernel flips to Kelly by THIS field alone when a
human certifies forward true-close λ̂.

Modes:
  ./sport_multiplier.py               # live: query DB, write reports/kernel_gate.json
  ./sport_multiplier.py --selftest    # no DB: prove the gate is fail-closed + belief-blind
  ./sport_multiplier.py --dry-run     # live compute, print JSON, do NOT write the file
"""

import datetime
import json
import math
import os
import random
import sys
from collections import defaultdict
from statistics import NormalDist

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import selection_null as SN  # noqa: E402  (null machinery: band, clustered_surplus, null_pvalue)

# --- pre-registered gate constants (applied, never fit) ---
N_FLOOR = 20            # sport_edge_tracker.N_FLOOR — distinct-event floor
P_BAR = 0.01            # selection_null.P_BAR — belief-blind gate
MIN_DRAWS = 1000        # selection_null minimum matched null draws
MIN_REGIMES = 2         # rule (c): ≥2 non-expiring time-regimes with positive surplus
K_POOL = 40.0           # slice_pooled_quality partial-pooling constant (consensus_cycle.rs)
ALPHA = 0.05            # base one-sided confidence level (Bonferroni-split across sports)
READOUT_FLOOR = 10      # a sport is "tested" (counts toward Bonferroni) at ≥10 events
COVERAGE_GATE = 0.50    # clv coverage floor for edge_reality = MET

# Sports whose ENTIRE current sample is a single expiring tournament (pre-registered
# 2026 summer: soccer = World Cup, tennis = Wimbledon). They score 0 non-expiring
# regimes until non-tournament events accrue — the persistence wall. Documented so a
# future non-tournament tennis/soccer sample is NOT wrongly excluded.
EXPIRING_SPORTS_NOW = {"soccer", "tennis"}

LAMBDA_REPORT = "reports/clv_lambda_marketkey.json"
GATE_OUT = "reports/kernel_gate.json"


def kernel_sport(event_slug, slug):
    """EXACT mirror of Rust scanner::decide::sport_of — event_slug-first, 6-way.
    Keys emitted here MUST match what the kernel derives, or the lookup fail-closes."""
    s = (event_slug or "").strip() or (slug or "")
    crypto = ("btc", "eth", "sol", "xrp", "bnb", "doge", "hype", "bitcoin", "ethereum")
    tennis = ("atp", "wta", "itf")
    if s.startswith(crypto):
        return "crypto"
    if s.startswith(tennis):
        return "tennis"
    if s.startswith("fifwc"):
        return "soccer"
    if s.startswith("mlb"):
        return "mlb"
    if s.startswith("cs"):
        return "cs2"
    return "other"


def evk(r):
    """Match-level cluster key (super_event), condition_id fallback — as SN uses."""
    from superkey import super_event
    return super_event(r.get("event_slug"), r.get("slug")) or r["condition_id"]


def iso_week(day):
    y, m, d = (int(x) for x in day.split("-"))
    iso = datetime.date(y, m, d).isocalendar()
    return (iso[0], iso[1])


def _bonferroni_lb(mean, se, n_sports):
    """One-sided lower confidence bound with Bonferroni-split alpha over #sports.
    Wider (more conservative) the more sports we test. Non-finite se (n<2, unknown
    spread) → -inf (fails closed). se == 0 (all events agree) → LB = mean."""
    if not math.isfinite(se) or se < 0:
        return float("-inf")
    alpha = ALPHA / max(n_sports, 1)
    z = NormalDist().inv_cdf(1.0 - alpha)
    return mean - z * se


def certify_sport(sport, fav_rows, sport_blind_rows, rb_edge_band, rng, n_sports):
    """Return (m_sport in {0.0, 1.0}, diagnostics dict). Fail-closed on ANY gap.
    `rb_edge_band`: {band: blind_edge} for THIS sport (the surplus baseline).
    `sport_blind_rows`: this sport's `_blind` universe (the null draws from it)."""
    diag = {"sport": sport}

    # event-clustered skill (surplus over this sport's band baseline) + its SE
    ev_map = defaultdict(list)
    for r in fav_rows:
        a = (r["won"] - r["entry"]) - rb_edge_band.get(SN.band(r["entry"]), 0.0)
        ev_map[evk(r)].append(a)
    event_means = [sum(v) / len(v) for v in ev_map.values()]
    n = len(event_means)
    diag["events"] = n
    if n == 0:
        diag["reason"] = "no events"
        return 0.0, diag
    skill = sum(event_means) / n
    diag["skill"] = skill
    if n >= 2:
        var = sum((x - skill) ** 2 for x in event_means) / (n - 1)
        se = math.sqrt(var / n)
    else:
        se = float("inf")

    # (a) event floor
    if n < N_FLOOR:
        diag["reason"] = f"N {n} < floor {N_FLOOR}"
        return 0.0, diag

    # (b) belief-blind selection-matched null over THIS sport's blind universe
    blind_cells = defaultdict(list)
    for r in sport_blind_rows:
        blind_cells[(SN.band(r["entry"]), r["day"])].append((evk(r), r["won"] - r["entry"]))
    picks = [(evk(r), SN.band(r["entry"]), r["won"] - r["entry"]) for r in fav_rows]
    obs, _ = SN.clustered_surplus(picks, rb_edge_band)
    meta = [(SN.band(r["entry"]), r["day"]) for r in fav_rows]
    draws = SN.null_pvalue(meta, blind_cells, rb_edge_band, rng, N_PERM)
    diag["null_draws"] = len(draws)
    if len(draws) < MIN_DRAWS:
        diag["reason"] = f"null unmatchable ({len(draws)} < {MIN_DRAWS} draws)"
        return 0.0, diag
    p = sum(1 for x in draws if x >= obs) / len(draws)
    diag["p"] = p
    if p > P_BAR:
        diag["reason"] = f"belief-blind p {p:.4f} > {P_BAR}"
        return 0.0, diag

    # (c) ≥2 non-expiring time-regimes with positive event-clustered surplus
    if sport in EXPIRING_SPORTS_NOW:
        diag["non_expiring_regimes"] = 0
        diag["reason"] = "expiring tournament (World Cup / Wimbledon) — 0 non-expiring regimes"
        return 0.0, diag
    by_week = defaultdict(list)
    for r in fav_rows:
        by_week[iso_week(r["day"])].append(r)
    pos_regimes = 0
    for _, rs in by_week.items():
        wk_picks = [(evk(r), SN.band(r["entry"]), r["won"] - r["entry"]) for r in rs]
        wk_surplus, _ = SN.clustered_surplus(wk_picks, rb_edge_band)
        if math.isfinite(wk_surplus) and wk_surplus > 0:
            pos_regimes += 1
    diag["non_expiring_regimes"] = pos_regimes
    if pos_regimes < MIN_REGIMES:
        diag["reason"] = f"{pos_regimes} non-expiring positive regimes < {MIN_REGIMES}"
        return 0.0, diag

    # (d) Bonferroni-corrected, K_POOL-shrunk lower bound > 0
    lb = _bonferroni_lb(skill, se, n_sports)
    w = n / (n + K_POOL)  # partial-pooling shrinkage toward 0
    diag.update(bonferroni_lb=lb, pool_w=w, shrunk_lb=w * lb)
    if not (w * lb > 0.0):
        diag["reason"] = f"shrunk Bonferroni LB {w * lb:+.4f} ≤ 0"
        return 0.0, diag

    diag["reason"] = "CERTIFIED"
    return 1.0, diag


N_PERM = 2000  # matched null draws attempted per sport (selection_null default)
SEED = 20260702


def readiness_fraction():
    """Map edge_reality → readiness. INDETERMINATE/NOT_MET → 0.0; MET → 1.0."""
    try:
        with open(LAMBDA_REPORT) as f:
            rep = json.load(f)
    except (OSError, json.JSONDecodeError):
        return 0.0, "INDETERMINATE (λ report unreadable)"
    cov = rep.get("trajectory_coverage", 0.0)
    verdict = str(rep.get("verdict", ""))
    lam_ci = rep.get("lambda_ci") or [None, None]
    if cov < COVERAGE_GATE or verdict.startswith("INDETERMINATE"):
        return 0.0, (f"INDETERMINATE (coverage {cov:.0%} < {COVERAGE_GATE:.0%}; "
                     f"λ̂={rep.get('lambda_hat')})")
    if lam_ci[0] is not None and lam_ci[0] > 0:
        return 1.0, f"MET (coverage {cov:.0%}, λ CI lower {lam_ci[0]:+.3f} > 0)"
    return 0.0, f"NOT_MET (coverage {cov:.0%} but λ CI lower {lam_ci[0]})"


def compute(rows, strat="favorite"):
    """Full gate over live rows. Returns the kernel_gate dict."""
    rng = random.Random(SEED)
    blind = [r for r in rows if r["strategy"] == "_blind"]
    fav = [r for r in rows if r["strategy"] == strat]

    # per-(sport,band) blind baseline (the surplus reference) + per-sport blind pool
    rb = defaultdict(list)
    blind_by_sport = defaultdict(list)
    for r in blind:
        sp = kernel_sport(r.get("event_slug"), r.get("slug"))
        rb[(sp, SN.band(r["entry"]))].append(r["won"] - r["entry"])
        blind_by_sport[sp].append(r)
    rb_edge = {k: sum(v) / len(v) for k, v in rb.items()}

    fav_by_sport = defaultdict(list)
    for r in fav:
        fav_by_sport[kernel_sport(r.get("event_slug"), r.get("slug"))].append(r)

    # #sports tested (Bonferroni denominator): distinct-event count ≥ readout floor
    def n_events(rs):
        return len({evk(r) for r in rs})
    n_sports = sum(1 for rs in fav_by_sport.values() if n_events(rs) >= READOUT_FLOOR) or 1

    sport_mult, certified, diags = {}, [], []
    for sport in sorted(fav_by_sport):
        rb_band = {b: rb_edge.get((sport, b), 0.0) for b in range(7)}
        m, diag = certify_sport(
            sport, fav_by_sport[sport], blind_by_sport.get(sport, []), rb_band, rng, n_sports
        )
        sport_mult[sport] = m
        diags.append(diag)
        if m > 0:
            certified.append(sport)

    frac, edge_reality = readiness_fraction()
    return {
        "sport_mult": sport_mult,
        "readiness_fraction": frac,
        "edge_reality": edge_reality,
        "certified_cells": certified,
        "n_sports_tested": n_sports,
        "strategy": strat,
        "gate": {
            "N_FLOOR": N_FLOOR, "P_BAR": P_BAR, "MIN_DRAWS": MIN_DRAWS,
            "MIN_REGIMES": MIN_REGIMES, "K_POOL": K_POOL, "ALPHA": ALPHA,
        },
        "diagnostics": diags,
        "as_of": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "note": ("k=0 shadow posture: with readiness_fraction=0.0 the kernel books stake=0 for "
                 "every sport regardless of sport_mult. sport_mult is fail-closed (unlisted → 0.0)."),
    }


def run_live(write):
    # reuse sport_edge_tracker.fetch (has slug, event_slug, condition_id, entry, won, day)
    import sport_edge_tracker as SET
    rows = SET.fetch()
    gate = compute(rows)
    print(json.dumps(gate, indent=2))
    if write:
        with open(GATE_OUT, "w") as f:
            json.dump(gate, f, indent=2)
            f.write("\n")
        print(f"\nwrote {GATE_OUT}")
    return 0


# --- self-test (no DB): the gate is fail-closed and belief-blind -----------------------------
def _mk(strategy, sport_slug, entry, won, i, day="2026-07-01"):
    return dict(strategy=strategy, event_slug=f"{sport_slug}-{i}", slug=f"{sport_slug}-{i}",
                condition_id=f"{sport_slug}-{i}", entry=entry, won=won, day=day)


def _self_test():
    ok = True
    # Build a synthetic universe:
    #  - soccer (fifwc): blind favs @0.80 win 92% (soft); strategy tracks pool (skill≈0) →
    #    must be 0.0 (soft-only) AND expiring (World Cup) → 0 regimes.
    #  - mlb: blind favs @0.80 win 80% (efficient); strategy wins 92% (real skill) BUT all on
    #    ONE week → fails the ≥2-non-expiring-regime persistence wall → 0.0 today.
    #  - mlb2 (mlb across 3 weeks, still efficient + skilled) → certifies 1.0.
    rows = []
    # soccer: unique events so N clears; strategy skill ~0
    rows += [_mk("_blind", "fifwc-a-b", 0.80, 1 if i < 46 else 0, i) for i in range(60)]
    rows += [_mk("favorite", "fifwc-a-b", 0.80, 1 if i < 23 else 0, 1000 + i) for i in range(25)]
    # mlb single-week: efficient blind, skilled strategy, one week only
    rows += [_mk("_blind", "mlb-c-d", 0.80, 1 if i < 48 else 0, i, day="2026-07-01") for i in range(60)]
    rows += [_mk("favorite", "mlb-c-d", 0.80, 1, 2000 + i, day="2026-07-01") for i in range(25)]

    gate = compute(rows)
    sm = gate["sport_mult"]
    # soccer fail-closed (expiring + soft)
    c1 = sm.get("soccer", 1.0) == 0.0
    ok = ok and c1
    soc_reason = next(d["reason"] for d in gate["diagnostics"] if d["sport"] == "soccer")
    print(f"  [{'ok' if c1 else 'FAIL'}] soccer m=0.0  ({soc_reason})")
    # mlb single-week fails the persistence wall (or an earlier gate) → 0.0
    c2 = sm.get("mlb", 1.0) == 0.0
    ok = ok and c2
    mlb_reason = next(d["reason"] for d in gate["diagnostics"] if d["sport"] == "mlb")
    print(f"  [{'ok' if c2 else 'FAIL'}] mlb single-week m=0.0  ({mlb_reason})")
    # readiness fail-closed when the λ report is INDETERMINATE / absent
    c3 = gate["readiness_fraction"] == 0.0
    ok = ok and c3
    print(f"  [{'ok' if c3 else 'FAIL'}] readiness_fraction=0.0  ({gate['edge_reality']})")
    # kernel_sport mirrors Rust sport_of exactly on the cells that matter
    c4 = (kernel_sport("mlb-laa-sea-2026-06-30", "x") == "mlb"
          and kernel_sport("fifwc-bel-sen-2026-07-01", "x") == "soccer"
          and kernel_sport("atp-x-2026", "x") == "tennis"
          and kernel_sport("btc-updown", "x") == "crypto"
          and kernel_sport("", "mlb-nyy-2026-07-01") == "mlb"
          and kernel_sport("nba-lal-2026", "x") == "other")
    ok = ok and c4
    print(f"  [{'ok' if c4 else 'FAIL'}] kernel_sport mirrors Rust sport_of")
    # multi-week efficient+skilled mlb DOES certify (proves the gate can say yes, not just no).
    # blind @0.80 win 80% (efficient, edge≈0); strategy win 90% (skill +10%); across 3 weeks.
    weeks = ["2026-07-01", "2026-07-08", "2026-07-15"]
    rows2 = [_mk("_blind", "mlb-c-d", 0.80, 1 if i % 5 != 0 else 0, i, day=weeks[i % 3])
             for i in range(150)]  # 80% win, efficient
    rows2 += [_mk("favorite", "mlb-c-d", 0.80, 1 if i % 20 != 0 else 0, 3000 + i, day=weeks[i % 3])
              for i in range(40)]  # 95% win → +15% skill over the efficient blind
    m_mlb2, d_mlb2 = None, None
    g2 = compute(rows2)
    m_mlb2 = g2["sport_mult"].get("mlb")
    d_mlb2 = next(d for d in g2["diagnostics"] if d["sport"] == "mlb")
    c5 = m_mlb2 == 1.0
    ok = ok and c5
    print(f"  [{'ok' if c5 else 'FAIL'}] multi-week efficient+skilled mlb CERTIFIES m=1.0 "
          f"(p={d_mlb2.get('p')}, regimes={d_mlb2.get('non_expiring_regimes')})")
    print("SELF-TEST", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(0 if _self_test() else 1)
    sys.exit(run_live(write="--dry-run" not in sys.argv))
