#!/usr/bin/env python3
"""
ORTHOGONALITY GATE — is there a SECOND edge that actually DIVERSIFIES the favorite edge?

The diversification-risk run (entry 12 / D15) proved the record's reliability is
SUPPLY-limited, not allocation-limited: at favorite's ≈0 within-slate correlation, adding an
extra INDEPENDENT regime cuts variance ~linearly in volume, but you cannot ALLOCATE
diversification into existence — you need a genuinely uncorrelated edge SOURCE. This
instrument asks the belief-blind question directly: does any candidate strategy in the
ALREADY-CAPTURED stream add a second edge that is BOTH real AND independent of favorite?

The generator is wild (test every candidate); the gate is rigorous. A candidate S
DIVERSIFIES favorite iff ALL THREE hold:

  G1  INDEPENDENT VOLUME.  S fires on events favorite does NOT (S⊥fav = S_only). A nested
      strategy (elite_fresh_fav ⊂ favorite) adds ZERO independent events → cannot diversify,
      full stop (this is the entry-12 dedup finding, now a gate).
  G2  ORTHOGONAL-COMPONENT EDGE.  The diversifying picks THEMSELVES carry edge: the
      selection-matched null (selection_null.py machinery) on S_only must be selection-real
      (p ≤ 0.01) and positive. If S's only edge is on the events it SHARES with favorite,
      it is favorite wearing a different name.
  G3  RESIDUAL INDEPENDENCE.  On shared events, S's advantage residual must be ~uncorrelated
      with favorite's (else the "independent" volume co-moves with favorite through a common
      shock). Report Pearson r on shared events + the S_only-vs-fav regime-shock correlation.

Only a candidate clearing G1∧G2∧G3 buys reliability. The RELIABILITY VALUE of one that does
is priced by the design effect: two uncorrelated edges of N_a, N_b independent events combine
to N_a+N_b effective bets, so the combined per-bet SE falls by √((N_a+N_b)/N_a) vs favorite
alone — the honest, quantified "what a second edge is worth", complementary to the risk
engine's regime-count Monte Carlo (priced end-to-end in portfolio_constructor.py).

Read-only, paper-only. Reuses selection_null (fetch/band/regime/null) so the selection stat
is byte-identical to the gate.

Modes:
  ./edge_orthogonality.py             # live DB; the gate over every candidate; writes JSON
  ./edge_orthogonality.py --selftest  # injected orthogonal edge must PASS; nested + correlated
                                      # decoys must FAIL the right gate. Exit != 0 on fail.
"""

import json
import math
import os
import random
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import selection_null as sn  # fetch, band, regime, clustered_surplus, null_pvalue

SEED = 20260702
ANCHOR = "favorite"
P_BAR = 0.01
N_PERM = 2000


def blind_edge_map(rows):
    bb = defaultdict(list)
    for r in rows:
        if r["strategy"] == "_blind":
            bb[sn.band(r["entry"])].append(r["won"] - r["entry"])
    return {b: sum(v) / len(v) for b, v in bb.items()}


def ev_residuals(srows, blind_edge):
    """Per-event advantage residual (a − band-blind edge), averaged over the event's rows."""
    by_ev = defaultdict(list)
    for r in srows:
        by_ev[r["ev"]].append((r["won"] - r["entry"]) - blind_edge.get(sn.band(r["entry"]), 0.0))
    return {ev: float(np.mean(v)) for ev, v in by_ev.items()}


def selection_null_on(subrows, blind_cells, blind_edge, rng, n_perm=N_PERM):
    """selection_null.py machinery restricted to an arbitrary row subset. Returns
    (obs, mu, sd, p, n_events)."""
    picks = [(r["ev"], sn.band(r["entry"]), r["won"] - r["entry"]) for r in subrows]
    obs, n_ev = sn.clustered_surplus(picks, blind_edge)
    meta = [(sn.band(r["entry"]), r["day"]) for r in subrows]
    draws = sn.null_pvalue(meta, blind_cells, blind_edge, rng, n_perm)
    if len(draws) < 1000:
        return obs, None, None, None, n_ev
    mu = sum(draws) / len(draws)
    sd = math.sqrt(sum((x - mu) ** 2 for x in draws) / (len(draws) - 1))
    p = sum(1 for x in draws if x >= obs) / len(draws)
    return obs, mu, sd, p, n_ev


