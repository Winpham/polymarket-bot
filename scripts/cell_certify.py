#!/usr/bin/env python3
"""
CELL CERTIFY — the belief-blind, out-of-sample, multiplicity-corrected certification loop for the
per-(sport × market-type) conditioning of the `favorite` book (RUN-PER-SPORT-CONDITIONING §1, §2).

A cell is CERTIFIED (promotion-ELIGIBLE, still a deliberate call — never auto-promote) only if ALL:
  (1) within-cell selection-null p_emp ≤ 0.01          (belief-blind; consensus beats a random
      SAME-CELL blind favorite — NOT a favorite-longshot composition artifact), AND
      SURVIVES Bonferroni across the C cells tested (p_emp·C ≤ 0.05), AND
  (2) event-clustered bootstrap LB(2.5%) on POOLED skill > +3% margin, AND
  (3) POSITIVE out-of-sample: skill_raw > 0 in the LATE (verify) time-half, AND
  (4) NON-TOURNAMENT: sport ∉ {tennis(Wimbledon), soccer(World Cup)} — an expiring-tournament cell
      cannot clear the non-tournament holdout and is REJECTED however good it looks in-window, AND
  (5) realizable ROI (entry_ask, corrected fee) > 0 on its ask-covered subset, AND
  (6) power: n_events ≥ floor (20 w/ mechanism, 30 w/o).

PARTIAL POOLING decides (§2): certification reads `skill_pooled`, never the raw per-cell mean.
Both "here is a certified cell + forward gate" and "nothing certifies — here is why" are success;
a goal-sought green is failure. Reuses cell_skill_map (one accounting source of truth).

Read-only. Writes reports/CELL-CERT-LOG.md + reports/REJECTED-CELLS.md.

  ./cell_certify.py               # certify all candidate cells + logs
  ./cell_certify.py --self-test   # predicate + bootstrap fixtures
"""

import os
import random
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cell_skill_map as csm       # noqa: E402
import selection_null as sn        # noqa: E402

RDIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")
SEED = 20260709
MARGIN = 0.03                       # belief-blind LB must clear +3 points
P_BAR = 0.01                        # pre-registered per-cell selection-null bar
TOURNAMENT_SPORTS = {"tennis", "soccer"}   # current data: Wimbledon + World Cup (expiring)
READ_FLOOR = 10                     # a cell below this n_events is not even scored (no readout)


def boot_skill_lb(cell_rows, sband_edge, n_boot=2000, seed=SEED, lo=0.025):
    """Event-clustered bootstrap of POOLED skill; returns (lb, hi) as fractions.
    Resamples event-clusters (the inference unit) with replacement, re-pools each draw."""
    ev = defaultdict(list)
    for r in cell_rows:
        base = sband_edge.get((csm.sport_of(r), r["band"]), 0.0)
        ev[csm.evk(r)].append((r["won"] - r["entry"]) - base)
    clusters = [sum(v) / len(v) for v in ev.values()]
    n = len(clusters)
    if n < 2:
        return float("nan"), float("nan")
    rng = random.Random(seed)
    gfs = csm.sport_band_surplus  # unused placeholder to keep flake quiet
    means = []
    for _ in range(n_boot):
        s = sum(clusters[rng.randrange(n)] for _ in range(n)) / n
        w = n / (n + csm.K_POOL)
        means.append(GLOBAL_FAV_SKILL + (s - GLOBAL_FAV_SKILL) * w)   # pooled, per draw
    means.sort()
    return means[int(lo * n_boot)], means[int((1 - lo) * n_boot)]


GLOBAL_FAV_SKILL = 0.0   # set in run()


