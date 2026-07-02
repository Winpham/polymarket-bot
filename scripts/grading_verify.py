#!/usr/bin/env python3
"""
INDEPENDENT GRADING VERIFICATION (truth-audit attack D).

The bot grades resolutions from CLOB `/markets/{condition_id}` → `tokens[].winner`. This
instrument re-grades against a SECOND, independent source — the Gamma API's `outcomePrices`
(UMA-settled, a separate service) — and reports the mismatch rate.

  our grade    = (outcome_index, outcome_won) on consensus_signals   (per condition_id×outcome)
  gamma grade  = outcomePrices[outcome_index] == "1"  (the settled winner), when
                 umaResolutionStatus == 'resolved'
  mismatch     = our outcome_won != gamma grade  (both present)

Sample (D spec): ALL `favorite` + `elite_fresh_fav` rows (both winners oversampled), plus a
stratified win/loss × sport sample of the rest — well over the ≥50 floor. Grading is per
(condition_id, outcome_index), so we dedup to distinct graded outcomes. Coverage < 100% is
expected (Gamma does not index every sub-market — exact-score / more-markets); coverage is
REPORTED, never interpolated.

K1 (kill): mismatch > 1% of the verified sample ⇒ STOP, grading is a first-order bug, all
downstream numbers void until re-run. Each mismatch is printed with its condition_id.

Self-test:  ./grading_verify.py --self-test   (compare() over injected match/mismatch/multi/unresolved)
Live:       ./grading_verify.py               (hits Gamma; cost-zero, public, no auth)
"""

import csv
import io
import json
import subprocess
import sys
import urllib.parse
import urllib.request
from collections import defaultdict

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]
GAMMA = "https://gamma-api.polymarket.com/markets"
BATCH = 18
K1_BAR = 0.01

SPORT_SQL = """
SELECT condition_id, outcome_index, outcome_won,
       CASE WHEN slug ~ '^(atp|wta|itf)' THEN 'tennis'
            WHEN slug ~ '^fifwc' THEN 'soccer'
            WHEN slug ~ '^mlb' THEN 'mlb'
            WHEN slug ~ '^(btc|eth|sol|xrp|bnb|doge|bitcoin|ethereum)' THEN 'crypto'
            ELSE 'other' END AS sport,
       bool_or(strategy IN ('favorite','elite_fresh_fav')) AS is_winner,
       max(strategy) AS a_strategy
FROM consensus_signals WHERE resolved AND outcome_won IS NOT NULL
GROUP BY condition_id, outcome_index, outcome_won, sport
"""


def compare(our_index, our_won, outcomes, prices, status):
    """Pure grader. Returns 'match' | 'mismatch' | 'unverifiable' + the gamma winner index."""
    if status != "resolved" or not prices:
        return "unverifiable", None
    try:
        pr = [float(x) for x in prices]
    except (TypeError, ValueError):
        return "unverifiable", None
    if our_index >= len(pr):
        return "unverifiable", None
    # winner = the outcome priced at 1 (settled). Require a clean 1/0 settle.
    winners = [i for i, p in enumerate(pr) if p > 0.5]
    if len(winners) != 1:
        return "unverifiable", None  # void / 50-50 / multi — not a clean binary settle
    gamma_won = (winners[0] == our_index)
    return ("match" if gamma_won == bool(our_won) else "mismatch"), winners[0]


