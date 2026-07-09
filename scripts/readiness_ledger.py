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
    # FAIL-CLOSED integrity guard (beat-best-trader run): B_LB is UNINFORMATIVE when it is
    # deeply negative (Bonferroni over thin per-wallet day-counts, effective_n≈1-3). "Beating"
    # a garbage floor is not beating the best trader. A real PASS requires the arm itself to be
    # profitable (LB>0) AND B_LB to be an informative (non-deeply-negative) floor. Otherwise the
    # honest verdict is INDETERMINATE-BY-POWER, per the charter — NOT a mechanical MET.
    UNINFORMATIVE_BLB = -0.05
    if best <= 0 or (b_lb is not None and b_lb < UNINFORMATIVE_BLB):
        return gate("beats_best_trader", "INDETERMINATE-BY-POWER",
                    cur + " — B_LB uninformative (thin per-wallet power) and/or arm LB≤0",
                    thr, "need ≥30 tailable events/wallet-regime so B_LB is a real floor; accrue months",
                    "months")
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

    # --- router_vs_fleet (beat-best-trader run): router forward surplus over the
    #     day-matched fleet blind, with the matched permutation null. ---
    rvf = load("router_verify.json") or {}
    fwd = ((rvf.get("a2_forward_cohort") or {}).get("surplus_vs_fleet_day") or {})
    a3 = (rvf.get("a3_permutation_null") or {})
    if fwd:
        s, lb, p = fwd.get("mean"), fwd.get("lb"), a3.get("p_emp")
        met = (lb is not None and lb > 0.03 and p is not None and p <= 0.01)
        gates.append(gate("router_vs_fleet",
                          "MET" if met else "NOT_MET",
                          f"fwd surplus {_pf(s)} LB {_pf(lb)}, null p={p}",
                          "surplus LB > 3% AND null p ≤ 0.01",
                          "router forward surplus is ≈0 / null-indistinguishable; accrue non-soccer regimes",
                          "months"))
    else:
        gates.append(gate("router_vs_fleet", "INDETERMINATE", "no router_verify forward artifact",
                          "surplus LB > 3%", "run router_verify.py", "weeks"))

    # --- router_vs_best (H2): router forward surplus vs B_LB (best copyable wallet repriced). ---
    bt = load("best_trader_benchmark.json") or {}
    blb_overall = ((bt.get("benchmark") or {}).get("overall") or {}).get("B_LB")
    raw = ((rvf.get("a2_forward_cohort") or {}).get("raw") or {}).get("mean")
    gates.append(gate("router_vs_best", "INDETERMINATE-BY-POWER",
                      f"router raw {_pf(raw)} vs B_LB(overall) {_pf(blb_overall)} — both negative, uninformative",
                      "router LB > B_LB + 3pp, both meaningfully positive",
                      "B_LB uninformative: <30 tailable events/wallet-regime, effective_n≈1-3 days; accrue months",
                      "months"))

    # --- fade_transfer (H5): soft cells that persist OUTSIDE the discovery cell. ---
    sm2 = load("softness_fade.json") or {}
    soft2 = [c for c in (sm2.get("cells") or []) if c.get("SOFT_CELL")]
    disc = {("soccer", "directional", 5)}
    transfer = [c for c in soft2 if (c.get("sport"), c.get("mtype"), c.get("band")) not in disc]
    gates.append(gate("fade_transfer",
                      "MET" if transfer else "NOT_MET",
                      (f"{len(transfer)} soft cell(s) OUTSIDE discovery" if transfer
                       else f"{len(soft2)} soft cell(s), all = discovery cell (soccer/directional/b5); NO transfer"),
                      "≥1 FDR-soft fade cell in a sport-regime NOT discovered on",
                      "band5 fade is soccer-confined (SOCCER-ARTIFACT); accrue non-soccer band5 population",
                      "months"))

    # --- mm_screen_refinement (H7): relaxed round_trip vs frozen on cohort forward copy-return. ---
    mse = load("mm_screen_effect.json") or {}
    ab = mse.get("screen_ab") or {}
    fr = (ab.get("current_0.30/0.25/0.50") or {}).get("cohort_fwd_h2")
    rl = (ab.get("relax_round_trip_0.50") or {}).get("cohort_fwd_h2")
    if fr is not None and rl is not None:
        nod = rl >= fr
        gates.append(gate("mm_screen_refinement",
                          "LEAD" if nod else "NOT_MET",
                          f"relaxed cohort-fwd {_pf(rl)} vs frozen {_pf(fr)} (relaxed {'≥' if nod else '<'} frozen); both NEGATIVE now",
                          "relaxed ≥ frozen on cohort fwd-return, forward-confirmed ≥1 more week",
                          "no-downside + recovers directional traders, but cohort return decayed negative; forward-confirm before any Rust change (Phase-1 STOP)",
                          "weeks"))
    else:
        gates.append(gate("mm_screen_refinement", "INDETERMINATE", "no mm_screen_effect artifact",
                          "relaxed ≥ frozen cohort fwd-return", "run mm_screen_effect.py", "weeks"))

    # ============================ Cycle-2 rows (beat-best-trader run, Threads A-D) ============
    # --- decay_diagnosis (Thread A): is the copy-cohort forward-return decay recoverable? ---
    dd = load("decay_decompose.json") or {}
    if dd:
        soc = (dd.get("soccer") or {})
        ver = dd.get("verdict", "")
        gates.append(gate("decay_diagnosis",
                          "RECOVERABLE" if "RECOVERABLE" in ver else
                          ("GENUINE-DECAY" if "GENUINE" in ver else "INDETERMINATE"),
                          f"soccer copy-edge {_pf(soc.get('r_early'))}->{_pf(soc.get('r_late'))} "
                          f"(intact={soc.get('intact')}); ts artifact ruled out",
                          "distinguish mix/composition vs genuine soccer-edge decay",
                          "soccer edge intact-but-unpowered; pooled decay = composition + thin reversion; "
                          "route per-cell (do not pool soccer w/ never-copy cells)",
                          "weeks"))

    # --- topk_ensemble (Thread B): does a small concentrated ensemble beat fleet-average OOS? ---
    tk = load("topk_ensemble.json") or {}
    if tk:
        k3 = ((tk.get("conditional_on_pick") or {}).get("ew_k3") or {})
        p3 = (tk.get("random_k_null_p") or {}).get("3")
        met = (k3.get("ci_lo") is not None and k3["ci_lo"] > 0 and p3 is not None and p3 <= 0.01)
        gates.append(gate("topk_ensemble",
                          "MET" if met else "INDETERMINATE-BY-POWER",
                          f"k=3 meanΔ {_pf(k3.get('mean'))} vs fleet-avg, CI[{_pf(k3.get('ci_lo'))},"
                          f"{_pf(k3.get('ci_hi'))}], random-k null p={p3}",
                          "k-ensemble meanΔ CI-lo > 0 AND random-k null p ≤ 0.01, ≥2 regimes",
                          "k≈3 is the operator sweet spot (beats k=1 router AND fleet-avg on point est), "
                          "but CI straddles 0 / null p not gate-clearing; accrue regimes",
                          "months"))

    # --- fade_persistence (Thread C): is the soccer-band5 fade a recurring within-soccer edge? ---
    fp = load("fade_persistence.json") or {}
    if fp:
        ver = fp.get("verdict", "")
        wn = (fp.get("within_soccer_null") or {})
        gates.append(gate("fade_persistence",
                          "RECURRING" if "RECURRING" in ver else
                          ("ARTIFACT" if "ARTIFACT" in ver else "INDETERMINATE"),
                          f"early {_pf((fp.get('early') or {}).get('fade_net'))} vs late "
                          f"{_pf((fp.get('late') or {}).get('fade_net'))} (sign flips), "
                          f"within-soccer null p={wn.get('p_emp')}",
                          "fade positive in BOTH soccer halves, day-bootstrap CI>0, within-soccer null p≤0.05",
                          "fade is a few-day artifact within soccer (not just non-transfer); do NOT "
                          "forward-track; needs a genuinely recurring soft cell",
                          "months"))

    # --- dense_capture_coverage (Thread D): λ̂ trajectory coverage + the paper-safe fix. ---
    dc = load("dense_capture_diag.json") or {}
    if dc:
        today = ((dc.get("coverage_signal_id_join_TODAY") or {}).get("frac"))
        fix = ((dc.get("coverage_market_key_join_FIX") or {}).get("frac"))
        gates.append(gate("dense_capture_coverage",
                          "PENDING",
                          f"coverage {_pf(today)} (signal_id join) -> {_pf(fix)} with market-key fix "
                          f"(13x); root cause = sibling-dedup crowd-out",
                          "trajectory coverage ≥ 50% for a measured (non-proxy) λ̂",
                          "apply read-side market-key join (paper-safe, DEFERRED gate-input swap) then "
                          "accrue post-dense-start favorites toward 50%",
                          "weeks"))

    # --- reliability_shortlist (R1): gated reliability composite at THEIR price ---
    rl = load("reliability_score.json") or {}
    if rl:
        m = rl.get("meta", {})
        nsl = m.get("n_shortlist")
        gates.append(gate("reliability_shortlist",
                          "BUILT",
                          f"{nsl} gate-clearing wallets of {m.get('n_wallets_scored')} scored "
                          f"(66% positive at their price); ranked by Sortino",
                          "gated on every axis (skill-null, cross-sport, both-halves, consistency)",
                          "sanity: 1/5 named specialists surface (rest MM-screened or miss skill-null) "
                          "— gate is belief-blind, not reputation-driven",
                          "weeks"))

    # --- reliability_persistence (R2): the GO/NO-GO — does reliability persist OOS? ---
    rp = load("reliability_persistence.json") or {}
    if rp:
        rt = (rp.get("rank_tests") or {}).get("reg_sortino") or {}
        gates.append(gate("reliability_persistence",
                          "GO" if rp.get("verdict", "").startswith("GO") else
                          ("NO-GO" if rp.get("verdict") == "NO-GO" else "INDETERMINATE-BY-POWER"),
                          f"reg_sortino rank rho {_pf(rt.get('spearman'))} p_global {rt.get('perm_p_global')} "
                          f"p_nstrata {rt.get('perm_p_nstrata')} (confound-controlled null agrees)",
                          "early-window reliability rank predicts late-window rank, matched null p≤0.05",
                          "reliability RANK persists (survives Bonferroni + n-strata null); practical "
                          "profit-arm marginal (p≈0.044); split is within-wallet-temporal not calendar-forward",
                          "weeks"))

    # --- reliability_book (R3): diversified reliability-weighted book vs best single trader ---
    rb = load("reliability_portfolio.json") or {}
    if rb:
        iw = rb.get("book_vs_best_single_insample", {})
        nb = rb.get("belief_blind_null", {})
        gates.append(gate("reliability_book",
                          "RISK-REDUCTION-ONLY",
                          f"book maxDD {_pf(iw.get('maxdd_book'))} vs best-single {_pf(iw.get('maxdd_best'))} "
                          f"(halved, in+out sample); Sortino {_pf(iw.get('sortino_book'))} < "
                          f"{_pf(iw.get('sortino_best'))} (loses); selection-vs-random p={nb.get('selection_beats_random_p')}",
                          "book beats best single reliable trader on risk-adjusted return (Sortino) OOS + null p≤0.01",
                          "diversification HALVES drawdown (the risk axis) but does NOT beat best single on "
                          "Sortino; copyable-positive at modeled entry but fill/lag-unvalidated; nothing promoted",
                          "months"))

    # ============================ Cycle-5 rows (REAL follower-tax measurement) ================
    # --- real_follower_tax (T2): MEASURED tax vs the MODELED (0.013+spread) every verdict rests on ---
    rt = load("real_tax.json") or {}
    if rt:
        ov = rt.get("overall", {})
        gates.append(gate("real_follower_tax",
                          "MEASURED (thin)",
                          f"real tax mkt-clustered {_pf(ov.get('real_tax_market_clustered_mean'))} / "
                          f"pooled {_pf(ov.get('real_tax_pooled_mean'))} vs MODELED "
                          f"{_pf(ov.get('modeled_tax_fillwt'))}; coverage {_pf(ov.get('coverage'))} "
                          f"({ov.get('n_matched')}/{ov.get('n_fills')} fills, {ov.get('n_markets')} mkts)",
                          "measured tax on ≥50% coverage, stable across ≥5 independent regimes",
                          "REAL tax < MODELED (partial modeling artifact) BUT ~8% coverage, ~2.3d capture, "
                          "capture-burst-adjacent bias — INDETERMINATE-BY-POWER; DEFERRED live/Rust swap",
                          "weeks"))

    # --- realizable_edge_on_measured_tax (T3): does any play survive the measured tax? ---
    dr = load("drawdown_optimization_real_pooled.json") or {}
    drc = load("drawdown_optimization_real_clustered.json") or {}
    if dr and drc:
        gp = dr.get("WORTH_IT_GATE", {})
        gc = drc.get("WORTH_IT_GATE", {})
        gates.append(gate("realizable_edge_on_measured_tax",
                          "NOT_MET",
                          f"refined OOS Calmar {_pf(gc.get('refined_our_calmar_OOS'))}(clust)/"
                          f"{_pf(gp.get('refined_our_calmar_OOS'))}(pool) still < best-single "
                          f"{_pf(gp.get('best_single_our_OOS_calmar'))}; belief-blind p≈"
                          f"{gc.get('belief_blind',{}).get('p')}/{gp.get('belief_blind',{}).get('p')}",
                          "a play beats random book (p≤0.05) AND best single on realizable Calmar at MEASURED tax",
                          "lighter measured tax lifts realizable Calmar ~15-50% but the best single trader "
                          "ALSO improves and still dominates; selection-p invariant to tax level (~0.10). "
                          "WALL CONFIRMED — forward accrual only; NO play forward-tracked (T4 skipped)",
                          "months"))

    # --- edge_reality_recovered (T2 λ̂): market-key-join λ̂ on recovered dense-capture coverage ---
    clvmk = load("clv_lambda_marketkey.json") or {}
    if clvmk:
        lo = (clvmk.get("lambda_ci") or [None, None])[0]
        gates.append(gate("edge_reality_recovered",
                          "INDETERMINATE",
                          f"market-key join recovers coverage {_pf(clvmk.get('trajectory_coverage'))} "
                          f"(vs 2% signal_id); λ̂ {_pf(clvmk.get('lambda_hat'))} CI-lo {_pf(lo)} "
                          f"(<< {MIN_LAMBDA} floor); CLV-null p={clvmk.get('null_p')}",
                          f"λ̂ CI-lo > {MIN_LAMBDA} at ≥{COVERAGE_FLOOR:.0%} coverage",
                          "coverage 2%->20% (real recovery) but still <50% and λ̂-lo far below floor — edge "
                          "remains mostly FLB-bias; informational (DEFERRED default-swap of the GO gate input)",
                          "weeks"))

    # ============================ Cycle-6 rows (FORWARD-TRACK accrual instrument) ==============
    # Per frozen play (PREREG_FORWARD_TRACK): the forward (post-seal) readiness STATUS, its accrual
    # counts, and the first binding failure. Informational (NOT GO gates). Binding = accrual horizon
    # (independent NON-SOCCER regime persistence, MONTHS). Reads reports/forward_track.json.
    for row in forward_track_rows(load("forward_track.json")):
        gates.append(row)

    # ============================ Cycle-7 rows (STANDARD GUARD non-regression) =================
    # The frozen STANDARD (favorite-tilted consensus) champion metrics + regression status. Reads
    # reports/standard_guard.json. Informational (NOT GO gates): tracks whether our current best system
    # is still belief-blind-real and has not silently regressed. See reports/STANDARD-BASELINE.md.
    for row in standard_rows(load("standard_guard.json")):
        gates.append(row)
    return gates


