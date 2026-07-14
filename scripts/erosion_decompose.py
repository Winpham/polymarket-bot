#!/usr/bin/env python3
"""
PHASE B -- decompose the favorite-edge erosion across the seven plausible axes.

READ PHASE A FIRST. The day-block permutation null returns BH-adjusted p = 0.086: a cold streak
from a CONSTANT +8% edge is NOT excluded. Everything below is therefore DESCRIPTIVE attribution
under a null that survived. Do not read any axis here as a proven cause. In particular, do NOT
turn any of these splits into an exclusion rule -- that is the exact data-dredge this run exists
to avoid.

Axes (all on the stationary `imp` basis, match-clustered at superkey, fee 0.03p(1-p)):
  1. edge decay        -- rolling skill (favorite - _blind, same band mix) vs rolling raw ROI
  2. crowding          -- is the _blind structural underpricing ITSELF shrinking?
  3. mix shift         -- category / tournament composition of firing, recent vs earlier
  4. band drift        -- entry-price distribution over time
  5. convergence qual. -- net_count / n_backers of recent signals vs earlier
  6. pipeline artifact -- capture coverage + resolution completeness over time
  7. cell contamination-- leave-one-DAY-out and leave-one-CATEGORY-out on the recent window

Read-only. Emits reports/EROSION-DECOMPOSITION.json.
  --selftest exercises the estimators.
"""

import json
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import effective_n as EN  # noqa: E402
import erosion_lib as E  # noqa: E402
import market_taxonomy as TAX  # noqa: E402

RECENT_K = 5  # days; the window the brief flags. Sensitivity at k=3,4,7 reported too.


def _roi(units):
    tt = sum(u[1] for u in units)
    return (sum(u[0] for u in units) / tt) if tt else 0.0


def _lb(units):
    """Cluster-robust 95% LB on ROI-on-turnover. Each match is its own cluster here
    (legs are already collapsed), so CR reduces to small-cluster t on the match surplus."""
    if len(units) < 3:
        return None
    tt = sum(u[1] for u in units)
    if tt <= 0:
        return None
    # per-match contribution to ROI, scaled so the mean equals ROI-on-turnover
    n = len(units)
    contrib = np.array([u[0] / (tt / n) for u in units], dtype=float)
    theta = float(contrib.mean())
    se = float(contrib.std(ddof=1) / np.sqrt(n))
    t = EN._t_ppf(0.95, n - 1)
    return theta - t * se


def enrich(rows, basis="imp"):
    """Band-filtered favorite legs + category/market-type, plus the blind baseline per band."""
    ls = E.legs(rows, basis=basis)
    blind, nb = E.blind_edge_by_band(rows, basis=basis)
    for l in ls:
        cat, mtype = TAX.classify(l["slug"], l["title"])
        l["cat"] = cat
        l["mtype"] = mtype
        b = min(int(l["p"] * nb), nb - 1)
        l["blind_band_edge"] = blind.get(b, 0.0)
    return ls, blind, nb


def match_units(ls, skill=False):
    """{superkey: (pnl, turnover)} with optional blind subtraction (skill)."""
    agg = defaultdict(lambda: [0.0, 0.0])
    for l in ls:
        g, t = E.pnl(l)
        if skill:
            g -= l["blind_band_edge"] * t
        agg[l["key"]][0] += g
        agg[l["key"]][1] += t
    return {k: tuple(v) for k, v in agg.items()}


def window_split(ls, k):
    days = sorted({l["d"] for l in ls})
    recent = set(days[-k:])
    mday = E.match_day(ls)
    rec_keys = {m for m, d in mday.items() if d in recent}
    return rec_keys, days[-k:], days[:-k]


