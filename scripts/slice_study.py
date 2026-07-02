#!/usr/bin/env python3
"""
SLICE STUDY — the PRIORITIZE / NEUTRAL / DODGE map (reliability × frequency).

Maps the whole forward record into PRE-REGISTERED slices (see
reports/entries/2026-07-02-10-slice-study.md — the family was frozen before anything
was computed) and, per cell:

  surplus      event-clustered mean of (a − blind_edge[regime × band]) at the AT-FIRE
               entry (D6) — the blind baseline is matched on (regime × 5-band), never
               the global blind alone.
  p_emp        selection-matched null (the selection_null.py machinery, imported —
               its CLI stays byte-identical): ≥1000 seeded draws from `_blind`,
               profile-matched on (5-band × UTC-day × regime), same clustered statistic.
  realizable   event-clustered ROI at MEASURED costs (0.5¢ haircut, 2% fee), 95% CI by
               seeded event-bootstrap.
  freq         qualifying events/day (whole record + last 48h — the planning number).
  $/day        freq_recent × $100 × realizable ROI, joint bootstrap CI (Poisson × ROI).
  persistence  positive matched surplus in how many UTC days / regimes.
  K2           sign stability at-fire vs drifted entry (flip ⇒ UNSTABLE, never PRIORITIZE).
  LODO / exWC  leave-one-day-out fragility + soccer cells recomputed without fifwc rows.

Multiplicity: Benjamini-Hochberg FDR q=0.10 across the WHOLE family (~123 cells).
  PRIORITIZE ⇔ FDR-surviving ∧ realizable-LB>0 ∧ N≥20 ∧ ≥2 day-or-regime splits >0
               ∧ freq_recent ≥ 1/day ∧ K2-stable ∧ at-fire-true definition.
  DODGE      ⇔ realizable-UB<0 ∧ N≥20 (the mirror test; small N is NEVER a dodge).
DRIFT-DEFINED dims (σ, backer comp, freshness, liquidity — overwritten on upsert, not
knowable at fire) are †-capped: they can nominate at-fire capture, never bind.

Exploration nominates; forward data confirms; D7 promotes. Nothing changes live behavior.

Modes:
  ./slice_study.py             # live DB (docker-exec psql, house pattern)
  ./slice_study.py --selftest  # synthetic fixtures: injected-edge cell X must
                               # PRIORITIZE, no-edge cell Y must stay NEUTRAL, and a
                               # pure-noise fixture must give 0 FDR survivors.
                               # Exit non-zero on failure.
"""

import csv
import io
import json
import math
import os
import random
import subprocess
import sys
from collections import Counter, defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import selection_null as sn  # band(), regime(), clustered_surplus(), null_pvalue()

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]
POPULATIONS = ["favorite", "elite_fresh_fav", "strict"]
SEED = 20260702
N_NULL = 1200            # ≥1000 per the pre-registration
N_BOOT = 2000
FDR_Q = 0.10
HAIRCUT = 0.005          # measured median real haircut (D11 / honest-pnl), NOT the 1¢ guess
FEE = 0.02
N_FLOOR = 20             # verdict floor (PRIORITIZE and DODGE both)
READOUT_FLOOR = 10       # below this: metrics shown, no null p (selection_null convention)
FREQ_FLOOR = 1.0         # events/day (last 48h) for PRIORITIZE
STAKE = 100.0            # $ per event, flat-shares normalized

SQL = """
SELECT strategy, COALESCE(event_slug, condition_id) AS ev, event_slug, slug, title,
       COALESCE(initial_mean_price, mean_price) AS entry,
       mean_price AS drifted,
       (outcome_won::int) AS won,
       to_char(first_detected_at AT TIME ZONE 'UTC', 'YYYY-MM-DD') AS day,
       extract(hour from first_detected_at AT TIME ZONE 'UTC')::int AS hour,
       extract(epoch from first_detected_at) AS t_fire,
       extract(epoch from resolved_at) AS t_res,
       initial_net_count, initial_n_backers,
       net_count, n_backers, price_std, recency_mins, total_usd, best_backer_rank,
       {shape_cols}
FROM consensus_signals WHERE resolved
"""
# Migration 036 adds set-once at-fire shape columns; the study prefers them and un-caps
# a DRIFT dim once ≥95% of a cell's rows carry the at-fire value.
SHAPE_COLS = ["initial_price_std", "initial_recency_mins", "initial_total_usd",
              "initial_best_backer_rank"]
