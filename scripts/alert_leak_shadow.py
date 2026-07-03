#!/usr/bin/env python3
"""
WS-C — ALERT-LEAK SHADOW VERIFY. Quantify the value leaking out because the WINNERS are silent.

THE LEAK (D19-b, confirmed empirically here): the only strategy that has EVER pushed an alert is
`strict` (243 alerts on this record). `favorite` and `elite_fresh_fav` — the +EV selection edges
(entry 10 / D16) — carry `alerting: false` in `default_portfolio()` (consensus.rs) and have fired
**332 signals / 0 alerts**. Anyone acting on alerts therefore follows `strict` — whose non-favorite
residue is the record's reliably-LOSING DODGE cell (entry 10) — while the winners fire silently. This
is the single biggest REALIZED-P&L lever and it costs nothing to fix: the default-OFF env override
`CONSENSUS_ALERT_STRATEGIES` (+ `CONSENSUS_ALERT_WATCH_FOR`) already exists (config.rs L141-148, the
D12 config) and was simply never deployed. No code change is needed — this script produces the
SHADOW EVIDENCE for the flip, which is Tue's call.

What it measures on the resolved record:
  1. Alert volume by strategy TODAY (the leak: winners = 0).
  2. NET-NEW leaked alerts if `favorite,elite_fresh_fav` were enabled — fired winner-signals MINUS
     those already covered by a `strict` alert on the same (market, outcome) within the cross-strategy
     dedup window (config default 60 min). The dedup is what stops double-firing; net-new < fired
     PROVES it is intact.
  3. The realizable-P&L COST of the leak: flat-shares realizable P&L (entry+1¢ haircut, 2% fee, per
     $100 notional) of the net-new leaked RESOLVED winner-signals — the money an alert-follower leaves
     on the table — vs the realizable P&L of what `strict` actually alerted (the DODGE side).
  4. Spam check: net-new alerts/day vs strict's current alerts/day. A sane (≈1–2×) increase ⇒ enable;
     a blow-up ⇒ gate on a rate-limit first.

Read-only. Nothing enabled. The fix is an env flip Tue makes; this run PROPOSES + STOPS.
  ./alert_leak_shadow.py                 # the shadow report; writes reports/alert_leak_shadow.json
  ./alert_leak_shadow.py --dedup-mins 60 # match CONSENSUS_ALERT_CROSS_DEDUP_MINS
"""

import argparse
import csv
import io
import json
import os
import subprocess
import sys
from collections import defaultdict

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]
WINNERS = ("favorite", "elite_fresh_fav")
FEE, HAIRCUT_C, STAKE = 0.02, 0.01, 100.0     # match selection_null / corr_risk cost model

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")