def fetch_rows():
    out = subprocess.run(PG + ["-c", SPORT_SQL.replace("\n", " ")], capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    return list(csv.DictReader(io.StringIO(out.stdout)))


def gamma_lookup(cids):
    """Batch-fetch resolved markets by condition_id (repeated params). Returns {cid: market}."""
    res = {}
    for i in range(0, len(cids), BATCH):
        chunk = cids[i:i + BATCH]
        q = "closed=true&" + "&".join("condition_ids=" + urllib.parse.quote(c) for c in chunk)
        try:
            req = urllib.request.Request(f"{GAMMA}?{q}", headers={"User-Agent": "curl/8.4"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.load(r)
        except Exception as e:  # noqa: BLE001 — network best-effort; uncovered cids stay unverifiable
            print(f"  (gamma batch {i//BATCH} failed: {e})", file=sys.stderr)
            continue
        for m in data:
            cid = m.get("conditionId")
            if cid:
                res[cid.lower()] = m
    return res


def build_sample(rows):
    """All winner outcomes + a stratified win/loss×sport sample of the rest (dedup by cid×index)."""
    seen = {}
    for r in rows:
        key = (r["condition_id"], r["outcome_index"])
        # prefer keeping a winner-tagged row for oversampling accounting
        if key not in seen or r["is_winner"] == "t":
            seen[key] = r
    winners = [r for r in seen.values() if r["is_winner"] == "t"]
    others = [r for r in seen.values() if r["is_winner"] != "t"]
    # stratified other-sample: up to 12 per (sport, won) cell — deterministic (sorted), no RNG
    strat = defaultdict(list)
    for r in sorted(others, key=lambda x: (x["sport"], x["outcome_won"], x["condition_id"], x["outcome_index"])):
        cell = (r["sport"], r["outcome_won"])
        if len(strat[cell]) < 12:
            strat[cell].append(r)
    sample = winners + [r for v in strat.values() for r in v]
    return sample, len(winners)


def run_live():
    rows = fetch_rows()
    sample, n_win = build_sample(rows)
    cids = sorted({r["condition_id"] for r in sample})
    print(f"grading verify · {len(sample)} distinct graded outcomes "
          f"({n_win} winner-strategy, {len(sample)-n_win} stratified other) · {len(cids)} markets → Gamma")
    gm = gamma_lookup(cids)

    tally = defaultdict(int)
    strat_tally = defaultdict(lambda: defaultdict(int))
    mismatches = []
    for r in sample:
        m = gm.get(r["condition_id"].lower())
        outcomes = json.loads(m["outcomes"]) if m and m.get("outcomes") else None
        prices = json.loads(m["outcomePrices"]) if m and m.get("outcomePrices") else None
        status = (m or {}).get("umaResolutionStatus")
        verdict, gwin = compare(int(r["outcome_index"]), r["outcome_won"] == "t", outcomes, prices, status)
        tally[verdict] += 1
        grp = "winner" if r["is_winner"] == "t" else "other"
        strat_tally[grp][verdict] += 1
        strat_tally[r["sport"]][verdict] += 1
        if verdict == "mismatch":
            mismatches.append((r, gwin, outcomes, prices))

    verified = tally["match"] + tally["mismatch"]
    print(f"\n  match={tally['match']}  mismatch={tally['mismatch']}  "
          f"unverifiable(no Gamma index / void)={tally['unverifiable']}")
    cov = verified / len(sample) if sample else 0
    print(f"  coverage = {verified}/{len(sample)} = {cov:.0%} (uncovered = sub-markets Gamma doesn't index; reported, not interpolated)")
    print(f"\n  {'group':<12} {'match':>6} {'mismatch':>9} {'unverif':>8}")
    for g in ("winner", "other", "tennis", "soccer", "mlb", "other", "crypto"):
        t = strat_tally.get(g)
        if t:
            print(f"  {g:<12} {t['match']:>6} {t['mismatch']:>9} {t['unverifiable']:>8}")

    rate = tally["mismatch"] / verified if verified else 0.0
    print(f"\n  mismatch rate = {tally['mismatch']}/{verified} = {rate:.2%}  (K1 bar {K1_BAR:.0%})")
    for r, gwin, oc, pr in mismatches:
        print(f"    MISMATCH cid={r['condition_id']} idx={r['outcome_index']} our_won={r['outcome_won']} "
              f"gamma_winner_idx={gwin} outcomes={oc} prices={pr}")
    if verified == 0:
        print("  ⚠ zero coverage — cannot clear K1; grading UNVERIFIED by this source")
        return 1
    if rate > K1_BAR:
        print("  ❌ K1 TRIGGERED: grading mismatch > 1% — STOP; downstream numbers void until fixed")
        return 2
    print("  ✅ K1 clear: grading independently confirmed within tolerance")
    return 0


# --- self-test -------------------------------------------------------------------------------
def _self_test():
    ok = True
    cases = [
        # (idx, won, outcomes, prices, status, expect)
        (0, True, ["Brazil", "Japan"], ["1", "0"], "resolved", "match"),
        (1, True, ["Brazil", "Japan"], ["1", "0"], "resolved", "mismatch"),   # we say idx1 won, gamma says idx0
        (0, False, ["Brazil", "Japan"], ["0", "1"], "resolved", "match"),      # we say idx0 lost, gamma idx1 won
        (2, True, ["0-0", "1-0", "2-1", "0-1"], ["0", "0", "1", "0"], "resolved", "match"),  # multi-outcome exact score
        (2, False, ["0-0", "1-0", "2-1", "0-1"], ["0", "0", "1", "0"], "resolved", "mismatch"),
        (0, True, ["A", "B"], None, "resolved", "unverifiable"),               # missing prices
        (0, True, ["A", "B"], ["0.5", "0.5"], "resolved", "unverifiable"),     # 50-50 / void
        (0, True, ["A", "B"], ["1", "0"], "posted", "unverifiable"),           # not resolved yet
    ]
    for idx, won, oc, pr, st, want in cases:
        got, _ = compare(idx, won, oc, pr, st)
        flag = "ok" if got == want else "FAIL"
        if got != want:
            ok = False
        print(f"  [{flag}] compare(idx={idx},won={won},prices={pr},status={st}) = {got} (want {want})")
    print("SELF-TEST", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(0 if _self_test() else 1)
    sys.exit(run_live())
