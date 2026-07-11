#!/usr/bin/env python3
"""
CELL-SCAN (Generalize-the-Band-Strategy, phase 2, 2026-07-11).

Measure every sufficiently-powered cell on THE LOCKED OBJECTIVE and emit reports/CELL-EDGE-MAP.json
ranked by it. The objective (frozen, no re-derivation — cell_lib): cluster-robust one-sided 95%
LOWER BOUND of realizable, copyable ROI-on-turnover at the MATCH super-key. Diagnostics ONLY (never
the objective): win rate (the win-rate trap — a 0.97 favorite winning 96% earns <0/$), total P&L,
skill-over-blind, capacity.

Cells measured:
  • CHAMPION pool `favorite` 0.71-0.98 (the incumbent to beat) — realizable entry_ask.
  • Per-category within the champion band (soccer / tennis / …) — realizable.
  • Per-band pooled within 0.71-0.98 (71-82 / 82-90 / 90-98) — realizable, a-priori mechanism only.
  • REPLAY cohorts (top40 / 41-100 / 101-250 / wide 1-250) at the champion band — DIRECTIONAL
    (the sharps' own fill = the non-copyable ceiling) plus tape-realizable where the 72h tape covers
    it. Directional numbers are context; a directional/soft-week number is NOT an edge.

Belief-blind SKILL (mandatory): surplus over the `_blind` favorite at the same category+band (both on
the at-fire/mean price basis — `_blind` has no entry_ask). A cell whose edge ≈ its blind baseline is
riding structure/softness, not skill, and will not transfer.

CERTIFIES nothing, PROMOTES nothing. Phase 3 runs the anti-overfit battery + champion head-to-head.

Self-test:  ./cell_scan.py --selftest
Live:       ./cell_scan.py
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cell_lib as C                                    # noqa: E402
from cell_map import fetch_live_favorite, fetch_replay_cohort   # noqa: E402


CHAMP_LABEL = "CHAMPION_favorite_0.71-0.98"


def fetch_blind_baseline():
    """`_blind` favorite mean(won − price) per category × band on the at-fire price basis.
    Returns {(category, band): (edge, n)}. This is the softness/structure baseline the consensus
    SKILL must beat."""
    rows = C.q(f"""
    SELECT COALESCE(event_slug,''), COALESCE(slug,''),
           COALESCE(initial_mean_price, mean_price) e, outcome_won
    FROM consensus_signals
    WHERE strategy='_blind' AND resolved AND outcome_won IS NOT NULL
      AND COALESCE(initial_mean_price, mean_price) BETWEEN {C.CHAMP_LO} AND {C.CHAMP_HI};
    """)
    agg = defaultdict(lambda: [0.0, 0])
    for r in rows:
        es, slug, e, won = (r + [""] * 4)[:4]
        e = float(e)
        key = (C.category(es, slug), C.band_of(e))
        agg[key][0] += (1.0 if won == "t" else 0.0) - e
        agg[key][1] += 1
    return {k: (v[0] / v[1], v[1]) for k, v in agg.items() if v[1] > 0}


def fetch_capacity(picks):
    """Coarse liquidity proxy: median observed trade size (last_size) on the tape for the cell's
    conditions. NOT true fillable depth (the tape stores top-of-book, not the ladder) — a directional
    read of how thin the books are. The handoff's measured fillable size is ~$20-80/pick."""
    conds = sorted({p["condition_id"] for p in picks})
    if not conds:
        return None
    vals = ",".join(f"'{c}'" for c in conds[:400])
    rows = C.q(f"""
    SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY last_size),
           count(DISTINCT condition_id)
    FROM clob_price_tape
    WHERE condition_id IN ({vals}) AND last_size IS NOT NULL AND last_size>0;
    """)
    if not rows or rows[0][0] in ("", None):
        return {"median_trade_shares": None, "conds_with_tape": 0}
    return {"median_trade_shares": round(float(rows[0][0]), 1),
            "conds_with_tape": int(rows[0][1])}


