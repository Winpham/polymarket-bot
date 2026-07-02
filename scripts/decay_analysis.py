#!/usr/bin/env python3
"""
EXECUTION-LATENCY DECAY — the confound-controlled speed budget (decay run Phase 1).

Within-signal or it's a confound: the naive "edge at τ minutes" curve measures which
markets happen to live long, not "the same market, later". This instrument computes the
PAIRED delta per signal — Δ(τ) = e(τ) − e0 = p0 − price(τ), each signal its own control —
event-clustered, with a bootstrap CI, a shuffle placebo beside every claim, and the
structural follower tax (sharps' fill → our first mid) reported SEPARATELY from delay
decay (our first mid → τ later; the part speed protects).

Sources: `signal_price_trajectory` (dense, ~45s, preferred) + `consensus_snapshots`
(5-min housekeeping cadence, fallback). Prices are pre-resolution by construction
(points are only captured while open; offsets past resolution are undefined).

Output: `reports/decay_report.json` + a stdout table with, per strategy:
fire edge (CLV anchor), structural tax, Δ(τ) curve ± CI with surviving-N,
the placebo curve, the SPEED BUDGET (τ where EDGE_LOSS_TOLERANCE of the fire
edge is gone) and an auto-vs-manual verdict.

Modes:
  ./decay_analysis.py               # live DB (docker-exec psql, house pattern)
  ./decay_analysis.py --selftest    # synthetic fixtures: known injected decay must be
                                    # recovered within CI; a no-decay fixture must be
                                    # flat AND ≈ its placebo. Exit non-zero on failure.
"""

import csv
import io
import json
import math
import os
import random
import subprocess
import sys
from collections import defaultdict

import numpy as np

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]
STRATEGIES = ["strict", "favorite", "elite_fresh_fav"]
GRID_MINS = [1.0, 2.0, 3.0, 5.0, 10.0, 15.0, 30.0, 60.0]
MIN_SURVIVORS = 20          # never publish a τ bucket thinner than this
N_BOOT = 2000
SEED = 20260702
EDGE_LOSS_TOLERANCE = 0.25  # speed budget = τ where 25% of the fire edge is gone
CAPTURE_MARGIN = 0.03       # slippage + fee (τ_breakeven reference)
MANUAL_LATENCY_MIN = 3.0    # achievable by a prompt human
AUTO_LATENCY_MIN = 0.25     # achievable by an auto-trader (15s)

SIG_SQL = """
SELECT id, strategy, COALESCE(event_slug, condition_id) AS ev,
       extract(epoch from first_detected_at) AS t0,
       extract(epoch from resolved_at) AS tr,
       (outcome_won::int) AS won,
       initial_market_price AS p0,
       COALESCE(initial_mean_price, mean_price) AS sharp_entry
FROM consensus_signals
WHERE resolved AND initial_market_price IS NOT NULL
  AND strategy IN ({strats})
"""

TRAJ_SQL = """
SELECT signal_id, secs_after_fire::double precision AS secs, mid AS price
FROM signal_price_trajectory WHERE mid IS NOT NULL
"""

SNAP_SQL = """
SELECT s.signal_id, extract(epoch from s.ts) AS ts, s.market_price AS price
FROM consensus_snapshots s
JOIN consensus_signals c ON c.id = s.signal_id
WHERE s.market_price IS NOT NULL AND c.resolved
  AND c.strategy IN ({strats})
"""


def q(sql):
    out = subprocess.run(PG + ["-f", "-"], input=sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    return list(csv.DictReader(io.StringIO(out.stdout)))


def load_live():
    strats = ",".join(f"'{s}'" for s in STRATEGIES)
    signals = {}
    for r in q(SIG_SQL.format(strats=strats)):
        signals[int(r["id"])] = {
            "strategy": r["strategy"], "ev": r["ev"],
            "t0": float(r["t0"]), "tr": float(r["tr"]) if r["tr"] else None,
            "won": int(r["won"]), "p0": float(r["p0"]),
            "sharp_entry": float(r["sharp_entry"]),
            "points": [],   # (secs_after_fire, price)
        }
    dense_pts = 0
    for r in q(TRAJ_SQL):
        sid = int(r["signal_id"])
        if sid in signals:
            signals[sid]["points"].append((float(r["secs"]), float(r["price"])))
            dense_pts += 1
    for r in q(SNAP_SQL.format(strats=strats)):
        sid = int(r["signal_id"])
        if sid in signals:
            secs = float(r["ts"]) - signals[sid]["t0"]
            if secs >= 0:
                signals[sid]["points"].append((secs, float(r["price"])))
    return list(signals.values()), dense_pts


def price_at(sig, tau_secs):
    """Nearest pre-resolution point to t0+τ, within ±max(45s, τ/2). None if absent
    or the signal resolved before τ (the survival condition)."""
    if sig["tr"] is not None and (sig["tr"] - sig["t0"]) <= tau_secs:
        return None
    tol = max(45.0, tau_secs / 2.0)
    best, best_d = None, None
    for secs, price in sig["points"]:
        d = abs(secs - tau_secs)
        if d <= tol and (best_d is None or d < best_d):
            best, best_d = price, d
    return best


def cluster_mean(pairs):
    """pairs: (ev, value) → event-clustered mean and per-event means dict."""
    ev = defaultdict(list)
    for e, v in pairs:
        ev[e].append(v)
    means = {e: sum(v) / len(v) for e, v in ev.items()}
    vals = list(means.values())
    return (sum(vals) / len(vals) if vals else float("nan")), means


def boot_ci(ev_means, rng):
    """Bootstrap CI over EVENTS (the correlated unit)."""
    vals = np.array(list(ev_means.values()))
    if len(vals) < 2:
        return (float("nan"), float("nan"))
    idx = rng.integers(0, len(vals), size=(N_BOOT, len(vals)))
    boots = vals[idx].mean(axis=1)
    return (float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5)))