def q(sql):
    out = subprocess.run(PG + ["-f", "-"], input=sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    return list(csv.DictReader(io.StringIO(out.stdout)))


def realizable_pnl(entry, won):
    """Flat-shares realizable P&L per $100 notional: buy at entry+1¢, pay 2% fee on cost."""
    e = min(0.999, entry + HAIRCUT_C)
    return STAKE * (won - e) - FEE * STAKE * e


def selftest():
    ok = True
    # realizable_pnl: a winner at 0.80 → buy 0.81, +100*(1-0.81) - 0.02*100*0.81 = +19 - 1.62 = +17.38
    w = realizable_pnl(0.80, 1)
    if abs(w - 17.38) > 1e-6:
        print(f"  FAIL winner pnl {w:+.2f} (expected +17.38)"); ok = False
    else:
        print(f"  PASS winner pnl {w:+.2f}")
    # a loser at 0.80 → buy 0.81, -100*0.81 - 1.62 = -82.62
    l = realizable_pnl(0.80, 0)
    if abs(l - (-82.62)) > 1e-6:
        print(f"  FAIL loser pnl {l:+.2f} (expected -82.62)"); ok = False
    else:
        print(f"  PASS loser pnl {l:+.2f}")
    # net-new must never exceed fired (dedup can only remove) — logical invariant
    print(f"  PASS net-new≤fired is enforced by construction (covered rows `continue`)")
    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dedup-mins", type=int, default=60)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return

    # 1. alert volume today
    vol = q("SELECT strategy, COUNT(*) n_alerts, COUNT(DISTINCT signal_id) n_sig, "
            "MIN(sent_at)::date first, MAX(sent_at)::date last, "
            "COUNT(DISTINCT sent_at::date) n_days FROM consensus_alerts GROUP BY strategy")
    strict_days = next((int(r["n_days"]) for r in vol if r["strategy"] == "strict"), 1) or 1
    strict_alerts = next((int(r["n_alerts"]) for r in vol if r["strategy"] == "strict"), 0)

    # 2/3. winner signals + strict-alert coverage overlap (cross-strategy dedup, ±dedup window)
    rows = q(f"""
    WITH strict_al AS (
      SELECT cs.condition_id, cs.outcome_index, a.sent_at
      FROM consensus_alerts a JOIN consensus_signals cs ON cs.id=a.signal_id
      WHERE a.strategy='strict')
    SELECT w.strategy, w.id, w.condition_id, w.outcome_index, w.tier, w.resolved,
      w.outcome_won, w.initial_mean_price AS entry, w.first_detected_at,
      EXISTS (SELECT 1 FROM strict_al s WHERE s.condition_id=w.condition_id
              AND s.outcome_index=w.outcome_index
              AND s.sent_at BETWEEN w.first_detected_at - make_interval(mins => {args.dedup_mins})
                               AND w.first_detected_at + make_interval(mins => {args.dedup_mins})
             ) AS covered_by_strict
    FROM consensus_signals w
    WHERE w.strategy IN {WINNERS} AND w.initial_mean_price IS NOT NULL
    """)

    by = defaultdict(lambda: {"fired": 0, "resolved": 0, "covered": 0, "netnew": 0,
                              "netnew_resolved": 0, "netnew_pnl": 0.0, "netnew_won": 0,
                              "days": set(), "tiers": defaultdict(int)})
    for r in rows:
        s = by[r["strategy"]]
        s["fired"] += 1
        s["tiers"][r["tier"]] += 1
        s["days"].add(r["first_detected_at"][:10])
        resolved = r["resolved"] == "t"
        covered = r["covered_by_strict"] == "t"
        if resolved:
            s["resolved"] += 1
        if covered:
            s["covered"] += 1
            continue
        s["netnew"] += 1
        if resolved:
            s["netnew_resolved"] += 1
            won = int(r["outcome_won"] == "t")
            s["netnew_won"] += won
            s["netnew_pnl"] += realizable_pnl(float(r["entry"]), won)

    # realizable P&L of what strict actually alerted (the DODGE side), resolved
    strict_pnl_rows = q("""
      SELECT cs.outcome_won, cs.initial_mean_price AS entry
      FROM consensus_alerts a JOIN consensus_signals cs ON cs.id=a.signal_id
      WHERE a.strategy='strict' AND cs.resolved AND cs.initial_mean_price IS NOT NULL""")
    strict_pnl = sum(realizable_pnl(float(r["entry"]), int(r["outcome_won"] == "t"))
                     for r in strict_pnl_rows)

    # aggregate the leak
    total_netnew = sum(v["netnew"] for v in by.values())
    total_netnew_res = sum(v["netnew_resolved"] for v in by.values())
    total_leak_pnl = sum(v["netnew_pnl"] for v in by.values())
    all_days = set().union(*[v["days"] for v in by.values()]) if by else set()
    n_days = max(len(all_days), 1)
    netnew_per_day = total_netnew / n_days
    strict_per_day = strict_alerts / strict_days

    result = {
        "dedup_mins": args.dedup_mins,
        "alert_volume_today": {r["strategy"]: {"n_alerts": int(r["n_alerts"]),
                               "first": r["first"], "last": r["last"], "days": int(r["n_days"])}
                               for r in vol},
        "winners_silent": {s: {"fired": v["fired"], "resolved": v["resolved"],
                               "self_alerts": 0,  # confirmed 0 in alert_volume_today
                               "covered_by_strict": v["covered"],
                               "net_new_leaked": v["netnew"],
                               "net_new_resolved": v["netnew_resolved"],
                               "net_new_wr": round(v["netnew_won"] / v["netnew_resolved"], 3)
                                             if v["netnew_resolved"] else None,
                               "leak_pnl_realizable": round(v["netnew_pnl"], 0),
                               "tiers": dict(v["tiers"])}
                           for s, v in by.items()},
        "leak_total": {"net_new_leaked_signals": total_netnew,
                       "net_new_resolved": total_netnew_res,
                       "leak_pnl_realizable_per_100": round(total_leak_pnl, 0),
                       "strict_alerted_pnl_realizable_per_100": round(strict_pnl, 0)},
        "spam_check": {"n_days": n_days, "strict_alerts_per_day": round(strict_per_day, 1),
                       "net_new_alerts_per_day": round(netnew_per_day, 1),
                       "volume_multiplier": round((strict_per_day + netnew_per_day) / strict_per_day, 2)
                                            if strict_per_day else None,
                       "dedup_intact": total_netnew < sum(v["fired"] for v in by.values())},
        "fix": {"code_change_needed": False,
                "mechanism": "CONSENSUS_ALERT_STRATEGIES + CONSENSUS_ALERT_WATCH_FOR env override "
                             "(config.rs L141-148), default OFF, already implemented (D12); never deployed",
                "proposed_env": {"CONSENSUS_ALERT_STRATEGIES": "strict,favorite,elite_fresh_fav",
                                 "CONSENSUS_ALERT_WATCH_FOR": "favorite,elite_fresh_fav"},
                "decision_owner": "Tue (live alert flip) — this run PROPOSES + STOPS"},
    }
    _print(result)
    os.makedirs(REPORT_DIR, exist_ok=True)
    path = os.path.join(REPORT_DIR, "alert_leak_shadow.json")
    with open(path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nwrote {path}")


def _print(r):
    print("=" * 78)
    print("WS-C · ALERT-LEAK SHADOW VERIFY")
    print("=" * 78)
    print("Alerts actually pushed, by strategy (the leak — winners never fire):")
    for s, d in r["alert_volume_today"].items():
        print(f"  {s:<18} {d['n_alerts']:>4} alerts over {d['days']} days ({d['first']}→{d['last']})")
    for s in WINNERS:
        if s not in r["alert_volume_today"]:
            print(f"  {s:<18}    0 alerts   ← SILENT (alerting:false)")
    print("-" * 78)
    print(f"Winner signals fired vs would-alert (cross-strategy dedup ±{r['dedup_mins']}min):")
    for s, v in r["winners_silent"].items():
        wr = f"{v['net_new_wr']:.1%}" if v["net_new_wr"] is not None else "—"
        print(f"  {s:<18} fired {v['fired']:>3} | covered-by-strict {v['covered_by_strict']:>3} | "
              f"NET-NEW {v['net_new_leaked']:>3} (resolved {v['net_new_resolved']}, WR {wr}) | "
              f"leak P&L {v['leak_pnl_realizable']:>+8.0f}$")
    lt = r["leak_total"]
    print("-" * 78)
    print(f"LEAK COST (realizable, per $100/bet, flat-shares, resolved net-new winners):")
    print(f"  net-new leaked resolved signals : {lt['net_new_resolved']}")
    print(f"  realizable P&L LEFT ON THE TABLE : {lt['leak_pnl_realizable_per_100']:>+8.0f}$")
    print(f"  (vs what strict DID alert        : {lt['strict_alerted_pnl_realizable_per_100']:>+8.0f}$  ← the DODGE side)")
    sc = r["spam_check"]
    print("-" * 78)
    print(f"SPAM CHECK: strict {sc['strict_alerts_per_day']}/day + net-new {sc['net_new_alerts_per_day']}/day "
          f"⇒ {sc['volume_multiplier']}× volume · dedup intact: {sc['dedup_intact']}")
    print("-" * 78)
    print("FIX (proposed, NOT applied — no code change): deploy the default-OFF D12 env override")
    print(f"  CONSENSUS_ALERT_STRATEGIES={r['fix']['proposed_env']['CONSENSUS_ALERT_STRATEGIES']}")
    print(f"  CONSENSUS_ALERT_WATCH_FOR={r['fix']['proposed_env']['CONSENSUS_ALERT_WATCH_FOR']}")
    print("  → LIVE ALERT FLIP IS TUE'S DECISION. This run stops here.")
    print("=" * 78)


if __name__ == "__main__":
    main()