def _basis(rows, entry_key):
    """Core objective stats on ONE price basis. rows already filtered to have entry_key."""
    er = [{**r, "entry": r[entry_key]} for r in rows if r.get(entry_key) is not None]
    if len(er) < 2:
        return {"n_picks": len(er), "roi_turn_point": None, "roi_turn_LB": None}
    lb = C.roi_lb(er)
    boot = C.bootstrap_lb(er)
    return {
        "n_picks": len(er),
        "roi_turn_point": None if lb is None else round(lb["point"], 4),
        "roi_turn_LB": None if (lb is None or lb.get("lb") is None) else round(lb["lb"], 4),
        "bootstrap_LB": None if boot is None else round(boot["lb"], 4),
        "G_clusters": None if lb is None else lb.get("G_clusters"),
        "N_events": None if lb is None else lb.get("N_events"),
        "win_rate_diag": round(C.win_rate(er), 3),
    }


def measure(rows, label, blind, regime_gated=True, capacity=False):
    """One dual-basis cell record. rows carry BOTH prices: 'atfire' (unbiased full-population, the
    PRIMARY objective basis + skill basis) and 'entry_ask' (copyable but capture-biased → the
    conservative BRACKET). Power flags computed on the at-fire population."""
    full = [r for r in rows if r.get("atfire") is not None]
    if len(full) < 2:
        return {"label": label, "n_picks": len(full), "verdict": "INSUFFICIENT (<2 events)"}
    prim = _basis(full, "atfire")
    ask_rows = [r for r in rows if r.get("entry_ask") is not None]
    bracket = _basis(ask_rows, "entry_ask") if len(ask_rows) >= 2 else {"n_picks": len(ask_rows)}
    pf = C.power_flags([{**r, "entry": r["atfire"]} for r in full])

    # belief-blind SKILL on the CLEAN at-fire basis (apples-to-apples with _blind).
    cell_edge = sum((1.0 if r["won"] else 0.0) - r["atfire"] for r in full) / len(full)
    bw_num = bw_den = 0.0
    for r in full:
        b = blind.get((r["category"], r["band"]))
        if b:
            bw_num += b[0]
            bw_den += 1
    blind_edge = (bw_num / bw_den) if bw_den else None
    skill = None if blind_edge is None else round(cell_edge - blind_edge, 4)
    # capture haircut check (brief §2): how far the biased ask sits below the at-fire mid on the
    # SAME picks — the bracket's pessimism, and whether at-fire ≈ ask on captured rows.
    paired = [r for r in ask_rows if r.get("atfire") is not None]
    haircut = (sum(r["entry_ask"] - r["atfire"] for r in paired) / len(paired)) if paired else None

    rec = {
        "label": label,
        "primary_atfire": prim,
        "realizable_bracket_ask": bracket,
        "capture_haircut_ask_minus_atfire": None if haircut is None else round(haircut, 4),
        "mean_edge_atfire_diag": round(cell_edge, 4),
        "blind_baseline_diag": None if blind_edge is None else round(blind_edge, 4),
        "skill_over_blind_diag": skill,
        "active_days": pf["active_days"],
        "n_match_clusters": pf["n_matches"],
        "regimes_over_subfloor": pf["regimes"],
        "regime_clusters": pf["regime_clusters"],
        "meets_volume_floor": pf["meets_volume_floor"],
        "meets_duration_floor": pf["meets_duration_floor"],
        "meets_regime_floor": pf["meets_regime_floor"],
        # convenience top-level: the primary-basis objective LB used for ranking
        "roi_turn_LB": prim["roi_turn_LB"], "bootstrap_LB": prim["bootstrap_LB"],
        "G_clusters": prim["G_clusters"],
    }
    if capacity:
        rec["capacity_diag"] = fetch_capacity(full)
    fails = []
    if not pf["meets_volume_floor"]:
        fails.append(f"volume<{C.VOL_FLOOR}clusters({pf['n_matches']})")
    if not pf["meets_duration_floor"]:
        fails.append(f"duration<{C.DUR_FLOOR_DAYS}days({pf['active_days']})")
    if regime_gated and not pf["meets_regime_floor"]:
        fails.append(f"regimes<{C.REGIME_FLOOR}({pf['n_regimes_over_subfloor']})")
    if fails:
        rec["verdict"] = "INDETERMINATE (" + "; ".join(fails) + ")"
    elif prim["roi_turn_LB"] is not None and prim["roi_turn_LB"] > 0:
        skill_ok = (skill is None) or (skill > 0)
        rec["verdict"] = "CANDIDATE_POSITIVE_LB" + ("" if skill_ok else " (but skill≤blind — riding softness)")
    else:
        rec["verdict"] = "NON_POSITIVE_LB"
    return rec


