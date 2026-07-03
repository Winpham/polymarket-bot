#!/usr/bin/env python3
"""
SOFTNESS × SKILL MAP — steer the generic favorite edge to the soft-AND-skilled pockets (2026-07-03).

The consensus-favorite edge is real but lives in the SOFT pockets of the book (casual/patriotic
money floods thin sub-markets) and BLEEDS in the sharp, professionally-modelled ones. This
instrument separates three numbers PER `category × market-type × band` cell and never conflates
them (the whole point):

  SOFTNESS   = opportunity size = event-clustered mean(won − at-fire entry) over the `_blind`
               pool's FAVORITES (entry ≥ 0.60) in the cell. + ⇒ favorites underpriced ⇒ casual /
               soft market. ≤ 0 ⇒ sharp / professionally-modelled. Knowable from the blind pool
               alone with FAR less data than a P&L verdict — the reason the map can steer FORWARD.
  SKILL      = the edge = event-clustered surplus of the `favorite` strategy over the matched
               (category × 5-band) blind baseline — what the CONSENSUS adds beyond the blind
               favorite at the SAME price. Must clear the ~3% capture cost to be bankable.
  REALIZABLE = event-clustered ROI at MEASURED costs (0.5¢ haircut + 2% fee), with a bootstrap LB.

Softness is NECESSARY, not sufficient: a soft cell (+3%) can still be −EV after the ~3% capture
cost (K2 downgrade), and a sharp cell (softness < 0) bleeds on the base rate no matter who we
follow (DODGE). The map's job is to keep these three separate and emit a pre-registered
PRIORITIZE / NEUTRAL / DODGE ordering that concentrates the SAME generic edge where the fish are.

Everything event-clustered at the match super-key (superkey.super_event), at-fire entry
(COALESCE(initial_mean_price, mean_price)), matched (category × 5-band) baseline — NEVER a
global-blind baseline (the composition trap). Categories from market_taxonomy (incl. politics,
esports, econ). Multiplicity: BH-FDR q=0.10 across the testable skill-cell family.

Modes:
  ./softness_map.py --self-test   # K1: injected soft+skilled cell→PRIORITIZE, sharp cell→DODGE,
                                  #     pure-noise→0 FDR survivors. Exit non-zero on failure.
  ./softness_map.py               # live map (softness table, skill table, combined verdicts)
  ./softness_map.py --seed-map    # append the combined map as a NEW DIMENSION (v002) in the
                                  # existing map_state.py store (carries v001 cells forward)
  ./softness_map.py --overlay     # Phase-5 silent forward steering overlay: paired lift of a
                                  # PRIORITIZE-concentrated favorite vs base favorite (forward-only)
"""

import csv
import io
import math
import os
import random
import subprocess
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import selection_null as sn                       # band(), clustered_surplus(), null_pvalue()
from superkey import super_event                  # noqa: E402
from market_taxonomy import category, market_type  # noqa: E402

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]

# --- pre-registration (frozen before computing) ---------------------------------------------
FAV_FLOOR = 0.60                 # softness/skill measured on favorites (entry ≥ 0.60)
FAV_BANDS = [("0.60-0.80", 0.60, 0.80), ("0.80-0.90", 0.80, 0.90), ("0.90-1.00", 0.90, 1.00)]
SOFT_N_FLOOR = 30                # softness needs ≥30 blind favorites in the cell (pre-registered)
SKILL_N_FLOOR = 20               # no skill verdict from < 20 fired events
READOUT_FLOOR = 10               # below this: no selection-null p (selection_null convention)
SOFT_MARGIN = 0.03               # capture cost ≈ 0.5¢ + 2% → the sharp-DODGE margin
HAIRCUT = 0.005                  # measured median haircut (D11 / honest-pnl)
FEE = 0.02
FDR_Q = 0.10
SEED = 20260703
N_NULL = 1200
N_BOOT = 2000
STRAT = "favorite"               # primary strategy (elite_fresh_fav is materially weaker, D16)

SQL = """
SELECT strategy, event_slug, slug, title, condition_id,
       COALESCE(initial_mean_price, mean_price) AS entry,
       (outcome_won::int) AS won,
       to_char(first_detected_at AT TIME ZONE 'UTC','YYYY-MM-DD') AS day
FROM consensus_signals WHERE resolved
"""


