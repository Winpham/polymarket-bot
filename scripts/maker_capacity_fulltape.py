#!/usr/bin/env python3
"""
MAKER-CAPACITY (FULL-TAPE) — G2b. maker_capacity.py measured fill flow against trader_fills, which is
ONLY the ~489 followed sharks (co-directional with us) → near-zero fill BY CONSTRUCTION. This pulls
the FULL public per-market trade tape (data-api /trades?market=<cid>, ALL wallets, no auth) around each
signal's [fire, fire+5m] window and re-runs the SAME capacity curve on the REAL universe — the retail
counterparty a maker would actually fill against.

WHAT IT DOES / DOES NOT settle:
  ✅ FLOW CEILING — how much eligible counterparty flow EXISTS at our price (upper bound on fillable $).
     Sample probe already shows this is material (complement ≈ hundreds–few $k/signal) vs the tracked
     cohort's ~$3.5, so the "unfillable" read was a wrong-universe artifact.
  ❌ CAPTURE FRACTION — what share of that flow OUR resting bid actually wins is a QUEUE-POSITION
     question the historical tape cannot answer (we don't know our place in line). That needs forward
     live paper-quoting (G3). So numbers here are an UPPER BOUND on realized maker capacity.
  ❌ EDGE — this instrument measures FILLABILITY, not edge. mc.curve's raw_favorite_return (won/L−1) is
     base-rate dominated; the baselined signal edge lives in regime_net_edge (+0.28% LB ≈ 0).
  Note: DIRECT sell-favorite flow is ~zero even full-market (nobody sells the favorite into a consensus);
  all capacity is COMPLEMENT — the CLOB minting our favorite-buy against an underdog-buyer at price ≥ 1−L
  (a resting BUY-fav @L is a synthetic SELL-NO @1−L; a BUY-NO taker mints against it iff L+price ≥ 1).

AUDIT 2026-07-05 (3 independent reviewers) fixed the v1 blockers: complement rule was `≤1−L` (backwards —
counted deep-longshot buys that can't mint), `size` was treated as USD (it is SHARES → ×L for deployable
capital), transient-400 markets were silently booked as zero (now retried + excluded from denominator),
pagination-cap truncation is now an error not a false empty. v1's +4.8% LB was an artifact of these.

Resumable: raw window fills cached to reports/cache/fulltape/<signal_id>.json (re-runs are free; delete
to refetch). Polite ~0.25s/call, capped pages/market. Read-only, paper-only.
  ./maker_capacity_fulltape.py [--limit N] [--moneyline-only]   # pull + curve; writes JSON
  ./maker_capacity_fulltape.py --selftest                        # window-extract + reuse of mc.curve
"""

import argparse
import json
import os
import sys
import time
import urllib.request
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import regime_edge as reg
import maker_capacity as mc     # reuse curve(), _median, PG/q

TRADES_URL = "https://data-api.polymarket.com/trades?market={cid}&limit=500&offset={off}"
WINDOW_S = mc.WINDOW_S
MAX_PAGES = 20
SLEEP = 0.25
CACHE_DIR = os.path.join(reg.REPORT_DIR, "cache", "fulltape")
REPORT = os.path.join(reg.REPORT_DIR, "maker_capacity_fulltape.json")


def _signals(moneyline_only, limit):
    filt = "AND slug NOT ILIKE '%-total-%' AND slug NOT ILIKE '%exact-score%'" if moneyline_only else ""
    lim = f"LIMIT {int(limit)}" if limit else ""
    return mc.q(f"""
      SELECT id, condition_id AS cid, extract(epoch FROM first_detected_at)::bigint AS fire,
             initial_mean_price AS anchor, outcome_index AS fidx, outcome_won::int AS won,
             date(first_detected_at)::text AS day
      FROM consensus_signals
      WHERE strategy='favorite' AND resolved AND initial_mean_price IS NOT NULL AND condition_id IS NOT NULL
      {filt}
      ORDER BY first_detected_at DESC {lim}
    """)


def _get(url, tries=4):
    """GET with linear backoff — the data-api 400s observed in the first backfill were TRANSIENT
    (rate-limit), not delistings (audit D3). Retry so they don't get silently booked as zero-flow."""
    last = None
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.load(r)
        except Exception as e:
            last = e
            time.sleep(0.6 * (k + 1))
    raise last


def _fetch_window(cid, fire):
    """Full-market trades in [fire, fire+WINDOW_S]. Tape is newest-first; page by offset until past the
    window start. RAISES on pagination-cap truncation (audit D4) so a busy market is flagged as an
    ERROR, never silently booked as an empty window. size is SHARES (converted downstream)."""
    lo, hi = fire, fire + WINDOW_S
    win, off = [], 0
    for _ in range(MAX_PAGES):
        batch = _get(TRADES_URL.format(cid=cid, off=off))
        if not batch:
            return win                         # exhausted the tape → complete (dormant/short markets ok)
        for t in batch:
            ts = int(t["timestamp"])
            if lo <= ts <= hi:
                win.append({"ts": ts, "side": t["side"], "oidx": int(t["outcomeIndex"]),
                            "price": float(t["price"]), "size": float(t["size"])})
        if min(int(t["timestamp"]) for t in batch) < lo:   # paged past the window start → complete
            return win
        off += 500
        time.sleep(SLEEP)
    raise RuntimeError(f"pagination cap (MAX_PAGES={MAX_PAGES}) hit before reaching window — incomplete")


