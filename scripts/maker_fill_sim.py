#!/usr/bin/env python3
"""
MAKER-FILL SIMULATOR — can limit orders at (or near) the sharp's price claw back the
copyability tax, and how much comes back as adverse selection?

The tax decomposes as  sharp fill → our mid (drift, ~1.3¢) → crossing the spread (band model)
→ the 2% modeled cost buffer. A TAKER pays all three. A MAKER limit at the sharp's price + δ
pays ~none of the first two — but fills PREFERENTIALLY when the market moves AGAINST the
signal (adverse selection): the bets you win are the ones the market never let you have. Any
honest claim of "we keep the whole edge with limit orders" must survive that check.

This instrument replays the dense-capture trajectories (`signal_price_trajectory`, ~45s mid +
executable best-ask for the first minutes of each fresh signal) under a frozen policy menu:

  TAKER          — buy at the earliest captured ask (the incumbent assumption).
  MAKER δ/T      — limit at initial_mean_price + δ (δ ∈ {0¢, 1¢, 2¢}), cancel after T minutes
                   (T ∈ {5, 15}). Fill iff any captured ask ≤ limit within T (conservative:
                   between-sample touches are missed, so TRUE fill rates are ≥ reported).

Per policy, on RESOLVED signals: fill rate, mean entry, realized edge per SIGNAL
(unfilled = abstain = 0), realized edge per FILL, and the ADVERSE-SELECTION check
(win-rate of filled vs win-rate of all resolved — a filled-when-wrong bias shows here).
Costs are reported BOTH at the repo's conservative FEE=2% buffer AND at fee=0 (Polymarket's
posted trading fee on most markets is currently zero — the 2% is our modeled cushion, not an
exchange charge; verify the live fee schedule before any real order, which this is not).

Read-only, paper-only; expected verdict today: INDETERMINATE-BY-DATA (few resolved tracked
signals) — it accrues with every dense-captured fire.  ./maker_fill_sim.py [--selftest]
Writes reports/maker_fill_sim.json.
"""

import argparse
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trader_scorecard as tsc

REPORT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "reports", "maker_fill_sim.json")
DELTAS = [0.0, 0.01, 0.02]
WINDOWS_MIN = [5, 15]
MIN_RESOLVED = 30    # honesty floor before any verdict wording strengthens


def fetch():
    """One row per trajectory point, joined to its signal's anchor + resolution."""
    return tsc.q("""
      SELECT t.signal_id, t.secs_after_fire, t.mid, t.ask,
             s.strategy, s.initial_mean_price AS anchor,
             s.resolved::int AS resolved, s.outcome_won::int AS won
      FROM signal_price_trajectory t
      JOIN consensus_signals s ON s.id = t.signal_id
      WHERE s.initial_mean_price IS NOT NULL
      ORDER BY t.signal_id, t.secs_after_fire""")


def by_signal(rows):
    sigs = defaultdict(lambda: {"pts": [], "anchor": None, "resolved": 0, "won": None,
                                "strategy": None})
    for r in rows:
        s = sigs[r["signal_id"]]
        s["anchor"] = float(r["anchor"])
        s["strategy"] = r["strategy"]
        s["resolved"] = int(r["resolved"])
        s["won"] = int(r["won"]) if r["won"] not in ("", None) else None
        if r["ask"] not in ("", None):
            s["pts"].append((int(r["secs_after_fire"]), float(r["ask"])))
    return {k: v for k, v in sigs.items() if v["pts"]}


def simulate(sigs, fee):
    """Frozen policy menu over the trajectories. Returns per-policy metrics."""
    out = {}
    resolved = {k: s for k, s in sigs.items() if s["resolved"] and s["won"] is not None}
    wr_all = (sum(s["won"] for s in resolved.values()) / len(resolved)) if resolved else None

    # TAKER: earliest captured ask.
    taker_entries = {k: min(s["pts"])[1] for k, s in sigs.items()}
    pol = {"fill_rate": 1.0, "mean_entry": None, "edge_per_signal": None,
           "edge_per_fill": None, "wr_filled": None, "n_resolved": len(resolved)}
    if resolved:
        ent = [taker_entries[k] for k in resolved]
        pol["mean_entry"] = sum(ent) / len(ent)
        edges = [(s["won"] - taker_entries[k]) / taker_entries[k] - fee
                 for k, s in resolved.items()]
        pol["edge_per_signal"] = pol["edge_per_fill"] = sum(edges) / len(edges)
        pol["wr_filled"] = wr_all
    out["taker"] = pol

    for delta in DELTAS:
        for tmin in WINDOWS_MIN:
            fills = {}
            for k, s in sigs.items():
                limit = s["anchor"] + delta
                hit = [p for p in s["pts"] if p[0] <= tmin * 60 and p[1] <= limit]
                if hit:
                    fills[k] = limit  # a resting limit fills AT the limit price
            name = f"maker_+{int(delta*100)}c_{tmin}m"
            fr = len(fills) / len(sigs) if sigs else 0.0
            p = {"fill_rate": fr, "mean_entry": None, "edge_per_signal": None,
                 "edge_per_fill": None, "wr_filled": None,
                 "n_resolved_filled": 0, "n_resolved": len(resolved)}
            rf = {k: v for k, v in fills.items() if k in resolved}
            if rf:
                p["mean_entry"] = sum(rf.values()) / len(rf)
                per_fill = [(resolved[k]["won"] - e) / e - fee for k, e in rf.items()]
                p["edge_per_fill"] = sum(per_fill) / len(per_fill)
                # per SIGNAL: unfilled = abstain = 0 (the opportunity cost is priced in)
                p["edge_per_signal"] = sum(per_fill) / len(resolved)
                p["wr_filled"] = sum(resolved[k]["won"] for k in rf) / len(rf)
                p["n_resolved_filled"] = len(rf)
            p["adverse_selection_gap"] = (
                round(p["wr_filled"] - wr_all, 4)
                if (p["wr_filled"] is not None and wr_all is not None) else None)
            out[name] = p
    out["_wr_all_resolved"] = wr_all
    return out


