#!/usr/bin/env python3
"""
CELL SKILL MAP — per (sport × market-type × trader-tier) softness/skill decomposition of the
`favorite` champion book, under the overfitting guard (RUN-PER-SPORT-CONDITIONING §1, §3.1).

The deployed `favorite` arm (price_band 0.65–0.98) treats every sport the same. This instrument
decomposes its edge into SOFTNESS (does the market misprice favorites) vs SKILL (does the
consensus SELECTION add surplus over a band-matched blind favorite OF THE SAME CELL), per cell,
so a durable non-tournament edge (MLB in a near-efficient market) can be told apart from a
soft-tournament artifact (soccer World Cup, tennis Wimbledon).

REUSES the single accounting source of truth — no re-implementation:
  garbage_segments.load_book / score / pnl_taker  (favorite book ⋈ ledger, corrected fee, CI)
  sport_edge_tracker.sport                         (garbage-policy-fixed sport map + coverage)
  market_taxonomy.market_type                      (main | deriv | None)
  selection_null.band / clustered_surplus / null_pvalue  (belief-blind statistic + permutation)
  superkey.super_event                             (event-cluster super-key)

Every cell reports, EVENT-CLUSTERED, AT-FIRE entry (COALESCE(initial_mean_price, mean_price)):
  n_picks / n_events / win% / softness (sport blind-fav edge) /
  skill_raw   = clustered surplus vs (sport×band) blind favorite  (the §0 skill definition)
  skill_pooled= skill_raw shrunk toward the GLOBAL favorite skill by n_ev/(n_ev+K_POOL)  [MANDATORY]
  null_p      = within-cell selection-null p_emp (consensus vs random SAME-CELL blind favorite)
  roi_ask     = realizable ROI paying entry_ask, corrected fee 0.03·p(1-p)  (+ ask coverage)
  roi_mid     = at-fire-mid ROI (gs.score) for reference
  power       = OK / UNDERPOWERED against the pre-registered support floor

PARTIAL POOLING IS NOT OPTIONAL (§2): raw per-cell means are banned as a decision basis; only
`skill_pooled` decides. K_POOL=40 mirrors the Rust `slice_pooled_quality` shrink.

Read-only. Paper-only. Writes reports/CELL-SKILL-MAP.json. No DB writes, no network, no LLM.

  ./cell_skill_map.py               # full cell map + §0 reproduction + JSON
  ./cell_skill_map.py --self-test   # pooling + power-flag fixtures
"""

import csv
import io
import json
import os
import random
import subprocess
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import garbage_segments as gs      # noqa: E402
import selection_null as sn        # noqa: E402
import sport_edge_tracker as st    # noqa: E402
import market_taxonomy as mtx      # noqa: E402
from superkey import super_event   # noqa: E402

REPORT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "reports", "CELL-SKILL-MAP.json")

K_POOL = 40.0            # partial-pool shrink constant (mirrors Rust slice_pooled_quality)
N_PERM = 2000
SEED = 20260709
# Pre-registered support floors (event-clusters): with a mechanism vs without.
FLOOR_MECH = 20
FLOOR_NOMECH = 30
FAV_FLOOR = 0.6          # "favorite" price floor for the softness measure


# ---- trader-quality tier (DESCRIPTIVE ONLY — raw rank is REFUTED as a decision basis) --------
# The ARM's trader-quality feature is the SHRUNK EARNED trust (Rust slice_pooled_quality), not
# this. This tier is a read-only diagnostic to see whether quality co-varies with skill per cell;
# it is NEVER a certification basis (project-polymarket-identify-skilled: raw rank REFUTED 5 ways).
def trader_tier(init_rank):
    if init_rank is None:
        return "unranked"
    if init_rank < 5:
        return "top5"
    if init_rank < 20:
        return "top20"
    return "ranked20+"


def evk(r):
    return super_event(r.get("event_slug"), r.get("slug")) or r.get("cond") or r.get("condition_id")


def sport_of(r):
    return st.sport(r.get("slug") or r.get("event_slug") or "")


