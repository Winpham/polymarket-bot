#!/usr/bin/env python3
"""
CORRELATED-RISK VERIFICATION — is the D20 result TRUE, or a modeling artifact?

The adversarial audit of corr_risk_engine.py (entry 18 / D20), which recommended re-keying the
exposure cap from event_slug to the GAME (≤3 units/game) and reported a "good" risk-adjusted
trade-off. D20's copula made three assumptions this instrument attacks head-on, because each could
have manufactured the result:

  A1 · ONE w_game for every market in a game. But the market types are heterogeneous: the
       DIRECTIONAL markets (moneyline, spread, "to advance", halftime) all flip together on an
       upset, while TOTAL/OVER-UNDER and "Exact Score X — No" are near-INDEPENDENT of who wins (a
       different final score still makes them win). A uniform w_game cannot see this — and worse,
       D20's count cap ranks by band-edge, which KEEPS the directional (correlated) markets and
       drops the independent ones. So a heterogeneous model may REVERSE the cap ranking.
  A2 · GAUSSIAN copula ⇒ ZERO tail dependence. Real joint upsets (a bad tournament day taking down
       several favorites at once) have tail dependence; a t-copula prices it. Gaussian may
       understate the very tail the caps are supposed to insure.
  A3 · Point estimates at 2500 paths. p95/p99 maxDD and the ratio are tail statistics with Monte
       Carlo noise; without a multi-seed CI the "0.50 vs 0.44" ordering could be noise.

This instrument re-runs the frontier under (A1) heterogeneous per-market-type correlation, (A2) a
t-copula with tail dependence, (A3) ≥8 seeds with a reported band, and adds the DOWNSIDE metrics
D20 under-reported: CVaR(5%) of terminal P&L, p99 maxDD, ruin, and the worst REALIZED single-game
block loss along a path. It answers, with kill criteria:

  Q1  Does the cap-vs-P1 ordering survive t-copula + heterogeneous corr + w_day + seed noise?
      KILL: if the sign of (cap better/worse than P1 on downside) flips → recommendation is
      model-dependent, downgrade to directional-only.
  Q2  Is the honest override (a per-game cap over P1) JUSTIFIED on downside metrics (CVaR, p99,
      ruin, worst-block), under the ADVERSE tail model? KILL: if no cap dominates P1 on downside,
      the override is unjustified → the honest recommendation is P1 (no cap), i.e. the fix was
      unnecessary.
  Q4  Null/false-positive: at λ=0 (efficient market) and under a label-permuted null, the "good"
      trade-off MUST collapse. If it does not, the machinery is manufacturing it.
  Q5  Refinement: does a MARKET-TYPE-AWARE cap (bound DIRECTIONAL units/game, keep the independent
      +EV totals/exact-score) PARETO-dominate the blunt count cap (more growth AND less tail)?
      Classify by market-type STRING only (no outcome fitting — the market_resid/entry-10 guard).

Read-only, paper-only, nothing applied live, zero migrations. Reuses corr_risk_engine
(fetch/build_games/kelly/masks/stake) so every number is comparable to D20's.

Modes:
  ./corr_risk_verify.py            # live DB; the full audit table + verdict; writes JSON
  ./corr_risk_verify.py --selftest # t-copula tail-dependence recovery; heterogeneous-corr
                                   # ordering; CVaR/p99 monotonicity; null collapse. Exit !=0 on fail.
"""

import json
import math
import os
import re
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corr_risk_engine as ce
import portfolio_concentration as pc

try:
    import scipy.stats as _st
    HAVE_SCIPY = True
except Exception:
    HAVE_SCIPY = False

SEED = 20260702
N_PATHS = 2500
N_SEEDS = 8
B = 10_000.0
STAKE, FEE, HAIRCUT, KMULT = ce.STAKE, ce.FEE, ce.HAIRCUT, ce.KELLY_MULT
STOP = ce.STOP_LOSS_UNITS * STAKE

# Heterogeneous within-game correlation loadings (A1). Directional markets share the game's
# outcome; total/exact-score are near-independent of who wins. NOT fit — assigned by market type,
# and SWEPT (the binding uncertainty stays the correlation level, per K2).
W_DIR = 0.55          # directional (moneyline/spread/advance/halftime) within-game loading
W_INDEP = 0.08        # total/OU and exact-score-No within-game loading (≈ day level)
W_DAY = 0.05
T_NU = 4              # t-copula degrees of freedom (heavy tail dependence); ∞ ⇒ Gaussian

