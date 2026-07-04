#!/usr/bin/env python3
"""
mm_common — shared, read-only DB machinery for the MM-FILTER Phase-1 validation harness
(mm_calibrate.py, mm_persistence_effect.py, mm_reconcile.py).

WHY A SHARED MODULE: the three Phase-1 scripts all need (a) the exact position-grain
microstructure the LIVE screen uses (round_trip_rate / two_sided_rate / sell_buy_ratio),
optionally computed AS-OF a cutoff to kill leakage, and (b) the same psql/CSV access the
existing instruments use (selection_null.PG). Cloning it once here — instead of three times —
mirrors how persistence_tracker imports selection_null/effective_n byte-identically.

This module is READ-ONLY. It never writes the DB, never mutates trader_type, never places an
order. It reproduces the microstructure algebra of `refresh_router_followset`
(common/src/storage/consensus.rs:1587-1610) so Python can score the SAME rates the Rust screen
scores — the two must agree by construction (mm_reconcile asserts the lifetime case).

The LIVE screen (interim, pending this calibration) flags a wallet as a churner (NOT clean) iff
  round_trip_rate >= 0.30 OR two_sided_rate >= 0.25 OR sell_buy_ratio >= 0.50
i.e. a wallet is CLEAN (kept) iff all three are strictly below those thresholds.
"""

import subprocess
import sys
from collections import defaultdict

# Same access path as selection_null.PG / specialist_mining — docker psql, CSV out.
PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q", "-t"]

# LIVE interim thresholds (consensus.rs:1649-1651). A wallet is CLEAN iff all three below.
TAU_RT = 0.30
TAU_2S = 0.25
TAU_SB = 0.50


