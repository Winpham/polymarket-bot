#!/usr/bin/env python3
"""
CONSOLIDATE-AND-IMPROVE harness (Cycle 8) — test accumulated learnings as CHALLENGERS to the STANDARD.

The STANDARD (champion) is the favorite-tilted consensus family (`favorite` + `elite_fresh_fav`;
reports/baseline_champion.json). This harness formulates each accumulated learning as a CHALLENGER —
a re-selection / re-weight / overlay of the standard — and judges it through the SAME belief-blind
machinery the standard was validated with, then hands the verdict to standard_guard.judge_challenger.
It ADOPTS NOTHING; it reports ADOPT / CHAMPION-STANDS / INDETERMINATE-BY-POWER per challenger, with
realizable-edge deltas + bootstrap CIs. NEVER manufactures a win — INDETERMINATE-BY-POWER is honest
and expected for most subset challengers on ~8 correlated days.

Reuse (no logic rebuild):
  - selection_null.py  : band(), regime(), clustered_surplus(), null_pvalue() — the IDENTICAL null.
  - standard_guard.py  : judge_challenger(), belief_blind_lb(), TAX_BY_BAND, POWER_FLOOR, P_BAR.
  - reliability_score.py / trader_scorecard.py : reliable-wallet pool + MM/bot flags.

Metrics, all LABELED:
  - realizable_roi : event-clustered honest_roi at the MEASURED band-aware tax over `initial_market_price`
                     — the EXACT metric standard_guard uses (verified in --selftest to reproduce the
                     champion family +4.90%). This is the OOS metric a challenger must BEAT.
  - belief-blind   : selection_null surplus over the band-matched `_blind` baseline (at-fire entry),
                     p_emp, one-sided LB, and disjoint NON-soccer regimes positive. The honest gate.

Challengers:
  1 reliable_backed   — favorite events whose backers include a durably-reliable trader (reliability_score
                        shortlist / skill pool). "Concentrate on durably-skilled backers."
  2 clean_backers     — favorite events whose backer pool is directional (drop MM/bot-dominated). "Cleaner
                        backers -> cleaner signal."
  3 midband_consensus — CONSENSUS (strict) restricted to band 0.35-0.65: is it selection-real, and does a
                        favorite+midband combined book DIVERSIFY the standard (day-return corr, Calmar)?
  4 clv_exit          — overlay: exit favorite positions at a CLV target vs hold-to-resolution (variance /
                        drawdown / capital-velocity). Selection UNCHANGED -> risk-adjusted axis only.
  5 conviction_sizing — overlay: size favorite bets by cell-edge x conviction (cap 3% bankroll) vs flat.
                        Selection UNCHANGED -> compounding / Calmar axis only.

  ./consolidate_challengers.py            # live: test all, write reports/consolidate_challengers.json
  ./consolidate_challengers.py --selftest # pure/fixture tests incl. guard-reproduction; NO heavy DB perm

PAPER-ONLY. Promotes/arms/adopts NOTHING. No Rust. DB READ-ONLY. Cost-zero (Max-only).
"""

import argparse
import csv
import io
import json
import math
import os
import random
import subprocess
import sys
from collections import defaultdict

csv.field_size_limit(1 << 24)  # backers/observed_votes jsonb fields are large

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import selection_null as sn          # noqa: E402
import standard_guard as guard       # noqa: E402

REPORT_DIR = os.path.join(os.path.dirname(HERE), "reports")
REPORT = os.path.join(REPORT_DIR, "consolidate_challengers.json")
PG = sn.PG
SEED = 20260702
N_PERM = 2000
POWER_FLOOR = guard.POWER_FLOOR          # 30 distinct events for belief-blind
TAX = guard.TAX_BY_BAND
CHAMP_ARMS = ("favorite", "elite_fresh_fav")