def shared_residual_corr(anchor_resid, cand_resid):
    """Pearson r of per-event residuals on the events BOTH fire (G3)."""
    shared = sorted(set(anchor_resid) & set(cand_resid))
    if len(shared) < 8:
        return None, len(shared)
    a = np.array([anchor_resid[e] for e in shared])
    b = np.array([cand_resid[e] for e in shared])
    if a.std() < 1e-12 or b.std() < 1e-12:
        return 0.0, len(shared)
    return float(np.corrcoef(a, b)[0, 1]), len(shared)


def regime_shock_corr(anchor_rows, cand_only_rows, blind_edge):
    """G3 second leg: even on DISJOINT events, do S_only and favorite co-move through a shared
    (regime × day) shock? Correlate the two strategies' per-slate mean residuals across the
    slates they have in common. High r ⇒ the 'independent' volume is not independent."""
    def slate_means(rows):
        by_slate = defaultdict(list)
        for r in rows:
            by_slate[(sn.regime(r["event_slug"]), r["day"])].append(
                (r["won"] - r["entry"]) - blind_edge.get(sn.band(r["entry"]), 0.0))
        return {s: float(np.mean(v)) for s, v in by_slate.items()}
    a, b = slate_means(anchor_rows), slate_means(cand_only_rows)
    shared = sorted(set(a) & set(b))
    if len(shared) < 4:
        return None, len(shared)
    av = np.array([a[s] for s in shared]); bv = np.array([b[s] for s in shared])
    if av.std() < 1e-12 or bv.std() < 1e-12:
        return 0.0, len(shared)
    return float(np.corrcoef(av, bv)[0, 1]), len(shared)


def reliability_value(n_fav_indep, n_s_indep, r_resid):
    """Design-effect value of a CLEAN orthogonal edge: two uncorrelated edges of N_a, N_b
    independent events combine to ≈ N_a+N_b effective bets → combined per-bet SE shrinks by
    √((N_a+N_b)/N_a). A residual correlation r inflates the combined variance by the usual
    portfolio factor, discounting the effective added N by (1−r) on the shared axis."""
    if n_s_indep <= 0:
        return {"se_shrink_factor": 1.0, "eff_added_n": 0.0}
    eff_added = n_s_indep * max(0.0, 1.0 - abs(r_resid or 0.0))
    shrink = math.sqrt((n_fav_indep + eff_added) / n_fav_indep) if n_fav_indep > 0 else 1.0
    return {"se_shrink_factor": shrink, "eff_added_n": eff_added}


def gate_candidate(name, anchor_rows, cand_rows, anchor_resid, blind_cells, blind_edge, rng):
    anchor_evs = {r["ev"] for r in anchor_rows}
    cand_evs = {r["ev"] for r in cand_rows}
    s_only_evs = cand_evs - anchor_evs
    s_only_rows = [r for r in cand_rows if r["ev"] in s_only_evs]
    cand_resid = ev_residuals(cand_rows, blind_edge)

    g1_indep = len(s_only_evs)                       # independent events added
    frac_indep = g1_indep / max(1, len(cand_evs))

    # G2: does the diversifying component carry edge?
    if g1_indep >= 10:
        obs, mu, sd, p, n_ev = selection_null_on(s_only_rows, blind_cells, blind_edge, rng)
    else:
        obs, mu, sd, p, n_ev = (float("nan"), None, None, None, g1_indep)
    g2_edge_real = (p is not None and p <= P_BAR and obs > 0)

    # G3: residual independence on shared events + regime-shock independence on disjoint events.
    r_shared, n_shared = shared_residual_corr(anchor_resid, cand_resid)
    r_shock, n_shock_slates = regime_shock_corr(anchor_rows, s_only_rows, blind_edge)
    g3_independent = (abs(r_shared or 0.0) <= 0.3) and (abs(r_shock or 0.0) <= 0.5)

    diversifies = (g1_indep >= 10) and g2_edge_real and g3_independent
    rv = reliability_value(len(anchor_evs), g1_indep, r_shared)
    return {
        "candidate": name,
        "n_events": len(cand_evs), "n_independent": g1_indep, "frac_independent": round(frac_indep, 3),
        "g1_pass": g1_indep >= 10,
        "orth_surplus": None if math.isnan(obs) else round(obs, 4),
        "orth_null_p": p, "orth_n_events": n_ev, "g2_pass": g2_edge_real,
        "r_shared": None if r_shared is None else round(r_shared, 3), "n_shared": n_shared,
        "r_regime_shock": None if r_shock is None else round(r_shock, 3), "n_shock_slates": n_shock_slates,
        "g3_pass": g3_independent,
        "diversifies": diversifies,
        "se_shrink_if_real": round(rv["se_shrink_factor"], 3), "eff_added_n": round(rv["eff_added_n"], 1),
    }