def time_split_skill(cell_rows, sband_edge):
    """skill_raw in the early and late time-halves (by UTC day). Returns (early, late, split_day)."""
    days = sorted({r["day"] for r in cell_rows})
    if len(days) < 2:
        return float("nan"), float("nan"), None
    mid = days[len(days) // 2]
    early = [r for r in cell_rows if r["day"] < mid]
    late = [r for r in cell_rows if r["day"] >= mid]
    es, _ = csm.sport_band_surplus(early, sband_edge)
    ls, _ = csm.sport_band_surplus(late, sband_edge)
    return es, ls, mid


def certify_cell(label, rows, blind_same_cell, sband_edge, gband_edge, rng, n_cells, with_mech):
    """Return (verdict_dict). verdict['certified'] ∈ {True, False}; reasons list every failed gate."""
    n_ev_ok = None
    skill_raw, n_ev = csm.sport_band_surplus(rows, sband_edge)
    w = n_ev / (n_ev + csm.K_POOL) if n_ev else 0.0
    skill_pooled = GLOBAL_FAV_SKILL + (skill_raw - GLOBAL_FAV_SKILL) * w if skill_raw == skill_raw else GLOBAL_FAV_SKILL
    lb, hi = boot_skill_lb(rows, sband_edge)
    p_emp, n_draws = (None, 0)
    if n_ev >= READ_FLOOR and blind_same_cell:
        p_emp, n_draws = csm.cell_null_p(rows, blind_same_cell, gband_edge, rng)
    es, ls, split_day = time_split_skill(rows, sband_edge)
    ra, cov, n_ask = csm.roi_ask(rows)
    sport = label.split("=")[1].split("|")[0]
    floor = csm.FLOOR_MECH if with_mech else csm.FLOOR_NOMECH
    is_tourn = sport in TOURNAMENT_SPORTS

    reasons = []
    # (1) belief-blind null
    p_bonf = (p_emp * n_cells) if p_emp is not None else None
    if p_emp is None:
        reasons.append("null unmeasurable (blind pool cannot match cell profile → power)")
    else:
        if p_emp > P_BAR:
            reasons.append(f"selection-null p_emp={p_emp:.3f} > {P_BAR} (no belief-blind skill)")
        if p_bonf is not None and p_bonf > 0.05:
            reasons.append(f"fails Bonferroni across {n_cells} cells (p·C={p_bonf:.2f} > 0.05)")
    # (2) bootstrap LB > margin
    if not (lb == lb) or lb <= MARGIN:
        reasons.append(f"pooled-skill LB={100*lb:+.1f}% ≤ +{100*MARGIN:.0f}% margin"
                       if lb == lb else "pooled-skill LB n/a")
    # (3) OOS late-half positive
    if not (ls == ls) or ls <= 0:
        reasons.append(f"OOS late-half skill={100*ls:+.1f}% ≤ 0" if ls == ls else "OOS: single-day (no split)")
    # (4) non-tournament
    if is_tourn:
        reasons.append(f"TOURNAMENT-only ({sport}=expiring); cannot clear non-tournament holdout")
    # (5) realizable
    if ra is None:
        reasons.append("realizable ROI unmeasured (no ask coverage)")
    elif ra <= 0:
        reasons.append(f"realizable ROI(ask)={ra:+.1f}% ≤ 0 (spread eats the mid edge)")
    # (6) power
    if n_ev < floor:
        reasons.append(f"UNDERPOWERED n_ev={n_ev} < floor {floor}")

    certified = len(reasons) == 0
    return dict(label=label, n_picks=len(rows), n_events=n_ev, skill_raw=skill_raw,
                skill_pooled=skill_pooled, lb=lb, hi=hi, p_emp=p_emp, p_bonf=p_bonf,
                n_draws=n_draws, oos_early=es, oos_late=ls, split_day=split_day,
                roi_ask=ra, ask_cov=cov, n_ask=n_ask, is_tourn=is_tourn, floor=floor,
                certified=certified, reasons=reasons)


def run():
    global GLOBAL_FAV_SKILL
    fav = csm.load_fav_full()
    blind = csm.load_blind_rich()
    gband_edge, sband_edge, softness = csm.blind_baselines(blind)
    GLOBAL_FAV_SKILL, _ = csm.sport_band_surplus(fav, sband_edge)
    rng = random.Random(SEED)

    blind_by_sport = defaultdict(list)
    blind_by_sport_mt = defaultdict(list)
    for r in blind:
        blind_by_sport[r["sport"]].append(r)
        blind_by_sport_mt[(r["sport"], r["mt"])].append(r)

    # candidate cells: sport-only + sport×mt, above the readout floor
    cands = []
    by_sport = defaultdict(list)
    for r in fav:
        by_sport[csm.sport_of(r)].append(r)
    for sp, rows in by_sport.items():
        _, n_ev = csm.sport_band_surplus(rows, sband_edge)
        if n_ev >= READ_FLOOR:
            cands.append((f"sport={sp}", rows, blind_by_sport.get(sp, []), False))
    by_sport_mt = defaultdict(list)
    for r in fav:
        by_sport_mt[(csm.sport_of(r), r["mt"] or "unc")].append(r)
    for (sp, mt), rows in by_sport_mt.items():
        _, n_ev = csm.sport_band_surplus(rows, sband_edge)
        if n_ev >= READ_FLOOR:
            cands.append((f"sport={sp}|mt={mt}", rows,
                          blind_by_sport_mt.get((sp, mt if mt != "unc" else None), []), True))
    n_cells = len(cands)

    results = [certify_cell(lbl, rows, bl, sband_edge, gband_edge, rng, n_cells, wm)
               for (lbl, rows, bl, wm) in cands]
    results.sort(key=lambda v: (-int(v["certified"]), v["p_emp"] if v["p_emp"] is not None else 1.0))

    certified = [v for v in results if v["certified"]]
    rejected = [v for v in results if not v["certified"]]

    # ---- CELL-CERT-LOG.md ----
    lines = ["# CELL CERTIFICATION LOG — per-(sport×market-type) `favorite` conditioning\n",
             f"_{n_cells} candidate cells tested (n_events ≥ {READ_FLOOR}); Bonferroni family = {n_cells}._  ",
             f"_Global favorite skill (pooling target) = {100*GLOBAL_FAV_SKILL:+.2f}%. "
             f"K_POOL={csm.K_POOL:g}. Belief-blind bar p≤{P_BAR}, LB>+{100*MARGIN:.0f}%, "
             f"OOS late-half>0, non-tournament, realizable>0, power floor._\n",
             "## Certification criteria (ALL must hold)\n",
             "1. within-cell selection-null `p_emp ≤ 0.01` **and** Bonferroni `p·C ≤ 0.05`  ",
             "2. event-clustered bootstrap **LB(pooled skill) > +3%**  ",
             "3. OOS **late-half skill > 0**  ",
             "4. **non-tournament** sport (tennis=Wimbledon / soccer=World Cup auto-reject)  ",
             "5. **realizable ROI(entry_ask) > 0**  ",
             "6. power **n_events ≥ floor**\n",
             "| cell | nEv | skillRaw | skillPooled | LB(pool) | null p | p·C | OOS late | roiAsk(cov) | tourn | verdict |",
             "|------|----:|---------:|------------:|---------:|-------:|----:|---------:|------------:|:-----:|---------|"]
    for v in results:
        p = f"{v['p_emp']:.3f}" if v["p_emp"] is not None else "—"
        pc = f"{v['p_bonf']:.2f}" if v["p_bonf"] is not None else "—"
        lb = f"{100*v['lb']:+.1f}%" if v["lb"] == v["lb"] else "n/a"
        ls = f"{100*v['oos_late']:+.1f}%" if v["oos_late"] == v["oos_late"] else "n/a"
        ra = f"{v['roi_ask']:+.1f}%({v['ask_cov']:.0%})" if v["roi_ask"] is not None else "—"
        vd = "✅ CERTIFIED" if v["certified"] else "❌ reject"
        lines.append(f"| `{v['label']}` | {v['n_events']} | {100*v['skill_raw']:+.1f}% | "
                     f"{100*v['skill_pooled']:+.1f}% | {lb} | {p} | {pc} | {ls} | {ra} | "
                     f"{'Y' if v['is_tourn'] else 'n'} | {vd} |")
    lines.append(f"\n**Result: {len(certified)} of {n_cells} cells certified.**\n")
    if certified:
        lines.append("Certified cells (promotion-ELIGIBLE — still a deliberate call, forward gate is the arbiter):")
        for v in certified:
            lines.append(f"- `{v['label']}`: pooled skill {100*v['skill_pooled']:+.1f}%, "
                         f"LB {100*v['lb']:+.1f}%, null p={v['p_emp']:.3f}, realizable {v['roi_ask']:+.1f}%")
    else:
        lines.append("**No cell certified.** The per-sport structure in the map is soft-market softness "
                     "and/or power-limited, not a belief-blind selection edge that clears the bar at "
                     "realizable entry. This is a valid, honest outcome (the belief-blind gate is the "
                     "judge, not the goal). Closest candidates and exactly why they fail are in "
                     "REJECTED-CELLS.md.")
    with open(os.path.join(RDIR, "CELL-CERT-LOG.md"), "w") as f:
        f.write("\n".join(lines) + "\n")

    # ---- REJECTED-CELLS.md ----
    rlines = ["# REJECTED CELLS — why each candidate failed certification\n",
              f"_{len(rejected)} of {n_cells} candidate cells rejected. Ranked by selection-null p "
              "(closest-to-real first)._\n"]
    for v in sorted(rejected, key=lambda x: x["p_emp"] if x["p_emp"] is not None else 1.0):
        p = f"{v['p_emp']:.3f}" if v["p_emp"] is not None else "n/a"
        rlines.append(f"### `{v['label']}` — nEv={v['n_events']}, pooled skill {100*v['skill_pooled']:+.1f}%, "
                      f"null p={p}")
        rlines.append(f"- raw skill {100*v['skill_raw']:+.1f}% → pooled {100*v['skill_pooled']:+.1f}% "
                      f"(LB {100*v['lb']:+.1f}%); OOS early {100*v['oos_early']:+.1f}% / "
                      f"late {100*v['oos_late']:+.1f}%; realizable "
                      f"{('%+.1f%%' % v['roi_ask']) if v['roi_ask'] is not None else 'n/a'} "
                      f"(ask cov {v['ask_cov']:.0%}, n={v['n_ask']})")
        for reason in v["reasons"]:
            rlines.append(f"  - ❌ {reason}")
        rlines.append("")
    with open(os.path.join(RDIR, "REJECTED-CELLS.md"), "w") as f:
        f.write("\n".join(rlines) + "\n")

    # ---- console ----
    print(f"CELL CERTIFY · {n_cells} cells · Bonferroni family {n_cells} · global fav skill "
          f"{100*GLOBAL_FAV_SKILL:+.2f}% · seed {SEED}\n" + "=" * 100)
    print(f"{'cell':<26}{'nEv':>4}{'skillP':>8}{'LB':>8}{'null_p':>8}{'p·C':>7}"
          f"{'OOSlate':>9}{'roiAsk':>9}  verdict")
    for v in results:
        p = f"{v['p_emp']:.3f}" if v["p_emp"] is not None else "—"
        pc = f"{v['p_bonf']:.2f}" if v["p_bonf"] is not None else "—"
        lb = f"{100*v['lb']:+.1f}%" if v["lb"] == v["lb"] else "n/a"
        ls = f"{100*v['oos_late']:+.1f}%" if v["oos_late"] == v["oos_late"] else "n/a"
        ra = f"{v['roi_ask']:+.1f}%" if v["roi_ask"] is not None else "—"
        vd = "✅CERT" if v["certified"] else "reject"
        print(f"{v['label']:<26}{v['n_events']:>4}{100*v['skill_pooled']:>+7.1f}%{lb:>8}{p:>8}{pc:>7}"
              f"{ls:>9}{ra:>9}  {vd}  {'' if v['certified'] else '· '+v['reasons'][0]}")
    print(f"\n{len(certified)}/{n_cells} certified. Wrote CELL-CERT-LOG.md + REJECTED-CELLS.md")
    return 0


def residual_scan():
    """§1.6 re-scan: does conditioning INTO the arm's non-tournament cells (or OUT of the discarded
    tournament cells) unmask a realizable negative? Compares the flat champion book, the arm's
    fired subset, and the discarded subset on belief-blind skill + within-subset null + realizable
    ROI(ask). Writes reports/BYSPORT-RESIDUAL-SCAN.md (distinct from the garbage-policy run's
    RESIDUAL-SCAN.md, which is a different artifact and must not be clobbered)."""
    global GLOBAL_FAV_SKILL
    fav = csm.load_fav_full()
    blind = csm.load_blind_rich()
    gband_edge, sband_edge, _ = csm.blind_baselines(blind)
    GLOBAL_FAV_SKILL, _ = csm.sport_band_surplus(fav, sband_edge)
    rng = random.Random(SEED)
    NONT = {"mlb", "nba/cbb", "nfl/cfb", "nhl", "esports"}
    TOUR = TOURNAMENT_SPORTS
    pops = [
        ("FULL favorite book (flat, sport-agnostic)", fav, None),
        ("ARM non-tournament subset (mlb,nba/cbb,esports,…)", [r for r in fav if csm.sport_of(r) in NONT], NONT),
        ("DISCARDED tournament subset (soccer,tennis)", [r for r in fav if csm.sport_of(r) in TOUR], TOUR),
    ]
    lines = ["# RESIDUAL SCAN — is per-sport conditioning progressive or regressive at realizable entry?\n",
             "Compares the flat champion `favorite` book vs the arm's fired (non-tournament) subset vs the",
             "discarded (soft-tournament) subset on belief-blind skill, within-subset selection-null, and",
             "**realizable ROI (entry_ask, corrected fee)**. Reuses the committed instruments.\n",
             "| population | nEv | raw skill | LB(pool) | null p | realizable ROI(ask) (cov) |",
             "|---|---:|---:|---:|---:|---:|"]
    console = []
    for name, rows, restrict in pops:
        sk, nev = csm.sport_band_surplus(rows, sband_edge)
        lb, _ = boot_skill_lb(rows, sband_edge)
        if restrict is None:
            bl = blind
        else:
            bl = [b for b in blind if b["sport"] in restrict]
        p, _nd = (None, 0)
        if nev >= 10 and bl:
            p, _nd = csm.cell_null_p(rows, bl, gband_edge, rng)
        ra, cov, nask = csm.roi_ask(rows)
        ps = f"{p:.3f}" if p is not None else "—"
        ras = f"{ra:+.1f}% ({cov:.0%}, n={nask})" if ra is not None else "—"
        lines.append(f"| {name} | {nev} | {100*sk:+.1f}% | {100*lb:+.1f}% | {ps} | {ras} |")
        console.append(f"{name:<48} nEv={nev:>3} skill={100*sk:+5.1f}% LB={100*lb:+5.1f}% "
                       f"null_p={ps} realizable={ras}")
    lines += ["\n**Reading:** if the FULL flat book is belief-blind-significant and realizable-positive while",
              "the non-tournament subset is not, per-sport conditioning SUBTRACTS realizable value — the",
              "efficient-market skill is un-harvestable through thin-book spreads, and the realizable money",
              "lives in the soft-but-liquid tournament cells the arm discards. See BYSPORT-VERDICT.md.\n"]
    with open(os.path.join(RDIR, "BYSPORT-RESIDUAL-SCAN.md"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print("RESIDUAL SCAN " + "=" * 90)
    for c in console:
        print(c)
    print(f"\nglobal fav skill {100*GLOBAL_FAV_SKILL:+.2f}% · wrote {os.path.join(RDIR, 'BYSPORT-RESIDUAL-SCAN.md')}")
    return 0


def _self_test():
    global GLOBAL_FAV_SKILL
    ok = True
    GLOBAL_FAV_SKILL = 0.05
    # bootstrap: a cell of identical +0.30 clusters → LB near pooled(0.30) with n large
    rows = [{"won": 1, "entry": 0.70, "band": 4, "slug": "mlb-x-%d" % i, "event_slug": "mlb-x-%d" % i,
             "day": "2026-07-%02d" % (1 + i % 8)} for i in range(60)]
    lb, hi = boot_skill_lb(rows, {})   # all won at 0.70 → surplus +0.30 each, base 0
    w = 60 / (60 + csm.K_POOL)
    pooled_pt = 0.05 + (0.30 - 0.05) * w
    c1 = abs(lb - pooled_pt) < 0.02 and abs(hi - pooled_pt) < 0.02   # zero variance → tight
    ok &= c1
    print(f"  [{'ok' if c1 else 'FAIL'}] bootstrap LB on zero-variance cell ≈ pooled point "
          f"(LB {100*lb:+.1f}%, pt {100*pooled_pt:+.1f}%)")
    # time split
    rows2 = ([{"won": 1, "entry": 0.7, "band": 4, "slug": "mlb-a", "event_slug": "mlb-a", "day": "2026-07-01"}]
             + [{"won": 0, "entry": 0.7, "band": 4, "slug": "mlb-b", "event_slug": "mlb-b", "day": "2026-07-08"}])
    es, ls, mid = time_split_skill(rows2, {})
    c2 = es > 0 and ls < 0 and mid == "2026-07-08"
    ok &= c2
    print(f"  [{'ok' if c2 else 'FAIL'}] time split: early {100*es:+.0f}% late {100*ls:+.0f}% @ {mid}")
    # tournament auto-reject: a perfect tennis cell must still fail on the non-tournament gate
    v = certify_cell("sport=tennis", rows, [], {}, {}, random.Random(1), 5, False)
    c3 = (not v["certified"]) and any("TOURNAMENT" in r for r in v["reasons"])
    ok &= c3
    print(f"  [{'ok' if c3 else 'FAIL'}] tennis auto-rejected on non-tournament holdout")
    print("SELF-TEST", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(0 if _self_test() else 1)
    if "--residual" in sys.argv:
        sys.exit(residual_scan())
    sys.exit(run())
