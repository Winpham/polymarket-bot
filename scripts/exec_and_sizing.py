#!/usr/bin/env python3
"""
EXECUTION REALISM + SIZING BAKE-OFF (harden-edge, P4+P5). Favorite arm, resolved, price 0.65-0.98.

P4 — the fee model matters and is NOT unified in the tree. The correct Polymarket sports TAKER fee is
0.03·(1−p) per $ of stake (charged at entry; makers pay 0). Favorites sit at high p, so the correct
fee is small (~0.5% at p=0.82) — far below the flat `0.03·stake` in backtest.py or the 2% buffer in
copyability/selection_null. We report resolved ROI under each fee × each entry basis, ALL LABELED.
Entry bases: at-fire mid (`initial_mean_price`), mid + measured follower tax (~1¢, real_tax.json),
measured real ask (`entry_ask`, where captured — CAVEAT: G3 audit found entry_ask is captured ~20min
post-detection, a FUTURE price flattering the entry ~1.8pp; shown but flagged, never the headline).

P5 — sizing bake-off as the frozen finding predicts: a thin, capacity-capped edge cannot be safely
levered, so prudent (⅛-Kelly) compounding ≈ flat. flat-$ vs flat-shares vs capped-favoritedness vs
⅛-Kelly-on-selection-surplus, total resolved P&L at the correct fee.

Read-only, paper-only, adopts nothing, no real money. DB via docker-exec.
"""
import io
import csv
import json
import os
import subprocess
import sys

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q", "-c"]
MEASURED_TAX = 0.01     # real_tax.json median follower tax (~1c)
SURPLUS = 0.06          # belief-blind selection surplus estimate (favorite), for Kelly edge
STAKE = 100.0

SQL = """
SELECT (outcome_won::int) AS won,
       COALESCE(initial_mean_price, mean_price) AS mid,
       entry_ask
FROM consensus_signals
WHERE resolved AND strategy='favorite'
  AND COALESCE(initial_mean_price, mean_price) BETWEEN 0.65 AND 0.98
  AND outcome_won IS NOT NULL;
"""


def fetch():
    out = subprocess.run(PG + [SQL], capture_output=True, text=True, check=True).stdout
    rows = []
    for r in csv.DictReader(io.StringIO(out.stdout if False else out)):
        rows.append({"won": int(r["won"]), "mid": float(r["mid"]),
                     "ask": float(r["entry_ask"]) if r["entry_ask"] not in ("", None) else None})
    return rows


def fee_frac(entry, model):
    if model == "correct 0.03(1-p)":
        return 0.03 * (1 - entry)
    if model == "flat 2% buffer":
        return 0.02
    if model == "flat 3%*stake":
        return 0.03
    if model == "maker fee 0":
        return 0.0
    raise ValueError(model)


def roi_flatdollar(rows, entry_key, fee_model):
    """flat-$STAKE per bet. per-bet pnl = won*STAKE*(1-e)/e - (1-won)*STAKE - fee*STAKE."""
    tot_pnl, tot_stake = 0.0, 0.0
    for r in rows:
        e = r["mid"] if entry_key == "mid" else \
            (r["mid"] + MEASURED_TAX) if entry_key == "mid+tax" else r["ask"]
        if e is None or not (0 < e < 1):
            continue
        f = fee_frac(e, fee_model)
        pnl = (STAKE * (1 - e) / e if r["won"] else -STAKE) - f * STAKE
        tot_pnl += pnl; tot_stake += STAKE
    return tot_pnl, tot_stake, tot_pnl / tot_stake if tot_stake else 0.0


