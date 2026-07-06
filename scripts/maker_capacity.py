#!/usr/bin/env python3
"""
MAKER-CAPACITY — G2. The net-edge work (fee_schedule_sensitivity, regime_net_edge) found the MAKER
path is the only config whose cluster-robust LB clears zero (+0.28% pooled). But that number assumes
you FILL your intended size. A maker only fills when someone crosses INTO the resting quote — and a
consensus-BUY signal fires precisely when everyone is buying the SAME side, so the counterparty flow
to fill a resting BUY on the favorite is thin. This instrument measures, from the REAL trade tape
(trader_fills, 2.3M fills), how much size actually fills and what edge survives AS A FUNCTION OF the
per-signal dollar cap S — i.e. the capacity ceiling the maker thesis lives or dies on.

FILL MODEL (resting maker BUY at the anchor L = initial_mean_price, δ=0, window T=5m from fire):
  a maker BUY at L is filled by opposing flow at a matchable price. Two eligible sources:
    DIRECT      SELL of the favorite token at price ≤ L                     (a taker sells to us)
    COMPLEMENT  BUY of the OTHER outcome at price ≥ 1−L                     (mints a set against us:
                a resting BUY-fav @L is a synthetic SELL-NO @1−L; a BUY-NO taker mints iff L+price≥1)
  eligible flow is consumed CHRONOLOGICALLY to fill up to S. size_usd = DEPLOYABLE MAKER CAPITAL.
  Reports DIRECT-only and DIRECT+COMPLEMENT. Output separates FILLABILITY from raw_favorite_return
  (which is base-rate, NOT edge — baselined edge lives in regime_net_edge, +0.28% LB).

⚠ DATA-UNIVERSE CAVEAT (read before trusting any number here): trader_fills is NOT the full market
  tape — it is the fills of the ~489 TRACKED/FOLLOWED sharp wallets only (489/489 ∈ followed_traders).
  Those wallets are CO-DIRECTIONAL with us (they ARE the consensus we copy), so measuring "who fills
  our resting bid" against THEM is near-empty BY CONSTRUCTION. These numbers are therefore a LOWER
  BOUND on true maker fill capacity and CANNOT establish that the market lacks counterparty flow — the
  natural maker counterparty (retail/uninformed sellers) is absent from this dataset entirely. This
  instrument RESOLVES one thing (you cannot fill by trading against the tracked sharps — a dead end)
  and CANNOT resolve the real question (full-market maker fill rate), which needs the full public
  per-market trade tape or forward live paper-quoting (G3). The adverse-selection gap here is on a
  sharp-only (maximally informed) universe and thus OVERSTATES true adverse selection.

PER SIZE CAP S, over resolved favorites, day-clustered:
  fill_frac(S)   = filled/S, mean AND median (median is the reliability read — the mean is carried by
                   a thin top decile of signals).
  deployed(S)    = mean filled $/signal (and total book $/window).
  adverse(S)     = size-weighted win-rate of the FILLED flow vs the base signal win-rate (a maker fills
                   preferentially when the market moves against the signal → filled win-rate < base).
  net_ret(S)     = maker return per DEPLOYED $ = won/L − 1 (maker fills at L; no spread, no fee, rebate
                   UNMODELED upside), fill-weighted, with a day-clustered small-cluster-t LB.
  ceiling S*     = largest S whose net_ret LB > 0 AND median fill_frac ≥ 0.5 (deployable AND reliable).

Read-only, paper-only, promotes nothing.
  ./maker_capacity.py             # capacity curve + ceiling; writes reports/maker_capacity.json
  ./maker_capacity.py --selftest  # thin one-sided flow → fill collapses with S; adverse flow lowers wr
"""

import csv
import io
import json
import math
import os
import subprocess
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import effective_n as en          # cluster_robust()
import regime_edge as reg         # lb_small_cluster (small-cluster t), FOLLOWER_TAX, REPORT_DIR

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q", "-v", "ON_ERROR_STOP=1"]
WINDOW_S = 300
SIZE_CAPS = [10, 25, 50, 100, 250, 1000]
REPORT = os.path.join(reg.REPORT_DIR, "maker_capacity.json")


