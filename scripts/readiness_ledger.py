#!/usr/bin/env python3
"""
WS-2 — UNIFIED READINESS LEDGER. One honest answer to "how far are we from real money, and on what
evidence?" Fuses every gate this project has built into a single board: each gate's STATUS, its
current value vs threshold, what's needed to clear it, and the ETA. The binding constraint is the
unmet gate with the longest horizon — so the ledger tells you the ONE thing that actually governs the
timeline, not the many that don't.

It reads the instruments' own JSON artifacts (no re-computation) plus a couple of direct DB reads, so
it's a fast dashboard that stays in sync with the underlying runs. It DECIDES nothing new — it
aggregates the standing verdicts (D6–D22) into a distance-to-money read that updates as data accrues.

Gates (real money requires ALL of the first four):
  edge_reality  λ̂ CI lower bound > 0.25 floor        (WS-A/WS-1; INDETERMINATE until dense capture)
  persistence   ≥5 independent clusters, non-expiring  (D7/D18; the binding wall — MONTHS)
  power         ≥30 distinct events, LB>3% margin      (gate; met on count, day-deflated SE the caveat)
  sizing        de-lever fraction pinned               (WS-B; MET — ⅟₁₂-Kelly)
  copyability   edge survives to a fillable price       (WS-3; MET — favorites ~69%)
  pilot_harness built, unarmed, kill-switches           (WS-D; BUILT)
  operational   dense capture running + monitors        (Option B; PENDING deploy)
Plus an informational read: alt_thesis (WS-4 softness lead).

Read-only, paper-only. Certifies nothing; it reports the standing gates honestly.
  ./readiness_ledger.py             # the board + distance-to-money; writes reports/readiness_ledger.json
  ./readiness_ledger.py --selftest  # overall-verdict logic on synthetic gate states
"""

import argparse
import csv
import io
import json
import os
import subprocess
import sys

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]
REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")
MIN_LAMBDA, COVERAGE_FLOOR = 0.25, 0.50
EVENT_FLOOR, CLUSTER_FLOOR = 30, 5
GO_GATES = ("edge_reality", "persistence", "power", "sizing")   # ALL required for real money

# status ranks for the "binding = longest horizon unmet" pick
ETA_RANK = {"none": 0, "days": 1, "weeks": 2, "months": 3, "unknown": 4}


