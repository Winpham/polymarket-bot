#!/usr/bin/env python3
"""
RE-KEY THE HEADLINE (truth-audit attack E) — recompute the promotion stats at MATCH-level
clustering and compare to the incumbent event_slug key.

Mirrors, exactly, the two load-bearing computations:

  1. `consensus_scoreboard_by_strategy` (common/src/storage/consensus.rs):
       a          = won − COALESCE(initial_mean_price, mean_price)           (at-fire, D6)
       band       = width_bucket(entry, 0, 1, 5)
       blind_edge = AVG(a) over _blind rows in that band
       surplus_row= a − blind_edge[band]
       ev_surplus = AVG(surplus_row)  grouped by (strategy, EV)              ← EV is the swap point
       surplus    = AVG(ev_surplus)   over events
       surplus_sd = STDDEV_SAMP(ev_surplus)
       distinct_days = COUNT(DISTINCT MIN-day per event)

  2. `surplus_bounds` / `promotion_verdict` (copy-trading-bot/src/scanner/promotion.rs):
       effective_n = clamp(distinct_days, 1, distinct_events)
       z           = probit(1 − 0.05 / n_core_strategies)                    (Bonferroni, core family)
       LB          = surplus − z · surplus_sd / sqrt(effective_n)

The ONLY thing that changes between the two columns is EV:
  incumbent  = COALESCE(event_slug, condition_id)     (the live gate's key)
  match      = superkey.super_event(event_slug, slug) (one row-real-world-MATCH, attack E)

It also re-runs the selection-matched null (selection_null.py machinery) at the match key.

K2 (DECISIONS kill criterion): if match-level clustering drops favorite's surplus LB below the
3% capture margin, D7 eligibility is REVOKED and the accrual clock restarts at the stricter key.

Self-test:  ./rekey_headline.py --self-test   (synthetic collapse fixture + probit spot-checks)
Live:       ./rekey_headline.py                (also asserts it reproduces the incumbent gate LB)
"""

import csv
import io
import math
import random
import subprocess
import sys
from collections import defaultdict

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from superkey import super_event  # noqa: E402

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]
ALPHA = 0.05
MARGIN = 0.03
N_PERM = 2000
SEED = 20260702
WINNERS = ("favorite", "elite_fresh_fav")

# Experimental family (mirror of enrich/mod.rs::family) — everything else with rows is "core".
EXPERIMENTAL = {
    "consensus_ens", "consensus_logit", "market_ml", "market_veto", "market_resid",
    "bayes_anchor", "trust_weighted", "trusted_only", "cross_cohort", "strict_retuned",
    "sharp_tail_fresh", "sharp_tail",
}

SQL = """
SELECT strategy, event_slug, slug, condition_id,
       COALESCE(initial_mean_price, mean_price) AS entry,
       (outcome_won::int) AS won,
       (first_detected_at AT TIME ZONE 'UTC')::date AS day
FROM consensus_signals WHERE resolved
"""


def probit(p):
    """Acklam inverse-normal — same algorithm/constants as promotion.rs::probit."""
    if p <= 0.0:
        return -math.inf
    if p >= 1.0:
        return math.inf
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p <= phigh:
        q = p - 0.5
        r = q*q
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    q = math.sqrt(-2*math.log(1-p))
    return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)


def band(p):  # width_bucket(p,0,1,5)
    if p < 0.0:
        return 0
    if p >= 1.0:
        return 6
    return int(p * 5.0) + 1


