#!/usr/bin/env python3
"""
SILENT FORWARD STEERING OVERLAY — Phase 5 (2026-07-03).

A VIRTUAL overlay strategy: the SAME generic `favorite` edge, but STEERED by the softness×skill
map — concentrate on PRIORITIZE cells, DODGE the sharp ones. It changes NOTHING live (no Rust
arm, no env flip, no alert change — the arm is EARNED, not built, per K3); it only MEASURES
whether steering the existing edge would have added realizable P&L, and it accrues that judgment
FORWARD from the map's effective time.

Because the current map has 0 PRIORITIZE cells (nothing certifies on ~5 correlated summer days),
the only steering signal available today is the DODGE set — so the overlay = base `favorite`
MINUS the picks in DODGE cells. The excluded picks' realized P&L is fully accounted (that is the
whole point: we only "win" by steering if the dropped picks were −EV).

  base_roi     = event-clustered realizable ROI (0.5¢ + 2%) over ALL favorite picks.
  overlay_roi  = same over favorite picks NOT in a DODGE cell.
  excluded_roi = same over the DROPPED (DODGE-cell) picks — the money we chose not to deploy.
  lift         = overlay_roi − base_roi  (per $ deployed).

FORWARD-ONLY judgment (K3): the map is pre-registered and effective 2026-07-03T18:00Z; the
honest forward window is events fired AFTER that. On today's record that window is EMPTY, so the
forward lift is INDETERMINATE and the overlay orders NOTHING yet — reported LOUDLY. The
retrospective (map-in-sample) lift is shown only as a sanity read, clearly labelled not-forward.

Modes:
  ./overlay_lift.py --self-test   # dropping an all-loser DODGE cell → lift>0; no DODGE → lift 0
  ./overlay_lift.py               # live overlay + forward-accrual status + watch-list
"""

import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import softness_map as sm

MAP_EFFECTIVE = "2026-07-03T18:00:00Z"   # v002 effective time; forward window = fires after this
MAP_EFFECTIVE_DAY = "2026-07-03"


def _event_roi(rows):
    """favorite rows → {ev: event-mean realizable ROI at measured costs}."""
    pairs = defaultdict(list)
    for r in rows:
        e = min(0.999, r["entry"] + sm.HAIRCUT)
        pairs[sm.evk(r)].append((r["won"] - e) / e - sm.FEE)
    return {ev: float(np.mean(v)) for ev, v in pairs.items()}


def overlay(rows, res):
    dodge = {c for c, v in res["verdicts"].items() if v["verdict"] == "DODGE"}
    picks = [r for r in rows if r["strategy"] == sm.STRAT and sm.cellof(r) is not None]
    kept = [r for r in picks if sm.cellof(r) not in dodge]
    dropped = [r for r in picks if sm.cellof(r) in dodge]

    def summ(rs):
        er = _event_roi(rs)
        vals = list(er.values())
        return (len(vals), float(np.mean(vals)) if vals else float("nan"))

    n_base, base_roi = summ(picks)
    n_ov, ov_roi = summ(kept)
    n_ex, ex_roi = summ(dropped)
    lift = (ov_roi - base_roi) if (n_base and n_ov) else float("nan")
    return dict(dodge_cells=sorted("/".join(c) for c in dodge),
                n_base=n_base, base_roi=base_roi, n_overlay=n_ov, overlay_roi=ov_roi,
                n_excluded=n_ex, excluded_roi=ex_roi, lift=lift)


def watch_list(res):
    """Cells approaching a floor — the re-read triggers (per cell: N→20 fires / +7 days / in-season)."""
    out = []
    for c, v in res["verdicts"].items():
        cat, mt, band = c
        nf = v.get("n_fav") or 0
        nb = v.get("n_blind_fav") or 0
        soft = v.get("softness")
        # soft AND close to the skill floor = the most valuable to watch
        if v["verdict"] == "INDETERMINATE" and soft is not None and soft > sm.SOFT_MARGIN \
                and nf >= 3:
            out.append((c, nf, nb, soft, f"skill N {nf}/{sm.SKILL_N_FLOOR} — re-read at +{sm.SKILL_N_FLOOR-nf} fires"))
        elif v["verdict"] == "INDETERMINATE" and nb >= 15 and nf == 0 and cat not in ("crypto",):
            lean = ("soft-but-silent — watch to harvest" if (soft or 0) > 0
                    else "sharp-but-silent — watch to DODGE")
            out.append((c, nf, nb, soft, f"{lean} when it fires / in-season"))
    return sorted(out, key=lambda x: -(x[3] or -1))