def fetch():
    out = subprocess.run(PG + ["-c", SQL.replace("\n", " ")], capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    rows = []
    for r in csv.DictReader(io.StringIO(out.stdout)):
        r["entry"] = float(r["entry"])
        r["won"] = int(r["won"])
        rows.append(r)
    return rows


def evk(r):
    return super_event(r["event_slug"], r["slug"]) or r["condition_id"]


def fav_band(e):
    for lab, lo, hi in FAV_BANDS:
        if lo <= e < hi or (hi == 1.00 and e >= lo):
            return lab
    return None


def cellof(r):
    """(category, market_type, fav_band) or None if not a favorite / uncovered mtype."""
    if r["entry"] < FAV_FLOOR:
        return None
    cat = category(r["slug"], r["title"])
    mt = market_type(r["slug"], r["title"])
    fb = fav_band(r["entry"])
    if mt is None or fb is None:
        return None
    return (cat, mt, fb)


def _boot_ci(ev_values, nprng, n_boot=N_BOOT):
    """event-level values → (mean, lb, ub) 95% bootstrap CI; (mean,None,None) if <5 events."""
    arr = np.array(ev_values, dtype=float)
    m = float(arr.mean()) if len(arr) else float("nan")
    if len(arr) < 5:
        return m, None, None
    boots = np.array([arr[nprng.integers(0, len(arr), len(arr))].mean() for _ in range(n_boot)])
    return m, float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))


def _ev_means(pairs):
    m = defaultdict(list)
    for ev, v in pairs:
        m[ev].append(v)
    return {ev: sum(v) / len(v) for ev, v in m.items()}


def bh_fdr(pvals, q):
    order = sorted(range(len(pvals)), key=lambda i: pvals[i])
    m, k_max = len(pvals), 0
    for rank, i in enumerate(order, start=1):
        if pvals[i] <= q * rank / m:
            k_max = rank
    return {order[i] for i in range(k_max)}