_INDEP_RE = re.compile(r"exact-score|total|over|under|corners|goals")


def is_directional(slug):
    """Directional = flips with the game outcome (moneyline/spread/advance/halftime). Independent
    = total/OU/exact-score-No (a different final score/scoreline still resolves them favourably)."""
    return not bool(_INDEP_RE.search(slug or ""))


def classify(positions):
    for p in positions:
        p["directional"] = is_directional(p["slug"])
    return positions


# ---------------------------------------------------------------------------------------
# Generalised simulator: heterogeneous within-game loadings + Gaussian OR t copula + the
# downside metrics D20 under-reported (CVaR, p99 maxDD, worst realized single-game block).
# ---------------------------------------------------------------------------------------
def _ppf(p, nu, copula):
    p = np.clip(np.asarray(p, float), 1e-9, 1 - 1e-9)
    if copula == "t" and HAVE_SCIPY:
        return _st.t.ppf(p, nu)
    return ce.norm_ppf(p)


def simulate_v(positions, include, f, stake_kind, H, lam, delta, games,
               w_dir=W_DIR, w_indep=W_INDEP, w_day=W_DAY, copula="gauss", nu=T_NU,
               n_paths=N_PATHS, seed=SEED, gps=6):
    """Returns dict of arrays: term, maxdd, minb, worst_block (worst single-GAME realized block
    P&L along the path, in $). Heterogeneous loadings per position by market type. t-copula uses a
    per-slate chi2 mixing variable W (a 'bad-day' catastrophe multiplier) ⇒ tail dependence."""
    rng = np.random.default_rng(seed)
    idx_arr = [np.asarray(g) for g in games]
    n_games = len(games)
    c = np.array([p["c"] for p in positions])
    won_real = np.array([p["won"] for p in positions], dtype=float)
    entry = np.array([p["entry"] for p in positions])
    p_true = np.clip(entry + lam * delta, 0.02, 0.995)
    thr = _ppf(p_true, nu, copula)
    # per-position within-game loading
    w_i = np.array([w_dir if p["directional"] else w_indep for p in positions])
    a_i = np.sqrt(w_day)
    b_i = np.sqrt(np.maximum(w_i - w_day, 0.0))
    c_i = np.sqrt(np.maximum(1.0 - np.maximum(w_i, w_day), 0.0))
    is_kelly = stake_kind == "kelly"
    is_t = copula == "t"

    term = np.empty(n_paths); maxdd = np.empty(n_paths)
    minb = np.empty(n_paths); worst_blk = np.empty(n_paths)

    for pth in range(n_paths):
        bank = peak = mnb = B
        mdd = 0.0; wblk = 0.0
        presented = 0
        while presented < H:
            sg = rng.integers(0, n_games, size=gps)
            u_day = rng.standard_normal()
            slate_pnl = 0.0
            stopped = False
            for g in sg:
                idx = idx_arr[g]
                v_game = rng.standard_normal()
                # t-copula: a per-GAME chi2 mixing variable shared by all of a game's positions.
                # X_i = z_i·sqrt(ν/W_game) is marginally t_ν (thr = t.ppf(p) preserves the win
                # prob), and a heavy-tail draw (small W) crashes the whole game block together —
                # the joint-upset tail dependence Gaussian (W≡ν) cannot produce.
                tmix = math.sqrt(nu / rng.chisquare(nu)) if is_t else 1.0
                z = (a_i * u_day + b_i[idx] * v_game + c_i[idx] * rng.standard_normal(len(idx)))
                win = ((z * tmix) <= thr[idx]).astype(float)
                block_pnl = 0.0
                for k in range(len(idx)):
                    if presented >= H:
                        break
                    presented += 1
                    i = idx[k]
                    if stopped or not include[i]:
                        continue
                    ci = c[i]
                    if is_kelly:
                        d = f[i] * bank * (win[k] / ci - 1.0 - FEE)
                    else:
                        d = STAKE * (win[k] - ci) - FEE * STAKE * ci
                    bank += d; slate_pnl += d; block_pnl += d
                    if bank > peak:
                        peak = bank
                    else:
                        dd = (peak - bank) / peak if peak > 0 else 1.0
                        if dd > mdd:
                            mdd = dd
                    if bank < mnb:
                        mnb = bank
                    if slate_pnl <= -STOP:
                        stopped = True
                if block_pnl < wblk:
                    wblk = block_pnl
                if presented >= H:
                    break
        term[pth] = bank; maxdd[pth] = mdd; minb[pth] = mnb; worst_blk[pth] = wblk
    return {"term": term, "maxdd": maxdd, "minb": minb, "worst_block": worst_blk}