def main():
    rows = sm.fetch()
    res = sm.analyze(rows)
    o = overlay(rows, res)
    days = res["meta"]["days"]
    forward_days = [d for d in days if d > MAP_EFFECTIVE_DAY]
    print("SILENT FORWARD STEERING OVERLAY · virtual (changes nothing live) · "
          f"map effective {MAP_EFFECTIVE}")
    print(f"steering signal today: DODGE {o['dodge_cells'] or '(none)'}  "
          f"(0 PRIORITIZE cells — nothing certifies yet)\n")
    print(f"  base favorite : {o['n_base']:>3} events  realizable ROI {sm._f(o['base_roi'])}")
    print(f"  overlay (−DODGE): {o['n_overlay']:>3} events  realizable ROI {sm._f(o['overlay_roi'])}")
    print(f"  excluded (DODGE): {o['n_excluded']:>3} events  realizable ROI {sm._f(o['excluded_roi'])}")
    print(f"  retrospective lift (map-in-sample, NOT forward proof): {sm._f(o['lift'])}\n")

    # K3 — the forward judgment
    if not forward_days:
        print("K3 · FORWARD LIFT = INDETERMINATE: 0 events fired after the map's effective time.")
        print("     The overlay orders NOTHING yet. The map is pre-registered; the paired lift")
        print("     accrues from here. Re-run this after ≥1 forward day to get the honest number.")
    else:
        fwd_rows = [r for r in rows if r["day"] in forward_days]
        of = overlay(fwd_rows, res)
        print(f"K3 · FORWARD LIFT ({len(forward_days)} days, {of['n_base']} events): {sm._f(of['lift'])}")
        if not (of["lift"] > 0):
            print("     ≤ 0 → the map orders nothing forward; steering adds no realizable P&L (NULL).")

    # watch-list
    wl = watch_list(res)
    print(f"\nWATCH-LIST · {len(wl)} cells approaching a floor (re-read triggers):")
    for c, nf, nb, soft, trig in wl:
        print(f"  {'/'.join(c):<34} softness {sm._f(soft):>7}  Nfav {nf:>2} Nblind {nb:>3}  · {trig}")
    return 0


# --- self-test ------------------------------------------------------------------------------
def _self_test():
    ok = True
    days = ["2026-06-29", "2026-06-30", "2026-07-01", "2026-07-02"]
    rows = []
    # a sharp DODGE cell (mlb/deriv) whose favorite picks are ALL losers, + a healthy soccer cell.
    for day in days:
        for i in range(60):
            rows.append(sm._mk("_blind", "mlb", i, "deriv", 0.75, int(__import__("random").Random(i).random() < 0.55), day))
        for i in range(200, 212):  # favorite picks in the sharp cell — all lose
            rows.append(sm._mk("favorite", "mlb", i, "deriv", 0.75, 0, day))
        for i in range(60):
            rows.append(sm._mk("_blind", "fifwc", i, "main", 0.75, int(__import__("random").Random(1000 + i).random() < 0.85), day))
        for i in range(300, 330):  # favorite picks in a healthy cell — mostly win
            rows.append(sm._mk("favorite", "fifwc", i, "main", 0.75, int(__import__("random").Random(9000 + i).random() < 0.9), day))
    res = sm.analyze(rows, n_null=300, n_boot=300)
    o = overlay(rows, res)
    c1 = ("mlb/deriv/0.60-0.80" in o["dodge_cells"])
    print(f"  [{'ok' if c1 else 'FAIL'}] sharp all-loser cell is DODGE ({o['dodge_cells']})")
    c2 = o["lift"] > 0 and o["excluded_roi"] < o["base_roi"]
    print(f"  [{'ok' if c2 else 'FAIL'}] dropping the −EV cell lifts ROI "
          f"(base {sm._f(o['base_roi'])} → overlay {sm._f(o['overlay_roi'])}, lift {sm._f(o['lift'])})")
    # no-DODGE fixture: overlay == base, lift 0
    rows2 = [r for r in rows if not (r["strategy"] == "favorite" and r["slug"].startswith("mlb"))]
    # remove the sharp blind too so no DODGE forms
    rows2 = [r for r in rows2 if not r["slug"].startswith("mlb")]
    res2 = sm.analyze(rows2, n_null=300, n_boot=300)
    o2 = overlay(rows2, res2)
    c3 = (not o2["dodge_cells"]) and (o2["lift"] == 0 or (isinstance(o2["lift"], float) and abs(o2["lift"]) < 1e-9))
    print(f"  [{'ok' if c3 else 'FAIL'}] no-DODGE fixture → overlay == base, lift {sm._f(o2['lift'])}")
    ok = c1 and c2 and c3
    print("SELF-TEST", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(0 if _self_test() else 1)
    sys.exit(main())
