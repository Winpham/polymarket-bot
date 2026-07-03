#!/usr/bin/env python3
"""
CORRELATED-RISK ENGINE — size the GAME, not the position, and keep the profit.

The correction to risk_engine.py. That engine event-clustered (COALESCE(event_slug,
condition_id)) to measure the EDGE and block-bootstrapped at the SLATE grain. This engine
answers a DIFFERENT question — the BANKROLL SWING — for which the atomic unit is the POSITION
(each staked market bet, one DB row) and the true correlation unit is the GAME
(superkey.super_event). The `favorite` book holds ~220 positions on ~78 games; up to 17
positions sit on one World-Cup game (moneyline, spread, "team to advance", halftime, O/U, six
"Exact Score X — No"). All resolve on the SAME underlying outcome, so with flat-shares on
favorites (+$16 win / −$84 loss ≈ 5× asymmetry) a single stacked-game upset is a synchronised
−$0.9k…−$1.5k block loss. Event-clustering or slate-blocking UNDER-counts that; game-blocking
prices it.

THE MOTTO: the game is the bet; a dozen markets on one game is one bet levered a dozen times;
size the bet, keep the edge, drop the redundancy that is pure levered variance.

WHAT THIS ENGINE IS NOT (binding, K3/K4):
  1. NOT a promise of profit. Every P(profit) is CONDITIONAL on the measured edge being real
     and persisting (D7's job). At λ=0 (efficient market) every policy loses to costs.
  2. NOT applied to anything. The recommended sizing is PRE-REGISTERED for the hypothetical GO
     day (D7 + pilot floors + Tue). Nothing here changes live behaviour.
  3. NOT a fit of w_game. You cannot estimate within-game correlation from a no-upset sample
     (game_correlation.py: measured ≈ 0, a benign-sample artifact). w_game is SWEPT as a
     structural assumption; the tail's sensitivity to it is the binding uncertainty (K2).

FROZEN PRE-REGISTRATION (see reports/entries/2026-07-02-18-correlated-risk.md):
  Objective — RECOMMENDED = max median log-growth per 100 positions SUBJECT TO
    P(maxDD > 25%) ≤ 10% under the GAME-BLOCK copula at λ=0.5, robust across the w_game sweep.
    Report the frontier; recommend the knee. risk-adjusted ratio = median growth ÷ p95-maxDD
    (game-block copula, λ=0.5) per policy — the single "profit per unit of risk" number.
  Correlation model — resample GAME blocks with replacement (never positions, never event_slug):
    A · block-bootstrap: each sampled game keeps its REAL joint outcome (benign floor).
    B · nested Gaussian copula: true P(win_i)=clip(entry_i+λδ, .02,.995), δ calibrated so λ=1
        reproduces realized WR; latent z_i = √w_day·U_day + √(w_game−w_day)·V_game +
        √(1−w_game)·ε_i, win iff z_i ≤ Φ⁻¹(p_i). Sweep λ∈{1,.5,.25,0}, w_game∈{lb,.4,.55,.8}
        (lb = game_correlation.py measured lower bound), w_day small.
  Policy family (frozen): P0 flat_shares; P1 kelly_eighth_capped with EVENT-keyed caps (current
    constitution — its ≤1/event cap lets one game take ≥3 units: the gap); P2 = P1 + hard
    ≤K_game units/GAME (sweep {1,2,3,5,∞}, keep highest matched-blind-surplus positions);
    P3 = P2 + drop the "Exact Score — No"/entry≥0.95 redundancy; P4 per-game Kelly (size the
    game as ONE bet, split across kept markets).
  K5 profit-preservation — recommended median growth at λ=1 must be ≥ 90% of P0/P1's; if no
    policy both cuts the tail AND keeps ≥90% of the edge's growth, THAT is the finding.

Modes:
  ./corr_risk_engine.py            # live DB; frontier + λ/w_game sweeps + recommendation; JSON
  ./corr_risk_engine.py --selftest # iid⇒game/position bootstrap agree & per-game cap inert;
                                   # fully-correlated-game⇒block recovers inflated variance,
                                   # per-game cap truncates it, POSITION bootstrap UNDERSTATES
                                   # it (the exact leak); zero-edge⇒every policy loses; upset
                                   # cluster⇒stop-loss/caps bind. Exit !=0 on failure.
"""

import csv
import io
import json
import math
import os
import subprocess
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import selection_null as sn            # band(), regime()
import risk_engine as re_              # kelly_by_band (byte-compatible per-band Kelly)
from superkey import super_event