def build():
    live = fetch_live_favorite(require_ask=False)      # FULL population for the unbiased at-fire basis
    blind = fetch_blind_baseline()
    for r in live:
        r["category"] = C.category(r["event_slug"], r["slug"])
        r["band"] = C.band_of(r["atfire"])

    champ_rows = [r for r in live if C.CHAMP_LO <= r["atfire"] <= C.CHAMP_HI]

    cells = []
    # 1. the incumbent champion pool (regime-gated: soccer+tennis are its 2 regimes)
    cells.append(measure(champ_rows, CHAMP_LABEL, blind, regime_gated=True, capacity=True))

    # 2. per-category within the champion band
    by_cat = defaultdict(list)
    for r in champ_rows:
        by_cat[r["category"]].append(r)
    for cat, rs in sorted(by_cat.items(), key=lambda kv: -len(kv[1])):
        cells.append(measure(rs, f"live_favorite:{cat}:0.71-0.98", blind, regime_gated=True, capacity=True))

    # 3. per-band pooled within champion (a-priori: deep favorites earn ~0/$, watch the 90+ band)
    for bname, lo, hi in [("c_71_82", 0.71, 0.82), ("d_82_90", 0.82, 0.90), ("e_90_98", 0.90, 0.999)]:
        rs = [r for r in champ_rows if lo <= r["atfire"] < hi or (hi >= 0.99 and r["atfire"] >= 0.98)]
        cells.append(measure(rs, f"live_favorite:pooled:{bname}", blind, regime_gated=False))

    # 4. replay cohorts: directional (at the sharps' own fill = non-copyable ceiling) + tape-realizable.
    #    'atfire' here = the sharps' mean fill (the only pre-live price a replay has); the 'entry_ask'
    #    slot carries the realizable tape_ask so the bracket shows the (thin, 72h-capped) copyable price.
    cohort_cells = {}
    for name, lo, hi in C.COHORTS:
        rowset = fetch_replay_cohort(lo, hi)
        for r in rowset:
            r["category"] = C.category(r["event_slug"], r["slug"])
            r["band"] = C.band_of(r["sharp_entry"])
            r["atfire"] = r["sharp_entry"]         # directional basis (sharps' own price)
            r["entry_ask"] = r.get("tape_ask")     # realizable bracket (tape, sparse)
        champ_band = [r for r in rowset if r["band"] in ("c_71_82", "d_82_90", "e_90_98")]
        cohort_cells[name] = measure(champ_band, f"replay:{name}:0.71-0.98", blind, regime_gated=True)

    ranked = sorted([c for c in cells if c.get("roi_turn_LB") is not None],
                    key=lambda c: c["roi_turn_LB"], reverse=True)

    return {
        "as_of": "2026-07-11",
        "run": "generalize-band-strategy phase 2 (edge measurement)",
        "objective": "cluster-robust one-sided 95% LB of realizable copyable ROI-turn @ match super-key",
        "entry_basis": "PRIMARY = at-fire mid COALESCE(initial_mean_price,mean_price): unbiased FULL "
                       "population (the handoff's headline basis + a fast-copier proxy). BRACKET = "
                       "entry_ask: copyable executable ask but CAPTURE-BIASED (only slow/loser-tilted "
                       "picks get one) → pessimistic, never truth (brief §2). REPLAY primary = the "
                       "sharps' own fill (non-copyable ceiling); its bracket = 72h clob tape ask.",
        "diagnostics_note": "win_rate/total-P&L/capacity are DIAGNOSTIC ONLY. skill_over_blind = "
                            "consensus edge beyond the blind favorite at the same cell on the CLEAN "
                            "at-fire basis; ≤0 ⇒ riding softness (won't transfer).",
        "live_cells": cells,
        "live_cells_ranked_by_objective": [
            {"label": c["label"], "roi_turn_LB": c["roi_turn_LB"], "bootstrap_LB": c["bootstrap_LB"],
             "G_clusters": c["G_clusters"], "skill_over_blind_diag": c["skill_over_blind_diag"],
             "bracket_ask_LB": c.get("realizable_bracket_ask", {}).get("roi_turn_LB"),
             "verdict": c["verdict"]} for c in ranked],
        "replay_cohorts": cohort_cells,
    }


