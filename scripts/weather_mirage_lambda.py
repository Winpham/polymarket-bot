#!/usr/bin/env python3
"""
MIRAGE test — does the BLIND favourite band get the same forward CLV as the SHARP-selected weather_fav?

The committed 1c140f1 cert claims the sharp selection is decorative ("the band does the work") on 2 days.
This adjudicates it on the 9-day harvest edge window: compute day-clustered forward CLV (spread-neutral
tape-print basis, leak-free, controlled horizons) for BOTH the blind favourite-band pool and the
sharp-selected picks, and compare. If blind CLV ≈ sharp CLV ⇒ decorative; if sharp CLV > blind ⇒ the
selection carries information.

  ./weather_mirage_lambda.py --selftest
  ./weather_mirage_lambda.py
"""
import argparse
import csv
import io
import pickle
import subprocess
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import weather_fav_4bar_harvest as W  # noqa: E402  (reuse close_at, entry_from_tape, day_boot, psql, q_lit)

BLIND_SQL = f"""
SELECT condition_id, outcome_index, initial_mean_price AS atfire, (outcome_won::int) AS won,
       EXTRACT(epoch FROM first_detected_at)::bigint AS ts0,
       EXTRACT(epoch FROM resolved_at)::bigint AS res_ts,
       to_char(resolved_at AT TIME ZONE 'UTC','YYYY-MM-DD') AS day
FROM consensus_signals
WHERE strategy='_blind' AND slug ~ 'highest-temperature' AND resolved AND outcome_won IS NOT NULL
  AND initial_mean_price IS NOT NULL AND first_detected_at IS NOT NULL AND resolved_at IS NOT NULL;
"""


def clv_pool(picks, tape, band, hz, entry_basis="tape"):
    lo, hi = band
    clv_d = defaultdict(list)
    n_cov = 0
    sel = [p for p in picks if lo <= p["atfire"] < hi]
    for p in sel:
        e = p["atfire"] if entry_basis == "atfire" else W.entry_from_tape(
            tape.get((p["cond"], p["oi"]), []), p["ts0"])
        if e is None:
            continue
        c = W.close_at(tape.get((p["cond"], p["oi"]), []), p["res_ts"], hz, after_ts=p["ts0"])
        if c is None:
            continue
        n_cov += 1
        clv_d[p["day"]].append(c - e)
    r = W.day_boot(clv_d)
    return {"n_sel": len(sel), "n_cov": n_cov, "coverage": round(n_cov / len(sel), 3) if sel else 0,
            "clv": round(r["point"], 4) if r else None,
            "clv_ci": [round(r["lo"], 4), round(r["hi"], 4)] if r else None,
            "p_le0": round(r["p_le0"], 3) if r else None, "n_days": r["n_days"] if r else 0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        # trivial: clv_pool on a single synthetic pick/day
        tp = {("c", 0): [(0, 0.80), (100, 0.85), (1000, 0.90)]}
        pk = [{"cond": "c", "oi": 0, "atfire": 0.80, "won": 1, "ts0": 0, "res_ts": 100000, "day": "d1"}]
        r = clv_pool(pk, tp, [0.71, 0.98], None)
        assert r["n_cov"] == 1, r
        print("weather_mirage_lambda selftest: PASS")
        return

    sharp_picks, sharp_tape = W.build()  # sharp-selected picks + their tape (cache)
    sharp_days = sorted({p["day"] for p in sharp_picks})

    # blind pool, restricted to the sharp window's resolution days (fair comparison)
    blind = []
    for r in W.psql(BLIND_SQL):
        if r["day"] in sharp_days:
            blind.append({"cond": r["condition_id"], "oi": int(r["outcome_index"]),
                          "atfire": float(r["atfire"]), "won": int(r["won"]),
                          "ts0": int(r["ts0"]), "res_ts": int(r["res_ts"]), "day": r["day"]})
    print(f"blind pool: {len(blind)} favourites over {len({b['day'] for b in blind})} days "
          f"(window {sharp_days[0]}..{sharp_days[-1]})", file=sys.stderr)

    # fetch harvest tape for blind conds not already cached
    need = sorted({b["cond"] for b in blind} - {p["cond"] for p in sharp_picks})
    btape = dict(sharp_tape)
    for i in range(0, len(need), W.BATCH):
        ch = need[i:i + W.BATCH]
        for r in W.psql(f"""SELECT condition_id, outcome_index, EXTRACT(epoch FROM ts)::bigint t, price p
                            FROM harvest_fills WHERE side='BUY' AND condition_id IN ({W.q_lit(ch)});"""):
            btape.setdefault((r["condition_id"], int(r["outcome_index"])), []).append(
                (int(r["t"]), float(r["p"])))
        sys.stderr.write(f"\r  blind tape {min(i+W.BATCH,len(need)):,}/{len(need):,}")
    sys.stderr.write("\n")
    for k in btape:
        btape[k] = sorted(btape[k])

    print("\n=== MIRAGE: blind favourite-band CLV vs sharp-selected CLV (tape spread-neutral, leak-free) ===")
    for band in ([0.71, 0.90], [0.71, 0.98]):
        print(f"\nBAND {band[0]:.2f}-{band[1]:.2f}")
        print(f"  {'hz':>4s} {'pool':>6s} {'n':>4s} {'days':>4s} {'CLV':>8s} {'CI':>20s} {'p(CLV<=0)':>9s}")
        for hz, lbl in [(12, "12h"), (6, "6h"), (None, "last")]:
            s = clv_pool(sharp_picks, sharp_tape, band, hz)
            b = clv_pool(blind, btape, band, hz)
            for nm, r in [("sharp", s), ("blind", b)]:
                print(f"  {lbl:>4s} {nm:>6s} {r['n_cov']:>4d} {r['n_days']:>4d} "
                      f"{(r['clv'] if r['clv'] is not None else float('nan')):>+8.4f} "
                      f"{str(r['clv_ci']):>20s} {str(r['p_le0']):>9s}")


if __name__ == "__main__":
    main()
