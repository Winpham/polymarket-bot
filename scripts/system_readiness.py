#!/usr/bin/env python3
"""
SYSTEM READINESS — is the machine POSITIONED to certify the edge and stop leaking money?

The reliability-first stance (D17) says "wait for persistence." But waiting is only coherent if
the system is actually (a) ACCRUING the independent clusters that will answer the persistence
question, and (b) not LEAKING money on the wrong signal while it waits. This instrument audits
both, read-only, so "wait" is an active plan with an ETA, not a shrug.

Three reads:
  1. ACCRUAL ETA — per key strategy: resolved events, distinct UTC-day clusters (the binding unit
     per D17-a), events/day, and the ETA to the K_MIN independent-cluster floor a persistence read
     needs. Turns "~1–2 weeks" into a dated number.
  2. THE ORTHOGONAL LEVER — trust_weighted (the D17 watch-item) accrual velocity: it fires far more
     than favorite, so IF its orthogonal edge is real it accrues statistical power fast. Report its
     rate so the profitability upside has a timeline.
  3. THE LIVE LEAK — the alert config. If the deployed CONSENSUS_ALERT_STRATEGIES does not include
     the winners (favorite/elite) but strict IS alerting, the bot is pushing a strategy that is
     NEGATIVE after costs while the real edge stays silent. Reads the effective config from an
     env-file (default ../.env.consensus) and flags the gap + the exact one-line fix.

Read-only, paper-only. Reuses selection_null.fetch. Nothing changes live.

Modes:
  ./system_readiness.py                  # live DB + ../.env.consensus; the scorecard; writes JSON
  ./system_readiness.py --env <path>     # point at a specific env file
  ./system_readiness.py --selftest       # the ETA math + config-gap detector on fixtures
"""

import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import selection_null as sn

WINNERS = ["favorite", "elite_fresh_fav"]
ORTHO_WATCH = "trust_weighted"
LOSING_ALERTER = "strict"       # the default-alerting strategy that is −EV after costs (entry 10 DODGE)
K_MIN_CLUSTERS = 10             # independent day-clusters a persistence read needs (D17-a floor)

READINESS_SQL = """
SELECT strategy,
       count(*) FILTER (WHERE resolved) AS resolved_events,
       count(DISTINCT (first_detected_at AT TIME ZONE 'UTC')::date) FILTER (WHERE resolved) AS distinct_days,
       count(*) FILTER (WHERE resolved AND first_detected_at > now() - interval '24 hours') AS resolved_24h,
       count(*) FILTER (WHERE NOT resolved) AS open_pending,
       min((first_detected_at AT TIME ZONE 'UTC')::date) FILTER (WHERE resolved) AS first_day,
       max((first_detected_at AT TIME ZONE 'UTC')::date) FILTER (WHERE resolved) AS last_day
FROM consensus_signals GROUP BY strategy
"""


