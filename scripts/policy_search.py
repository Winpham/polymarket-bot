#!/usr/bin/env python3
"""
POLICY SEARCH — evaluate candidate exclusion policies for the `favorite` book under the
overfitting guard (RUN-GARBAGE-EXCLUSION-FILTERS §1–§2).

Reuses garbage_segments.load_book / score / blind_edge (single accounting source of truth).
A POLICY is a list of named predicates; a bet is EXCLUDED if ANY predicate fires (garbage=OR).
For each policy we report, on the FULL book and on OOS folds:
  - clean-book: n, ROI(taker), belief-blind surplus, bootstrap CI
  - removed-set: n, ROI, surplus  (must be negative WITH a mechanism to justify the cut)
  - turnover retained
OOS folds:
  - TIME split: early half vs late half by first_detected_at day (fit-early / verify-late)
  - NON-FIFWC: strip the World-Cup era; a cut that only helps in FIFWC is an artifact
Sweep: --sweep AXIS scans a threshold grid and prints roi_keep / roi_cut / drag to find a plateau.

Read-only, paper-only. Writes reports/POLICY-SEARCH.json.

  ./policy_search.py                     # evaluate the candidate policies below
  ./policy_search.py --sweep liquidity   # threshold sweep for one axis
  ./policy_search.py --self-test
"""
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import garbage_segments as gs
import selection_null as sn

REPORT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "reports", "POLICY-SEARCH.json")

# ---- predicates (a bet is GARBAGE if the predicate returns True) ---------------------------
# All use AT-FIRE (initial_*) fields → decision-time, forward-valid. A predicate returns False
# when its field is null (pre-snapshot) — the cut cannot be evaluated in-sample for those bets,
# but WILL apply forward (every new signal carries the value). This is the conservative choice:
# in-sample we neither credit nor blame the 58 pre-snapshot bets to a liquidity/rank cut.
def thin_liquidity(thr):
    return lambda r: r["init_total_usd"] is not None and r["init_total_usd"] < thr

def weak_rank(thr):
    # best backer rank strictly worse than thr (higher number = worse leaderboard rank)
    return lambda r: r["init_rank"] is not None and r["init_rank"] >= thr

def payup(lo, hi):
    return lambda r: (r["entry_ask"] is not None and lo <= (r["entry_ask"] - r["entry"]) < hi)

def slug_prefix(prefixes):
    return lambda r: (r["event_slug"] or "").lower().startswith(tuple(prefixes))

def exact_score():
    return lambda r: r["fine"] == "exact-score"


# ---- policy evaluation --------------------------------------------------------------------
def apply_policy(rows, preds):
    keep, cut = [], []
    for r in rows:
        (cut if any(p(r) for p in preds) else keep).append(r)
    return keep, cut

def eval_policy(rows, blind_edge, preds):
    keep, cut = apply_policy(rows, preds)
    return {"keep": gs.score(keep, blind_edge), "cut": gs.score(cut, blind_edge),
            "n_keep": len(keep), "n_cut": len(cut)}