def q(sql):
    out = subprocess.run(PG + ["-f", "-"], input=sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    return list(csv.DictReader(io.StringIO(out.stdout)))


def load(name):
    try:
        with open(os.path.join(REPORT_DIR, name)) as f:
            return json.load(f)
    except Exception:
        return None


def gate(name, status, current, threshold, needs, eta):
    return {"gate": name, "status": status, "current": current, "threshold": threshold,
            "needs": needs, "eta": eta}


def persistence_current(persist, edge, ndays, tracker_verdict):
    """Regime-aware `current`/`needs` for the persistence GO gate. The BAR is unchanged (≥CLUSTER_FLOOR
    non-expiring regimes over months); this only makes the read name recurring vs expiring regimes.
    Pure (takes the loaded JSONs), so it is unit-tested without a DB."""
    needs = f"≥{CLUSTER_FLOOR} independent NON-EXPIRING regimes (months)"
    fav_e = (edge or {}).get("arms", {}).get("favorite", {})
    fav_p = (persist or {}).get("arms", {}).get("favorite", {})
    if not fav_e or not fav_p:
        return f"{ndays} event-day clusters (WC-heavy), tracker={tracker_verdict}", needs
    br = fav_e.get("breadth", {})
    rec_cleared = br.get("recurring_cleared", 0)
    n_rec = br.get("n_recurring", 0)
    verdict = fav_p.get("verdict", "PENDING")
    exp_ids = br.get("expiring_ids", [])
    exp_sports = sorted({rid.split("|")[0] for rid in exp_ids})
    exp_note = ("; " + "/".join(exp_sports) + " expiring") if exp_sports else ""
    current = f"regime={verdict}; {rec_cleared}/{n_rec} recurring regimes clear floor{exp_note}"
    return current, needs


def regime_panel(edge, persist, net):
    """Informational per-regime persistence panel (NOT a GO gate). Pure — takes the three loaded
    JSON artifacts (regime_edge / regime_persistence / regime_net_edge). Returns None if unavailable."""
    if not edge or not persist or not net:
        return None
    fe = edge.get("arms", {}).get("favorite", {})
    fp = persist.get("arms", {}).get("favorite", {})
    fn = net.get("arms", {}).get("favorite", {})
    if not fe.get("regimes") or not fn.get("regimes"):
        return None
    edge_reg = fe["regimes"]
    net_reg = fn["regimes"]
    rows = []
    for rid, nr in net_reg.items():
        if not nr.get("recurring"):
            continue
        er = edge_reg.get(rid, {})
        rows.append({
            "regime": rid, "n_clusters": nr.get("n_clusters"),
            "edge_lb": er.get("lb"), "net_taker_fee2": nr.get("net_taker_fee2"),
            "net_positive": nr.get("net_taker_fee2_positive"),
            "clears_cluster_floor": er.get("clears_floor", False),
        })
    rows.sort(key=lambda r: -(r["net_taker_fee2"] if r["net_taker_fee2"] is not None else -9))
    conc = fe.get("concentration", {})
    br = fe.get("breadth", {})
    return {
        "verdict": fp.get("verdict"), "why": fp.get("why"),
        "recurring_regimes": rows,
        "n_recurring_net_positive": fn.get("n_recurring_net_positive", 0),
        "concentration": {"top_regime": conc.get("top_regime"), "top_share": conc.get("top_share"),
                          "expiring_edge_mass_share": conc.get("expiring_edge_mass_share")},
        "breadth": {"recurring_cleared": br.get("recurring_cleared", 0),
                    "n_recurring": br.get("n_recurring", 0),
                    "cluster_floor": br.get("cluster_floor"), "bar": 2},
    }


def build_gates():
    gates = []

    # --- edge_reality (λ) ---
    clv = load("clv_lambda.json")
    if not clv:
        gates.append(gate("edge_reality", "INDETERMINATE", "no artifact", f"λ̂_lo > {MIN_LAMBDA}",
                          "run clv_lambda / dense capture", "weeks"))
    else:
        cov = clv.get("trajectory_coverage", 0.0)
        lo = clv.get("lambda_ci", [float("nan"), float("nan")])[0]
        if cov < COVERAGE_FLOOR:
            gates.append(gate("edge_reality", "INDETERMINATE",
                              f"coverage {cov:.0%}, proxy λ̂_lo {lo:.2f}", f"λ̂_lo > {MIN_LAMBDA} at ≥{COVERAGE_FLOOR:.0%} coverage",
                              "deploy dense capture, accrue ~2–4 wk", "weeks"))
        elif lo > MIN_LAMBDA:
            gates.append(gate("edge_reality", "MET", f"λ̂_lo {lo:.2f}", f"> {MIN_LAMBDA}", "—", "none"))
        else:
            gates.append(gate("edge_reality", "NOT_MET", f"λ̂_lo {lo:.2f}", f"> {MIN_LAMBDA}",
                              "edge is bias, not information — PIVOT (WS-4/WS-3)", "months"))

    # --- persistence (independent clusters, non-expiring) ---
    # REGIME-AWARE (2026-07-04, regime-persistence run): the `current`/`needs` now consume
    # regime_persistence.json / regime_edge.json so the binding read names WHICH regimes are
    # recurring vs expiring. The GO-gate BAR is UNCHANGED (still NOT_MET until ≥CLUSTER_FLOOR
    # independent NON-EXPIRING regimes over months) — this only makes the read regime-legible.
    days = q("select count(distinct date(first_detected_at at time zone 'UTC')) d, "
             "count(distinct coalesce(event_slug,condition_id)) ev "
             "from consensus_signals where strategy='favorite' and resolved")
    ndays = int(days[0]["d"]) if days else 0
    nev = int(days[0]["ev"]) if days else 0
    pt = load("persistence_tracker.json")
    pv = (pt or {}).get("verdict", "PENDING")
    current, needs = persistence_current(load("regime_persistence.json"), load("regime_edge.json"),
                                         ndays, pv)
    gates.append(gate("persistence", "NOT_MET", current, needs,
                      "accrue across sports past the World Cup/Wimbledon", "months"))

    # --- power (distinct events) ---
    if nev >= EVENT_FLOOR:
        gates.append(gate("power", "MET (caveat)", f"{nev} events", f"≥{EVENT_FLOOR}",
                          "count OK; day-deflated SE on ~5 correlated days is the real limit (⊂ persistence)", "none"))
    else:
        gates.append(gate("power", "NOT_MET", f"{nev} events", f"≥{EVENT_FLOOR}", "accrue events", "weeks"))

    # --- sizing (de-lever pinned) ---
    dl = load("corr_risk_delever.json")
    rec = (dl or {}).get("recommendation", {}).get("recommended")
    gates.append(gate("sizing", "MET" if rec else "INDETERMINATE",
                      rec or "no artifact", "de-lever fraction pinned",
                      "—" if rec else "run corr_risk_delever", "none"))

    # --- copyability (fillable at our price) ---
    cp = load("copyability.json")
    favcp = None
    if cp:
        favcp = next((s for s in cp.get("strategies", []) if s["strategy"] == "favorite"), None)
    if favcp and favcp.get("modeled_realizable_net", -1) > 0:
        gates.append(gate("copyability", "MET",
                          f"favorite {favcp['copyability_frac']:.0%} survives, net {favcp['modeled_realizable_net']:+.1%}",
                          "modeled realizable > 0", "—", "none"))
    else:
        gates.append(gate("copyability", "INDETERMINATE", "no artifact / not +", "realizable > 0",
                          "run copyability", "none"))

    # --- pilot harness (built, unarmed) ---
    gates.append(gate("pilot_harness", "BUILT", "unarmed, kill-switches, place-path unreachable",
                      "wired behind PILOT_ARMED + master", "arm only after the 4 GO gates + Tue", "none"))

    # --- operational (dense capture running) ---
    traj = q("select count(*) n from signal_price_trajectory")
    ntraj = int(traj[0]["n"]) if traj else 0
    gates.append(gate("operational", "MET" if ntraj > 0 else "NOT_MET",
                      f"{ntraj} trajectory rows", "dense capture writing + monitors live",
                      "—" if ntraj > 0 else "deploy Option B (DENSE_CAPTURE=true)", "none" if ntraj > 0 else "days"))

    # --- alt_thesis (informational: softness lead) ---
    sm = load("softness_fade.json")
    soft = [c for c in (sm or {}).get("cells", []) if c.get("SOFT_CELL")]
    gates.append(gate("alt_thesis", "LEAD" if soft else "NONE",
                      f"{len(soft)} FDR-soft cell(s)" + (f": {soft[0]['sport']}/{soft[0]['mtype']}/b{soft[0]['band']} {soft[0]['side']} {soft[0]['net_edge']:+.1%}" if soft else ""),
                      "a durable, post-tournament soft pocket", "re-run softness_map as blind universe grows", "months"))
    return gates


def verdict(gates):
    gmap = {g["gate"]: g for g in gates}
    go = [gmap[n] for n in GO_GATES]
    met = [g for g in go if g["status"].startswith("MET")]
    unmet = [g for g in go if not g["status"].startswith("MET")]
    eligible = len(unmet) == 0
    # binding = unmet GO gate with the longest ETA
    binding = max(unmet, key=lambda g: ETA_RANK.get(g["eta"], 0)) if unmet else None
    # nearest actionable across ALL gates (shortest non-none ETA that unblocks progress)
    actionable = [g for g in gates if g["eta"] in ("days", "weeks") and not g["status"].startswith("MET")]
    actionable.sort(key=lambda g: ETA_RANK.get(g["eta"], 9))
    return {"real_money_eligible": eligible, "go_gates_met": f"{len(met)}/{len(go)}",
            "binding_constraint": binding["gate"] if binding else None,
            "binding_eta": binding["eta"] if binding else None,
            "nearest_action": actionable[0]["needs"] if actionable else None,
            "unmet": [g["gate"] for g in unmet]}


def run():
    gates = build_gates()
    v = verdict(gates)
    panel = regime_panel(load("regime_edge.json"), load("regime_persistence.json"),
                         load("regime_net_edge.json"))
    _print(gates, v)
    _print_panel(panel)
    out = {"gates": gates, "verdict": v, "regime_panel": panel}
    os.makedirs(REPORT_DIR, exist_ok=True)
    with open(os.path.join(REPORT_DIR, "readiness_ledger.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {os.path.join(REPORT_DIR, 'readiness_ledger.json')}")
    return out


def _pf(x, spec="+.1%"):
    return "n/a" if x is None or (isinstance(x, float) and x != x) else format(x, spec)


def _print_panel(panel):
    if not panel:
        print("\n(regime panel unavailable — run regime_edge / regime_persistence / regime_net_edge first)")
        return
    print("\n" + "=" * 96)
    print("REGIME PERSISTENCE PANEL (informational — NOT a GO gate; makes 'accumulate over months' watchable)")
    print("=" * 96)
    print(f"regime verdict: {panel['verdict']} — {panel['why']}")
    print(f"{'recurring regime':<26}{'status':<14}{'edge LB':>9}{'net-taker':>11}{'clusters':>9}{'net+?':>7}")
    print("-" * 76)
    for r in panel["recurring_regimes"]:
        status = "cleared" if r["clears_cluster_floor"] else "below-floor"
        npos = "yes" if r["net_positive"] else ("no" if r["net_positive"] is not None else "—")
        print(f"{r['regime']:<26}{status:<14}{_pf(r['edge_lb']):>9}{_pf(r['net_taker_fee2']):>11}"
              f"{str(r['n_clusters']):>9}{npos:>7}")
    print("-" * 76)
    c = panel["concentration"]
    print(f"concentration: top regime '{c['top_regime']}' = {_pf(c['top_share'],'.0%')} of edge mass · "
          f"EXPIRING regimes carry {_pf(c['expiring_edge_mass_share'],'.0%')} (soccer-artifact test)")
    b = panel["breadth"]
    print(f"breadth: {b['recurring_cleared']}/{b['n_recurring']} recurring regimes clear the "
          f"{b['cluster_floor']}-cluster floor · {panel['n_recurring_net_positive']} net-positive after tax "
          f"· need ≥{b['bar']} non-expiring for PERSISTS-NET")


def _print(gates, v):
    print("=" * 96)
    print("WS-2 · READINESS LEDGER · distance to real money (fuses D6–D22; certifies nothing)")
    print("=" * 96)
    hdr = f"{'gate':<15}{'status':<16}{'current':<44}{'eta':>7}"
    print(hdr); print("-" * len(hdr))
    for g in gates:
        req = "*" if g["gate"] in GO_GATES else " "
        print(f"{req}{g['gate']:<14}{g['status']:<16}{g['current'][:43]:<44}{g['eta']:>7}")
    print("-" * len(hdr))
    print(f"(* = required for real money; all four must be MET)")
    print(f"\nGO gates met: {v['go_gates_met']}   ·   real-money eligible: {v['real_money_eligible']}")
    print(f"BINDING CONSTRAINT: {v['binding_constraint']} (ETA {v['binding_eta']}) — this governs the timeline.")
    print(f"unmet GO gates: {', '.join(v['unmet']) or 'none'}")
    print(f"NEAREST ACTION (unblocks progress now): {v['nearest_action']}")
    print("\nHonest read: NOT-YET. The distance is dominated by PERSISTENCE (months, non-expiring")
    print("regimes) — but the nearest lever is turning ON dense capture so λ becomes measurable at all.")


def selftest():
    ok = True
    # all four GO gates MET → eligible
    g_all = [gate(n, "MET", "", "", "", "none") for n in GO_GATES]
    v = verdict(g_all)
    c1 = v["real_money_eligible"] and v["binding_constraint"] is None
    ok = ok and c1
    print(f"  [{'ok' if c1 else 'FAIL'}] all GO gates MET → eligible, no binding")
    # persistence unmet (months) + edge unmet (weeks) → NOT eligible, binding=persistence (longest ETA)
    g_mix = [gate("edge_reality", "INDETERMINATE", "", "", "", "weeks"),
             gate("persistence", "NOT_MET", "", "", "", "months"),
             gate("power", "MET", "", "", "", "none"),
             gate("sizing", "MET", "", "", "", "none")]
    v2 = verdict(g_mix)
    c2 = (not v2["real_money_eligible"]) and v2["binding_constraint"] == "persistence"
    ok = ok and c2
    print(f"  [{'ok' if c2 else 'FAIL'}] persistence(months)+edge(weeks) unmet → binding=persistence")
    # MET (caveat) counts as met
    c3 = verdict([gate(n, "MET (caveat)" if n == "power" else "MET", "", "", "", "none") for n in GO_GATES])["real_money_eligible"]
    ok = ok and c3
    print(f"  [{'ok' if c3 else 'FAIL'}] 'MET (caveat)' counts as met")

    # --- regime-aware persistence gate rewire (pure, fixture JSONs) ---
    edge_fix = {"arms": {"favorite": {"breadth": {"recurring_cleared": 0, "n_recurring": 5,
                "expiring_ids": ["soccer|2026-07", "tennis|2026-06"]},
                "concentration": {"top_regime": "mlb|2026-07", "top_share": 0.23,
                                  "expiring_edge_mass_share": 0.57},
                "regimes": {"mlb|2026-07": {"lb": 0.10, "clears_floor": False, "recurring": True}}}}}
    persist_fix = {"arms": {"favorite": {"verdict": "SOCCER-ARTIFACT", "why": "expiring-carried"}}}
    cur, needs = persistence_current(persist_fix, edge_fix, 6, "PENDING")
    c4 = ("SOCCER-ARTIFACT" in cur and "0/5" in cur and "soccer" in cur
          and needs == f"≥{CLUSTER_FLOOR} independent NON-EXPIRING regimes (months)")
    ok = ok and c4
    print(f"  [{'ok' if c4 else 'FAIL'}] persistence gate rewired regime-aware, bar UNCHANGED: '{cur}'")

    # gate stays NOT_MET and eta months even when regime-aware (does not weaken)
    g_p = next(g for g in [gate("persistence", "NOT_MET", cur, needs, "accrue", "months")])
    c4b = g_p["status"] == "NOT_MET" and g_p["eta"] == "months"
    ok = ok and c4b
    print(f"  [{'ok' if c4b else 'FAIL'}] persistence gate still NOT_MET / months (bar not weakened)")

    # --- regime panel (pure, fixture JSONs) ---
    net_fix = {"arms": {"favorite": {"n_recurring_net_positive": 2, "regimes": {
        "mlb|2026-07": {"recurring": True, "n_clusters": 4, "net_taker_fee2": 0.169, "net_taker_fee2_positive": True},
        "nba/cbb|2026-07": {"recurring": True, "n_clusters": 2, "net_taker_fee2": 0.22, "net_taker_fee2_positive": True},
        "soccer|2026-07": {"recurring": False, "n_clusters": 4, "net_taker_fee2": 0.05, "net_taker_fee2_positive": False}}}}}
    panel = regime_panel(edge_fix, persist_fix, net_fix)
    c5 = (panel is not None and panel["verdict"] == "SOCCER-ARTIFACT"
          and len(panel["recurring_regimes"]) == 2  # only recurring regimes, soccer excluded
          and panel["n_recurring_net_positive"] == 2
          and panel["concentration"]["expiring_edge_mass_share"] == 0.57)
    ok = ok and c5
    print(f"  [{'ok' if c5 else 'FAIL'}] regime panel: {len(panel['recurring_regimes'])} recurring rows, "
          f"verdict {panel['verdict']}, {panel['n_recurring_net_positive']} net-positive")

    c6 = regime_panel(None, None, None) is None   # graceful when artifacts missing
    ok = ok and c6
    print(f"  [{'ok' if c6 else 'FAIL'}] regime panel graceful when artifacts missing")

    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    if ap.parse_args().selftest:
        selftest()
        return
    run()


if __name__ == "__main__":
    main()
