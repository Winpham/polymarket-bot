#!/usr/bin/env python3
"""
RELIABILITY TRADEOFF — what does WAITING for persistence cost, and what does it save?

The reliability-first stance (D17) says: don't bet favorite's real, well-estimated in-sample
edge (+12.5%, p=0.0000) until it is proven to PERSIST across the post-WC regime shift. That is a
tradeoff, and until now it was a vibe. This instrument puts a NUMBER on it via a transparent
decision model, so "wait" vs "bet now" is a computed choice, not a posture.

The model (all inputs explicit; nothing hidden):
  * Two states of the world, mixed by the PERSISTENCE PROBABILITY π (your belief the edge is a
    durable selection skill, not a soft-summer artifact):
      - persists (prob π):   forward edge multiplier λ = 1 (the measured surplus holds).
      - fades   (prob 1−π):  λ = λ_fade ∈ {0, 0.25} — the SELECTION skill (surplus over the
        blind-favorite baseline) decays; you are left betting blind favorites (skill gone),
        which after costs is ≈ break-even/negative. λ scales the surplus, NOT the whole return:
        won_eff = entry + blind_edge[band] + λ·(advantage − blind_edge[band]).
  * Forward horizon = H_DAYS independent day-clusters (the binding unit per D17-a — the record
    accrues ~1 new cluster per calendar day). Each simulated day bootstrap-resamples one observed
    favorite day (preserving within-day count + correlation + between-day heterogeneity), scaled by λ.
  * Three POSTURES:
      BET_NOW   — size ⅛-Kelly-capped from day 0 on all H_DAYS.
      WAIT      — bet 0 for W_WAIT days; run the D17 certification test on the accrued clusters
                  (cluster-robust LB > margin AND ≥ K_MIN independent clusters); bet the rest
                  ONLY if it certifies. Waiting forgoes EV when the edge is real, but AVOIDS the
                  loss (and the over-sizing — you'd have sized on the measured edge) when it fades.
      PILOT     — bet the wait window at a FRACTION (learns fills / limits exposure), full after cert.
  * Sizing uses the MEASURED per-band Kelly (frozen) — so when the edge fades you OVER-size, which
    is exactly the risk WAIT hedges.

Outputs, swept over π: expected median log-growth, P(loss), P(maxDD>30%) per posture; the COST OF
WAITING (growth forgone when the edge is real) vs the LOSS AVOIDED (when it fades); and the
BREAK-EVEN π above which BET_NOW's expected growth beats WAIT's. Conditional on the model — it
sizes and schedules an edge, it does not create one.

Reuses selection_null (fetch/band/blind edge) + risk_engine (per-band Kelly) + effective_n
(cluster-robust cert) byte-identically. Paper-only, read-only, changes nothing live.

Modes:
  ./reliability_tradeoff.py            # live DB; the posture table + break-even π; writes JSON
  ./reliability_tradeoff.py --selftest # π=1 ⇒ BET_NOW dominates; π=0 ⇒ WAIT dominates; cert has power
"""

import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import selection_null as sn
import risk_engine as rk_risk
import effective_n as en

SEED = 20260702
ANCHOR = "favorite"
HAIRCUT = rk_risk.HAIRCUT
FEE = rk_risk.FEE
STAKE = rk_risk.STAKE
MARGIN = 0.03

# Frozen model parameters (pre-registered before looking at outputs).
H_DAYS = 30                 # forward horizon in independent day-clusters
W_WAIT = 12                 # accrual/wait window (days) before the certification test
K_MIN = 10                  # min independent clusters to be eligible to certify (D17-a floor)
PILOT_FRAC = 0.25           # PILOT sizes the wait window at ¼ of the ⅛-Kelly stake
KELLY_MULT = 0.125          # ⅛-Kelly (the D15/D17 default)
DD_CEIL = 0.30
N_PATHS = 4000
PI_GRID = [0.2, 0.35, 0.5, 0.65, 0.8, 0.95]
LAMBDA_FADE = 0.25          # "fade" = skill decays to ¼ (sensitivity: also report 0.0)
Z_CERT = 1.96               # cluster-robust normal z for the cert LB (≥K_MIN clusters ⇒ ~normal ok)
# The forward model forecasts the FALL, where markets are SHARP (entry-15 sport_edge_tracker:
# tennis softness +1.8%, MLB −3.7% — the summer soft-favorite edge does NOT persist). So the
# forward advantage = FALL_BLIND + λ·(measured skill/surplus); FALL_BLIND≈0 (efficient market,
# favorites fairly priced ⇒ betting them with NO skill LOSES to costs). This removes the
# no-losing-slate artifact of bootstrapping only-positive summer days. Sensitivity: also −0.02.
FALL_BLIND = 0.0