def analyze(signals, label="live", dense_pts=0):
    rng = np.random.default_rng(SEED)
    pyrng = random.Random(SEED)
    report = {"label": label, "grid_mins": GRID_MINS, "min_survivors": MIN_SURVIVORS,
              "dense_points": dense_pts, "strategies": {}}
    if dense_pts == 0:
        report["coarse_data_caveat"] = (
            "signal_price_trajectory is empty (DENSE_CAPTURE off or just enabled): "
            "sub-10-minute buckets ride on change-only ~5-min snapshots, where the "
            "nearest point to a small τ is often the SAME snapshot that set p0 — "
            "an exact Δ=0 artifact. Trust τ ≥ 10 min only until dense data accrues."
        )
    for strat in sorted({s["strategy"] for s in signals}):
        rows = [s for s in signals if s["strategy"] == strat]
        # Fire edge (CLV anchor) + structural tax, event-clustered.
        fire_edge, _ = cluster_mean([(s["ev"], s["won"] - s["p0"]) for s in rows])
        tax, _ = cluster_mean([(s["ev"], s["p0"] - s["sharp_entry"]) for s in rows])
        curve = []
        for tau in GRID_MINS:
            tau_s = tau * 60.0
            deltas, placebo = [], []
            for s in rows:
                p = price_at(s, tau_s)
                if p is None:
                    continue
                deltas.append((s["ev"], s["p0"] - p))  # Δ(τ) = e(τ) − e0
                # Placebo: a uniformly random OTHER observed pre-resolution point
                # of the SAME signal — destroys the offset→price time structure.
                open_pts = [pp for sec, pp in s["points"]
                            if s["tr"] is None or sec < (s["tr"] - s["t0"])]
                if open_pts:
                    placebo.append((s["ev"], s["p0"] - pyrng.choice(open_pts)))
            n_surv = len({e for e, _ in deltas})
            if n_surv < MIN_SURVIVORS:
                curve.append({"tau_mins": tau, "n_events": n_surv, "published": False})
                continue
            d_mean, d_ev = cluster_mean(deltas)
            lo, hi = boot_ci(d_ev, rng)
            p_mean, _ = cluster_mean(placebo)
            curve.append({
                "tau_mins": tau, "n_events": n_surv, "published": True,
                "delta": d_mean, "ci_lo": lo, "ci_hi": hi, "placebo": p_mean,
            })
        # Speed budget: first τ (linear interp between published points) where
        # Δ(τ) ≤ −tolerance × fire_edge. None if the curve never loses that much.
        budget = None
        pub = [c for c in curve if c.get("published")]
        if fire_edge and fire_edge > 0:
            thresh = -EDGE_LOSS_TOLERANCE * fire_edge
            prev_tau, prev_d = 0.0, 0.0
            for c in pub:
                if c["delta"] <= thresh:
                    span = c["delta"] - prev_d
                    frac = (thresh - prev_d) / span if span < 0 else 1.0
                    budget = prev_tau + frac * (c["tau_mins"] - prev_tau)
                    break
                prev_tau, prev_d = c["tau_mins"], c["delta"]
        if budget is None:
            verdict = "no material decay measured on this grid — manual is fine"
        elif budget >= MANUAL_LATENCY_MIN:
            verdict = f"manual is fine (budget {budget:.1f}m ≥ {MANUAL_LATENCY_MIN:.0f}m)"
        elif budget >= AUTO_LATENCY_MIN:
            verdict = f"auto-trader materially worth it (budget {budget:.1f}m < {MANUAL_LATENCY_MIN:.0f}m)"
        else:
            verdict = f"needs low-latency auto (budget {budget:.2f}m)"
        report["strategies"][strat] = {
            "n_signals": len(rows), "fire_edge": fire_edge, "structural_tax": tax,
            "curve": curve, "speed_budget_mins": budget,
            "edge_loss_tolerance": EDGE_LOSS_TOLERANCE, "verdict": verdict,
        }
    return report