def fold_report(rows, blind_edge, preds):
    days = sorted(set(r["day"] for r in rows))
    mid = days[len(days) // 2] if days else None
    early = [r for r in rows if r["day"] < mid]
    late = [r for r in rows if r["day"] >= mid]
    nonfifwc = [r for r in rows if not (r["event_slug"] or "").lower().startswith(("fifwc", "world"))]
    return {
        "full": eval_policy(rows, blind_edge, preds),
        "time_early": eval_policy(early, blind_edge, preds),
        "time_late": eval_policy(late, blind_edge, preds),
        "non_fifwc": eval_policy(nonfifwc, blind_edge, preds),
        "split_day": mid,
    }


# ---- candidate policies -------------------------------------------------------------------
def candidates():
    return {
        "P0_champion (no cut)": [],
        "P1_liquidity>=1000": [thin_liquidity(1000)],
        "P2_liq1000 + rank<20cut": [thin_liquidity(1000), weak_rank(20)],
        "P3_liq1000 + rank<10cut": [thin_liquidity(1000), weak_rank(10)],
        "P4_liq1000 + rank<5cut": [thin_liquidity(1000), weak_rank(5)],
        "P5_liq1000 + payup[.01,.03]": [thin_liquidity(1000), payup(0.01, 0.03)],
        "P6_liq1000 + ucl/col/swe": [thin_liquidity(1000), slug_prefix(["ucl-", "col-", "swe-"])],
        "P7_rank<5cut only": [weak_rank(5)],
    }


def _fmt(e):
    k, c = e["keep"], e["cut"]
    ks = (f"KEEP n={k['n']:>3} ROIt={k.get('roi_taker',0):>+6.2f}% "
          f"surp={('%+.1f' % k['surplus']) if k.get('surplus') is not None else ' n/a':>6} "
          f"CI[{k.get('ci_lo',0):>+5.1f},{k.get('ci_hi',0):>+5.1f}]") if k.get("n") else "KEEP n=0"
    cs = (f"CUT n={c['n']:>3} ROIt={c.get('roi_taker',0):>+7.2f}% "
          f"$drag={c.get('pnl_taker',0):>+7.1f}") if c.get("n") else "CUT n=0"
    return ks + "  |  " + cs


def run():
    rows = gs.load_book()
    be = gs.load_blind_edge()
    out = {}
    print(f"POLICY SEARCH · favorite book n={len(rows)} · at-fire fields · corrected fee\n" + "=" * 104)
    for name, preds in candidates().items():
        fr = fold_report(rows, be, preds)
        out[name] = fr
        print(f"\n[{name}]  (time split @ {fr['split_day']})")
        for fold in ("full", "time_early", "time_late", "non_fifwc"):
            print(f"  {fold:<11} {_fmt(fr[fold])}")
    with open(REPORT, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nwrote {REPORT}")
    return 0


def sweep(axis):
    rows = gs.load_book()
    be = gs.load_blind_edge()
    grids = {
        "liquidity": [(t, [thin_liquidity(t)]) for t in (0, 250, 500, 750, 1000, 1250, 1500, 2000, 2500)],
        "rank": [(t, [weak_rank(t)]) for t in (3, 4, 5, 7, 10, 15, 20, 30)],
        "rank_in_liquid": [(t, [thin_liquidity(1000), weak_rank(t)]) for t in (3, 4, 5, 7, 10, 15, 20, 30)],
    }
    if axis not in grids:
        sys.exit(f"unknown axis; choose {list(grids)}")
    print(f"SWEEP {axis} · full book (cut = ANY predicate)\n" + "-" * 90)
    print(f"{'thr':>6} {'n_keep':>7} {'roi_keep':>9} {'surp_keep':>10} {'n_cut':>6} {'roi_cut':>9} {'drag':>9}")
    for t, preds in grids[axis]:
        e = eval_policy(rows, be, preds)
        k, c = e["keep"], e["cut"]
        print(f"{t:>6} {k['n']:>7} {k.get('roi_taker',0):>+9.2f} "
              f"{(k.get('surplus') if k.get('surplus') is not None else 0):>+10.2f} "
              f"{c.get('n',0):>6} {(c.get('roi_taker') if c.get('n') else 0):>+9.2f} "
              f"{(c.get('pnl_taker') if c.get('n') else 0):>+9.1f}")
    return 0


def bbgate():
    """Belief-blind selection-null gate on the converged keep-set (in-sample, permutation p).
    Mirrors selection_null: observed = event-clustered mean (a - blind_edge[band]); null =
    same over (band,day)-matched random draws from the _blind universe. Reports p_emp + LB."""
    import csv, io, random, subprocess
    from math import sqrt
    rows = gs.load_book()
    # _blind universe with (band, day)
    sql = ("SELECT COALESCE(initial_mean_price,mean_price) AS entry,(outcome_won::int) AS won,"
           "COALESCE(event_slug,condition_id) AS ev,"
           "to_char(first_detected_at AT TIME ZONE 'UTC','YYYY-MM-DD') AS day "
           "FROM consensus_signals WHERE resolved AND strategy='_blind'")
    out = subprocess.run(gs.PG + ["-c", sql], capture_output=True, text=True)
    blind_cells = defaultdict(list)
    band_edge = defaultdict(list)
    for r in csv.DictReader(io.StringIO(out.stdout)):
        p = float(r["entry"]); b = sn.band(p); a = int(r["won"]) - p
        blind_cells[(b, r["day"])].append((r["ev"], a))
        band_edge[b].append(a)
    blind_edge = {b: sum(v) / len(v) for b, v in band_edge.items()}
    POLICIES = {"champion": [], "liq1000": [thin_liquidity(1000)],
                "liq1000+rank<5": [thin_liquidity(1000), weak_rank(5)],
                "liq1000+rank<10": [thin_liquidity(1000), weak_rank(10)]}
    print("BELIEF-BLIND GATE (selection_null statistic, in-sample keep-set) · 2000 draws\n" + "-" * 78)
    print(f"{'policy':<20}{'n_ev':>6}{'surplus':>10}{'null_sd':>9}{'z':>7}{'p_emp':>9}{'LB(obs-1.64sd)':>16}")
    res = {}
    for name, preds in POLICIES.items():
        keep, _ = apply_policy(rows, preds)
        picks = [(r["event_slug"] or r["cond"], r["band"], r["surplus_a"]) for r in keep]
        obs, n_ev = sn.clustered_surplus(picks, blind_edge)
        meta = [(r["band"], r["day"]) for r in keep]
        rng = random.Random(sn.SEED)
        draws = sn.null_pvalue(meta, blind_cells, blind_edge, rng, 2000)
        mu = sum(draws) / len(draws)
        sd = sqrt(sum((d - mu) ** 2 for d in draws) / len(draws)) if len(draws) > 1 else float("nan")
        z = (obs - mu) / sd if sd else float("nan")
        p_emp = sum(1 for d in draws if d >= obs) / len(draws)
        lb = obs - 1.64 * sd
        res[name] = dict(n_ev=n_ev, surplus=round(100 * obs, 2), null_sd=round(100 * sd, 2),
                         z=round(z, 2), p_emp=p_emp, lb=round(100 * lb, 2))
        print(f"{name:<20}{n_ev:>6}{100*obs:>+9.2f}%{100*sd:>+8.2f}%{z:>7.2f}{p_emp:>9.4f}{100*lb:>+15.2f}%")
    return res


CONVERGED = [thin_liquidity(1000), weak_rank(5)]

def residual():
    """Apply the CONVERGED policy, then scan the KEEP set across every axis for a remaining
    structural negative slice AT POWER (n>=20 w/ mechanism, else n>=30). Prints candidates."""
    rows = gs.load_book()
    be = gs.load_blind_edge()
    keep, _ = apply_policy(rows, CONVERGED)
    print(f"RESIDUAL SCAN · converged keep-set n={len(keep)} · flag: ROIt<0 AND surplus<0 AND n>=20\n" + "-" * 92)
    flagged = []
    for axis, slc in gs.axis_slices(keep).items():
        for label, rs in slc.items():
            if len(rs) < 8:
                continue
            m = gs.score(rs, be)
            neg = m["roi_taker"] < 0 and (m["surplus"] is not None and m["surplus"] < 0)
            at_power = m["n"] >= 20
            if neg:
                tag = "AT-POWER" if at_power else f"below-support(n={m['n']})"
                flagged.append((axis, label, m, at_power))
                print(f"  [{axis}] {label:<22} n={m['n']:>3} ROIt={m['roi_taker']:>+6.2f}% "
                      f"surp={m['surplus']:>+6.2f}% $drag={m['pnl_taker']:>+7.1f}  {tag}")
    atp = [f for f in flagged if f[3]]
    print(f"\n  negative slices at power (n>=20): {len(atp)}")
    if not atp:
        print("  → NO structural negative slice survives at power. Remaining negatives are "
              "below the support floor (power-limited / irreducible noise).")
    return 0


def _self_test():
    rows = [{"init_total_usd": 500, "init_rank": 8, "entry_ask": 0.82, "entry": 0.80,
             "event_slug": "ucl-x", "fine": "moneyline"},
            {"init_total_usd": 5000, "init_rank": 2, "entry_ask": 0.80, "entry": 0.80,
             "event_slug": "fifwc-x", "fine": "exact-score"}]
    ok = True
    keep, cut = apply_policy(rows, [thin_liquidity(1000)])
    ok &= len(cut) == 1 and cut[0]["init_total_usd"] == 500
    keep, cut = apply_policy(rows, [weak_rank(5)])
    ok &= len(cut) == 1 and cut[0]["init_rank"] == 8
    keep, cut = apply_policy(rows, [payup(0.01, 0.03)])
    ok &= len(cut) == 1 and cut[0]["entry_ask"] == 0.82
    keep, cut = apply_policy(rows, [exact_score()])
    ok &= len(cut) == 1 and cut[0]["fine"] == "exact-score"
    print("self-test:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(0 if _self_test() else 1)
    if "--sweep" in sys.argv:
        sys.exit(sweep(sys.argv[sys.argv.index("--sweep") + 1]))
    if "--bbgate" in sys.argv:
        bbgate()
        sys.exit(0)
    if "--residual" in sys.argv:
        sys.exit(residual())
    sys.exit(run())