def metrics_v(arr, H):
    term, dd, mnb, wblk = arr["term"], arr["maxdd"], arr["minb"], arr["worst_block"]
    pnl = term - B
    with np.errstate(divide="ignore"):
        logr = np.log(np.maximum(term, 1e-9) / B)
    g100 = float(np.median(logr) * (100.0 / H))
    p95 = float(np.percentile(dd, 95))
    q05 = np.percentile(pnl, 5)
    cvar5 = float(pnl[pnl <= q05].mean()) if np.any(pnl <= q05) else float(q05)
    return {
        "median_pnl": float(np.median(pnl)), "p_profit": float(np.mean(pnl > 0)),
        "g100": g100, "p95_maxdd": p95, "p99_maxdd": float(np.percentile(dd, 99)),
        "p_dd_over25": float(np.mean(dd > 0.25)), "p_ruin": float(np.mean(mnb <= 0.20 * B)),
        "cvar5_pnl": cvar5, "worst_block_p99": float(np.percentile(wblk, 1)),  # 1st pct = worst
        "ratio": (g100 / p95 if p95 > 1e-9 else float("inf")),
    }


def multiseed(positions, include, f, kind, H, lam, delta, games, n_seeds=N_SEEDS, **kw):
    """Aggregate metrics over n_seeds; report mean and [min,max] band for the key tail stats."""
    ms = [metrics_v(simulate_v(positions, include, f, kind, H, lam, delta, games,
                               seed=SEED + 100 * s, **kw), H) for s in range(n_seeds)]
    out = {}
    for key in ms[0]:
        vals = [m[key] for m in ms]
        out[key] = float(np.mean(vals))
        out[key + "_band"] = [float(np.min(vals)), float(np.max(vals))]
    return out


# ---------------------------------------------------------------------------------------
# Market-type-aware cap (Q5 refinement): keep ALL independent (+EV, low-corr) markets, cap only
# the DIRECTIONAL units per game. Classify by string; keep highest a-priori-edge directional first.
# ---------------------------------------------------------------------------------------
def mask_market_aware(positions, games, order, k_dir, kelly_full):
    N = len(positions)
    include = np.zeros(N, dtype=bool)
    for g, idxs in order.items():
        ev_count = defaultdict(int)
        dir_kept = 0
        for i in idxs:  # a-priori edge order
            p = positions[i]
            if ev_count[p["event"]] >= ce.EVENT_CAP:
                continue
            if p["directional"]:
                if dir_kept >= k_dir:
                    continue
                dir_kept += 1
            include[i] = True
            ev_count[p["event"]] += 1
    return include


def worst_game_loss_pct(positions, games, include, f, kind):
    loss = defaultdict(float)
    for gi, idxs in enumerate(games):
        for i in idxs:
            if not include[i]:
                continue
            loss[gi] += (f[i] * B * (1 + FEE)) if kind == "kelly" else STAKE * positions[i]["c"] * (1 + FEE)
    return 100.0 * (max(loss.values()) if loss else 0.0) / B


# ---------------------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------------------
def build_policy(positions, order, games, kelly_full, spec):
    """spec: ('P0'|'P1'|'P2'|'P4', k) or ('P5dir', k_dir). Returns (include, f, kind, label)."""
    kind_map = spec[0]
    if kind_map == "P5dir":
        inc = mask_market_aware(positions, games, order, spec[1], kelly_full)
        f = np.zeros(len(positions))
        for i in range(len(positions)):
            if inc[i]:
                f[i] = KMULT * kelly_full.get(positions[i]["band"], 0.0)
        return inc, f, "kelly", f"P5_dir_cap_{spec[1]}"
    inc = ce.policy_mask(positions, order, kind_map, (spec[1] or 10**9))
    f, kind = ce.stake_fractions(positions, inc, order, kind_map, kelly_full)
    label = {"P0": "P0_flat", "P1": "P1_constitution",
             "P2": f"P2_game_cap_{'inf' if (spec[1] or 10**9) >= 10**9 else spec[1]}",
             "P4": "P4_per_game_kelly"}[kind_map]
    return inc, f, kind, label


