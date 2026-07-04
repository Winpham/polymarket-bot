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

# --- capture-hardening Item 3 constants (frozen) ---
# The proven_router pre-registration stamp: signals are judged ONLY from here
# forward (PREREG_2026-07-04T094304Z_proven_router.md). Do not tune.
ROUTER_PREREG_TS = "2026-07-04T09:43:04Z"
UNIFIED_BOOK_FLOOR = 20          # forward day-blocks the unified paper book must accrue
BEST_TRADER_MARGIN = 0.03        # "as profitable as the best": beat B_LB by ≥ 3pp

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


# --- capture-hardening Item 3: three pure row builders (fixture-testable) ---

def router_gate_row(counts, artifact):
    """proven_router forward signals (first_detected_at ≥ prereg) vs the standing
    gate: promotion_verdict ≥30 events / day-deflated LB > 3% / selection_null
    p ≤ 0.01 / ≥2 disjoint regimes. Expected PENDING with counts for months
    (accrual is the binding constraint). `counts` come from the DB; `artifact` is
    the optional gate JSON (None until the gate instrument writes it)."""
    nsig = int((counts or {}).get("n_signals", 0))
    nev = int((counts or {}).get("n_events", 0))
    nreg = int((counts or {}).get("n_regimes", 0))       # distinct months = disjoint regimes
    cur = f"{nsig} sigs / {nev} events / {nreg} regimes since prereg"
    thr = f"≥{EVENT_FLOOR} events / LB>3% / selection_null p≤0.01 / ≥2 regimes"
    verdict = str((artifact or {}).get("promotion_verdict", "")).upper()
    null_p = (artifact or {}).get("selection_null_p")
    if nev < EVENT_FLOOR or nreg < 2:
        eta = "weeks" if nev < EVENT_FLOOR else "months"
        return gate("router_gate", "PENDING", cur, thr,
                    "accrue proven_router fires past the prereg stamp", eta)
    if verdict.startswith("PROMOTE") and null_p is not None and null_p <= 0.01:
        return gate("router_gate", "MET", cur, thr, "—", "none")
    return gate("router_gate", "PENDING", cur, thr,
                "counts OK; needs day-deflated LB>3% + selection_null p≤0.01", "months")


def unified_book_row(ub):
    """Forward day-blocks the unified paper book has accrued vs the ≥20 floor
    (reports/unified_book.json → book.forward_days)."""
    if not ub:
        return gate("unified_book", "INDETERMINATE", "no artifact",
                    f"≥{UNIFIED_BOOK_FLOOR} forward day-blocks", "run unified_book.py forward", "weeks")
    fd = int((ub.get("book") or {}).get("forward_days", 0))
    cur = f"{fd}/{UNIFIED_BOOK_FLOOR} forward day-blocks"
    thr = f"≥{UNIFIED_BOOK_FLOOR}"
    if fd >= UNIFIED_BOOK_FLOOR:
        return gate("unified_book", "MET", cur, thr, "—", "none")
    return gate("unified_book", "NOT_MET", cur, thr, "accrue forward-sealed day-blocks", "weeks")