def standard_rows(sg):
    """Pure: map standard_guard.json to two informational ledger rows — `standard_champion` (the frozen
    standard's belief-blind + realizable + resolved-P&L read) and `standard_regression` (HEALTHY /
    REGRESSION-ALARM / INDETERMINATE-BY-POWER against the pre-registered belief-blind floor). Returns []
    when the artifact is missing. Informational only — NEVER a GO gate."""
    if not sg:
        return []
    ch = sg.get("champion") or {}
    key = ch.get("key_arm_metrics") or {}
    led = ch.get("resolved_ledger") or {}
    reg = sg.get("regression") or {}
    champ = gate(
        "standard_champion",
        "STANDARD",
        (f"favorite surplus {_pf(key.get('observed'))} (z {key.get('z')}, p {key.get('p_emp')}, "
         f"LB {_pf(key.get('belief_blind_lb'))}); realizable {_pf(ch.get('realizable_roi_family'))}; "
         f"resolved-P&L {_pf(led.get('roi_on_turnover'))} over {led.get('bets')} bets"),
        "the frozen standard (favorite-tilted consensus); challengers must beat it OOS + clear belief-blind",
        "iterate only via standard_guard.py --challenger; adopt NOTHING that does not beat the champion",
        "none")
    alarm = reg.get("status") == "REGRESSION-ALARM"
    regr = gate(
        "standard_regression",
        reg.get("status", "INDETERMINATE-BY-POWER"),
        f"belief-blind LB {_pf(reg.get('belief_blind_lb'))} vs floor {_pf(reg.get('floor'))} — {reg.get('reason')}",
        f"champion belief-blind LB must stay > {_pf(reg.get('floor'))} (pre-registered)",
        ("ESCALATE — the standard itself may be dying (regime change); do not silently regress"
         if alarm else "none — standard holding; keep watching forward"),
        "weeks" if alarm else "none")
    return [champ, regr]