def run(quiet=False):
    positions = classify(ce.fetch_positions("favorite"))
    wr = float(np.mean([p["won"] for p in positions]))
    delta = ce.calibrate_delta(positions, wr)
    kelly_full = ce.re_.kelly_by_band(
        [{"c": p["c"], "won": p["won"], "band": p["band"]} for p in positions])
    games, order, _ = ce.build_games(positions)
    game_idx = list(games.values())
    H = len(positions)
    n_dir = sum(1 for p in positions if p["directional"])

    specs = [("P0", None), ("P1", None), ("P2", 1), ("P2", 2), ("P2", 3), ("P2", 5),
             ("P4", None), ("P5dir", 1), ("P5dir", 2), ("P5dir", 3)]

    meta = {"seed": SEED, "n_positions": len(positions), "n_games": len(games),
            "n_directional": n_dir, "n_independent": len(positions) - n_dir,
            "realized_wr": round(wr, 4), "delta": round(delta, 4), "bankroll": B,
            "w_dir": W_DIR, "w_indep": W_INDEP, "w_day": W_DAY, "t_nu": T_NU,
            "n_paths": N_PATHS, "n_seeds": N_SEEDS, "have_scipy": HAVE_SCIPY,
            "kelly_by_band": {str(k): round(v, 4) for k, v in kelly_full.items()}}

    result = {"meta": meta, "audit": {}, "null_check": {}, "verdict": {}}

    # ---- Q1/Q2/Q5: the audit table. Each policy under 3 tail models at λ=0.5, multi-seed. ----
    models = {
        "gauss_homog": dict(copula="gauss", w_dir=0.55, w_indep=0.55),   # D20's model (homog Gaussian)
        "gauss_hetero": dict(copula="gauss", w_dir=0.55, w_indep=0.08),  # A1 heterogeneous
        "t_hetero": dict(copula="t", w_dir=0.55, w_indep=0.08, nu=T_NU),  # A1+A2 adverse
    }
    for spec in specs:
        inc, f, kind, label = build_policy(positions, order, game_idx, kelly_full, spec)
        wgl = round(worst_game_loss_pct(positions, game_idx, inc, f, kind), 1)
        row = {"n_bet": int(inc.sum()), "worst_game_loss_pct": wgl, "models": {}}
        for mname, mk in models.items():
            row["models"][mname] = multiseed(positions, inc, f, kind, H, 0.5, delta, game_idx, **mk)
        # K5 at λ=1 under the adverse model
        row["g100_lambda1_adverse"] = multiseed(
            positions, inc, f, kind, H, 1.0, delta, game_idx,
            copula="t", w_dir=0.55, w_indep=0.08, nu=T_NU, n_seeds=4)["g100"]
        result["audit"][label] = row

    base_g1 = max(result["audit"]["P0_flat"]["g100_lambda1_adverse"],
                  result["audit"]["P1_constitution"]["g100_lambda1_adverse"])
    for label, row in result["audit"].items():
        row["k5_frac"] = (row["g100_lambda1_adverse"] / base_g1) if base_g1 > 0 else float("nan")

    # ---- Q4: null / false-positive. The copula's ENTIRE edge is δ = calibrate_delta(WR). Two
    #         honest facts: (1) λ=0 (δ removed ⇒ efficient market) MUST make every policy lose to
    #         costs — the real null. (2) δ is SHUFFLE-INVARIANT: any permutation of `won` preserves
    #         the realized WR (and mean price), so it leaves δ unchanged and the copula unchanged.
    #         Therefore this engine CANNOT self-validate the edge — δ's reality is the SELECTION
    #         NULL's job (selection_null.py / D16: favorite p=0.0000, beats blind-favorite +6-11pt),
    #         not this sizing engine's. We demonstrate the invariance rather than pretend to test it.
    p1_inc, p1_f, p1_kind, _ = build_policy(positions, order, game_idx, kelly_full, ("P1", None))
    lam0 = multiseed(positions, p1_inc, p1_f, p1_kind, H, 0.0, delta, game_idx,
                     copula="t", w_dir=0.55, w_indep=0.08, nu=T_NU, n_seeds=4)
    rng = np.random.default_rng(SEED)
    shuffled_won = [p["won"] for p in positions]
    rng.shuffle(shuffled_won)
    delta_shuf = ce.calibrate_delta(
        [{"entry": p["entry"], "won": w} for p, w in zip(positions, shuffled_won)],
        float(np.mean(shuffled_won)))
    result["null_check"] = {
        "lambda0_efficient_market": {"median_pnl": lam0["median_pnl"], "p_profit": lam0["p_profit"],
                                     "g100": lam0["g100"]},
        "delta_shuffle_invariance": {"delta_real": round(delta, 5), "delta_shuffled": round(delta_shuf, 5),
                                     "note": "δ is shuffle-invariant ⇒ the copula edge is δ, whose "
                                             "reality is the selection-null's job (D16), not this engine's"},
    }

    _verdict(result)
    if not quiet:
        _print(result)
    return result