HAS_SHAPE_SQL = ("SELECT column_name FROM information_schema.columns "
                 "WHERE table_name='consensus_signals' "
                 "AND column_name='initial_price_std'")
ATFIRE_UNCAP_COV = 0.95

# Dimension registry: (dim_id, at_fire_true). DRIFT-DEFINED dims are †-capped.
DIMS = [
    ("regime", True), ("mtype", True), ("band3", True),
    ("netc", True), ("opp", True), ("sigma", False),
    ("elite", False), ("rank3", False), ("fresh", False),
    ("liq", False), ("tod", True), ("horizon", True),
]
DRIFTED = {d for d, at_fire in DIMS if not at_fire}


def fetch():
    probe = subprocess.run(PG, input=HAS_SHAPE_SQL, capture_output=True, text=True)
    has_shape = "initial_price_std" in probe.stdout
    shape_cols = (", ".join(SHAPE_COLS) if has_shape
                  else ", ".join(f"NULL AS {c}" for c in SHAPE_COLS))
    out = subprocess.run(PG + ["-f", "-"], input=SQL.format(shape_cols=shape_cols),
                         capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    rows = []
    for r in csv.DictReader(io.StringIO(out.stdout)):
        for k in ("entry", "drifted", "t_fire", "t_res", "price_std", "total_usd",
                  "initial_price_std", "initial_total_usd"):
            r[k] = float(r[k]) if r[k] not in ("", None) else None
        for k in ("won", "hour", "initial_net_count", "initial_n_backers",
                  "net_count", "n_backers", "recency_mins", "best_backer_rank",
                  "initial_recency_mins", "initial_best_backer_rank"):
            r[k] = int(r[k]) if r[k] not in ("", None) else None
        rows.append(r)
    return rows


def classify_mtype(slug, title):
    """Market-type classifier (pre-registered patterns; coverage reported → K1)."""
    s, t = (slug or ""), (title or "")
    if "-exact-score" in s or t.startswith("Exact Score"):
        return "exact-score"
    if "-spread-" in s or t.startswith("Spread:"):
        return "spread"
    if "-total-" in s or "O/U" in t or "Over/Under" in t:
        return "over-under"
    if "-btts" in s or "Both Teams to Score" in t:
        return "prop"
    if s.endswith("-draw") or "end in a draw" in t:
        return "draw"
    tl = t.lower()
    if "champion" in tl or "to win the" in tl or "nominee" in tl or s.endswith("-winner"):
        return "futures"
    if ("up-or-down" in s or "-above-" in s or " above " in tl
            or "up or down" in tl):
        return "over-under"          # crypto threshold markets are O/U-shaped
    if ("-halftime" in s or "-first-to-score" in s or "-goals-" in s
            or "first-half" in s or "-corners" in s or "-cards" in s
            or "-scorer" in s):
        return "prop"
    import re
    if re.match(r"^[a-z0-9]+(-[a-z0-9]+)*-\d{4}-\d{2}-\d{2}$", s) and " vs" in tl:
        return "moneyline"
    if ("-team-to-advance" in s                       # who advances = match-outcome
            or re.search(r"-game\d+$", s)             # e.g. LoL per-game winner
            or re.match(r"^will .* win on \d{4}-\d{2}-\d{2}\?", tl)):
        return "moneyline"
    return None


def assign_cells(r, liq_cuts):
    """Row → {dim: cell or None}. At-fire-true fields preferred (see pre-registration)."""
    cells = {}
    cells["regime"] = sn.regime(r["event_slug"])
    cells["mtype"] = classify_mtype(r["slug"], r["title"])
    e = r["entry"]
    cells["band3"] = ("0.65-0.80" if 0.65 <= e < 0.80 else
                      "0.80-0.90" if 0.80 <= e < 0.90 else
                      "0.90-0.97" if 0.90 <= e < 0.97 else None)
    nc = r["initial_net_count"] if r["initial_net_count"] is not None else r["net_count"]
    cells["netc"] = (None if nc is None or nc < 3 else
                     "3" if nc == 3 else "4-5" if nc <= 5 else "6+")
    nb = r["initial_n_backers"] if r["initial_n_backers"] is not None else r["n_backers"]
    cells["opp"] = None if nb is None or nc is None else ("0" if nb - nc == 0 else ">=1")
    r["_shape_at_fire"] = r["initial_price_std"] is not None
    sd = r["initial_price_std"] if r["_shape_at_fire"] else r["price_std"]
    cells["sigma"] = (None if sd is None or sd > 0.10 else
                      "<=0.04" if sd <= 0.04 else "0.04-0.10")
    br = (r["initial_best_backer_rank"] if r["initial_best_backer_rank"] is not None
          else r["best_backer_rank"])
    cells["elite"] = None if br is None else ("elite<=10" if br <= 10 else "no-elite")
    cells["rank3"] = (None if br is None or br > 40 else
                      "<=10" if br <= 10 else "11-25" if br <= 25 else "26-40")
    rm = (r["initial_recency_mins"] if r["initial_recency_mins"] is not None
          else r["recency_mins"])
    cells["fresh"] = (None if rm is None or rm > 2880 else
                      "<=30m" if rm <= 30 else "30m-3h" if rm <= 180 else "3h-48h")
    u = (r["initial_total_usd"] if r["initial_total_usd"] is not None
         else r["total_usd"])
    cells["liq"] = (None if u is None else
                    "lo" if u < liq_cuts[0] else "mid" if u < liq_cuts[1] else "hi")
    cells["tod"] = f"{(r['hour'] // 8) * 8:02d}-{(r['hour'] // 8) * 8 + 8:02d}"
    if r["t_res"] is not None and r["t_fire"] is not None:
        h = (r["t_res"] - r["t_fire"]) / 3600.0
        cells["horizon"] = "<6h" if h < 6 else "6-24h" if h <= 24 else ">24h"
    else:
        cells["horizon"] = None
    return cells


def bh_fdr(pvals, q):
    """Benjamini-Hochberg: returns the set of indices that survive at FDR q."""
    order = sorted(range(len(pvals)), key=lambda i: pvals[i])
    m = len(pvals)
    k_max = 0
    for rank, i in enumerate(order, start=1):
        if pvals[i] <= q * rank / m:
            k_max = rank
    return {order[i] for i in range(k_max)}


def ev_means(pairs):
    """[(ev, x)] → per-event means (the within-match leak fix)."""
    m = defaultdict(list)
    for ev, x in pairs:
        m[ev].append(x)
    return {ev: sum(v) / len(v) for ev, v in m.items()}


def analyze(rows, n_null=N_NULL, n_boot=N_BOOT, seed=SEED, populations=POPULATIONS,
            quiet=False):
    rng = random.Random(seed)
    nprng = np.random.default_rng(seed)

    blind = [r for r in rows if r["strategy"] == "_blind"]
    pop_rows = {p: [r for r in rows if r["strategy"] == p] for p in populations}
    all_pop = [r for p in populations for r in pop_rows[p]]
    if not blind or not all_pop:
        sys.exit("no blind baseline or no population rows")

    # Record shape (denominators).
    days = sorted({r["day"] for r in rows})
    n_days = len(days)
    t_max = max(r["t_fire"] for r in rows)
    t_48h = t_max - 48 * 3600

    # Liquidity tercile cuts on the pooled population record (documented in the JSON).
    usd = sorted(r["total_usd"] for r in all_pop if r["total_usd"] is not None)
    liq_cuts = ((usd[len(usd) // 3], usd[2 * len(usd) // 3]) if len(usd) >= 3
                else (float("inf"), float("inf")))

    # Matched blind baseline: (regime × 5-band), band-only fallback (flagged).
    rb, bb = defaultdict(list), defaultdict(list)
    for r in blind:
        a = r["won"] - r["entry"]
        rb[(sn.regime(r["event_slug"]), sn.band(r["entry"]))].append(a)
        bb[sn.band(r["entry"])].append(a)
    base_rb = {k: sum(v) / len(v) for k, v in rb.items()}
    base_b = {k: sum(v) / len(v) for k, v in bb.items()}

    def baseline(r):
        k = (sn.regime(r["event_slug"]), sn.band(r["entry"]))
        return base_rb.get(k, base_b.get(sn.band(r["entry"]), 0.0)), k in base_rb

    # Drifted baseline for K2 (same matching, drifted entries on BOTH sides).
    rb_d = defaultdict(list)
    for r in blind:
        rb_d[(sn.regime(r["event_slug"]), sn.band(r["drifted"]))].append(
            r["won"] - r["drifted"])
    base_rb_d = {k: sum(v) / len(v) for k, v in rb_d.items()}

    # Null pools: (band, day, regime) → [(ev, adjusted a)]; pre-adjusted by the matched
    # baseline so sn.null_pvalue can run with blind_edge={} (reusing its machinery).
    blind_cells = defaultdict(list)
    for r in blind:
        b0, _ = baseline(r)
        blind_cells[(sn.band(r["entry"]), r["day"], sn.regime(r["event_slug"]))].append(
            (r["ev"], r["won"] - r["entry"] - b0))

    # Market-type classifier coverage (K1) over the pooled populations.
    mt = [classify_mtype(r["slug"], r["title"]) for r in all_pop]
    mtype_cov = sum(1 for x in mt if x is not None) / len(mt)
    drop_mtype = mtype_cov < 0.90

    results = []
    for pop in populations:
        prows = pop_rows[pop]
        for r in prows:
            r["_cells"] = assign_cells(r, liq_cuts)
        for dim, at_fire in DIMS:
            if dim == "mtype" and drop_mtype:
                continue
            by_cell = defaultdict(list)
            for r in prows:
                c = r["_cells"][dim]
                if c is not None:
                    by_cell[c].append(r)
            for cell, crows in sorted(by_cell.items()):
                res = _cell_metrics(pop, dim, cell, crows, baseline, base_rb_d,
                                    blind_cells, rng, nprng, n_null, n_boot,
                                    n_days, t_48h, days)
                results.append(res)

    # BH-FDR across the whole family (cells with a valid p).
    idx = [i for i, r in enumerate(results) if r["p_emp"] is not None]
    surviving = bh_fdr([results[i]["p_emp"] for i in idx], FDR_Q)
    for rank, i in enumerate(idx):
        results[i]["fdr_pass"] = rank in surviving

    # Verdicts (binding rules — see module docstring / pre-registration). A DRIFT dim
    # un-caps once ≥95% of the cell's rows carry the migration-036 at-fire shape.
    for r in results:
        r["capped"] = (r["dim"] in DRIFTED
                       and r.get("atfire_cov", 0.0) < ATFIRE_UNCAP_COV)
        v = "NEUTRAL"
        splits = max(r["days_pos"], r["regimes_pos"])
        if (r.get("fdr_pass") and r["roi_lb"] is not None and r["roi_lb"] > 0
                and r["n_events"] >= N_FLOOR and splits >= 2
                and r["freq_recent"] >= FREQ_FLOOR and not r["unstable"]):
            v = "PRIORITIZE"
        elif (r["roi_ub"] is not None and r["roi_ub"] < 0
                and r["n_events"] >= N_FLOOR and not r["unstable"]):
            v = "DODGE"
        if r["unstable"] and v != "NEUTRAL":
            v = "UNSTABLE"
        if r["capped"] and v in ("PRIORITIZE", "DODGE"):
            v += "†"  # drift-defined: nominates at-fire capture, never binds
        r["verdict"] = v

    meta = {"seed": seed, "n_null": n_null, "n_boot": n_boot, "fdr_q": FDR_Q,
            "haircut": HAIRCUT, "fee": FEE, "n_floor": N_FLOOR,
            "freq_floor": FREQ_FLOOR, "days": days, "n_days": n_days,
            "mtype_coverage": round(mtype_cov, 4), "mtype_dropped_K1": drop_mtype,
            "liq_cuts_usd": [round(c, 2) for c in liq_cuts],
            "family_size": len(idx),
            "fdr_survivors": sum(1 for r in results if r.get("fdr_pass"))}
    if not quiet:
        _print_table(results, meta)
    return results, meta


def _cell_metrics(pop, dim, cell, crows, baseline, base_rb_d, blind_cells,
                  rng, nprng, n_null, n_boot, n_days, t_48h, days):
    picks, meta_cells, roi_pairs, drift_pairs = [], [], [], []
    fallback_n = 0
    for r in crows:
        b0, matched = baseline(r)
        if not matched:
            fallback_n += 1
        a_adj = r["won"] - r["entry"] - b0
        picks.append((r["ev"], sn.band(r["entry"]), a_adj))
        meta_cells.append((sn.band(r["entry"]), r["day"], sn.regime(r["event_slug"])))
        e = min(0.999, r["entry"] + HAIRCUT)
        roi_pairs.append((r["ev"], (r["won"] - e) / e - FEE))
        bd = base_rb_d.get((sn.regime(r["event_slug"]), sn.band(r["drifted"])), b0)
        drift_pairs.append((r["ev"], r["won"] - r["drifted"] - bd))

    obs, n_events = sn.clustered_surplus(picks, {})

    # Selection-matched null (profile: band × day × regime), reusing sn.null_pvalue.
    p_emp = None
    if n_events >= READOUT_FLOOR:
        draws = sn.null_pvalue(meta_cells, blind_cells, {}, rng, n_null)
        if len(draws) >= 0.8 * n_null:  # live: n_null=1200 → ≥960≈the 1000-draw bar
            p_emp = sum(1 for x in draws if x >= obs) / len(draws)

    # Realizable ROI (event-clustered) + bootstrap CI.
    ev_roi = list(ev_means(roi_pairs).values())
    roi = float(np.mean(ev_roi))
    roi_lb = roi_ub = None
    if len(ev_roi) >= 5:
        arr = np.array(ev_roi)
        boots = np.array([arr[nprng.integers(0, len(arr), len(arr))].mean()
                          for _ in range(n_boot)])
        roi_lb, roi_ub = float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))

    # Frequency: whole record + last 48h (the planning number).
    evs = {r["ev"] for r in crows}
    ev_first_fire = {}
    for r in crows:
        ev_first_fire[r["ev"]] = min(ev_first_fire.get(r["ev"], r["t_fire"]), r["t_fire"])
    n48 = sum(1 for t in ev_first_fire.values() if t >= t_48h)
    freq_all, freq_recent = len(evs) / n_days, n48 / 2.0

    # $/day joint bootstrap: Poisson on the 48h count × the ROI bootstrap.
    dpd = STAKE * roi * freq_recent
    dpd_lb = dpd_ub = None
    if len(ev_roi) >= 5:
        ks = nprng.poisson(max(n48, 1e-9), n_boot) / 2.0
        vals = STAKE * boots * ks
        dpd_lb, dpd_ub = float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))

    # Persistence: matched surplus > 0 per UTC day / per regime.
    by_day, by_reg = defaultdict(list), defaultdict(list)
    for (ev, _b, a), r in zip(picks, crows):
        by_day[r["day"]].append((ev, a))
        by_reg[sn.regime(r["event_slug"])].append((ev, a))
    day_surp = {d: float(np.mean(list(ev_means(v).values()))) for d, v in by_day.items()}
    reg_surp = {g: float(np.mean(list(ev_means(v).values()))) for g, v in by_reg.items()}
    days_pos = sum(1 for v in day_surp.values() if v > 0)
    regimes_pos = sum(1 for v in reg_surp.values() if v > 0)

    # K2: drifted-entry recomputation; sign flip ⇒ UNSTABLE.
    drift_obs = float(np.mean(list(ev_means(drift_pairs).values())))
    unstable = (obs > 0) != (drift_obs > 0) and abs(obs) > 1e-9

    # Leave-one-day-out fragility + soccer WC-exclusion.
    lodo_min = None
    if len(day_surp) >= 2:
        lodo = []
        for d in day_surp:
            sub = [(ev, a) for (ev, _b, a), r in zip(picks, crows) if r["day"] != d]
            if sub:
                lodo.append(float(np.mean(list(ev_means(sub).values()))))
        lodo_min = min(lodo) if lodo else None
    ex_wc = None
    soccer_frac = sum(1 for r in crows
                      if sn.regime(r["event_slug"]) == "soccer") / len(crows)
    if soccer_frac >= 0.30:
        sub = [(ev, a) for (ev, _b, a), r in zip(picks, crows)
               if not (r["event_slug"] or "").startswith("fifwc")]
        if sub:
            em = list(ev_means(sub).values())
            ex_wc = {"n_events": len(em), "surplus": float(np.mean(em))}
        else:
            ex_wc = {"n_events": 0, "surplus": None}

    atfire_cov = (sum(1 for r in crows if r.get("_shape_at_fire")) / len(crows)
                  if crows else 0.0)

    return {"pop": pop, "dim": dim, "cell": cell, "n_rows": len(crows),
            "atfire_cov": atfire_cov,
            "n_events": n_events, "surplus": obs, "p_emp": p_emp,
            "roi": roi, "roi_lb": roi_lb, "roi_ub": roi_ub,
            "freq_all": freq_all, "freq_recent": freq_recent, "n48": n48,
            "dollars_per_day": dpd, "dpd_lb": dpd_lb, "dpd_ub": dpd_ub,
            "days_pos": days_pos, "days_n": len(day_surp),
            "regimes_pos": regimes_pos, "regimes_n": len(reg_surp),
            "drift_surplus": drift_obs, "unstable": unstable,
            "lodo_min_surplus": lodo_min, "ex_wc": ex_wc,
            "baseline_fallback_rows": fallback_n}


