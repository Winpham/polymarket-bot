#!/usr/bin/env python3
"""
GARBAGE SEGMENTS — read-only multi-axis decomposition of the `favorite` champion book.

Purpose (RUN-GARBAGE-EXCLUSION-FILTERS): reproduce the §0 seed table AND emit the full
multi-axis slice map that the policy-search loop consumes. Every slice is scored on the
CORRECTED fee model and, where meaningful, the belief-blind selection surplus — so a slice is
never cut on P&L alone.

Accounting convention (LOCKED — reproduces RUN-HARDEN-FAVORITE-EDGE §0 "+2.8% taker"):
  entry p    = COALESCE(initial_mean_price, mean_price)            # at-fire entry (selection_null)
  won        = honest_paper_ledger.outcome_won                    # resolved truth
  shares     = 100 (flat shares)
  fee_taker  = 100 * feeRate(category) * p * (1-p)                # entry-only; makers pay 0
  pnl_taker  = [won? 100*(1-p) : -100*p] - fee_taker
  turnover   = $100 / bet (nominal)  →  ROI = Σpnl / (100 * n)     # the canonical baseline basis
  (Secondary: stake-weighted ROI = Σpnl / Σ(100*p) is printed alongside for honesty.)

feeRate by taxonomy category (docs.polymarket.com/trading/fees, 2026-07; mirror of
fee_schedule_sensitivity): sports 0.03, politics 0.04, econ/other 0.05, crypto 0.07.
The champion book is ~all sports, so 0.03 dominates; category-awareness only affects stray
crypto/politics fires.

Belief-blind selection surplus (per slice): mean over event-clusters of (a - blind_edge[band]),
a = won - entry, blind_edge[band] = mean (won-entry) of the `_blind` population in that price band.
Exact statistic of selection_null.clustered_surplus — so a slice's surplus is comparable to the
champion's +8.06%. A NEGATIVE-ROI slice whose surplus is still POSITIVE is a PRICE-COMPOSITION
loss (favorite-longshot), not a selection failure — a mechanism flag, not a cut on its own.

Read-only. Paper-only. Writes reports/GARBAGE-SEGMENTS.json. No DB writes, no network, no LLM.

  ./garbage_segments.py               # full report + JSON
  ./garbage_segments.py --self-test   # accounting fixtures + §0-anchor reproduction
"""

import csv
import io
import json
import math
import os
import subprocess
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import selection_null as sn          # band(), clustered_surplus(), PG, REGIMES, regime()
import market_taxonomy as mtx        # category(), _classify_mtype_fine(), market_type()

PG = sn.PG
REPORT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "reports", "GARBAGE-SEGMENTS.json")
SHARES = 100.0

# category → taker feeRate (sports family collapses to 0.03; the anchor uses 0.03 throughout)
_SPORTS = {"tennis", "soccer", "mlb", "nfl/cfb", "nba/cbb", "nhl", "esports", "cs2"}
def fee_rate(cat):
    if cat in _SPORTS:
        return 0.03
    if cat == "politics/elections":
        return 0.04
    if cat == "crypto":
        return 0.07
    return 0.05  # econ/other / other


# ---- accounting ---------------------------------------------------------------------------
def pnl_taker(p, won, cat):
    fee = SHARES * fee_rate(cat) * p * (1.0 - p)
    return (SHARES * (1.0 - p) if won else -SHARES * p) - fee

def pnl_maker(p, won):
    return SHARES * (1.0 - p) if won else -SHARES * p


# ---- fetch: favorite book (ledger ⋈ signals) + the full _blind population ------------------
SQL_BOOK = """
SELECT s.condition_id, s.outcome_index,
       s.event_slug, s.slug, s.title,
       COALESCE(s.initial_mean_price, s.mean_price)          AS entry,
       (l.outcome_won::int)                                  AS won,
       s.recency_mins, s.initial_recency_mins,
       s.total_usd,   s.initial_total_usd,
       s.n_backers,   s.initial_n_backers,
       s.best_backer_rank, s.initial_best_backer_rank,
       s.mean_price, s.entry_ask, s.entry_ask_mid,
       s.net_count, s.net_quality,
       to_char(s.first_detected_at AT TIME ZONE 'UTC','YYYY-MM-DD') AS day
FROM honest_paper_ledger l
JOIN consensus_signals s USING (strategy, condition_id, outcome_index)
WHERE l.strategy = 'favorite'
"""