def q(sql):
    """Run SQL, return list of row-tuples (strings). Mirrors selection_null's subprocess call."""
    out = subprocess.run(PG, input=sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.stderr.write(out.stderr)
        raise RuntimeError(f"psql failed: {out.returncode}")
    rows = []
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append([c.strip() for c in line.split(",")])
    return rows


def _fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def microstructure(asof=None):
    """Per-wallet {rt, ts, sb, vol, n_pos, n_fills} — the EXACT algebra of
    refresh_router_followset's `pos → sided → two → micro` CTEs (consensus.rs:1587-1610),
    plus volume / position-count / fill-count covariates for the matched null.

    asof=None  → lifetime (must reproduce the Rust screen byte-for-byte on the rate columns).
    asof=DATE  → only fills with ts < DATE (UTC) count. This is the leak-free grain the Tier-2
                 test requires: the MM verdict that decides who to remove is computed from
                 EARLY fills only, so it cannot peek at the late outcomes it will be correlated
                 against (brief §4b requirement 2)."""
    where = ""
    if asof is not None:
        where = f"WHERE ts < TIMESTAMP '{asof} 00:00:00+00' "
    sql = f"""
    WITH pos AS (
      SELECT wallet, condition_id, outcome_index,
             COALESCE(SUM(size_usd) FILTER (WHERE side='BUY'),0)  AS buy_usd,
             COALESCE(SUM(size_usd) FILTER (WHERE side='SELL'),0) AS sell_usd,
             COUNT(*) FILTER (WHERE side='BUY')  AS n_buy,
             COUNT(*) FILTER (WHERE side='SELL') AS n_sell
      FROM trader_fills {where} GROUP BY 1,2,3),
    sided AS (SELECT wallet, condition_id, COUNT(*) FILTER (WHERE n_buy>0) AS n_out_held
              FROM pos GROUP BY 1,2),
    two AS (SELECT wallet, AVG((n_out_held>=2)::int)::float8 AS two_sided_rate
            FROM sided GROUP BY 1),
    micro AS (
      SELECT p.wallet,
             AVG((p.n_sell>0 AND p.n_buy>0)::int)::float8 AS round_trip_rate,
             (SUM(LEAST(p.sell_usd,p.buy_usd))/NULLIF(SUM(p.buy_usd),0))::float8 AS sell_buy_ratio,
             t.two_sided_rate,
             SUM(p.buy_usd+p.sell_usd)::float8 AS vol,
             COUNT(*)::int AS n_pos
      FROM pos p JOIN two t USING(wallet) GROUP BY p.wallet, t.two_sided_rate),
    fillcnt AS (SELECT wallet, COUNT(*)::int AS n_fills FROM trader_fills {where} GROUP BY 1)
    SELECT lower(m.wallet), m.round_trip_rate, m.two_sided_rate, m.sell_buy_ratio,
           m.vol, m.n_pos, f.n_fills
    FROM micro m JOIN fillcnt f USING(wallet);
    """
    out = {}
    for r in q(sql):
        w = r[0]
        out[w] = {
            "rt": _fnum(r[1]) or 0.0,
            "ts": _fnum(r[2]) or 0.0,
            "sb": _fnum(r[3]) or 0.0,
            "vol": _fnum(r[4]) or 0.0,
            "n_pos": int(float(r[5])) if r[5] else 0,
            "n_fills": int(float(r[6])) if r[6] else 0,
        }
    return out


def is_churner(m, tau_rt=TAU_RT, tau_2s=TAU_2S, tau_sb=TAU_SB):
    """True iff the screen FLAGS this wallet (NOT clean). Mirrors the negation of the live
    keep-clause: kept iff rt<tau_rt AND ts<tau_2s AND sb<tau_sb."""
    return not (m["rt"] < tau_rt and m["ts"] < tau_2s and m["sb"] < tau_sb)


def wallet_event_surplus(asof_lo=None, asof_hi=None):
    """Per (wallet, event) blind-baselined surplus rows, split-ready by placement day.

    Reproduces the surplus convention of trader_slice_scores (consensus.rs:1499-1515):
      a          = outcome_won - price          (directional advantage of a BUY fill)
      blind_edge = AVG(a) per price band (width_bucket 5), over the fleet
      surplus    = a - blind_edge[band]
    Event-clustered at COALESCE(event_slug, condition_id); day = UTC placement day (ts), NOT
    resolved_at — the early/late split is by WHEN THE PICK WAS MADE, which is what "does this
    trader's early selection predict their late selection" means, and keeps early and late as
    disjoint pick sets (no outcome leakage across the split).

    Returns list of dicts: {wallet, ev, event_slug, band, a, surplus, day}.
    asof_lo/asof_hi bound the placement ts (both optional, ISO date strings)."""
    bounds = ["resolved AND side='BUY' AND outcome_won IS NOT NULL"]
    if asof_lo is not None:
        bounds.append(f"ts >= TIMESTAMP '{asof_lo} 00:00:00+00'")
    if asof_hi is not None:
        bounds.append(f"ts < TIMESTAMP '{asof_hi} 00:00:00+00'")
    where = " AND ".join(bounds)
    sql = f"""
    WITH adv AS (
      SELECT lower(wallet) AS wallet, COALESCE(event_slug, condition_id) AS ev, event_slug,
             width_bucket(price,0.0,1.0,5) AS band,
             (outcome_won::int)::float8 - price AS a,
             (ts AT TIME ZONE 'UTC')::date AS day
      FROM trader_fills WHERE {where}),
    blind AS (SELECT band, AVG(a) AS be FROM adv GROUP BY band)
    SELECT v.wallet, v.ev, COALESCE(v.event_slug,''), v.band, v.a,
           v.a - COALESCE(b.be,0) AS surplus, v.day
    FROM adv v LEFT JOIN blind b USING(band);
    """
    rows = []
    for r in q(sql):
        rows.append({
            "wallet": r[0], "ev": r[1], "event_slug": r[2],
            "band": int(float(r[3])) if r[3] else 0,
            "a": _fnum(r[4]) or 0.0, "surplus": _fnum(r[5]) or 0.0, "day": r[6],
        })
    return rows


def all_days():
    """Sorted distinct UTC placement days over resolved BUY fills (for choosing a cutoff)."""
    rows = q("SELECT DISTINCT (ts AT TIME ZONE 'UTC')::date d FROM trader_fills "
             "WHERE resolved AND side='BUY' AND outcome_won IS NOT NULL ORDER BY d;")
    return [r[0] for r in rows if r and r[0]]