def run_live():
    rows = sn.fetch()
    rng = random.Random(SEED)
    blind_edge = blind_edge_map(rows)
    blind_cells = defaultdict(list)
    for r in rows:
        if r["strategy"] == "_blind":
            blind_cells[(sn.band(r["entry"]), r["day"])].append((r["ev"], r["won"] - r["entry"]))

    anchor_rows = [r for r in rows if r["strategy"] == ANCHOR]
    anchor_resid = ev_residuals(anchor_rows, blind_edge)
    candidates = sorted({r["strategy"] for r in rows}
                        - {"_blind", ANCHOR}
                        - {s for s in {r["strategy"] for r in rows}
                           if len({r["ev"] for r in rows if r["strategy"] == s}) < 10})

    print(f"ORTHOGONALITY GATE · anchor={ANCHOR} (N={len(anchor_resid)}) · seed {SEED} · "
          f"a candidate DIVERSIFIES iff G1(≥10 indep evts) ∧ G2(orth-component selection-real p≤{P_BAR}) ∧ G3(residual+shock independent)")
    print(f"\n{'candidate':<16}{'N':>5}{'indep':>6}{'%ind':>6}{'orth surplus':>13}{'orth p':>8}"
          f"{'r_shared':>9}{'r_shock':>8}{'  gates':>8}  verdict")
    print("-" * 96)
    results = []
    for c in candidates:
        crows = [r for r in rows if r["strategy"] == c]
        g = gate_candidate(c, anchor_rows, crows, anchor_resid, blind_cells, blind_edge, rng)
        results.append(g)
        gates = ("G1" if g["g1_pass"] else "··") + ("G2" if g["g2_pass"] else "··") + ("G3" if g["g3_pass"] else "··")
        surp = "n/a" if g["orth_surplus"] is None else f"{g['orth_surplus']:+.2%}"
        pp = "n/a" if g["orth_null_p"] is None else f"{g['orth_null_p']:.4f}"
        rs = "n/a" if g["r_shared"] is None else f"{g['r_shared']:+.2f}"
        rk = "n/a" if g["r_regime_shock"] is None else f"{g['r_regime_shock']:+.2f}"
        verdict = "DIVERSIFIES ✔" if g["diversifies"] else "no"
        print(f"{c:<16}{g['n_events']:>5}{g['n_independent']:>6}{g['frac_independent']*100:>5.0f}%"
              f"{surp:>13}{pp:>8}{rs:>9}{rk:>8}{gates:>8}  {verdict}")

    winners = [g for g in results if g["diversifies"]]
    print(f"\nVERDICT: {len(winners)} of {len(results)} candidates diversify favorite.")
    if not winners:
        print("  No orthogonal second edge exists in the CURRENT captured stream. Every candidate that adds")
        print("  independent volume (G1) either has no edge on that volume (G2 — the diversifying picks are")
        print("  the reliably-losing non-favorite residue) or co-moves with favorite (G3). This is the")
        print("  RIGOROUS backing for 'diversification is supply-limited, not allocation-limited' (D15):")
        print("  reliability accrues only with NEW uncorrelated SUPPLY (sibling breadth run) or forward time,")
        print("  NOT by recombining today's picks. The gate stands ready to certify a real orthogonal edge")
        print("  the instant one appears (post-WC MLB bridge, a trust-weighted layer once wallets certify).")
    else:
        for g in winners:
            print(f"  {g['candidate']}: +{g['eff_added_n']:.0f} effective independent bets, "
                  f"combined SE ×{g['se_shrink_if_real']:.2f} — CERTIFY via the constructor + accrual floors.")
    return results


# ---------------------------------------------------------------------------------------
# Self-test: injected orthogonal edge must PASS; nested + correlated decoys must FAIL.
# ---------------------------------------------------------------------------------------
def _mk(strategy, ev, entry, won, day="2026-06-29", slug=None):
    return {"strategy": strategy, "ev": ev, "event_slug": slug or ev, "entry": float(entry),
            "won": int(won), "day": day}