def analyze(rows, seed=SEED, n_null=N_NULL, n_boot=N_BOOT, strat=STRAT):
    rng = random.Random(seed)
    nprng = np.random.default_rng(seed)
    blind = [r for r in rows if r["strategy"] == "_blind"]
    picks = [r for r in rows if r["strategy"] == strat]

    # matched (category × 5-band) blind baseline — the composition-safe baseline for SKILL.
    base = defaultdict(list)
    for r in blind:
        base[(category(r["slug"], r["title"]), sn.band(r["entry"]))].append(r["won"] - r["entry"])
    base_cb = {k: sum(v) / len(v) for k, v in base.items()}

    def baseline(r):
        return base_cb.get((category(r["slug"], r["title"]), sn.band(r["entry"])), 0.0)

    # SOFTNESS: per cell, event-clustered blind-favorite edge (+ boot CI). Also rolled up to
    # (cat, mtype) so a thin band doesn't hide the signal.
    soft_cell = defaultdict(list)   # cell -> [(ev, won-entry)]
    for r in blind:
        c = cellof(r)
        if c is not None:
            soft_cell[c].append((evk(r), r["won"] - r["entry"]))
    softness = {}
    for c, pairs in soft_cell.items():
        evm = list(_ev_means(pairs).values())
        m, lb, ub = _boot_ci(evm, nprng)
        softness[c] = dict(n_blind_fav=len(pairs), n_events=len(evm),
                           softness=m, soft_lb=lb, soft_ub=ub)

    # rollup to (category × mtype) — pooled across bands, so a thin band doesn't hide the
    # signal and the numbers reconcile with sport_edge_tracker's pooled softness (Phase-0 check).
    roll = defaultdict(list)
    for c, pairs in soft_cell.items():
        roll[(c[0], c[1])].extend(pairs)
    softness_roll = {}
    for cm, pairs in roll.items():
        evm = list(_ev_means(pairs).values())
        mm, lb, ub = _boot_ci(evm, nprng)
        softness_roll[cm] = dict(n_blind_fav=len(pairs), n_events=len(evm),
                                 softness=mm, soft_lb=lb, soft_ub=ub)

    # pre-adjusted blind null pool (band5, day) → [(ev, a − base)] for the selection null.
    blind_cells = defaultdict(list)
    for r in blind:
        a = r["won"] - r["entry"] - baseline(r)
        blind_cells[(sn.band(r["entry"]), r["day"])].append((evk(r), a))

    # SKILL: per cell over the favorite picks.
    skill_rows = defaultdict(list)
    for r in picks:
        c = cellof(r)
        if c is not None:
            skill_rows[c].append(r)

    skill = {}
    for c, crows in skill_rows.items():
        picks_stat = [(evk(r), sn.band(r["entry"]), r["won"] - r["entry"] - baseline(r))
                      for r in crows]
        obs, n_ev = sn.clustered_surplus(picks_stat, {})
        # selection-null p (band5 × day matched), reusing the proven machinery.
        p_emp = None
        if n_ev >= READOUT_FLOOR:
            meta = [(sn.band(r["entry"]), r["day"]) for r in crows]
            draws = sn.null_pvalue(meta, blind_cells, {}, rng, n_null)
            if len(draws) >= 0.8 * n_null:
                p_emp = sum(1 for x in draws if x >= obs) / len(draws)
        # realizable ROI at measured costs (event-clustered) + boot CI.
        roi_pairs = []
        for r in crows:
            e = min(0.999, r["entry"] + HAIRCUT)
            roi_pairs.append((evk(r), (r["won"] - e) / e - FEE))
        ev_roi = list(_ev_means(roi_pairs).values())
        roi, roi_lb, roi_ub = _boot_ci(ev_roi, nprng, n_boot)
        # persistence splits: positive surplus in how many UTC days.
        by_day = defaultdict(list)
        for r, (_, _, a) in zip(crows, picks_stat):
            by_day[r["day"]].append((evk(r), a))
        days_pos = sum(1 for v in by_day.values()
                       if np.mean(list(_ev_means(v).values())) > 0)
        skill[c] = dict(n_fav=len(crows), n_events=n_ev, surplus=obs, p_emp=p_emp,
                        roi=roi, roi_lb=roi_lb, roi_ub=roi_ub,
                        days_pos=days_pos, days_n=len(by_day))

    # BH-FDR across the testable skill family.
    keys = [c for c in skill if skill[c]["p_emp"] is not None]
    surv = bh_fdr([skill[c]["p_emp"] for c in keys], FDR_Q)
    for c in skill:
        skill[c]["fdr_pass"] = False
    for rank, c in enumerate(keys):
        skill[c]["fdr_pass"] = rank in surv

    # ---- the combined 2×2 verdict (pre-registered; K1/K2 bind) ----
    verdicts = {}
    all_cells = set(softness) | set(skill)
    for c in all_cells:
        s = softness.get(c, {})
        k = skill.get(c, {})
        soft = s.get("softness")
        soft_ub = s.get("soft_ub")
        n_blind = s.get("n_blind_fav", 0)
        n_fav = k.get("n_fav", 0)
        roi_lb, roi_ub = k.get("roi_lb"), k.get("roi_ub")
        v, why = _verdict(soft, soft_ub, n_blind, k, n_fav, roi_lb, roi_ub)
        merged = dict(verdict=v, why=why,
                      softness=soft, soft_lb=s.get("soft_lb"), soft_ub=soft_ub,
                      n_blind_fav=n_blind, soft_events=s.get("n_events"))
        for kk in ("n_fav", "n_events", "surplus", "p_emp", "roi", "roi_lb", "roi_ub",
                   "days_pos", "days_n", "fdr_pass"):
            merged[kk] = k.get(kk)
        verdicts[c] = merged

    meta = dict(seed=seed, n_null=n_null, n_boot=n_boot, fdr_q=FDR_Q, haircut=HAIRCUT,
                fee=FEE, soft_margin=SOFT_MARGIN, soft_n_floor=SOFT_N_FLOOR,
                skill_n_floor=SKILL_N_FLOOR, strat=strat,
                fdr_family=len(keys), fdr_survivors=len(surv),
                days=sorted({r["day"] for r in rows}))
    return dict(softness=softness, softness_roll=softness_roll, skill=skill,
                verdicts=verdicts, base_cb=base_cb, meta=meta)