# ----------------------------------------------------------------- data
def q(sql):
    r = subprocess.run(PG + ["-c", sql], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("psql failed:\n" + r.stderr)
    return list(csv.DictReader(io.StringIO(r.stdout)))


def fetch_signals():
    rows = q("""
      SELECT strategy, COALESCE(event_slug,condition_id) AS ev, event_slug,
             COALESCE(initial_mean_price, mean_price) AS entry,
             initial_market_price, last_market_price,
             (outcome_won::int) AS won,
             to_char(first_detected_at AT TIME ZONE 'UTC','YYYY-MM-DD') AS day,
             net_quality, n_backers, net_count, backers, observed_votes
      FROM consensus_signals
      WHERE resolved AND strategy IN ('_blind','favorite','elite_fresh_fav','strict')
    """)
    for r in rows:
        r["entry"] = float(r["entry"]) if r["entry"] not in (None, "") else None
        r["imp"] = float(r["initial_market_price"]) if r["initial_market_price"] not in (None, "") else None
        r["last"] = float(r["last_market_price"]) if r["last_market_price"] not in (None, "") else None
        r["won"] = int(r["won"]) if r["won"] not in (None, "") else None
        r["net_quality"] = float(r["net_quality"]) if r["net_quality"] not in (None, "") else 0.0
    return rows


def backer_wallets(r):
    try:
        return {(x.get("wallet") or "").lower() for x in json.loads(r["backers"] or "[]")}
    except Exception:
        return set()


# ----------------------------------------------------------------- realizable (guard's EXACT metric)
def realizable_roi(rows):
    """Event-clustered honest_roi at band-aware tax over initial_market_price. Mirrors
    standard_guard.realizable_roi_at_band_tax (WHERE initial_market_price NOT NULL, width_bucket 0..1/5,
    hroi=(won-(p0+tx))/(p0+tx), event-clustered). Returns (mean_roi|None, n_events)."""
    ev_map = defaultdict(list)
    for r in rows:
        p0 = r["imp"]
        if p0 is None or r["won"] is None:
            continue
        b = sn.band(p0)                       # width_bucket(p0,0,1,5)
        tx = TAX.get(b)
        if tx is None:
            continue
        denom = p0 + tx
        if denom == 0:
            continue
        ev_map[r["ev"]].append((r["won"] - denom) / denom)
    if not ev_map:
        return None, 0
    means = [sum(v) / len(v) for v in ev_map.values()]
    return sum(means) / len(means), len(means)


# ----------------------------------------------------------------- belief-blind (selection_null math)
def build_blind(rows):
    blind = [r for r in rows if r["strategy"] == "_blind" and r["entry"] is not None and r["won"] is not None]
    blind_cells = defaultdict(list)
    blind_band = defaultdict(list)
    rb_edge = defaultdict(lambda: defaultdict(list))
    for r in blind:
        b = sn.band(r["entry"])
        a = r["won"] - r["entry"]
        blind_cells[(b, r["day"])].append((r["ev"], a))
        blind_band[b].append(a)
        rb_edge[sn.regime(r["event_slug"])][b].append(a)
    blind_edge = {b: sum(v) / len(v) for b, v in blind_band.items()}
    rb = {rg: {b: sum(v) / len(v) for b, v in bands.items()} for rg, bands in rb_edge.items()}
    return blind_cells, blind_edge, rb


def belief_blind(picks, blind_cells, blind_edge, rb, rng, n_perm=N_PERM):
    """picks: list of signal rows (entry, won, event_slug, ev, day). Returns dict with
    events, observed surplus, null_sigma, z, p_emp, lb, non_soccer_regimes_positive."""
    picks = [r for r in picks if r["entry"] is not None and r["won"] is not None]
    trip = [(r["ev"], sn.band(r["entry"]), r["won"] - r["entry"]) for r in picks]
    obs, n_ev = sn.clustered_surplus(trip, blind_edge)
    if n_ev < POWER_FLOOR:
        return {"events": n_ev, "observed": obs if n_ev else None, "underpowered": True}
    meta = [(sn.band(r["entry"]), r["day"]) for r in picks]
    draws = sn.null_pvalue(meta, blind_cells, blind_edge, rng, n_perm)
    if len(draws) < 1000:
        return {"events": n_ev, "observed": obs, "null_unmatchable": True}
    mu = sum(draws) / len(draws)
    sd = math.sqrt(sum((x - mu) ** 2 for x in draws) / (len(draws) - 1))
    z = (obs - mu) / sd if sd > 0 else float("nan")
    p = sum(1 for x in draws if x >= obs) / len(draws)
    lb = guard.belief_blind_lb(obs, sd)
    # non-soccer regime persistence (regime x band matched blind baseline)
    by_reg = defaultdict(list)
    for r in picks:
        rg = sn.regime(r["event_slug"])
        base = rb.get(rg, {}).get(sn.band(r["entry"]))
        if base is None:
            continue
        by_reg[rg].append((r["ev"], r["won"] - r["entry"] - base))
    reg_surplus = {}
    for rg, prs in by_reg.items():
        em = defaultdict(list)
        for ev, s in prs:
            em[ev].append(s)
        means = [sum(v) / len(v) for v in em.values()]
        reg_surplus[rg] = sum(means) / len(means)
    nsr = sum(1 for rg, v in reg_surplus.items() if rg != "soccer" and v > 0)
    return {"events": n_ev, "observed": obs, "null_mu": mu, "null_sigma": sd, "z": z,
            "p_emp": p, "belief_blind_lb": lb, "non_soccer_regimes_positive": nsr,
            "regime_surplus": reg_surplus, "underpowered": False}


# ----------------------------------------------------------------- bootstrap CI on realizable-edge delta
def bootstrap_delta_ci(chal_rows, champ_rows, n_boot=2000, seed=SEED):
    """Event-clustered bootstrap of (challenger realizable - champion realizable). Resample the UNION of
    events with replacement; recompute both event-clustered ROIs on the resampled event set. 90% CI."""
    def ev_means(rows):
        m = defaultdict(list)
        for r in rows:
            p0 = r["imp"]
            if p0 is None or r["won"] is None:
                continue
            b = sn.band(p0); tx = TAX.get(b)
            if tx is None:
                continue
            m[r["ev"]].append((r["won"] - (p0 + tx)) / (p0 + tx))
        return {ev: sum(v) / len(v) for ev, v in m.items()}
    cm = ev_means(chal_rows)
    hm = ev_means(champ_rows)
    all_ev = list(set(cm) | set(hm))
    if not all_ev:
        return None, None, None
    rng = random.Random(seed)
    deltas = []
    for _ in range(n_boot):
        samp = [all_ev[rng.randrange(len(all_ev))] for _ in all_ev]
        cv = [cm[e] for e in samp if e in cm]
        hv = [hm[e] for e in samp if e in hm]
        if not cv or not hv:
            continue
        deltas.append(sum(cv) / len(cv) - sum(hv) / len(hv))
    if not deltas:
        return None, None, None
    deltas.sort()
    lo = deltas[int(0.05 * len(deltas))]
    hi = deltas[int(0.95 * len(deltas))]
    point = (sum(cm.values()) / len(cm)) - (sum(hm.values()) / len(hm)) if cm and hm else None
    return point, lo, hi


# ----------------------------------------------------------------- verdict wrapper
def verdict_for(chal_bb, chal_realizable, champ_realizable, champ_bb, calibrate):
    """Return (verdict, adopt, reasons). Uses guard.judge_challenger for the ADOPT decision; classifies
    the non-adopt space into CHAMPION-STANDS (discard) vs INDETERMINATE-BY-POWER (pre-register)."""
    if chal_bb.get("underpowered") or chal_bb.get("null_unmatchable"):
        return ("INDETERMINATE-BY-POWER",
                False,
                [f"belief-blind underpowered: {chal_bb.get('events')} events "
                 f"< {POWER_FLOOR} floor (or null unmatchable)"])
    champ_metric = {"realizable_roi": champ_realizable,
                    "observed": champ_bb["observed"], "null_sigma": champ_bb["null_sigma"]}
    chal_metric = {"realizable_roi": chal_realizable,
                   "observed": chal_bb["observed"], "null_sigma": chal_bb["null_sigma"],
                   "p_emp": chal_bb["p_emp"],
                   "non_soccer_regimes_positive": chal_bb["non_soccer_regimes_positive"]}
    adopt, v, reasons = guard.judge_challenger(champ_metric, chal_metric, calibrate)
    if adopt:
        return "ADOPT-CHALLENGER", True, reasons
    beats = (chal_realizable is not None and champ_realizable is not None
             and chal_realizable > champ_realizable)
    promising_bb = chal_bb.get("p_emp") is not None and chal_bb["p_emp"] <= 0.10
    if beats and promising_bb:
        return "INDETERMINATE-BY-POWER", False, reasons + ["beats realizable + belief-blind promising "
                                                           "(p<=0.10) but under strict gate -> pre-register"]
    return "CHAMPION-STANDS", False, reasons


# ----------------------------------------------------------------- MM/bot flags (challenger 2)
def mm_bot_flags():
    try:
        import trader_scorecard as tsc
        micro = tsc.fetch_micro()
        bots = tsc.fetch_bot_flags()
        mm = {w for w, m in micro.items() if tsc.is_mm(m)}
        bot = {w for w, t in bots.items() if t == "bot"}
        return mm, bot
    except Exception as e:
        print(f"  [warn] MM/bot flags unavailable ({e}); clean_backers challenger skipped", file=sys.stderr)
        return None, None


def reliable_pool():
    """Reliable-wallet pool from reliability_score.json: shortlist (durable) + skill (cal_gap>0,
    null_p<=0.05, directional). Returns (shortlist_set, skill_set)."""
    path = os.path.join(REPORT_DIR, "reliability_score.json")
    if not os.path.exists(path):
        return set(), set()
    rep = json.load(open(path))
    short = {v["wallet"].lower() for v in rep.get("shortlist", [])}
    skill = {v["wallet"].lower() for v in rep.get("all_scored", [])
             if v.get("cal_gap") and v["cal_gap"] > 0 and v.get("null_p") is not None
             and v["null_p"] <= 0.05 and not v.get("is_mm") and not v.get("is_bot")}
    return short, skill | short


# ----------------------------------------------------------------- overlays (challengers 4,5)
def clv_exit_overlay(fav_rows):
    """Exit-at-CLV vs hold. For each favorite signal with last_market_price observed while open:
    if the market moved in our favor by >= target (last - entry >= target), 'exit' locking the CLV
    (payoff = last - entry, capped realized), else hold to resolution (payoff = won - entry). We compare
    per-event realized return distributions: mean, sd, max-drawdown of the equity curve, and the
    fraction of positions exited (capital velocity proxy). initial_market_price basis; 1c haircut."""
    rows = [r for r in fav_rows if r["imp"] is not None and r["last"] is not None and r["won"] is not None]
    out = {}
    for target in (0.03, 0.05, 0.08):
        hold_ev, exit_ev = defaultdict(list), defaultdict(list)
        exited = 0
        for r in rows:
            p0 = r["imp"]
            hold_ret = (r["won"] - (p0 + 0.01)) / (p0 + 0.01)
            clv = r["last"] - p0
            if clv >= target:                     # lock in the CLV move (sell at last observed mid - 1c)
                sell = max(0.0, min(0.999, r["last"] - 0.01))
                ret = (sell - (p0 + 0.01)) / (p0 + 0.01)
                exited += 1
            else:
                ret = hold_ret
            hold_ev[r["ev"]].append(hold_ret)
            exit_ev[r["ev"]].append(ret)
        def summ(evm):
            means = [sum(v) / len(v) for v in evm.values()]
            n = len(means)
            mu = sum(means) / n if n else None
            sd = math.sqrt(sum((x - mu) ** 2 for x in means) / (n - 1)) if n > 1 else None
            # max drawdown of the equity curve (event order arbitrary -> report sd as risk proxy too)
            eq = 0.0; peak = 0.0; mdd = 0.0
            for x in means:
                eq += x; peak = max(peak, eq); mdd = max(mdd, peak - eq)
            return {"events": n, "mean": mu, "sd": sd, "max_drawdown": mdd}
        h, e = summ(hold_ev), summ(exit_ev)
        out[f"target_{target:.2f}"] = {
            "hold": h, "exit": e, "exit_fraction": exited / len(rows) if rows else 0.0,
            "mean_delta": (e["mean"] - h["mean"]) if (e["mean"] is not None and h["mean"] is not None) else None,
            "sd_delta": (e["sd"] - h["sd"]) if (e["sd"] is not None and h["sd"] is not None) else None,
        }
    out["_coverage"] = {"favorite_with_last_price": len(rows)}
    return out


def conviction_sizing_overlay(fav_rows, blind_edge):
    """Size favorite bets by conviction (net_quality percentile, cap 3% bankroll) vs flat 1%. Compare
    realized log-wealth growth + Calmar over the resolved sequence (event order = day order). Selection
    is UNCHANGED; this is a compounding/risk-adjusted overlay, NOT a selection edge. Block-day resample
    gives a rough CI on the log-growth delta."""
    rows = [r for r in fav_rows if r["imp"] is not None and r["won"] is not None]
    rows.sort(key=lambda r: r["day"])
    if not rows:
        return {}
    nqs = sorted(r["net_quality"] for r in rows)
    def pct(x):
        # percentile rank of net_quality in [0,1]
        lo = sum(1 for v in nqs if v < x)
        return lo / len(nqs) if nqs else 0.5
    def sim(size_fn, cap):
        wealth = 1.0
        rets = []
        for r in rows:
            p0 = r["imp"]
            roi = (r["won"] - (p0 + 0.01)) / (p0 + 0.01)
            f = min(cap, size_fn(r))
            wealth *= (1.0 + f * roi)
            rets.append(f * roi)
            if wealth <= 0:
                wealth = 1e-9
                break
        # Calmar = total return / max drawdown of wealth curve
        eq = 1.0; peak = 1.0; mdd = 0.0; w = 1.0
        for r in rets:
            w *= (1.0 + r); peak = max(peak, w); mdd = max(mdd, (peak - w) / peak)
        total = w - 1.0
        calmar = total / mdd if mdd > 0 else (float("inf") if total > 0 else 0.0)
        return {"final_wealth": w, "log_growth": math.log(max(1e-9, w)), "total_return": total,
                "max_drawdown_frac": mdd, "calmar": calmar if calmar != float("inf") else None}
    flat = sim(lambda r: 0.01, 0.01)                                   # flat 1%
    conv = sim(lambda r: 0.01 + 0.02 * pct(r["net_quality"]), 0.03)    # 1%..3% by conviction
    return {"flat_1pct": flat, "conviction_1to3pct": conv,
            "log_growth_delta": conv["log_growth"] - flat["log_growth"],
            "n_events_sequence": len(rows),
            "note": "selection UNCHANGED; compounding/risk-adjusted overlay only, not a selection edge"}


# ----------------------------------------------------------------- day-return correlation (challenger 3)
def day_returns(rows):
    byday = defaultdict(list)
    for r in rows:
        p0 = r["imp"]
        if p0 is None or r["won"] is None:
            continue
        byday[r["day"]].append((r["won"] - (p0 + 0.01)) / (p0 + 0.01))
    return {d: sum(v) / len(v) for d, v in byday.items()}


def pearson(a, b):
    keys = sorted(set(a) & set(b))
    if len(keys) < 3:
        return None, len(keys)
    xs = [a[k] for k in keys]; ys = [b[k] for k in keys]
    mx = sum(xs) / len(xs); my = sum(ys) / len(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs)); dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return None, len(keys)
    return num / (dx * dy), len(keys)


