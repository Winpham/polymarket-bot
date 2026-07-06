#!/usr/bin/env python3
"""
CLV / λ INSTRUMENT — turn the favorite edge δ from an ASSUMPTION into a MEASUREMENT.

Every profit number this project has produced is conditional on λ — how much of the measured
favorite surplus (δ = realized_WR − price ≈ +0.11) is REAL information versus favorite-longshot
bias. Four benign World-Cup days cannot separate λ=1 from λ=0.25 from λ=0 because the separating
event (an adverse correlated day) has not occurred. CLOSING-LINE-VALUE is the one independent,
PRE-resolution read on λ: if our at-fire entries reliably beat the market's CLOSING price (the line
moves our way), that is evidence the edge is information the market later confirmed, not luck or a
static bias. This script MEASURES that.

Three pre-registered questions, each with a null (DECISIONS.md, EDGE-TRUTH-AND-LEVERS-PROMPT.md):
  (1) Is CLV > 0 on favorites?   — event-clustered mean CLV vs a SELECTION-MATCHED null
      (band×UTC-day-matched random draws from the `_blind` universe; reuse selection_null.py).
      Positive & p≤0.01 ⇒ the line reliably moves our way ⇒ independent evidence δ is real.
  (2) Does CLV EXPLAIN the surplus?  — decompose realized surplus (won − entry) into a
      CLV-explained component (close − entry, value the market later confirmed) and a residual
      (won − close, luck/variance). High CLV-explained fraction ⇒ λ closer to 1.
  (3) Data-driven λ̂.  — λ̂ = clip(mean_CLV / δ, 0, 1), with a block/selection-bootstrap CI.
      Reported with its honest (WIDE on this record) CI. The width IS the finding.

CLV DEFINITION (frozen):
  entry = initial_mean_price (at-fire, D6).
  close = the LAST trajectory `mid` at/before `resolved_at` with mid ∈ [0.02, 0.98] — the
          degenerate-price GUARD: once the result is effectively known the price prints to 0/1;
          that is hindsight, not value, and is excluded. Fall back to mean_price ONLY when the
          trajectory is empty for a signal, and FLAG the fallback rate (a high rate is a
          data-quality caveat, not a result).
  CLV = close − entry  (a back).

KILL CRITERIA (report honestly; a negative IS the deliverable — do NOT launder it):
  K1  trajectory coverage < ~50% ⇒ CLV is fallback-dominated ⇒ INDETERMINATE-BY-DATA, not a λ.
  K2  CLV null p > 0.01 ⇒ no CLV evidence the edge is real ⇒ say so plainly.
  K3  the degenerate post-resolution price MUST be excluded (proven in --selftest).

Usage:
  ./clv_lambda.py                 # measure on the live record; writes reports/clv_lambda.json
  ./clv_lambda.py --selftest      # synthetic fixtures: degenerate-guard + positive-CLV recovery
  ./clv_lambda.py --strategy favorite --draws 2000 --seed 20260703
"""

import argparse
import csv
import io
import json
import os
import random
import subprocess
import sys
from collections import defaultdict
from math import sqrt
from statistics import NormalDist

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]
GUARD_LO, GUARD_HI = 0.02, 0.98        # degenerate-price guard (K3)
DEFAULT_DRAWS = 2000
DEFAULT_SEED = 20260703
P_BAR = 0.01
COVERAGE_BAR = 0.50                     # K1

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")

SIG_SQL = """
SELECT id, strategy,
       COALESCE(event_slug, condition_id) AS ev,
       event_slug,
       initial_mean_price AS entry,
       mean_price         AS mean_price,
       last_market_price  AS last_mkt,
       (outcome_won::int)  AS won,
       to_char(COALESCE(first_detected_at, resolved_at) AT TIME ZONE 'UTC', 'YYYY-MM-DD') AS day,
       resolved_at
FROM consensus_signals
WHERE resolved AND initial_mean_price IS NOT NULL
"""

