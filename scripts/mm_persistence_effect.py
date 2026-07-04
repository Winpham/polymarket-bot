#!/usr/bin/env python3
"""
mm_persistence_effect — Tier-2, LABEL-FREE, the BINDING validation of the MM screen (brief §4b).

THE QUESTION: does excluding the wallets the microstructure screen flags actually make the
survivor pool MORE PERSISTENT out-of-sample? Operationally: split each pool wallet's resolved-BUY
picks into an EARLY and a LATE half by placement day; measure the cross-wallet correlation between
early-half mean surplus and late-half mean surplus (does a trader's early selection predict their
late selection); compute that correlation WITH vs WITHOUT the screen-flagged wallets.

WHY THIS IS THE BINDING TEST (Tier-1 is not sufficient): Tier-1's labeled AUC is partly circular
(the labels partly derive from the same two-sided heuristic under test). Tier-2 asks whether the
screen improves a quantity nobody hand-labeled — forward persistence of the copy pool.

TWO METHODOLOGY GUARDS THE BLUEPRINT MISSED, both mandatory here:
  (1) MATCHED-SUBSET NULL. A positive Δcorr from removing ANY high-variance/high-volume subset of
      a ~30-wallet pool is mechanically expected. So we remove random subsets of the SAME size,
      MATCHED on (volume, n_positions) strata, ≥N_PERM times, build the null of Δcorr, and require
      the real removal to sit in the right tail (p ≤ 0.05). A bare Δcorr is NOT evidence.
  (2) AS-OF / LEAKAGE. The screen verdict that decides who to remove is computed from EARLY fills
      ONLY (mm_common.microstructure(asof=cutoff)); it must not peek at the late outcomes it is
      correlated against.

POWER: at n≈30-80 wallets a Pearson r has a very wide CI (Fisher-z se = 1/sqrt(n-3)). If the real
Δcorr sits inside the null bulk, OR the correlation CIs swamp the effect, the verdict is
INDETERMINATE-BY-POWER — reported plainly, with the N (months of independent forward clusters) it
would take. We do NOT dress an indeterminate result as a pass.

DATA CAVEAT (headline, honest): on this record the resolved-BUY fills are dominated by a large
backfill crawl over 2026-06-30..07-03, and `ts` on backfilled rows is a crawl stamp, so the
early/late split is only weakly temporal. We therefore ALSO run a parity split-half robustness
cross-check (--parity), and treat the temporal read as suggestive, not forward-certified.

READ-ONLY. PAPER-ONLY. No DB writes, no order path.

Modes:
  ./mm_persistence_effect.py                 # live; default cutoff 2026-07-01, min_ev 8
  ./mm_persistence_effect.py --cutoff DATE --min-ev N --nperm K
  ./mm_persistence_effect.py --parity        # split-half by event-key parity (crawl-stamp robust)
  ./mm_persistence_effect.py --selftest      # synthetic: an MM-injected pool must verdict GO
"""

import hashlib
import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mm_common as mc
import portfolio_concentration as pc

CUTOFF = "2026-07-01"
MIN_EV = 8
N_PERM = 2000
SEED = 20260704
Z = 1.96


def _pearson(xs, ys):
    if len(xs) < 4:
        return None
    x = np.asarray(xs, float)
    y = np.asarray(ys, float)
    if x.std() == 0 or y.std() == 0:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def _fisher_ci(r, n):
    """Two-sided 95% CI for a Pearson r via Fisher z. Returns (lo, hi) or (None,None)."""
    if r is None or n < 4 or abs(r) >= 1.0:
        return (None, None)
    z = 0.5 * math.log((1 + r) / (1 - r))
    se = 1.0 / math.sqrt(n - 3)
    lo, hi = z - Z * se, z + Z * se
    return (math.tanh(lo), math.tanh(hi))