def _verdict(result):
    a = result["audit"]
    p1 = a["P1_constitution"]
    # Q2: does any per-game cap dominate P1 on DOWNSIDE under the adverse (t_hetero) model?
    adv = "t_hetero"
    caps = [k for k in a if k.startswith("P2_game_cap") and k != "P2_game_cap_inf"]
    dir_caps = [k for k in a if k.startswith("P5_dir_cap")]
    def dominates_on_downside(cand):
        c, p = a[cand]["models"][adv], p1["models"][adv]
        return (c["cvar5_pnl"] >= p["cvar5_pnl"] and c["p99_maxdd"] <= p["p99_maxdd"]
                and c["worst_block_p99"] >= p["worst_block_p99"])
    q2_caps = {k: {"dominates_downside": dominates_on_downside(k), "k5_frac": a[k]["k5_frac"],
                   "cvar5": a[k]["models"][adv]["cvar5_pnl"], "p99dd": a[k]["models"][adv]["p99_maxdd"]}
               for k in caps + dir_caps}
    # Q1: sign of (cap p95 vs P1 p95) across the 3 models — does it flip?
    q1 = {}
    for k in caps + dir_caps:
        signs = [np.sign(a[k]["models"][m]["p95_maxdd"] - p1["models"][m]["p95_maxdd"])
                 for m in ("gauss_homog", "gauss_hetero", "t_hetero")]
        q1[k] = {"p95_minus_p1_by_model": [round(a[k]["models"][m]["p95_maxdd"]
                                                 - p1["models"][m]["p95_maxdd"], 4)
                                          for m in ("gauss_homog", "gauss_hetero", "t_hetero")],
                 "ordering_stable": len(set(s for s in signs if s != 0)) <= 1}
    # Q5: best market-type-aware cap that PARETO-dominates cap_3 (>=growth AND <=tail on t_hetero)
    ref = a.get("P2_game_cap_3")
    pareto = {}
    for k in dir_caps:
        c, r = a[k]["models"][adv], ref["models"][adv]
        pareto[k] = {"g_ge": a[k]["k5_frac"] >= ref["k5_frac"] - 0.005,
                     "tail_le": c["cvar5_pnl"] >= r["cvar5_pnl"] and c["p99_maxdd"] <= r["p99_maxdd"] + 1e-6,
                     "k5_frac": a[k]["k5_frac"], "cvar5": c["cvar5_pnl"], "p99dd": c["p99_maxdd"],
                     "worst_game_loss_pct": a[k]["worst_game_loss_pct"]}
    result["verdict"] = {"Q1_ordering_stable": q1, "Q2_cap_dominates_P1_downside": q2_caps,
                         "Q5_market_aware_vs_cap3": pareto,
                         "Q4_null_collapses": {
                             "lambda0_loses": result["null_check"]["lambda0_efficient_market"]["median_pnl"] < 0,
                             "delta_shuffle_invariant":
                                 abs(result["null_check"]["delta_shuffle_invariance"]["delta_real"]
                                     - result["null_check"]["delta_shuffle_invariance"]["delta_shuffled"]) < 1e-9}}


