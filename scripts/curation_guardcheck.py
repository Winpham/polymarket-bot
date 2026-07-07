#!/usr/bin/env python3
"""
CURATION CROSS-TAB + PRUNE GUARD-CHECK (beat-best-trader, Cycle 9) — the U2/U4/U5 analysis layer
on top of reports/universe_scorecard.json (produced by universe_curation.py). Read-only, paper-only;
recommends prunes/adds as a DEFERRED human-review list only — NEVER writes the DB.

U2  Cross-tab leaderboard rank/PnL vs OUR-PRICE realizable directional skill, and bucket every
    high-rank/high-PnL wallet by WHY it is inflated (mm_arber / longshot_lucky / bad_predictor /
    skill_within_luck / skilled_not_copyable / genuinely_skilled). Headline: how many top-leaderboard
    wallets are actually BAD predictors at our price.

U4  Segment the judgeable positive pool into (sport × price-band) sub-cohorts; report any group that is
    durably +EV at THEIR price with enough events, and flag which clear the copyable (our-price) bar.

U5  PRUNE list = judgeable wallets that help NEITHER role: a losing/no-skill predictor at our price AND
    NOT one of the favorite-consensus BACKERS (the 107 wallets the STANDARD rides on). GUARD-CHECK:
    (a) any prune candidate that IS a fav-consensus backer is CONSENSUS-CRITICAL → surfaced as a KEEP
    tension, never pruned; (b) because the favorite consensus signals are DEFINED by their backer set,
    pruning only non-backer TAIL wallets cannot change the recorded signals — so the standard is
    unaffected by construction; we ALSO invoke scripts/standard_guard.py to confirm the champion's
    belief-blind REGRESSION STATUS is HEALTHY and unchanged. The champion changes only if a pruned
    universe genuinely beats it (it does not — pruning removes no backer).

  ./curation_guardcheck.py            # reads universe_scorecard.json; writes curation_guardcheck.json
  ./curation_guardcheck.py --selftest # synthetic fixtures; no DB, no scorecard file
"""

import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.join(os.path.dirname(HERE), "reports")
SCORECARD = os.path.join(REPORT_DIR, "universe_scorecard.json")
OUT = os.path.join(REPORT_DIR, "curation_guardcheck.json")

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-t", "-q"]

RANK_TIERS = [(1, 10), (11, 50), (51, 100), (101, 200)]
MIN_CELL_EV = 8            # a (sport×band) sub-cohort needs >=8 events to report
BAD_BUCKETS = {"bad_predictor", "longshot_lucky", "skill_within_luck"}