def build_pool(cutoff, min_ev, parity=False):
    """Collapse fills to (wallet, match_key) event surplus, split each wallet's events into two
    disjoint halves, and keep wallets with >= min_ev events in BOTH halves.

    parity=False → temporal split by placement day at `cutoff` (brief's early/late).
    parity=True  → split by hash-parity of the match key (crawl-stamp-robust split-half)."""
    rows = mc.wallet_event_surplus()
    # collapse to (wallet, match_key): mean fill-surplus, earliest day
    ev = defaultdict(lambda: {"s": [], "day": None})
    for r in rows:
        mk = pc.match_key(r["event_slug"], r["ev"])
        key = (r["wallet"], mk)
        ev[key]["s"].append(r["surplus"])
        d = r["day"]
        if ev[key]["day"] is None or d < ev[key]["day"]:
            ev[key]["day"] = d
    early = defaultdict(dict)
    late = defaultdict(dict)
    for (w, mk), v in ev.items():
        s = float(np.mean(v["s"]))
        if parity:
            side_late = (int(hashlib.md5(mk.encode()).hexdigest(), 16) & 1) == 1
        else:
            side_late = v["day"] >= cutoff
        (late if side_late else early)[w][mk] = s
    pool = [w for w in set(list(early) + list(late))
            if len(early[w]) >= min_ev and len(late[w]) >= min_ev]
    return pool, early, late


def read_corr(pool, early, late):
    xs = [float(np.mean(list(early[w].values()))) for w in pool]
    ys = [float(np.mean(list(late[w].values()))) for w in pool]
    return _pearson(xs, ys), xs, ys


def strata(pool, cov):
    """4 covariate strata by median split of (log vol, log n_pos), as-of/leak-free covariates."""
    vols = np.array([math.log1p(cov[w]["vol"]) for w in pool])
    nps = np.array([math.log1p(cov[w]["n_pos"]) for w in pool])
    mv, mn = np.median(vols), np.median(nps)
    st = {}
    for w in pool:
        a = int(math.log1p(cov[w]["vol"]) >= mv)
        b = int(math.log1p(cov[w]["n_pos"]) >= mn)
        st[w] = (a, b)
    return st


def matched_null(pool, early, late, corr_with, flagged, cov, nperm, seed):
    """Δcorr null: remove random size-k subsets MATCHED to the flagged set's (vol,npos)-strata
    composition; return null Δcorr array + the observed Δcorr + p_emp."""
    st = strata(pool, cov)
    by_cell = defaultdict(list)
    for w in pool:
        by_cell[st[w]].append(w)
    flag_cell_ct = defaultdict(int)
    for w in flagged:
        flag_cell_ct[st[w]] += 1
    rng = np.random.default_rng(seed)
    # observed
    keep = [w for w in pool if w not in flagged]
    corr_obs, _, _ = read_corr(keep, early, late)
    dcorr_obs = None if (corr_obs is None or corr_with is None) else corr_obs - corr_with
    null = []
    for _ in range(nperm):
        drop = set()
        ok = True
        for cell, k in flag_cell_ct.items():
            avail = by_cell.get(cell, [])
            if len(avail) < k:
                ok = False
                break
            idx = rng.choice(len(avail), size=k, replace=False)
            for i in idx:
                drop.add(avail[i])
        if not ok:
            continue
        keepn = [w for w in pool if w not in drop]
        c, _, _ = read_corr(keepn, early, late)
        if c is not None and corr_with is not None:
            null.append(c - corr_with)
    null = np.array(null, float)
    p = None
    if dcorr_obs is not None and len(null):
        p = float((np.sum(null >= dcorr_obs) + 1) / (len(null) + 1))
    return dcorr_obs, corr_obs, null, p