def _fmt(x, spec="+.1%", none="    —"):
    return none if x is None else format(x, spec)


def _print_table(results, meta):
    print(f"slice study · seed {meta['seed']} · null {meta['n_null']} draws · "
          f"boot {meta['n_boot']} · BH-FDR q={meta['fdr_q']} over {meta['family_size']} "
          f"cells → {meta['fdr_survivors']} survive · haircut {HAIRCUT*100:.1f}¢ fee "
          f"{FEE:.0%} · record {meta['n_days']}d {meta['days'][0]}→{meta['days'][-1]}")
    print(f"market-type classifier coverage {meta['mtype_coverage']:.1%}"
          f"{' → K1: dimension DROPPED' if meta['mtype_dropped_K1'] else ''}"
          f" · liq terciles ${meta['liq_cuts_usd'][0]:,.0f}/${meta['liq_cuts_usd'][1]:,.0f}")
    hdr = (f"{'pop':<16}{'dim':<8}{'cell':<10}{'ev':>4} {'surplus':>8} {'p':>7} "
           f"{'FDR':>4} {'ROI[lb,ub]':>19} {'f/d48':>6} {'$/day[lb,ub]':>20} "
           f"{'d+':>3} {'r+':>3}  verdict")
    print(hdr)
    print("-" * len(hdr))
    order = {"PRIORITIZE": 0, "PRIORITIZE†": 1, "DODGE": 2, "DODGE†": 3,
             "UNSTABLE": 4, "NEUTRAL": 5}
    for r in sorted(results, key=lambda r: (order.get(r["verdict"], 9),
                                            -(r["dollars_per_day"] or 0))):
        roi_s = (f"{_fmt(r['roi'])}[{_fmt(r['roi_lb'])},{_fmt(r['roi_ub'])}]")
        dpd_s = (f"{r['dollars_per_day']:+7.1f}[" +
                 (f"{r['dpd_lb']:+.0f},{r['dpd_ub']:+.0f}]" if r['dpd_lb'] is not None
                  else "—]"))
        print(f"{r['pop']:<16}{r['dim']:<8}{r['cell']:<10}{r['n_events']:>4} "
              f"{_fmt(r['surplus'])} {_fmt(r['p_emp'], '.4f')} "
              f"{'✓' if r.get('fdr_pass') else '·':>4} {roi_s:>19} "
              f"{r['freq_recent']:>6.1f} {dpd_s:>20} "
              f"{r['days_pos']:>2}/{r['days_n']} {r['regimes_pos']:>2}/{r['regimes_n']}"
              f"  {r['verdict']}")