# Trajectory close: latest non-degenerate mid at/before resolved_at, per signal.
TRAJ_SQL = """
SELECT t.signal_id, t.mid
FROM signal_price_trajectory t
JOIN consensus_signals s ON s.id = t.signal_id
WHERE t.mid IS NOT NULL
  AND t.mid BETWEEN {lo} AND {hi}
  AND (s.resolved_at IS NULL OR t.ts <= s.resolved_at)
  AND t.ts = (
      SELECT MAX(t2.ts) FROM signal_price_trajectory t2
      WHERE t2.signal_id = t.signal_id
        AND t2.mid BETWEEN {lo} AND {hi}
        AND (s.resolved_at IS NULL OR t2.ts <= s.resolved_at)
  )
""".format(lo=GUARD_LO, hi=GUARD_HI)

# Cycle-5 T1 — MARKET-KEY join (Cycle-2 dense-capture fix, read-side): the CLV close is a MARKET
# property, so a sibling-anchored trajectory on the SAME (condition_id,outcome_index) is a valid
# close for the favorite that DISTINCT-ON crowded out. For each resolved signal, take the latest
# non-degenerate mid from ANY signal sharing the market, at/before that signal's own resolved_at.
# Recovers the sibling-keyed coverage clv_lambda's signal_id join misses (1.2% -> ~15% on favorites).
MARKET_KEY_TRAJ_SQL = """
WITH cap AS (
  SELECT s.condition_id, s.outcome_index, t.ts, t.mid
  FROM signal_price_trajectory t JOIN consensus_signals s ON s.id = t.signal_id
  WHERE t.mid IS NOT NULL AND t.mid BETWEEN {lo} AND {hi})
SELECT f.id AS signal_id, (
  SELECT c.mid FROM cap c
  WHERE c.condition_id = f.condition_id AND c.outcome_index = f.outcome_index
    AND (f.resolved_at IS NULL OR c.ts <= f.resolved_at)
  ORDER BY c.ts DESC LIMIT 1) AS mid
FROM consensus_signals f
WHERE f.resolved AND f.initial_mean_price IS NOT NULL
  AND EXISTS (SELECT 1 FROM cap c WHERE c.condition_id = f.condition_id
              AND c.outcome_index = f.outcome_index)
""".format(lo=GUARD_LO, hi=GUARD_HI)


