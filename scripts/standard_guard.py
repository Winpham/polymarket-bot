#!/usr/bin/env python3
"""
STANDARD GUARD (beat-best-trader, Cycle 7) — the champion-challenger non-regression mechanism.

Enforces Tue's directive: "only iterate and improve, never regress" from the frozen STANDARD
(the favorite-tilted consensus family: `favorite` + `elite_fresh_fav`; see reports/STANDARD-BASELINE.md
and reports/baseline_champion.json). Read-only, re-runnable with NO code change; it just re-measures.

Three jobs:

  1. MEASURE THE CHAMPION forward on the honest, belief-blind metric. The honest metric is the
     selection-matched surplus (surplus vs the band-matched `_blind` baseline) — NOT raw P&L (too noisy
     at the event level) and NOT the peak (unrepeatable). We reuse scripts/selection_null.py verbatim
     (subprocess, fixed seed) so the null is identical to the standing instrument; no logic duplication.
     We also read the realizable-edge context (resolved-ledger ROI + realizable honest_roi at the
     measured band-aware tax) for the report, clearly labeled.

  2. JUDGE A CHALLENGER (a proposed iteration = another strategy arm, or a future config). A challenger
     is ADOPTED only if it BEATS the champion out-of-sample on the honest realizable metric AND clears
     the belief-blind gate: selection_null p <= 0.01 with --calibrate PASS, promotion_verdict
     (belief-blind LB > 3% margin), and >= 2 disjoint NON-soccer regimes positive. Otherwise the
     CHAMPION STANDS. The decision function `judge_challenger` is pure and unit-tested (--selftest).

  3. REGRESSION ALARM. If the champion's own belief-blind lower bound (observed - 1.64*null_sigma) drops
     <= the pre-registered floor (0.0) over the scored record — or its selection is no longer real
     (p_emp > 0.01), or it is below the power floor (30 events) — the guard flags it LOUDLY, so a dying
     standard (regime change) is visible instead of a silent regression.

  ./standard_guard.py                 # measure champion; write reports/standard_guard.json
  ./standard_guard.py --challenger X  # also judge strategy X as a challenger to the champion
  ./standard_guard.py --selftest      # pure decision-function + regression-logic tests (NO DB/subprocess)

PAPER-ONLY. Promotes NOTHING, arms NOTHING, adopts NOTHING (it only REPORTS the verdict; adoption stays a
deliberate human call behind the standing 4 GO gates). No Rust. DB read-only. Cost-zero (Max-only).
"""

import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.join(os.path.dirname(HERE), "reports")
REPORT = os.path.join(REPORT_DIR, "standard_guard.json")

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]

# ---- FROZEN by reports/baseline_champion.json (the standard is defined by CONFIG) ----
CHAMPION_ARMS = ("favorite", "elite_fresh_fav")
CHAMPION_KEY_ARM = "favorite"          # the load-bearing belief-blind arm the regression floor keys on
REGRESSION_FLOOR = 0.0                 # pre-registered: champion belief-blind LB must stay > 0
POWER_FLOOR = 30                       # distinct-event power floor
PROMOTION_MARGIN = 0.03               # belief-blind LB must clear this for a challenger (capture margin)
P_BAR = 0.01                          # selection_null pre-registered p threshold
Z_LB = 1.64                           # one-sided 95% lower-bound multiplier on null sigma
# MEASURED band-aware follower tax (Cycle-5 real_tax.json; Win #1 baked in, NOT the old flat 0.013)
TAX_BY_BAND = {1: 0.0223, 2: 0.0273, 3: 0.0259, 4: 0.0235, 5: 0.0092}
SOCCER = "soccer"


# ============================ pure logic (unit-tested, NO I/O) ============================

def belief_blind_lb(observed, null_sigma):
    """One-sided 95% lower bound on the selection surplus using the null's sigma as the SE of the
    surplus estimate (matches how selection_null's z = observed/null_sigma is formed)."""
    if observed is None or null_sigma is None:
        return None
    return observed - Z_LB * null_sigma