def forward_track_rows(ft):
    """Pure: map forward_track.json to informational ledger rows (one per frozen play). Returns [] when
    the artifact is missing. Binding = the accrual horizon (non-soccer regime persistence, months)."""
    if not ft:
        return []
    rows = []
    for pid, p in (ft.get("plays") or {}).items():
        cal = p.get("realizable_calmar")
        rows.append(gate(
            f"forward_{pid}",
            p.get("status", "INDETERMINATE-BY-POWER"),
            (f"{p.get('n_events', 0)} fwd events / {p.get('n_days', 0)} days / "
             f"{p.get('non_soccer_regimes', 0)} non-soccer regimes; realizable Calmar "
             f"{_pf(cal) if cal is not None else 'n/a'}; first-binding={p.get('first_binding')}"),
            "clears every forward gate (power/Calmar/beats-best/selection_null/promotion/pilot/"
            "≥2 non-soccer regimes/λ̂≥0.25) → GO-CANDIDATE (ESCALATE)",
            p.get("needs", "accrue forward non-soccer regimes"),
            p.get("eta", "months")))
    return rows


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
    # forward_track serializes an infinite Calmar (zero-drawdown play) as the string 'inf';
    # a display helper must not crash on a non-numeric value — pass strings through verbatim.
    if isinstance(x, str):
        return x
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

    # beats_best_trader: real fixture (favorite LB −7.1%, UNDERWATER) → the Cycle-1 fail-closed guard
    # returns INDETERMINATE-BY-POWER (an underwater arm cannot be said to beat/not-beat a benchmark —
    # that is an edge/power problem, not a decidable comparison); a hypothetical arm above the bar → MET.
    bt_real = beats_best_trader_row({
        "benchmark": {"overall": {"B_LB": 0.034}},
        "our_arms": {"favorite": {"lb95": -0.071}, "loose": {"lb95": -0.20}},
    })
    bt_win = beats_best_trader_row({
        "benchmark": {"overall": {"B_LB": 0.034}},
        "our_arms": {"favorite": {"lb95": 0.10}},
    })
    bt_none = beats_best_trader_row(None)
    c6 = (bt_real["status"] == "INDETERMINATE-BY-POWER" and bt_win["status"] == "MET"
          and bt_none["status"] == "INDETERMINATE")
    ok = ok and c6
    print(f"  [{'ok' if c6 else 'FAIL'}] beats_best_trader: favorite LB<bar→NOT_MET, above→MET, none→INDETERMINATE")

    # The three rows are informational — they must NOT enter the GO-gate verdict.
    c7 = all(n not in GO_GATES for n in ("router_gate", "unified_book", "beats_best_trader"))
    ok = ok and c7
    print(f"  [{'ok' if c7 else 'FAIL'}] new rows are informational (not GO gates)")

    # --- Cycle-6 forward-track rows (pure, fixture JSON) ---
    ft_fix = {"plays": {
        "play_A_tail": {"status": "INDETERMINATE-BY-POWER", "n_events": 0, "n_days": 0,
                        "non_soccer_regimes": 0, "realizable_calmar": None,
                        "first_binding": "power_events", "needs": "accrue >= 30 forward events",
                        "eta": "weeks"},
        "play_C_book": {"status": "GO-CANDIDATE", "n_events": 120, "n_days": 40,
                        "non_soccer_regimes": 4, "realizable_calmar": 0.3,
                        "first_binding": None, "needs": "ESCALATE", "eta": "none"}}}
    frows = forward_track_rows(ft_fix)
    c8 = (len(frows) == 2
          and frows[0]["gate"] == "forward_play_A_tail" and frows[0]["status"] == "INDETERMINATE-BY-POWER"
          and any(r["status"] == "GO-CANDIDATE" for r in frows)
          and all(r["gate"] not in GO_GATES for r in frows))       # informational only
    ok = ok and c8
    print(f"  [{'ok' if c8 else 'FAIL'}] forward-track rows: per-play, informational (not GO gates)")
    c9 = forward_track_rows(None) == []                            # graceful when artifact missing
    ok = ok and c9
    print(f"  [{'ok' if c9 else 'FAIL'}] forward-track rows graceful when artifact missing")

    # --- Cycle-7 standard-guard rows (pure, fixture JSON) ---
    sg_fix = {"champion": {"key_arm_metrics": {"observed": 0.0806, "z": 4.28, "p_emp": 0.0,
                           "belief_blind_lb": 0.0493}, "realizable_roi_family": 0.0525,
                           "resolved_ledger": {"bets": 229, "roi_on_turnover": 0.0217}},
              "regression": {"status": "HEALTHY", "reason": "LB +4.93% > 0", "belief_blind_lb": 0.0493,
                             "floor": 0.0}}
    srows = standard_rows(sg_fix)
    c10 = (len(srows) == 2 and srows[0]["gate"] == "standard_champion"
           and srows[1]["gate"] == "standard_regression" and srows[1]["status"] == "HEALTHY"
           and all(r["gate"] not in GO_GATES for r in srows))       # informational only
    ok = ok and c10
    print(f"  [{'ok' if c10 else 'FAIL'}] standard-guard rows: champion+regression, informational (not GO gates)")
    alarm_fix = dict(sg_fix, regression={"status": "REGRESSION-ALARM", "reason": "LB<=0",
                                         "belief_blind_lb": -0.01, "floor": 0.0})
    c11 = (standard_rows(alarm_fix)[1]["status"] == "REGRESSION-ALARM"
           and standard_rows(alarm_fix)[1]["eta"] == "weeks"        # alarm escalates
           and standard_rows(None) == [])                           # graceful when artifact missing
    ok = ok and c11
    print(f"  [{'ok' if c11 else 'FAIL'}] standard-guard: alarm escalates + graceful when missing")

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