def load_favorite():
    """Favorite events grouped by observed UTC day, each carrying entry, won, band, blind_edge,
    and the per-band frozen ⅛-Kelly fraction. Returns (days: list[list[event]], f_full)."""
    rows = sn.fetch()
    blind_band = defaultdict(list)
    for r in rows:
        if r["strategy"] == "_blind":
            blind_band[sn.band(r["entry"])].append(r["won"] - r["entry"])
    blind_edge = {b: sum(v) / len(v) for b, v in blind_band.items()}

    fav = [r for r in rows if r["strategy"] == ANCHOR]
    # event-cluster (one bet per event) via risk_engine, then attach day + surplus decomposition
    events = rk_risk.build_events(fav)
    f_full = rk_risk.kelly_by_band(events)
    by_day = defaultdict(list)
    for e in events:
        entry = e["c"] - HAIRCUT
        band = e["band"]
        be = blind_edge.get(band, 0.0)
        adv = e["won"] - entry                      # measured advantage (won − at-fire entry)
        by_day[e["day"]].append({
            "entry": entry, "c": e["c"], "band": band, "blind_edge": be,
            "advantage": adv, "surplus": adv - be, "won": e["won"]})
    days = [by_day[d] for d in sorted(by_day)]
    return days, f_full, blind_edge


def apply_lambda(ev, lam, fall_blind=FALL_BLIND):
    """Forecast the FALL: forward advantage = fall_blind + λ·(measured skill/surplus). λ=1 skill
    intact, λ=0 skill gone (⇒ advantage=fall_blind, an efficient market ⇒ loses to costs). The
    within-event win/loss STRUCTURE is preserved (surplus_i carries it); only the mean shifts.
    Returns (won_eff, surplus_eff, unit_return, flat_pnl)."""
    adv_eff = fall_blind + lam * ev["surplus"]
    won_eff = ev["entry"] + adv_eff
    c = ev["c"]
    unit = won_eff / c - 1.0 - FEE
    flat = STAKE * (won_eff - c) - FEE * STAKE * c
    return won_eff, lam * ev["surplus"], unit, flat


def certify(accrued_days):
    """The D17 certification test on the accrued day-clusters: cluster-robust LB of the per-event
    surplus > margin AND ≥ K_MIN independent clusters. accrued_days: list of (day_id, [surplus_eff])."""
    n_clusters = len(accrued_days)
    if n_clusters < K_MIN:
        return False
    ev_surplus, ev_cluster = {}, {}
    i = 0
    for cid, surps in accrued_days:
        for s in surps:
            ev_surplus[f"e{i}"] = s
            ev_cluster[f"e{i}"] = cid
            i += 1
    cr = en.cluster_robust(ev_surplus, ev_cluster)
    if cr is None or not math.isfinite(cr["se_CR"]) or cr["se_CR"] <= 0:
        return False
    lb = cr["theta"] - Z_CERT * cr["se_CR"]
    return lb > MARGIN