def regression_status(arm):
    """Pure: given the champion key-arm's parsed selection_null row (dict with events/observed/
    null_sigma/p_emp), return (status, reason). status in
    {HEALTHY, REGRESSION-ALARM, INDETERMINATE-BY-POWER}."""
    if arm is None:
        return "INDETERMINATE-BY-POWER", "champion arm not measurable (no selection_null row)"
    ev = arm.get("events", 0)
    if ev < POWER_FLOOR:
        return "INDETERMINATE-BY-POWER", f"{ev} events < {POWER_FLOOR} power floor"
    lb = belief_blind_lb(arm.get("observed"), arm.get("null_sigma"))
    p = arm.get("p_emp")
    if arm.get("observed", 0) <= 0:
        return "REGRESSION-ALARM", f"selection surplus went non-positive ({arm.get('observed'):+.2%})"
    if p is not None and p > P_BAR:
        return "REGRESSION-ALARM", f"selection no longer real (p_emp {p:.4f} > {P_BAR})"
    if lb is not None and lb <= REGRESSION_FLOOR:
        return "REGRESSION-ALARM", f"belief-blind LB {lb:+.2%} <= floor {REGRESSION_FLOOR:+.2%}"
    return "HEALTHY", f"belief-blind LB {lb:+.2%} > {REGRESSION_FLOOR:+.2%}, p_emp {p:.4f}, {ev} ev"


def judge_challenger(champion, challenger, calibrate_pass):
    """Pure decision function. A challenger is ADOPTED iff it BEATS the champion out-of-sample on the
    honest realizable metric AND clears the belief-blind gate. Otherwise the CHAMPION STANDS.

    champion/challenger are dicts with:
      realizable_roi  : event-clustered honest_roi at the band-aware tax (the honest OOS metric)
      observed        : selection surplus over blind
      null_sigma      : the null sigma (for the belief-blind LB)
      p_emp           : selection_null empirical p
      non_soccer_regimes_positive : count of disjoint NON-soccer regimes with surplus > 0
    calibrate_pass    : bool (selection_null --calibrate PASS — the null is trustworthy)

    Returns (adopt: bool, verdict: str, reasons: [str]). ADOPTS NOTHING itself — reports the verdict.
    """
    reasons = []
    beats = (challenger.get("realizable_roi") is not None
             and champion.get("realizable_roi") is not None
             and challenger["realizable_roi"] > champion["realizable_roi"])
    reasons.append(
        f"beats champion realizable edge: {challenger.get('realizable_roi')} > "
        f"{champion.get('realizable_roi')} = {beats}")

    lb = belief_blind_lb(challenger.get("observed"), challenger.get("null_sigma"))
    p_ok = challenger.get("p_emp") is not None and challenger["p_emp"] <= P_BAR
    promo_ok = lb is not None and lb > PROMOTION_MARGIN
    regimes_ok = challenger.get("non_soccer_regimes_positive", 0) >= 2
    reasons.append(f"selection_null p<= {P_BAR}: {p_ok} (p={challenger.get('p_emp')})")
    reasons.append(f"--calibrate PASS: {calibrate_pass}")
    reasons.append(f"promotion_verdict LB> {PROMOTION_MARGIN:.0%}: {promo_ok} (LB={_pf(lb)})")
    reasons.append(f">=2 disjoint NON-soccer regimes: {regimes_ok} "
                   f"({challenger.get('non_soccer_regimes_positive', 0)})")

    belief_blind = p_ok and calibrate_pass and promo_ok and regimes_ok
    adopt = bool(beats and belief_blind)
    verdict = "ADOPT-CHALLENGER" if adopt else "CHAMPION-STANDS"
    return adopt, verdict, reasons


def _pf(x, spec="+.2%"):
    return "n/a" if x is None else format(x, spec)


# ============================ I/O: measure from the live system ============================

def _run(cmd, inp=None):
    return subprocess.run(cmd, input=inp, capture_output=True, text=True)


def selection_null_calibrate():
    """Run selection_null.py --calibrate; return True on PASS (exit 0)."""
    r = _run(["python3", os.path.join(HERE, "selection_null.py"), "--calibrate"])
    return r.returncode == 0


_ROW = re.compile(
    r"^(\S+)\s+(\d+)\s+([+-][\d.]+)%\s+([+-][\d.]+)%\s+±\s*([\d.]+)%\s+"
    r"([+-]?[\d.]+)\s+([\d.]+)\s+(\S.*)$")
_REGIME = re.compile(r"^(\S+)\s+(soccer|tennis|mlb|cs2|crypto|other)\s+(\d+)\s+([+-][\d.]+)%\s*$")


