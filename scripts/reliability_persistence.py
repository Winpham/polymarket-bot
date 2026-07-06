#!/usr/bin/env python3
"""
RELIABILITY-PERSISTENCE VALIDATION — the GO/NO-GO for the whole reliability-portfolio thesis
(Thread R2, cycle-3). §5 of TRADER-RELIABILITY-PORTFOLIO-PLAN.md, the honesty trap.

Selecting on realized consistency is survivorship/look-ahead bait: a trader looks smooth in-sample
then reverts. The method is only worth building if reliability PERSISTS out-of-sample. So, leak-free
(genuine fill ts — the crawl-stamp is confirmed real, Cycle-2 backfill 1.7%), for each wallet we
split its record by its own median event-time into an EARLY window and a held-out LATE window, score
each with the Thread-R1 factor library (at their price, event-clustered), and ask:

  RANK TEST (the go/no-go). Does early-window reliability RANK predict late-window reliability RANK,
    better than a matched null? Reliability scalar = REGULARIZED SORTINO = cal_gap / (downside_dev +
    EPS) (EPS floors the tiny-denominator noise of a ~15-event half and kills the inf/NaN of a
    loss-free half). Report signed Spearman + bootstrap CI + TWO permutation nulls:
      global   — shuffle late scores across all wallets (breaks the early->late pairing);
      n-strata — shuffle WITHIN n_events tertiles (preserves the power structure, so a spurious
                 correlation driven purely by 'big-n wallets are less noisy in both windows' cannot
                 masquerade as persistence). p_emp = fraction of permuted |or signed| Spearman >= obs.
    Plus the quartile TRANSITION MATRIX (do early-top-quartile-reliable stay reliable?).
    Robustness: the same test on raw cal_gap (skill persistence) and pos_window_frac (consistency).

  PRACTICAL TEST (the money version). Select a reliability-lean shortlist on EARLY data ONLY
    (early cal_gap>0 AND early null_p<=0.10, then top-quartile by early regSortino), then measure the
    pooled LATE clustered cal_gap of the selected wallets vs a matched-random-subset null (same count,
    drawn from the scored pool, >=2000x). Positive AND beating random => early reliability is
    forward-actionable. Needs far less data than ROI-certification (tests a stable ranking, not a
    profit magnitude at our price).

VERDICT: GO (reliability persists -> proceed to R3) / NO-GO (smooth-looking noise -> stop honestly) /
  INDETERMINATE-BY-POWER (positive but CI/null straddles). Adversarial by design: a NO-GO is the
  correct, valuable outcome. Read-only, paper-only, promotes nothing. Emits reports/reliability_persistence.json.

  ./reliability_persistence.py            # live
  ./reliability_persistence.py --selftest # persistent fixture -> GO-ish; null fixture -> NO-GO
"""

import argparse
import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trader_scorecard as tsc
import reliability_score as rs

REPORT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "reports", "reliability_persistence.json")

MIN_HALF_EV = 15         # each window needs >=15 events (=> total >=30, the R1 floor)
EPS = 0.10               # regularized-Sortino downside-dev floor (share-scale)
N_PERM = 2000
N_BOOT = 2000
SEED = 20260705
EARLY_NULL_P = 0.10      # practical-arm early reliability-lean skill floor


def reg_sortino(s):
    cg = s["cal_gap"]
    if cg != cg:
        return float("nan")
    return cg / (s["downside_dev"] + EPS)


def split_score(rows):
    """Median-ts split of one wallet's fills -> (early_score, late_score) or None if underpowered.
    Leak-free: the split is on genuine fill ts; every fill of an event rides with that event."""
    evs = rs._events(rows)                       # time-sorted per-event records
    if len(evs) < 2 * MIN_HALF_EV:
        return None
    # split events (not fills) at the median so both halves are event-balanced
    half = len(evs) // 2
    early_evset = {e["ev"] for e in evs[:half]}
    early_rows = [r for r in rows if r["ev"] in early_evset]
    late_rows = [r for r in rows if r["ev"] not in early_evset]
    se = rs.score_wallet(early_rows)
    sl = rs.score_wallet(late_rows)
    if se["n_events"] < MIN_HALF_EV or sl["n_events"] < MIN_HALF_EV:
        return None
    return se, sl


