#!/usr/bin/env python3
"""
RELIABILITY-FIRST PORTFOLIO CONSTRUCTOR — the book that maximises growth per unit of TRUE
independent exposure, and the price of the reliability we do not yet have.

The capstone of the reliability run. It composes the three prior instruments into one
decision:

  * effective_n.py       → the honest sample size (cluster-robust n_eff, Q1) + the
                           persistence floor (disjoint regime-blocks, Q2).
  * edge_orthogonality.py→ the MENU of edges that actually diversify (today: only favorite;
                           elite_fresh_fav is nested; no orthogonal partner exists yet).
  * risk_engine.py       → the frozen sizing policy menu × block-bootstrap Monte Carlo.

The algorithm (belief-blind; it sizes edges, it never invents one):

  1. DEDUP.  Build the book from the menu, greedily dropping any edge that adds < MIN_INDEP
     independent events over the events already in the book (elite_fresh_fav ⊂ favorite ⇒
     adds 0 ⇒ never enters the book — a {favorite, eff} 'portfolio' is just favorite).
  2. SIZE.   Pick the sizing policy by the risk engine's FROZEN rule (max median log-growth
     s.t. P(maxDD>30%) ≤ 10%), with the honesty override to the structurally-capped policy
     when the ceiling is slack (the 4-day record has no losing slate to price a drawdown).
  3. SCORE per RELIABILITY, not per bet.  A book's growth is trusted only out to its
     n_eff (Q1); horizons beyond n_eff are labelled EXTRAPOLATION (K1). Among admissible
     books the objective is median log-growth per 100 events, s.t. the drawdown ceiling AND
     an n_eff trust floor, tie-broken by higher n_eff (reliability). With one edge in the
     menu the construction is trivial — the VALUE is making the objective explicit so a
     second edge is allocated by data the instant one certifies.
  4. PRICE what is missing.  Reuse the risk engine's independent-regime Monte Carlo to price
     the marginal reliability an ADDITIONAL uncorrelated edge/regime would buy (P(loss) and
     SE reduction per added regime) — whether it arrives as breadth SUPPLY (sibling run) or a
     matured orthogonal edge (edge_orthogonality's trust_weighted watch-item). The number
     that says how valuable the search for a second edge actually is.

Output = the PRE-REGISTERED reliability-first book for the hypothetical real-money day (still
gated on D7 + persistence accrual + Tue): which edges, sized how, with P(profit)/P(maxDD) at
each horizon, the conditional-on-edge caveat on every line, and the accrual triggers. Nothing
is promoted, nothing touches money, zero migrations.

Modes:
  ./portfolio_constructor.py            # live DB; the book + the orthogonal-edge price; JSON
  ./portfolio_constructor.py --selftest # dedup/monotonicity/independence-value invariants
"""

import json
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import selection_null as sn
import risk_engine as rk_risk
import rekey_headline as rk
import effective_n as en
import edge_orthogonality as eo

SEED = 20260702
MIN_INDEP = 10           # an edge must add ≥ this many independent events to enter the book
N_PATHS = 8_000
# The certifiable-quality anchor + any strategy the orthogonality gate CERTIFIES as a
# diversifier (built from data, not hardcoded). elite_fresh_fav is kept as an explicit
# nested-dedup demonstration; the anchor is always considered.
BASE_MENU = ["favorite", "elite_fresh_fav"]


def build_menu(rows):
    """MENU = anchor + explicit nested demo + every edge_orthogonality diversifier (G1∧G2∧G3).
    Today the gate certifies none, so MENU == BASE_MENU — but a matured orthogonal edge would
    enter automatically, which is the whole point of composing the gate rather than hardcoding."""
    results, _, _ = eo.evaluate(rows)
    diversifiers = [g["candidate"] for g in results if g["diversifies"]]
    menu = list(BASE_MENU)
    for d in diversifiers:
        if d not in menu:
            menu.append(d)
    return menu, diversifiers