def axis_1_2_decay_and_crowding(rows, ls, blind, nb):
    """Split raw ROI into structural (blind) + skill (surplus). Which one moved?"""
    out = {"windows": []}
    for k in (3, 4, 5, 7):
        rec_keys, rdays, edays = window_split(ls, k)
        rec = [l for l in ls if l["key"] in rec_keys]
        ear = [l for l in ls if l["key"] not in rec_keys]
        row = {"k_days": k, "recent_days": rdays}
        for name, sub in (("recent", rec), ("earlier", ear)):
            raw_u = match_units(sub, skill=False)
            sk_u = match_units(sub, skill=True)
            structural = E.blind_expected(sub, blind, nb)
            row[name] = {
                "matches": len(raw_u),
                "raw_roi": _roi(list(raw_u.values())),
                "structural_blind_roi": structural,   # AXIS 2: is softness itself dying?
                "skill_surplus": _roi(list(sk_u.values())),  # AXIS 1: is OUR edge dying?
                "skill_lb95": _lb(list(sk_u.values())),
            }
        row["delta_raw"] = row["recent"]["raw_roi"] - row["earlier"]["raw_roi"]
        row["delta_structural"] = (row["recent"]["structural_blind_roi"]
                                   - row["earlier"]["structural_blind_roi"])
        row["delta_skill"] = row["recent"]["skill_surplus"] - row["earlier"]["skill_surplus"]
        # attribution: how much of the raw drop is structural vs skill
        if abs(row["delta_raw"]) > 1e-9:
            row["pct_from_structural"] = 100.0 * row["delta_structural"] / row["delta_raw"]
            row["pct_from_skill"] = 100.0 * row["delta_skill"] / row["delta_raw"]
        out["windows"].append(row)
    return out


def axis_3_mix(ls, k=RECENT_K):
    """Category / market-type composition + per-cell ROI, recent vs earlier.
    Turnover-share shift x cell-ROI = the MIX contribution to the drop."""
    rec_keys, rdays, edays = window_split(ls, k)
    res = {"k_days": k, "recent_days": rdays, "by_cat": {}, "mix_effect": {}}

    def cells(sub, keyfn):
        agg = defaultdict(list)
        for l in sub:
            agg[keyfn(l)].append(l)
        return agg

    rec = [l for l in ls if l["key"] in rec_keys]
    ear = [l for l in ls if l["key"] not in rec_keys]

    all_cats = sorted({l["cat"] for l in ls})
    tot_r = sum(l["p"] for l in rec) or 1.0
    tot_e = sum(l["p"] for l in ear) or 1.0
    rc, ec = cells(rec, lambda l: l["cat"]), cells(ear, lambda l: l["cat"])

    # Oaxaca-style split of the raw-ROI change into MIX (weights moved) vs PERF (cells got worse)
    mix_term = perf_term = 0.0
    for c in all_cats:
        r, e = rc.get(c, []), ec.get(c, [])
        wr = sum(l["p"] for l in r) / tot_r
        we = sum(l["p"] for l in e) / tot_e
        roi_r = _roi(list(match_units(r).values())) if r else None
        roi_e = _roi(list(match_units(e).values())) if e else None
        res["by_cat"][c] = {
            "recent": {"matches": len({l["key"] for l in r}), "legs": len(r),
                       "turnover_share": wr, "roi": roi_r},
            "earlier": {"matches": len({l["key"] for l in e}), "legs": len(e),
                        "turnover_share": we, "roi": roi_e},
            "share_delta": wr - we,
        }
        # mix effect uses the EARLIER cell performance (what the shift alone would have cost)
        if roi_e is not None:
            mix_term += (wr - we) * roi_e
        if roi_r is not None and roi_e is not None:
            perf_term += we * (roi_r - roi_e)
    res["mix_effect"] = {
        "mix_term": mix_term,           # drop explained by firing into different cells
        "perf_term": perf_term,         # drop explained by the same cells performing worse
        "note": "Oaxaca decomposition of the raw-ROI change; residual = interaction",
    }
    return res


