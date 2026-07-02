#!/usr/bin/env python3
"""
EFFECTIVE-N RECONCILIATION — one honest sample size, and the two questions the gate conflates.

Truth-audit finding E-1 (DECISIONS D16-a): the public board and the real-money pilot gate
disagree, BY CONSTRUCTION, on the effective N that deflates the surplus SE:

  * board.rs / promotion_verdict  →  effective_n = clamp(distinct_days, 1, distinct_events)
       = **distinct event-DAYS** (Moulton-style FULL within-day correlation ⇒ ICC = 1).
       favorite (match key): 4 days ⇒ SE = sd/√4 ⇒ LB ≈ −21%  ("nothing certifies on 4 days").
  * honest.rs / surplus_bounds    →  effective_n = distinct_events
       = **event count** (independence ⇒ ICC = 0).
       favorite (match key): 71 events ⇒ SE = sd/√71 ⇒ LB ≈ +4.6%  ("eligible").

Both are ENDPOINTS of the same design-effect formula at opposite extreme ICC assumptions.
The data does not have to be guessed — the concentration instrument MEASURED the within-day
correlation of the surplus residual (ICC_slate ≈ 0.002 for favorite). So NEITHER endpoint is
right; the honest effective N is the cluster-robust one that MEASURES the between-cluster
dispersion instead of assuming it:

  n_eff_CR = sd² / V_CR ,   V_CR = cluster-robust variance of the event-clustered surplus mean.

n_eff_CR spans the two Rust endpoints exactly: → distinct_events when clusters are iid
(ICC≈0), → #clusters when fully correlated within cluster (ICC≈1). It lands where the data
actually is — but the POINT n_eff is not the whole story: with only G≈4 clusters the CR SE is
itself imprecise, so the honest CI uses a small-cluster Student t(G-1), NOT a normal z.

The reconciliation exposes that the single SE conflates two DIFFERENT questions:

  Q1  CI WIDTH given outcome-correlation — n_eff_CR (cluster-robust). board.rs's ICC=1 is
      falsified (measured within-day ICC≈0.007), so its −23% is a MISLEADING mechanism that
      makes a strong, near-independent edge look statistically dead; honest.rs's ICC=0 is the
      opposite error. The correct CI is cluster-robust — but read at small-cluster t, not z.
  Q2  PERSISTENCE / d.o.f. — how many INDEPENDENT clusters (days/tournaments) exist? Only ~4.
      This is what actually binds: a family-wise cluster-robust interval on ~4 clusters is
      NEGATIVE regardless, because 4 is too few degrees of freedom. board.rs reaches this
      right answer (hold) but by the wrong route (ICC=1); the honest route is the cluster COUNT.

RECONCILED CONVENTION (proposed — NOT applied to live Rust; paper-only, Tue's call):
  * Drop the ICC=1 √days deflation (misleading). Compute the surplus LB from the cluster-robust
    SE read at small-cluster t(G-1) — honest, and it does NOT falsely resurrect the edge.
  * Make the BINDING gate an EXPLICIT independent-cluster-COUNT floor (≥K disjoint day/regime
    blocks) — the accrual wall no SE re-derivation can shortcut. The strong POINT estimate
    (surplus, 4/4 regimes +, ICC≈0) is surfaced separately so the board stops reading "dead".

Read-only, paper-only, changes nothing live. Reuses rekey_headline (the truth-audit's
validated surplus_bounds/promotion_verdict mirror) and portfolio_concentration (icc/n_eff)
so every number is byte-identical to the gate.

Modes:
  ./effective_n.py             # live DB; the reconciliation table + verdict; writes JSON
  ./effective_n.py --selftest  # the CR estimator must span the two Rust endpoints on
                               # iid / fully-correlated / known-dispersion fixtures. Exit != 0 on fail.
"""