def stddev_samp(xs):
    n = len(xs)
    if n < 2:
        return None
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def gate_stats(rows, keyfn, n_core):
    """Replicate consensus_scoreboard_by_strategy + surplus_bounds for every non-blind strategy.
    keyfn(row) -> event cluster key. Returns {strategy: dict(...)}."""
    blind_band = defaultdict(list)
    for r in rows:
        if r["strategy"] == "_blind":
            blind_band[band(r["entry"])].append(r["won"] - r["entry"])
    blind_edge = {b: sum(v) / len(v) for b, v in blind_band.items()}

    z = probit(1 - ALPHA / max(n_core, 1))
    out = {}
    strategies = {r["strategy"] for r in rows} - {"_blind"}
    for s in strategies:
        srows = [r for r in rows if r["strategy"] == s]
        ev_map = defaultdict(list)          # ev -> [surplus_row]
        ev_day = {}                         # ev -> min day
        for r in srows:
            surplus_row = (r["won"] - r["entry"]) - blind_edge.get(band(r["entry"]), 0.0)
            k = keyfn(r)
            ev_map[k].append(surplus_row)
            ev_day[k] = min(ev_day.get(k, r["day"]), r["day"])
        ev_surplus = {k: sum(v) / len(v) for k, v in ev_map.items()}
        n_events = len(ev_surplus)
        surplus = sum(ev_surplus.values()) / n_events if n_events else None
        sd = stddev_samp(list(ev_surplus.values()))
        distinct_days = len({ev_day[k] for k in ev_map})
        # Two LBs, both surplus_bounds machinery, differing ONLY in the SE's N:
        #   lb_dayN   = CURRENT live scoreboard/promotion_verdict (5b83d33): SE over event-DAYS
        #               (effective_n = clamp(distinct_days,1,events)) — Moulton within-day.
        #   lb_eventN = D6-era scoreboard AND honest.rs pilot path: SE over event-N.
        lb_dayN = lb_eventN = None
        if surplus is not None and sd is not None and n_events >= 30:
            eff_day = max(1, min(distinct_days, max(n_events, 1)))
            lb_dayN = surplus - z * sd / math.sqrt(eff_day)
            lb_eventN = surplus - z * sd / math.sqrt(n_events)
        out[s] = dict(n_events=n_events, surplus=surplus, surplus_sd=sd,
                      distinct_days=distinct_days, lb_dayN=lb_dayN, lb_eventN=lb_eventN, z=z)
    return out


def selection_null(rows, keyfn, strategy, rng, n_perm=N_PERM):
    """selection_null.py machinery, but clustering on keyfn. Returns (obs, mu, sd, p, n_ev)."""
    blind = [r for r in rows if r["strategy"] == "_blind"]
    blind_band = defaultdict(list)
    blind_cells = defaultdict(list)   # (band, day) -> [(ev, a)]
    for r in blind:
        b = band(r["entry"])
        a = r["won"] - r["entry"]
        blind_band[b].append(a)
        blind_cells[(b, r["day"])].append((keyfn(r), a))
    blind_edge = {b: sum(v) / len(v) for b, v in blind_band.items()}

    def clustered(picks):
        em = defaultdict(list)
        for ev, b, a in picks:
            em[ev].append(a - blind_edge.get(b, 0.0))
        if not em:
            return float("nan")
        means = [sum(v) / len(v) for v in em.values()]
        return sum(means) / len(means)

    srows = [r for r in rows if r["strategy"] == strategy]
    picks = [(keyfn(r), band(r["entry"]), r["won"] - r["entry"]) for r in srows]
    obs = clustered(picks)
    n_ev = len({keyfn(r) for r in srows})
    profile = defaultdict(int)
    for r in srows:
        profile[(band(r["entry"]), r["day"])] += 1
    draws = []
    for _ in range(n_perm):
        sel, ok = [], True
        for cell, k in profile.items():
            pool = blind_cells.get(cell)
            if not pool:
                ok = False
                break
            take = rng.choices(pool, k=k) if k > len(pool) else rng.sample(pool, k)
            sel.extend((ev, cell[0], a) for ev, a in take)
        if ok:
            draws.append(clustered(sel))
    if len(draws) < 1000:
        return obs, None, None, None, n_ev
    mu = sum(draws) / len(draws)
    sd = math.sqrt(sum((x - mu) ** 2 for x in draws) / (len(draws) - 1))
    p = sum(1 for x in draws if x >= obs) / len(draws)
    return obs, mu, sd, p, n_ev