def simulate_posture(posture, days, f_full, lam, fall_blind, day_seq):
    """One path over a PRE-DRAWN day sequence (day-grain block bootstrap: each draw replays an
    observed day's real outcomes, preserving within-day correlation). Deterministic given inputs
    ⇒ all three postures share the same world (common random numbers). Returns (log_growth,
    min_bankroll_frac, maxdd_frac, did_bet)."""
    B0 = 1000.0
    bank = peak = B0
    maxdd = 0.0
    accrued = []            # (day_id, [surplus_eff]) during the wait window (for the cert test)
    certified = None
    did_bet = False
    for d, di in enumerate(day_seq):
        day = days[di]
        if posture == "BET_NOW":
            frac = KELLY_MULT
        elif posture == "PILOT":
            frac = KELLY_MULT * PILOT_FRAC if d < W_WAIT else (KELLY_MULT if certified else 0.0)
        else:  # WAIT
            frac = 0.0 if d < W_WAIT else (KELLY_MULT if certified else 0.0)
        day_surps = []
        for ev in day:
            _, surp_eff, unit, _ = apply_lambda(ev, lam, fall_blind)
            day_surps.append(surp_eff)
            if frac > 0.0:
                bank += frac * f_full.get(ev["band"], 0.0) * bank * unit
                did_bet = True
        if d < W_WAIT and posture in ("WAIT", "PILOT"):
            accrued.append((f"d{d}", day_surps))
        if d == W_WAIT - 1 and posture in ("WAIT", "PILOT"):
            certified = certify(accrued)
        peak = max(peak, bank)
        maxdd = max(maxdd, (peak - bank) / peak if peak > 0 else 0.0)
    return math.log(max(bank, 1e-9) / B0), bank / B0, maxdd, did_bet


def run_posture_grid(days, f_full, pi, lam_fade, fall_blind, n_paths, seed):
    """Monte Carlo. Each path draws the world (persist w.p. π else fade) + ONE day sequence, then
    runs all three postures on that same world (common random numbers ⇒ clean comparison)."""
    out = {p: {"lg": [], "endb": [], "maxdd": []} for p in ("BET_NOW", "WAIT", "PILOT")}
    rng = np.random.default_rng(seed)
    n_obs = len(days)
    for _ in range(n_paths):
        lam = 1.0 if rng.random() < pi else lam_fade
        day_seq = rng.integers(0, n_obs, H_DAYS)
        for p in out:
            lg, endb, dd, _ = simulate_posture(p, days, f_full, lam, fall_blind, day_seq)
            out[p]["lg"].append(lg)
            out[p]["endb"].append(endb)
            out[p]["maxdd"].append(dd)
    res = {}
    for p, d in out.items():
        lg = np.array(d["lg"])
        res[p] = {
            "median_log_growth": float(np.median(lg)),
            "mean_log_growth": float(np.mean(lg)),
            "p_loss": float(np.mean(np.array(d["endb"]) < 1.0)),
            "p_maxdd_over_30": float(np.mean(np.array(d["maxdd"]) > DD_CEIL)),
            "p5_log_growth": float(np.percentile(lg, 5)),
        }
    return res