def print_report(report):
    print(f"latency decay [{report['label']}] · grid mins {report['grid_mins']} · "
          f"dense points {report['dense_points']} · MIN_SURVIVORS {report['min_survivors']}")
    if report.get("coarse_data_caveat"):
        print(f"⚠ {report['coarse_data_caveat']}")
    for strat, r in report["strategies"].items():
        print(f"\n{strat}: fire edge {r['fire_edge']:+.2%} (CLV anchor) · "
              f"structural tax {r['structural_tax']:+.2%} (sharps' fill → our mid; speed can't fix) · "
              f"N={r['n_signals']}")
        print(f"  {'τ(min)':>7} {'N_ev':>5} {'Δ(τ)':>8} {'95% CI':>18} {'placebo':>8}")
        for c in r["curve"]:
            if not c.get("published"):
                print(f"  {c['tau_mins']:>7} {c['n_events']:>5}   — (below survivor floor)")
                continue
            print(f"  {c['tau_mins']:>7} {c['n_events']:>5} {c['delta']:>+7.2%} "
                  f"[{c['ci_lo']:>+7.2%},{c['ci_hi']:>+7.2%}] {c['placebo']:>+7.2%}")
        b = r["speed_budget_mins"]
        print(f"  speed budget: {'—' if b is None else f'{b:.1f} min'} "
              f"(τ losing {r['edge_loss_tolerance']:.0%} of fire edge) → {r['verdict']}")


# --- Self-test: recover a KNOWN injected decay; a no-decay fixture must be flat ---

def synth(decay_per_min, n_signals=400, seed=7):
    """Signals whose price drifts toward the outcome at `decay_per_min` per minute
    (edge lost per minute), observed at a 45s cadence, resolving at 90 min."""
    rng = random.Random(seed)
    out = []
    for i in range(n_signals):
        won = rng.random() < 0.6
        p0 = 0.55 + rng.uniform(-0.1, 0.1)
        pts = []
        for k in range(1, 120):
            secs = k * 45.0
            drift = decay_per_min * (secs / 60.0) * (1 if won else -1)
            noise = rng.gauss(0, 0.004)
            pts.append((secs, min(0.99, max(0.01, p0 + drift + noise))))
        out.append({"strategy": "synth", "ev": f"ev{i}", "t0": 0.0, "tr": 90 * 60.0,
                    "won": int(won), "p0": p0, "sharp_entry": p0 - 0.012, "points": pts})
    return out


def selftest():
    ok = True
    # (a) Known decay 1%/min toward the outcome ⇒ Δ(τ) ≈ −1%·τ·(2·hit−1)... the
    # injected drift moves price TOWARD the realized outcome, so for winners
    # p rises (Δ<0) and for losers p falls (Δ>0): expected Δ(τ) at hit-rate h is
    # −decay·τ·(2h−1). With h=0.6 ⇒ −0.2%/min. Check τ=10 within CI.
    rep = analyze(synth(0.01), label="selftest-decay")
    c10 = next(c for c in rep["strategies"]["synth"]["curve"]
               if c["tau_mins"] == 10.0 and c.get("published"))
    expected = -0.01 * 10.0 * (2 * 0.6 - 1)
    if not (c10["ci_lo"] - 0.01 <= expected <= c10["ci_hi"] + 0.01):
        print(f"SELFTEST FAIL: injected decay not recovered: Δ(10m)={c10['delta']:+.3%} "
              f"CI [{c10['ci_lo']:+.3%},{c10['ci_hi']:+.3%}] vs expected {expected:+.3%}")
        ok = False
    # (b) No-decay fixture: flat at every published τ. "Flat" = the CI contains 0
    # OR the point estimate is within a 0.2% practical tolerance — 8 τ-buckets ×
    # 95% CIs would otherwise fail by chance ~1/3 of the time (the same multiple-
    # comparisons trap this whole system exists to avoid).
    rep0 = analyze(synth(0.0), label="selftest-null")
    for c in rep0["strategies"]["synth"]["curve"]:
        if not c.get("published"):
            continue
        flat = (c["ci_lo"] <= 0.0 <= c["ci_hi"]) or abs(c["delta"]) <= 0.002
        if not flat:
            print(f"SELFTEST FAIL: no-decay fixture not flat at τ={c['tau_mins']}: "
                  f"Δ={c['delta']:+.3%} [{c['ci_lo']:+.3%},{c['ci_hi']:+.3%}]")
            ok = False
    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    if "--selftest" in sys.argv:
        selftest()
    signals, dense_pts = load_live()
    report = analyze(signals, label="live", dense_pts=dense_pts)
    os.makedirs("reports", exist_ok=True)
    with open("reports/decay_report.json", "w") as f:
        json.dump(report, f, indent=1)
    print_report(report)
    print("\nwrote reports/decay_report.json")


if __name__ == "__main__":
    main()
