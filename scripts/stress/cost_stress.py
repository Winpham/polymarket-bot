#!/usr/bin/env python3
"""
F4 — COST STRESS.  Does favorite's edge survive realistic execution?

After costs, only favorite-tilted strategies are +EV and the margin is thin. This asks the
kill question with numbers: sweep haircut & fee 1x-5x and add a liquidity-limited ADVERSE-FILL
model (the favorite side, price band 0.80-0.97, is thin at the exact odds you want, so you fill
worse than mid) plus a small resolution/dispute probability, then recompute favorite's
realizable ROI and its BLOCK-BOOTSTRAP lower bound (slate grain, preserving within-slate
correlation exactly). KILL (pre-registered): favorite's corrected LB <= 0 under
2x haircut + adverse-fill (+2c).

Realizable per-event ROI (mirrors risk_engine `unit`): with entry e (event-clustered),
  c        = min(0.999, e + HAIRCUT*hc_mult + fill_bump)      # what you actually pay
  won_eff  = won * (1 - dispute_p)                            # disputes turn some wins to losses
  roi      = won_eff/c - 1 - FEE*fee_mult                     # per $ of position

Modes:
  ./cost_stress.py            # live favorite, full grid -> reports/stress/cost_stress.json
  ./cost_stress.py --selftest # zero-cost recovers raw edge; monotone in cost; zero-edge dies
"""
import json
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import selection_null as sn  # fetch(), band(), regime()

HAIRCUT = 0.005
FEE = 0.02
SEED = 20260702
N_BOOT = 10_000
# Grid (pre-registered): the kill cell is hc_mult=2, fill=0.02, fee_mult=1.
HC_MULTS = [1, 2, 3, 5]
FILLS = [0.0, 0.01, 0.02, 0.03]
FEE_MULTS = [1, 2]
DISPUTE_P = 0.005  # small graded-loss-even-on-a-win probability (Polymarket resolution/dispute)


def favorite_events(rows=None, strategy="favorite"):
    """Event-cluster favorite's resolved rows with at-fire entry -> one bet per event."""
    rows = rows if rows is not None else sn.fetch()
    srows = [r for r in rows if r["strategy"] == strategy]
    by_ev = defaultdict(list)
    for r in srows:
        by_ev[r["ev"]].append(r)
    events = []
    for ev, rs in by_ev.items():
        entry = float(np.mean([x["entry"] for x in rs]))
        won = float(np.mean([x["won"] for x in rs]))
        rg = sn.regime(rs[0]["event_slug"])
        events.append({"ev": ev, "entry": entry, "won": won, "band": sn.band(entry),
                       "regime": rg, "day": rs[0]["day"], "slate": (rg, rs[0]["day"])})
    return events


def event_roi(e, hc_mult, fill, fee_mult, dispute_p=DISPUTE_P):
    c = min(0.999, e["entry"] + HAIRCUT * hc_mult + fill)
    won_eff = e["won"] * (1.0 - dispute_p)
    return won_eff / c - 1.0 - FEE * fee_mult


def clustered_mean(events, rois):
    """Event-clustered already (one row per event); return simple mean ROI."""
    return float(np.mean(rois)) if len(rois) else float("nan")


def block_bootstrap_lb(events, rois, seed=SEED, n=N_BOOT, pct=5.0):
    """Slate-block bootstrap of the mean ROI. Resample (regime x day) slates with
    replacement (preserves within-slate correlation) -> 5th-pct of the resampled mean."""
    slates = defaultdict(list)
    for i, e in enumerate(events):
        slates[e["slate"]].append(i)
    slate_keys = list(slates.keys())
    slate_idx = [np.array(slates[k]) for k in slate_keys]
    slate_roi = [np.array([rois[i] for i in idx]) for idx in slate_idx]
    slate_n = np.array([len(idx) for idx in slate_idx])
    rng = np.random.default_rng(seed)
    nslate = len(slate_keys)
    total_n = int(slate_n.sum())
    means = np.empty(n)
    for b in range(n):
        pick = rng.integers(0, nslate, size=nslate)
        num = sum(slate_roi[j].sum() for j in pick)
        den = sum(slate_n[j] for j in pick)
        means[b] = num / den if den else np.nan
    return float(np.nanpercentile(means, pct)), float(np.nanmean(means)), total_n


def run(strategy="favorite"):
    events = favorite_events(strategy=strategy)
    n = len(events)
    grid = []
    kill_cell = None
    for hc in HC_MULTS:
        for fill in FILLS:
            for fee in FEE_MULTS:
                rois = [event_roi(e, hc, fill, fee) for e in events]
                mean = clustered_mean(events, rois)
                lb, boot_mean, _ = block_bootstrap_lb(events, rois)
                cell = {"hc_mult": hc, "fill_cents": round(fill * 100, 1), "fee_mult": fee,
                        "mean_roi": mean, "boot_mean": boot_mean, "lb5": lb,
                        "lb_gt_0": lb > 0, "lb_gt_3pct": lb > 0.03}
                grid.append(cell)
                if hc == 2 and abs(fill - 0.02) < 1e-9 and fee == 1:
                    kill_cell = cell
    # per-band decomposition at the kill cell (2x haircut + 2c fill)
    by_band = defaultdict(list)
    for e in events:
        by_band[e["band"]].append(e)
    band_rows = {}
    for b, evs in sorted(by_band.items()):
        rois = [event_roi(e, 2, 0.02, 1) for e in evs]
        lb, bm, _ = block_bootstrap_lb(evs, rois, seed=SEED + b)
        band_rows[int(b)] = {"n": len(evs),
                             "avg_entry": float(np.mean([e["entry"] for e in evs])),
                             "winrate": float(np.mean([e["won"] for e in evs])),
                             "mean_roi_killcell": float(np.mean(rois)), "lb5": lb}
    # regression-to-price stress: what if band-5's lucky win-rate reverts to its price?
    revert = None
    b5 = by_band.get(5, [])
    if b5:
        priced = [dict(e, won=e["entry"]) for e in b5]  # winrate -> price (zero raw edge)
        rois = [event_roi(e, 2, 0.02, 1) for e in priced]
        revert = {"n": len(b5), "mean_roi_if_band5_reverts_to_price": float(np.mean(rois))}
    result = {"meta": {"strategy": strategy, "n_events": n, "haircut": HAIRCUT, "fee": FEE,
                       "dispute_p": DISPUTE_P, "seed": SEED, "n_boot": N_BOOT,
                       "kill_criterion": "LB<=0 at hc_mult=2, fill=2c, fee_mult=1"},
              "baseline_roi_no_stress": clustered_mean(
                  events, [event_roi(e, 1, 0.0, 1, dispute_p=0.0) for e in events]),
              "grid": grid, "kill_cell": kill_cell, "by_band_at_killcell": band_rows,
              "band5_revert": revert}
    return result