def _verdict(soft, soft_ub, n_blind, k, n_fav, roi_lb, roi_ub):
    """PRIORITIZE / NEUTRAL / DODGE with the softness gate + K2 downgrade. Returns (v, why)."""
    fdr = k.get("fdr_pass", False)
    # DODGE-A: softness reliably sharp (blind pool alone, needs LESS data) → base rate bleeds.
    if n_blind >= SOFT_N_FLOOR and soft is not None and soft < -SOFT_MARGIN \
            and soft_ub is not None and soft_ub < 0:
        return "DODGE", f"sharp: softness {soft:+.1%} (ub {soft_ub:+.1%}) < −{SOFT_MARGIN:.0%}, base rate bleeds"
    # DODGE-B: skill measurable and reliably −EV after costs.
    if n_fav >= SKILL_N_FLOOR and roi_ub is not None and roi_ub < 0:
        return "DODGE", f"skill −EV: realizable-ROI ub {roi_ub:+.1%} < 0 at N={n_fav}"
    # PRIORITIZE: skill clears cost margin (FDR-survives ∧ roi_lb>0) AND cell not sharp.
    if fdr and roi_lb is not None and roi_lb > 0 and n_fav >= SKILL_N_FLOOR \
            and (soft is None or soft >= 0) and k.get("days_pos", 0) >= 2:
        return "PRIORITIZE", f"skill clears cost: roi_lb {roi_lb:+.1%}>0, FDR✓, softness≥0"
    # K2 downgrade: soft but skill measurable and NOT cost-clearing → NEUTRAL, say so.
    if soft is not None and soft >= 0 and n_fav >= SKILL_N_FLOOR \
            and (roi_lb is None or roi_lb <= 0):
        return "NEUTRAL", f"soft ({soft:+.1%}) but skill not cost-clearing (roi_lb {roi_lb if roi_lb is None else format(roi_lb,'+.1%')}) → K2 downgrade"
    # below a floor: INDETERMINATE (the watch-list).
    if n_fav < SKILL_N_FLOOR and n_blind < SOFT_N_FLOOR:
        return "INDETERMINATE", f"below both floors (N_fav {n_fav}, N_blind {n_blind})"
    if n_fav < SKILL_N_FLOOR:
        tag = "soft" if (soft is not None and soft >= 0) else "neutral-softness"
        return "INDETERMINATE", f"{tag} (softness {soft:+.1%} on {n_blind} blind) but skill unmeasured (N_fav {n_fav}<{SKILL_N_FLOOR})" if soft is not None else f"skill unmeasured (N_fav {n_fav})"
    return "NEUTRAL", "no binding signal"


# ------------------------------- printing ---------------------------------------------------
def _f(x, spec="+.1%"):
    return "   —" if x is None or (isinstance(x, float) and math.isnan(x)) else format(x, spec)


