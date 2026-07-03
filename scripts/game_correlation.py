#!/usr/bin/env python3
"""
GAME CORRELATION — the book's true unit of correlation is the GAME (match-key), not the
position and not the event_slug.

The companion to portfolio_concentration.py and the input to corr_risk_engine.py. Sizing
sizes an edge; the concentration instrument (portfolio_concentration.py) measured how few
INDEPENDENT bets the record holds at the SLATE grain and reported ICC_slate ≈ 0.008. This
instrument corrects the UNIT: the `favorite` book holds ~220 positions on only ~78 GAMES,
62–66% of them on ~10 World-Cup soccer games. Every position on one game (moneyline, spread,
"team to advance", halftime, O/U, six "Exact Score X — No") resolves on the SAME underlying
outcome. The correlation unit is therefore the GAME (superkey.super_event), and it is far
coarser than either the event_slug the gate clusters on or the slate the risk engine blocks on.

Why ICC_slate ≈ 0.008 is a BENIGN-SAMPLE ARTIFACT (one paragraph, reproduced numerically):
portfolio_concentration measured the ICC of the advantage RESIDUAL (a − matched-blind edge),
which SUBTRACTS the shared favorite factor by construction; on a 93%-win record with no losing
day the residual variance is near zero (⇒ ICC ⇒ 0); and the event-clustering step had already
collapsed the worst same-event_slug stacks BEFORE the ICC was measured. Measure the correlation
of the RAW win outcome at the GAME grain instead and the picture is different — but even THAT is
a lower bound, because on this 4-day record NO stacked favorite team was upset, so the shared
within-game shock (moneyline+spread+advance+halftime all resolving against together) was never
sampled. The measured within-game correlation ≈ 0 is the discordance of a handful of
idiosyncratic single-market losses; the structural block correlation is invisible until an upset
occurs, and the mechanism guarantees it is large. So this instrument reports the measured
within-game correlation as an explicit LOWER BOUND and hands corr_risk_engine.py a w_game to
SWEEP, not to trust.

Read-only, paper-only, changes nothing live. Reuses superkey.super_event (the canonical match
key — falls back to `slug` for the empty-event_slug WC rows, which pc.match_key does NOT),
portfolio_concentration.icc_oneway/n_eff, effective_n.cluster_robust, and selection_null
band/regime.

Modes:
  ./game_correlation.py            # live DB; the game-grain concentration table; writes JSON
  ./game_correlation.py --selftest # injected known within-game-correlation fixtures; the
                                   # estimators must recover them and order correctly. Exit !=0 on fail.
"""

import csv
import io
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import portfolio_concentration as pc   # icc_oneway, n_eff
import effective_n as en               # cluster_robust
import selection_null as sn            # band(), regime()
from superkey import super_event       # canonical GAME key

POPULATIONS = ["favorite", "elite_fresh_fav", "strict"]
SEED = 20260702
HAIRCUT = 0.005
FEE = 0.02
STAKE = 100.0

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]
SQL = """SELECT strategy, event_slug, slug, condition_id,
       COALESCE(initial_mean_price, mean_price) AS entry,
       (outcome_won::int) AS won,
       to_char(first_detected_at AT TIME ZONE 'UTC', 'YYYY-MM-DD') AS day
FROM consensus_signals WHERE resolved"""