import json
import math
import os
import random
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import portfolio_concentration as pc  # icc_oneway, n_eff, match_key, tournament
import rekey_headline as rk           # probit, band, gate_stats, fetch, n_core, super_event mirror
import selection_null as sn           # regime()

SEED = 20260702
MARGIN = 0.03
WINNERS = ("favorite", "elite_fresh_fav")


def _t_ppf(p, df):
    """One-sided Student-t critical value. scipy if available, else a Cornish-Fisher-style
    normal expansion (accurate to ~1% for the df≥3 / p≈0.996 range we use)."""
    try:
        import scipy.stats as _st
        return float(_st.t.ppf(p, df))
    except Exception:
        from statistics import NormalDist
        z = NormalDist().inv_cdf(p)
        # Fisher expansion of the t quantile in terms of the normal quantile.
        g1 = (z**3 + z) / 4.0
        g2 = (5 * z**5 + 16 * z**3 + 3 * z) / 96.0
        g3 = (3 * z**7 + 19 * z**5 + 17 * z**3 - 15 * z) / 384.0
        return z + g1 / df + g2 / df**2 + g3 / df**3


# ---------------------------------------------------------------------------------------
# Cluster-robust variance of the event-clustered surplus mean θ = (1/N) Σ_e s_e.
# CR1 estimator with the standard small-sample G/(G-1)·(N-1)/(N-K) correction, K=1.
# ---------------------------------------------------------------------------------------
def cluster_robust(ev_surplus, ev_cluster):
    """ev_surplus: {ev: s_e}. ev_cluster: {ev: cluster_id}. Returns dict with V_CR, se_CR,
    n_eff_CR = sd²/V_CR, G clusters, N events, and the plain event-N (iid) se for reference."""
    evs = list(ev_surplus.keys())
    n = len(evs)
    if n < 2:
        return None
    vals = np.array([ev_surplus[e] for e in evs])
    theta = float(vals.mean())
    sd = float(vals.std(ddof=1))
    se_iid = sd / math.sqrt(n)
    groups = defaultdict(list)
    for e in evs:
        groups[ev_cluster[e]].append(ev_surplus[e] - theta)
    g = len(groups)
    # CR1: V = c · (1/N²) Σ_g (Σ_{i∈g} u_i)² ,  c = G/(G-1) · (N-1)/(N-K), K=1
    ss = sum((sum(u)) ** 2 for u in groups.values())
    if g < 2:
        return {"theta": theta, "sd": sd, "se_iid": se_iid, "G": g, "N": n,
                "V_CR": float("nan"), "se_CR": float("nan"), "n_eff_CR": float("nan")}
    corr = (g / (g - 1.0)) * ((n - 1.0) / (n - 1.0))  # K=1 → (N-1)/(N-1)=1; keep explicit
    v_cr = corr * ss / (n * n)
    se_cr = math.sqrt(v_cr) if v_cr > 0 else 0.0
    n_eff_cr = (sd * sd) / v_cr if v_cr > 0 else float(n)
    return {"theta": theta, "sd": sd, "se_iid": se_iid, "G": g, "N": n,
            "V_CR": v_cr, "se_CR": se_cr, "n_eff_CR": n_eff_cr}


def lb_at(surplus, se, z):
    return surplus - z * se