def _print(r):
    m = r["meta"]
    print(f"CORRELATED-RISK VERIFICATION · favorite · {m['n_positions']} positions "
          f"({m['n_directional']} directional / {m['n_independent']} independent) on {m['n_games']} games")
    print(f"WR {m['realized_wr']:.1%} · δ {m['delta']:+.3f} · t-copula ν={m['t_nu']} (scipy={m['have_scipy']}) "
          f"· {m['n_seeds']} seeds × {m['n_paths']} paths · adverse model = t + heterogeneous corr\n")
    print("AUDIT — each policy at λ=0.5, DOWNSIDE metrics, under 3 tail models (multi-seed mean):")
    print("  gH=Gaussian-homogeneous(D20)  gX=Gaussian-heterogeneous  tX=t-copula+heterogeneous(ADVERSE)")
    hdr = (f"{'policy':<20}{'bet':>4}{'wGmL%':>6}{'K5':>5}"
           f"{'p95 gH/gX/tX':>22}{'CVaR5(tX)':>11}{'p99DD(tX)':>10}{'ratio(tX)':>10}")
    print(hdr); print("-" * len(hdr))
    for label, row in r["audit"].items():
        p95s = "/".join(f"{row['models'][m]['p95_maxdd']:.0%}"
                        for m in ("gauss_homog", "gauss_hetero", "t_hetero"))
        tx = row["models"]["t_hetero"]
        print(f"{label:<20}{row['n_bet']:>4}{row['worst_game_loss_pct']:>5.0f}%{100*row['k5_frac']:>4.0f}%"
              f"{p95s:>22}{tx['cvar5_pnl']:>+11.0f}{tx['p99_maxdd']:>10.0%}{tx['ratio']:>10.2f}")

    v = r["verdict"]
    print("\nQ1 — is the cap-vs-P1 p95 ordering STABLE across the 3 models? (Δp95 = cap − P1)")
    for k, d in v["Q1_ordering_stable"].items():
        print(f"  {k:<18} Δp95 [gH,gX,tX]={d['p95_minus_p1_by_model']}  "
              f"{'STABLE' if d['ordering_stable'] else 'FLIPS ⇒ model-dependent'}")
    print("\nQ2 — does a per-game cap DOMINATE P1 on downside (CVaR↑ ∧ p99DD↓ ∧ worst-block↑), adverse model?")
    for k, d in v["Q2_cap_dominates_P1_downside"].items():
        print(f"  {k:<18} dominates={d['dominates_downside']}  K5={100*d['k5_frac']:.0f}%  "
              f"CVaR5={d['cvar5']:+.0f}  p99DD={d['p99dd']:.0%}")
    print("\nQ5 — market-type-aware DIRECTIONAL cap vs blunt count cap_3 (Pareto: growth≥ ∧ tail≤)?")
    for k, d in v["Q5_market_aware_vs_cap3"].items():
        pareto = d["g_ge"] and d["tail_le"]
        print(f"  {k:<18} K5={100*d['k5_frac']:.0f}%  CVaR5={d['cvar5']:+.0f}  p99DD={d['p99dd']:.0%}  "
              f"wGmL={d['worst_game_loss_pct']:.0f}%  {'PARETO-DOMINATES cap_3' if pareto else 'no'}")
    print("\nQ4 — null / false-positive:")
    nc = r["null_check"]
    print(f"  λ=0 (efficient market, δ removed): median P&L {nc['lambda0_efficient_market']['median_pnl']:+.0f} "
          f"{'✓ loses to costs' if v['Q4_null_collapses']['lambda0_loses'] else '✗ STILL WINS — suspect'}")
    di = nc["delta_shuffle_invariance"]
    print(f"  δ real {di['delta_real']:+.4f} vs δ shuffled {di['delta_shuffled']:+.4f} "
          f"{'✓ shuffle-invariant' if v['Q4_null_collapses']['delta_shuffle_invariant'] else '✗'} "
          f"⇒ the copula edge IS δ; its reality is the selection-null's job (D16 p=0.0000), NOT this engine's.")