SEED = 20260702
HAIRCUT = 0.005
FEE = 0.02
STAKE = 100.0                          # 1 unit = $100 notional (flat-shares = 100 shares)
BANKROLLS = [5_000.0, 10_000.0, 25_000.0]
B_HEADLINE = 10_000.0
N_PATHS = 2_500
N_PATHS_REC = 5_000
RUIN_FRAC = 0.20
DD_CEIL = 0.25                         # P(maxDD > 25%) ceiling
DD_CEIL_P = 0.10
KELLY_MULT = 0.125                     # ⅛-Kelly
STOP_LOSS_UNITS = 5.0                  # −5-unit per-slate stop-loss (constitution)
LAMBDAS = [1.0, 0.5, 0.25, 0.0]
WGAME_SWEEP_HI = [0.4, 0.55, 0.8]      # + the measured lower bound, prepended at runtime
W_DAY = 0.05                           # small cross-game within-day latent (secondary)
K_GAME_SWEEP = [1, 2, 3, 5, 10**9]     # 10**9 = ∞ (no game cap)
EVENT_CAP = 1                          # the constitution's ≤1 unit/event (event_slug)

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]
SQL = """SELECT event_slug, slug, condition_id,
       COALESCE(initial_mean_price, mean_price) AS entry,
       (outcome_won::int) AS won,
       to_char(first_detected_at AT TIME ZONE 'UTC', 'YYYY-MM-DD') AS day
FROM consensus_signals WHERE resolved AND strategy=%(s)s"""


