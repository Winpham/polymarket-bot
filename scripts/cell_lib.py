#!/usr/bin/env python3
"""
CELL-LIBRARY — shared taxonomy + realizability + objective helpers for the
Generalize-the-Band-Strategy run (2026-07-11).

A *cell* = (category × sport/discipline × price-band × trader-cohort). This module gives the
deterministic, no-fitting classifiers and the LOCKED objective math shared by `cell_map.py`
(phase 1 enumeration + power flags) and `cell_scan.py` (phase 2 edge measurement) so the two
NEVER drift. Everything here is read-only.

The objective (RUN-GENERALIZE-BAND-STRATEGY §0.5, frozen — no re-derivation):
  maximize the CLUSTER-ROBUST one-sided 95% LOWER BOUND of realizable, COPYABLE ROI-on-turnover
  at the MATCH super-key, subject to volume + duration + disjoint-regime floors, belief-blind
  (surplus over the `_blind` favorite at the same cell), that BEATS/COMPLEMENTS the champion
  `favorite` 0.71-0.98. Win rate + total P&L are DIAGNOSTICS ONLY (the two traps the run rejects).

Realizability ladder (the copyability cap — a sharp's early fill is NOT ours):
  entry_ask  — executable best ASK captured once on the live signal (leak-free, set-once).
  tape_ask   — clob_price_tape best_ask at/after convergence (executable; only ~72h retained).
  sharp_fill — the sharps' own mean fill; DIRECTIONAL ceiling ONLY, never the objective.
"""

import math
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from superkey import super_event                       # noqa: E402
from effective_n import cluster_robust, _t_ppf          # noqa: E402

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q", "-t", "-A", "-F", "\t"]

GO_LIVE = "2026-06-29"
FEE_K = 0.03
ALPHA = 0.05
# floors (frozen, inherited from the soft-market prereg §3)
VOL_FLOOR = 20          # ≥20 match-clusters or INDETERMINATE (never "best"/"worst")
SIG_FLOOR_PER_DAY = 3   # ≥~3 signals/active-day → deployable
DUR_FLOOR_DAYS = 7      # ≥7 distinct active days: one tournament weekend is NOT a strategy
REGIME_FLOOR = 2        # ≥2 disjoint non-expiring regimes
REGIME_SUBFLOOR = 8     # min match-clusters a sub-regime needs to count

# price bands (~0.10-wide; NEVER finer — settled overfit finding). 0.65-0.71 = efficient coinflips.
BANDS = [("a_55_65", 0.55, 0.65), ("b_65_71", 0.65, 0.71), ("c_71_82", 0.71, 0.82),
         ("d_82_90", 0.82, 0.90), ("e_90_98", 0.90, 0.98)]
CHAMP_LO, CHAMP_HI = 0.71, 0.98        # the champion pooled band

# trader cohorts (eligibility-rank bands). top40 == consensus_eligible (verified live).
COHORTS = [("top40", 1, 40), ("r41_100", 41, 100), ("r101_250", 101, 250), ("wide_1_250", 1, 250)]

# category by event_slug prefix (structured) — reuses market_taxonomy's mapping, sports-first.
_CAT = [
    (r"^(atp|wta|itf)", "tennis"),
    (r"^(fifwc|world|epl|uefa|mls|laliga|seriea|bund|mar1|bra2|chi|crint|ligue|erediv)", "soccer"),
    (r"^(mlb|kbo|npb)", "baseball"),
    (r"^(nba|wnba|ncaab|cbb|bkfiba)", "basketball"),
    (r"^(nfl|ncaaf|cfb)", "football"),
    (r"^(nhl|khl|hok)", "hockey"),
    (r"^(lol|cs2|csgo|cs-|val|valorant|dota2|dota|r6|co-|ow-|rl-)", "esports"),
    (r"^(btc|eth|sol|xrp|bnb|doge|hype|bitcoin|ethereum|solana|ada|avax)", "crypto"),
]
import re as _re
_CAT_RE = [(_re.compile(p), n) for p, n in _CAT]

# esports disciplines — the disjoint-regime axis within esports.
_DISC = ("dota2", "dota", "csgo", "cs2", "valorant", "val", "lol", "r6", "co-", "ow-", "rl-")


def q(sql):
    out = subprocess.run(PG + ["-c", sql], capture_output=True, text=True)
    if out.returncode != 0:
        sys.stderr.write(out.stderr)
        raise SystemExit(f"psql failed: {out.stderr[:400]}")
    return [r.split("\t") for r in out.stdout.strip().splitlines() if r.strip()]


def category(event_slug, slug=""):
    s = (event_slug or slug or "").lower().strip()
    for rx, name in _CAT_RE:
        if rx.match(s):
            return name
    return "nonsport"


def discipline(event_slug):
    """esports discipline for the disjoint-regime check; for non-esports the regime axis is
    the tournament/date week (see regime_key)."""
    s = (event_slug or "")
    for d in _DISC:
        if s.startswith(d):
            return {"dota": "dota2", "csgo": "cs2", "valorant": "val", "co-": "cod",
                    "ow-": "ow", "rl-": "rl"}.get(d, d)
    return "other"


