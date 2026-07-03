#!/usr/bin/env python3
"""
WS-B — PIN THE DE-LEVER KELLY FRACTION.

D18/D19/D21 all concluded "de-lever the band-5 Kelly" (P0 flat-shares is ~4× safer on CVaR than any
⅛-Kelly cap) but NEVER pinned the multiplier. This finds the Kelly multiplier `k` that maximizes
growth-per-unit-of-tail-risk under the ADVERSE model, robust across the λ we cannot yet measure.

It does NOT re-open the sizing/game-cap debate (settled: D20→D21, the cap is not a free win; the
KELLY FRACTION is the first-order lever). It PINS the fraction on the frontier and recommends the knee.

Method (reuses corr_risk_verify's adverse simulator verbatim so every number is comparable):
  policy   = P1 constitution (all favorite positions, per-slate −5u stop) — the sizing question,
             isolated from the cap question.
  sweep    = k ∈ {¼, ⅙, ⅛, ⅟₁₂, ⅟₁₆, ⅟₂₄, ⅟₃₂}  (f_i = k · kelly_full[band_i]); flat-shares = floor.
  model    = t-copula ν=4 + heterogeneous within-game correlation (the adverse tail).
  λ        = {1, 0.5, 0.25, 0}, multi-seed. Every metric carries the conditional-on-λ caveat + λ=0 line.
  objective= OBJ(k) = median growth/100 ÷ |CVaR₅|  at λ=0.5,  FEASIBLE ⇔ P(maxDD>25%) ≤ 10% at λ=0.5.
  recommend= the FEASIBLE k maximizing OBJ at λ=0.5 (the honest de-lever knee). If the knee is
             flat-shares (k→0) the honest answer is "don't Kelly-size at all yet." If the knee flips
             across λ, the conservative (lowest-k) binds.

Read-only, paper-only, nothing applied. Zero migrations.
  ./corr_risk_delever.py            # frontier table + recommended k; writes reports/corr_risk_delever.json
  ./corr_risk_delever.py --selftest # monotonicity: growth↑ and |CVaR|↑ in k at λ=1; flat is the floor
"""

import json
import os
import sys
from fractions import Fraction

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import corr_risk_engine as ce
import corr_risk_verify as cv

# Kelly multipliers to sweep (as exact fractions for labelling).
K_SWEEP = [Fraction(1, 4), Fraction(1, 6), Fraction(1, 8), Fraction(1, 12),
           Fraction(1, 16), Fraction(1, 24), Fraction(1, 32)]
LAMBDAS = [1.0, 0.5, 0.25, 0.0]
ADVERSE = dict(copula="t", w_dir=0.55, w_indep=0.08, nu=4)   # A1+A2 adverse (matches corr_risk_verify)
DD_CAP = 0.25          # feasibility: P(maxDD > 25%) ≤ 10% at λ=0.5
DD_CAP_P = 0.10
N_SEEDS = cv.N_SEEDS


def kelly_f(positions, include, kelly_full, k):
    """f_i = k · kelly_full[band_i] for included positions, 0 otherwise (k = Kelly multiplier)."""
    f = np.zeros(len(positions))
    for i, p in enumerate(positions):
        if include[i]:
            f[i] = float(k) * kelly_full.get(p["band"], 0.0)
    return f


def metrics_at(positions, include, f, kind, H, delta, games, lam, n_seeds=N_SEEDS):
    return cv.multiseed(positions, include, f, kind, H, lam, delta, games,
                        n_seeds=n_seeds, **ADVERSE)