# ----------------------------------------------------------------- main run
def run():
    rows = fetch_signals()
    rng = random.Random(SEED)
    blind_cells, blind_edge, rb = build_blind(rows)

    fav = [r for r in rows if r["strategy"] == "favorite"]
    elite = [r for r in rows if r["strategy"] == "elite_fresh_fav"]
    strict = [r for r in rows if r["strategy"] == "strict"]
    champ_rows = fav + elite

    # champion reference
    champ_realizable, champ_rn = realizable_roi(champ_rows)
    champ_bb = belief_blind(fav, blind_cells, blind_edge, rb, random.Random(SEED))
    calibrate = guard.selection_null_calibrate()

    results = {}

    # ---- Challenger 1: reliable_backed ----
    short, skill = reliable_pool()
    c1 = [r for r in fav if backer_wallets(r) & skill]
    bb1 = belief_blind(c1, blind_cells, blind_edge, rb, random.Random(SEED))
    rr1, rn1 = realizable_roi(c1)
    p1, lo1, hi1 = bootstrap_delta_ci(c1, champ_rows)
    v1, a1, r1 = verdict_for(bb1, rr1, champ_realizable, champ_bb, calibrate)
    results["1_reliable_backed"] = {
        "desc": "favorite events with >=1 durably-reliable backer (reliability_score skill pool)",
        "reliable_pool_size": len(skill), "shortlist_size": len(short),
        "belief_blind": bb1, "realizable_roi": rr1, "realizable_events": rn1,
        "realizable_delta_vs_champ": p1, "delta_ci90": [lo1, hi1],
        "verdict": v1, "adopt": a1, "reasons": r1}

    # ---- Challenger 2: clean_backers (directional screen) ----
    mm, bot = mm_bot_flags()
    if mm is not None:
        dirty = mm | bot
        def clean(r):
            w = backer_wallets(r)
            if not w:
                return True                       # no identifiable dirty backer -> keep
            return len(w & dirty) < len(w) / 2.0  # majority directional
        c2 = [r for r in fav if clean(r)]
        bb2 = belief_blind(c2, blind_cells, blind_edge, rb, random.Random(SEED))
        rr2, rn2 = realizable_roi(c2)
        p2, lo2, hi2 = bootstrap_delta_ci(c2, champ_rows)
        v2, a2, r2 = verdict_for(bb2, rr2, champ_realizable, champ_bb, calibrate)
        results["2_clean_backers"] = {
            "desc": "favorite events whose backer pool is majority-directional (drop MM/bot-dominated)",
            "dirty_wallets_flagged": len(dirty),
            "favorite_events_total": len({r["ev"] for r in fav}),
            "favorite_events_kept": len({r["ev"] for r in c2}),
            "belief_blind": bb2, "realizable_roi": rr2, "realizable_events": rn2,
            "realizable_delta_vs_champ": p2, "delta_ci90": [lo2, hi2],
            "verdict": v2, "adopt": a2, "reasons": r2}

    # ---- Challenger 3: midband_consensus ----
    mid = [r for r in strict if r["entry"] is not None and 0.35 <= r["entry"] < 0.65]
    bb3 = belief_blind(mid, blind_cells, blind_edge, rb, random.Random(SEED))
    rr3, rn3 = realizable_roi(mid)
    # combined book = favorite + elite + midband; realizable + day-return corr + Calmar-ish
    combined = champ_rows + mid
    rr_comb, rn_comb = realizable_roi(combined)
    corr, ncorr = pearson(day_returns(fav), day_returns(mid))
    bb_comb = belief_blind(combined, blind_cells, blind_edge, rb, random.Random(SEED))
    pc, loc, hic = bootstrap_delta_ci(combined, champ_rows)
    v3, a3, r3 = verdict_for(bb_comb, rr_comb, champ_realizable, champ_bb, calibrate)
    results["3_midband_consensus"] = {
        "desc": "strict consensus restricted to band 0.35-0.65; combined favorite+midband book",
        "midband_standalone": {"belief_blind": bb3, "realizable_roi": rr3, "realizable_events": rn3},
        "combined_book": {"belief_blind": bb_comb, "realizable_roi": rr_comb,
                          "realizable_events": rn_comb,
                          "realizable_delta_vs_champ": pc, "delta_ci90": [loc, hic]},
        "day_return_corr_fav_vs_midband": corr, "corr_n_days": ncorr,
        "verdict": v3, "adopt": a3, "reasons": r3,
        "note": "diversification value requires LOW corr AND midband standalone selection-real"}

    # ---- Challenger 4: clv_exit overlay ----
    results["4_clv_exit"] = {
        "desc": "OVERLAY: exit favorite positions at a CLV target vs hold-to-resolution (selection UNCHANGED)",
        "overlay": clv_exit_overlay(fav),
        "verdict": "OVERLAY (risk-adjusted axis; not a selection challenger — cannot ADOPT via belief-blind)",
        "adopt": False}

    # ---- Challenger 5: conviction_sizing overlay ----
    results["5_conviction_sizing"] = {
        "desc": "OVERLAY: size favorite bets by conviction (net_quality pct, cap 3%) vs flat 1% (selection UNCHANGED)",
        "overlay": conviction_sizing_overlay(fav, blind_edge),
        "verdict": "OVERLAY (compounding axis; not a selection challenger — cannot ADOPT via belief-blind)",
        "adopt": False}

    out = {
        "meta": {
            "cycle": 8, "posture": "PAPER-ONLY; adopts/arms/promotes NOTHING; no Rust; DB read-only; cost-zero",
            "seed": SEED, "n_perm": N_PERM, "power_floor_events": POWER_FLOOR,
            "calibrate_pass": calibrate,
            "champion": {"arms": list(CHAMP_ARMS),
                         "realizable_roi_family": champ_realizable, "realizable_events": champ_rn,
                         "belief_blind_favorite": {k: champ_bb.get(k) for k in
                             ("events", "observed", "null_sigma", "z", "p_emp",
                              "belief_blind_lb", "non_soccer_regimes_positive")}},
            "decision_rule": "ADOPT iff beats champion realizable OOS AND belief-blind gate "
                             "(p<=0.01, calibrate PASS, LB>3%, >=2 non-soccer regimes); "
                             "else INDETERMINATE-BY-POWER (pre-register) if promising-but-underpowered, "
                             "else CHAMPION-STANDS.",
        },
        "challengers": results,
    }
    os.makedirs(REPORT_DIR, exist_ok=True)
    with open(REPORT, "w") as f:
        json.dump(out, f, indent=2, default=str)
    _print(out)
    print(f"\nwrote {REPORT}")
    return out