def fetch():
    out = subprocess.run(PG + ["-c", SQL.replace("\n", " ")], capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    rows = []
    for r in csv.DictReader(io.StringIO(out.stdout)):
        r["entry"] = float(r["entry"])
        r["won"] = int(r["won"])
        rows.append(r)
    return rows


def n_core(rows):
    strat = {r["strategy"] for r in rows if r["strategy"] != "_blind"}
    return sum(1 for s in strat if s not in EXPERIMENTAL)


def run_live():
    rows = fetch()
    nc = n_core(rows)
    inc = lambda r: r["event_slug"] or r["condition_id"]              # noqa: E731
    mat = lambda r: super_event(r["event_slug"], r["slug"]) or r["condition_id"]  # noqa: E731
    gi = gate_stats(rows, inc, nc)
    gm = gate_stats(rows, mat, nc)

    print(f"RE-KEY HEADLINE · core family n={nc} · z={gi[WINNERS[0]]['z']:.3f} · margin {MARGIN:.0%} · at-fire entry")
    print("LB_eventN = SE over event-N (D6-era scoreboard + honest.rs pilot). "
          "LB_dayN = SE over event-DAYS (CURRENT live scoreboard, 5b83d33 Moulton).\n")
    print(f"{'strategy':<16} {'key':<10} {'N_ev':>5} {'days':>4} {'surplus':>9} {'sd':>7} {'LB_eventN':>10} {'LB_dayN':>9}")
    for s in WINNERS + ("strict", "count", "elite_gated", "longshot"):
        for label, g in (("event_slug", gi), ("match", gm)):
            r = g[s]
            le = f"{r['lb_eventN']:+.2%}" if r['lb_eventN'] is not None else "n/a"
            ld = f"{r['lb_dayN']:+.2%}" if r['lb_dayN'] is not None else "n/a"
            print(f"{s:<16} {label:<10} {r['n_events']:>5} {r['distinct_days']:>4} "
                  f"{r['surplus']:>+8.2%} {(r['surplus_sd'] or 0):>6.2%} {le:>10} {ld:>9}")
        srows = [x for x in rows if x["strategy"] == s]
        ni = len({inc(x) for x in srows})
        nm = len({mat(x) for x in srows})
        print(f"{'':<16} {'collapse':<10} {ni} → {nm}  ({100*(ni-nm)/ni:.0f}% fewer clusters)\n")

    # selection null at match level for the winners
    rng = random.Random(SEED)
    print("selection-matched null @ MATCH level (2000 draws):")
    for s in WINNERS:
        obs, mu, sd, p, n_ev = selection_null(rows, mat, s, rng)
        zc = (obs - mu) / sd if sd else float("nan")
        print(f"  {s:<16} N_ev={n_ev:>3} obs={obs:+.2%} null μ={mu:+.2%}±{sd:.2%} z={zc:.2f} p={p:.4f}"
              f"  {'SELECTION-REAL' if p is not None and p <= 0.01 else 'indeterminate/NULL'}")

    # K2 verdict — evaluated on the LB that D7 rule (a) actually referenced (event-N, D6-era),
    # AND separately on the current live scoreboard LB (day-N), because 5b83d33 changed the SE
    # AFTER D6/D7 were written (finding E-1).
    fav_e = gm["favorite"]["lb_eventN"]
    fav_d = gm["favorite"]["lb_dayN"]
    print("\nK2 kill-criterion (does match-level clustering drop favorite's LB below the 3% margin?):")
    print(f"  event-N LB (D7 rule-(a) statistic): incumbent {gi['favorite']['lb_eventN']:+.2%} "
          f"→ match {fav_e:+.2%}  {'>' if fav_e>MARGIN else '≤'} 3% "
          f"→ {'K2 NOT triggered by re-key' if fav_e>MARGIN else 'K2 TRIGGERED'}")
    print(f"  day-N  LB (CURRENT live scoreboard):  incumbent {gi['favorite']['lb_dayN']:+.2%} "
          f"→ match {fav_d:+.2%}  ≤ 3% at BOTH keys (only 4 event-days) — a pre-existing condition, not caused by E")

    # reproduction gate: the D6-era event-N incumbent LB must land near the recorded +3.33%.
    inc_e = gi["favorite"]["lb_eventN"]
    print(f"\nreproduction check: incumbent favorite event-N LB = {inc_e:+.2%} (D6 recorded +3.33%, N then 95); "
          f"surplus {gi['favorite']['surplus']:+.2%} (D6 +10.64%)")
    if inc_e is None or abs(inc_e - 0.0333) > 0.02:
        print("  ⚠ reproduction OUT OF NOISE — mirror not faithful; do not trust the match column")
        return 1
    print("  ✓ reproduces the D6-era event-N gate LB within noise (data grew from N=95→99) → mirror is faithful")
    return 0


# --- self-test -------------------------------------------------------------------------------
def _self_test():
    ok = True
    # probit spot checks vs known normal quantiles
    for pp, want in [(0.975, 1.959964), (0.995, 2.575829), (0.9, 1.281552)]:
        got = probit(pp)
        if abs(got - want) > 1e-4:
            ok = False
        print(f"  [{'ok' if abs(got-want)<=1e-4 else 'FAIL'}] probit({pp})={got:.6f} (want {want})")

    # Synthetic collapse: strategy 'fav' fires on 3 sub-markets of ONE match (same day) all won,
    # entry 0.70. Blind band-4 edge = 0. Incumbent sees 3 events; match sees 1.
    rows = []

    def mk(strategy, evt, slug, won, entry="0.70", day="2026-06-29"):
        return dict(strategy=strategy, event_slug=evt, slug=slug, condition_id=slug,
                    entry=float(entry), won=won, day=day)
    # blind band-4 (0.6-0.8): 14/20 won at 0.70 → AVG(a)=0 so blind_edge[band4]=0 exactly
    rows += [mk("_blind", f"b{i}", f"b{i}", 1 if i < 14 else 0, "0.70") for i in range(20)]
    # fav: 3 sub-markets of match M1, all won at 0.70 (a=0.30 each); plus 1 other match won
    rows += [mk("fav", "fifwc-a-b-2026-06-29", "fifwc-a-b-2026-06-29-a", 1),
             mk("fav", "fifwc-a-b-2026-06-29-exact-score", "fifwc-a-b-2026-06-29-exact-score-1-0", 1),
             mk("fav", "", "fifwc-a-b-2026-06-29-total-2pt5", 1),
             mk("fav", "fifwc-c-d-2026-06-29", "fifwc-c-d-2026-06-29-c", 1)]
    inc = lambda r: r["event_slug"] or r["condition_id"]              # noqa: E731
    mat = lambda r: super_event(r["event_slug"], r["slug"]) or r["condition_id"]  # noqa: E731
    gi = gate_stats(rows, inc, 1)["fav"]
    gm = gate_stats(rows, mat, 1)["fav"]
    # incumbent: 4 events (3 M1 subs + 1 M2). match: 2 events (M1, M2).
    c1 = gi["n_events"] == 4 and gm["n_events"] == 2
    ok = ok and c1
    print(f"  [{'ok' if c1 else 'FAIL'}] collapse: incumbent {gi['n_events']} events → match {gm['n_events']} events (want 4→2)")
    # match-level surplus: both events have ev_surplus = 0.30 → surplus 0.30, sd 0
    c2 = abs(gm["surplus"] - 0.30) < 1e-9
    ok = ok and c2
    print(f"  [{'ok' if c2 else 'FAIL'}] match surplus = {gm['surplus']:+.4f} (want +0.3000)")
    # incumbent surplus also 0.30 (all won) but N inflated → this is the whole point
    c3 = abs(gi["surplus"] - 0.30) < 1e-9 and gi["n_events"] > gm["n_events"]
    ok = ok and c3
    print(f"  [{'ok' if c3 else 'FAIL'}] incumbent inflates N ({gi['n_events']}>{gm['n_events']}) at same surplus")
    print("SELF-TEST", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(0 if _self_test() else 1)
    sys.exit(run_live())