def axis_4_band(ls, k=RECENT_K):
    rec_keys, rdays, _ = window_split(ls, k)
    out = {"k_days": k, "sub_bands": {}}
    edges = [(0.71, 0.82), (0.82, 0.90), (0.90, 0.98)]
    for lo, hi in edges:
        r = [l for l in ls if l["key"] in rec_keys and lo <= l["p"] < hi]
        e = [l for l in ls if l["key"] not in rec_keys and lo <= l["p"] < hi]
        out["sub_bands"][f"{lo}-{hi}"] = {
            "recent": {"legs": len(r), "roi": _roi(list(match_units(r).values())) if r else None},
            "earlier": {"legs": len(e), "roi": _roi(list(match_units(e).values())) if e else None},
        }
    rec_p = [l["p"] for l in ls if l["key"] in rec_keys]
    ear_p = [l["p"] for l in ls if l["key"] not in rec_keys]
    out["mean_entry_recent"] = float(np.mean(rec_p)) if rec_p else None
    out["mean_entry_earlier"] = float(np.mean(ear_p)) if ear_p else None
    return out


def axis_5_convergence(ls, k=RECENT_K):
    rec_keys, _, _ = window_split(ls, k)
    r = [l for l in ls if l["key"] in rec_keys]
    e = [l for l in ls if l["key"] not in rec_keys]
    f = lambda sub, fld: float(np.mean([x[fld] for x in sub])) if sub else None  # noqa: E731
    return {
        "k_days": k,
        "recent": {"mean_net_count": f(r, "net_count"), "mean_n_backers": f(r, "n_backers"),
                   "legs": len(r)},
        "earlier": {"mean_net_count": f(e, "net_count"), "mean_n_backers": f(e, "n_backers"),
                    "legs": len(e)},
    }


def axis_6_pipeline(rows):
    """Capture coverage + resolution completeness per day -- the artifact axis."""
    per_day = defaultdict(lambda: {"legs": 0, "with_ask": 0, "resolved": 0})
    for r in rows:
        if r["strategy"] != "favorite" or not (E.BAND_LO <= r["imp"] <= E.BAND_HI):
            continue
        d = per_day[r["d"]]
        d["legs"] += 1
        d["with_ask"] += 1 if r["ask"] is not None else 0
        d["resolved"] += 1 if r["resolved"] else 0
    out = {}
    for d, v in sorted(per_day.items()):
        out[d] = {
            "legs": v["legs"],
            "ask_coverage": v["with_ask"] / v["legs"] if v["legs"] else 0.0,
            "resolution_completeness": v["resolved"] / v["legs"] if v["legs"] else 0.0,
        }
    # the headline series is on `imp` (100% coverage) -> capture drift CANNOT drive it.
    # but the incumbent COALESCE basis WOULD be contaminated; quantify the gap for the record.
    both = [(r["ask"], r["imp"]) for r in rows
            if r["strategy"] == "favorite" and r["ask"] is not None
            and E.BAND_LO <= r["imp"] <= E.BAND_HI]
    return {
        "per_day": out,
        "ask_minus_imp_mean": float(np.mean([a - i for a, i in both])) if both else None,
        "verdict": ("headline series uses `imp` (100% coverage every day) -> the erosion is NOT a "
                    "capture-coverage artifact. NOTE: any metric on COALESCE(entry_ask, imp) IS "
                    "contaminated, because ask coverage swings ~5%->70% across the window and ask "
                    "sits above imp."),
    }