def verdict(dcorr, p, corr_with, corr_without, n, ci_with, ci_without):
    reasons = []
    if dcorr is None or corr_without is None:
        return "INDETERMINATE-BY-POWER", "pool too small / degenerate to correlate after removal"
    # power: does the corr CI swamp the effect?
    ci_w = ci_without
    ci_span = None if ci_w[0] is None else (ci_w[1] - ci_w[0])
    swamped = (ci_span is not None and abs(dcorr) < 0.5 * ci_span)
    if p is None:
        return "INDETERMINATE-BY-POWER", "matched null could not be built (strata too thin)"
    if dcorr > 0 and p <= 0.05 and not swamped:
        return "GO", (f"Δcorr {dcorr:+.3f} beyond matched-subset null (p={p:.3f}) and not swamped "
                      f"by the corr CI (±{ci_span/2:.2f})")
    if dcorr <= 0:
        return "NO-GO", f"removing flagged wallets does NOT raise persistence (Δcorr {dcorr:+.3f})"
    if p > 0.05:
        return "INDETERMINATE-BY-POWER", (f"Δcorr {dcorr:+.3f} is positive but inside the matched "
                                          f"null (p={p:.3f}) — mechanically expected from removing "
                                          f"high-leverage points, not screen-specific")
    return "INDETERMINATE-BY-POWER", (f"Δcorr {dcorr:+.3f} clears the null (p={p:.3f}) but is "
                                      f"swamped by the corr CI (±{ci_span/2:.2f}) at n={n}")


def run(cutoff=CUTOFF, min_ev=MIN_EV, nperm=N_PERM, parity=False, seed=SEED, quiet=False):
    pool, early, late = build_pool(cutoff, min_ev, parity=parity)
    cov = mc.microstructure(asof=None if parity else cutoff)  # leak-free covariates + as-of screen
    # wallets in pool but absent from as-of micro (no early fills) → treat clean, drop from screen
    flagged = set(w for w in pool if w in cov and mc.is_churner(cov[w]))
    corr_with, xs, ys = read_corr(pool, early, late)
    dcorr, corr_without, null, p = matched_null(pool, early, late, corr_with, flagged, cov, nperm, seed)
    n = len(pool)
    ci_with = _fisher_ci(corr_with, n)
    ci_without = _fisher_ci(corr_without, n - len(flagged))
    vd, why = verdict(dcorr, p, corr_with, corr_without, n, ci_with, ci_without)
    res = {
        "mode": "parity-split-half" if parity else "temporal",
        "cutoff": None if parity else cutoff, "min_ev": min_ev, "nperm": int(len(null)),
        "pool_n": n, "n_flagged_in_pool": len(flagged),
        "flagged": sorted(w[:12] for w in flagged),
        "corr_with": corr_with, "corr_without": corr_without,
        "delta_corr": dcorr, "matched_null_p": p,
        "null_mean": float(np.mean(null)) if len(null) else None,
        "null_q95": float(np.quantile(null, 0.95)) if len(null) else None,
        "ci_with": ci_with, "ci_without": ci_without,
        "verdict": vd, "why": why,
    }
    if not quiet:
        _print(res)
    return res


def _print(r):
    print(f"MM PERSISTENCE-EFFECT · {r['mode']} · "
          f"{'cutoff '+str(r['cutoff']) if r['cutoff'] else 'event-parity'} · "
          f"min_ev {r['min_ev']} · null draws {r['nperm']}\n")
    print(f"  pool wallets            : {r['pool_n']}")
    print(f"  flagged (churner) in pool: {r['n_flagged_in_pool']}  {r['flagged']}")
    cw = 'n/a' if r['corr_with'] is None else f"{r['corr_with']:+.3f}"
    co = 'n/a' if r['corr_without'] is None else f"{r['corr_without']:+.3f}"
    print(f"  early→late corr WITH flagged   : {cw}   95% CI {_cistr(r['ci_with'])}")
    print(f"  early→late corr WITHOUT flagged: {co}   95% CI {_cistr(r['ci_without'])}")
    dc = 'n/a' if r['delta_corr'] is None else f"{r['delta_corr']:+.3f}"
    nm = 'n/a' if r['null_mean'] is None else f"{r['null_mean']:+.3f}"
    nq = 'n/a' if r['null_q95'] is None else f"{r['null_q95']:+.3f}"
    pp = 'n/a' if r['matched_null_p'] is None else f"{r['matched_null_p']:.3f}"
    print(f"  Δcorr (without − with)  : {dc}")
    print(f"  matched-subset null     : mean {nm} · q95 {nq} · p_emp {pp}")
    print(f"\n  VERDICT: {r['verdict']} — {r['why']}")


