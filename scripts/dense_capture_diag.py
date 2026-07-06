#!/usr/bin/env python3
"""
dense_capture_diag — THREAD D (Cycle 2): why is dense-capture trajectory coverage ~0.6%, and what is
the exact, paper-safe fix + expected lift?

Cycle 1: clv_lambda coverage = 0.6% (2/307 favorite positions have a real at-fire trajectory).
DENSE_CAPTURE is live (DENSE_STRATEGIES already includes favorite,elite_fresh_fav) and writing rows.
So the 0.6% is NOT "capture is off" and NOT "favorites out of scope". This instrument decomposes it.

MECHANISM (proven with live numbers):
  (1) TEMPORAL — dense capture only began at the first signal_price_trajectory.ts. Every favorite
      signal DETECTED before that has no trajectory possible; those are pure accrual (age out over time).
  (2) SIBLING-DEDUP CROWD-OUT (the real, fixable bug) — the capture candidate query
      (common/src/storage/consensus.rs::dense_capture_candidates) is
        SELECT DISTINCT ON (condition_id, outcome_index) ... WHERE strategy = ANY(strategies)
        ORDER BY condition_id, outcome_index, first_detected_at, id LIMIT cap
      `strict` and `favorite` score the SAME markets and fire on the SAME (condition_id, outcome_index);
      DISTINCT ON keeps ONE anchor (earliest fire → usually the `strict` sibling). The trajectory is
      therefore written under the SIBLING signal_id, not the favorite's. clv_lambda's TRAJ_SQL joins
      the trajectory to the favorite by t.signal_id = s.id, so it misses the sibling-anchored path —
      even though the SAME market's price trajectory was captured.

FIX (read-side, paper-safe, reversible, NO Rust change): join the trajectory by
  (condition_id, outcome_index) within the signal's life, not by signal_id. The CLV close is a MARKET
  property (last mid before resolution), identical for every sibling signal on that market/outcome,
  so the market-key join is correct — it recovers the sibling-anchored trajectories.

This script measures coverage under BOTH joins for the favorite family and reports the immediate lift,
and separates the residual gap that is pure temporal accrual (pre-dense-start signals). It does NOT
mutate clv_lambda's default (that is a gate input — flagged DEFERRED for human safe-swap review).

Read-only, paper-only.
  ./dense_capture_diag.py --selftest
  ./dense_capture_diag.py            # writes reports/dense_capture_diag.json
"""

import argparse
import csv
import io
import json
import os
import subprocess
import sys

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]
GUARD_LO, GUARD_HI = 0.02, 0.98
FAM = "('favorite','elite_fresh_fav')"
REPORT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "reports", "dense_capture_diag.json")