def _pf(x, s="+.2%"):
    return "n/a" if x is None else (format(x, s) if isinstance(x, (int, float)) else str(x))


def _print(out):
    m = out["meta"]; ch = out["challengers"]
    c = m["champion"]
    print("=" * 92)
    print("CONSOLIDATE-AND-IMPROVE (Cycle 8) — challengers vs the favorite-tilted STANDARD")
    print("=" * 92)
    bb = c["belief_blind_favorite"]
    print(f"CHAMPION: realizable {_pf(c['realizable_roi_family'])} ({c['realizable_events']} ev) · "
          f"belief-blind favorite LB {_pf(bb['belief_blind_lb'])} p {bb['p_emp']} ({bb['events']} ev) · "
          f"calibrate {'PASS' if m['calibrate_pass'] else 'FAIL'}")
    print(f"{'challenger':<22}{'evs':>5}{'realizable':>12}{'Δ vs champ':>12}{'CI90':>22}{'p_emp':>8}  verdict")
    for name, r in ch.items():
        if name.startswith(("4_", "5_")):
            print(f"{name:<22}   —  OVERLAY (risk-adjusted / compounding axis; see JSON)")
            continue
        bbc = r.get("belief_blind", {}) or r.get("combined_book", {}).get("belief_blind", {})
        rr = r.get("realizable_roi")
        if "combined_book" in r:
            rr = r["combined_book"]["realizable_roi"]
            dlt = r["combined_book"].get("realizable_delta_vs_champ")
            ci = r["combined_book"].get("delta_ci90", [None, None])
        else:
            dlt = r.get("realizable_delta_vs_champ"); ci = r.get("delta_ci90", [None, None])
        ci_s = f"[{_pf(ci[0])},{_pf(ci[1])}]" if ci and ci[0] is not None else "n/a"
        print(f"{name:<22}{bbc.get('events','-'):>5}{_pf(rr):>12}{_pf(dlt):>12}{ci_s:>22}"
              f"{str(bbc.get('p_emp','n/a')):>8}  {r['verdict']}")