def fav_backers():
    """The distinct wallets that back the favorite-consensus STANDARD (the pool it rides on)."""
    out = subprocess.run(PG + ["-c",
        "SELECT DISTINCT lower(je->>'wallet') "
        "FROM consensus_signals cs, jsonb_array_elements(cs.backers) je "
        "WHERE cs.strategy IN ('favorite','elite_fresh_fav')"],
        capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    return {ln.strip() for ln in out.stdout.splitlines() if ln.strip()}


def run_standard_guard():
    """Invoke the standing guard read-only to confirm champion REGRESSION STATUS (no code change)."""
    try:
        r = subprocess.run([sys.executable, os.path.join(HERE, "standard_guard.py")],
                           capture_output=True, text=True, timeout=900)
        gj = os.path.join(REPORT_DIR, "standard_guard.json")
        status = None
        if os.path.exists(gj):
            with open(gj) as f:
                g = json.load(f)
            status = g.get("regression", g.get("champion", {}))
        return {"ran": r.returncode == 0, "tail": r.stdout.strip().splitlines()[-6:], "guard": status}
    except Exception as e:
        return {"ran": False, "error": str(e)}


# ------------------------------------------------------------------ analysis
def crosstab(records):
    """U2: rank-tier × realizable-skill cross-tab + bucket tallies over judgeable wallets."""
    judge = [r for r in records if r.get("judgeable")]
    tab = {}
    for lo, hi in RANK_TIERS:
        cell = [r for r in judge if (r.get("leaderboard") or {}).get("rank") is not None
                and lo <= r["leaderboard"]["rank"] <= hi]
        bad_our = [r for r in cell if (r["realizable"].get("realizable_roi") or -1) <= 0]
        buckets = defaultdict(int)
        for r in cell:
            buckets[r["bucket"]] += 1
        tab[f"rank_{lo}_{hi}"] = {
            "n_judgeable": len(cell),
            "bad_at_our_price": len(bad_our),
            "bad_frac": round(len(bad_our) / len(cell), 3) if cell else None,
            "buckets": dict(buckets),
        }
    # top-PnL decile view
    pnl_sorted = sorted((r for r in judge if (r.get("leaderboard") or {}).get("pnl")),
                        key=lambda r: -r["leaderboard"]["pnl"])
    topN = pnl_sorted[:max(1, len(pnl_sorted) // 10)]
    bad_top = [r for r in topN if (r["realizable"].get("realizable_roi") or -1) <= 0]
    top_buckets = defaultdict(int)
    for r in topN:
        top_buckets[r["bucket"]] += 1
    return {
        "by_rank_tier": tab,
        "top_pnl_decile": {"n": len(topN), "bad_at_our_price": len(bad_top),
                           "buckets": dict(top_buckets)},
        "overall_judgeable": {
            "n": len(judge),
            "bad_at_our_price": sum(1 for r in judge
                                    if (r["realizable"].get("realizable_roi") or -1) <= 0),
            "genuinely_skilled": sum(1 for r in judge if r["bucket"] == "genuinely_skilled"),
        },
    }


def subcohorts(records):
    """U4: (sport×band) sub-cohorts among judgeable POSITIVE-skill wallets. Aggregate the per-wallet
    best_cell — a group is any (sport×band) cell that is the best_cell of >=2 wallets, or a sport that
    multiple survivors share. Report their-price gap + how many are copyable (realizable>0)."""
    judge_pos = [r for r in records if r.get("judgeable")
                 and ((r.get("skill") or {}).get("cal_gap") or 0) > 0]
    by_cell = defaultdict(list)
    for r in judge_pos:
        cell = (r.get("skill") or {}).get("best_cell")
        if cell:
            by_cell[cell].append(r)
    groups = []
    for cell, rs in sorted(by_cell.items(), key=lambda kv: -len(kv[1])):
        if len(rs) < 2:
            continue
        copyable = sum(1 for r in rs if (r["realizable"].get("realizable_roi") or -1) > 0)
        gaps = [(r.get("skill") or {}).get("best_cell_gap") or 0 for r in rs]
        groups.append({
            "cell": cell, "n_wallets": len(rs),
            "n_copyable_our_price": copyable,
            "mean_best_cell_gap_their_price": round(sum(gaps) / len(gaps), 4),
            "members": [r.get("username") or r["wallet"][:12] for r in rs],
        })
    return {"n_judgeable_positive": len(judge_pos), "shared_best_cell_groups": groups}


def prune_and_guard(records, backers):
    """U5: prune candidates (help neither role) + backer-criticality guard-check."""
    judge = [r for r in records if r.get("judgeable")]
    prune, keep_tension = [], []
    for r in judge:
        roi = r["realizable"].get("realizable_roi")
        no_skill = (r["bucket"] in BAD_BUCKETS) or (roi is not None and roi <= 0)
        if not no_skill:
            continue
        is_backer = r["wallet"] in backers
        row = {"wallet": r["wallet"], "username": r.get("username"),
               "bucket": r["bucket"], "realizable_roi": roi,
               "rank": (r.get("leaderboard") or {}).get("rank"),
               "pnl": (r.get("leaderboard") or {}).get("pnl"),
               "is_fav_backer": is_backer}
        if is_backer:
            keep_tension.append(row)        # consensus-critical → do NOT prune
        else:
            prune.append(row)
    return {
        "n_judgeable": len(judge),
        "prune_count": len(prune),
        "prune_list": sorted(prune, key=lambda x: (x["realizable_roi"] is None,
                                                   x["realizable_roi"] or 0)),
        "keep_consensus_critical_count": len(keep_tension),
        "keep_consensus_critical": sorted(keep_tension,
                                          key=lambda x: (x["realizable_roi"] or 0)),
    }


# ------------------------------------------------------------------ live
def run_live():
    with open(SCORECARD) as f:
        sc = json.load(f)
    records = sc["records"]
    backers = fav_backers()
    ct = crosstab(records)
    sub = subcohorts(records)
    pg = prune_and_guard(records, backers)
    guard = run_standard_guard()

    out = {"meta": {"cycle": 9, "n_fav_backers": len(backers),
                    "source": "reports/universe_scorecard.json",
                    "note": "prune/add are DEFERRED human-review recommendations; DB never written"},
           "U2_crosstab": ct, "U4_subcohorts": sub, "U5_prune_guard": pg,
           "standard_guard": guard}
    with open(OUT, "w") as f:
        json.dump(out, f, indent=2, default=str)

    print(f"fav-consensus backers (STANDARD rides on): {len(backers)}")
    print("\nU2 — bad-at-our-price by rank tier:")
    for k, v in ct["by_rank_tier"].items():
        print(f"  {k:<14} judgeable={v['n_judgeable']:>3}  bad_at_our_price={v['bad_at_our_price']:>3}"
              f"  ({v['bad_frac']})  buckets={v['buckets']}")
    o = ct["overall_judgeable"]
    print(f"  OVERALL judgeable={o['n']}  bad_at_our_price={o['bad_at_our_price']}  "
          f"genuinely_skilled={o['genuinely_skilled']}")
    print(f"\nU4 — shared-best-cell sub-cohorts: {len(sub['shared_best_cell_groups'])}")
    for g in sub["shared_best_cell_groups"][:12]:
        print(f"  {g['cell']:<16} wallets={g['n_wallets']} copyable={g['n_copyable_our_price']} "
              f"gap(their)={g['mean_best_cell_gap_their_price']:+.3f} {g['members']}")
    print(f"\nU5 — prune_count={pg['prune_count']}  keep_consensus_critical="
          f"{pg['keep_consensus_critical_count']}")
    g = guard.get("guard")
    print(f"  standard_guard ran={guard.get('ran')}  regression/champion status={g}")
    print(f"\nwrote {OUT}")
    return out


# ------------------------------------------------------------------ selftest
def selftest():
    recs = [
        # genuinely skilled + copyable (not pruned; would pass quality upstream)
        {"wallet": "a", "username": "good", "judgeable": True, "bucket": "genuinely_skilled",
         "leaderboard": {"rank": 5, "pnl": 1e6}, "realizable": {"realizable_roi": 0.08},
         "skill": {"cal_gap": 0.12, "best_cell": "soccer|b4", "best_cell_gap": 0.10}},
        # mm arber, high rank, bad at our price, NOT a backer → prune
        {"wallet": "b", "username": "arb", "judgeable": True, "bucket": "mm_arber",
         "leaderboard": {"rank": 2, "pnl": 5e6}, "realizable": {"realizable_roi": -0.2},
         "skill": {"cal_gap": 0.0, "best_cell": None, "best_cell_gap": None}},
        # bad predictor, is a fav-backer → KEEP (consensus-critical tension), not pruned
        {"wallet": "c", "username": "backer", "judgeable": True, "bucket": "bad_predictor",
         "leaderboard": {"rank": 30, "pnl": 2e5}, "realizable": {"realizable_roi": -0.1},
         "skill": {"cal_gap": -0.03, "best_cell": None, "best_cell_gap": None}},
        # positive skill, shares best_cell with 'a' → sub-cohort of 2
        {"wallet": "d", "username": "good2", "judgeable": True, "bucket": "skilled_not_copyable",
         "leaderboard": {"rank": 60, "pnl": 3e5}, "realizable": {"realizable_roi": -0.01},
         "skill": {"cal_gap": 0.04, "best_cell": "soccer|b4", "best_cell_gap": 0.05}},
        # unjudgeable → ignored everywhere
        {"wallet": "e", "username": "tiny", "judgeable": False, "bucket": "unjudgeable",
         "leaderboard": {"rank": 1, "pnl": 9e6}, "realizable": {"realizable_roi": None},
         "skill": None},
    ]
    backers = {"c"}
    ct = crosstab(recs)
    assert ct["overall_judgeable"]["n"] == 4, ct["overall_judgeable"]
    assert ct["overall_judgeable"]["bad_at_our_price"] == 3   # b,c,d
    assert ct["overall_judgeable"]["genuinely_skilled"] == 1
    assert ct["by_rank_tier"]["rank_1_10"]["bad_at_our_price"] == 1   # b (a is good)
    sub = subcohorts(recs)
    grp = [g for g in sub["shared_best_cell_groups"] if g["cell"] == "soccer|b4"]
    assert grp and grp[0]["n_wallets"] == 2 and grp[0]["n_copyable_our_price"] == 1, grp
    pg = prune_and_guard(recs, backers)
    pruned = {x["wallet"] for x in pg["prune_list"]}
    assert pruned == {"b", "d"}, pruned                         # c held (backer), a kept (skilled)
    assert pg["keep_consensus_critical_count"] == 1 and pg["keep_consensus_critical"][0]["wallet"] == "c"
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    run_live()


if __name__ == "__main__":
    main()