def q(sql):
    out = subprocess.run(PG + ["-f", "-"], input=sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    return list(csv.DictReader(io.StringIO(out.stdout)))


def band(p):  # mirror of width_bucket(p,0,1,5)
    if p < 0.0:
        return 0
    if p >= 1.0:
        return 6
    return int(p * 5.0) + 1


def fetch(market_key=False):
    sig = q(SIG_SQL)
    traj_sql = MARKET_KEY_TRAJ_SQL if market_key else TRAJ_SQL
    traj = {r["signal_id"]: float(r["mid"]) for r in q(traj_sql) if r["mid"] not in (None, "")}
    rows = []
    for r in sig:
        entry = float(r["entry"])
        traj_close = traj.get(r["id"])
        rows.append({
            "id": r["id"], "strategy": r["strategy"], "ev": r["ev"],
            "event_slug": r["event_slug"], "entry": entry, "won": int(r["won"]),
            "day": r["day"],
            "mean_price": float(r["mean_price"]) if r["mean_price"] not in (None, "") else None,
            "traj_close": traj_close,
        })
    return rows


def assign_close(row):
    """Returns (close, used_fallback). Trajectory when present (already degenerate-guarded);
    else the mean_price proxy (flagged). None if neither is usable/non-degenerate."""
    if row["traj_close"] is not None:
        return row["traj_close"], False
    mp = row["mean_price"]
    if mp is not None and GUARD_LO <= mp <= GUARD_HI:
        return mp, True
    return None, True


# ---- event-clustered helpers (mirror selection_null.py) --------------------------------------
def clustered_mean(pairs):
    """pairs: iterable of (ev, value) -> (event-clustered mean, n_events)."""
    ev_map = defaultdict(list)
    for ev, v in pairs:
        ev_map[ev].append(v)
    if not ev_map:
        return float("nan"), 0
    means = [sum(v) / len(v) for v in ev_map.values()]
    return sum(means) / len(means), len(means)


def block_bootstrap_ci(events, stat_fn, rng, n=2000, alpha=0.05):
    """Resample event clusters with replacement; stat_fn(list_of_event_keys)->float."""
    keys = list(events.keys())
    if not keys:
        return (float("nan"), float("nan"))
    draws = []
    for _ in range(n):
        sample = [keys[rng.randrange(len(keys))] for _ in keys]
        v = stat_fn(sample)
        if v == v:  # not nan
            draws.append(v)
    draws.sort()
    if not draws:
        return (float("nan"), float("nan"))
    lo = draws[int(alpha / 2 * len(draws))]
    hi = draws[int((1 - alpha / 2) * len(draws)) - 1]
    return lo, hi


def selection_null(picks_meta, blind_cells, rng, n_perm):
    """picks_meta: list of (band, day). Draw band×day-matched random selections from `_blind`
    (blind_cells: (band,day)->[(ev, clv)]) and return their event-clustered mean CLVs."""
    profile = defaultdict(int)
    for cell in picks_meta:
        profile[cell] += 1
    draws = []
    for _ in range(n_perm):
        sel, ok = [], True
        for cell, k in profile.items():
            pool = blind_cells.get(cell)
            if not pool:
                ok = False
                break
            take = rng.choices(pool, k=k) if k > len(pool) else rng.sample(pool, k)
            sel.extend(take)
        if not ok:
            continue
        m, _ = clustered_mean(sel)
        draws.append(m)
    return draws


def measure(strategy, draws, seed, market_key=False):
    rows = fetch(market_key=market_key)
    rng = random.Random(seed)

    # blind CLV universe for the selection-matched null
    blind_cells = defaultdict(list)   # (band, day) -> [(ev, clv)]
    for r in rows:
        if r["strategy"] != "_blind":
            continue
        close, _ = assign_close(r)
        if close is None:
            continue
        blind_cells[(band(r["entry"]), r["day"])].append((r["ev"], close - r["entry"]))

    srows = [r for r in rows if r["strategy"] == strategy]
    n_total = len(srows)
    usable, n_traj, n_fallback, n_unusable = [], 0, 0, 0
    for r in srows:
        close, fb = assign_close(r)
        if close is None:
            n_unusable += 1
            continue
        if fb:
            n_fallback += 1
        else:
            n_traj += 1
        r["close"] = close
        r["clv"] = close - r["entry"]
        r["surplus"] = r["won"] - r["entry"]
        r["resid"] = r["won"] - close
        usable.append(r)

    coverage = (n_traj / n_total) if n_total else 0.0     # TRUE trajectory coverage (K1)
    usable_frac = (len(usable) / n_total) if n_total else 0.0

    # per-event maps for clustered stats + bootstrap
    ev_clv = defaultdict(list)
    ev_surplus = defaultdict(list)
    for r in usable:
        ev_clv[r["ev"]].append(r["clv"])
        ev_surplus[r["ev"]].append(r["surplus"])
    events = {ev: (sum(ev_clv[ev]) / len(ev_clv[ev]),
                   sum(ev_surplus[ev]) / len(ev_surplus[ev])) for ev in ev_clv}

    mean_clv, n_ev = clustered_mean([(r["ev"], r["clv"]) for r in usable])
    mean_surplus, _ = clustered_mean([(r["ev"], r["surplus"]) for r in usable])
    mean_resid, _ = clustered_mean([(r["ev"], r["resid"]) for r in usable])

    # Q1: selection-matched null on CLV
    meta = [(band(r["entry"]), r["day"]) for r in usable]
    null_draws = selection_null(meta, blind_cells, rng, draws)
    if len(null_draws) >= 1000:
        mu = sum(null_draws) / len(null_draws)
        sd = sqrt(sum((x - mu) ** 2 for x in null_draws) / (len(null_draws) - 1))
        z = (mean_clv - mu) / sd if sd > 0 else float("nan")
        p_emp = sum(1 for x in null_draws if x >= mean_clv) / len(null_draws)
    else:
        mu = sd = z = p_emp = float("nan")

    # bootstrap CIs (event-clustered)
    def clv_of(keys):
        return sum(events[k][0] for k in keys) / len(keys)

    def lam_of(keys):
        c = sum(events[k][0] for k in keys) / len(keys)
        d = sum(events[k][1] for k in keys) / len(keys)
        return max(0.0, min(1.0, c / d)) if d > 0 else float("nan")

    clv_lo, clv_hi = block_bootstrap_ci(events, clv_of, rng, n=draws)
    # absolute one-sample p that mean CLV>0 (event-clustered), for context alongside the null
    clv_z = mean_clv / ((clv_hi - clv_lo) / (2 * 1.96)) if clv_hi > clv_lo else float("nan")

    # Q2 / Q3
    explained_frac = (mean_clv / mean_surplus) if mean_surplus not in (0, float("nan")) else float("nan")
    lam_hat = max(0.0, min(1.0, mean_clv / mean_surplus)) if mean_surplus > 0 else float("nan")
    lam_lo, lam_hi = block_bootstrap_ci(events, lam_of, rng, n=draws)

    return {
        "strategy": strategy, "join": "market_key" if market_key else "signal_id",
        "n_total": n_total, "n_events": n_ev,
        "n_traj": n_traj, "n_fallback": n_fallback, "n_unusable": n_unusable,
        "trajectory_coverage": coverage, "usable_frac": usable_frac,
        "mean_clv": mean_clv, "clv_ci": [clv_lo, clv_hi], "clv_z_approx": clv_z,
        "mean_surplus_delta": mean_surplus, "mean_resid": mean_resid,
        "null_mu": mu, "null_sd": sd, "null_z": z, "null_p": p_emp, "null_draws": len(null_draws),
        "clv_explained_frac": explained_frac,
        "lambda_hat": lam_hat, "lambda_ci": [lam_lo, lam_hi],
    }


def verdict(res):
    cov = res["trajectory_coverage"]
    if cov < COVERAGE_BAR:
        headline = ("INDETERMINATE-BY-DATA (K1): trajectory coverage "
                    f"{cov:.0%} < {COVERAGE_BAR:.0%} — CLV is fallback-dominated. "
                    "The mean_price proxy below is a WEAK, single-snapshot read, NOT a certified λ.")
    elif res["null_p"] != res["null_p"] or res["null_p"] > P_BAR:
        headline = (f"NO CLV EVIDENCE (K2): selection-null p={res['null_p']:.3f} > {P_BAR} — "
                    "the line does not reliably move our way beyond composition. λ not supported > 0.")
    else:
        headline = (f"CLV-POSITIVE (p={res['null_p']:.3f} ≤ {P_BAR}): independent evidence the edge "
                    f"is real; λ̂={res['lambda_hat']:.2f}. NOT the D7 gate — persistence still governs.")
    return headline


def print_report(res):
    print("=" * 78)
    print(f"CLV / λ instrument · strategy={res['strategy']} · "
          f"{res['n_total']} positions / {res['n_events']} events")
    print("=" * 78)
    print(f"trajectory coverage: {res['trajectory_coverage']:.1%}  "
          f"(traj={res['n_traj']}  proxy-fallback={res['n_fallback']}  unusable={res['n_unusable']})")
    print(f"                     usable positions: {res['usable_frac']:.1%}")
    print("-" * 78)
    print("Q1  mean CLV (close − entry), event-clustered:")
    print(f"      mean_CLV = {res['mean_clv']:+.4f}  95% CI [{res['clv_ci'][0]:+.4f}, {res['clv_ci'][1]:+.4f}]")
    print(f"      selection-matched null: μ={res['null_mu']:+.4f} σ={res['null_sd']:.4f} "
          f"z={res['null_z']:+.2f} p={res['null_p']:.4f}  ({res['null_draws']} draws)")
    print("Q2  surplus decomposition:")
    print(f"      realized surplus δ = {res['mean_surplus_delta']:+.4f}")
    print(f"      CLV-explained      = {res['mean_clv']:+.4f}  ({res['clv_explained_frac']:.1%} of δ)")
    print(f"      residual (won−close)= {res['mean_resid']:+.4f}  (luck/variance/static-bias)")
    print("Q3  data-driven λ̂ (clip(mean_CLV/δ, 0, 1)):")
    print(f"      λ̂ = {res['lambda_hat']:.3f}  95% CI [{res['lambda_ci'][0]:.3f}, {res['lambda_ci'][1]:.3f}]")
    print("-" * 78)
    print("VERDICT: " + verdict(res))
    print("=" * 78)


# ---- self-test (K3 degenerate guard + positive-CLV recovery; no DB) --------------------------
def selftest():
    ok = True

    # Fixture 1 — degenerate-price guard: entry 0.80, trajectory rises to 0.82 pre-resolution,
    # then prints 0.99 AT resolution. The close MUST be 0.82 (CLV +0.02), NEVER 0.99 (+0.19).
    mids_all = [0.80, 0.81, 0.82, 0.99]
    non_degen = [m for m in mids_all if GUARD_LO <= m <= GUARD_HI]
    close = non_degen[-1]
    clv = close - 0.80
    if abs(clv - 0.02) > 1e-9:
        print(f"  FAIL degenerate-guard: close={close} clv={clv:+.4f} (expected +0.0200)")
        ok = False
    else:
        print(f"  PASS degenerate-guard: 0.99 excluded → close=0.82 clv={clv:+.4f}")

    # Fixture 2 — positive-CLV recovery: a clean +CLV signal is recovered and its λ read is sane.
    rows = [
        {"ev": f"e{i}", "entry": 0.70, "won": 1, "traj_close": 0.78, "mean_price": 0.78}
        for i in range(20)
    ]
    for r in rows:
        r["close"], _ = assign_close(r) if False else (r["traj_close"], False)
        r["clv"] = r["close"] - r["entry"]
        r["surplus"] = r["won"] - r["entry"]
    mclv, nev = clustered_mean([(r["ev"], r["clv"]) for r in rows])
    msur, _ = clustered_mean([(r["ev"], r["surplus"]) for r in rows])
    lam = max(0.0, min(1.0, mclv / msur))
    if abs(mclv - 0.08) > 1e-9 or nev != 20:
        print(f"  FAIL positive-CLV recovery: mean_clv={mclv:+.4f} nev={nev} (expected +0.0800 / 20)")
        ok = False
    else:
        print(f"  PASS positive-CLV recovery: mean_clv={mclv:+.4f} λ̂={lam:.3f} over {nev} events")

    # Fixture 3 — assign_close prefers trajectory over proxy, and rejects a degenerate proxy.
    a, fb = assign_close({"traj_close": 0.55, "mean_price": 0.99})
    b, fb2 = assign_close({"traj_close": None, "mean_price": 0.99})   # degenerate proxy → unusable
    c, fb3 = assign_close({"traj_close": None, "mean_price": 0.60})   # usable proxy (flagged)
    if not (a == 0.55 and fb is False and b is None and c == 0.60 and fb3 is True):
        print(f"  FAIL assign_close routing: a={a},{fb} b={b},{fb2} c={c},{fb3}")
        ok = False
    else:
        print("  PASS assign_close routing: traj>proxy, degenerate-proxy rejected, proxy flagged")

    print("SELFTEST: " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", default="favorite")
    ap.add_argument("--draws", type=int, default=DEFAULT_DRAWS)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--market-key-join", action="store_true",
                    help="Cycle-5 T1: join trajectory by (condition_id,outcome_index) not signal_id "
                         "(recovers sibling-crowded coverage). DEFERRED as default (changes a gate input).")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(selftest())

    res = measure(args.strategy, args.draws, args.seed, market_key=args.market_key_join)
    print_report(res)
    res["verdict"] = verdict(res)
    os.makedirs(REPORT_DIR, exist_ok=True)
    suffix = "_marketkey" if args.market_key_join else ""
    path = os.path.join(REPORT_DIR, f"clv_lambda{suffix}.json")
    with open(path, "w") as f:
        json.dump(res, f, indent=2)
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