# ----------------------------------------------------------------- selftest
def selftest():
    ok = True
    def check(name, cond):
        nonlocal ok; ok = ok and cond
        print(f"  [{'ok' if cond else 'FAIL'}] {name}")

    # realizable_roi reproduces the guard formula on a tiny fixture
    fix = [
        {"ev": "e1", "imp": 0.70, "won": 1},   # band4 tax .0235 -> (1-.7235)/.7235
        {"ev": "e1", "imp": 0.70, "won": 0},
        {"ev": "e2", "imp": 0.90, "won": 1},   # band5 tax .0092 -> (1-.9092)/.9092
    ]
    r1 = (1 - 0.7235) / 0.7235
    r2 = (0 - 0.7235) / 0.7235
    r3 = (1 - 0.9092) / 0.9092
    expect = ((r1 + r2) / 2 + r3) / 2         # event-cluster e1 then mean with e2
    got, n = realizable_roi(fix)
    check("realizable_roi matches guard band-tax formula", abs(got - expect) < 1e-9 and n == 2)

    # verdict: underpowered -> INDETERMINATE-BY-POWER
    v, a, _ = verdict_for({"underpowered": True, "events": 12}, 0.09, 0.05,
                          {"observed": 0.08, "null_sigma": 0.02}, True)
    check("underpowered challenger -> INDETERMINATE-BY-POWER", v == "INDETERMINATE-BY-POWER" and not a)

    # verdict: strong beats + clears gate -> ADOPT (delegates to guard.judge_challenger)
    strong = {"underpowered": False, "observed": 0.14, "null_sigma": 0.02, "p_emp": 0.0,
              "non_soccer_regimes_positive": 3, "events": 60}
    v, a, _ = verdict_for(strong, 0.10, 0.05, {"observed": 0.08, "null_sigma": 0.02}, True)
    check("strong challenger beats+gate -> ADOPT", v == "ADOPT-CHALLENGER" and a)

    # verdict: beats realizable but p=0.07 -> INDETERMINATE-BY-POWER (pre-register)
    prom = {"underpowered": False, "observed": 0.07, "null_sigma": 0.03, "p_emp": 0.07,
            "non_soccer_regimes_positive": 2, "events": 45}
    v, a, _ = verdict_for(prom, 0.10, 0.05, {"observed": 0.08, "null_sigma": 0.02}, True)
    check("beats + promising-but-underpowered -> INDETERMINATE-BY-POWER", v == "INDETERMINATE-BY-POWER" and not a)

    # verdict: does not beat realizable + weak -> CHAMPION-STANDS
    weak = {"underpowered": False, "observed": 0.02, "null_sigma": 0.03, "p_emp": 0.4,
            "non_soccer_regimes_positive": 1, "events": 50}
    v, a, _ = verdict_for(weak, 0.03, 0.05, {"observed": 0.08, "null_sigma": 0.02}, True)
    check("weak, loses realizable -> CHAMPION-STANDS", v == "CHAMPION-STANDS" and not a)

    # pearson sanity
    r, n = pearson({"d1": 1.0, "d2": 2.0, "d3": 3.0}, {"d1": 2.0, "d2": 4.0, "d3": 6.0})
    check("pearson perfect corr = 1", abs(r - 1.0) < 1e-9 and n == 3)

    # bootstrap CI returns a triple on a fixture
    ch = [{"ev": "e1", "imp": 0.7, "won": 1}, {"ev": "e2", "imp": 0.8, "won": 1}]
    hp = [{"ev": "e1", "imp": 0.7, "won": 0}, {"ev": "e2", "imp": 0.8, "won": 0}]
    p, lo, hi = bootstrap_delta_ci(ch, hp, n_boot=200)
    check("bootstrap_delta_ci returns ordered CI", p is not None and lo <= hi)

    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
    else:
        run()


if __name__ == "__main__":
    main()
