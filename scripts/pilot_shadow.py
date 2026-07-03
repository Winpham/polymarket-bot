#!/usr/bin/env python3
"""
WS-D — PILOT SHADOW REPLAY. What the unarmed pilot harness WOULD have done on the resolved record.

Mirrors the sizing + kill-switch rules of `copy-trading-bot/src/pilot.rs` (the source of truth; this
replay is for the report, the Rust module is what guards real money). Replays the favorite record in
chronological order through: de-levered ⅟₁₂-Kelly sizing, the day-stop / drawdown / edge-degradation /
master kill-switches, and CLV + honest realizable-P&L tracking. PLACES NOTHING — it is a paper replay.

The honest headline it surfaces: with WS-A's measured λ̂≈0.15 BELOW the pilot's `min_lambda` floor
(0.25), the pilot's OWN edge-degradation kill-switch halts it before it places a single bet. The
harness, run honestly on today's evidence, self-vetoes. The counterfactual mode (assume λ above the
floor) shows the machinery + the go/no-go envelope, clearly labelled conditional-on-λ.

Read-only, paper-only.
  ./pilot_shadow.py                 # honest (λ̂ from reports/clv_lambda.json) + counterfactual λ=0.5
  ./pilot_shadow.py --lambda 0.5    # force a λ
  ./pilot_shadow.py --selftest      # sizing/kill-switch parity fixtures
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
FEE = 0.02
DELEVER_K = 1.0 / 12.0
STAKE_FRAC_CAP = 0.05
REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")

# Pilot config (mirror pilot.rs PilotConfig::default(), but master_on=True for the shadow so we can
# observe what it WOULD do — the real default is master_on=False, i.e. halted from birth).
CFG = {"bankroll": 500.0, "delever_k": DELEVER_K, "day_stop_loss_frac": 0.05,
       "max_drawdown_frac": 0.15, "min_lambda": 0.25}


def q(sql):
    out = subprocess.run(PG + ["-f", "-"], input=sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    return list(csv.DictReader(io.StringIO(out.stdout)))


def delevered_stake_frac(c, p, k):
    if not (0.0 <= c < 1.0) or not (0.0 <= p <= 1.0):
        return 0.0
    r_win = (1.0 - c) / c - FEE
    if r_win <= 0.0:
        return 0.0
    f_star = p / (1.0 + FEE) - (1.0 - p) / r_win
    if f_star <= 0.0:
        return 0.0
    return min(max(k * f_star, 0.0), STAKE_FRAC_CAP)


def realizable_pnl(entry, won, notional):
    e = min(0.999, entry + 0.01)
    return notional * (won - e) - FEE * notional * e


def band(p):
    if p < 0.0:
        return 0
    if p >= 1.0:
        return 6
    return int(p * 5.0) + 1


def replay(rows, lam, delta, cfg):
    """Chronological replay. Returns a summary dict. Edge-degradation halt keys on `lam` (the live
    λ̂ estimate) vs cfg['min_lambda'] — the pilot refuses to bet when λ̂ is below the floor."""
    equity = peak = cfg["bankroll"]
    day = None
    day_pnl = 0.0
    max_dd = 0.0
    n_bet = n_win = 0
    clv_sum = 0.0
    halted = None
    # edge-degradation is evaluated up front (λ̂ is a slate-level estimate)
    if lam < cfg["min_lambda"]:
        halted = "EdgeDegraded"
    for r in rows:
        if halted:
            break
        d = r["day"]
        if d != day:
            day = d
            day_pnl = 0.0
        c = r["entry"]
        p = min(max(c + lam * delta, 0.02), 0.995)
        f = delevered_stake_frac(c, p, cfg["delever_k"])
        if f <= 0.0:
            continue
        e = min(0.999, c + 0.01)
        shares = f * equity / e
        won = r["won"]
        pnl = realizable_pnl(c, won, shares)
        equity += pnl
        day_pnl += pnl
        n_bet += 1
        n_win += int(won == 1)
        clv_sum += (r["close_proxy"] - c) if r["close_proxy"] is not None else 0.0
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)
        # kill-switch checks (latching)
        if day_pnl <= -(cfg["day_stop_loss_frac"] * cfg["bankroll"]):
            halted = "DayStopLoss"
        elif dd >= cfg["max_drawdown_frac"]:
            halted = "MaxDrawdown"
    return {"lambda": lam, "n_bet": n_bet, "n_win": n_win,
            "wr": round(n_win / n_bet, 3) if n_bet else None,
            "final_equity": round(equity, 2), "roi": round((equity / cfg["bankroll"] - 1.0), 4),
            "max_drawdown": round(max_dd, 4), "mean_clv": round(clv_sum / n_bet, 4) if n_bet else None,
            "halted": halted}


def load_records():
    rows = q("""
      SELECT initial_mean_price AS entry, (outcome_won::int) AS won, mean_price AS close_proxy,
        to_char(COALESCE(first_detected_at, resolved_at) AT TIME ZONE 'UTC','YYYY-MM-DD') AS day,
        COALESCE(first_detected_at, resolved_at) AS ts
      FROM consensus_signals
      WHERE strategy='favorite' AND resolved AND initial_mean_price IS NOT NULL
      ORDER BY COALESCE(first_detected_at, resolved_at)""")
    out = []
    for r in rows:
        out.append({"entry": float(r["entry"]), "won": int(r["won"]),
                    "close_proxy": float(r["close_proxy"]) if r["close_proxy"] not in (None, "") else None,
                    "day": r["day"]})
    return out


def load_lambda_hat():
    path = os.path.join(REPORT_DIR, "clv_lambda.json")
    try:
        with open(path) as f:
            return json.load(f).get("lambda_hat")
    except Exception:
        return None


def selftest():
    ok = True
    # sizing parity with pilot.rs test: c=0.8 p=0.85 → ⅟₁₂-Kelly ≈ 0.01510
    f = delevered_stake_frac(0.8, 0.85, DELEVER_K)
    if abs(f - 0.01510) > 1e-4:
        print(f"  FAIL sizing {f:.5f} (expected 0.01510)"); ok = False
    else:
        print(f"  PASS sizing {f:.5f}")
    # realizable pnl parity
    if abs(realizable_pnl(0.80, 1, 100) - 17.38) > 1e-6 or abs(realizable_pnl(0.80, 0, 100) + 82.62) > 1e-6:
        print("  FAIL realizable_pnl"); ok = False
    else:
        print("  PASS realizable_pnl")
    # edge-degradation: λ below floor ⇒ 0 bets
    r = replay([{"entry": 0.8, "won": 1, "close_proxy": 0.82, "day": "d"}], 0.10, 0.14, CFG)
    if r["halted"] != "EdgeDegraded" or r["n_bet"] != 0:
        print(f"  FAIL edge-degradation self-veto: {r}"); ok = False
    else:
        print("  PASS edge-degradation self-veto (λ<floor ⇒ 0 bets)")
    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lambda", dest="lam", type=float, default=None)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return

    rows = load_records()
    wr = sum(r["won"] for r in rows) / len(rows)
    entry_mean = sum(r["entry"] for r in rows) / len(rows)
    delta = wr - entry_mean       # realized favorite δ
    lam_hat = load_lambda_hat()

    modes = []
    if args.lam is not None:
        modes.append(("forced", args.lam))
    else:
        modes.append(("honest (WS-A λ̂)", lam_hat if lam_hat is not None else 0.15))
        modes.append(("counterfactual λ=0.5", 0.5))
        modes.append(("counterfactual λ=1.0", 1.0))

    print("=" * 78)
    print(f"WS-D · PILOT SHADOW REPLAY · favorite · {len(rows)} resolved positions · "
          f"WR {wr:.1%} δ {delta:+.3f}")
    print(f"config: bankroll ${CFG['bankroll']:.0f} · k=⅟₁₂ · day-stop {CFG['day_stop_loss_frac']:.0%} · "
          f"maxDD {CFG['max_drawdown_frac']:.0%} · min_λ {CFG['min_lambda']}")
    print("(shadow runs with master_on=True to observe; the REAL default is master_off ⇒ halted from birth)")
    print("-" * 78)
    results = []
    for name, lam in modes:
        res = replay(rows, lam, delta, CFG)
        res["mode"] = name
        results.append(res)
        halt = res["halted"] or "—"
        bets = f"{res['n_bet']} bets, WR {res['wr']}" if res["n_bet"] else "0 bets"
        print(f"  {name:<22} λ={lam:<5.2f}  {bets:<22} equity ${res['final_equity']:>8.2f} "
              f"(ROI {res['roi']:>+6.1%})  maxDD {res['max_drawdown']:>5.1%}  halt={halt}")
    print("-" * 78)
    honest = results[0]
    if honest["halted"] == "EdgeDegraded":
        print("HONEST OUTCOME: the pilot SELF-VETOES — WS-A's λ̂ is below the min_λ floor, so the")
        print("edge-degradation kill-switch halts it before a single bet. It places nothing on today's")
        print("evidence. The counterfactual rows show the machinery IF λ were measured above the floor.")
    print("Real money awaits Tue's go; PILOT_ARMED unset + master_off ⇒ unreachable place path (pilot.rs).")
    print("=" * 78)

    os.makedirs(REPORT_DIR, exist_ok=True)
    path = os.path.join(REPORT_DIR, "pilot_shadow.json")
    with open(path, "w") as f:
        json.dump({"meta": {"n": len(rows), "wr": round(wr, 4), "delta": round(delta, 4),
                            "lambda_hat": lam_hat, "config": CFG}, "modes": results}, f, indent=2)
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