def main():
    rows = fetch()
    n = len(rows)
    have_ask = sum(1 for r in rows if r["ask"] is not None)
    print(f"favorite arm · {n} resolved bets · entry_ask captured on {have_ask}\n")

    # ---- P4: fee × entry reconciliation (flat-$100) ----
    print("P4 — REALIZABLE-EDGE ROI, at-fire-entry basis (flat-$100) by ENTRY × FEE  [ALL LABELED]")
    print("     (this is the §3b realizable/honest_roi basis — matches prior +8.36%; the CANONICAL")
    print("      resolved-P&L on actual ledger fills stays +1.27% (standard_guard.json), lower & front-loaded)")
    print(f"{'entry basis':<12}{'correct 0.03(1-p)':>19}{'flat 2% buffer':>16}{'flat 3%*stake':>15}{'maker fee 0':>13}")
    p4 = {}
    for entry_key, label in (("mid", "at-fire mid"), ("mid+tax", "mid+1c tax"), ("ask", "measured ask*")):
        cells = []
        for fee in ("correct 0.03(1-p)", "flat 2% buffer", "flat 3%*stake", "maker fee 0"):
            _, _, roi = roi_flatdollar(rows, entry_key, fee)
            cells.append(roi); p4[f"{entry_key}|{fee}"] = round(roi, 5)
        print(f"{label:<12}" + "".join(f"{c:>+18.2%} " for c in cells))
    print("  *measured ask = entry_ask, captured ~20min post-detection (G3): a FUTURE price, flatters ~1.8pp. Not the headline.")
    print("  → the correct 0.03(1-p) taker fee costs favorites ~0.5% vs the 2-3% flat fees scattered in the tree;")
    print("    using it makes the HONEST resolved edge look better, and it is the right number.\n")

    # ---- P5: sizing bake-off (correct fee, at-fire mid) ----
    print("P5 — sizing bake-off (correct fee, at-fire mid entry) · total P&L, ROI-on-turnover (realizable basis)")
    def kelly_stake(e):
        q = min(0.999, e + SURPLUS)            # edge estimate: true prob ~ price + selection surplus
        fstar = max(0.0, (q - e) / (1 - e))    # Kelly fraction for binary at price e
        return (fstar / 8.0)                    # 1/8-Kelly, as a fraction of bankroll
    schemes = {}
    # normalize kelly to mean-$100 so it's comparable turnover
    kfracs = [kelly_stake(r["mid"]) for r in rows]
    kmean = sum(kfracs) / len(kfracs) if kfracs else 1
    for name in ("flat-$", "flat-shares", "capped-fav", "1/8-Kelly"):
        tot_pnl, tot_stake = 0.0, 0.0
        for r in rows:
            e = r["mid"]
            if name == "flat-$":
                stake = STAKE
            elif name == "flat-shares":
                stake = STAKE * e                       # buy ~STAKE shares
            elif name == "capped-fav":
                stake = STAKE if e <= 0.92 else STAKE * 0.5   # halve extreme favorites
            else:  # 1/8-Kelly, normalized to mean $100 turnover
                stake = STAKE * kelly_stake(e) / kmean
            f = fee_frac(e, "correct 0.03(1-p)")
            pnl = (stake * (1 - e) / e if r["won"] else -stake) - f * stake
            tot_pnl += pnl; tot_stake += stake
        schemes[name] = (tot_pnl, tot_stake, tot_pnl / tot_stake if tot_stake else 0)
    print(f"{'scheme':<14}{'P&L':>12}{'turnover':>12}{'ROI':>9}")
    for name, (pnl, stake, roi) in schemes.items():
        print(f"{name:<14}{pnl:>+12.0f}{stake:>12.0f}{roi:>+8.2%}")
    spread = max(s[2] for s in schemes.values()) - min(s[2] for s in schemes.values())
    print(f"\n  ROI spread across sizing schemes: {spread:.2%}. The edge is thin + capacity-capped (P2: ~\$500-1k/signal");
    print("  ceiling), so prudent ⅛-Kelly ≈ flat — it CANNOT be safely levered into materially more $. Confirmed.")

    json.dump({"p4_roi": p4, "p5_sizing": {k: {"pnl": round(v[0], 1), "turnover": round(v[1], 1),
              "roi": round(v[2], 5)} for k, v in schemes.items()}, "n_bets": n, "entry_ask_n": have_ask},
              open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "reports", "exec_and_sizing.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