# =======================================================================================
# SELF-TESTS
# =======================================================================================
def selftest():
    ok = True
    positions = classify(ce.fetch_positions("favorite"))
    games, order, _ = ce.build_games(positions)
    gi = list(games.values())
    kf = ce.re_.kelly_by_band([{"c": p["c"], "won": p["won"], "band": p["band"]} for p in positions])
    delta = ce.calibrate_delta(positions, np.mean([p["won"] for p in positions]))
    inc, f, kind, _ = build_policy(positions, order, gi, kf, ("P1", None))

    print("— (1) t-copula fattens the single-GAME worst-block tail (the game-level tail-dependence")
    print("      signature); portfolio maxDD is diluted across ~78 games. avg 3 seeds, ν=3 —")
    def wb(cop):
        return np.mean([metrics_v(simulate_v(positions, inc, f, kind, len(positions), 0.5, delta, gi,
                        copula=cop, nu=3, w_dir=0.55, w_indep=0.55, n_paths=3000, seed=SEED + s),
                        len(positions))["worst_block_p99"] for s in range(3)])
    gwb, twb = wb("gauss"), wb("t")
    c1 = twb < gwb   # heavier (more negative) worst single-game block under tail dependence
    ok = ok and c1
    print(f"  [{'ok' if c1 else 'FAIL'}] worst single-game block: t {twb:+.0f} < gauss {gwb:+.0f} "
          f"(heavier joint-upset tail)")

    print("— (2) heterogeneous corr ⇒ lower tail than homogeneous (independent markets decorrelate) —")
    hom = metrics_v(simulate_v(positions, inc, f, kind, len(positions), 0.5, delta, gi,
                               copula="gauss", w_dir=0.55, w_indep=0.55, n_paths=3000), len(positions))
    het = metrics_v(simulate_v(positions, inc, f, kind, len(positions), 0.5, delta, gi,
                               copula="gauss", w_dir=0.55, w_indep=0.08, n_paths=3000), len(positions))
    c2 = het["p95_maxdd"] <= hom["p95_maxdd"] + 1e-6
    ok = ok and c2
    print(f"  [{'ok' if c2 else 'FAIL'}] hetero p95 {het['p95_maxdd']:.1%} ≤ homog {hom['p95_maxdd']:.1%}")

    print("— (3) λ=0 (efficient market) loses to costs —")
    z = metrics_v(simulate_v(positions, inc, f, kind, len(positions), 0.0, delta, gi,
                             copula="t", nu=4, n_paths=3000), len(positions))
    c3 = z["median_pnl"] < 0
    ok = ok and c3
    print(f"  [{'ok' if c3 else 'FAIL'}] λ=0 median P&L {z['median_pnl']:+.0f} (<0)")

    print("— (4) market-aware cap bounds directional/game AND keeps ≥ as many independent as blunt cap_1 —")
    ma = mask_market_aware(positions, gi, order, 1, kf)
    blunt = ce.policy_mask(positions, order, "P2", 1)  # ≤1/game regardless of type
    ma_indep = sum(1 for i, p in enumerate(positions) if ma[i] and not p["directional"])
    blunt_indep = sum(1 for i, p in enumerate(positions) if blunt[i] and not positions[i]["directional"])
    maxdir = max((sum(1 for i in idxs if ma[i] and positions[i]["directional"]) for idxs in gi), default=0)
    # market-aware keeps the diversifying (independent) markets the blunt count cap throws away.
    c4 = maxdir <= 1 and ma_indep >= blunt_indep
    ok = ok and c4
    print(f"  [{'ok' if c4 else 'FAIL'}] max {maxdir} directional/game; market-aware keeps "
          f"{ma_indep} independent vs blunt cap_1's {blunt_indep} (refinement keeps the diversifiers)")

    print("— (5) CVaR ≤ p5 ≤ median (ordering sanity) —")
    a = simulate_v(positions, inc, f, kind, len(positions), 0.5, delta, gi, n_paths=3000)
    mm = metrics_v(a, len(positions))
    pnl = a["term"] - B
    c5 = mm["cvar5_pnl"] <= np.percentile(pnl, 5) <= np.median(pnl)
    ok = ok and c5
    print(f"  [{'ok' if c5 else 'FAIL'}] CVaR5 {mm['cvar5_pnl']:+.0f} ≤ p5 {np.percentile(pnl,5):+.0f} "
          f"≤ median {np.median(pnl):+.0f}")

    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    result = run()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports", "corr_risk_verify.json")
    with open(out, "w") as f:
        json.dump(result, f, indent=1, default=str)
    print("\nartifact → reports/corr_risk_verify.json")


if __name__ == "__main__":
    main()