def build_book(menu, pop_rows):
    """Greedy dedup: add edges in menu order, keeping only those that contribute ≥ MIN_INDEP
    events not already covered. Returns (selected names, merged rows, per-edge contribution)."""
    seen_evs, selected, merged, contrib = set(), [], [], {}
    for name in menu:
        rows = pop_rows.get(name, [])
        evs = {r["ev"] for r in rows}
        new = evs - seen_evs
        contrib[name] = {"n_events": len(evs), "independent_added": len(new)}
        if len(new) >= MIN_INDEP:
            selected.append(name)
            merged.extend([r for r in rows if r["ev"] in new])   # only its NEW events
            seen_evs |= evs
        # else: dropped (nested / redundant) — adds < MIN_INDEP independent bets
    return selected, merged, contrib


def score_book(events, n_eff_day, n_paths, seed):
    """Size the merged book by the risk engine's frozen rule + honesty override, and score it
    per reliability (n_eff trust floor; horizons beyond n_eff = extrapolation)."""
    res, kelly_full = rk_risk.run_strategy(events, "slate", n_paths, seed)
    rec = rk_risk.recommend(res)
    policy = rec["honest_recommendation"]
    B0 = str(int(rk_risk.BANKROLLS[0]))
    cells = {}
    for H in rk_risk.HORIZONS:
        s = res[policy][B0][str(H)]
        cells[str(H)] = {
            "median_pnl": s["median_pnl"], "p5_pnl": s["p5_pnl"], "p_profit": s["p_profit"],
            "p_maxdd_over_30pct": s["p_maxdd_over_30pct"], "p_ruin": s["p_ruin"],
            "median_log_growth_per_100ev": s["median_log_growth_per_100ev"],
            "extrapolation_beyond_n_eff": H > n_eff_day,
        }
    return {"policy": policy, "recommendation_detail": rec,
            "kelly_by_band": {str(k): round(v, 4) for k, v in kelly_full.items()},
            "cells": cells}, kelly_full


def price_independence(events, kelly_full, n_paths, seed):
    """Marginal reliability value of an ADDITIONAL uncorrelated edge/regime: spread the same
    H=100 volume across k independent regimes (risk_engine.simulate_multiregime) and report
    P(loss) + SE per k. Whether the k-th regime comes from breadth supply or a matured
    orthogonal edge, this is what independence is worth at favorite's ~0 within-slate corr."""
    out = {}
    prev = None
    for k in (1, 2, 3, 4):
        m = rk_risk.simulate_multiregime(events, "flat_shares_100", 1000.0, n_paths,
                                         seed + k, kelly_full, k, H=100)
        p_loss = 1.0 - m["p_profit"]
        row = {"p_loss": round(p_loss, 4), "sd_pnl": round(m["sd_pnl"], 1),
               "median_pnl": round(m["median_pnl"], 1), "p5_pnl": round(m["p5_pnl"], 1)}
        if prev is not None:
            row["p_loss_reduction_vs_prev"] = round(prev["p_loss"] - p_loss, 4)
            row["sd_reduction_frac_vs_prev"] = round(1 - m["sd_pnl"] / prev["sd_pnl"], 4) \
                if prev["sd_pnl"] else None
        out[f"{k}_independent_regimes"] = row
        prev = {"p_loss": p_loss, "sd_pnl": m["sd_pnl"]}
    return out