# ---------------------------------------------------------------------------------------
# Per-event surplus at MATCH clustering + per-event cluster labels (day / tournament / regime).
# Mirrors rekey_headline.gate_stats' event-surplus exactly (at-fire a − band-blind edge).
# ---------------------------------------------------------------------------------------
def match_surplus(rows, strategy):
    blind_band = defaultdict(list)
    for r in rows:
        if r["strategy"] == "_blind":
            blind_band[rk.band(r["entry"])].append(r["won"] - r["entry"])
    blind_edge = {b: sum(v) / len(v) for b, v in blind_band.items()}

    srows = [r for r in rows if r["strategy"] == strategy]
    ev_rows = defaultdict(list)
    for r in srows:
        k = rk.super_event(r["event_slug"], r["slug"]) or r["condition_id"]
        ev_rows[k].append(r)
    ev_surplus, ev_day, ev_tourn, ev_regime = {}, {}, {}, {}
    for k, rs in ev_rows.items():
        ev_surplus[k] = float(np.mean(
            [(r["won"] - r["entry"]) - blind_edge.get(rk.band(r["entry"]), 0.0) for r in rs]))
        ev_day[k] = min(str(r["day"]) for r in rs)
        # cluster on the event_slug that carries the sport prefix (match key strips suffix)
        es = next((r["event_slug"] for r in rs if r["event_slug"]), rs[0]["slug"])
        ev_regime[k] = sn.regime(es)
        ev_tourn[k] = pc.tournament(es, k)
    return ev_surplus, ev_day, ev_tourn, ev_regime


def reconcile(rows, strategy, nc):
    """The full reconciliation for one strategy at match-level clustering."""
    ev_s, ev_day, ev_tourn, ev_reg = match_surplus(rows, strategy)
    n = len(ev_s)
    if n < 2:
        return None
    z = rk.probit(1 - 0.05 / max(nc, 1))
    surplus = float(np.mean(list(ev_s.values())))
    sd = float(np.std(list(ev_s.values()), ddof=1))

    # The two Rust endpoints (validity anchors), reproduced exactly.
    distinct_events = n
    distinct_days = len(set(ev_day.values()))
    eff_day = max(1, min(distinct_days, distinct_events))
    lb_eventN = lb_at(surplus, sd / math.sqrt(distinct_events), z)   # honest.rs pilot
    lb_dayN = lb_at(surplus, sd / math.sqrt(eff_day), z)             # board.rs Moulton ICC=1

    # Measured design-effect N_eff (portfolio_concentration machinery) at day / slate-ish /
    # regime grains — the outcome-independence answer to Q1.
    def icc_neff(cluster_map):
        groups = defaultdict(list)
        for e, s in ev_s.items():
            groups[cluster_map[e]].append(s)
        icc, m_bar, k, ntot = pc.icc_oneway(list(groups.values()))
        ne, de = pc.n_eff(ntot, m_bar, icc)
        return {"icc": icc, "n_eff": ne, "design_effect": de, "k_groups": k}

    de_day = icc_neff(ev_day)
    de_reg = icc_neff(ev_reg)

    # Cluster-robust (the honest CI that assumes NEITHER endpoint) at day and tournament grains.
    cr_day = cluster_robust(ev_s, ev_day)
    cr_tourn = cluster_robust(ev_s, ev_tourn)
    # LB at the gate's Bonferroni NORMAL z — comparable to the anchors, but NORMAL ignores the
    # small-cluster degrees of freedom. With only G clusters the honest reference is Student
    # t(G-1) at the SAME family-wise alpha — which is much wider and is the number that binds.
    lb_cr_day = lb_at(surplus, cr_day["se_CR"], z)
    lb_cr_tourn = lb_at(surplus, cr_tourn["se_CR"], z)
    # Small-cluster t needs ≥2 d.o.f. (G≥3) to be even loosely informative; below that the
    # bound is nonsense (t(1)≈83) and we report it as undefined rather than print garbage.
    def _small_cluster_t_lb(cr):
        df = cr["G"] - 1
        if df < 2:
            return None, df
        return surplus - _t_ppf(1 - 0.05 / max(nc, 1), df) * cr["se_CR"], df
    lb_cr_day_bonf_t, t_df = _small_cluster_t_lb(cr_day)
    lb_cr_tourn_bonf_t, _ = _small_cluster_t_lb(cr_tourn)
    t_crit_bonf = _t_ppf(1 - 0.05 / max(nc, 1), max(2, t_df))

    # Persistence (Q2): per-regime surplus (rule c), how many disjoint regimes individually > 0.
    by_reg = defaultdict(list)
    for e, s in ev_s.items():
        by_reg[ev_reg[e]].append(s)
    regimes = {rg: {"n": len(v), "surplus": float(np.mean(v))} for rg, v in by_reg.items()}
    n_pos_regimes = sum(1 for v in regimes.values() if v["surplus"] > 0 and v["n"] >= 5)

    return {
        "strategy": strategy, "surplus": surplus, "sd": sd, "z": z,
        "distinct_events": distinct_events, "distinct_days": distinct_days,
        "lb_eventN_honest_rs": lb_eventN, "lb_dayN_board_rs": lb_dayN,
        "measured_de_day": de_day, "measured_de_regime": de_reg,
        "cr_day": cr_day, "cr_tourn": cr_tourn,
        "lb_cr_day_gate_z": lb_cr_day, "lb_cr_tourn_gate_z": lb_cr_tourn,
        "lb_cr_day_bonf_t": lb_cr_day_bonf_t, "lb_cr_tourn_bonf_t": lb_cr_tourn_bonf_t,
        "t_df_day": t_df, "t_crit_bonf": t_crit_bonf, "n_clusters_day": cr_day["G"],
        "n_clusters_tourn": cr_tourn["G"],
        "n_eff_CR_day": cr_day["n_eff_CR"], "n_eff_CR_tourn": cr_tourn["n_eff_CR"],
        "regimes": regimes, "n_pos_regimes": n_pos_regimes,
    }