# --- Self-test: a KNOWN injected edge must PRIORITIZE; a no-edge cell must stay
# --- NEUTRAL; a pure-noise fixture must give 0 FDR survivors. -------------------
def _synth(edge_tennis, seed=SEED):
    """4-day fixture. Blind universe ~3200 rows; strategy 'synthpop' fires on tennis
    (edge injected) and soccer (none), ≥1 event/day recent. Efficient market
    elsewhere: P(win) = entry."""
    rng = random.Random(seed)
    days = ["2026-06-29", "2026-06-30", "2026-07-01", "2026-07-02"]
    t0 = 1_800_000_000.0
    regs = [("atp-x{}-y{}-{}", "tennis"), ("fifwc-a{}-b{}-{}", "soccer"),
            ("btc-up-{}-{}x", "crypto")]
    rows = []

    def mk(strategy, slugf, i, di, entry, won):
        ev = slugf.format(i, i, days[di])
        return {"strategy": strategy, "ev": ev, "event_slug": ev,
                "slug": ev, "title": "A vs B",
                "entry": entry, "drifted": min(0.999, entry + rng.gauss(0.005, 0.01)),
                "won": won, "day": days[di], "hour": rng.randrange(24),
                "t_fire": t0 + di * 86400 + rng.uniform(0, 86000),
                "t_res": t0 + di * 86400 + 90000,
                "initial_net_count": rng.choice([3, 3, 4, 5, 6]),
                "initial_n_backers": None, "net_count": None, "n_backers": None,
                "price_std": rng.uniform(0.01, 0.09),
                "recency_mins": rng.randrange(5, 2000),
                "total_usd": rng.uniform(100, 20000),
                "best_backer_rank": rng.randrange(1, 40),
                "initial_price_std": None, "initial_recency_mins": None,
                "initial_total_usd": None, "initial_best_backer_rank": None}

    for di in range(4):
        for i in range(270):
            slugf, _ = regs[i % 3]
            entry = rng.uniform(0.55, 0.95)
            rows.append(mk("_blind", slugf, i, di, entry,
                           int(rng.random() < entry)))
        for i in range(300, 340):  # tennis picks: injected selection edge
            entry = rng.uniform(0.65, 0.92)
            p = min(0.99, entry + edge_tennis)
            rows.append(mk("synthpop", "atp-x{}-y{}-{}", i, di, entry,
                           int(rng.random() < p)))
        for i in range(400, 440):  # soccer picks: no edge
            entry = rng.uniform(0.65, 0.92)
            rows.append(mk("synthpop", "fifwc-a{}-b{}-{}", i, di, entry,
                           int(rng.random() < entry)))
    for r in rows:  # complete the n_backers pair for the opp dim
        r["initial_n_backers"] = r["initial_net_count"] + rng.choice([0, 0, 1])
    return rows