def break_even_pi(days, f_full, lam_fade, fall_blind, n_paths, seed):
    """Finest π where BET_NOW's mean log-growth first exceeds WAIT's (linear scan + interp)."""
    prev = None
    for pi in [i / 100 for i in range(5, 100, 5)]:
        r = run_posture_grid(days, f_full, pi, lam_fade, fall_blind, max(1500, n_paths // 3), seed)
        diff = r["BET_NOW"]["mean_log_growth"] - r["WAIT"]["mean_log_growth"]
        if prev is not None and prev[1] <= 0 < diff:
            p0, d0 = prev
            return round(p0 + (pi - p0) * (-d0) / (diff - d0), 3)
        prev = (pi, diff)
    return None if prev is None or prev[1] < 0 else 0.05


def run_live():
    days, f_full, blind_edge = load_favorite()
    n_ev = sum(len(d) for d in days)
    obs_blind = f"{np.mean([e['blind_edge'] for d in days for e in d]):+.1%}"
    print(f"RELIABILITY TRADEOFF · anchor={ANCHOR} · {len(days)} observed day-clusters, {n_ev} events · "
          f"⅛-Kelly-capped · horizon {H_DAYS}d, wait {W_WAIT}d (cert floor {K_MIN} clusters) · fade λ={LAMBDA_FADE}")
    print(f"FORWARD MODEL forecasts a SHARP fall market: forward advantage = FALL_BLIND({FALL_BLIND:+.0%}) + λ·skill; the")
    print(f"summer soft-favorite edge ({obs_blind} blind) is EXCLUDED as non-persistent (entry-15 sport_edge_tracker).")
    print("ALL NUMBERS CONDITIONAL ON THE MODEL — it schedules & sizes an edge, it does not create one.\n")
    print(f"per-band ⅛-Kelly (SE-shrunk, frozen): "
          f"{', '.join(f'{b}:{f_full[b]:.3f}' for b in sorted(f_full))}\n")
    print(f"{'π (persist)':>11} {'posture':<9} {'med log-grow':>12} {'P(loss)':>8} {'P(DD>30%)':>10} {'5th log-grow':>13}")
    print("-" * 70)
    results = {"fall_blind": FALL_BLIND}
    for pi in PI_GRID:
        r = run_posture_grid(days, f_full, pi, LAMBDA_FADE, FALL_BLIND, N_PATHS, SEED)
        results[str(pi)] = r
        for p in ("BET_NOW", "WAIT", "PILOT"):
            c = r[p]
            print(f"{pi:>11.2f} {p:<9} {c['median_log_growth']:>+12.3f} {c['p_loss']:>7.1%} "
                  f"{c['p_maxdd_over_30']:>10.1%} {c['p5_log_growth']:>+13.3f}")
        print()
    be = break_even_pi(days, f_full, LAMBDA_FADE, FALL_BLIND, N_PATHS, SEED)
    be0 = break_even_pi(days, f_full, 0.0, FALL_BLIND, N_PATHS, SEED)
    be_sharp = break_even_pi(days, f_full, 0.0, -0.02, N_PATHS, SEED)  # overpriced-fall sensitivity
    results["break_even_pi"] = {"fade_0.25_fallblind_0": be, "fade_0.0_fallblind_0": be0,
                                "fade_0.0_fallblind_-0.02": be_sharp}

    # Cost of waiting (edge real, π→1) vs loss avoided (edge fake→0, π→0), at the extremes.
    r_real = run_posture_grid(days, f_full, 0.99, LAMBDA_FADE, FALL_BLIND, N_PATHS, SEED)
    r_fake = run_posture_grid(days, f_full, 0.01, 0.0, FALL_BLIND, N_PATHS, SEED)
    cost_wait = r_real["BET_NOW"]["mean_log_growth"] - r_real["WAIT"]["mean_log_growth"]
    loss_avoided = r_fake["WAIT"]["mean_log_growth"] - r_fake["BET_NOW"]["mean_log_growth"]
    results["cost_of_waiting_if_real"] = cost_wait
    results["loss_avoided_if_fake"] = loss_avoided

    print("THE TRADEOFF, QUANTIFIED:")
    print(f"  • If the edge IS real (π≈1): waiting {W_WAIT}d forgoes {cost_wait:+.3f} log-growth vs betting now")
    print(f"    (BET_NOW {r_real['BET_NOW']['median_log_growth']:+.3f} vs WAIT {r_real['WAIT']['median_log_growth']:+.3f} median).")
    print(f"  • If the edge FADES (π≈0): waiting AVOIDS {loss_avoided:+.3f} log-growth of loss")
    print(f"    (BET_NOW {r_fake['BET_NOW']['median_log_growth']:+.3f} vs WAIT {r_fake['WAIT']['median_log_growth']:+.3f} median; "
          f"BET_NOW P(loss) {r_fake['BET_NOW']['p_loss']:.0%}).")
    def _pct(x):
        return "n/a" if x is None else f"{x:.0%}"
    print(f"  • BREAK-EVEN persistence probability (bet-now beats waiting once π exceeds): "
          f"{_pct(be)} (fade→¼) / {_pct(be0)} (fade→0) / {_pct(be_sharp)} (fade→0, overpriced fall).")
    print("    PILOT is the middle path: caps the fade loss while keeping most of the real-edge upside.")
    return results


# ---------------------------------------------------------------------------------------
# Self-test: the model must behave correctly at the belief extremes.
# ---------------------------------------------------------------------------------------
def _synth_days(n_days=6, per_day=40, surplus=0.12, blind=-0.05, seed=SEED):
    """Synthetic favorite: n_days clusters, per_day band-5 events at entry 0.75; surplus over a
    blind-favorite edge=blind. blind<0 = a SHARP market where SELECTION SKILL is the only edge, so
    a full fade (λ=0) genuinely LOSES — the case where waiting demonstrably avoids a loss."""
    rng = np.random.default_rng(seed)
    days = []
    for d in range(n_days):
        evs = []
        adv_target = blind + surplus
        # win prob so that E[won-entry] ≈ adv_target at entry 0.75 (won∈{0,1}): p - 0.75 = adv...
        p_win = min(0.98, 0.75 + adv_target)
        for _ in range(per_day):
            won = 1 if rng.random() < p_win else 0
            evs.append({"entry": 0.75, "c": 0.755, "band": 5, "blind_edge": blind,
                        "advantage": won - 0.75, "surplus": (won - 0.75) - blind, "won": won})
        days.append(evs)
    return days


def selftest():
    ok = True
    days = _synth_days()
    f_full = {5: 0.5}  # aggressive so growth is visible
    blind_edge = {5: 0.02}

    # (1) π=1 (edge certainly real): BET_NOW mean log-growth must exceed WAIT (waiting only forgoes).
    r1 = run_posture_grid(days, f_full, 0.99, 0.25, 0.0, 2500, SEED)
    c1 = r1["BET_NOW"]["mean_log_growth"] > r1["WAIT"]["mean_log_growth"]
    ok = ok and c1
    print(f"  [{'ok' if c1 else 'FAIL'}] π=1: BET_NOW {r1['BET_NOW']['mean_log_growth']:+.3f} > "
          f"WAIT {r1['WAIT']['mean_log_growth']:+.3f} (waiting forgoes real edge)")

    # (2) π=0, full fade (λ=0) into a SHARP fall market (fall_blind=−0.05): WAIT must beat BET_NOW.
    r0 = run_posture_grid(days, f_full, 0.01, 0.0, -0.05, 2500, SEED)
    c2 = r0["WAIT"]["mean_log_growth"] > r0["BET_NOW"]["mean_log_growth"]
    ok = ok and c2
    print(f"  [{'ok' if c2 else 'FAIL'}] π=0 (fade→0, sharp fall): WAIT {r0['WAIT']['mean_log_growth']:+.3f} > "
          f"BET_NOW {r0['BET_NOW']['mean_log_growth']:+.3f} (waiting avoids the loss)")

    # (3) certification has POWER: certifies a real edge far more often than a dead one.
    rng = np.random.default_rng(SEED)
    real = [(f"d{i}", [apply_lambda(e, 1.0)[1] for e in days[rng.integers(0, len(days))]])
            for i in range(K_MIN + 2)]
    dead = [(f"d{i}", [apply_lambda(e, 0.0)[1] for e in days[rng.integers(0, len(days))]])
            for i in range(K_MIN + 2)]
    c3 = certify(real) and not certify(dead)
    ok = ok and c3
    print(f"  [{'ok' if c3 else 'FAIL'}] cert power: real edge certifies={certify(real)}, "
          f"dead edge certifies={certify(dead)} (want True/False)")

    # (4) cert floor: fewer than K_MIN clusters can NEVER certify (the accrual wall).
    c4 = not certify(real[:K_MIN - 1])
    ok = ok and c4
    print(f"  [{'ok' if c4 else 'FAIL'}] cert floor: {K_MIN-1}<{K_MIN} clusters cannot certify (accrual wall)")

    # (5) break-even π is interior (0,1) — there IS a real tradeoff, not a dominant posture.
    be = break_even_pi(days, f_full, 0.25, -0.05, 1500, SEED)
    c5 = be is not None and 0.0 < be < 1.0
    ok = ok and c5
    print(f"  [{'ok' if c5 else 'FAIL'}] break-even π = {be} ∈ (0,1) (a genuine tradeoff exists)")

    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    results = run_live()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports", "reliability_tradeoff.json")
    with open(out, "w") as f:
        json.dump(results, f, indent=1, default=str)
    print("\nartifact → reports/reliability_tradeoff.json")


if __name__ == "__main__":
    main()