def run_live():
    rows = sn.fetch()
    rk_rows = rk.fetch()
    nc = rk.n_core(rk_rows)
    menu, diversifiers = build_menu(rows)
    pop_rows = {p: [r for r in rows if r["strategy"] == p] for p in menu}

    # honest cluster-robust n_eff (Q1) from effective_n
    recon = en.reconcile(rk_rows, "favorite", nc)
    n_eff_day = recon["n_eff_CR_day"] if recon else float("nan")

    selected, merged, contrib = build_book(menu, pop_rows)
    events = rk_risk.build_events(merged)
    book, kelly_full = score_book(events, n_eff_day, N_PATHS, SEED)
    price = price_independence(events, kelly_full, rk_risk.N_PATHS_SENS, SEED + 50)

    print("RELIABILITY-FIRST PORTFOLIO CONSTRUCTOR")
    print("ALL P(profit) ARE CONDITIONAL ON THE MEASURED EDGE BEING REAL & PERSISTING (D7). "
          "Sizing sizes an edge; it cannot create one.\n")
    print(f"MENU considered (belief-blind) = anchor + nested-demo + orthogonality-certified diversifiers: {menu}")
    print(f"  (edge_orthogonality certified {len(diversifiers)} diversifier(s) today: {diversifiers or 'none'})")
    print("STEP 1 — dedup (an edge enters the book only if it adds ≥%d independent bets):" % MIN_INDEP)
    for name in menu:
        c = contrib[name]
        verdict = "SELECTED" if name in selected else f"DROPPED (adds {c['independent_added']} < {MIN_INDEP})"
        print(f"    {name:<18} {c['n_events']:>3} events, +{c['independent_added']:>3} independent → {verdict}")
    print(f"  ⇒ BOOK = {selected}  ({len({e['ev'] for e in events})} independent events; "
          f"honest cluster-robust n_eff ≈ {n_eff_day:.0f})")

    print(f"\nSTEP 2–3 — sizing (frozen rule + honesty override) → policy = {book['policy']}")
    print(f"  full-Kelly-by-band (SE-shrunk): "
          f"{', '.join(f'{k}:{v}' for k, v in sorted(book['kelly_by_band'].items())) or '(none)'}")
    print(f"  {'H (events)':>11}{'med P&L':>10}{'5th P&L':>10}{'P(profit)':>11}{'P(DD>30%)':>11}{'P(ruin)':>9}  trust")
    for H in rk_risk.HORIZONS:
        c = book["cells"][str(H)]
        trust = "EXTRAPOLATION (H>n_eff)" if c["extrapolation_beyond_n_eff"] else "within n_eff"
        print(f"  {H:>11}{c['median_pnl']:>+10.0f}{c['p5_pnl']:>+10.0f}{c['p_profit']:>11.1%}"
              f"{c['p_maxdd_over_30pct']:>11.1%}{c['p_ruin']:>9.1%}  {trust}")

    print("\nSTEP 4 — what a second edge is (and is NOT) worth, priced two honest ways:")
    print("  (a) DECORRELATING FIXED volume — same H=100 spread across k uncorrelated sub-streams (flat-shares):")
    print(f"      {'k regimes':>10}{'P(loss)':>9}{'SD P&L':>9}{'5th P&L':>10}{'ΔSD':>8}")
    for k in (1, 2, 3, 4):
        r = price[f"{k}_independent_regimes"]
        dsd = r.get("sd_reduction_frac_vs_prev")
        dsd_s = "" if dsd is None else f"{dsd:+.0%}"
        print(f"      {k:>10}{r['p_loss']:>9.1%}{r['sd_pnl']:>9.0f}{r['p5_pnl']:>+10.0f}{dsd_s:>8}")
    print("      → ~0 by construction: favorite's within-slate correlation is ≈0, so re-spreading the SAME")
    print("        volume buys almost nothing, and P(loss)=0% is the D15 no-losing-slate artifact (uninformative).")
    print("  (b) ADDING independent volume (√N) — the value edge_orthogonality.reliability_value prices: a")
    print("      clean orthogonal edge of Nb independent events shrinks the combined per-bet SE by √((Na+Nb)/Na).")
    print("      THIS is a second edge's real worth here — VOLUME + continuity (betting through post-WC supply")
    print("      droughts) + INSURANCE if favorite's edge degrades — NOT per-bet variance reduction of fixed volume.")

    print("\nVERDICT — the pre-registered reliability-first book (for the hypothetical GO day):")
    print(f"  • BOOK: {selected} only — sized {book['policy']} (⅛-Kelly per band, SE-shrunk, exposure-capped).")
    print("    elite_fresh_fav is nested in favorite → adds 0 independent bets → NOT in the book (never double-count).")
    print("  • RELIABILITY today comes ONLY from the structural caps (drawdown bounded by construction)")
    print("    and forward accrual — NOT from diversification: the orthogonality gate certified 0 partner edges,")
    print("    so there is nothing to spread across. A second edge's worth is added-volume/continuity/insurance")
    print("    (STEP 4b), not fixed-volume variance reduction (STEP 4a ≈ 0 at favorite's ~0 within-slate corr).")
    print("  • ACCRUAL TRIGGERS (re-run this constructor at each): post-WC + post-Wimbledon (first adverse")
    print("    regime — the DD ceiling may finally bind, unlocking ¼-Kelly); +50 favorite / +300 fleet events;")
    print("    any edge_orthogonality candidate reaching G1∧G2∧G3; and MANDATORY before any real-money pilot.")
    print("  • CONDITIONAL: if favorite's edge is not real or does not persist, every policy loses to costs.")

    return {"menu": menu, "diversifiers_certified": diversifiers, "book": selected,
            "contrib": contrib, "n_eff_day": n_eff_day, "sizing": book,
            "independence_price_fixed_volume": price}