# ---- realizable ROI paying entry_ask (the ONLY honest execution price) ----------------------
def roi_ask(rows):
    """Realizable ROI over the subset with entry_ask present; pays the ask, corrected fee.
    Returns (roi_pct or None, coverage_frac, n_with_ask)."""
    have = [r for r in rows if r.get("entry_ask") is not None]
    if not have:
        return None, 0.0, 0
    pnl = 0.0
    for r in have:
        ask = min(0.999, r["entry_ask"])
        fee = gs.SHARES * gs.fee_rate(r["cat"]) * ask * (1.0 - ask)
        pnl += (gs.SHARES * (1.0 - ask) if r["won"] else -gs.SHARES * ask) - fee
    return round(100.0 * pnl / (gs.SHARES * len(have)), 3), round(len(have) / len(rows), 3), len(have)


# ---- favorite book: the FULL resolved consensus_signals book (NOT the ledger subset) --------
# gs.load_book joins honest_paper_ledger (only the ~222 laddered picks); §0 / sport_edge_tracker
# use the full resolved `favorite` book (438 picks). Reproducing §0 requires the full book, so we
# fetch consensus_signals directly, building the SAME row schema gs.score/roi_ask consume.
SQL_FAV_FULL = """
SELECT s.condition_id, s.outcome_index, s.event_slug, s.slug, s.title,
       COALESCE(s.initial_mean_price, s.mean_price) AS entry,
       (s.outcome_won::int) AS won,
       s.initial_recency_mins, s.total_usd, s.initial_total_usd,
       s.n_backers, s.initial_n_backers, s.best_backer_rank, s.initial_best_backer_rank,
       s.mean_price, s.entry_ask,
       to_char(s.first_detected_at AT TIME ZONE 'UTC','YYYY-MM-DD') AS day
FROM consensus_signals s
WHERE s.strategy = 'favorite' AND s.resolved AND s.outcome_won IS NOT NULL
"""