def _print(r):
    m = r["meta"]
    print(f"F4 cost stress · {m['strategy']} · {m['n_events']} events · {N_BOOT} slate-block "
          f"boot · baseline ROI {r['baseline_roi_no_stress']:+.2%}")
    print(f"{'hc':>3}{'fill':>6}{'fee':>5}{'meanROI':>10}{'boot':>9}{'LB(5%)':>9}  flags")
    for c in r["grid"]:
        flag = "" if c["lb_gt_0"] else "  LB<=0"
        flag += "  <3%margin" if (c["lb_gt_0"] and not c["lb_gt_3pct"]) else ""
        star = " <<KILL-CELL" if c is r["kill_cell"] else ""
        print(f"{c['hc_mult']:>3}{c['fill_cents']:>5}c{c['fee_mult']:>5}"
              f"{c['mean_roi']:>+10.2%}{c['boot_mean']:>+9.2%}{c['lb5']:>+9.2%}{flag}{star}")
    kc = r["kill_cell"]
    print(f"\nKILL CELL (2x haircut + 2c adverse fill): mean ROI {kc['mean_roi']:+.2%}, "
          f"LB(5%) {kc['lb5']:+.2%} -> {'FAIL (LB<=0)' if not kc['lb_gt_0'] else 'survives >0' + (' but <3% margin' if not kc['lb_gt_3pct'] else '')}")
    print("\nper-band at kill cell:")
    for b, br in r["by_band_at_killcell"].items():
        print(f"  band {b}: n={br['n']:>3} entry {br['avg_entry']:.3f} win {br['winrate']:.3f} "
              f"-> ROI {br['mean_roi_killcell']:+.2%}  LB {br['lb5']:+.2%}")
    if r["band5_revert"]:
        rv = r["band5_revert"]
        print(f"\nif band-5 win-rate reverts to its price (zero raw edge) + kill-cell costs: "
              f"ROI {rv['mean_roi_if_band5_reverts_to_price']:+.2%} on n={rv['n']}")


def selftest():
    ok = True
    # synthetic favorite: band-5 entry 0.90 win 0.98 (edge), 60 events over 6 slates
    rng = np.random.default_rng(SEED)
    evs = []
    for s in range(6):
        for k in range(10):
            evs.append({"ev": f"e{s}_{k}", "entry": 0.90,
                        "won": 1.0 if rng.random() < 0.98 else 0.0, "band": 5,
                        "regime": "tennis", "day": f"d{s}", "slate": ("tennis", f"d{s}")})
    r0 = [event_roi(e, 1, 0.0, 1, dispute_p=0.0) for e in evs]
    # analytic check on a single deterministic winning event: 1/(0.90+0.005) - 1 - 0.02
    one = event_roi({"entry": 0.90, "won": 1.0}, 1, 0.0, 1, dispute_p=0.0)
    analytic = 1.0 / 0.905 - 1.0 - 0.02
    match = abs(one - analytic) < 1e-12
    print(f"  formula on a won event {one:+.5%} == analytic {analytic:+.5%} [{'ok' if match else 'FAIL'}]")
    ok = ok and match
    # monotone: more cost -> lower ROI
    seq = [np.mean([event_roi(e, hc, 0.0, 1) for e in evs]) for hc in (1, 2, 3, 5)]
    mono = all(seq[i] > seq[i + 1] for i in range(len(seq) - 1))
    print(f"  ROI monotone-decreasing in haircut: {[f'{x:+.2%}' for x in seq]} [{'ok' if mono else 'FAIL'}]")
    ok = ok and mono
    # zero-edge (win-rate == price) must go negative under any real cost
    ze = [dict(e, won=e["entry"]) for e in evs]
    roi_ze = np.mean([event_roi(e, 1, 0.0, 1) for e in ze])
    dies = roi_ze < 0
    print(f"  zero-edge ROI under baseline cost {roi_ze:+.3%} (<0 required) [{'ok' if dies else 'FAIL'}]")
    ok = ok and dies
    # bootstrap LB below mean
    lb, bm, _ = block_bootstrap_lb(evs, r0, n=2000)
    below = lb < bm
    print(f"  boot LB {lb:+.3%} < boot mean {bm:+.3%} [{'ok' if below else 'FAIL'}]")
    ok = ok and below
    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    r = run()
    _print(r)
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "..", "reports", "stress", "cost_stress.json")
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "..", "reports", "stress", "cost_stress.json"), "w") as f:
        json.dump(r, f, indent=1, default=str)
    print("\nartifact -> reports/stress/cost_stress.json")


if __name__ == "__main__":
    main()