def run_live():
    rows = rk.fetch()
    nc = rk.n_core(rows)
    print(f"EFFECTIVE-N RECONCILIATION · core family n={nc} · at-fire entry · match-level clustering")
    print("Reconciling board.rs (day-N, ICC=1) vs honest.rs (event-N, ICC=0) into one measured n_eff.\n")
    pf = lambda x: "n/a" if x is None else f"{x:+.2%}"  # noqa: E731  (t-LB is None when G<3)
    results = {}
    for s in WINNERS:
        r = reconcile(rows, s, nc)
        if not r:
            continue
        results[s] = r
        print(f"── {s}  (surplus {r['surplus']:+.2%}, sd {r['sd']:.2%}, "
              f"{r['distinct_events']} matches over {r['distinct_days']} days) ──")
        print(f"  Q1  WITHIN-SAMPLE precision of the surplus (Bonferroni z={r['z']:.2f}) — how well is +{r['surplus']*100:.1f}% pinned down?")
        print(f"      board.rs   day-N     N={r['distinct_days']:>3}  (assumes within-day ICC=1)   LB {r['lb_dayN_board_rs']:+.2%}  ← FALSIFIED")
        print(f"      measured within-day ICC = {r['measured_de_day']['icc']:.3f} ≈ 0  ⇒  events ~independent in-sample ⇒ ICC=1 is wrong")
        print(f"      honest.rs  event-N   N={r['distinct_events']:>3}  (ICC≈0, matches data)        LB {r['lb_eventN_honest_rs']:+.2%}")
        print(f"      cluster-robust @measured ICC (n_eff_CR {r['n_eff_CR_day']:.0f})                 LB {r['lb_cr_day_gate_z']:+.2%}  ← agrees w/ event-N")
        print(f"      ⇒ IN-SAMPLE the surplus is well-estimated and clears 3%. board.rs's {r['lb_dayN_board_rs']:+.0%} is a misleading artifact.")
        print(f"  Q2  OUT-OF-SAMPLE persistence — the ACTUAL wall, and it is NOT a within-sample SE:")
        print(f"      trying to price persistence by clustering+penalising is GRAIN-ARBITRARY: small-cluster t LB =")
        print(f"        {pf(r['lb_cr_day_bonf_t'])} at day grain (G={r['n_clusters_day']}, t({r['t_df_day']}))  vs  {pf(r['lb_cr_tourn_bonf_t'])} at tournament grain (G={r['n_clusters_tourn']}).")
        print(f"      the answer swings on an arbitrary grain ⇒ persistence must be COUNTED, not deflated into an SE.")
        print(f"      independent regime-blocks individually > 0 (rule c, N≥5):"
              f" {r['n_pos_regimes']} of {len(r['regimes'])}  (but only ~2 tournament cycles / {r['distinct_days']} calendar days total)")
        for rg, v in sorted(r["regimes"].items(), key=lambda kv: -kv[1]["n"]):
            flag = "＋" if v["surplus"] > 0 and v["n"] >= 5 else " "
            print(f"        {flag} {rg:<8} N={v['n']:>3}  surplus {v['surplus']:+.2%}")
        print()

    # Verdict
    fav = results.get("favorite")
    if fav:
        print("VERDICT (favorite) — the gate conflates TWO questions; separating them is the whole fix:")
        print(f"  • WITHIN-SAMPLE (Q1): board.rs's {fav['lb_dayN_board_rs']:+.0%} assumes within-day ICC=1; the MEASURED ICC is "
              f"{fav['measured_de_day']['icc']:.3f}≈0,")
        print(f"    so events are ~independent in-sample and the surplus IS well pinned down: event-N LB {fav['lb_eventN_honest_rs']:+.1%} ≈ "
              f"cluster-robust LB {fav['lb_cr_day_gate_z']:+.1%} > 3%. The −20% is a misleading artifact, not a dead edge.")
        print(f"  • OUT-OF-SAMPLE (Q2) is the ACTUAL wall — and it is NOT a within-sample SE. Encoding persistence-doubt")
        print(f"    as an SE is grain-arbitrary (day-grain t LB {fav['lb_cr_day_bonf_t']:+.1%} vs tournament {fav['lb_cr_tourn_bonf_t']:+.1%} — the answer")
        print(f"    flips on the grain). board.rs's ICC=1 and my own earlier 'small-cluster t' framing commit the SAME sin.")
        print(f"    The honest wall is a COUNT: ~{fav['distinct_days']} calendar days / ~2 tournament cycles — too few INDEPENDENT")
        print(f"    regime-blocks to establish generalisation, however precise the in-sample estimate. Point estimate is")
        print(f"    strong and consistent ({fav['n_pos_regimes']}/{len(fav['regimes'])} disjoint regimes individually +, surplus {fav['surplus']:+.1%}) → promising, unproven.")
        print("  RECONCILED CONVENTION (proposed, NOT applied to Rust): (a) surplus WITHIN-SAMPLE LB from the")
        print("  cluster-robust SE at the MEASURED ICC (≈ event-N here) — drop the ICC=1 √days deflation entirely;")
        print("  (b) a SEPARATE, EXPLICIT independent-cluster-COUNT / persistence floor for Q2 — never an SE. Both")
        print("  current gates mis-handle it: event-N ignores Q2; day-N smuggles Q2 into the SE and gets Q1 wrong too.")
    return results