def beats_best_trader_row(bt):
    """Our best arm's day-clustered LB vs B_LB + 3pp — the fair "as profitable as
    the most profitable copyable trader" bar (reports/best_trader_benchmark.json:
    benchmark.overall.B_LB and our_arms.*.lb95)."""
    if not bt:
        return gate("beats_best_trader", "INDETERMINATE", "no artifact",
                    "best arm LB > B_LB + 3pp", "run best_trader_benchmark.py", "weeks")
    b_lb = ((bt.get("benchmark") or {}).get("overall") or {}).get("B_LB")
    best, best_arm = None, None
    for name, a in (bt.get("our_arms") or {}).items():
        lb = a.get("lb95")
        if lb is None:
            continue
        if best is None or lb > best:
            best, best_arm = lb, name
    if b_lb is None or best is None:
        return gate("beats_best_trader", "INDETERMINATE", "missing B_LB or arm LB",
                    "best arm LB > B_LB + 3pp", "accrue benchmark inputs", "weeks")
    thr_val = b_lb + BEST_TRADER_MARGIN
    cur = f"best arm {best_arm} LB {best:+.1%} vs B_LB+3pp {thr_val:+.1%}"
    thr = f"B_LB {b_lb:+.1%} + 3pp"
    if best > thr_val:
        return gate("beats_best_trader", "MET", cur, thr, "—", "none")
    return gate("beats_best_trader", "NOT_MET", cur, thr,
                "arm LB must clear the copyable-best floor +3pp", "months")


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
    days = q("select count(distinct date(first_detected_at at time zone 'UTC')) d, "
             "count(distinct coalesce(event_slug,condition_id)) ev "
             "from consensus_signals where strategy='favorite' and resolved")
    ndays = int(days[0]["d"]) if days else 0
    nev = int(days[0]["ev"]) if days else 0
    pt = load("persistence_tracker.json")
    pv = (pt or {}).get("verdict", "PENDING")
    gates.append(gate("persistence", "NOT_MET", f"{ndays} event-day clusters (WC-heavy), tracker={pv}",
                      f"≥{CLUSTER_FLOOR} independent NON-EXPIRING regimes (months)",
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

    # --- router_gate (capture-hardening Item 3): proven_router forward vs the
    #     standing gate. Distinct calendar months of first_detected_at proxy the
    #     "disjoint regimes" the gate requires (consensus_signals has no sport col).
    rc = q("select count(*) n, "
           "count(distinct coalesce(event_slug,condition_id)) ev, "
           "count(distinct to_char(first_detected_at at time zone 'UTC','YYYY-MM')) reg "
           "from consensus_signals "
           "where strategy='proven_router' and resolved "
           f"and first_detected_at >= '{ROUTER_PREREG_TS}'")
    counts = ({"n_signals": rc[0]["n"], "n_events": rc[0]["ev"], "n_regimes": rc[0]["reg"]}
              if rc else {})
    gates.append(router_gate_row(counts, load("router_gate.json")))

    # --- unified_book (Item 3): forward day-blocks vs the ≥20 floor ---
    gates.append(unified_book_row(load("unified_book.json")))

    # --- beats_best_trader (Item 3): best arm LB vs B_LB + 3pp ---
    gates.append(beats_best_trader_row(load("best_trader_benchmark.json")))
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
    _print(gates, v)
    out = {"gates": gates, "verdict": v}
    os.makedirs(REPORT_DIR, exist_ok=True)
    with open(os.path.join(REPORT_DIR, "readiness_ledger.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {os.path.join(REPORT_DIR, 'readiness_ledger.json')}")
    return out


def _print(gates, v):
    print("=" * 96)
    print("WS-2 · READINESS LEDGER · distance to real money (fuses D6–D22; certifies nothing)")
    print("=" * 96)
    hdr = f"{'gate':<19}{'status':<16}{'current':<44}{'eta':>7}"
    print(hdr); print("-" * len(hdr))
    for g in gates:
        req = "*" if g["gate"] in GO_GATES else " "
        print(f"{req}{g['gate']:<18}{g['status']:<16}{g['current'][:43]:<44}{g['eta']:>7}")
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

    # --- capture-hardening Item 3: the three new rows, on fixture JSON shapes ---
    # router_gate: thin counts → PENDING; counts cleared + gate artifact → MET.
    r_thin = router_gate_row({"n_signals": 3, "n_events": 4, "n_regimes": 1}, None)
    r_ok = router_gate_row({"n_signals": 200, "n_events": 40, "n_regimes": 3},
                           {"promotion_verdict": "PROMOTE", "selection_null_p": 0.004})
    r_cnt = router_gate_row({"n_signals": 200, "n_events": 40, "n_regimes": 3}, None)
    c4 = (r_thin["status"] == "PENDING" and r_thin["eta"] == "weeks"
          and r_ok["status"] == "MET" and r_cnt["status"] == "PENDING")
    ok = ok and c4
    print(f"  [{'ok' if c4 else 'FAIL'}] router_gate: thin→PENDING, cleared+artifact→MET, cleared-only→PENDING")

    # unified_book: below floor → NOT_MET; at/above → MET; missing → INDETERMINATE.
    ub_lo = unified_book_row({"book": {"forward_days": 1}})
    ub_hi = unified_book_row({"book": {"forward_days": 20}})
    ub_none = unified_book_row(None)
    c5 = (ub_lo["status"] == "NOT_MET" and "1/20" in ub_lo["current"]
          and ub_hi["status"] == "MET" and ub_none["status"] == "INDETERMINATE")
    ok = ok and c5
    print(f"  [{'ok' if c5 else 'FAIL'}] unified_book: 1/20→NOT_MET, 20/20→MET, none→INDETERMINATE")

    # beats_best_trader: real fixture (favorite LB −7.1% vs B_LB +3.4% + 3pp) → NOT_MET;
    # a hypothetical arm above the bar → MET.
    bt_real = beats_best_trader_row({
        "benchmark": {"overall": {"B_LB": 0.034}},
        "our_arms": {"favorite": {"lb95": -0.071}, "loose": {"lb95": -0.20}},
    })
    bt_win = beats_best_trader_row({
        "benchmark": {"overall": {"B_LB": 0.034}},
        "our_arms": {"favorite": {"lb95": 0.10}},
    })
    bt_none = beats_best_trader_row(None)
    c6 = (bt_real["status"] == "NOT_MET" and bt_win["status"] == "MET"
          and bt_none["status"] == "INDETERMINATE")
    ok = ok and c6
    print(f"  [{'ok' if c6 else 'FAIL'}] beats_best_trader: favorite LB<bar→NOT_MET, above→MET, none→INDETERMINATE")

    # The three rows are informational — they must NOT enter the GO-gate verdict.
    c7 = all(n not in GO_GATES for n in ("router_gate", "unified_book", "beats_best_trader"))
    ok = ok and c7
    print(f"  [{'ok' if c7 else 'FAIL'}] new rows are informational (not GO gates)")

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