# ---------------------------------------------------------------------------------------
# Self-test: dedup, extrapolation labelling, and the independence-value invariant.
# ---------------------------------------------------------------------------------------
def _synth_events(n, edge, seed, prefix, regimes=("a", "b", "c", "d"), days=4):
    """n independent events at entry 0.70 with P(win)=0.70+edge, spread across regimes/days."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        won = 1 if rng.random() < 0.70 + edge else 0
        rows.append({"strategy": prefix, "ev": f"{prefix}{i}", "event_slug": f"{regimes[i%len(regimes)]}-{i}",
                     "entry": 0.70, "won": won, "day": f"2026-06-2{9 - (i % days)}"})
    return rows


def selftest():
    ok = True

    # (1) dedup: a nested edge (identical event ids) must add 0 and be dropped.
    base = _synth_events(60, 0.15, SEED, "favorite")
    nested = [{**r, "strategy": "nested"} for r in base]            # same ev ids
    pop = {"favorite": base, "nested": nested}
    selected, merged, contrib = build_book(["favorite", "nested"], pop)
    c1 = selected == ["favorite"] and contrib["nested"]["independent_added"] == 0 \
        and len({e["ev"] for e in merged}) == 60
    ok = ok and c1
    print(f"  [{'ok' if c1 else 'FAIL'}] dedup: nested adds {contrib['nested']['independent_added']} → "
          f"book {selected} (want ['favorite'], 0)")

    # (2) a genuinely disjoint edge must be ADDED and enlarge the book.
    disj = _synth_events(40, 0.15, SEED + 1, "disj", regimes=("x", "y"))
    sel2, merged2, contrib2 = build_book(["favorite", "disj"], {"favorite": base, "disj": disj})
    c2 = sel2 == ["favorite", "disj"] and len({e["ev"] for e in merged2}) == 100
    ok = ok and c2
    print(f"  [{'ok' if c2 else 'FAIL'}] disjoint: book {sel2}, {len({e['ev'] for e in merged2})} events (want 2 edges, 100)")

    # (3) extrapolation labelling: horizons beyond n_eff flagged (n_eff=300 → H=100/300 within, 1000 beyond).
    events = rk_risk.build_events(base)
    kf = rk_risk.kelly_by_band(events)
    book, _ = score_book(events, n_eff_day=300, n_paths=1500, seed=SEED)
    c3 = book["cells"]["100"]["extrapolation_beyond_n_eff"] is False \
        and book["cells"]["1000"]["extrapolation_beyond_n_eff"] is True
    ok = ok and c3
    print(f"  [{'ok' if c3 else 'FAIL'}] extrapolation: H=100 within, H=1000 beyond n_eff=300 "
          f"({book['cells']['100']['extrapolation_beyond_n_eff']}/{book['cells']['1000']['extrapolation_beyond_n_eff']})")

    # (4) independence value: on a THIN-edge book (nonzero P(loss)), more independent regimes
    #     must NOT increase P(loss) — diversification of a real edge is never harmful.
    thin = _synth_events(120, 0.03, SEED + 5, "thin")
    tev = rk_risk.build_events(thin)
    tkf = rk_risk.kelly_by_band(tev)
    price = price_independence(tev, tkf, 4000, SEED + 9)
    pl1 = price["1_independent_regimes"]["p_loss"]
    pl4 = price["4_independent_regimes"]["p_loss"]
    c4 = pl4 <= pl1 + 0.02 and pl1 > 0.0   # meaningful: there IS loss probability to (not) reduce
    ok = ok and c4
    print(f"  [{'ok' if c4 else 'FAIL'}] independence value: P(loss) 1-regime {pl1:.1%} → 4-regime {pl4:.1%} "
          f"(nonzero, must not rise)")

    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    result = run_live()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports", "portfolio_constructor.json")
    with open(out, "w") as f:
        json.dump(result, f, indent=1, default=str)
    print("\nartifact → reports/portfolio_constructor.json")


if __name__ == "__main__":
    main()