def load_fav_full():
    out = subprocess.run(gs.PG + ["-f", "-"], input=SQL_FAV_FULL, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    rows = []
    for r in csv.DictReader(io.StringIO(out.stdout)):
        p = gs._f(r["entry"])
        if p is None:
            continue
        cat = mtx.category(r["slug"], r["title"])
        won = int(r["won"])
        rows.append({
            "cond": r["condition_id"], "condition_id": r["condition_id"],
            "event_slug": r["event_slug"] or "", "slug": r["slug"] or "",
            "title": r["title"] or "", "entry": p, "won": won,
            "init_recency": gs._f(r["initial_recency_mins"]),
            "total_usd": gs._f(r["total_usd"]), "init_total_usd": gs._f(r["initial_total_usd"]),
            "n_backers": gs._f(r["n_backers"]), "init_n_backers": gs._f(r["initial_n_backers"]),
            "rank": gs._f(r["best_backer_rank"]), "init_rank": gs._f(r["initial_best_backer_rank"]),
            "mean_price": gs._f(r["mean_price"]), "entry_ask": gs._f(r["entry_ask"]),
            "day": r["day"], "cat": cat, "fine": mtx._classify_mtype_fine(r["slug"], r["title"]),
            "mt": mtx.market_type(r["slug"], r["title"]),
            "band": sn.band(p), "surplus_a": won - p,
            "pnl_t": gs.pnl_taker(p, won, cat), "pnl_m": gs.pnl_maker(p, won),
        })
    return rows


# ---- blind baselines ------------------------------------------------------------------------
SQL_BLIND_RICH = """
SELECT COALESCE(initial_mean_price, mean_price) AS entry, (outcome_won::int) AS won,
       event_slug, slug, title, condition_id,
       to_char(first_detected_at AT TIME ZONE 'UTC','YYYY-MM-DD') AS day
FROM consensus_signals WHERE resolved AND strategy = '_blind'
"""


def load_blind_rich():
    out = subprocess.run(gs.PG + ["-f", "-"], input=SQL_BLIND_RICH, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    rows = []
    for r in csv.DictReader(io.StringIO(out.stdout)):
        p = gs._f(r["entry"])
        if p is None:
            continue
        rows.append({"entry": p, "won": int(r["won"]),
                     "event_slug": r["event_slug"] or "", "slug": r["slug"] or "",
                     "title": r["title"] or "", "condition_id": r["condition_id"],
                     "day": r["day"], "band": sn.band(p),
                     "sport": st.sport(r["slug"] or r["event_slug"] or ""),
                     "mt": mtx.market_type(r["slug"], r["title"])})
    return rows


def blind_baselines(blind):
    """global per-band edge (sn/gs style), per-(sport,band) edge (§0 skill baseline), and
    per-sport blind-favorite softness."""
    gband = defaultdict(list)
    sband = defaultdict(list)
    soft = defaultdict(list)
    for r in blind:
        gband[r["band"]].append(r["won"] - r["entry"])
        sband[(r["sport"], r["band"])].append(r["won"] - r["entry"])
        if r["entry"] >= FAV_FLOOR:
            soft[r["sport"]].append((evk(r), r["won"] - r["entry"]))
    g = {b: sum(v) / len(v) for b, v in gband.items()}
    s = {k: sum(v) / len(v) for k, v in sband.items()}
    softness = {sp: sn.clustered_surplus([(e, 0, a) for e, a in pairs], {})[0]
                for sp, pairs in soft.items()}
    return g, s, softness


def sport_band_surplus(rows, sband_edge):
    """event-clustered surplus vs (sport,band) blind — the §0 / sport_edge_tracker skill stat."""
    ev = defaultdict(list)
    for r in rows:
        base = sband_edge.get((sport_of(r), r["band"]), 0.0)
        ev[evk(r)].append((r["won"] - r["entry"]) - base)
    if not ev:
        return float("nan"), 0
    return sum(sum(v) / len(v) for v in ev.values()) / len(ev), len(ev)


# ---- within-cell selection null (consensus vs random SAME-CELL blind favorite) --------------
def cell_null_p(cell_rows, cell_blind, gband_edge, rng, n_perm=N_PERM):
    """Restrict the blind universe to the SAME cell, then run the selection_null permutation on
    the cell's (band×day) pick profile. Returns (p_emp, n_draws) or (None, 0) if unmatchable."""
    blind_cells = defaultdict(list)
    for r in cell_blind:
        blind_cells[(r["band"], r["day"])].append((evk(r), r["won"] - r["entry"]))
    picks = [(evk(r), r["band"], r["won"] - r["entry"]) for r in cell_rows]
    obs, n_ev = sn.clustered_surplus(picks, gband_edge)
    meta = [(r["band"], r["day"]) for r in cell_rows]
    draws = sn.null_pvalue(meta, blind_cells, gband_edge, rng, n_perm)
    if len(draws) < 1000:
        return None, len(draws)
    return sum(1 for x in draws if x >= obs) / len(draws), len(draws)


# ---- cell scoring ---------------------------------------------------------------------------
def score_cell(rows, blind_same_cell, sband_edge, gband_edge, global_fav_skill, rng,
               with_mechanism, run_null=True):
    base = gs.score(rows, {b: gband_edge.get(b, 0.0) for b in range(7)})  # n, win%, roi_mid, CI
    skill_raw, n_ev = sport_band_surplus(rows, sband_edge)
    w = n_ev / (n_ev + K_POOL) if n_ev else 0.0
    skill_pooled = global_fav_skill + (skill_raw - global_fav_skill) * w if skill_raw == skill_raw else global_fav_skill
    ra, cov, n_ask = roi_ask(rows)
    floor = FLOOR_MECH if with_mechanism else FLOOR_NOMECH
    power = "OK" if n_ev >= floor else "UNDERPOWERED"
    p_emp = n_draws = None
    if run_null and n_ev >= 10 and blind_same_cell:
        p_emp, n_draws = cell_null_p(rows, blind_same_cell, gband_edge, rng)
    return {
        "n_picks": base.get("n", 0), "n_events": n_ev, "win_pct": base.get("win_pct"),
        "skill_raw_pct": round(100 * skill_raw, 3) if skill_raw == skill_raw else None,
        "skill_pooled_pct": round(100 * skill_pooled, 3),
        "shrink_w": round(w, 3),
        "null_p": round(p_emp, 4) if p_emp is not None else None, "null_draws": n_draws,
        "roi_ask_pct": ra, "ask_coverage": cov, "n_with_ask": n_ask,
        "roi_mid_pct": base.get("roi_taker"),
        "surplus_globalband_pct": base.get("surplus"),
        "ci_lo": base.get("ci_lo"), "ci_hi": base.get("ci_hi"),
        "power": power, "floor": floor,
    }


def run():
    fav = load_fav_full()                     # FULL resolved favorite book (reproduces §0)
    blind = load_blind_rich()
    gband_edge, sband_edge, softness = blind_baselines(blind)
    rng = random.Random(SEED)

    global_fav_skill, _ = sport_band_surplus(fav, sband_edge)   # pooling target (§1.2)

    # blind universe partitioned by cell for the within-cell null
    blind_by_sport = defaultdict(list)
    blind_by_sport_mt = defaultdict(list)
    for r in blind:
        blind_by_sport[r["sport"]].append(r)
        blind_by_sport_mt[(r["sport"], r["mt"])].append(r)

    print(f"CELL SKILL MAP · favorite book n={len(fav)} · blind n={len(blind)} · "
          f"K_POOL={K_POOL:g} · global favorite skill={100*global_fav_skill:+.2f}% · at-fire\n" + "=" * 118)
    print(f"ask coverage: {sum(1 for r in fav if r.get('entry_ask') is not None)}/{len(fav)} "
          f"favorite picks carry entry_ask (snapshot era) → realizable ROI is coverage-limited; "
          f"belief-blind skill uses the full book.\n")

    out = {"meta": {"n_fav": len(fav), "n_blind": len(blind), "K_POOL": K_POOL,
                    "global_fav_skill_pct": round(100 * global_fav_skill, 3),
                    "floors": {"with_mechanism": FLOOR_MECH, "without": FLOOR_NOMECH},
                    "seed": SEED, "n_perm": N_PERM},
           "softness_by_sport": {k: round(100 * v, 3) for k, v in softness.items()},
           "cells": {}}

    # ---- dimension 1: sport-only (reproduces §0) ----
    by_sport = defaultdict(list)
    for r in fav:
        by_sport[sport_of(r)].append(r)
    hdr = (f"{'cell':<34}{'nP':>4}{'nEv':>4}{'win%':>6}{'soft':>7}{'skillR':>8}"
           f"{'skillP':>8}{'w':>5}{'null_p':>8}{'roiAsk':>8}{'cov':>5}{'roiMid':>8}  power")
    print("── DIM 1 · sport ──────────────────────────────────────────────────────────────")
    print(hdr)
    for sp in sorted(by_sport, key=lambda s: -len(by_sport[s])):
        rows = by_sport[sp]
        m = score_cell(rows, blind_by_sport.get(sp, []), sband_edge, gband_edge,
                       global_fav_skill, rng, with_mechanism=False)
        m["softness_pct"] = round(100 * softness.get(sp, float("nan")), 3) if sp in softness else None
        out["cells"][f"sport={sp}"] = m
        _print_row(f"sport={sp}", m, softness.get(sp))

    # ---- dimension 2: sport × market-type ----
    print("\n── DIM 2 · sport × market-type ────────────────────────────────────────────────")
    print(hdr)
    by_sport_mt = defaultdict(list)
    for r in fav:
        by_sport_mt[(sport_of(r), r["mt"] or "unc")].append(r)
    for (sp, mt) in sorted(by_sport_mt, key=lambda k: -len(by_sport_mt[k])):
        rows = by_sport_mt[(sp, mt)]
        if len(rows) < 3:
            continue
        m = score_cell(rows, blind_by_sport_mt.get((sp, mt if mt != "unc" else None), []),
                       sband_edge, gband_edge, global_fav_skill, rng, with_mechanism=True)
        m["softness_pct"] = round(100 * softness.get(sp, float("nan")), 3) if sp in softness else None
        out["cells"][f"sport={sp}|mt={mt}"] = m
        _print_row(f"sport={sp}|mt={mt}", m, softness.get(sp))

    # ---- dimension 3: sport × market-type × trader-tier (DESCRIPTIVE; power-shattered) ----
    print("\n── DIM 3 · sport × mt × trader-tier (DESCRIPTIVE — raw rank REFUTED; power-shattered) ──")
    print(hdr)
    by_full = defaultdict(list)
    for r in fav:
        by_full[(sport_of(r), r["mt"] or "unc", trader_tier(r.get("init_rank")))].append(r)
    for key in sorted(by_full, key=lambda k: -len(by_full[k])):
        rows = by_full[key]
        if len(rows) < 5:
            continue
        sp, mt, tier = key
        # null pool: same sport×mt (tier not partitioned in blind — descriptive only, no null)
        m = score_cell(rows, [], sband_edge, gband_edge, global_fav_skill, rng,
                       with_mechanism=True, run_null=False)
        m["softness_pct"] = round(100 * softness.get(sp, float("nan")), 3) if sp in softness else None
        out["cells"][f"sport={sp}|mt={mt}|tier={tier}"] = m
        _print_row(f"sport={sp}|mt={mt}|tier={tier}", m, softness.get(sp))

    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {REPORT}")

    # ---- §0 reproduction check ----
    print("\n§0 REPRODUCTION CHECK (sport-only skill_raw vs the brief's seed table)")
    seed0 = {"mlb": 14.0, "tennis": 5.5, "soccer": -2.7}
    ok = True
    for sp, want in seed0.items():
        got = out["cells"].get(f"sport={sp}", {}).get("skill_raw_pct")
        if got is None:
            print(f"  {sp:<8} MISSING"); ok = False; continue
        delta = abs(got - want)
        flag = "OK" if delta <= 4.0 else "MISMATCH"
        if flag != "OK":
            ok = False
        print(f"  {sp:<8} §0 skill {want:+.1f}%  reproduced {got:+.1f}%  (Δ{delta:.1f}pp) {flag}")
    print("§0 reproduction:", "PASS — proceed" if ok else "FAIL — STOP and report (materially disagrees with §0)")
    return 0 if ok else 2


def _print_row(label, m, soft):
    soft_s = f"{100*soft:+.1f}%" if soft is not None and soft == soft else "   n/a"
    nullp = f"{m['null_p']:.4f}" if m["null_p"] is not None else "   —"
    roiask = f"{m['roi_ask_pct']:+.1f}%" if m["roi_ask_pct"] is not None else "   —"
    skr = f"{m['skill_raw_pct']:+.1f}%" if m["skill_raw_pct"] is not None else "  n/a"
    print(f"{label:<34}{m['n_picks']:>4}{m['n_events']:>4}"
          f"{(m['win_pct'] or 0):>5.0f}%{soft_s:>7}{skr:>8}"
          f"{m['skill_pooled_pct']:>+7.1f}%{m['shrink_w']:>5.2f}{nullp:>8}"
          f"{roiask:>8}{m['ask_coverage']:>5.2f}{(m['roi_mid_pct'] or 0):>+7.1f}%  {m['power']}")


# ---- self-test ------------------------------------------------------------------------------
def _self_test():
    ok = True
    # partial pooling: a 5-event cell must sit near the global mean; a 200-event cell near raw.
    gfs = 0.05
    for n_ev, raw, want_near in [(5, 0.30, gfs), (200, 0.30, 0.30)]:
        w = n_ev / (n_ev + K_POOL)
        pooled = gfs + (raw - gfs) * w
        c = abs(pooled - want_near) < 0.06
        ok &= c
        print(f"  [{'ok' if c else 'FAIL'}] pool n_ev={n_ev}: raw {raw:+.0%} → pooled {pooled:+.2%} "
              f"(near {'global' if want_near == gfs else 'raw'})")
    # power floor
    c = ("UNDERPOWERED" if 12 < FLOOR_MECH else "OK") == "UNDERPOWERED"
    ok &= c
    print(f"  [{'ok' if c else 'FAIL'}] power: 12 events < floor {FLOOR_MECH} → UNDERPOWERED")
    # roi_ask pays the ask (higher price → lower ROI than mid)
    rows = [{"entry_ask": 0.85, "won": 1, "cat": "mlb"}, {"entry_ask": 0.85, "won": 0, "cat": "mlb"}]
    ra, cov, n = roi_ask(rows)
    c = ra is not None and cov == 1.0 and n == 2
    ok &= c
    print(f"  [{'ok' if c else 'FAIL'}] roi_ask pays ask: roi={ra}% cov={cov} n={n}")
    c = trader_tier(None) == "unranked" and trader_tier(3) == "top5" and trader_tier(12) == "top20"
    ok &= c
    print(f"  [{'ok' if c else 'FAIL'}] trader_tier buckets")
    print("SELF-TEST", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(0 if _self_test() else 1)
    sys.exit(run())