def selftest():
    print("— fixture 1: tennis edge +0.12, soccer none —")
    res, meta = analyze(_synth(0.12), n_null=600, n_boot=500,
                        populations=["synthpop"], quiet=True)
    by = {(r["dim"], r["cell"]): r for r in res if r["pop"] == "synthpop"}
    x = by[("regime", "tennis")]
    y = by[("regime", "soccer")]
    ok = True
    if x["verdict"] != "PRIORITIZE":
        ok = False
        print(f"FAIL: injected-edge cell X (tennis) → {x['verdict']} "
              f"(surplus {x['surplus']:+.2%}, p {_fmt(x['p_emp'], '.4f')}, "
              f"roi_lb {_fmt(x['roi_lb'])})")
    else:
        print(f"pass: X (tennis) PRIORITIZE (surplus {x['surplus']:+.2%}, "
              f"p {_fmt(x['p_emp'], '.4f')})")
    if y["verdict"] != "NEUTRAL":
        ok = False
        print(f"FAIL: no-edge cell Y (soccer) → {y['verdict']} "
              f"(surplus {y['surplus']:+.2%}, p {_fmt(y['p_emp'], '.4f')})")
    else:
        print(f"pass: Y (soccer) NEUTRAL (surplus {y['surplus']:+.2%}, "
              f"p {_fmt(y['p_emp'], '.4f')})")

    print("— fixture 2: pure noise —")
    res0, meta0 = analyze(_synth(0.0), n_null=600, n_boot=500,
                          populations=["synthpop"], quiet=True)
    n_surv = meta0["fdr_survivors"]
    n_prior = sum(1 for r in res0 if r["verdict"].startswith("PRIORITIZE"))
    if n_surv > 0 or n_prior > 0:
        ok = False
        print(f"FAIL: pure-noise fixture → {n_surv} FDR survivors, "
              f"{n_prior} PRIORITIZE")
    else:
        print("pass: pure-noise fixture → 0 FDR survivors, 0 PRIORITIZE")
    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    rows = fetch()
    results, meta = analyze(rows)
    art = {"meta": meta, "cells": results}
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "reports", "slice_study.json")
    with open(out, "w") as f:
        json.dump(art, f, indent=1, default=str)
    print(f"\nartifact → reports/slice_study.json")


if __name__ == "__main__":
    main()