def selection_null_measure():
    """Run selection_null.py and parse per-strategy scoreboard rows + regime table.
    Returns {strategy: {events, observed, null_mu, null_sigma, z, p_emp, verdict, regimes:{rg:surplus}}}."""
    r = _run(["python3", os.path.join(HERE, "selection_null.py")])
    if r.returncode != 0:
        sys.exit("selection_null.py failed:\n" + r.stderr)
    out = {}
    for line in r.stdout.splitlines():
        m = _ROW.match(line)
        if m:
            s = m.group(1)
            out[s] = {
                "events": int(m.group(2)),
                "observed": float(m.group(3)) / 100.0,
                "null_mu": float(m.group(4)) / 100.0,
                "null_sigma": float(m.group(5)) / 100.0,
                "z": float(m.group(6)),
                "p_emp": float(m.group(7)),
                "verdict": m.group(8).strip(),
                "regimes": {},
            }
            continue
        mr = _REGIME.match(line)
        if mr and mr.group(1) in out:
            out[mr.group(1)]["regimes"][mr.group(2)] = float(mr.group(4)) / 100.0
    return out


def non_soccer_regimes_positive(entry):
    return sum(1 for rg, v in (entry or {}).get("regimes", {}).items() if rg != SOCCER and v > 0)


def _q(sql):
    r = _run(PG + ["-c", sql])
    if r.returncode != 0:
        sys.exit("psql failed:\n" + r.stderr)
    return r.stdout.strip().splitlines()


def realizable_roi_at_band_tax(strategies):
    """Event-clustered honest_roi at the MEASURED band-aware tax over the resolved record. The honest
    realizable metric the challenger must beat. Returns (mean_roi, n_events)."""
    tax_vals = ",".join(f"({b},{t})" for b, t in TAX_BY_BAND.items())
    strat_in = ",".join(f"'{s}'" for s in strategies)
    sql = (
        f"WITH tax(band,tx) AS (VALUES {tax_vals}), "
        f"base AS (SELECT COALESCE(event_slug,condition_id) AS ev, "
        f"(outcome_won::int)::double precision AS w, "
        f"width_bucket(initial_market_price,0.0,1.0,5) AS band, initial_market_price AS p0 "
        f"FROM consensus_signals WHERE resolved AND initial_market_price IS NOT NULL "
        f"AND strategy IN ({strat_in})), "
        f"sig AS (SELECT b.ev, (b.w-(b.p0+tax.tx))/NULLIF(b.p0+tax.tx,0) AS hroi "
        f"FROM base b JOIN tax ON b.band=tax.band), "
        f"evt AS (SELECT ev, AVG(hroi) AS e FROM sig GROUP BY ev) "
        f"SELECT COUNT(*), AVG(e) FROM evt"
    )
    rows = _q(sql)
    # rows: header 'count,avg' then data
    data = rows[-1].split(",") if len(rows) >= 2 else ["0", ""]
    n = int(data[0]) if data[0] else 0
    roi = float(data[1]) if len(data) > 1 and data[1] else None
    return roi, n


def resolved_ledger_roi(strategies):
    """Combined resolved-P&L ROI-on-turnover from honest_paper_ledger (the canonical baseline number)."""
    strat_in = ",".join(f"'{s}'" for s in strategies)
    rows = _q(f"SELECT COUNT(*), SUM(pnl), SUM(stake) FROM honest_paper_ledger "
              f"WHERE strategy IN ({strat_in})")
    data = rows[-1].split(",") if len(rows) >= 2 else ["0", "", ""]
    n = int(data[0]) if data[0] else 0
    pnl = float(data[1]) if len(data) > 1 and data[1] else 0.0
    stake = float(data[2]) if len(data) > 2 and data[2] else 0.0
    roi = pnl / stake if stake else None
    return {"bets": n, "pnl_usd": round(pnl, 2), "roi_on_turnover": roi}


def arm_metrics(sn, strategy):
    """Fuse selection_null row + realizable roi for one strategy into the guard's metric dict."""
    row = sn.get(strategy)
    rroi, rn = realizable_roi_at_band_tax([strategy])
    if row is None:
        return None
    return {
        "strategy": strategy,
        "events": row["events"],
        "observed": row["observed"],
        "null_sigma": row["null_sigma"],
        "z": row["z"],
        "p_emp": row["p_emp"],
        "verdict": row["verdict"],
        "belief_blind_lb": belief_blind_lb(row["observed"], row["null_sigma"]),
        "non_soccer_regimes_positive": non_soccer_regimes_positive(row),
        "realizable_roi": rroi,
        "realizable_events": rn,
    }