def axis_7_lodo(ls, k=RECENT_K):
    """Leave-one-DAY-out and leave-one-CATEGORY-out on the RECENT window: is one slate/cell
    dragging it, or is the softness broad?"""
    rec_keys, rdays, _ = window_split(ls, k)
    rec = [l for l in ls if l["key"] in rec_keys]
    base = _roi(list(match_units(rec).values()))
    out = {"k_days": k, "recent_roi": base, "leave_one_day_out": {}, "leave_one_cat_out": {}}
    mday = E.match_day(ls)
    for d in rdays:
        sub = [l for l in rec if mday[l["key"]] != d]
        out["leave_one_day_out"][d] = {
            "roi_without": _roi(list(match_units(sub).values())) if sub else None,
            "matches_dropped": len({l["key"] for l in rec if mday[l["key"]] == d}),
        }
    for c in sorted({l["cat"] for l in rec}):
        sub = [l for l in rec if l["cat"] != c]
        out["leave_one_cat_out"][c] = {
            "roi_without": _roi(list(match_units(sub).values())) if sub else None,
            "matches_dropped": len({l["key"] for l in rec if l["cat"] == c}),
        }
    return out


def selftest():
    ok = True
    # _roi turnover-weighting
    if abs(_roi([(1.0, 10.0), (-1.0, 10.0)]) - 0.0) > 1e-9:
        print("  FAIL: _roi zero case"); ok = False
    if abs(_roi([(2.0, 10.0)]) - 0.2) > 1e-9:
        print("  FAIL: _roi single"); ok = False
    else:
        print("  ok: _roi turnover-weighted")
    # _lb below point estimate, and wider for noisier data
    tight = _lb([(0.1, 1.0)] * 20)
    noisy = _lb([(0.1 + (1 if i % 2 else -1) * 0.5, 1.0) for i in range(20)])
    if tight is None or noisy is None or not (noisy < tight):
        print(f"  FAIL: _lb not noise-sensitive tight={tight} noisy={noisy}"); ok = False
    else:
        print(f"  ok: _lb noise-sensitive ({tight:.3f} tight vs {noisy:.3f} noisy)")
    # Oaxaca: pure mix shift with identical cell perf => perf_term ~ 0
    fake = []
    for i in range(10):
        fake.append({"key": f"e{i}", "d": "2026-07-01", "p": 0.8, "won": i < 9, "cat": "A",
                     "slug": "", "title": "", "blind_band_edge": 0.0})
    for i in range(10):
        fake.append({"key": f"r{i}", "d": "2026-07-13", "p": 0.8, "won": i < 9, "cat": "B",
                     "slug": "", "title": "", "blind_band_edge": 0.0})
    m = axis_3_mix(fake, k=1)
    if abs(m["mix_effect"]["perf_term"]) > 1e-9:
        print(f"  FAIL: perf_term should be ~0 on pure mix shift, got {m['mix_effect']['perf_term']}")
        ok = False
    else:
        print("  ok: Oaxaca perf_term ~0 under pure mix shift")
    print("SELFTEST", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        sys.exit(selftest())

    rows = E.fetch()
    ls, blind, nb = enrich(rows)

    out = {
        "basis": "imp (stationary; entry_ask coverage is non-stationary and unusable for trend)",
        "phase_a_gate": {
            "day_block_BH_min_p": 0.086,
            "variance_ruled_out": False,
            "reading": "A constant-edge cold streak is NOT excluded. Every axis below is "
                       "DESCRIPTIVE, not causal. No exclusion rule may be derived from it.",
        },
        "axis_1_2_decay_and_crowding": axis_1_2_decay_and_crowding(rows, ls, blind, nb),
        "axis_3_mix_shift": axis_3_mix(ls),
        "axis_4_band_drift": axis_4_band(ls),
        "axis_5_convergence_quality": axis_5_convergence(ls),
        "axis_6_pipeline_artifact": axis_6_pipeline(rows),
        "axis_7_cell_contamination": axis_7_lodo(ls),
        "blind_edge_by_band": {str(k): v for k, v in blind.items()},
    }
    os.makedirs("reports", exist_ok=True)
    with open("reports/EROSION-DECOMPOSITION.json", "w") as f:
        json.dump(out, f, indent=2)

    # --- console read
    print("AXIS 1+2 — is it SKILL decaying, or SOFTNESS (structural) being arbitraged away?")
    print(f"{'k':>2s} {'M_rec':>5s} {'raw_rec':>8s} {'raw_ear':>8s} {'blind_rec':>9s} "
          f"{'blind_ear':>9s} {'skill_rec':>9s} {'skill_ear':>9s}")
    for w in out["axis_1_2_decay_and_crowding"]["windows"]:
        r, e = w["recent"], w["earlier"]
        print(f"{w['k_days']:2d} {r['matches']:5d} {100*r['raw_roi']:7.1f}% {100*e['raw_roi']:7.1f}% "
              f"{100*r['structural_blind_roi']:8.2f}% {100*e['structural_blind_roi']:8.2f}% "
              f"{100*r['skill_surplus']:8.1f}% {100*e['skill_surplus']:8.1f}%")

    print("\nAXIS 3 — MIX shift by category (turnover share + cell ROI)")
    m = out["axis_3_mix_shift"]
    print(f"{'category':22s} {'shr_rec':>7s} {'shr_ear':>7s} {'d_shr':>6s} "
          f"{'roi_rec':>8s} {'roi_ear':>8s} {'M_rec':>5s}")
    for c, v in sorted(m["by_cat"].items(), key=lambda x: -abs(x[1]["share_delta"])):
        rr = v["recent"]["roi"]
        re_ = v["earlier"]["roi"]
        print(f"{c:22s} {100*v['recent']['turnover_share']:6.1f}% "
              f"{100*v['earlier']['turnover_share']:6.1f}% {100*v['share_delta']:+5.1f} "
              f"{(f'{100*rr:7.1f}%' if rr is not None else '      -'):>8s} "
              f"{(f'{100*re_:7.1f}%' if re_ is not None else '      -'):>8s} "
              f"{v['recent']['matches']:5d}")
    me = m["mix_effect"]
    print(f"  -> MIX term {100*me['mix_term']:+.2f}pt | PERF term {100*me['perf_term']:+.2f}pt")

    print("\nAXIS 4 — band drift")
    b = out["axis_4_band_drift"]
    for sb, v in b["sub_bands"].items():
        rr, re_ = v["recent"]["roi"], v["earlier"]["roi"]
        print(f"  {sb}: recent {v['recent']['legs']:3d} legs "
              f"{(f'{100*rr:6.1f}%' if rr is not None else '     -')} | "
              f"earlier {v['earlier']['legs']:3d} legs "
              f"{(f'{100*re_:6.1f}%' if re_ is not None else '     -')}")
    print(f"  mean entry: recent {b['mean_entry_recent']:.3f} vs earlier {b['mean_entry_earlier']:.3f}")

    print("\nAXIS 5 — convergence quality")
    c5 = out["axis_5_convergence_quality"]
    print(f"  net_count  recent {c5['recent']['mean_net_count']:.2f} vs earlier "
          f"{c5['earlier']['mean_net_count']:.2f}")
    print(f"  n_backers  recent {c5['recent']['mean_n_backers']:.2f} vs earlier "
          f"{c5['earlier']['mean_n_backers']:.2f}")

    print("\nAXIS 6 — pipeline / capture")
    print(f"  ask-minus-imp (same legs): {out['axis_6_pipeline_artifact']['ask_minus_imp_mean']:+.4f}")
    print(f"  {out['axis_6_pipeline_artifact']['verdict']}")

    print("\nAXIS 7 — recent-window LODO")
    l7 = out["axis_7_cell_contamination"]
    print(f"  recent-window ROI = {100*l7['recent_roi']:.1f}%")
    for d, v in l7["leave_one_day_out"].items():
        print(f"    without {d} ({v['matches_dropped']:2d} M): {100*v['roi_without']:6.1f}%")
    for c, v in l7["leave_one_cat_out"].items():
        print(f"    without cat {c:20s} ({v['matches_dropped']:2d} M): {100*v['roi_without']:6.1f}%")
    print("\n-> reports/EROSION-DECOMPOSITION.json")


if __name__ == "__main__":
    main()