def fetch():
    out = subprocess.run(PG + ["-f", "-"], input=SQL, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    rows = []
    for r in csv.DictReader(io.StringIO(out.stdout)):
        r["entry"] = float(r["entry"])
        r["won"] = int(r["won"])
        rows.append(r)
    return rows


def game_key(r):
    return super_event(r["event_slug"], r["slug"]) or r["condition_id"]


def event_key(r):
    return r["event_slug"] or r["condition_id"]


def fs_pnl(entry, won):
    """flat-shares realizable P&L of one position (100 shares)."""
    c = min(0.999, entry + HAIRCUT)
    return STAKE * (won - c) - FEE * STAKE * c


def within_game_pair_concordance(by_game):
    """Fraction of same-game position PAIRS whose win outcomes agree. Compared to the
    independence baseline p²+(1-p)² at the pooled win rate — excess over baseline is the
    ONLY model-free signal of within-game correlation, and on a no-upset record it is ~0."""
    agree = tot = 0
    wins = []
    for rs in by_game.values():
        w = [r["won"] for r in rs]
        wins.extend(w)
        for i in range(len(w)):
            for j in range(i + 1, len(w)):
                tot += 1
                agree += (w[i] == w[j])
    if tot == 0:
        return None
    p = float(np.mean(wins))
    baseline = p * p + (1 - p) * (1 - p)
    return {"concordance": agree / tot, "independence_baseline": baseline,
            "excess": agree / tot - baseline, "n_pairs": tot, "win_rate": p}


def concentration(prows):
    by_game = defaultdict(list)
    for r in prows:
        by_game[game_key(r)].append(r)
    n_pos = len(prows)
    n_games = len(by_game)
    n_events = len({event_key(r) for r in prows})

    sizes = sorted((len(v) for v in by_game.values()), reverse=True)
    top = Counter({g: len(v) for g, v in by_game.items()}).most_common(10)
    top10_pos = sum(n for _, n in top)

    # regime / world-cup concentration
    wc_pos = sum(1 for r in prows if game_key(r).startswith("fifwc"))
    wc_games = len({game_key(r) for r in prows if game_key(r).startswith("fifwc")})

    # win-indicator ICC at GAME grain (design-effect ICC on the RAW outcome — the number
    # portfolio_concentration deliberately did NOT compute, because it worked on residuals).
    wins_by_game = [[r["won"] for r in rs] for rs in by_game.values()]
    icc_win, mbar_g, kg, ng = pc.icc_oneway(wins_by_game)
    ne_win, de_win = pc.n_eff(ng, mbar_g, icc_win)
    # P&L ICC at game grain — the bankroll-swing view.
    pnl_by_game = [[fs_pnl(r["entry"], r["won"]) for r in rs] for rs in by_game.values()]
    icc_pnl, _, _, _ = pc.icc_oneway(pnl_by_game)

    # cluster-robust n_eff at the GAME grain (spans the ICC endpoints; effective_n machinery).
    ev_pnl = {}      # one aggregate per game (mean position P&L) → game-clustered CR n_eff
    ev_cluster = {}
    for g, rs in by_game.items():
        for i, r in enumerate(rs):
            k = f"{g}#{i}"
            ev_pnl[k] = fs_pnl(r["entry"], r["won"])
            ev_cluster[k] = g
    cr = en.cluster_robust(ev_pnl, ev_cluster)

    # data-driven LOWER-BOUND within-game correlation, from mixed-outcome games only.
    mixed = [w for w in wins_by_game if 0 < sum(w) < len(w)]
    icc_mixed, _, k_mixed, _ = pc.icc_oneway(mixed) if len(mixed) >= 2 else (0.0, 0, len(mixed), 0)
    conc = within_game_pair_concordance(by_game)

    # worst-game block loss under a hypothetical FULL upset (all positions lose) — the tail the
    # record never sampled; and the as-resolved block P&L for contrast.
    worst = []
    for g, rs in sorted(by_game.items(), key=lambda kv: -len(kv[1]))[:10]:
        worst.append({"game": g, "n_pos": len(rs),
                      "pnl_as_resolved": round(sum(fs_pnl(r["entry"], r["won"]) for r in rs), 0),
                      "pnl_if_full_upset": round(sum(fs_pnl(r["entry"], 0) for r in rs), 0),
                      "pnl_if_all_chalk": round(sum(fs_pnl(r["entry"], 1) for r in rs), 0),
                      "win_rate": round(float(np.mean([r["won"] for r in rs])), 2)})

    return {
        "n_positions": n_pos, "n_games": n_games, "n_event_slug_clusters": n_events,
        "positions_per_game_mean": round(n_pos / n_games, 2),
        "positions_per_game_top10": [{"game": g, "n": n} for g, n in top],
        "top10_games_hold_pct": round(100 * top10_pos / n_pos, 1),
        "size_distribution": sizes[:15],
        "world_cup": {"positions": wc_pos, "share_pct": round(100 * wc_pos / n_pos, 1),
                      "games": wc_games},
        "icc_win_game_grain": round(icc_win, 4),
        "n_eff_win_game_grain": round(ne_win, 1),
        "icc_pnl_game_grain": round(icc_pnl, 4),
        "cr_n_eff_game_grain": (round(cr["n_eff_CR"], 1) if cr else None),
        "cr_n_clusters": (cr["G"] if cr else None),
        "within_game_lower_bound": {
            "n_mixed_games": k_mixed, "icc_mixed_games": round(icc_mixed, 4),
            "pair_concordance": (round(conc["concordance"], 4) if conc else None),
            "independence_baseline": (round(conc["independence_baseline"], 4) if conc else None),
            "excess_over_independence": (round(conc["excess"], 4) if conc else None)},
        "worst_game_blocks": worst,
    }


def run(populations=POPULATIONS, quiet=False):
    rows = fetch()
    result = {"meta": {"seed": SEED, "haircut": HAIRCUT, "fee": FEE,
                       "days": sorted({r["day"] for r in rows}),
                       "populations": populations,
                       "game_key": "superkey.super_event (falls back to slug; strips through first date)"},
              "strategies": {}}
    for p in populations:
        prows = [r for r in rows if r["strategy"] == p]
        if not prows:
            continue
        result["strategies"][p] = concentration(prows)
    if not quiet:
        _print(result)
    return result


def _print(result):
    days = result["meta"]["days"]
    print(f"GAME CORRELATION · record {len(days)}d {days[0]}→{days[-1]} · "
          f"game key = super_event (match-level; falls back to slug)")
    print("\nTHE TRUE CORRELATION UNIT IS THE GAME — positions ≫ event_slugs ≫ GAMES")
    hdr = (f"{'strategy':<16}{'pos':>5}{'ev_slug':>8}{'GAMES':>7}{'pos/game':>9}"
           f"{'top10%':>8}{'WC%':>6}")
    print(hdr); print("-" * len(hdr))
    for p, c in result["strategies"].items():
        print(f"{p:<16}{c['n_positions']:>5}{c['n_event_slug_clusters']:>8}{c['n_games']:>7}"
              f"{c['positions_per_game_mean']:>9}{c['top10_games_hold_pct']:>7}%"
              f"{c['world_cup']['share_pct']:>5}%")
    print("\nHOW MANY INDEPENDENT BETS AT THE GAME GRAIN? (the honest denominator)")
    print(f"{'strategy':<16}{'ICC_win':>9}{'Neff_win':>9}{'ICC_pnl':>9}{'CR_Neff':>9}{'clusters':>9}")
    for p, c in result["strategies"].items():
        print(f"{p:<16}{c['icc_win_game_grain']:>9.3f}{c['n_eff_win_game_grain']:>9.1f}"
              f"{c['icc_pnl_game_grain']:>9.3f}{str(c['cr_n_eff_game_grain']):>9}"
              f"{str(c['cr_n_clusters']):>9}")
    print("\nWITHIN-GAME CORRELATION — the MEASURED value is a LOWER BOUND (no upset was sampled)")
    for p, c in result["strategies"].items():
        lb = c["within_game_lower_bound"]
        print(f"  {p}: {lb['n_mixed_games']} mixed games, ICC(mixed)={lb['icc_mixed_games']:.3f}; "
              f"pair-concordance {lb['pair_concordance']} vs independence "
              f"{lb['independence_baseline']} → excess {lb['excess_over_independence']:+}")
    fav = result["strategies"].get("favorite")
    if fav:
        print("\nWORST GAME BLOCKS (favorite) — as-resolved vs the FULL-UPSET tail the record never sampled")
        print(f"  {'n':>3} {'as-resolved':>12} {'all-chalk':>10} {'FULL-UPSET':>11}  game")
        for w in fav["worst_game_blocks"]:
            print(f"  {int(w['n_pos']):>3} {w['pnl_as_resolved']:>+12.0f} {w['pnl_if_all_chalk']:>+10.0f} "
                  f"{w['pnl_if_full_upset']:>+11.0f}  {w['game']}")
        print("  → a single stacked-game upset is a synchronised −$0.9k…−$1.5k block loss vs ~+$0.1–0.3k chalk.")


# --- self-test: injected known within-game correlation must be recovered / ordered ----------
def _synth(icc_target, n_games=60, per_game=8, wr=0.85, seed=SEED):
    """Games with a KNOWN within-game outcome correlation. Latent game shock g~N(0,icc),
    idiosyncratic e~N(0,1-icc); win if (g+e) <= Phi^{-1}(wr). True within-game ICC ≈ icc_target."""
    from statistics import NormalDist
    rng = np.random.default_rng(seed)
    thr = NormalDist().inv_cdf(wr)
    sb, sw = np.sqrt(icc_target), np.sqrt(1 - icc_target)
    by_game = {}
    for gi in range(n_games):
        u = rng.normal(0, sb) if sb > 0 else 0.0
        by_game[f"g{gi}"] = [{"won": int((u + rng.normal(0, sw)) <= thr),
                              "entry": 0.85} for _ in range(per_game)]
    return by_game


def selftest():
    ok = True
    print("— within-game ICC recovery + ordering (win-indicator, game grain) —")
    iccs = {}
    for target in (0.0, 0.3, 0.7):
        vals = []
        for sd in range(6):
            by_game = _synth(target, seed=SEED + sd)
            wins = [[r["won"] for r in rs] for rs in by_game.values()]
            icc, _, _, _ = pc.icc_oneway(wins)
            vals.append(icc)
        iccs[target] = float(np.mean(vals))
        # binary ICC is attenuated vs the latent target; require monotone recovery + right sign
        print(f"  target {target:.1f} → measured win-ICC {iccs[target]:.3f}")
    c_order = iccs[0.0] < iccs[0.3] < iccs[0.7] and iccs[0.0] < 0.08 and iccs[0.7] > 0.25
    ok = ok and c_order
    print(f"  [{'ok' if c_order else 'FAIL'}] iid≈0 < mid < high, monotone & sign-correct")

    print("— pair concordance: independent fixture ⇒ excess ≈ 0 —")
    by_game = _synth(0.0, seed=SEED + 99)
    conc = within_game_pair_concordance(by_game)
    c_ind = abs(conc["excess"]) < 0.03
    ok = ok and c_ind
    print(f"  [{'ok' if c_ind else 'FAIL'}] excess {conc['excess']:+.3f} (indep ⇒ ≈0)")
    by_game_hi = _synth(0.7, seed=SEED + 98)
    conc_hi = within_game_pair_concordance(by_game_hi)
    c_hi = conc_hi["excess"] > 0.05
    ok = ok and c_hi
    print(f"  [{'ok' if c_hi else 'FAIL'}] correlated excess {conc_hi['excess']:+.3f} > indep")

    print("— cluster-robust n_eff at game grain: fully-correlated ⇒ ≈#games —")
    ev_pnl, ev_cl = {}, {}
    G = 30
    rng = np.random.default_rng(SEED)
    gval = {f"g{j}": float(rng.normal()) for j in range(G)}
    for j in range(G):
        for i in range(8):
            ev_pnl[f"g{j}_{i}"] = gval[f"g{j}"]   # identical within game ⇒ ICC=1
            ev_cl[f"g{j}_{i}"] = f"g{j}"
    cr = en.cluster_robust(ev_pnl, ev_cl)
    c_cr = abs(cr["n_eff_CR"] - G) <= 1.5
    ok = ok and c_cr
    print(f"  [{'ok' if c_cr else 'FAIL'}] n_eff_CR {cr['n_eff_CR']:.1f} ≈ G={G}")

    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    result = run()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "reports", "game_correlation.json")
    with open(out, "w") as f:
        json.dump(result, f, indent=1, default=str)
    print("\nartifact → reports/game_correlation.json")


if __name__ == "__main__":
    main()
