#!/usr/bin/env python3
"""
CELL-VERDICT (Generalize-the-Band-Strategy, phase 3, 2026-07-11).

Apply the full anti-overfit battery + champion head-to-head + complement/correlation test to every
candidate cell that cleared the phase-2 floors, and emit reports/CELL-VERDICT.json + a one-paragraph
verdict per cell. Read-only; certifies nothing; the forward gate is the arbiter.

The battery (each catches a real prior-run failure mode):
  • LODO jackknife    — drop the dominant sub-regime (most match-clusters); LB must stay > 0. Caught
                        the soft-esports dota2 soft-week artifact and the champion's late-half fade.
  • Time-split OOS    — early vs late active-days; a late-half LB ≤ 0 is the decay signature.
  • Cluster bootstrap — 2000× resample of MATCH clusters (from cell_lib); guards small-G t miscalibration.
  • Bonferroni        — recompute the LB at α' = 0.05 / M over the M cells scanned; the more cells, the
                        higher the bar. M reported explicitly.
  • selection_null    — the cell's consensus SELECTION vs random favorite selection from `_blind` in the
                        SAME category, matched to its (band × day) profile; p_emp ≤ 0.01, ≥1000 draws.
                        Kills the market_resid composition-artifact class.
  • head-to-head      — cell LB vs champion LB on the identical at-fire metric; a WIN needs the
                        pre-registered +2.0pp non-inferiority margin.
  • complement test   — match-DAY return correlation of the cell's disjoint remainder vs the champion;
                        a COMPLEMENT must be positively-EV AND low-correlated (else it's the same bet
                        re-labeled). Subsets of the champion are refinements, NOT complements.

Self-test:  ./cell_verdict.py --selftest
Live:       ./cell_verdict.py
"""

import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cell_lib as C                                    # noqa: E402
from cell_scan import fetch_live_favorite, fetch_blind_baseline   # noqa: E402

M_CELLS_SCANNED = 14        # 10 live cells + 4 replay cohorts (phase 2) — the Bonferroni family
SEED = 20260711
N_PERM = 2000


def a_stat(r):
    """The at-fire surplus atom a = won − at-fire entry (the scoreboard statistic)."""
    return (1.0 if r["won"] else 0.0) - r["atfire"]


def lodo(rows):
    """Drop the dominant regime (most match-clusters), recompute the objective LB on the rest."""
    by_reg = defaultdict(list)
    for r in rows:
        by_reg[C.regime_key(r["event_slug"], r["slug"])].append(r)
    if len(by_reg) < 2:
        return {"dropped": None, "lb_without_dominant": None, "note": "single regime — LODO N/A"}
    dom = max(by_reg, key=lambda k: len({C.mkey(r) for r in by_reg[k]}))
    rest = [{**r, "entry": r["atfire"]} for r in rows if C.regime_key(r["event_slug"], r["slug"]) != dom]
    lb = C.roi_lb(rest)
    return {"dropped": dom, "n_regimes": len(by_reg),
            "lb_without_dominant": None if (lb is None or lb.get("lb") is None) else round(lb["lb"], 4),
            "G_without_dominant": None if lb is None else lb.get("G_clusters")}