def run_live(strat=STRAT):
    res = analyze(fetch(), strat=strat)
    m = res["meta"]
    days = m["days"]
    print(f"SOFTNESS × SKILL MAP · strategy={strat} · match-clustered · at-fire · "
          f"cat×mtype×band · record {len(days)}d {days[0]}→{days[-1]}")
    print(f"softness=blind-fav edge (entry≥{FAV_FLOOR}) · skill=surplus over (cat×band) blind · "
          f"BH-FDR q={FDR_Q} over {m['fdr_family']} skill cells → {m['fdr_survivors']} survive · "
          f"cost {HAIRCUT*100:.1f}¢+{FEE:.0%}\n")

    # SOFTNESS table (softest → sharpest), rolled to (cat, mtype) with band detail.
    print("── SOFTNESS (where casual money pools · blind favorites only) ──")
    hdr = f"{'category':<18}{'mtype':<7}{'band':<11}{'nFav':>5}{'ev':>4}{'softness':>10}{'  95% CI':>18}"
    print(hdr)
    for c in sorted(res["softness"], key=lambda c: -res["softness"][c]["softness"]):
        s = res["softness"][c]
        ci = f"[{_f(s['soft_lb'])},{_f(s['soft_ub'])}]" if s["soft_lb"] is not None else "  (n<5)"
        flag = " ★soft" if (s["soft_lb"] or 0) > 0 else (" ⚠sharp" if (s["soft_ub"] or 0) < 0 else "")
        print(f"{c[0]:<18}{c[1]:<7}{c[2]:<11}{s['n_blind_fav']:>5}{s['n_events']:>4}"
              f"{_f(s['softness']):>10}{ci:>18}{flag}")

    # (cat × mtype) softness rollup — reconciles with sport_edge_tracker's pooled numbers.
    print("\n── SOFTNESS rollup (category × market-type, pooled bands) ──")
    print(f"{'category':<18}{'mtype':<7}{'nFav':>6}{'ev':>5}{'softness':>10}{'  95% CI':>18}")
    for cm in sorted(res["softness_roll"], key=lambda c: -res["softness_roll"][c]["softness"]):
        s = res["softness_roll"][cm]
        ci = f"[{_f(s['soft_lb'])},{_f(s['soft_ub'])}]" if s["soft_lb"] is not None else "  (n<5)"
        flag = " ★soft" if (s["soft_lb"] or 0) > 0 else (" ⚠sharp" if (s["soft_ub"] or 0) < 0 else "")
        print(f"{cm[0]:<18}{cm[1]:<7}{s['n_blind_fav']:>6}{s['n_events']:>5}"
              f"{_f(s['softness']):>10}{ci:>18}{flag}")

    # SKILL table (only cells where the consensus fires).
    print("\n── SKILL (what the consensus ADDS · favorite picks only) ──")
    hdr2 = f"{'category':<18}{'mtype':<7}{'band':<11}{'nFav':>5}{'ev':>4}{'surplus':>9}{'p':>7}{'FDR':>4}{'realizROI[lb,ub]':>22}{'d+':>5}"
    print(hdr2)
    for c in sorted(res["skill"], key=lambda c: -res["skill"][c]["n_events"]):
        k = res["skill"][c]
        roi = f"{_f(k['roi'])}[{_f(k['roi_lb'])},{_f(k['roi_ub'])}]"
        print(f"{c[0]:<18}{c[1]:<7}{c[2]:<11}{k['n_fav']:>5}{k['n_events']:>4}"
              f"{_f(k['surplus']):>9}{_f(k['p_emp'],'.3f'):>7}{'✓' if k['fdr_pass'] else '·':>4}"
              f"{roi:>22}{k['days_pos']:>2}/{k['days_n']}")

    # COMBINED verdicts — ugly cells (DODGE) first, then the honest rest.
    print("\n── COMBINED MAP · PRIORITIZE / NEUTRAL / DODGE ──")
    order = {"DODGE": 0, "PRIORITIZE": 1, "NEUTRAL": 2, "INDETERMINATE": 3}
    for c in sorted(res["verdicts"], key=lambda c: (order.get(res["verdicts"][c]["verdict"], 9), c)):
        v = res["verdicts"][c]
        print(f"  {v['verdict']:<14}{c[0]}/{c[1]}/{c[2]:<11}  {v['why']}")
    print("\nread: SOFTNESS says where it's POSSIBLE (needs less data); SKILL says where it's REAL")
    print("(must clear the ~3% cost). Soft ≠ bankable (K2). Sharp cells DODGE on the base rate.")
    print("Categories that never fire consensus (crypto/other/econ) are observations, not arms (K4).")

    # durable artifact (keys stringified: cells are tuples)
    import json
    art = {"meta": m,
           "softness": {"|".join(k): v for k, v in res["softness"].items()},
           "softness_roll": {"|".join(k): v for k, v in res["softness_roll"].items()},
           "skill": {"|".join(k): v for k, v in res["skill"].items()},
           "verdicts": {"|".join(k): v for k, v in res["verdicts"].items()}}
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "reports", "softness_map.json")
    with open(out, "w") as f:
        json.dump(art, f, indent=1, default=str)
    print("\nartifact → reports/softness_map.json")
    return res


# ------------------------------- self-test (K1) ---------------------------------------------
def _mk(strategy, disc, i, kind, entry, won, day):
    """Realistic dated slug so the taxonomy classifies it. kind ∈ {'main','deriv'};
    each i is a distinct match (distinct super-event)."""
    base = f"{disc}-x{i}-y{i}-{day}"
    if kind == "deriv":
        slug, title = base + "-total-5pt5", "O/U 5.5"
    else:
        slug, title = base, "X vs Y"
    return dict(strategy=strategy, event_slug=base, slug=slug, title=title,
                condition_id=slug, entry=entry, won=won, day=day)