def _cistr(ci):
    if ci is None or ci[0] is None:
        return "[n/a]"
    return f"[{ci[0]:+.2f}, {ci[1]:+.2f}]"


def selftest():
    """Synthetic pool: 40 'humans' with persistent per-wallet skill (early corr late), plus 10
    injected 'MMs' whose early and late surplus are pure noise AND high-volume. Removing the MMs
    must raise corr and clear a matched null → GO. A no-effect control (MMs also persistent) must
    NOT verdict GO."""
    ok = True
    for kind, want_go in (("mm_noise", True), ("no_effect", False)):
        rng = np.random.default_rng(1)
        early, late = defaultdict(dict), defaultdict(dict)
        cov = {}
        pool = []
        for i in range(40):
            w = f"h{i:03d}"
            pool.append(w)
            skill = rng.normal(0, 0.08)
            for j in range(12):
                early[w][f"{w}e{j}"] = skill + rng.normal(0, 0.05)
                late[w][f"{w}l{j}"] = skill + rng.normal(0, 0.05)
            cov[w] = {"vol": rng.uniform(1e4, 1e5), "n_pos": rng.integers(50, 150),
                      "rt": 0.0, "ts": 0.0, "sb": 0.0}
        for i in range(10):
            w = f"m{i:03d}"
            pool.append(w)
            for j in range(12):
                if want_go:  # noise MM: early uncorrelated with late
                    early[w][f"{w}e{j}"] = rng.normal(0, 0.15)
                    late[w][f"{w}l{j}"] = rng.normal(0, 0.15)
                else:        # control: MMs persist just like humans
                    skill = rng.normal(0, 0.08)
                    early[w][f"{w}e{j}"] = skill + rng.normal(0, 0.05)
                    late[w][f"{w}l{j}"] = skill + rng.normal(0, 0.05)
            cov[w] = {"vol": rng.uniform(5e5, 1e6), "n_pos": rng.integers(200, 400),
                      "rt": 0.5, "ts": 0.6, "sb": 0.6}  # churner-shaped
        flagged = set(w for w in pool if mc.is_churner(cov[w]))
        corr_with, _, _ = read_corr(pool, early, late)
        dcorr, corr_wo, null, p = matched_null(pool, early, late, corr_with, flagged, cov, 1000, 7)
        n = len(pool)
        vd, why = verdict(dcorr, p, corr_with, corr_wo, n,
                          _fisher_ci(corr_with, n), _fisher_ci(corr_wo, n - len(flagged)))
        got_go = vd == "GO"
        good = got_go == want_go
        ok = ok and good
        print(f"  [{'ok' if good else 'FAIL'}] {kind}: corr {corr_with:+.3f}->{corr_wo:+.3f} "
              f"Δ{dcorr:+.3f} p={p:.3f} → {vd} (want {'GO' if want_go else 'not GO'})")
    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    a = sys.argv
    cutoff = a[a.index("--cutoff") + 1] if "--cutoff" in a else CUTOFF
    min_ev = int(a[a.index("--min-ev") + 1]) if "--min-ev" in a else MIN_EV
    nperm = int(a[a.index("--nperm") + 1]) if "--nperm" in a else N_PERM
    parity = "--parity" in a
    res = run(cutoff, min_ev, nperm, parity=parity)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports",
                       "mm_persistence_effect.json")
    with open(out, "w") as f:
        json.dump(res, f, indent=1, default=str)
    print("\nartifact → reports/mm_persistence_effect.json")


if __name__ == "__main__":
    main()