def run(quiet=False):
    positions = cv.classify(ce.fetch_positions("favorite"))
    wr = float(np.mean([p["won"] for p in positions]))
    delta = ce.calibrate_delta(positions, wr)
    kelly_full = ce.re_.kelly_by_band(
        [{"c": p["c"], "won": p["won"], "band": p["band"]} for p in positions])
    games, order, _ = ce.build_games(positions)
    game_idx = list(games.values())
    H = len(positions)
    inc = ce.policy_mask(positions, order, "P1", 10**9)      # constitution: all favorite positions

    rows = []
    # flat-shares floor
    flat_f = np.zeros(len(positions))
    rows.append(("flat_shares", None, flat_f, "flat"))
    for k in K_SWEEP:
        rows.append((f"kelly_1/{int(1/k)}", k, kelly_f(positions, inc, kelly_full, k), "kelly"))

    frontier = {}
    for label, k, f, kind in rows:
        by_lam = {}
        for lam in LAMBDAS:
            m = metrics_at(positions, inc, f, kind, H, delta, game_idx, lam)
            by_lam[str(lam)] = {
                "g100": m["g100"], "cvar5_pnl": m["cvar5_pnl"], "p95_maxdd": m["p95_maxdd"],
                "p99_maxdd": m["p99_maxdd"], "p_dd_over25": m["p_dd_over25"],
                "p_loss": 1.0 - m["p_profit"], "median_pnl": m["median_pnl"],
            }
        h = by_lam["0.5"]
        feasible = h["p_dd_over25"] <= DD_CAP_P
        # objective = growth per unit of FRACTIONAL CVaR (|CVaR5|/bankroll) — dimensionless & legible.
        frac_cvar = abs(h["cvar5_pnl"]) / cv.B
        obj = (h["g100"] / frac_cvar) if frac_cvar > 1e-9 else float("inf")
        frontier[label] = {"k": (float(k) if k is not None else 0.0), "kind": kind,
                           "feasible_at_0.5": feasible, "objective_at_0.5": obj, "by_lambda": by_lam}

    # recommend: feasible k maximizing OBJ at λ=0.5, among the Kelly rows (flat = floor sentinel)
    kelly_rows = {lab: d for lab, d in frontier.items() if d["kind"] == "kelly"}
    feasible_rows = {lab: d for lab, d in kelly_rows.items() if d["feasible_at_0.5"]}
    if feasible_rows:
        rec = max(feasible_rows.items(), key=lambda kv: kv[1]["objective_at_0.5"])
        rec_label, rec_d = rec
        knee_is_flat = False
    else:
        rec_label, rec_d, knee_is_flat = "flat_shares", frontier["flat_shares"], True

    # λ-sensitivity: recompute the argmax-OBJ at each λ; if it flips lower, the conservative binds.
    # Only λ>0 is meaningful — at λ=0 you should not bet at all (a growth/CVaR ratio on negative
    # growth is degenerate), so it does not vote on the leverage knee.
    argmax_by_lam = {}
    for lam in LAMBDAS:
        if lam <= 0.0:
            argmax_by_lam[str(lam)] = "(do-not-bet)"
            continue
        best, best_obj = None, -1e18
        for lab, d in kelly_rows.items():
            hl = d["by_lambda"][str(lam)]
            feas = hl["p_dd_over25"] <= DD_CAP_P
            o = (hl["g100"] / (abs(hl["cvar5_pnl"]) / cv.B)) if abs(hl["cvar5_pnl"]) > 1e-9 else -1e18
            if feas and o > best_obj:
                best, best_obj = lab, o
        argmax_by_lam[str(lam)] = best
    ks = [frontier[v]["k"] for v in argmax_by_lam.values()
          if v and v not in ("(do-not-bet)",)]
    knee_flips = len(set(ks)) > 1
    conservative_k = min(ks) if ks else 0.0

    result = {
        "meta": {"n_positions": len(positions), "n_games": len(games), "realized_wr": round(wr, 4),
                 "delta": round(delta, 4), "adverse_model": ADVERSE, "n_seeds": N_SEEDS,
                 "dd_cap": DD_CAP, "dd_cap_p": DD_CAP_P, "have_scipy": cv.HAVE_SCIPY,
                 "kelly_by_band": {str(k): round(v, 4) for k, v in kelly_full.items()}},
        "frontier": frontier,
        "recommendation": {
            "recommended": rec_label, "k": rec_d["k"], "knee_is_flat_shares": knee_is_flat,
            "argmax_by_lambda": argmax_by_lam, "knee_flips_across_lambda": knee_flips,
            "conservative_k_if_flips": conservative_k,
        },
    }
    if not quiet:
        _print(result)
    return result