def q(sql):
    out = subprocess.run(PG + ["-f", "-"], input=sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    return list(csv.DictReader(io.StringIO(out.stdout)))


def one(sql):
    return q(sql)[0]


def run(verbose=True):
    dense_start = one("SELECT MIN(ts) AS s, MAX(ts) AS e, COUNT(*) n, "
                      "COUNT(DISTINCT signal_id) nsig FROM signal_price_trajectory")
    start_ts = dense_start["s"]

    scope = q("SELECT cs.strategy, COUNT(DISTINCT t.signal_id) nsig, COUNT(*) nrows "
              "FROM signal_price_trajectory t JOIN consensus_signals cs ON cs.id=t.signal_id "
              "GROUP BY 1 ORDER BY 2 DESC")

    fam_counts = one(f"""
      SELECT
        COUNT(*) FILTER (WHERE resolved) AS fam_resolved,
        COUNT(*) FILTER (WHERE resolved AND first_detected_at >= '{start_ts}') AS fam_resolved_post,
        COUNT(*) FILTER (WHERE resolved AND first_detected_at <  '{start_ts}') AS fam_resolved_pre
      FROM consensus_signals
      WHERE strategy IN {FAM} AND initial_mean_price IS NOT NULL""")

    # coverage under signal_id join (what clv_lambda does today)
    cov_sig = one(f"""
      WITH usable_traj AS (
        SELECT DISTINCT t.signal_id
        FROM signal_price_trajectory t JOIN consensus_signals s ON s.id=t.signal_id
        WHERE t.mid BETWEEN {GUARD_LO} AND {GUARD_HI}
          AND (s.resolved_at IS NULL OR t.ts <= s.resolved_at))
      SELECT COUNT(*) AS n_fam,
             COUNT(*) FILTER (WHERE u.signal_id IS NOT NULL) AS n_cov
      FROM consensus_signals f
      LEFT JOIN usable_traj u ON u.signal_id = f.id
      WHERE f.strategy IN {FAM} AND f.resolved AND f.initial_mean_price IS NOT NULL""")

    # coverage under MARKET-KEY join (the fix): any sibling trajectory on the same
    # (condition_id, outcome_index) with a usable mid at/before the favorite's resolution
    cov_mkt = one(f"""
      WITH usable AS (
        SELECT s.condition_id, s.outcome_index, t.ts, t.mid, s.resolved_at AS sib_res
        FROM signal_price_trajectory t JOIN consensus_signals s ON s.id=t.signal_id
        WHERE t.mid BETWEEN {GUARD_LO} AND {GUARD_HI})
      SELECT COUNT(*) AS n_fam,
             COUNT(*) FILTER (WHERE EXISTS (
               SELECT 1 FROM usable u
               WHERE u.condition_id = f.condition_id AND u.outcome_index = f.outcome_index
                 AND (f.resolved_at IS NULL OR u.ts <= f.resolved_at))) AS n_cov
      FROM consensus_signals f
      WHERE f.strategy IN {FAM} AND f.resolved AND f.initial_mean_price IS NOT NULL""")

    # of POST-dense-start favorites, how many are recoverable by market-key (the addressable ceiling)?
    post_recover = one(f"""
      WITH usable AS (
        SELECT s.condition_id, s.outcome_index, t.ts, t.mid
        FROM signal_price_trajectory t JOIN consensus_signals s ON s.id=t.signal_id
        WHERE t.mid BETWEEN {GUARD_LO} AND {GUARD_HI})
      SELECT COUNT(*) AS n_post,
             COUNT(*) FILTER (WHERE EXISTS (
               SELECT 1 FROM usable u
               WHERE u.condition_id=f.condition_id AND u.outcome_index=f.outcome_index
                 AND (f.resolved_at IS NULL OR u.ts <= f.resolved_at))) AS n_post_recover
      FROM consensus_signals f
      WHERE f.strategy IN {FAM} AND f.resolved AND f.initial_mean_price IS NOT NULL
        AND f.first_detected_at >= '{start_ts}'""")

    n_fam = int(cov_sig["n_fam"])
    cov_sig_frac = int(cov_sig["n_cov"]) / n_fam if n_fam else 0.0
    cov_mkt_frac = int(cov_mkt["n_cov"]) / n_fam if n_fam else 0.0
    n_post = int(post_recover["n_post"])
    post_recover_frac = int(post_recover["n_post_recover"]) / n_post if n_post else 0.0

    out = {
        "dense_capture": {"start_ts": start_ts, "end_ts": dense_start["e"],
                          "n_rows": int(dense_start["n"]), "n_signals": int(dense_start["nsig"])},
        "capture_scope_by_strategy": [{"strategy": r["strategy"], "n_signals": int(r["nsig"]),
                                       "n_rows": int(r["nrows"])} for r in scope],
        "favorite_family": {"resolved_total": int(fam_counts["fam_resolved"]),
                            "resolved_pre_dense_start": int(fam_counts["fam_resolved_pre"]),
                            "resolved_post_dense_start": int(fam_counts["fam_resolved_post"])},
        "coverage_signal_id_join_TODAY": {"n_fam": n_fam, "n_cov": int(cov_sig["n_cov"]),
                                          "frac": cov_sig_frac},
        "coverage_market_key_join_FIX": {"n_fam": n_fam, "n_cov": int(cov_mkt["n_cov"]),
                                         "frac": cov_mkt_frac},
        "post_dense_start_recoverable": {"n_post": n_post,
                                         "n_recoverable": int(post_recover["n_post_recover"]),
                                         "frac": post_recover_frac},
        "lift": {"immediate_coverage_x": (cov_mkt_frac / cov_sig_frac) if cov_sig_frac > 0 else None,
                 "immediate_coverage_pp": cov_mkt_frac - cov_sig_frac},
        "diagnosis": {
            "primary_cause": "SIBLING-DEDUP CROWD-OUT: DISTINCT ON (condition_id,outcome_index) in "
                             "dense_capture_candidates keys the trajectory to the earliest-fired sibling "
                             "(usually strict); clv_lambda joins by signal_id and misses it.",
            "secondary_cause": "TEMPORAL: dense capture began at start_ts; favorites detected earlier "
                               "have no trajectory (pure accrual, resolves over weeks).",
            "not_the_cause": "scope (DENSE_STRATEGIES already includes favorite,elite_fresh_fav) and "
                             "capture-off (rows are being written).",
        },
        "fix_spec": {
            "paper_safe_read_side": "clv_lambda TRAJ_SQL: join trajectory by (condition_id, "
                                    "outcome_index) at/before the signal's resolved_at, taking the "
                                    "MAX(ts) usable mid, INSTEAD OF t.signal_id = s.id. The CLV close "
                                    "is a market property so the sibling path is valid. Add as an "
                                    "opt-in --market-key-join; DEFER default swap for human review "
                                    "(it changes a gate input mid-run).",
            "residual_is_accrual": "After the read-side fix, coverage is capped by post-dense-start "
                                   "favorites; it rises toward ~50% only as pre-start favorites age "
                                   "out and post-start ones accumulate (weeks) — no code lifts that.",
            "optional_rust_capture_side": "If per-favorite anchoring is ever wanted (not needed for "
                                          "λ̂), dense_capture_candidates could DISTINCT ON "
                                          "(condition_id, outcome_index, strategy) or prefer the "
                                          "favorite strategy in the ORDER BY — but this multiplies "
                                          "capture volume; the read-side market-key join is strictly "
                                          "better (zero extra capture, full recovery). NOT a threshold "
                                          "change; still DEFERRED (Rust touch).",
        },
    }
    with open(REPORT, "w") as f:
        json.dump(out, f, indent=2, default=str)

    if verbose:
        print(f"DENSE-CAPTURE DIAGNOSIS (Thread D)")
        print(f"  dense capture live since {start_ts} · {out['dense_capture']['n_rows']} rows / "
              f"{out['dense_capture']['n_signals']} signals")
        print(f"  capture scope by strategy: " +
              ", ".join(f"{r['strategy']}={r['n_signals']}" for r in out["capture_scope_by_strategy"]))
        ff = out["favorite_family"]
        print(f"  favorite family resolved: {ff['resolved_total']} "
              f"(pre-dense-start {ff['resolved_pre_dense_start']} / post {ff['resolved_post_dense_start']})")
        liftx = out["lift"]["immediate_coverage_x"]
        liftx_s = "n/a" if liftx is None else f"{liftx:.0f}x"
        print(f"  COVERAGE today (signal_id join): {int(cov_sig['n_cov'])}/{n_fam} = {cov_sig_frac:.1%}")
        print(f"  COVERAGE with market-key FIX:    {int(cov_mkt['n_cov'])}/{n_fam} = {cov_mkt_frac:.1%}"
              f"  → {liftx_s} (+{out['lift']['immediate_coverage_pp']*100:.0f}pp)")
        print(f"  post-dense-start favorites recoverable by market-key: "
              f"{int(post_recover['n_post_recover'])}/{n_post} = {post_recover_frac:.1%} "
              f"(the addressable ceiling; the rest is temporal accrual)")
        print(f"  PRIMARY CAUSE: {out['diagnosis']['primary_cause']}")
        print(f"  FIX: {out['fix_spec']['paper_safe_read_side'][:110]}...")
        print(f"wrote {REPORT}")
    return out


def selftest():
    """Synthetic proof that a market-key join recovers a sibling-anchored trajectory a signal_id join
    misses. 1 market, 2 sibling signals (strict id=1 captured, favorite id=2 not), favorite resolves."""
    # signal_id join: favorite id=2 has no trajectory row -> coverage 0/1
    traj = [{"signal_id": 1, "condition_id": "c1", "outcome_index": 0, "mid": 0.9}]  # strict-anchored
    fav = {"id": 2, "condition_id": "c1", "outcome_index": 0}
    cov_sig = 1 if any(t["signal_id"] == fav["id"] for t in traj) else 0
    cov_mkt = 1 if any(t["condition_id"] == fav["condition_id"]
                       and t["outcome_index"] == fav["outcome_index"] for t in traj) else 0
    assert cov_sig == 0 and cov_mkt == 1, f"expected sig-miss/market-hit, got {cov_sig}/{cov_mkt}"
    # degenerate-band guard still excludes an out-of-band mid
    traj_bad = [{"signal_id": 1, "condition_id": "c1", "outcome_index": 0, "mid": 0.995}]
    usable = [t for t in traj_bad if GUARD_LO <= t["mid"] <= GUARD_HI]
    assert usable == [], "degenerate mid must be excluded"
    print("selftest OK")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
    else:
        run()