def spearman(x, y):
    """Spearman rho via Pearson on ranks (average ranks for ties)."""
    n = len(x)
    if n < 3:
        return float("nan")

    def ranks(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = ranks(x), ranks(y)
    mx, my = sum(rx) / n, sum(ry) / n
    sx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    sy = math.sqrt(sum((a - my) ** 2 for a in ry))
    if sx == 0 or sy == 0:
        return float("nan")
    return sum((a - mx) * (b - my) for a, b in zip(rx, ry)) / (sx * sy)


def perm_p(x, y, rng, strata=None, n_perm=N_PERM):
    """One-sided permutation p that observed Spearman is > chance. If strata given (list of labels),
    permute y WITHIN each stratum (preserves the power structure)."""
    obs = spearman(x, y)
    y = list(y)
    n = len(y)
    idx_by_stratum = defaultdict(list)
    if strata is None:
        idx_by_stratum[0] = list(range(n))
    else:
        for i, s in enumerate(strata):
            idx_by_stratum[s].append(i)
    ge = 0
    for _ in range(n_perm):
        yp = y[:]
        for _, idxs in idx_by_stratum.items():
            vals = [y[i] for i in idxs]
            rng.shuffle(vals)
            for i, v in zip(idxs, vals):
                yp[i] = v
        if spearman(x, yp) >= obs:
            ge += 1
    return obs, (ge + 1) / (n_perm + 1)


def boot_ci(x, y, rng, n_boot=N_BOOT, lo=2.5, hi=97.5):
    n = len(x)
    rhos = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        r = spearman([x[i] for i in idx], [y[i] for i in idx])
        if r == r:
            rhos.append(r)
    rhos.sort()
    if not rhos:
        return None, None
    return (rhos[int(lo / 100 * len(rhos))], rhos[min(len(rhos) - 1, int(hi / 100 * len(rhos)))])


def quartile(vals):
    """Return per-item quartile label 0..3 by value (0 = lowest)."""
    n = len(vals)
    order = sorted(range(n), key=lambda i: vals[i])
    q = [0] * n
    for rank, i in enumerate(order):
        q[i] = min(3, int(4 * rank / n))
    return q


def transition_matrix(qe, ql):
    m = [[0] * 4 for _ in range(4)]
    for a, b in zip(qe, ql):
        m[a][b] += 1
    return m


def analyze(pairs, rng):
    """pairs: list of (wallet, early_score, late_score). Runs all three persistence tests."""
    wallets = [p[0] for p in pairs]
    e_sort = [reg_sortino(p[1]) for p in pairs]
    l_sort = [reg_sortino(p[2]) for p in pairs]
    e_cg = [p[1]["cal_gap"] for p in pairs]
    l_cg = [p[2]["cal_gap"] for p in pairs]
    e_pw = [p[1]["pos_window_frac"] for p in pairs]
    l_pw = [p[2]["pos_window_frac"] for p in pairs]
    e_n = [p[1]["n_events"] for p in pairs]

    # n_events tertile strata for the confound-controlled null
    n_order = sorted(range(len(e_n)), key=lambda i: e_n[i])
    strat = [0] * len(e_n)
    for rank, i in enumerate(n_order):
        strat[i] = min(2, int(3 * rank / len(e_n)))

    def one(xe, xl, name):
        obs, p_glob = perm_p(xe, xl, rng, strata=None)
        _, p_strat = perm_p(xe, xl, rng, strata=strat)
        ci = boot_ci(xe, xl, rng)
        return {"metric": name, "spearman": obs, "boot_ci95": list(ci),
                "perm_p_global": p_glob, "perm_p_nstrata": p_strat, "n_pairs": len(xe)}

    rank_tests = {
        "reg_sortino": one(e_sort, l_sort, "reg_sortino"),
        "cal_gap": one(e_cg, l_cg, "cal_gap"),
        "pos_window_frac": one(e_pw, l_pw, "pos_window_frac"),
    }

    # transition matrix on the primary reliability scalar (reg_sortino)
    qe = quartile(e_sort)
    ql = quartile(l_sort)
    tm = transition_matrix(qe, ql)
    top_stay = tm[3][3] / max(1, sum(tm[3]))          # early-top-Q -> late-top-Q retention
    top_stay_tophalf = (tm[3][2] + tm[3][3]) / max(1, sum(tm[3]))
    bot_stay = tm[0][0] / max(1, sum(tm[0]))

    # ---- practical test: select on EARLY only, measure LATE, vs matched-random-subset null ----
    early_ok = [i for i in range(len(pairs))
                if e_cg[i] > 0 and pairs[i][1]["null_p"] <= EARLY_NULL_P]
    practical = {"n_early_eligible": len(early_ok)}
    if early_ok:
        # top quartile by early reg_sortino among the early-eligible
        cut = sorted((e_sort[i] for i in early_ok))
        thr = cut[int(0.75 * (len(cut) - 1))]
        sel = [i for i in early_ok if e_sort[i] >= thr]
        if sel:
            sel_late = [l_cg[i] for i in sel]
            obs_late = sum(sel_late) / len(sel_late)
            k = len(sel)
            alllate = l_cg
            ge = 0
            draws = []
            for _ in range(N_PERM):
                pick = rng.sample(range(len(alllate)), k)
                m = sum(alllate[i] for i in pick) / k
                draws.append(m)
                if m >= obs_late:
                    ge += 1
            mu = sum(draws) / len(draws)
            practical.update({
                "n_selected": k, "selected_wallets": [wallets[i] for i in sel],
                "late_cal_gap_selected": obs_late, "late_cal_gap_random_mean": mu,
                "late_positive": obs_late > 0,
                "beats_random_p": (ge + 1) / (N_PERM + 1),
            })

    return {"n_pairs": len(pairs), "rank_tests": rank_tests,
            "transition_matrix_regsortino": tm,
            "top_quartile_retention": top_stay, "top_quartile_to_top_half": top_stay_tophalf,
            "bottom_quartile_retention": bot_stay,
            "practical": practical, "wallets": wallets}


def verdict(res):
    """GO / NO-GO / INDETERMINATE from the primary (reg_sortino) rank test + practical arm."""
    rt = res["rank_tests"]["reg_sortino"]
    rho, ci, pg, ps = rt["spearman"], rt["boot_ci95"], rt["perm_p_global"], rt["perm_p_nstrata"]
    pr = res["practical"]
    prac_go = pr.get("late_positive") and pr.get("beats_random_p", 1.0) <= 0.05
    ci_pos = ci[0] is not None and ci[0] > 0
    sig = (pg <= 0.05 and ps <= 0.05)
    if rho > 0 and sig and ci_pos:
        v = "GO" if prac_go else "GO-RANK / practical-INDETERMINATE"
    elif rho <= 0 or (pg > 0.20 and ps > 0.20):
        v = "NO-GO"
    else:
        v = "INDETERMINATE-BY-POWER"
    return v, {"spearman": rho, "boot_ci95": ci, "perm_p_global": pg, "perm_p_nstrata": ps,
               "practical_late_positive": pr.get("late_positive"),
               "practical_beats_random_p": pr.get("beats_random_p")}


# ---------------------------------------------------------------- selftest
def selftest():
    import random
    rng = random.Random(SEED)

    def wallet_rows(w, early_hit, late_hit, price=0.68, sport_a="soccer", sport_b="tennis",
                    n=80):
        """n events per half; two sports so R1 scoring is well-defined; deterministic-ish wins."""
        rows = []
        r2 = random.Random(hash(w) & 0xffff)
        for half, hit, base_ts in (("e", early_hit, 0), ("l", late_hit, 10_000_000)):
            for i in range(n):
                sport = sport_a if i % 2 == 0 else sport_b
                won = 1 if r2.random() < hit else 0
                rows.append({"wallet": w, "ev": f"{w}-{half}-{i}",
                             "day": f"2026-{'05' if half=='e' else '06'}-{(i % 20)+1:02d}",
                             "ts": base_ts + i, "price": price, "won": won, "sport": sport})
        return rows

    # PERSISTENT world: a wallet's late hit-rate ~ its early hit-rate (skill is stable).
    pairs_persist = []
    hits = [0.60, 0.64, 0.68, 0.72, 0.76, 0.80, 0.84, 0.62, 0.66, 0.70,
            0.74, 0.78, 0.82, 0.58, 0.61, 0.71, 0.75, 0.79, 0.83, 0.69]
    for i, h in enumerate(hits):
        rows = wallet_rows(f"p{i}", h, min(0.95, h + 0.01))     # late ~ early (+noise via RNG)
        sp = split_score(rows)
        assert sp is not None
        pairs_persist.append((f"p{i}", sp[0], sp[1]))
    res = analyze(pairs_persist, random.Random(1))
    rho = res["rank_tests"]["cal_gap"]["spearman"]
    assert rho > 0.4, f"persistent world cal_gap spearman should be high: {rho}"
    assert res["rank_tests"]["cal_gap"]["perm_p_global"] < 0.05, "persistent world should be significant"

    # NULL world: late hit-rate independent of early (shuffled) -> no persistence.
    late_shuf = hits[:]
    random.Random(99).shuffle(late_shuf)
    # decorrelate hard: late drawn from an independent uniform, unrelated to early
    pairs_null = []
    rr = random.Random(5)
    for i, h in enumerate(hits):
        lh = 0.58 + 0.28 * rr.random()
        rows = wallet_rows(f"n{i}", h, lh)
        sp = split_score(rows)
        assert sp is not None
        pairs_null.append((f"n{i}", sp[0], sp[1]))
    resn = analyze(pairs_null, random.Random(2))
    rhon = resn["rank_tests"]["cal_gap"]["spearman"]
    assert resn["rank_tests"]["cal_gap"]["perm_p_global"] > 0.05 or abs(rhon) < 0.3, \
        f"null world should not be significant: rho={rhon}, p={resn['rank_tests']['cal_gap']['perm_p_global']}"

    # spearman sanity
    assert abs(spearman([1, 2, 3, 4], [1, 2, 3, 4]) - 1.0) < 1e-9
    assert abs(spearman([1, 2, 3, 4], [4, 3, 2, 1]) + 1.0) < 1e-9

    # verdict wiring: persistent world verdict must not be NO-GO
    v, _ = verdict(res)
    assert v != "NO-GO", f"persistent world must not verdict NO-GO, got {v}"
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return

    import random
    rng = random.Random(SEED)
    rows = rs.fetch_fills()
    by_wallet = defaultdict(list)
    for r in rows:
        by_wallet[r["wallet"]].append(r)

    pairs = []
    for w, rs_rows in by_wallet.items():
        if len({r["ev"] for r in rs_rows}) < 2 * MIN_HALF_EV:
            continue
        sp = split_score(rs_rows)
        if sp is None:
            continue
        pairs.append((w, sp[0], sp[1]))

    res = analyze(pairs, rng)
    v, summary = verdict(res)

    name_rows = tsc.q("SELECT lower(proxy_wallet) AS w, username FROM followed_traders")
    names = {r["w"]: r["username"] for r in name_rows}

    out = {"meta": {"min_half_events": MIN_HALF_EV, "eps_sortino": EPS, "n_perm": N_PERM,
                    "n_boot": N_BOOT, "seed": SEED, "split": "per-wallet median event-time (leak-free)",
                    "n_pairs": res["n_pairs"], "charter": "TRADER-RELIABILITY-PORTFOLIO-PLAN.md §5"},
           "verdict": v, "verdict_summary": summary,
           "rank_tests": res["rank_tests"],
           "transition_matrix_regsortino": res["transition_matrix_regsortino"],
           "top_quartile_retention": res["top_quartile_retention"],
           "top_quartile_to_top_half": res["top_quartile_to_top_half"],
           "bottom_quartile_retention": res["bottom_quartile_retention"],
           "practical": {**res["practical"],
                         "selected_usernames": [names.get(w) for w in
                                                res["practical"].get("selected_wallets", [])]}}
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w") as f:
        json.dump(out, f, indent=2, default=str)

    print(f"RELIABILITY-PERSISTENCE (leak-free per-wallet median-ts split) · n_pairs = {res['n_pairs']}")
    print("  rank tests (early -> late, Spearman; permutation null p; bootstrap 95% CI):")
    for k, t in res["rank_tests"].items():
        ci = t["boot_ci95"]
        cis = f"[{ci[0]:+.2f}, {ci[1]:+.2f}]" if ci[0] is not None else "[n/a]"
        print(f"    {k:<16} rho {t['spearman']:+.3f}  CI95 {cis}  "
              f"p_global {t['perm_p_global']:.4f}  p_nstrata {t['perm_p_nstrata']:.4f}")
    print(f"  transition matrix (reg_sortino quartiles, early rows x late cols, 0=low..3=top):")
    for a in range(4):
        print(f"    early-Q{a}: {res['transition_matrix_regsortino'][a]}")
    print(f"    early-top-Q retention -> top-Q {res['top_quartile_retention']:.0%}, "
          f"-> top-HALF {res['top_quartile_to_top_half']:.0%}; "
          f"bottom-Q stays bottom {res['bottom_quartile_retention']:.0%}")
    pr = res["practical"]
    if "late_cal_gap_selected" in pr:
        print(f"  practical: select on EARLY (n={pr['n_selected']} of {pr['n_early_eligible']} eligible) "
              f"-> LATE cal_gap {pr['late_cal_gap_selected']:+.3f} vs random {pr['late_cal_gap_random_mean']:+.3f}"
              f"  (positive={pr['late_positive']}, beats-random p={pr['beats_random_p']:.4f})")
    else:
        print(f"  practical: only {pr.get('n_early_eligible',0)} early-eligible wallets -> underpowered")
    print(f"\n  VERDICT: {v}")
    print(f"  (primary reg_sortino: rho {summary['spearman']:+.3f}, CI {summary['boot_ci95']}, "
          f"p_global {summary['perm_p_global']:.4f}, p_nstrata {summary['perm_p_nstrata']:.4f})")
    print(f"wrote {REPORT}")


if __name__ == "__main__":
    main()