def selftest():
    # Falling ask crosses the limit → maker fills at the LIMIT price; rising ask → no fill.
    sigs = {
        1: {"anchor": 0.70, "resolved": 1, "won": 1, "strategy": "favorite",
            "pts": [(45, 0.74), (90, 0.71), (135, 0.70)]},          # touches 0.70 → fills @+0c
        2: {"anchor": 0.70, "resolved": 1, "won": 0, "strategy": "favorite",
            "pts": [(45, 0.72), (90, 0.69)]},                        # falls (against us) → fills
        3: {"anchor": 0.70, "resolved": 1, "won": 1, "strategy": "favorite",
            "pts": [(45, 0.74), (90, 0.78)]},                        # runs away → never fills
    }
    r = simulate(sigs, fee=0.0)
    m = r["maker_+0c_5m"]
    assert abs(m["fill_rate"] - 2 / 3) < 1e-9, "two of three should fill"
    assert m["mean_entry"] == 0.70, "maker fills at the limit price"
    # Adverse selection visible: filled set contains the loser; the runaway winner is missed.
    assert m["wr_filled"] < r["_wr_all_resolved"], "fixture must show filled-when-wrong bias"
    assert r["taker"]["fill_rate"] == 1.0 and r["taker"]["mean_entry"] > 0.70
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return

    sigs = by_signal(fetch())
    n_resolved = sum(1 for s in sigs.values() if s["resolved"] and s["won"] is not None)
    res = {"fee_2pct_buffer": simulate(sigs, tsc.FEE), "fee_zero": simulate(sigs, 0.0)}
    verdict = ("INDETERMINATE-BY-DATA: "
               f"{n_resolved} resolved tracked signals < {MIN_RESOLVED} floor — accruing; "
               "no execution-policy claim is certified"
               if n_resolved < MIN_RESOLVED else
               f"{n_resolved} resolved tracked signals — read the per-policy table")
    out = {"meta": {"n_signals_tracked": len(sigs), "n_resolved": n_resolved,
                    "deltas_cents": [int(d * 100) for d in DELTAS],
                    "windows_min": WINDOWS_MIN, "min_resolved_floor": MIN_RESOLVED,
                    "caveats": [
                        "fills sampled ~45s: between-sample touches missed => TRUE fill rates >= reported",
                        "queue position / partial fills not modeled (optimistic for maker)",
                        "anchor = initial_mean_price (sharp cohort mean), not a single wallet's fill",
                    ]},
           "policies": res, "verdict": verdict}
    with open(REPORT, "w") as f:
        json.dump(out, f, indent=2, default=str)

    print(f"MAKER-FILL SIM — {len(sigs)} tracked signals, {n_resolved} resolved. {verdict}")
    for fee_key, tbl in res.items():
        print(f"  [{fee_key}] wr(all resolved)={tbl['_wr_all_resolved']}")
        for name, p in tbl.items():
            if name.startswith("_"):
                continue
            eps = f"{p['edge_per_signal']:+.3f}" if p["edge_per_signal"] is not None else "  — "
            epf = f"{p['edge_per_fill']:+.3f}" if p["edge_per_fill"] is not None else "  — "
            gap = p.get("adverse_selection_gap")
            print(f"    {name:>14}: fill {p['fill_rate']:.0%} | edge/signal {eps} | "
                  f"edge/fill {epf} | adv-sel gap {gap if gap is not None else '—'}")
    print(f"wrote {REPORT}")


if __name__ == "__main__":
    main()