def time_split(rows):
    days = sorted({r["day"] for r in rows if r.get("day")})
    if len(days) < 2:
        return {"split_day": None}
    split = days[len(days) // 2]
    early = [{**r, "entry": r["atfire"]} for r in rows if r["day"] < split]
    late = [{**r, "entry": r["atfire"]} for r in rows if r["day"] >= split]
    le, ll = C.roi_lb(early), C.roi_lb(late)
    def g(x):
        return None if (x is None or x.get("lb") is None) else round(x["lb"], 4)
    return {"split_day": split,
            "early_LB": g(le), "early_G": None if le is None else le.get("G_clusters"),
            "late_LB": g(ll), "late_G": None if ll is None else ll.get("G_clusters"),
            "late_half_holds": (g(ll) is not None and g(ll) > 0)}


def bonferroni_lb(rows, m=M_CELLS_SCANNED):
    """Objective LB recomputed at the family-wise α' = 0.05/m (wider t critical value)."""
    er = [{**r, "entry": r["atfire"]} for r in rows]
    lb = C.roi_lb(er, alpha=0.05 / m)
    return {"alpha_adj": round(0.05 / m, 4), "m_cells": m,
            "bonferroni_LB": None if (lb is None or lb.get("lb") is None) else round(lb["lb"], 4)}


def selection_null(cell_rows, blind_pool, blind_edge, category, rng, n_perm=N_PERM):
    """Observed clustered surplus of the cell's SELECTION over the band-matched blind baseline vs a
    (band × day)-profile-matched random selection from the `_blind` favorites in the SAME category.
    p_emp = fraction of null draws ≥ observed. category=None ⇒ pool across all categories."""
    def clustered_surplus(picks):
        ev = defaultdict(list)
        for mk, band, a in picks:
            ev[mk].append(a - blind_edge.get(band, 0.0))
        if not ev:
            return float("nan")
        return sum(sum(v) / len(v) for v in ev.values()) / len(ev)

    obs = clustered_surplus([(C.mkey(r), r["band"], a_stat(r)) for r in cell_rows])
    # blind universe keyed by (band, day) within the category
    cells = defaultdict(list)
    for r in blind_pool:
        if category is None or r["category"] == category:
            cells[(r["band"], r["day"])].append((r["mkey"], r["band"], r["a"]))
    profile = defaultdict(int)
    for r in cell_rows:
        profile[(r["band"], r["day"])] += 1
    ge = 0
    draws = 0
    for _ in range(n_perm):
        sel = []
        ok = True
        for cell, k in profile.items():
            pool = cells.get(cell)
            if not pool:
                ok = False
                break
            sel.extend(rng.choices(pool, k=k) if k > len(pool) else rng.sample(pool, k))
        if not ok:
            continue
        draws += 1
        if clustered_surplus(sel) >= obs:
            ge += 1
    p = (ge + 1) / (draws + 1) if draws else None
    return {"observed_surplus": round(obs, 4), "p_emp": None if p is None else round(p, 4),
            "draws": draws, "pass_p01": (p is not None and p <= 0.01),
            "note": None if draws >= 1000 else "INSUFFICIENT matched draws (<1000) — INDETERMINATE"}


def daily_returns(rows):
    """Per active-day ROI-turn (Σpnl/Σstake at at-fire) — the series for the complement correlation."""
    num, den = defaultdict(float), defaultdict(float)
    for r in rows:
        num[r["day"]] += C.pnl(r["atfire"], r["won"])
        den[r["day"]] += r["atfire"]
    return {d: num[d] / den[d] for d in num if den[d] > 0}


def correlation(a_rows, b_rows):
    """Match-DAY return correlation between two disjoint cells. A complement is low-correlated."""
    ra, rb = daily_returns(a_rows), daily_returns(b_rows)
    common = sorted(set(ra) & set(rb))
    if len(common) < 3:
        return {"n_common_days": len(common), "corr": None, "note": "<3 shared days"}
    xa = [ra[d] for d in common]
    xb = [rb[d] for d in common]
    ma, mb = sum(xa) / len(xa), sum(xb) / len(xb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(xa, xb))
    va = sum((x - ma) ** 2 for x in xa)
    vb = sum((y - mb) ** 2 for y in xb)
    if va <= 0 or vb <= 0:
        return {"n_common_days": len(common), "corr": None, "note": "zero variance"}
    return {"n_common_days": len(common), "corr": round(cov / math.sqrt(va * vb), 3)}


def fetch_blind_universe():
    """`_blind` favorites in-band with (category, band, day, mkey, a) for the selection-null pool."""
    rows = C.q(f"""
    SELECT COALESCE(event_slug,''), COALESCE(slug,''), condition_id,
           COALESCE(initial_mean_price, mean_price) e, outcome_won, first_detected_at::date
    FROM consensus_signals
    WHERE strategy='_blind' AND resolved AND outcome_won IS NOT NULL
      AND COALESCE(initial_mean_price, mean_price) BETWEEN {C.CHAMP_LO} AND {C.CHAMP_HI};
    """)
    out = []
    for r in rows:
        es, slug, cond, e, won, day = (r + [""] * 6)[:6]
        e = float(e)
        out.append({"event_slug": es, "slug": slug, "condition_id": cond, "band": C.band_of(e),
                    "day": day, "category": C.category(es, slug),
                    "mkey": C.super_event(es, slug) or cond, "a": (1.0 if won == "t" else 0.0) - e})
    return out


def champion_LB(champ_rows):
    er = [{**r, "entry": r["atfire"]} for r in champ_rows]
    lb = C.roi_lb(er)
    return None if (lb is None or lb.get("lb") is None) else round(lb["lb"], 4)


def build():
    live = fetch_live_favorite(require_ask=False)
    blind_edge_cells = fetch_blind_baseline()
    blind_edge = {}                         # band → mean blind edge (pooled over categories)
    tmp = defaultdict(list)
    for (cat, band), (edge, n) in blind_edge_cells.items():
        tmp[band].append((edge, n))
    for band, lst in tmp.items():
        tot = sum(n for _, n in lst)
        blind_edge[band] = sum(e * n for e, n in lst) / tot if tot else 0.0
    for r in live:
        r["category"] = C.category(r["event_slug"], r["slug"])
        r["band"] = C.band_of(r["atfire"])
    champ = [r for r in live if C.CHAMP_LO <= r["atfire"] <= C.CHAMP_HI]
    champ_lb = champion_LB(champ)
    blind_pool = fetch_blind_universe()
    rng = random.Random(SEED)

    tennis = [r for r in champ if r["category"] == "tennis"]
    soccer = [r for r in champ if r["category"] == "soccer"]
    band_c = [r for r in champ if 0.71 <= r["atfire"] < 0.82]

    candidates = {
        "CHAMPION_favorite_0.71-0.98": (champ, None),
        "tennis_0.71-0.98": (tennis, "tennis"),
        "soccer_0.71-0.98": (soccer, "soccer"),
        "band_0.71-0.82_pooled": (band_c, None),
    }

    NI_MARGIN = 0.02
    verdicts = {}
    for name, (rows, cat) in candidates.items():
        if len(rows) < 5:
            verdicts[name] = {"verdict": "INSUFFICIENT", "n_picks": len(rows)}
            continue
        er = [{**r, "entry": r["atfire"]} for r in rows]
        base = C.roi_lb(er)
        boot = C.bootstrap_lb(er)
        pf = C.power_flags(er)
        lo = lodo(rows)
        ts = time_split(rows)
        bf = bonferroni_lb(rows)
        sn = selection_null(rows, blind_pool, blind_edge, cat, rng)
        base_lb = None if (base is None or base.get("lb") is None) else round(base["lb"], 4)
        h2h = None if (base_lb is None or champ_lb is None) else round(base_lb - champ_lb, 4)
        # complement: correlation of this cell's DISJOINT remainder vs the rest of champion.
        rest = [r for r in champ if id(r) not in {id(x) for x in rows}]
        corr = correlation(rows, rest) if (rest and name != "CHAMPION_favorite_0.71-0.98") else \
            {"note": "champion itself / no disjoint remainder"}

        passes = {
            "powered": pf["meets_volume_floor"] and pf["meets_duration_floor"] and pf["meets_regime_floor"],
            "base_LB_positive": base_lb is not None and base_lb > 0,
            "lodo_survives": lo["lb_without_dominant"] is not None and lo["lb_without_dominant"] > 0,
            "late_half_holds": ts.get("late_half_holds", False),
            "bonferroni_positive": bf["bonferroni_LB"] is not None and bf["bonferroni_LB"] > 0,
            "selection_null_p01": sn["pass_p01"],
        }
        beats_champ = (name != "CHAMPION_favorite_0.71-0.98" and h2h is not None and h2h >= NI_MARGIN)
        is_complement = (beats_champ and corr.get("corr") is not None and abs(corr["corr"]) < 0.3)
        verdicts[name] = {
            "n_picks": len(rows), "n_match_clusters": pf["n_matches"], "active_days": pf["active_days"],
            "regimes_over_subfloor": pf["regimes"],
            "base_objective_LB": base_lb, "bootstrap_LB": None if boot is None else round(boot["lb"], 4),
            "skill_over_blind": None,   # filled below from phase-2 mean edge
            "lodo": lo, "time_split": ts, "bonferroni": bf, "selection_null": sn,
            "head_to_head_vs_champion_pp": h2h, "beats_champion_by_NI_margin": beats_champ,
            "complement_correlation": corr, "is_low_correlated_complement": is_complement,
            "battery": passes,
            "survives_full_battery": all(passes.values()),
        }
        # skill over blind (at-fire), pooled over the cell's (cat,band) mix
        num = den = 0.0
        for r in rows:
            b = blind_edge_cells.get((r["category"], r["band"]))
            if b:
                num += b[0]; den += 1
        cell_edge = sum(a_stat(r) for r in rows) / len(rows)
        verdicts[name]["skill_over_blind"] = round(cell_edge - (num / den), 4) if den else None

    return {
        "as_of": "2026-07-11",
        "run": "generalize-band-strategy phase 3 (anti-overfit battery + head-to-head)",
        "champion_objective_LB": champ_lb,
        "NI_margin_pp": NI_MARGIN,
        "M_cells_scanned_bonferroni_family": M_CELLS_SCANNED,
        "candidates": verdicts,
        "note": "at-fire full-population basis (unbiased; entry_ask≈at-fire confirmed phase 2). A "
                "'beat' needs LB ≥ champion + 0.02 AND survive the full battery; a 'complement' needs "
                "that PLUS |match-day corr| < 0.3 with the champion remainder. Tennis and the 0.71-0.82 "
                "band are SUBSETS of the champion pool (refinements, not disjoint complements).",
    }


def selftest():
    ok = True
    rng = random.Random(1)
    # correlation: identical series → corr 1; anti → -1
    a = [{"day": f"d{i}", "atfire": 0.8, "won": (i % 2 == 0), "event_slug": f"x{i}", "slug": f"x{i}",
          "condition_id": f"c{i}"} for i in range(6)]
    if correlation(a, a)["corr"] != 1.0:
        print(f"FAIL corr self: {correlation(a,a)}"); ok = False
    # lodo: single regime → N/A
    one = [{"event_slug": "atp-a-2026-07-01", "slug": "atp-a-2026-07-01-x", "condition_id": f"c{i}",
            "atfire": 0.8, "won": True, "day": "2026-07-01"} for i in range(3)]
    if lodo(one)["dropped"] is not None:
        print("FAIL lodo single"); ok = False
    # bonferroni LB must be ≤ the 95% LB (wider interval)
    rows = [{"event_slug": f"atp-a{i}-2026-07-{1+i:02d}", "slug": f"atp-a{i}-2026-07-{1+i:02d}-x",
             "condition_id": f"c{i}", "atfire": 0.78, "won": (i < 8), "day": f"2026-07-{1+i:02d}"}
            for i in range(10)]
    er = [{**r, "entry": r["atfire"]} for r in rows]
    b95 = C.roi_lb(er)["lb"]
    bbf = bonferroni_lb(rows)["bonferroni_LB"]
    if not (bbf is not None and bbf <= b95 + 1e-9):
        print(f"FAIL bonferroni width: bf={bbf} 95={b95}"); ok = False
    print("selftest PASS" if ok else "selftest FAIL")
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    rep = build()
    outp = Path(__file__).resolve().parent.parent / "reports" / "CELL-VERDICT.json"
    outp.write_text(json.dumps(rep, indent=2))
    print(f"wrote {outp}\n")
    print(f"champion objective LB = {rep['champion_objective_LB']}  (M={rep['M_cells_scanned_bonferroni_family']} Bonferroni family)\n")
    for name, v in rep["candidates"].items():
        if "battery" not in v:
            print(f"  {name}: {v['verdict']}"); continue
        print(f"  {name}: LB {v['base_objective_LB']} | skill {v['skill_over_blind']} | "
              f"h2h {v['head_to_head_vs_champion_pp']}pp | LODO {v['lodo']['lb_without_dominant']} | "
              f"late {v['time_split']['late_LB']} | bonf {v['bonferroni']['bonferroni_LB']} | "
              f"null p={v['selection_null']['p_emp']} | corr {v['complement_correlation'].get('corr')}")
        print(f"      battery={v['battery']} -> survives_full={v['survives_full_battery']} "
              f"beats_champ={v['beats_champion_by_NI_margin']} complement={v['is_low_correlated_complement']}")


if __name__ == "__main__":
    main()