def _self_test():
    """K1: a soft+skilled cell → PRIORITIZE; a sharp cell → DODGE; pure noise → 0 FDR survivors."""
    rng = random.Random(1)
    days = ["2026-06-29", "2026-06-30", "2026-07-01", "2026-07-02"]
    rows = []
    # SOFT+SKILLED cell: soccer/main. Blind favorites at 0.75 win 82% (softness +7%). The
    # `favorite` strategy at 0.75 wins ~95% → skill well over cost, softness≥0 → PRIORITIZE.
    for day in days:
        for i in range(60):
            rows.append(_mk("_blind", "fifwc", i, "main", 0.75, int(rng.random() < 0.82), day))
        for i in range(500, 540):
            rows.append(_mk("favorite", "fifwc", i, "main", 0.75, int(rng.random() < 0.95), day))
    # SHARP cell: mlb/deriv. Blind favorites at 0.75 win 60% (softness −15%) → DODGE on base rate.
    for day in days:
        for i in range(60):
            rows.append(_mk("_blind", "mlb", i, "deriv", 0.75, int(rng.random() < 0.60), day))
    # NOISE cells: efficient market elsewhere (blind + favorite both P(win)=entry) → no edge.
    for day in days:
        for i in range(80):
            e = rng.uniform(0.6, 0.9)
            rows.append(_mk("_blind", "atp", i, "main", e, int(rng.random() < e), day))
        for i in range(700, 730):
            e = rng.uniform(0.6, 0.9)
            rows.append(_mk("favorite", "atp", i, "main", e, int(rng.random() < e), day))

    res = analyze(rows, n_null=400, n_boot=400)
    ok = True

    soft_cell = ("soccer", "main", "0.60-0.80")
    v_soft = res["verdicts"].get(soft_cell, {})
    c1 = v_soft.get("verdict") == "PRIORITIZE"
    ok = ok and c1
    print(f"  [{'ok' if c1 else 'FAIL'}] soft+skilled soccer/main → {v_soft.get('verdict')} "
          f"(softness {_f(v_soft.get('softness'))}, roi_lb {_f(v_soft.get('roi_lb'))}, FDR {v_soft.get('fdr_pass')})")

    sharp_cell = ("mlb", "deriv", "0.60-0.80")
    v_sharp = res["verdicts"].get(sharp_cell, {})
    c2 = v_sharp.get("verdict") == "DODGE"
    ok = ok and c2
    print(f"  [{'ok' if c2 else 'FAIL'}] sharp mlb/deriv → {v_sharp.get('verdict')} "
          f"(softness {_f(v_sharp.get('softness'))})")

    # pure-noise: the efficient tennis cells must NOT PRIORITIZE and must not FDR-survive.
    tennis_prior = any(v["verdict"] == "PRIORITIZE" for c, v in res["verdicts"].items()
                       if c[0] == "tennis")
    c3 = (not tennis_prior)
    ok = ok and c3
    print(f"  [{'ok' if c3 else 'FAIL'}] efficient-noise tennis cells → never PRIORITIZE")

    # a genuinely pure-noise family gives 0 FDR survivors (drop the injected-edge strategy).
    noise_only = [r for r in rows if not ((r["strategy"] == "favorite") and r["slug"].startswith("fifwc"))]
    res0 = analyze(noise_only, n_null=400, n_boot=400)
    c4 = res0["meta"]["fdr_survivors"] == 0
    ok = ok and c4
    print(f"  [{'ok' if c4 else 'FAIL'}] pure-noise family → {res0['meta']['fdr_survivors']} FDR survivors (want 0)")

    print("SELF-TEST", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(0 if _self_test() else 1)
    if "--seed-map" in sys.argv:
        import seed_softness_map  # noqa: F401  (writes v002; kept separate for map_state reuse)
        sys.exit(seed_softness_map.main())
    if "--overlay" in sys.argv:
        import overlay_lift
        sys.exit(overlay_lift.main())
    run_live()