def _print(r):
    m = r["meta"]
    print(f"WS-B DE-LEVER · favorite · {m['n_positions']} positions / {m['n_games']} games · "
          f"WR {m['realized_wr']:.1%} δ {m['delta']:+.3f}")
    print(f"adverse: t ν={m['adverse_model']['nu']} + hetero corr (scipy={m['have_scipy']}) · "
          f"{m['n_seeds']} seeds · objective = g100 ÷ |CVaR5| at λ=0.5 · feasible ⇔ P(DD>25%)≤10%\n")
    hdr = f"{'policy':<14}{'feas':>5}{'OBJ':>6}   λ=0.5 [g100  CVaR5  p95DD P(DD>25) Ploss]   λ=1 g100  λ=.25 g100  λ=0 med"
    print(hdr); print("-" * len(hdr))
    for lab, d in r["frontier"].items():
        h = d["by_lambda"]["0.5"]
        one = d["by_lambda"]["1.0"]; qtr = d["by_lambda"]["0.25"]; zero = d["by_lambda"]["0.0"]
        feas = "yes" if d["feasible_at_0.5"] else "NO"
        print(f"{lab:<14}{feas:>5}{d['objective_at_0.5']:>6.2f}   "
              f"[{h['g100']:>+6.3f} {h['cvar5_pnl']:>+6.0f} {h['p95_maxdd']:>5.0%} "
              f"{h['p_dd_over25']:>6.0%} {h['p_loss']:>5.0%}]   "
              f"{one['g100']:>+7.3f}   {qtr['g100']:>+7.3f}   {zero['median_pnl']:>+6.0f}")
    rec = r["recommendation"]
    print(f"\nRECOMMENDED de-lever k = {rec['recommended']} (k={rec['k']:.4f})"
          + ("  ⇒ knee is FLAT-SHARES: do NOT Kelly-size yet" if rec["knee_is_flat_shares"] else ""))
    print(f"argmax-OBJ by λ: {rec['argmax_by_lambda']}  "
          + (f"⇒ FLIPS across λ ⇒ conservative k={rec['conservative_k_if_flips']:.4f} binds"
             if rec["knee_flips_across_lambda"] else "⇒ stable across λ"))
    print("Every number is conditional on λ; the λ=0 column is the efficient-market loss floor.")


def selftest():
    ok = True
    positions = cv.classify(ce.fetch_positions("favorite"))
    delta = ce.calibrate_delta(positions, np.mean([p["won"] for p in positions]))
    kelly_full = ce.re_.kelly_by_band(
        [{"c": p["c"], "won": p["won"], "band": p["band"]} for p in positions])
    games, order, _ = ce.build_games(positions)
    gi = list(games.values()); H = len(positions)
    inc = ce.policy_mask(positions, order, "P1", 10**9)

    def at(k, lam, seeds=4):
        f = kelly_f(positions, inc, kelly_full, Fraction(1, k))
        return cv.multiseed(positions, inc, f, "kelly", H, lam, delta, gi, n_seeds=seeds, **ADVERSE)

    print("— (1) at λ=1, growth is monotone-ish INCREASING as k rises (¼ ≥ ⅛ ≥ ⅟₁₆ ≥ ⅟₃₂) —")
    g = {kk: at(kk, 1.0)["g100"] for kk in (4, 8, 16, 32)}
    c1 = g[4] >= g[8] >= g[16] >= g[32] - 1e-6
    ok = ok and c1
    print(f"  [{'ok' if c1 else 'FAIL'}] g100 ¼={g[4]:+.3f} ⅛={g[8]:+.3f} ⅟₁₆={g[16]:+.3f} ⅟₃₂={g[32]:+.3f}")

    print("— (2) tail risk |CVaR5| is monotone INCREASING in k at λ=0.5 (more lever ⇒ deeper tail) —")
    cvar = {kk: abs(at(kk, 0.5)["cvar5_pnl"]) for kk in (4, 8, 16, 32)}
    c2 = cvar[4] >= cvar[8] >= cvar[16] >= cvar[32] - 1e-6
    ok = ok and c2
    print(f"  [{'ok' if c2 else 'FAIL'}] |CVaR5| ¼={cvar[4]:.0f} ⅛={cvar[8]:.0f} ⅟₁₆={cvar[16]:.0f} ⅟₃₂={cvar[32]:.0f}")

    print("— (3) flat-shares is the tail floor: |CVaR5| ≤ ⅛-Kelly's at λ=0.5 —")
    flat = cv.multiseed(positions, inc, np.zeros(len(positions)), "flat", H, 0.5, delta, gi, n_seeds=4, **ADVERSE)
    c3 = abs(flat["cvar5_pnl"]) <= cvar[8] + 1e-6
    ok = ok and c3
    print(f"  [{'ok' if c3 else 'FAIL'}] flat |CVaR5| {abs(flat['cvar5_pnl']):.0f} ≤ ⅛ {cvar[8]:.0f}")

    print("— (4) λ=0 (efficient market) loses at every k (the honest floor) —")
    z = {kk: at(kk, 0.0)["median_pnl"] for kk in (4, 16)}
    c4 = z[4] < 0 and z[16] < 0
    ok = ok and c4
    print(f"  [{'ok' if c4 else 'FAIL'}] λ=0 median ¼={z[4]:+.0f} ⅟₁₆={z[16]:+.0f} (<0)")

    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    result = run()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports", "corr_risk_delever.json")
    with open(out, "w") as f:
        json.dump(result, f, indent=1, default=str)
    print("\nartifact → reports/corr_risk_delever.json")


if __name__ == "__main__":
    main()