def fetch_readiness():
    out = subprocess.run(sn.PG + ["-c", READINESS_SQL.replace("\n", " ")],
                         capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    import csv
    import io
    rows = {}
    for r in csv.DictReader(io.StringIO(out.stdout)):
        for k in ("resolved_events", "distinct_days", "resolved_24h", "open_pending"):
            r[k] = int(r[k] or 0)
        rows[r["strategy"]] = r
    return rows


def eta_to_floor(distinct_days, resolved_24h, resolved_events):
    """ETA (calendar days) to K_MIN independent clusters. The cluster is the UTC-day, and the
    stream adds ~1 cluster/day as long as it keeps firing (resolved_24h>0). Returns (need, eta_days)."""
    need = max(0, K_MIN_CLUSTERS - distinct_days)
    firing = resolved_24h > 0
    eta = 0 if need == 0 else (need if firing else None)  # ~1 cluster/day if still firing; None if silent
    return need, eta


def read_alert_config(env_path):
    """Parse the deployed alert config from the env file. Returns dict of the relevant keys
    (absent ⇒ the code default). Defaults: alerting is strict-only, trust arms off, dense off."""
    cfg = {"CONSENSUS_ALERT_STRATEGIES": None, "CONSENSUS_ALERT_WATCH_FOR": None,
           "CONSENSUS_TRUST_ARMS": None, "DENSE_CAPTURE": None}
    if env_path and os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() in cfg:
                    cfg[k.strip()] = v.strip()
    return cfg


def audit_alert_leak(cfg, ready):
    """The live-leak check: is a −EV strategy alerting while the winners are silent?"""
    alert_strats = cfg["CONSENSUS_ALERT_STRATEGIES"]
    # default (unset) ⇒ only `strict` alerts (its tier gate); winners fire at WATCH and are dropped.
    alerting = set(alert_strats.split(",")) if alert_strats else {LOSING_ALERTER}
    winners_alerting = [w for w in WINNERS if w in alerting]
    losing_alerting = LOSING_ALERTER in alerting and not alert_strats  # strict alerts by default
    leak = (not winners_alerting) and (LOSING_ALERTER in alerting)
    return {
        "effective_alerting": sorted(alerting),
        "winners_alerting": winners_alerting,
        "losing_strategy_alerting": LOSING_ALERTER in alerting,
        "LEAK": leak,
        "fix": ("append to .env.consensus: CONSENSUS_ALERT_STRATEGIES=strict,favorite,elite_fresh_fav "
                "+ CONSENSUS_ALERT_WATCH_FOR=favorite,elite_fresh_fav, then run "
                "scripts/consensus-autoupdate.sh (Tue's go — changes live alerts)") if leak else None,
    }


def run_live(env_path):
    ready = fetch_readiness()
    cfg = read_alert_config(env_path)
    print(f"SYSTEM READINESS · {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} · "
          f"persistence floor = {K_MIN_CLUSTERS} independent day-clusters (D17-a)\n")

    print("1. ACCRUAL — is the machine accruing what the persistence read needs?")
    print(f"   {'strategy':<18}{'resolved':>9}{'clusters':>9}{'/24h':>6}{'need':>6}{'ETA(d)':>8}  status")
    result = {"accrual": {}}
    for s in WINNERS + [ORTHO_WATCH, LOSING_ALERTER]:
        r = ready.get(s)
        if not r:
            print(f"   {s:<18}{'— not firing':>40}")
            continue
        need, eta = eta_to_floor(r["distinct_days"], r["resolved_24h"], r["resolved_events"])
        status = ("AT FLOOR" if need == 0 else
                  (f"~{eta}d to floor" if eta is not None else "STALLED (not firing)"))
        eta_s = "0" if need == 0 else (str(eta) if eta is not None else "∞")
        print(f"   {s:<18}{r['resolved_events']:>9}{r['distinct_days']:>9}{r['resolved_24h']:>6}"
              f"{need:>6}{eta_s:>8}  {status}")
        result["accrual"][s] = {"resolved": r["resolved_events"], "clusters": r["distinct_days"],
                                "per_24h": r["resolved_24h"], "need": need, "eta_days": eta}

    print(f"\n2. THE ORTHOGONAL LEVER — {ORTHO_WATCH} (D17 watch-item, the profitability upside):")
    tw = ready.get(ORTHO_WATCH)
    fav = ready.get("favorite")
    if tw and fav and fav["resolved_24h"] > 0:
        velocity = tw["resolved_24h"] / max(1, fav["resolved_24h"])
        print(f"   fires {tw['resolved_24h']}/24h = {velocity:.1f}× favorite ({fav['resolved_24h']}/24h) → if its")
        print(f"   orthogonal edge is real it accrues certification power ~{velocity:.1f}× faster. Currently")
        print(f"   {tw['distinct_days']} cluster(s) — needs {max(0, K_MIN_CLUSTERS - tw['distinct_days'])} more days of firing to test persistence.")
        result["ortho_lever"] = {"velocity_vs_favorite": round(velocity, 2),
                                 "clusters": tw["distinct_days"]}
    else:
        print(f"   {ORTHO_WATCH} not accruing (arm off or silent) → the orthogonal lever is DORMANT (nothing to certify).")
        result["ortho_lever"] = {"dormant": True}

    print("\n3. THE LIVE LEAK — is a −EV strategy alerting while the winners are silent?")
    leak = audit_alert_leak(cfg, ready)
    result["alert_audit"] = leak
    if leak["LEAK"]:
        print(f"   ⚠ LEAK: effective alerting = {leak['effective_alerting']} → '{LOSING_ALERTER}' (−EV after costs, entry-10 DODGE)")
        print(f"     is pushed while the winners {WINNERS} stay SILENT. Anyone acting on alerts follows the WRONG signal.")
        print(f"     FIX (Tue's go — live change): {leak['fix']}")
    else:
        print(f"   OK: alerting = {leak['effective_alerting']}; winners alerting = {leak['winners_alerting']}.")

    print("\nVERDICT:")
    fav_need = result["accrual"].get("favorite", {}).get("need")
    fav_eta = result["accrual"].get("favorite", {}).get("eta_days")
    if fav_need is not None:
        print(f"  • The persistence question favorite needs ~{fav_eta if fav_eta is not None else '∞'} more days of firing to reach"
              f" the {K_MIN_CLUSTERS}-cluster floor. Waiting is a DATED plan, not open-ended.")
    if leak["LEAK"]:
        print("  • BUT the system is LEAKING now: it alerts the losing strategy and silences the winners. The single")
        print("    highest-value action is not another instrument — it is flipping the alert config (pending Tue's go).")
    print(f"  • The orthogonal lever ({ORTHO_WATCH}) is the profitability upside to watch — high fire rate ⇒ fast power IF real.")
    return result


# ---------------------------------------------------------------------------------------
def selftest():
    ok = True
    # (1) ETA math: 4 clusters, still firing → need 6, ETA 6 days.
    need, eta = eta_to_floor(4, 43, 200)
    c1 = need == 6 and eta == 6
    ok = ok and c1
    print(f"  [{'ok' if c1 else 'FAIL'}] ETA: 4 clusters firing → need {need}, ETA {eta}d (want 6/6)")

    # (2) ETA: at floor → need 0, ETA 0.
    need2, eta2 = eta_to_floor(12, 40, 300)
    c2 = need2 == 0 and eta2 == 0
    ok = ok and c2
    print(f"  [{'ok' if c2 else 'FAIL'}] ETA at floor: need {need2}, ETA {eta2} (want 0/0)")

    # (3) ETA: silent (0/24h) below floor → ETA None (stalled, ∞).
    need3, eta3 = eta_to_floor(4, 0, 100)
    c3 = need3 == 6 and eta3 is None
    ok = ok and c3
    print(f"  [{'ok' if c3 else 'FAIL'}] ETA silent: need {need3}, ETA {eta3} (want 6/None = stalled)")

    # (4) leak detector: default config (unset) ⇒ strict-only alerting, winners silent ⇒ LEAK.
    leak_default = audit_alert_leak({"CONSENSUS_ALERT_STRATEGIES": None}, {})
    c4 = leak_default["LEAK"] is True
    ok = ok and c4
    print(f"  [{'ok' if c4 else 'FAIL'}] leak (default config): LEAK={leak_default['LEAK']} (want True)")

    # (5) leak detector: winners included ⇒ no leak.
    leak_fixed = audit_alert_leak({"CONSENSUS_ALERT_STRATEGIES": "strict,favorite,elite_fresh_fav"}, {})
    c5 = leak_fixed["LEAK"] is False and "favorite" in leak_fixed["winners_alerting"]
    ok = ok and c5
    print(f"  [{'ok' if c5 else 'FAIL'}] leak (fixed config): LEAK={leak_fixed['LEAK']} (want False)")

    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    env_path = None
    if "--env" in sys.argv:
        env_path = sys.argv[sys.argv.index("--env") + 1]
    else:
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env.consensus")
    result = run_live(env_path)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reports", "system_readiness.json")
    with open(out, "w") as f:
        json.dump(result, f, indent=1, default=str)
    print("\nartifact → reports/system_readiness.json")


if __name__ == "__main__":
    main()