# ---------------------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------------------
def fetch_positions(strategy="favorite"):
    q = SQL.replace("%(s)s", f"'{strategy}'")
    out = subprocess.run(PG + ["-f", "-"], input=q, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    rows = []
    for r in csv.DictReader(io.StringIO(out.stdout)):
        entry = float(r["entry"])
        slug = r["slug"] or ""
        rows.append({
            "game": super_event(r["event_slug"], r["slug"]) or r["condition_id"],
            "event": r["event_slug"] or r["condition_id"],
            "regime": sn.regime(r["event_slug"] or slug),
            "day": r["day"],
            "entry": entry,
            "c": min(0.999, entry + HAIRCUT),
            "won": int(r["won"]),
            "band": sn.band(entry),
            "is_exact_score": "exact-score" in slug,
            "near_certain": entry >= 0.95,
            "slug": slug,
        })
    return rows


def norm_ppf(p):
    """Vectorised inverse standard normal CDF (Acklam), numpy-friendly."""
    p = np.clip(np.asarray(p, dtype=float), 1e-12, 1 - 1e-12)
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    out = np.empty_like(p)
    lo = p < plow
    hi = p > phigh
    mid = ~(lo | hi)
    q = np.sqrt(-2 * np.log(p[lo]))
    out[lo] = (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = np.sqrt(-2 * np.log(1 - p[hi]))
    out[hi] = -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p[mid] - 0.5
    r = q * q
    out[mid] = (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    return out


def calibrate_delta(positions, target_wr):
    """δ such that mean_i clip(entry_i + δ, .02, .995) == realized win rate (λ=1)."""
    e = np.array([p["entry"] for p in positions])
    lo, hi = -0.5, 0.5
    for _ in range(60):
        mid = (lo + hi) / 2
        wr = float(np.mean(np.clip(e + mid, 0.02, 0.995)))
        if wr < target_wr:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# ---------------------------------------------------------------------------------------
# Games, a-priori edge rank, and per-policy static masks (outcome-independent).
# ---------------------------------------------------------------------------------------
def band_surplus(positions):
    """Per-band matched-blind surplus proxy used ONLY to RANK which positions to keep when a
    per-game cap binds. Band-aggregate (never per-position outcome), so the ranking is
    outcome-independent w.r.t. any single position — the a-priori 'which bands carry the
    consensus premium' signal (REFINED-STRATEGY: 0.6–0.8 richest)."""
    by_band = defaultdict(list)
    for p in positions:
        by_band[p["band"]].append(p["won"] - p["entry"])
    return {b: float(np.mean(v)) for b, v in by_band.items()}


def build_games(positions):
    """Group positions into games; attach a stable outcome-independent keep-order."""
    bsurp = band_surplus(positions)
    games = defaultdict(list)
    for i, p in enumerate(positions):
        games[p["game"]].append(i)
    order = {}   # game -> position indices sorted by (edge desc, entry asc, slug) — a-priori
    for g, idxs in games.items():
        order[g] = sorted(idxs, key=lambda i: (-bsurp.get(positions[i]["band"], 0.0),
                                               positions[i]["entry"], positions[i]["slug"]))
    return games, order, bsurp


def policy_mask(positions, order, policy, k_game):
    """Return (include: bool[N], stake_kind, f_full_by_band) applying EVENT (≤1) and GAME
    (≤k_game) caps + P3 redundancy drop, all outcome-independent. flat vs kelly handled at
    simulate time. keep-order = a-priori edge rank."""
    N = len(positions)
    include = np.zeros(N, dtype=bool)
    for g, idxs in order.items():
        ev_count = defaultdict(int)
        kept = 0
        cap_g = k_game if policy in ("P2", "P3", "P4") else 10**9
        for i in idxs:
            p = positions[i]
            if policy == "P3" and (p["is_exact_score"] or p["near_certain"]):
                continue                                  # drop the redundant near-certain family
            if policy in ("P1", "P2", "P3", "P4") and ev_count[p["event"]] >= EVENT_CAP:
                continue                                  # ≤1 unit/event (constitution)
            if kept >= cap_g:
                continue                                  # ≤k_game/GAME (the fix)
            include[i] = True
            ev_count[p["event"]] += 1
            kept += 1
    # P0 = flat_shares, everything in, no caps.
    if policy == "P0":
        include[:] = True
    return include


# ---------------------------------------------------------------------------------------
# Per-position stake fractions (kelly) — computed once from band Kelly; game-split for P4.
# ---------------------------------------------------------------------------------------
def stake_fractions(positions, include, order, policy, kelly_full):
    """Return per-position kelly fraction f_i (fraction of CURRENT bankroll) for kelly
    policies; flat policies ignore it. P0 is flat. P1/P2/P3 = ⅛-Kelly per band. P4 = size the
    GAME as ONE ⅛-Kelly bet (on the game's representative/highest-edge kept band), split equally
    across the game's kept positions."""
    N = len(positions)
    f = np.zeros(N)
    if policy == "P0":
        return f, "flat"
    if policy in ("P1", "P2", "P3"):
        for i in range(N):
            if include[i]:
                f[i] = KELLY_MULT * kelly_full.get(positions[i]["band"], 0.0)
        return f, "kelly"
    # P4 — per-game Kelly
    for g, idxs in order.items():
        kept = [i for i in idxs if include[i]]
        if not kept:
            continue
        rep_band = positions[kept[0]]["band"]             # highest a-priori-edge kept band
        F_g = KELLY_MULT * kelly_full.get(rep_band, 0.0)
        for i in kept:
            f[i] = F_g / len(kept)
    return f, "kelly"


# ---------------------------------------------------------------------------------------
# The Monte Carlo. Resample GAME blocks; group into synthetic slates (day latent + stop-loss).
# ---------------------------------------------------------------------------------------
def _precompute(positions, include, f, thr_by_lambda):
    """Static per-position arrays for the sim (only included positions carry stake)."""
    c = np.array([p["c"] for p in positions])
    won = np.array([p["won"] for p in positions], dtype=float)
    flat_pnl = STAKE * (won - c) - FEE * STAKE * c           # arm-A flat-shares $ (real outcome)
    unit = won / c - 1.0 - FEE                                # arm-A kelly per-$ return
    return {"c": c, "won": won, "flat_pnl": flat_pnl, "unit": unit,
            "f": f, "include": include, "thr": thr_by_lambda}


def _game_index(positions):
    by_game = defaultdict(list)
    for i, p in enumerate(positions):
        by_game[p["game"]].append(i)
    return list(by_game.values())


def simulate(positions, include, f, stake_kind, B, H, arm, lam, w_game, w_day,
             n_paths, seed, games=None, thr=None, gps=6):
    """One (policy × arm × λ × w_game) cell. arm ∈ {'A','B'}. Returns arrays term/maxdd/minb.
    games: list of position-index lists (one per game). gps = games per synthetic slate.
    H counts PRESENTED positions (the calendar), NOT bets — so every policy experiences the
    same opportunity stream and differs only by how it sizes it. Games are resampled with
    replacement; each synthetic slate of `gps` games shares a day latent U_day (arm B) and a
    −5-unit stop-loss window (both arms)."""
    rng = np.random.default_rng(seed)
    if games is None:
        games = _game_index(positions)
    idx_arr = [np.asarray(g) for g in games]
    c = np.array([p["c"] for p in positions])
    won_real = np.array([p["won"] for p in positions], dtype=float)
    a2 = math.sqrt(max(w_day, 0.0))
    b2 = math.sqrt(max(w_game - w_day, 0.0))
    c2 = math.sqrt(max(1.0 - w_game, 0.0))
    n_games = len(games)
    term = np.empty(n_paths)
    maxdd = np.empty(n_paths)
    minb = np.empty(n_paths)
    is_kelly = stake_kind == "kelly"
    is_B = arm == "B"

    for pth in range(n_paths):
        bank = peak = mnb = B
        mdd = 0.0
        presented = 0
        while presented < H:
            slate_games = rng.integers(0, n_games, size=gps)   # one synthetic slate
            u_day = rng.standard_normal() if is_B else 0.0
            slate_pnl = 0.0
            stopped = False
            for g in slate_games:
                idx = idx_arr[g]
                if is_B:
                    v_game = rng.standard_normal()
                    z = a2 * u_day + b2 * v_game + c2 * rng.standard_normal(len(idx))
                    win = (z <= thr[idx]).astype(float)
                else:
                    win = won_real[idx]
                for k in range(len(idx)):
                    if presented >= H:
                        break
                    presented += 1
                    i = idx[k]
                    if stopped or not include[i]:
                        continue
                    ci = c[i]
                    if is_kelly:
                        delta = f[i] * bank * (win[k] / ci - 1.0 - FEE)
                    else:
                        delta = STAKE * (win[k] - ci) - FEE * STAKE * ci
                    bank += delta
                    slate_pnl += delta
                    if bank > peak:
                        peak = bank
                    else:
                        dd = (peak - bank) / peak if peak > 0 else 1.0
                        if dd > mdd:
                            mdd = dd
                    if bank < mnb:
                        mnb = bank
                    if slate_pnl <= -STOP_LOSS_UNITS * STAKE:
                        stopped = True
                if presented >= H:
                    break
        term[pth] = bank
        maxdd[pth] = mdd
        minb[pth] = mnb
    return term, maxdd, minb


def worst_game_loss_pct(positions, games, include, f, stake_kind, B):
    """Worst-case single-GAME loss as % of bankroll B if that game's bet positions all lose
    together (the levered-block tail the event-keyed cap does NOT bound). kelly loss ≈
    f·B·(1+fee); flat-shares loss = c·(1+fee)·STAKE."""
    loss = defaultdict(float)
    for gi, idxs in enumerate(games):
        for i in idxs:
            if not include[i]:
                continue
            if stake_kind == "kelly":
                loss[gi] += f[i] * B * (1 + FEE)
            else:
                loss[gi] += STAKE * positions[i]["c"] * (1 + FEE)
    return 100.0 * (max(loss.values()) if loss else 0.0) / B


def metrics(term, maxdd, minb, B, H):
    pnl = term - B
    with np.errstate(divide="ignore"):
        logr = np.log(np.maximum(term, 1e-9) / B)
    g100 = float(np.median(logr) * (100.0 / H))
    p95dd = float(np.percentile(maxdd, 95))
    return {
        "median_pnl": float(np.median(pnl)),
        "p5_pnl": float(np.percentile(pnl, 5)),
        "p_profit": float(np.mean(pnl > 0)),
        "median_maxdd": float(np.median(maxdd)),
        "p95_maxdd": p95dd,
        "p_maxdd_over_ceil": float(np.mean(maxdd > DD_CEIL)),
        "p_ruin": float(np.mean(minb <= RUIN_FRAC * B)),
        "median_g_per_100": g100,
        "risk_adj_ratio": (g100 / p95dd if p95dd > 1e-9 else float("inf")),
    }


# ---------------------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------------------
def make_configs():
    cfgs = [("P0", None), ("P1", None)]
    for k in K_GAME_SWEEP:
        cfgs.append(("P2", k))
    cfgs.append(("P3", 2))     # P3 keeps ≤2/game after dropping redundancy
    cfgs.append(("P4", None))  # P4 sizes the game as one bet (k implicit)
    return cfgs


def cfg_name(policy, k):
    if policy == "P2":
        return f"P2_game_cap_{'inf' if k >= 10**9 else k}"
    if policy == "P3":
        return "P3_drop_redundant"
    if policy == "P4":
        return "P4_per_game_kelly"
    return {"P0": "P0_flat_shares", "P1": "P1_constitution_event_caps"}[policy]


def run(strategy="favorite", n_paths=N_PATHS, quiet=False):
    positions = fetch_positions(strategy)
    wr = float(np.mean([p["won"] for p in positions]))
    delta = calibrate_delta(positions, wr)
    kelly_full = re_.kelly_by_band(
        [{"c": p["c"], "won": p["won"], "band": p["band"]} for p in positions])
    games, order, bsurp = build_games(positions)
    game_idx = list(games.values())
    entries = np.array([p["entry"] for p in positions])
    # w_game measured lower bound = win-indicator ICC at the GAME grain (portfolio_concentration
    # machinery). It is a LOWER BOUND: on a no-upset record the within-game shared shock is
    # unsampled, so this measures only idiosyncratic single-market discordance (game_correlation.py).
    import portfolio_concentration as pc
    wins_by_game = defaultdict(list)
    for p in positions:
        wins_by_game[p["game"]].append(p["won"])
    icc_win, _, _, _ = pc.icc_oneway(list(wins_by_game.values()))
    w_lb = round(max(0.02, icc_win), 3)
    wgame_sweep = [w_lb] + WGAME_SWEEP_HI
    thr_by_lambda = {lam: norm_ppf(np.clip(entries + lam * delta, 0.02, 0.995))
                     for lam in LAMBDAS}

    meta = {"seed": SEED, "strategy": strategy, "n_positions": len(positions),
            "n_games": len(games), "realized_wr": round(wr, 4), "delta": round(delta, 4),
            "kelly_full_by_band": {str(k): round(v, 4) for k, v in kelly_full.items()},
            "w_game_lower_bound": w_lb, "w_game_sweep": wgame_sweep, "w_day": W_DAY,
            "dd_ceiling": DD_CEIL, "dd_ceiling_p": DD_CEIL_P, "lambda_grid": LAMBDAS,
            "bankroll_headline": B_HEADLINE, "n_paths": n_paths,
            "objective": "max median log-growth/100 s.t. P(maxDD>25%)<=10% under game-block "
                         "copula at lambda=0.5, robust across w_game; report the knee"}

    configs = make_configs()
    H1 = len(positions)                 # 1× record
    H5 = 5 * H1                          # ~1yr extrapolation (K1)

    def cell(policy, k, arm, lam, w_game, B, H, np_, seed):
        include = policy_mask(positions, order, policy, k or 10**9)
        f, kind = stake_fractions(positions, include, order, policy, kelly_full)
        term, mdd, mnb = simulate(positions, include, f, kind, B, H, arm, lam, w_game,
                                  W_DAY, np_, seed, games=game_idx, thr=thr_by_lambda[lam])
        m = metrics(term, mdd, mnb, B, H)
        m["n_bet"] = int(include.sum())
        m["worst_game_loss_pct"] = round(worst_game_loss_pct(
            positions, game_idx, include, f, kind, B), 1)
        return m

    result = {"meta": meta, "arm_A_benign": {}, "frontier_lambda05": {},
              "lambda_sweep": {}, "wgame_sweep": {}, "recommendation": {}}

    # arm A — benign block-bootstrap floor (real outcomes), H=1×, headline B
    for policy, k in configs:
        nm = cfg_name(policy, k)
        result["arm_A_benign"][nm] = cell(policy, k, "A", 1.0, 0.0, B_HEADLINE, H1, n_paths, SEED + 1)

    # frontier — arm B copula, λ=0.5, w_game=0.55 (headline) AND worst-case 0.8 (robust check)
    for policy, k in configs:
        nm = cfg_name(policy, k)
        result["frontier_lambda05"][nm] = {
            "wgame_0.55": cell(policy, k, "B", 0.5, 0.55, B_HEADLINE, H1, n_paths, SEED + 2),
            "wgame_0.80": cell(policy, k, "B", 0.5, 0.80, B_HEADLINE, H1, n_paths, SEED + 3)}

    # FROZEN pick: among configs satisfying P(maxDD>25%)<=10% at λ=0.5 for BOTH w_game 0.55 &
    # 0.80 (robust), pick the max median growth. Tie-break higher risk-adjusted ratio.
    elig = []
    for policy, k in configs:
        nm = cfg_name(policy, k)
        fr = result["frontier_lambda05"][nm]
        if (fr["wgame_0.55"]["p_maxdd_over_ceil"] <= DD_CEIL_P
                and fr["wgame_0.80"]["p_maxdd_over_ceil"] <= DD_CEIL_P):
            elig.append((policy, k, nm, fr["wgame_0.55"]["median_g_per_100"],
                         fr["wgame_0.55"]["risk_adj_ratio"]))
    elig.sort(key=lambda x: (-x[3], -x[4]))
    frozen_policy, frozen_k, frozen_nm = (
        (elig[0][0], elig[0][1], elig[0][2]) if elig else ("P4", None, cfg_name("P4", None)))

    # K5 per config: median log-growth at λ=1 (copula) — the profit the edge would deliver if real.
    # baseline = max(P0, P1). worst_game_loss = the levered-block tail (worst single-game % of B).
    k1 = {}
    for policy, k in configs:
        nm = cfg_name(policy, k)
        m = cell(policy, k, "B", 1.0, 0.55, B_HEADLINE, H1, N_PATHS_REC, SEED + 40)
        k1[nm] = {"g100_lambda1": m["median_g_per_100"], "worst_game_loss_pct": m["worst_game_loss_pct"],
                  "n_bet": m["n_bet"], "policy": policy, "k": k}
    base_g1 = max(k1[cfg_name("P0", None)]["g100_lambda1"], k1[cfg_name("P1", None)]["g100_lambda1"])
    for nm in k1:
        k1[nm]["k5_frac"] = (k1[nm]["g100_lambda1"] / base_g1) if base_g1 > 0 else float("nan")

    # HONEST OVERRIDE (à la risk_engine, D15): the record has NO upset, so the average-path DD
    # ceiling is slack and cannot see the worst-case single-GAME block (which the event-keyed cap
    # leaves at up to ~35% of bankroll). The construction-bounded recommendation is the tightest
    # per-GAME cap that STILL preserves ≥90% of the edge's growth (K5) — insurance against the
    # tail the benign record cannot price, bought without gutting EV.
    game_caps = [(cfg_name("P2", k), "P2", k) for k in K_GAME_SWEEP]
    k5_ok = [(nm, pol, k) for (nm, pol, k) in game_caps if k1[nm]["k5_frac"] >= 0.90]
    # tightest = lowest worst_game_loss among K5-passers; if none pass, no cap preserves profit.
    if k5_ok:
        honest_nm, honest_policy, honest_k = min(k5_ok, key=lambda t: k1[t[0]]["worst_game_loss_pct"])
    else:
        honest_nm, honest_policy, honest_k = frozen_nm, frozen_policy, frozen_k
    rec_policy, rec_k, rec_nm = honest_policy, honest_k, honest_nm

    # λ sweep for the key policies (P0, P1, recommended, P3, P4) at w_game 0.55, headline B
    key = [("P0", None), ("P1", None), (rec_policy, rec_k)]
    for extra in [("P3", 2), ("P4", None)]:
        if extra not in key:
            key.append(extra)
    for policy, k in key:
        nm = cfg_name(policy, k)
        result["lambda_sweep"][nm] = {
            str(lam): cell(policy, k, "B", lam, 0.55, B_HEADLINE, H1, n_paths, SEED + 10 + int(lam*10))
            for lam in LAMBDAS}

    # w_game sensitivity for recommended + P0 + P1 at λ=0.5
    for policy, k in [("P0", None), ("P1", None), (rec_policy, rec_k)]:
        nm = cfg_name(policy, k)
        result["wgame_sweep"][nm] = {
            str(wg): cell(policy, k, "B", 0.5, wg, B_HEADLINE, H1, n_paths, SEED + 20 + int(wg*100))
            for wg in wgame_sweep}

    # K5 profit-preservation table (all configs), + the frozen-vs-honest comparison.
    k5 = {"baseline_max_g100_lambda1": base_g1, "bar_90pct": 0.90 * base_g1,
          "per_config": {nm: {"g100_lambda1": k1[nm]["g100_lambda1"],
                              "k5_frac": k1[nm]["k5_frac"],
                              "worst_game_loss_pct": k1[nm]["worst_game_loss_pct"],
                              "n_bet": k1[nm]["n_bet"]} for nm in k1},
          "frozen_pick": frozen_nm,
          "honest_recommendation": honest_nm,
          "honest_k5_frac": k1[honest_nm]["k5_frac"],
          "honest_passes_90": bool(k1[honest_nm]["k5_frac"] >= 0.90),
          "honest_worst_game_loss_pct": k1[honest_nm]["worst_game_loss_pct"],
          "constitution_worst_game_loss_pct": k1[cfg_name("P1", None)]["worst_game_loss_pct"],
          "rule": ("honest override: record has no upset ⇒ avg-path DD ceiling is slack and "
                   "cannot see the worst single-GAME block; recommend the tightest per-GAME cap "
                   "that still preserves ≥90% of λ=1 growth")}

    # recommended detail: H=1× and H=5× (extrapolation), λ=0.5 & 1, arm A, bankroll sensitivity
    rec_detail = {"config": rec_nm, "policy": rec_policy, "k_game": rec_k,
                  "arm_A_benign_H1": result["arm_A_benign"][rec_nm],
                  "copula_l05_w055_H1": result["frontier_lambda05"][rec_nm]["wgame_0.55"],
                  "copula_l05_w080_H1": result["frontier_lambda05"][rec_nm]["wgame_0.80"],
                  "copula_l05_w055_H5_extrapolation":
                      cell(rec_policy, rec_k, "B", 0.5, 0.55, B_HEADLINE, H5, n_paths, SEED + 50),
                  "risk_adj_ratio_l05_w055": result["frontier_lambda05"][rec_nm]["wgame_0.55"]["risk_adj_ratio"],
                  "bankroll_sensitivity": {}}
    for B in BANKROLLS:
        rec_detail["bankroll_sensitivity"][str(int(B))] = cell(
            rec_policy, rec_k, "B", 0.5, 0.55, B, H1, n_paths, SEED + 60 + int(B))
    result["recommendation"] = {"frozen_pick": frozen_nm, "chosen": rec_nm,
                                "eligible_frozen": [e[2] for e in elig],
                                "detail": rec_detail, "k5_profit_preservation": k5}

    if not quiet:
        _print(result)
    return result


def _print(r):
    m = r["meta"]
    print(f"CORRELATED-RISK ENGINE · {m['strategy']} · {m['n_positions']} positions on "
          f"{m['n_games']} games · WR {m['realized_wr']:.1%} · δ {m['delta']:+.3f} · "
          f"{m['n_paths']} game-block paths")
    print(f"kelly-by-band (SE-shrunk): {m['kelly_full_by_band']} · w_game lower bound "
          f"{m['w_game_lower_bound']} · sweep {m['w_game_sweep']}")
    print("ALL P(profit) CONDITIONAL ON THE EDGE BEING REAL (λ<1 haircuts it; λ=0 = costs-only).\n")

    print("ARM A — benign block-bootstrap (real outcomes; 'future = the good days we saw' FLOOR), "
          f"H={m['n_positions']}, B=${int(m['bankroll_headline'])}")
    hdr = f"{'config':<28}{'bet':>4}{'medP&L':>9}{'p95DD':>7}{'P(DD>25)':>9}{'g/100':>8}{'ratio':>7}"
    print(hdr); print("-" * len(hdr))
    for nm, s in r["arm_A_benign"].items():
        print(f"{nm:<28}{s['n_bet']:>4}{s['median_pnl']:>+9.0f}{s['p95_maxdd']:>7.1%}"
              f"{s['p_maxdd_over_ceil']:>9.1%}{s['median_g_per_100']:>+8.3f}{s['risk_adj_ratio']:>7.2f}")

    print(f"\nFRONTIER — GAME-BLOCK COPULA at λ=0.5 (the honest tail). w=0.55 | 0.80 | worst-game loss%")
    print(hdr + "  | w=.80 P(DD>25)ratio | wGmLoss%")
    print("-" * (len(hdr) + 32))
    for nm, cells in r["frontier_lambda05"].items():
        a, b = cells["wgame_0.55"], cells["wgame_0.80"]
        print(f"{nm:<28}{a['n_bet']:>4}{a['median_pnl']:>+9.0f}{a['p95_maxdd']:>7.1%}"
              f"{a['p_maxdd_over_ceil']:>9.1%}{a['median_g_per_100']:>+8.3f}{a['risk_adj_ratio']:>7.2f}"
              f"  | {b['p_maxdd_over_ceil']:>7.1%}{b['risk_adj_ratio']:>5.2f} | {a['worst_game_loss_pct']:>6.0f}%")

    rec = r["recommendation"]
    k5 = rec["k5_profit_preservation"]
    print(f"\nFROZEN pick (max growth s.t. P(maxDD>25%)≤10% @ λ=0.5): {rec['frozen_pick']}  "
          f"— but the DD ceiling is SLACK (no upset in the record).")
    print("K5 PROFIT-PRESERVATION across the per-GAME cap sweep (g/100 @ λ=1 vs baseline; worst-game loss %):")
    print(f"  {'config':<28}{'g/100 λ=1':>11}{'K5%':>6}{'worstGmLoss%':>13}")
    for nm, v in k5["per_config"].items():
        star = "  ← honest rec" if nm == rec["chosen"] else ""
        print(f"  {nm:<28}{v['g100_lambda1']:>+11.3f}{100*v['k5_frac']:>5.0f}%"
              f"{v['worst_game_loss_pct']:>12.0f}%{star}")
    print(f"\nHONEST RECOMMENDATION (tightest per-GAME cap preserving ≥90% of λ=1 growth): {rec['chosen']}")
    print(f"  → bounds worst single-GAME loss {k5['constitution_worst_game_loss_pct']:.0f}% "
          f"(current constitution) → {k5['honest_worst_game_loss_pct']:.0f}% of bankroll, "
          f"K5 {100*k5['honest_k5_frac']:.0f}% "
          f"[{'PASS' if k5['honest_passes_90'] else 'FAIL'}]")
    print(f"  risk-adjusted ratio (λ=0.5,w=0.55) = {rec['detail']['risk_adj_ratio_l05_w055']:.2f}  "
          f"[the single 'profit per unit of correlated tail risk' number]")

    print("\nλ-SWEEP (game-block copula, w_game 0.55, H=1×) — P(profit)/median P&L; λ=0 = costs-only floor")
    print(f"{'config':<28}" + "".join(f"{'λ='+str(l):>16}" for l in LAMBDAS))
    for nm, cells in r["lambda_sweep"].items():
        print(f"{nm:<28}" + "".join(
            f"{cells[str(l)]['p_profit']:>7.0%}/{cells[str(l)]['median_pnl']:>+7.0f}" for l in LAMBDAS))

    print("\nw_game SENSITIVITY (λ=0.5, H=1×) — p95 maxDD / P(DD>25%) as within-game correlation rises")
    sweep_keys = list(next(iter(r["wgame_sweep"].values())).keys())
    print(f"{'config':<28}" + "".join(f"{'w='+k:>16}" for k in sweep_keys))
    for nm, cells in r["wgame_sweep"].items():
        print(f"{nm:<28}" + "".join(
            f"{cells[k]['p95_maxdd']:>7.1%}/{cells[k]['p_maxdd_over_ceil']:>7.1%}" for k in sweep_keys))


# =======================================================================================
# SELF-TESTS (mandatory; ship only on PASS)
# =======================================================================================
def _mk(positions):
    games, order, _ = build_games(positions)
    return positions, games, order, list(games.values())


def _pos(game, event, entry, won, band=None, regime="soccer", day="d0", slug="", **kw):
    return {"game": game, "event": event, "regime": regime, "day": day, "entry": entry,
            "c": min(0.999, entry + HAIRCUT), "won": won, "band": band or sn.band(entry),
            "is_exact_score": kw.get("is_exact_score", False),
            "near_certain": entry >= 0.95, "slug": slug or f"{game}-{event}"}


def selftest():
    ok = True
    rng = np.random.default_rng(SEED)

    # ---- (a) iid fixture: game-block ≈ position bootstrap; per-game cap INERT (1 pos/game) ----
    print("— (a) iid: game-block ≈ position-block; per-game cap inert —")
    iid = [_pos(f"g{i}", f"g{i}", 0.60, 1.0 if rng.random() < 0.70 else 0.0, day=f"d{i%40}")
           for i in range(400)]
    inc = np.ones(len(iid), dtype=bool)
    f0 = np.zeros(len(iid))
    gi = _game_index(iid)
    tb, ddb, mnb = simulate(iid, inc, f0, "flat", 1000.0, 400, "A", 1.0, 0.0, 0.0, 2000, SEED, games=gi)
    # position bootstrap == each position its own game
    pg = [[i] for i in range(len(iid))]
    tp, ddp, mnp = simulate(iid, inc, f0, "flat", 1000.0, 400, "A", 1.0, 0.0, 0.0, 2000, SEED, games=pg)
    close = abs(np.std(tb) - np.std(tp)) <= 0.20 * np.std(tp)
    ok = ok and close
    print(f"  [{'ok' if close else 'FAIL'}] terminal SD: game-block {np.std(tb):.0f} ≈ position {np.std(tp):.0f}")

    # ---- (b) fully-correlated game: block recovers inflated variance; per-game cap truncates it;
    #          POSITION bootstrap UNDERSTATES it (the exact leak this run fixes) ----
    print("— (b) fully-correlated game: block>position tail; per-game cap truncates —")
    corr = []
    for gnum in range(60):
        gwin = 1.0 if rng.random() < 0.70 else 0.0        # whole game shares one outcome
        for k in range(10):
            corr.append(_pos(f"cg{gnum}", f"cg{gnum}-e{k}", 0.60, gwin, day=f"d{gnum}",
                             slug=f"cg{gnum}-e{k}"))
    incc = np.ones(len(corr), dtype=bool)
    fc = np.zeros(len(corr))
    gic = _game_index(corr)
    tb2, dd2, _ = simulate(corr, incc, fc, "flat", 1000.0, 600, "A", 1.0, 0.0, 0.0, 3000, SEED, games=gic)
    # position bootstrap breaks the block → understates
    pgc = [[i] for i in range(len(corr))]
    tp2, ddp2, _ = simulate(corr, incc, fc, "flat", 1000.0, 600, "A", 1.0, 0.0, 0.0, 3000, SEED, games=pgc)
    understates = np.std(tp2) < 0.6 * np.std(tb2)
    ok = ok and understates
    print(f"  [{'ok' if understates else 'FAIL'}] terminal SD: game-block {np.std(tb2):.0f} vs "
          f"position {np.std(tp2):.0f} (position understates ≥40%)")
    p5b = np.percentile(tb2 - 1000, 5); p5p = np.percentile(tp2 - 1000, 5)
    fatter = p5b < p5p
    ok = ok and fatter
    print(f"  [{'ok' if fatter else 'FAIL'}] 5th-pct P&L: block {p5b:+.0f} < position {p5p:+.0f} (fatter block tail)")
    # per-game cap ≤1 truncates the block: keep 1 of 10 per game
    _, order_c, _ = build_games(corr)
    inc_cap = policy_mask(corr, order_c, "P2", 1)
    tbc, ddc, _ = simulate(corr, inc_cap, fc, "flat", 1000.0, 600, "A", 1.0, 0.0, 0.0, 3000, SEED, games=gic)
    trunc = np.percentile(ddc, 95) < np.percentile(dd2, 95) and inc_cap.sum() < len(corr)
    ok = ok and trunc
    print(f"  [{'ok' if trunc else 'FAIL'}] per-game cap=1 kept {int(inc_cap.sum())}/{len(corr)}; "
          f"p95 maxDD {np.percentile(ddc,95):.1%} < uncapped {np.percentile(dd2,95):.1%}")

    # ---- (c) zero-edge (efficient market) copula ⇒ every policy loses to costs ----
    print("— (c) zero-edge copula (λ=0): loses to costs —")
    ze = [_pos(f"z{i}", f"z{i}", 0.60, 0.0, day=f"d{i%40}") for i in range(300)]
    incz = np.ones(len(ze), dtype=bool); fz = np.zeros(len(ze)); giz = _game_index(ze)
    thr0 = norm_ppf(np.clip(np.array([p["entry"] for p in ze]) + 0.0, 0.02, 0.995))
    tz, _, _ = simulate(ze, incz, fz, "flat", 1000.0, 300, "B", 0.0, 0.4, 0.05, 3000, SEED, games=giz, thr=thr0)
    loses = np.median(tz - 1000) < 0
    ok = ok and loses
    print(f"  [{'ok' if loses else 'FAIL'}] zero-edge median P&L {np.median(tz-1000):+.0f} (<0, costs)")

    # ---- (d) scripted upset cluster ⇒ stop-loss / caps bind ----
    print("— (d) scripted upset cluster ⇒ stop-loss binds —")
    upset = [_pos("BIG", f"BIG-e{k}", 0.90, 0.0, day="d0", slug=f"BIG-e{k}") for k in range(20)]
    upset += [_pos(f"ok{i}", f"ok{i}", 0.70, 1.0, day=f"d{1+i%20}") for i in range(300)]
    incu = np.ones(len(upset), dtype=bool); fu = np.zeros(len(upset)); giu = _game_index(upset)
    # uncapped vs per-game cap=2 — cap must reduce the tail from the 20-position upset block
    _, order_u, _ = build_games(upset)
    inc_uc = policy_mask(upset, order_u, "P2", 2)
    tu, ddu, _ = simulate(upset, incu, fu, "flat", 2000.0, 320, "A", 1.0, 0.0, 0.0, 2000, SEED, games=giu)
    tc, ddcap, _ = simulate(upset, inc_uc, fu, "flat", 2000.0, 320, "A", 1.0, 0.0, 0.0, 2000, SEED, games=giu)
    binds = np.percentile(ddcap, 95) < np.percentile(ddu, 95)
    ok = ok and binds
    print(f"  [{'ok' if binds else 'FAIL'}] per-game cap p95 maxDD {np.percentile(ddcap,95):.1%} "
          f"< uncapped {np.percentile(ddu,95):.1%}")

    # ---- (e) copula monotonicity: higher w_game ⇒ fatter tail ----
    print("— (e) copula: higher w_game ⇒ fatter tail —")
    thr_c = norm_ppf(np.clip(np.array([p["entry"] for p in corr]) + 0.11, 0.02, 0.995))
    dds = []
    for wg in (0.05, 0.5, 0.9):
        _, dd, _ = simulate(corr, incc, fc, "flat", 1000.0, 600, "B", 1.0, wg, 0.05, 2000, SEED,
                            games=gic, thr=thr_c)
        dds.append(np.percentile(dd, 95))
    mono = dds[0] < dds[1] < dds[2]
    ok = ok and mono
    print(f"  [{'ok' if mono else 'FAIL'}] p95 maxDD by w_game: {dds[0]:.1%} < {dds[1]:.1%} < {dds[2]:.1%}")

    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    result = run()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "reports", "corr_risk_engine.json")
    with open(out, "w") as f:
        json.dump(result, f, indent=1, default=str)
    print("\nartifact → reports/corr_risk_engine.json")


if __name__ == "__main__":
    main()