def _synth_rows(rng):
    """Blind universe + favorite + three decoys. Favorite: 60 fresh soccer/tennis events at
    0.7 with a real +edge. Decoys:
      NESTED   — re-picks favorite's exact events (0 independent).
      LOSING   — 40 DISJOINT mlb events at 0.7 that LOSE (the non-favorite residue mirror).
      ORTHO    — 40 DISJOINT crypto events at 0.7 with a real +edge, outcomes independent."""
    rows = []
    days = ["2026-06-29", "2026-06-30", "2026-07-01", "2026-07-02"]
    # blind band-4 (0.6-0.8) with base rate 0.70 → blind_edge[4] ≈ 0
    for i in range(400):
        rows.append(_mk("_blind", f"bl{i}", 0.70, 1 if rng.random() < 0.70 else 0,
                        days[i % 4], slug=f"fifwc-x{i}-2026-06-29"))
    # favorite: base rate 0.70 but wins 0.88 → +edge, on soccer/tennis
    fav_evs = []
    for i in range(60):
        ev = f"fifwc-fav{i}-2026-06-29"
        fav_evs.append((ev, days[i % 4]))
        rows.append(_mk("favorite", ev, 0.70, 1 if rng.random() < 0.88 else 0, days[i % 4], slug=ev))
    # NESTED decoy: same events, mirrors favorite outcome residual (fully correlated, 0 indep)
    for ev, day in fav_evs:
        won = next(r["won"] for r in rows if r["strategy"] == "favorite" and r["ev"] == ev)
        rows.append(_mk("nested", ev, 0.70, won, day, slug=ev))
    # LOSING decoy: disjoint mlb events, wins only 0.55 (< 0.70 base) → negative edge
    for i in range(40):
        ev = f"mlb-los{i}-2026-06-30"
        rows.append(_mk("losing", ev, 0.70, 1 if rng.random() < 0.55 else 0, days[i % 4], slug=ev))
    # ORTHO decoy: disjoint crypto events, wins 0.88 → real +edge, independent outcomes
    for i in range(40):
        ev = f"btc-ort{i}-2026-07-01"
        rows.append(_mk("ortho", ev, 0.70, 1 if rng.random() < 0.88 else 0, days[i % 4], slug=ev))
    return rows


def selftest():
    ok = True
    rng = random.Random(SEED)
    rows = _synth_rows(rng)
    blind_edge = blind_edge_map(rows)
    blind_cells = defaultdict(list)
    for r in rows:
        if r["strategy"] == "_blind":
            blind_cells[(sn.band(r["entry"]), r["day"])].append((r["ev"], r["won"] - r["entry"]))
    anchor_rows = [r for r in rows if r["strategy"] == "favorite"]
    anchor_resid = ev_residuals(anchor_rows, blind_edge)
    prng = random.Random(SEED)

    def gate(name):
        return gate_candidate(name, anchor_rows, [r for r in rows if r["strategy"] == name],
                              anchor_resid, blind_cells, blind_edge, prng)

    nested = gate("nested")
    c_nested = (nested["n_independent"] == 0) and (not nested["g1_pass"]) and (not nested["diversifies"])
    ok = ok and c_nested
    print(f"  [{'ok' if c_nested else 'FAIL'}] NESTED: {nested['n_independent']} indep events, "
          f"G1={nested['g1_pass']} → diversifies={nested['diversifies']} (want 0/False/False)")

    losing = gate("losing")
    c_losing = losing["g1_pass"] and (not losing["g2_pass"]) and (not losing["diversifies"])
    ok = ok and c_losing
    print(f"  [{'ok' if c_losing else 'FAIL'}] LOSING residue: G1={losing['g1_pass']} but "
          f"G2={losing['g2_pass']} (orth surplus {losing['orth_surplus']}) → diversifies={losing['diversifies']} (want T/F/F)")

    ortho = gate("ortho")
    c_ortho = ortho["g1_pass"] and ortho["g2_pass"] and ortho["g3_pass"] and ortho["diversifies"] \
        and ortho["se_shrink_if_real"] > 1.05
    ok = ok and c_ortho
    print(f"  [{'ok' if c_ortho else 'FAIL'}] ORTHO edge: G1={ortho['g1_pass']} G2={ortho['g2_pass']} "
          f"G3={ortho['g3_pass']} → diversifies={ortho['diversifies']}, SE×{ortho['se_shrink_if_real']} (want all True)")

    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    results = run_live()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports", "edge_orthogonality.json")
    with open(out, "w") as f:
        json.dump(results, f, indent=1, default=str)
    print("\nartifact → reports/edge_orthogonality.json")


if __name__ == "__main__":
    main()
