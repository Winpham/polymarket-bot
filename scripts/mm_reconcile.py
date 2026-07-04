#!/usr/bin/env python3
"""
mm_reconcile — Item 6 reconciliation (brief §4c): the 115 `fpd` bot flags vs the microstructure
screen. READ-ONLY analysis — it RECOMMENDS, it does NOT mutate trader_type or delete any wallet.

The `classify_trader_types` rule (consensus.rs:1327, fpd>=400) hard-labelled 115 wallets `bot` and
308 `human`. The microstructure screen is an independent verdict. Where they DISAGREE:

  (a) old-`bot` / screen-`clean`  = burst-human FPs the fpd rule likely deleted wrongly
                                    → candidates to RESTORE to the copy pool.
  (b) old-`human` / screen-`churner` = patient-MM FNs the fpd rule missed
                                    → candidates to EXCLUDE from the pool.

Output: a human-reviewable table (wallet, old label, screen verdict, firing axis, rt/ts/sb,
overall surplus, n_positions). Also cross-checks the Python microstructure against the persisted
`router_followset` rates (must agree — same algebra).

READ-ONLY. PAPER-ONLY.
  ./mm_reconcile.py            # print + write reports/mm_reconcile.json
"""

import json
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mm_common as mc


def fpd_labels():
    out = {}
    for r in mc.q("SELECT lower(proxy_wallet), COALESCE(trader_type,'') FROM followed_traders;"):
        out[r[0]] = r[1]
    return out


def overall_surplus():
    rows = mc.wallet_event_surplus()
    by = defaultdict(list)
    ev = defaultdict(lambda: defaultdict(list))
    for r in rows:
        ev[r["wallet"]][r["ev"]].append(r["surplus"])
    out = {}
    for w, evs in ev.items():
        out[w] = float(np.mean([np.mean(v) for v in evs.values()]))
    return out


def axis(m):
    a = []
    if m["rt"] >= mc.TAU_RT:
        a.append("rt")
    if m["ts"] >= mc.TAU_2S:
        a.append("ts")
    if m["sb"] >= mc.TAU_SB:
        a.append("sb")
    return a


def crosscheck():
    """Assert Python lifetime microstructure ≈ persisted router_followset rates (same algebra)."""
    rows = mc.q("SELECT DISTINCT ON (lower(wallet)) lower(wallet), round_trip_rate, "
                "two_sided_rate, sell_buy_ratio FROM router_followset "
                "WHERE round_trip_rate IS NOT NULL ORDER BY lower(wallet), scored_at DESC;")
    micro = mc.microstructure()
    diffs = []
    for r in rows:
        w = r[0]
        if w not in micro:
            continue
        for i, k in enumerate(["rt", "ts", "sb"], start=1):
            pv = micro[w][k]
            dv = mc._fnum(r[i])
            if dv is not None and abs(pv - dv) > 0.02:
                diffs.append((w[:12], k, round(pv, 3), round(dv, 3)))
    return len(rows), diffs


def run(quiet=False):
    fpd = fpd_labels()
    micro = mc.microstructure()
    surp = overall_surplus()
    restore, exclude = [], []
    for w, m in micro.items():
        old = fpd.get(w, "")
        flagged = mc.is_churner(m)
        rec = {"wallet": w[:14], "old": old or "(none)", "screen": "churner" if flagged else "clean",
               "axis": ",".join(axis(m)) or "-",
               "rt": round(m["rt"], 3), "ts": round(m["ts"], 3), "sb": round(m["sb"], 3),
               "surplus": round(surp.get(w, float("nan")), 4) if w in surp else None,
               "n_pos": m["n_pos"]}
        if old == "bot" and not flagged:
            restore.append(rec)
        elif old == "human" and flagged:
            exclude.append(rec)
    restore.sort(key=lambda r: -(r["surplus"] or -9))
    exclude.sort(key=lambda r: -(r["ts"]))
    n_rf, diffs = crosscheck()
    res = {
        "n_fpd_bot": sum(v == "bot" for v in fpd.values()),
        "n_fpd_human": sum(v == "human" for v in fpd.values()),
        "n_restore_candidates": len(restore),
        "n_exclude_candidates": len(exclude),
        "restore_fp": restore, "exclude_fn": exclude,
        "crosscheck": {"router_followset_rows": n_rf, "n_disagree_gt_0.02": len(diffs),
                       "sample": diffs[:10]},
    }
    if not quiet:
        _print(res)
    return res


def _print(r):
    print(f"MM RECONCILE · fpd flags: {r['n_fpd_bot']} bot / {r['n_fpd_human']} human\n")
    cc = r["crosscheck"]
    ok = "OK" if cc["n_disagree_gt_0.02"] == 0 else f"{cc['n_disagree_gt_0.02']} DISAGREE"
    print(f"  crosscheck vs router_followset ({cc['router_followset_rows']} rows): {ok}  {cc['sample'][:3]}\n")
    print(f"  (a) RESTORE candidates — fpd='bot' but screen-CLEAN (burst-human FPs): {r['n_restore_candidates']}")
    print(f"      {'wallet':<16}{'axis':<8}{'rt':>7}{'ts':>7}{'sb':>7}{'surplus':>9}{'n_pos':>7}")
    for x in r["restore_fp"][:12]:
        s = 'n/a' if x['surplus'] is None else f"{x['surplus']:+.3f}"
        print(f"      {x['wallet']:<16}{x['axis']:<8}{x['rt']:>7.3f}{x['ts']:>7.3f}{x['sb']:>7.3f}{s:>9}{x['n_pos']:>7}")
    print(f"\n  (b) EXCLUDE candidates — fpd='human' but screen-CHURNER (patient-MM FNs): {r['n_exclude_candidates']}")
    print(f"      {'wallet':<16}{'axis':<8}{'rt':>7}{'ts':>7}{'sb':>7}{'surplus':>9}{'n_pos':>7}")
    for x in r["exclude_fn"][:12]:
        s = 'n/a' if x['surplus'] is None else f"{x['surplus']:+.3f}"
        print(f"      {x['wallet']:<16}{x['axis']:<8}{x['rt']:>7.3f}{x['ts']:>7.3f}{x['sb']:>7.3f}{s:>9}{x['n_pos']:>7}")


def main():
    res = run()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports",
                       "mm_reconcile.json")
    with open(out, "w") as f:
        json.dump(res, f, indent=1, default=str)
    print("\nartifact → reports/mm_reconcile.json")


if __name__ == "__main__":
    main()