def regime_key(event_slug, slug):
    """A disjoint NON-EXPIRING regime label for the LODO jackknife. For esports = discipline
    (distinct metas). For other sports = the ISO week of the match date (a tournament weekend is
    one regime; two disjoint weeks = two regimes) — so 'survives only in its dominant week' is
    caught exactly like 'survives only in its dominant discipline'."""
    cat = category(event_slug, slug)
    if cat == "esports":
        return "esports:" + discipline(event_slug)
    base = super_event(event_slug, slug) or ""
    m = _re.search(r"(\d{4})-(\d{2})-(\d{2})", base)
    if not m:
        return cat + ":dateless"
    # ISO-week bucket without importing datetime arithmetic pitfalls: year + week-of-year
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    doy = (mo - 1) * 30 + d          # coarse day-of-year; only needs to bucket into ~weekly blocks
    return f"{cat}:{y}w{doy // 7:02d}"


def band_of(p):
    for name, lo, hi in BANDS:
        if lo <= p < hi:
            return name
    return "e_90_98" if p >= 0.98 else None


def fee(p):
    return FEE_K * p * (1.0 - p)


def pnl(entry, won):
    return (1.0 - entry if won else -entry) - fee(entry)


def mkey(r):
    return super_event(r.get("event_slug"), r.get("slug")) or r.get("condition_id")


def roi_lb(rows, alpha=ALPHA):
    """LOCKED objective: cluster-robust one-sided (1-alpha) LB of ROI-on-turnover at the MATCH
    super-key. rows: [{entry,won,event_slug,slug,condition_id}]. Per-market event surplus =
    Σpnl/Σstake so the LB is on turnover itself. None if <2 events."""
    ev_pnl, ev_stk, ev_cl = defaultdict(float), defaultdict(float), {}
    for r in rows:
        ev = r["condition_id"]
        ev_pnl[ev] += pnl(r["entry"], r["won"])
        ev_stk[ev] += r["entry"]
        ev_cl[ev] = mkey(r)
    ev_roi = {e: ev_pnl[e] / ev_stk[e] for e in ev_pnl if ev_stk[e] > 0}
    if len(ev_roi) < 2:
        return None
    cr = cluster_robust(ev_roi, {e: ev_cl[e] for e in ev_roi})
    if cr is None:
        return None
    if not (cr.get("se_CR") == cr.get("se_CR")) or cr.get("se_CR") is None:   # nan / single-cluster
        point = sum(ev_roi.values()) / len(ev_roi)
        return {"point": point, "lb": None, "N_events": len(ev_roi),
                "G_clusters": cr.get("G", 1), "note": "single cluster — LB undefined"}
    df = max(cr["G"] - 1, 1)
    t = _t_ppf(1 - alpha, df)
    return {"point": cr["theta"], "lb": cr["theta"] - t * cr["se_CR"], "se_CR": cr["se_CR"],
            "N_events": cr["N"], "G_clusters": cr["G"], "t_crit": t}


def bootstrap_lb(rows, draws=2000, alpha=ALPHA, seed=20260711):
    """Second-opinion: resample MATCH clusters with replacement, recompute ROI-turn, take the
    alpha-percentile. Guards the t-based LB against small-G miscalibration."""
    import numpy as np
    cl = defaultdict(list)
    for r in rows:
        cl[mkey(r)].append(r)
    clusters = list(cl.values())
    G = len(clusters)
    if G < 2:
        return None
    rng = np.random.default_rng(seed)
    idx = np.arange(G)
    pts = []
    for _ in range(draws):
        pick = rng.choice(idx, size=G, replace=True)
        num = den = 0.0
        for j in pick:
            for r in clusters[j]:
                num += pnl(r["entry"], r["won"])
                den += r["entry"]
        if den > 0:
            pts.append(num / den)
    if not pts:
        return None
    pts.sort()
    return {"point": float(np.mean(pts)), "lb": float(pts[int(alpha * len(pts))]), "draws": len(pts), "G": G}


def win_rate(rows):
    n = len(rows)
    return (sum(1 for r in rows if r["won"]) / n) if n else None


def power_flags(rows):
    """Volume + duration + disjoint-regime power, computed identically everywhere. Returns a
    dict of the three booleans + the diagnostics, so a cell reads INDETERMINATE (not best/worst)
    until ALL floors are met."""
    matches = {mkey(r) for r in rows}
    active_days = {(r.get("day") or "")[:10] for r in rows if r.get("day")}
    reg_clusters = defaultdict(set)
    for r in rows:
        reg_clusters[regime_key(r.get("event_slug"), r.get("slug"))].add(mkey(r))
    regimes = [k for k, s in reg_clusters.items() if len(s) >= REGIME_SUBFLOOR]
    return {
        "n_matches": len(matches),
        "active_days": len(active_days),
        "n_regimes_over_subfloor": len(regimes),
        "regimes": sorted(regimes),
        "meets_volume_floor": len(matches) >= VOL_FLOOR,
        "meets_duration_floor": len(active_days) >= DUR_FLOOR_DAYS,
        "meets_regime_floor": len(regimes) >= REGIME_FLOOR,
        "regime_clusters": {k: len(s) for k, s in reg_clusters.items()},
    }