def _cached_window(sig):
    """Cache ONLY successful pulls. Fetch errors/truncation propagate (uncached → retried next run),
    so they are never confused with a genuinely empty window."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"{sig['id']}.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    win = _fetch_window(sig["cid"], int(sig["fire"]))
    with open(path, "w") as f:
        json.dump(win, f)
    time.sleep(SLEEP)
    return win


def _elig_rows(sig, win):
    """Eligible maker-fill rows (mc.curve schema). data-api `size` is SHARES (audit D1); DEPLOYABLE
    MAKER CAPITAL = shares × L (we buy `size` favorite shares at our bid L). complement mints against
    a resting BUY-fav @L iff underdog price ≥ 1−L (audit D2 — was `≤`, provably backwards)."""
    L, fav = float(sig["anchor"]), int(sig["fidx"])
    rows = []
    for t in sorted(win, key=lambda x: x["ts"]):
        direct = (t["oidx"] == fav and t["side"] == "SELL" and t["price"] <= L)
        comp = (t["oidx"] != fav and t["side"] == "BUY" and t["price"] >= 1 - L)
        if direct or comp:
            rows.append({"id": sig["id"], "anchor": sig["anchor"], "won": sig["won"], "day": sig["day"],
                         "secs": str(t["ts"] - int(sig["fire"])), "size_usd": str(t["size"] * L),
                         "kind": "direct" if direct else "complement"})
    return rows


def run(moneyline_only, limit):
    sigs = _signals(moneyline_only, limit)
    print(f"FULL-TAPE pull · {len(sigs)} resolved favorites"
          f"{' (moneyline-only)' if moneyline_only else ''} · window {WINDOW_S}s · cache {CACHE_DIR}")
    meta, elig = [], []
    n_measured = n_empty = n_error = 0
    errors = []
    for i, s in enumerate(sigs):
        try:
            win = _cached_window(s)
        except Exception as e:
            n_error += 1
            errors.append(str(s["id"]))
            continue                          # EXCLUDE from denominator — never a false zero (audit D3)
        n_measured += 1
        if not win:
            n_empty += 1
        meta.append({"id": s["id"], "anchor": s["anchor"], "won": s["won"], "day": s["day"]})
        elig += _elig_rows(s, win)
        if (i + 1) % 25 == 0:
            print(f"  … {i+1}/{len(sigs)} ({n_measured} measured / {n_error} errored, {len(elig)} eligible rows)")
    if errors:
        print(f"  ! {n_error} signals excluded (fetch error/truncation after retries): {errors[:8]}"
              f"{'…' if len(errors) > 8 else ''}")
    res = {"meta": {"universe": "FULL public tape (all wallets, data-api /trades)",
                    "n_requested": len(sigs), "n_measured": n_measured, "n_empty_window": n_empty,
                    "n_excluded_fetch_error": n_error, "window_s": WINDOW_S, "size_caps": mc.SIZE_CAPS,
                    "size_unit_fix": "data-api size=SHARES; eligible = shares×L (deployable maker capital)",
                    "complement_rule": "underdog BUY price ≥ 1−L (mint); direct = fav SELL ≤ L",
                    "bound": "FLOW CEILING, queue capture=100% (UPPER bound); capture fraction needs G3",
                    "not_edge": "raw_favorite_return is base-rate, NOT edge; baselined edge = regime_net_edge",
                    "COVERAGE_BIAS": "the n_excluded markets are NOT random — they are the BUSIEST "
                            "(round-2 audit: median ~551 in-window fills vs ~184 covered; whole top-volume "
                            "tail excluded). data-api /trades caps offset at 3000 and IGNORES all time "
                            "filters, so a busy market's days-deep window is UNREACHABLE. Fillable flow "
                            "scales with volume ⇒ these numbers (fillable %, $/signal) are a DOWNWARD-"
                            "BIASED LOWER BOUND; true fillability is higher. Busy-market capacity is only "
                            "measurable FORWARD (G3), which polls at fire (offset 0) and bypasses the cap."},
           "direct_only": mc.curve(meta, elig, include_complement=False),
           "direct_plus_complement": mc.curve(meta, elig, include_complement=True)}
    os.makedirs(reg.REPORT_DIR, exist_ok=True)
    with open(REPORT, "w") as f:
        json.dump(res, f, indent=1)
    _print(res)
    print(f"\nartifact → reports/maker_capacity_fulltape.json")
    return res


def _f(x, s="+.2%"):
    return "  n/a" if x is None or (isinstance(x, float) and x != x) else format(x, s)


def _print(res):
    m = res["meta"]
    print("\n⚠ FLOW CEILING (queue capture=100%, UPPER bound): tape shows flow that EXISTS at our price;")
    print("  realized CAPTURE fraction (queue) needs forward G3. raw return is base-rate, NOT edge.")
    print(f"  coverage: {m['n_measured']} measured / {m['n_excluded_fetch_error']} excluded of "
          f"{m['n_requested']} requested; {m['n_empty_window']} measured-empty.")
    print("  ⚠ excluded = the BUSIEST markets (offset cap 3000, no time filter → deep windows unreachable);")
    print("    fillability scales with volume ⇒ these numbers are a DOWNWARD-BIASED lower bound. Busy-market")
    print("    capacity needs FORWARD capture (G3). raw return is base-rate, NOT edge.\n")
    for label, key in (("DIRECT-ONLY", "direct_only"), ("DIRECT + COMPLEMENT (the real path)", "direct_plus_complement")):
        c = res[key]
        fs, rr = c["flow_selection"], c["raw_favorite_return"]
        print("=" * 92)
        print(f"FULL-TAPE · {label} · {c['n_signals']} measured · {c['n_with_eligible_flow']} fillable "
              f"· {c['n_day_clusters_filled']} day-clusters")
        print(f"  eligible deployable $/signal: median(all) ${c['median_eligible_usd_all']}  "
              f"mean(all) ${c['mean_eligible_usd_all']}  median(filled) ${c['median_eligible_usd_filled']}")
        print(f"  FLOW-SELECTION: wr(fillable) {_f(fs['wr_fillable'],'.1%')} vs wr(no-flow) "
              f"{_f(fs['wr_noflow'],'.1%')} → gap {_f(fs['gap_fillable_minus_noflow'],'+.1%')} "
              f"(neg = fillable resolve WORSE)")
        print(f"  RAW favorite return (NOT edge, size-invariant): {_f(rr['mean'])} · cluster-robust LB "
              f"{_f(rr['cluster_robust_lb'])}  [edge → regime_net_edge +0.28% LB]")
        print(f"  {'cap $':>7}{'any-fill%':>10}{'fill%(all)':>11}{'fill%(filled-med)':>18}{'depl/filled':>13}{'tot$':>10}")
        for r in c["fillability_by_cap"]:
            print(f"  {r['size_cap']:>7}{_f(r['pct_signals_any_fill'],'.1%'):>10}"
                  f"{_f(r['mean_fill_frac_all'],'.1%'):>11}{_f(r['median_fill_frac_filled'],'.1%'):>18}"
                  f"{r['mean_deployed_per_filled']:>13.1f}{r['total_deployed_window']:>10.0f}")


def _selftest():
    L = 0.80
    sig = {"id": "s1", "cid": "0xdead", "fire": 1000, "anchor": "0.80", "fidx": 1, "won": "1", "day": "2026-07-01"}
    # _elig_rows tags eligibility on an ALREADY-WINDOWED list. Fav = oidx 1 @ L=0.80 → 1−L=0.20.
    win = [{"ts": 1050, "side": "BUY", "oidx": 0, "price": 0.22, "size": 100.0},   # dog BUY ≥0.20 → complement ELIGIBLE (mint)
           {"ts": 1055, "side": "BUY", "oidx": 0, "price": 0.15, "size": 999.0},   # dog BUY <0.20 → NOT (can't mint vs our bid)
           {"ts": 1060, "side": "BUY", "oidx": 1, "price": 0.81, "size": 500.0},   # our side (taker buy fav) — NOT eligible
           {"ts": 1070, "side": "SELL", "oidx": 1, "price": 0.79, "size": 30.0}]   # direct sell-fav ≤0.80 — ELIGIBLE
    rows = _elig_rows(sig, win)
    kinds = sorted(r["kind"] for r in rows)
    ok = kinds == ["complement", "direct"] and len(rows) == 2
    print(f"  [{'ok' if ok else 'FAIL'}] complement uses ≥1−L (mint): {kinds} (cheap-dog & our-side dropped)")
    # units: complement row size_usd = shares×L = 100×0.80 = 80; direct = 30×0.80 = 24
    comp = next(r for r in rows if r["kind"] == "complement")
    ok2 = abs(float(comp["size_usd"]) - 80.0) < 1e-9
    print(f"  [{'ok' if ok2 else 'FAIL'}] units: 100 shares × L(0.80) = ${comp['size_usd']} deployable (not $100)")
    meta = [{"id": "s1", "anchor": "0.80", "won": "1", "day": "2026-07-01"}]
    c = mc.curve(meta, rows, include_complement=True)
    ok3 = c["n_with_eligible_flow"] == 1 and c["fillability_by_cap"][0]["total_deployed_window"] > 0
    print(f"  [{'ok' if ok3 else 'FAIL'}] mc.curve reuse → {c['n_with_eligible_flow']} fillable, deploys "
          f"${c['fillability_by_cap'][0]['total_deployed_window']} at ${c['fillability_by_cap'][0]['size_cap']} cap")
    ok_all = ok and ok2 and ok3
    print("selftest:", "PASS" if ok_all else "FAIL")
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--moneyline-only", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        _selftest()
    else:
        run(a.moneyline_only, a.limit)