def selftest():
    ok = True
    blind = {("tennis", "c_71_82"): (0.023, 100), ("soccer", "e_90_98"): (0.024, 100)}
    # plumbing: dual-basis record with both prices present
    rows = [{"atfire": 0.78, "entry_ask": 0.79, "won": True,
             "event_slug": f"atp-a-b{i}-2026-07-{1+i:02d}", "slug": f"atp-a-b{i}-2026-07-{1+i:02d}-x",
             "condition_id": f"c{i}", "day": f"2026-07-{1+i:02d}", "category": "tennis",
             "band": "c_71_82"} for i in range(5)]
    m = measure(rows, "t", blind)
    if m["primary_atfire"]["roi_turn_point"] is None or m["skill_over_blind_diag"] is None:
        print(f"FAIL measure plumbing: {m}"); ok = False
    if m["capture_haircut_ask_minus_atfire"] is None or abs(m["capture_haircut_ask_minus_atfire"] - 0.01) > 1e-9:
        print(f"FAIL haircut: {m.get('capture_haircut_ask_minus_atfire')}"); ok = False
    # win-rate trap: deep favorites winning just below breakeven → negative point ROI at at-fire
    deep = [{"atfire": 0.97, "entry_ask": None, "won": (i < 96),
             "event_slug": f"x-{i}-2026-07-{1+(i%9):02d}", "slug": f"x-{i}", "condition_id": f"d{i}",
             "day": f"2026-07-{1+(i%9):02d}", "category": "soccer", "band": "e_90_98"} for i in range(100)]
    md = measure(deep, "deep", blind, regime_gated=False)
    if not (md["primary_atfire"]["roi_turn_point"] is not None and md["primary_atfire"]["roi_turn_point"] < 0):
        print(f"FAIL win-rate-trap: {md['primary_atfire']['roi_turn_point']}"); ok = False
    print("selftest PASS" if ok else "selftest FAIL")
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    rep = build()
    outp = Path(__file__).resolve().parent.parent / "reports" / "CELL-EDGE-MAP.json"
    outp.write_text(json.dumps(rep, indent=2))
    print(f"wrote {outp}\n")
    print("=== live cells ranked by PRIMARY at-fire objective (cluster-robust ROI-turn LB) ===")
    print("    (bracket = capture-biased entry_ask LB; skill = surplus over blind favorite)")
    for c in rep["live_cells_ranked_by_objective"]:
        print(f"  atfire {c['roi_turn_LB']:+.4f} LB | boot {c['bootstrap_LB']} | ask-bracket "
              f"{c['bracket_ask_LB']} | G={c['G_clusters']} | skill {c['skill_over_blind_diag']} "
              f"| {c['label']} -> {c['verdict']}")
    print("\n=== replay cohorts (directional ceiling — NON-copyable) ===")
    for name, c in rep["replay_cohorts"].items():
        p = c.get("primary_atfire", {})
        print(f"  {name}: atfire LB {p.get('roi_turn_LB')} pt {p.get('roi_turn_point')} "
              f"G={p.get('G_clusters')} skill {c.get('skill_over_blind_diag')} -> {c.get('verdict')}")


if __name__ == "__main__":
    main()