def measure(challenger_strategy=None):
    sn = selection_null_measure()
    calibrate = selection_null_calibrate()

    key = arm_metrics(sn, CHAMPION_KEY_ARM)
    # champion family realizable roi = combined arms (the honest metric a challenger must beat)
    champ_rroi, champ_rn = realizable_roi_at_band_tax(list(CHAMPION_ARMS))
    champion = {
        "arms": list(CHAMPION_ARMS),
        "key_arm": CHAMPION_KEY_ARM,
        "key_arm_metrics": key,
        "second_arm_metrics": arm_metrics(sn, "elite_fresh_fav"),
        "realizable_roi_family": champ_rroi,
        "realizable_events_family": champ_rn,
        "resolved_ledger": resolved_ledger_roi(list(CHAMPION_ARMS)),
    }
    reg_status, reg_reason = regression_status(key)

    out = {
        "meta": {
            "cycle": 7,
            "posture": "PAPER-ONLY; promotes/arms/adopts NOTHING; no Rust; DB read-only; cost-zero",
            "honest_metric": "belief-blind selection surplus (selection_null) + realizable edge at band-aware tax",
            "regression_floor": REGRESSION_FLOOR,
            "power_floor_events": POWER_FLOOR,
            "promotion_margin": PROMOTION_MARGIN,
            "calibrate_pass": calibrate,
            "champion_config": "favorite (price_band 0.65-0.98) + elite_fresh_fav; see baseline_champion.json",
        },
        "champion": champion,
        "regression": {"status": reg_status, "reason": reg_reason,
                       "belief_blind_lb": key.get("belief_blind_lb") if key else None,
                       "floor": REGRESSION_FLOOR},
        "challenger": None,
    }

    if challenger_strategy:
        chal = arm_metrics(sn, challenger_strategy)
        champ_metric = {"realizable_roi": champ_rroi,
                        "observed": key.get("observed") if key else None,
                        "null_sigma": key.get("null_sigma") if key else None}
        if chal is None:
            out["challenger"] = {"strategy": challenger_strategy,
                                 "verdict": "CHAMPION-STANDS",
                                 "reasons": ["challenger not measurable (below readout floor / no rows)"]}
        else:
            adopt, verdict, reasons = judge_challenger(champ_metric, chal, calibrate)
            out["challenger"] = {"strategy": challenger_strategy, "metrics": chal,
                                 "adopt": adopt, "verdict": verdict, "reasons": reasons}
    return out


def _print(out):
    m, ch = out["meta"], out["champion"]
    key = ch["key_arm_metrics"] or {}
    print("=" * 84)
    print("STANDARD GUARD — champion = favorite-tilted consensus (favorite + elite_fresh_fav)")
    print("=" * 84)
    print(f"belief-blind (selection_null, --calibrate {'PASS' if m['calibrate_pass'] else 'FAIL'}):")
    print(f"  key arm `{ch['key_arm']}`: {key.get('events')} ev · surplus {_pf(key.get('observed'))} · "
          f"z {key.get('z')} · p_emp {key.get('p_emp')} · LB {_pf(key.get('belief_blind_lb'))} · "
          f"{key.get('non_soccer_regimes_positive')} non-soccer regimes+ · {key.get('verdict')}")
    print(f"realizable edge (band-aware tax, event-clustered): family {_pf(ch['realizable_roi_family'])} "
          f"over {ch['realizable_events_family']} ev")
    led = ch["resolved_ledger"]
    print(f"resolved-P&L (canonical ledger): {led['bets']} bets · ${led['pnl_usd']} · "
          f"ROI {_pf(led['roi_on_turnover'])}")
    reg = out["regression"]
    banner = "  <<< LOUD" if reg["status"] == "REGRESSION-ALARM" else ""
    print(f"\nREGRESSION STATUS: {reg['status']} — {reg['reason']}{banner}")
    if out["challenger"]:
        c = out["challenger"]
        print(f"\nCHALLENGER `{c['strategy']}`: {c['verdict']}")
        for r in c.get("reasons", []):
            print(f"    · {r}")
    print("\nNOTE: adopts NOTHING. A challenger is only ADOPTED by a human, behind the standing 4 GO gates,")
    print("after it beats the champion OOS on the honest metric AND clears the belief-blind gate.")