def q(sql):
    out = subprocess.run(PG + ["-f", "-"], input=sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    return list(csv.DictReader(io.StringIO(out.stdout)))


def fetch():
    """One row per eligible maker-fill opportunity, ordered by (signal, time). `kind` = direct|complement."""
    return q(f"""
      WITH fav AS (
        SELECT id, condition_id, outcome_index AS fidx, first_detected_at AS t0,
               initial_mean_price AS anchor, outcome_won::int AS won, date(first_detected_at)::text AS day
        FROM consensus_signals
        WHERE strategy='favorite' AND resolved AND initial_mean_price IS NOT NULL
      )
      SELECT fav.id, fav.anchor, fav.won, fav.day,
             extract(epoch FROM (f.ts - fav.t0)) AS secs,
             f.size_usd,
             CASE WHEN f.outcome_index=fav.fidx THEN 'direct' ELSE 'complement' END AS kind
      FROM fav JOIN trader_fills f
        ON f.condition_id=fav.condition_id
       AND f.ts BETWEEN fav.t0 AND fav.t0 + interval '{WINDOW_S} seconds'
      WHERE (f.outcome_index=fav.fidx  AND f.side='SELL' AND f.price <= fav.anchor)
         OR (f.outcome_index<>fav.fidx AND f.side='BUY'  AND f.price >= 1-fav.anchor)
      ORDER BY fav.id, secs
    """)


def signals_meta():
    """Every resolved favorite (even those with zero eligible flow — they count as fill 0)."""
    return q("""
      SELECT id, initial_mean_price AS anchor, outcome_won::int AS won, date(first_detected_at)::text AS day
      FROM consensus_signals
      WHERE strategy='favorite' AND resolved AND initial_mean_price IS NOT NULL
    """)


def _by_signal(rows, include_complement):
    """{id: {'L','won','d','flow':[(size,)... chronological]}} of eligible fills for the chosen source set."""
    sig = defaultdict(lambda: {"flow": []})
    for r in rows:
        if not include_complement and r["kind"] != "direct":
            continue
        s = sig[r["id"]]
        s["L"], s["won"], s["d"] = float(r["anchor"]), int(r["won"]), r["day"]
        s["flow"].append(float(r["size_usd"]))
    return sig


def _consume(flow, cap):
    """Fill chronologically up to cap; return filled $ (the flow list is already time-ordered)."""
    filled = 0.0
    for sz in flow:
        if filled >= cap:
            break
        filled += min(sz, cap - filled)
    return filled


def _lb(series, cl):
    if not series:
        return None, None
    cr = en.cluster_robust(series, cl)
    mean = cr["theta"] if cr else float(sum(series.values()) / len(series))
    G = cr["G"] if cr else len(set(cl.values()))
    return mean, reg.lb_small_cluster(mean, cr["se_CR"] if cr else None, G)


def _median(xs):
    if not xs:
        return float("nan")
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def curve(meta, elig, include_complement):
    """Separates FILLABILITY (the instrument's real job) from the RAW favorite return (which is NOT
    edge — see audit 2026-07-05). `elig` size_usd = DEPLOYABLE MAKER CAPITAL (shares×L), dollars."""
    sig = _by_signal(elig, include_complement)
    ids = [m["id"] for m in meta]
    L = {m["id"]: float(m["anchor"]) for m in meta}
    won = {m["id"]: int(m["won"]) for m in meta}
    day = {m["id"]: m["day"] for m in meta}
    total_eligible = {i: sum(sig[i]["flow"]) if i in sig else 0.0 for i in ids}
    flow_ids = [i for i in ids if total_eligible[i] > 0]      # the fillable set (cap-invariant)
    noflow_ids = [i for i in ids if total_eligible[i] <= 0]

    # ---- FILLABILITY per size cap (coverage + fraction; NO per-cap edge — that was vacuous) ----
    per_cap = []
    for S in SIZE_CAPS:
        fills = {i: _consume(sig[i]["flow"], S) if i in sig else 0.0 for i in ids}
        fr_all = [fills[i] / S for i in ids]
        fr_filled = [fills[i] / S for i in flow_ids]
        deployed = sum(fills.values())
        per_cap.append({
            "size_cap": S,
            "pct_signals_any_fill": round(len(flow_ids) / len(ids), 4) if ids else None,
            "mean_fill_frac_all": round(sum(fr_all) / len(ids), 4) if ids else None,
            "median_fill_frac_filled": round(_median(fr_filled), 4) if fr_filled else 0.0,
            "mean_deployed_per_filled": round(deployed / len(flow_ids), 2) if flow_ids else 0.0,
            "total_deployed_window": round(deployed, 2),
        })

    # ---- FLOW-SELECTION (survivorship): do fillable signals resolve WORSE than no-flow ones? ----
    def wr(g):
        return (sum(won[i] for i in g) / len(g)) if g else float("nan")
    wr_all, wr_flow, wr_noflow = wr(ids), wr(flow_ids), wr(noflow_ids)

    # ---- RAW favorite return, size-INVARIANT, over the fillable set. NOT edge: won/L−1 is dominated
    #      by the favorite base rate; a blind favorite buyer earns the same. Baselined edge lives in
    #      regime_net_edge (+0.28% LB). Same (unweighted) estimator for point AND cluster-robust LB. ----
    ret = {i: (won[i] / L[i] - 1.0) for i in flow_ids}
    cl = {i: day[i] for i in flow_ids}
    raw_mean, raw_lb = _lb(ret, cl)

    return {
        "n_signals": len(ids), "n_with_eligible_flow": len(flow_ids),
        "n_day_clusters_filled": len(set(cl.values())) if cl else 0,
        "median_eligible_usd_all": round(_median([total_eligible[i] for i in ids]), 2),
        "mean_eligible_usd_all": round(sum(total_eligible.values()) / len(ids), 2) if ids else None,
        "median_eligible_usd_filled": round(_median([total_eligible[i] for i in flow_ids]), 2) if flow_ids else 0.0,
        "fillability_by_cap": per_cap,
        "flow_selection": {
            "wr_all": round(wr_all, 4), "wr_fillable": round(wr_flow, 4), "wr_noflow": round(wr_noflow, 4),
            "gap_fillable_minus_noflow": (round(wr_flow - wr_noflow, 4) if flow_ids and noflow_ids else None)},
        "raw_favorite_return": {
            "note": "won/L−1 over fillable signals; BASE-RATE dominated, NOT edge. Baselined edge = "
                    "regime_net_edge maker LB (+0.28%). Size-invariant.",
            "mean": None if raw_mean is None else round(raw_mean, 4),
            "cluster_robust_lb": None if raw_lb is None else round(raw_lb, 4)},
    }


def run():
    meta, elig = signals_meta(), fetch()
    res = {"meta": {"window_s": WINDOW_S, "size_caps": SIZE_CAPS, "delta": 0.0,
                    "note": "maker BUY @anchor; direct=sell-fav≤L, complement=buy-dog≥1−L (mint); "
                            "chronological fill; rebate UNMODELED; queue capture=100% (UPPER bound)",
                    "universe_caveat": "trader_fills = 489 TRACKED sharp wallets only (489/489 ∈ "
                            "followed_traders), CO-DIRECTIONAL with us. LOWER BOUND on true fill "
                            "capacity; retail counterparty absent. Resolves 'can't fill vs the sharks' "
                            "(yes, dead end); does NOT resolve full-market maker fill rate (needs full "
                            "public trade tape or forward live quoting). Adverse gap overstated."},
           "direct_only": curve(meta, elig, include_complement=False),
           "direct_plus_complement": curve(meta, elig, include_complement=True)}
    os.makedirs(reg.REPORT_DIR, exist_ok=True)
    with open(REPORT, "w") as f:
        json.dump(res, f, indent=1)
    _print(res)
    print(f"\nartifact → reports/maker_capacity.json")
    return res


def _f(x, s="+.2%"):
    return "  n/a" if x is None or (isinstance(x, float) and x != x) else format(x, s)


def _print(res):
    print("⚠ UNIVERSE: trader_fills = 489 TRACKED sharp wallets (co-directional). LOWER BOUND on fill")
    print("  capacity; retail counterparty absent → use maker_capacity_fulltape.py for the real universe.")
    print("⚠ raw_favorite_return is NOT edge (base-rate dominated); baselined edge = regime_net_edge.\n")
    for label, key in (("DIRECT-ONLY", "direct_only"), ("DIRECT + COMPLEMENT", "direct_plus_complement")):
        c = res[key]
        fs, rr = c["flow_selection"], c["raw_favorite_return"]
        print("=" * 92)
        print(f"MAKER-CAPACITY · {label} · {c['n_signals']} favorites · {c['n_with_eligible_flow']} fillable "
              f"· {c['n_day_clusters_filled']} day-clusters")
        print(f"  eligible deployable $/signal: median(all) ${c['median_eligible_usd_all']}  "
              f"mean(all) ${c['mean_eligible_usd_all']}  median(filled) ${c['median_eligible_usd_filled']}")
        print(f"  FLOW-SELECTION: wr(fillable) {_f(fs['wr_fillable'],'.1%')} vs wr(no-flow) "
              f"{_f(fs['wr_noflow'],'.1%')}  → gap {_f(fs['gap_fillable_minus_noflow'],'+.1%')} "
              f"(negative = fillable signals resolve WORSE)")
        print(f"  RAW favorite return (size-invariant, NOT edge): {_f(rr['mean'])}  "
              f"cluster-robust LB {_f(rr['cluster_robust_lb'])}")
        print("-" * 92)
        print(f"  {'cap $':>7}{'any-fill%':>10}{'fill%(all)':>11}{'fill%(filled-med)':>18}{'depl/filled':>13}{'tot$':>10}")
        for r in c["fillability_by_cap"]:
            print(f"  {r['size_cap']:>7}{_f(r['pct_signals_any_fill'],'.1%'):>10}"
                  f"{_f(r['mean_fill_frac_all'],'.1%'):>11}{_f(r['median_fill_frac_filled'],'.1%'):>18}"
                  f"{r['mean_deployed_per_filled']:>13.1f}{r['total_deployed_window']:>10.0f}")


# --------------------------------------------------------------------------------------------
def _selftest():
    ok = True
    # 4 signals / 2 days; 'a' (win) has $200 flow, 'c' (win) $50, 'b'&'d' none → fillable={a,c}, noflow={b,d}.
    meta = [{"id": "a", "anchor": "0.80", "won": "1", "day": "2026-07-01"},
            {"id": "b", "anchor": "0.80", "won": "0", "day": "2026-07-01"},
            {"id": "c", "anchor": "0.80", "won": "1", "day": "2026-07-02"},
            {"id": "d", "anchor": "0.80", "won": "0", "day": "2026-07-02"}]
    elig = [{"id": "a", "anchor": "0.80", "won": "1", "day": "2026-07-01", "secs": "10", "size_usd": "200", "kind": "direct"},
            {"id": "c", "anchor": "0.80", "won": "1", "day": "2026-07-02", "secs": "10", "size_usd": "50", "kind": "direct"}]
    c = curve(meta, elig, include_complement=False)
    c1 = c["n_with_eligible_flow"] == 2
    print(f"  [{'ok' if c1 else 'FAIL'}] fillable set = {c['n_with_eligible_flow']} (a,c)")
    # flow-selection: fillable {a,c} both won (100%), noflow {b,d} both lost (0%) → gap +100% (fixture)
    fs = c["flow_selection"]
    c2 = fs["wr_fillable"] == 1.0 and fs["wr_noflow"] == 0.0 and fs["gap_fillable_minus_noflow"] == 1.0
    ok = ok and c1 and c2
    print(f"  [{'ok' if c2 else 'FAIL'}] flow-selection gap {fs['gap_fillable_minus_noflow']:+.0%} "
          f"(fillable {fs['wr_fillable']:.0%} vs no-flow {fs['wr_noflow']:.0%})")
    # raw return over fillable (both won, L=0.8): won/L−1 = 0.25 each → mean 0.25
    rr = c["raw_favorite_return"]
    c3 = abs(rr["mean"] - 0.25) < 1e-9
    ok = ok and c3
    print(f"  [{'ok' if c3 else 'FAIL'}] raw favorite return mean {rr['mean']:+.2f} (won/L−1=0.25; NOT edge)")
    # per-cap: at $100 cap 'a' fills $100 (of 200) and 'c' fills $50 → median-over-filled fill-frac
    r100 = next(r for r in c["fillability_by_cap"] if r["size_cap"] == 100)
    c4 = r100["pct_signals_any_fill"] == 0.5 and r100["median_fill_frac_filled"] > 0
    ok = ok and c4
    print(f"  [{'ok' if c4 else 'FAIL'}] $100 cap: any-fill {r100['pct_signals_any_fill']:.0%}, "
          f"median-fill(filled) {r100['median_fill_frac_filled']:.0%}")
    # complement flow adds a fillable signal
    elig2 = elig + [{"id": "b", "anchor": "0.80", "won": "0", "day": "2026-07-01", "secs": "5", "size_usd": "50", "kind": "complement"}]
    c_cmp = curve(meta, elig2, include_complement=True)
    c5 = c_cmp["n_with_eligible_flow"] == 3
    ok = ok and c5
    print(f"  [{'ok' if c5 else 'FAIL'}] complement adds a fillable signal → {c_cmp['n_with_eligible_flow']}")
    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        run()