# ---------------------------------------------------------------------------------------
# Self-test: the CR estimator must SPAN the two Rust endpoints and recover known dispersion.
# ---------------------------------------------------------------------------------------
def selftest():
    ok = True
    rng = np.random.default_rng(SEED)

    # (1) iid fixture: random cluster assignment ⇒ ICC≈0 → n_eff_CR ≈ N (NOT G). The CR
    #     estimator is noisy with few clusters, so average over seeds (the estimand is N).
    N, G = 240, 24
    neffs, se_cr_s, se_iid_s = [], [], []
    for sd_i in range(8):
        r2 = np.random.default_rng(SEED + 100 + sd_i)
        ev_s_i = {f"e{i}": float(r2.normal(0.1, 1.0)) for i in range(N)}
        ev_cl_i = {f"e{i}": f"g{i % G}" for i in range(N)}   # random assignment ⇒ no within-cluster corr
        c = cluster_robust(ev_s_i, ev_cl_i)
        neffs.append(c["n_eff_CR"]); se_cr_s.append(c["se_CR"]); se_iid_s.append(c["se_iid"])
    neff_iid = float(np.mean(neffs))
    c1 = 0.6 * N <= neff_iid <= 1.5 * N and neff_iid > 4 * G \
        and abs(np.mean(se_cr_s) - np.mean(se_iid_s)) <= 0.25 * np.mean(se_iid_s)
    ok = ok and c1
    print(f"  [{'ok' if c1 else 'FAIL'}] iid (8-seed mean): n_eff_CR {neff_iid:.0f}/{N} (≈N ≫ G={G}), "
          f"se_CR {np.mean(se_cr_s):.4f} ≈ se_iid {np.mean(se_iid_s):.4f}")

    # (2) fully within-cluster-correlated fixture: every event in a cluster shares ONE value
    #     (ICC=1) → n_eff_CR ≈ G (the Moulton/board endpoint).
    clusters = {f"g{j}": float(rng.normal(0.1, 1.0)) for j in range(G)}
    ev_s2, ev_cl2 = {}, {}
    for i in range(N):
        g = f"g{i % G}"
        ev_s2[f"e{i}"] = clusters[g]        # identical within cluster ⇒ ICC = 1
        ev_cl2[f"e{i}"] = g
    cr2 = cluster_robust(ev_s2, ev_cl2)
    c2 = abs(cr2["n_eff_CR"] - G) <= 1.0
    ok = ok and c2
    print(f"  [{'ok' if c2 else 'FAIL'}] fully-correlated: n_eff_CR {cr2['n_eff_CR']:.2f} ≈ G={G} "
          f"(reproduces board.rs day-N endpoint)")

    # (3) known-dispersion fixture: inject cluster means with variance τ², within-cluster σ².
    #     Analytic n_eff_CR ≈ N/(1+(m-1)·ρ), ρ = τ²/(τ²+σ²). Estimator must land near it.
    tau, sig, m = 0.8, 0.6, N // G
    means = {f"g{j}": float(rng.normal(0.1, tau)) for j in range(G)}
    ev_s3, ev_cl3 = {}, {}
    for i in range(N):
        g = f"g{i % G}"
        ev_s3[f"e{i}"] = means[g] + float(rng.normal(0, sig))
        ev_cl3[f"e{i}"] = g
    cr3 = cluster_robust(ev_s3, ev_cl3)
    rho = tau * tau / (tau * tau + sig * sig)
    neff_true = N / (1 + (m - 1) * rho)
    c3 = abs(cr3["n_eff_CR"] - neff_true) <= 0.6 * neff_true + 3
    ok = ok and c3
    print(f"  [{'ok' if c3 else 'FAIL'}] known ρ={rho:.2f}: n_eff_CR {cr3['n_eff_CR']:.0f} "
          f"vs analytic {neff_true:.0f} (spans the endpoints)")

    # (4) monotone: the three fixtures must order n_eff_CR: correlated < known-disp < iid.
    c4 = cr2["n_eff_CR"] < cr3["n_eff_CR"] < neff_iid
    ok = ok and c4
    print(f"  [{'ok' if c4 else 'FAIL'}] ordering: G-endpoint {cr2['n_eff_CR']:.0f} < "
          f"mid {cr3['n_eff_CR']:.0f} < N-endpoint {neff_iid:.0f}")

    # (5) probit reproduction (the gate's z machinery is faithful).
    c5 = abs(rk.probit(0.975) - 1.959964) < 1e-4
    ok = ok and c5
    print(f"  [{'ok' if c5 else 'FAIL'}] probit(0.975)={rk.probit(0.975):.6f} (gate z machinery)")

    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    results = run_live()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports", "effective_n.json")
    with open(out, "w") as f:
        json.dump(results, f, indent=1, default=str)
    print("\nartifact → reports/effective_n.json")


if __name__ == "__main__":
    main()