# ============================ selftest (pure; NO DB/subprocess) ============================

def selftest():
    ok = True

    def check(name, cond):
        nonlocal ok
        ok = ok and cond
        print(f"  [{'ok' if cond else 'FAIL'}] {name}")

    # --- regression_status ---
    healthy = {"events": 158, "observed": 0.0806, "null_sigma": 0.0191, "p_emp": 0.0}
    st, _ = regression_status(healthy)
    check("healthy champion -> HEALTHY", st == "HEALTHY")

    dying_lb = {"events": 158, "observed": 0.02, "null_sigma": 0.02, "p_emp": 0.02}  # LB<=0, p>bar
    st, _ = regression_status(dying_lb)
    check("champion belief-blind LB<=0 / p>bar -> REGRESSION-ALARM", st == "REGRESSION-ALARM")

    neg = {"events": 100, "observed": -0.01, "null_sigma": 0.02, "p_emp": 0.9}
    st, _ = regression_status(neg)
    check("champion surplus non-positive -> REGRESSION-ALARM", st == "REGRESSION-ALARM")

    thin = {"events": 12, "observed": 0.08, "null_sigma": 0.02, "p_emp": 0.0}
    st, _ = regression_status(thin)
    check("champion below power floor -> INDETERMINATE-BY-POWER", st == "INDETERMINATE-BY-POWER")

    st, _ = regression_status(None)
    check("no champion row -> INDETERMINATE-BY-POWER", st == "INDETERMINATE-BY-POWER")

    # --- judge_challenger ---
    champ = {"realizable_roi": 0.05, "observed": 0.08, "null_sigma": 0.019}

    # (1) beats + clears belief-blind -> ADOPT
    good = {"realizable_roi": 0.09, "observed": 0.12, "null_sigma": 0.02,
            "p_emp": 0.0, "non_soccer_regimes_positive": 3}
    adopt, v, _ = judge_challenger(champ, good, True)
    check("challenger beats + belief-blind + calibrate PASS -> ADOPT", adopt and v == "ADOPT-CHALLENGER")

    # (2) beats but fails belief-blind p -> CHAMPION-STANDS
    weak_p = dict(good, p_emp=0.05)
    adopt, v, _ = judge_challenger(champ, weak_p, True)
    check("challenger beats but p>0.01 -> CHAMPION-STANDS", (not adopt) and v == "CHAMPION-STANDS")

    # (3) beats + significant but only 1 non-soccer regime -> CHAMPION-STANDS
    one_reg = dict(good, non_soccer_regimes_positive=1)
    adopt, _, _ = judge_challenger(champ, one_reg, True)
    check("challenger beats but <2 non-soccer regimes -> CHAMPION-STANDS", not adopt)

    # (4) clears belief-blind but does NOT beat champion realizable -> CHAMPION-STANDS
    not_better = dict(good, realizable_roi=0.03)
    adopt, _, _ = judge_challenger(champ, not_better, True)
    check("challenger clears gate but loses on realizable -> CHAMPION-STANDS", not adopt)

    # (5) calibrate FAIL (null untrustworthy) blocks adoption even if everything else clears
    adopt, _, _ = judge_challenger(champ, good, False)
    check("calibrate FAIL blocks adoption", not adopt)

    # (6) promotion margin: LB just above/below 3%
    thin_margin = {"realizable_roi": 0.09, "observed": 0.05, "null_sigma": 0.02,
                   "p_emp": 0.0, "non_soccer_regimes_positive": 3}  # LB = 0.05-1.64*0.02 = 0.0172 < 0.03
    adopt, _, _ = judge_challenger(champ, thin_margin, True)
    check("challenger LB below 3% margin -> CHAMPION-STANDS", not adopt)

    # --- belief_blind_lb arithmetic ---
    check("belief_blind_lb math", abs(belief_blind_lb(0.0806, 0.0191) - (0.0806 - 1.64 * 0.0191)) < 1e-9)

    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--challenger", metavar="STRATEGY", default=None,
                    help="judge STRATEGY as a challenger to the champion")
    args = ap.parse_args()
    if args.selftest:
        selftest()
    out = measure(args.challenger)
    _print(out)
    os.makedirs(REPORT_DIR, exist_ok=True)
    with open(REPORT, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {REPORT}")


if __name__ == "__main__":
    main()