SQL_BLIND = """
SELECT COALESCE(initial_mean_price, mean_price) AS entry, (outcome_won::int) AS won,
       COALESCE(event_slug, condition_id) AS ev
FROM consensus_signals WHERE resolved AND strategy = '_blind'
"""

def _psql(sql):
    out = subprocess.run(PG + ["-f", "-"], input=sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    return list(csv.DictReader(io.StringIO(out.stdout)))

def _f(v):
    return None if v in (None, "", "\\N") else float(v)

def load_book():
    rows = []
    for r in _psql(SQL_BOOK):
        p = _f(r["entry"])
        if p is None:
            continue
        cat = mtx.category(r["slug"], r["title"])
        fine = mtx._classify_mtype_fine(r["slug"], r["title"])
        mt = mtx.market_type(r["slug"], r["title"])
        won = int(r["won"])
        rows.append({
            "cond": r["condition_id"], "oi": r["outcome_index"],
            "event_slug": r["event_slug"] or "", "slug": r["slug"] or "",
            "title": r["title"] or "", "entry": p, "won": won,
            "recency_mins": _f(r["recency_mins"]),
            "init_recency": _f(r["initial_recency_mins"]),
            "total_usd": _f(r["total_usd"]), "init_total_usd": _f(r["initial_total_usd"]),
            "n_backers": _f(r["n_backers"]), "init_n_backers": _f(r["initial_n_backers"]),
            "rank": _f(r["best_backer_rank"]), "init_rank": _f(r["initial_best_backer_rank"]),
            "mean_price": _f(r["mean_price"]), "entry_ask": _f(r["entry_ask"]),
            "entry_ask_mid": _f(r["entry_ask_mid"]),
            "net_count": _f(r["net_count"]), "net_quality": _f(r["net_quality"]),
            "day": r["day"], "cat": cat, "fine": fine, "mt": mt,
            "band": sn.band(p),
            "surplus_a": won - p,
            "pnl_t": pnl_taker(p, won, cat),
            "pnl_m": pnl_maker(p, won),
        })
    return rows

def load_blind_edge():
    band_edge = defaultdict(list)
    for r in _psql(SQL_BLIND):
        p = _f(r["entry"])
        if p is None:
            continue
        band_edge[sn.band(p)].append(int(r["won"]) - p)
    return {b: sum(v) / len(v) for b, v in band_edge.items()}


# ---- slice scoring ------------------------------------------------------------------------
def score(rows, blind_edge):
    """Return dict of slice metrics on a subset of book rows."""
    n = len(rows)
    if n == 0:
        return dict(n=0)
    wins = sum(r["won"] for r in rows)
    pnl_t = sum(r["pnl_t"] for r in rows)
    pnl_m = sum(r["pnl_m"] for r in rows)
    stake = sum(SHARES * r["entry"] for r in rows)
    roi_t = pnl_t / (SHARES * n)          # canonical: turnover = $100/bet
    roi_m = pnl_m / (SHARES * n)
    roi_t_stake = pnl_t / stake if stake else float("nan")
    picks = [(r["event_slug"] or r["cond"], r["band"], r["surplus_a"]) for r in rows]
    surplus, n_ev = sn.clustered_surplus(picks, blind_edge)
    # bootstrap 95% CI on canonical ROI (resample bets; cheap, deterministic seed)
    lo, hi = _boot_roi_ci(rows)
    return dict(n=n, wins=wins, win_pct=round(100 * wins / n, 1),
                pnl_taker=round(pnl_t, 2), pnl_maker=round(pnl_m, 2),
                roi_taker=round(100 * roi_t, 3), roi_maker=round(100 * roi_m, 3),
                roi_taker_stake=round(100 * roi_t_stake, 3),
                surplus=round(100 * surplus, 3) if surplus == surplus else None,
                n_events=n_ev, ci_lo=round(100 * lo, 3), ci_hi=round(100 * hi, 3))

def _boot_roi_ci(rows, n_boot=2000, seed=20260709):
    import random
    rng = random.Random(seed)
    idx = range(len(rows))
    pnls = [r["pnl_t"] for r in rows]
    n = len(rows)
    means = []
    for _ in range(n_boot):
        s = 0.0
        for _ in range(n):
            s += pnls[rng.randrange(n)]
        means.append(s / (SHARES * n))
    means.sort()
    return means[int(0.025 * n_boot)], means[int(0.975 * n_boot)]


# ---- axes ---------------------------------------------------------------------------------
def obscure_prefix(event_slug):
    """token before first '-' in event_slug (league/discipline code)."""
    s = (event_slug or "").lower()
    return s.split("-", 1)[0] if s else "(none)"

def axis_slices(rows):
    """Yield (axis_name, {slice_label: [rows]})."""
    A = {}
    # sport / regime
    d = defaultdict(list)
    for r in rows:
        d[sn.regime(r["event_slug"])].append(r)
    A["regime"] = d
    # category (taxonomy)
    d = defaultdict(list)
    for r in rows:
        d[r["cat"]].append(r)
    A["category"] = d
    # league prefix
    d = defaultdict(list)
    for r in rows:
        d[obscure_prefix(r["event_slug"])].append(r)
    A["league_prefix"] = d
    # market type fine
    d = defaultdict(list)
    for r in rows:
        d[r["fine"] or "(uncovered)"].append(r)
    A["market_type_fine"] = d
    # market type binary
    d = defaultdict(list)
    for r in rows:
        d[r["mt"] or "(uncovered)"].append(r)
    A["market_type"] = d
    # price sub-band (0.05 bins within 0.65-0.98)
    d = defaultdict(list)
    for r in rows:
        lo = math.floor(r["entry"] / 0.05) * 0.05
        d[f"{lo:.2f}-{lo+0.05:.2f}"].append(r)
    A["price_subband"] = d
    # freshness — AT-FIRE only (initial_recency_mins). LIVE recency_mins is look-ahead
    # contaminated (updated post-fire toward resolution; corr with outcome +0.13 vs +0.04
    # at-fire) and is NOT forward-usable, so it is NOT an axis. Kept as a diagnostic below.
    d = defaultdict(list)
    for r in rows:
        rec = r["init_recency"]
        lab = "(null/pre-snapshot)" if rec is None else _bucket(rec, [30, 60, 180, 360, 720])
        d[lab].append(r)
    A["freshness_ATFIRE_recency_mins"] = d
    # LIVE freshness — LEAK DIAGNOSTIC ONLY (do NOT cut on this)
    d = defaultdict(list)
    for r in rows:
        rec = r["recency_mins"]
        lab = "(null)" if rec is None else _bucket(rec, [180, 360, 720, 1440, 2880])
        d[lab].append(r)
    A["freshness_LIVE_LEAKY_diag"] = d
    # backer volume — AT-FIRE (initial_total_usd) primary
    d = defaultdict(list)
    for r in rows:
        u = r["init_total_usd"]
        lab = "(null/pre-snapshot)" if u is None else _bucket(u, [250, 500, 1000, 2500, 5000])
        d[lab].append(r)
    A["backer_ATFIRE_total_usd"] = d
    # backer volume — LIVE diagnostic
    d = defaultdict(list)
    for r in rows:
        u = r["total_usd"]
        lab = "(null)" if u is None else _bucket(u, [250, 500, 1000, 2500, 5000])
        d[lab].append(r)
    A["backer_LIVE_total_usd_diag"] = d
    # #distinct backers — AT-FIRE (initial_n_backers)
    d = defaultdict(list)
    for r in rows:
        nb = r["init_n_backers"]
        lab = "(null/pre-snapshot)" if nb is None else _bucket(nb, [3, 4, 5, 7, 10])
        d[lab].append(r)
    A["n_backers_ATFIRE"] = d
    # best backer rank — AT-FIRE (initial_best_backer_rank)
    d = defaultdict(list)
    for r in rows:
        rk = r["init_rank"]
        lab = "(null/pre-snapshot)" if rk is None else _bucket(rk, [3, 5, 10, 20, 50])
        d[lab].append(r)
    A["best_backer_rank_ATFIRE"] = d
    # ask vs AT-FIRE consensus (entry_ask - at-fire p): positive = we pay UP over consensus
    d = defaultdict(list)
    for r in rows:
        if r["entry_ask"] is None:
            d["(null)"].append(r)
        else:
            dv = r["entry_ask"] - r["entry"]
            d[_signed_bucket(dv, [-0.03, -0.01, 0.01, 0.03])].append(r)
    A["ask_minus_atfire_consensus"] = d
    # correlated cluster size (# favorite bets sharing an event_slug)
    ev_ct = defaultdict(int)
    for r in rows:
        ev_ct[r["event_slug"] or r["cond"]] += 1
    d = defaultdict(list)
    for r in rows:
        c = ev_ct[r["event_slug"] or r["cond"]]
        lab = "1 (singleton)" if c == 1 else ("2" if c == 2 else "3+")
        d[lab].append(r)
    A["event_cluster_size"] = d
    return A

def _bucket(v, edges):
    lab_lo = 0
    for e in edges:
        if v < e:
            return f"<{e:g}" if lab_lo == 0 else f"{lab_lo:g}-{e:g}"
        lab_lo = e
    return f">={edges[-1]:g}"

def _signed_bucket(v, edges):
    prev = None
    for e in edges:
        if v < e:
            return f"<{e:g}" if prev is None else f"{prev:g}..{e:g}"
        prev = e
    return f">={edges[-1]:g}"


# ---- §0 seed table ------------------------------------------------------------------------
def seed_table(rows, blind_edge):
    """Reproduce the four §0 seed hypotheses on the corrected fee."""
    import re
    seeds = {}
    # AT-FIRE (decision-time, forward-valid) versions — PRIMARY
    stale_i = [r for r in rows if r["init_recency"] is not None and r["init_recency"] > 720]
    seeds["stale_ATFIRE_recency_gt720"] = score(stale_i, blind_edge)
    thin_i = [r for r in rows if r["init_total_usd"] is not None and r["init_total_usd"] < 1000]
    seeds["thin_ATFIRE_total_usd_lt1000"] = score(thin_i, blind_edge)
    # LIVE (leaky) versions — the §0 in-session read; shown to expose the field artifact
    stale_l = [r for r in rows if r["recency_mins"] is not None and r["recency_mins"] > 720]
    seeds["stale_LIVE_recency_gt720_LEAKY"] = score(stale_l, blind_edge)
    thin_l = [r for r in rows if r["total_usd"] is not None and r["total_usd"] < 1000]
    seeds["thin_LIVE_total_usd_lt1000"] = score(thin_l, blind_edge)
    obreg = re.compile(r"^(col|ucl|swe|chi)-")
    obs = [r for r in rows if obreg.match((r["event_slug"] or "").lower())]
    seeds["obscure_league_col_ucl_swe_chi"] = score(obs, blind_edge)
    ex = [r for r in rows if r["fine"] == "exact-score"]
    seeds["exact_score"] = score(ex, blind_edge)
    # crude "exclude all four" — AT-FIRE fields (the honest, forward-valid version)
    def is_garbage(r):
        return ((r["init_recency"] is not None and r["init_recency"] > 720)
                or (r["init_total_usd"] is not None and r["init_total_usd"] < 1000)
                or obreg.match((r["event_slug"] or "").lower())
                or r["fine"] == "exact-score")
    clean = [r for r in rows if not is_garbage(r)]
    seeds["_clean_book_crude_4cut_ATFIRE"] = score(clean, blind_edge)
    seeds["_full_book"] = score(rows, blind_edge)
    return seeds


# ---- report -------------------------------------------------------------------------------
def _fmt(m):
    if m.get("n", 0) == 0:
        return "n=0"
    return (f"n={m['n']:>4} win={m['win_pct']:>5.1f}% "
            f"ROIt={m['roi_taker']:>+7.2f}% ROIm={m['roi_maker']:>+7.2f}% "
            f"$drag={m['pnl_taker']:>+8.1f} surplus="
            f"{('%+.2f%%' % m['surplus']) if m['surplus'] is not None else '  n/a ':>8} "
            f"CI[{m['ci_lo']:>+6.1f},{m['ci_hi']:>+6.1f}] nev={m['n_events']}")

def run():
    rows = load_book()
    blind_edge = load_blind_edge()
    print(f"GARBAGE SEGMENTS · favorite book · n={len(rows)} resolved bets · corrected fee "
          f"(sports 0.03·p(1-p)) · turnover=$100/bet\n" + "=" * 110)
    full = score(rows, blind_edge)
    print("FULL BOOK   " + _fmt(full))
    print(f"  (anchor: RUN-HARDEN +2.8% taker → here ROIt={full['roi_taker']:+.2f}%; "
          f"stake-wtd {full['roi_taker_stake']:+.2f}%)\n")

    seeds = seed_table(rows, blind_edge)
    print("§0 SEED HYPOTHESES (corrected fee) " + "-" * 74)
    for k in ("stale_ATFIRE_recency_gt720", "stale_LIVE_recency_gt720_LEAKY",
              "thin_ATFIRE_total_usd_lt1000", "thin_LIVE_total_usd_lt1000",
              "obscure_league_col_ucl_swe_chi", "exact_score",
              "_clean_book_crude_4cut_ATFIRE", "_full_book"):
        print(f"  {k:<38} {_fmt(seeds[k])}")

    out = {"full_book": full, "seed_table": seeds, "axes": {}}
    print("\nMULTI-AXIS SLICE MAP " + "-" * 88)
    for axis, slc in axis_slices(rows).items():
        print(f"\n[{axis}]")
        scored = {}
        for label, rs in sorted(slc.items(), key=lambda kv: -len(kv[1])):
            m = score(rs, blind_edge)
            scored[label] = m
            print(f"  {label:<24} {_fmt(m)}")
        out["axes"][axis] = scored
    out["meta"] = {"n_bets": len(rows), "blind_edge_bands": {str(k): round(v, 4) for k, v in blind_edge.items()},
                   "fee_model": "sports 0.03*p*(1-p) entry-only; maker 0", "turnover_basis": "$100/bet"}
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {REPORT}")
    return 0


# ---- self-test ----------------------------------------------------------------------------
def _self_test():
    ok = True
    # accounting: favorite at p=0.8, win → 100*0.2 - 100*0.03*0.8*0.2 = 20 - 0.48 = 19.52
    v = pnl_taker(0.8, True, "soccer")
    ok &= abs(v - 19.52) < 1e-9
    # loss at p=0.8 → -80 - 0.48
    v = pnl_taker(0.8, False, "soccer")
    ok &= abs(v - (-80.48)) < 1e-9
    # maker no fee
    ok &= abs(pnl_maker(0.8, True) - 20.0) < 1e-9
    # crypto fee higher
    ok &= fee_rate("crypto") == 0.07 and fee_rate("soccer") == 0.03
    # bucket helper
    ok &= _bucket(500, [250, 1000]) == "250-1000"
    ok &= _bucket(100, [250, 1000]) == "<250"
    ok &= _bucket(5000, [250, 1000]) == ">=1000"
    print("self-test:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(0 if _self_test() else 1)
    sys.exit(run())
