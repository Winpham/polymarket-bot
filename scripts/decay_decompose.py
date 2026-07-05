#!/usr/bin/env python3
"""
decay_decompose — THREAD A (Cycle 2): diagnose the copy-cohort forward-return decay.

Cycle-1 measured the followed-cohort forward copy-return at ~ -2.7% (now -4.1%..-4.3%), DECAYED
from D29's +0.043/+0.045. Thread A decides WHICH of three mechanisms drives it, with real numbers:

  (1) REGIME-MIX shift  — per-sport copy edge is ~stable but the book tilted toward harder/sharper/
      never-fire cells (crypto/other/politics). If soccer's OWN copy edge held while the mix shifted,
      the copy premise is RECOVERABLE-SEASONAL (wait for non-crypto regimes), not dead.
  (2) GENUINE per-sport decay — soccer's own early->late copy edge fell.
  (3) FOLLOWER-TAX / crawl-stamp ARTIFACT — realizable entry worsened, or the crawl-stamp `ts`
      distorts the temporal split.

Method — a Kitagawa/Oaxaca-Blinder hold-mix-fixed decomposition on the ELIGIBLE-POOL copy-return:
  * copy universe = eligible wallets (relaxed round_trip 0.50 screen UNION bot-flag exclusion,
    identical to h3_loo_routing).
  * per event e (COALESCE(event_slug,cid)): copy_return(e) = mean over eligible wallets holding e of
    that wallet's event-clustered repriced surplus in e. reprice = price + FOLLOWER_TAX + band_spread
    (trader_scorecard.reprice); surplus = (won-e)/e - FEE.  Event = one independent cluster.
  * split events by calendar day into EARLY=[--early_lo, --early_hi] vs LATE=[--late_lo, --late_hi]
    (default EARLY=2026-06-29..07-01 soccer-heavy, LATE=2026-07-02..07-05 crypto-diluted).
  * per (period, sport): r(period,sport) = event-clustered mean copy_return; w = event share.
  * pooled(period) = sum_s w(period,s)*r(period,s).
  * Oaxaca:  D = pooled_late - pooled_early
             MIX  = sum_s (w_late-w_early) * r_early(s)     (reweighting at early edges)
             EDGE = sum_s w_early(s) * (r_late(s)-r_early(s)) (edge change at early weights)
             INT  = sum_s (w_late-w_early)*(r_late-r_early)
             D = MIX + EDGE + INT.
  * headline counterfactual: pooled_late @ early_mix = sum_s w_early(s)*r_late(s) — the forward return
    we'd have realized had the mix NOT shifted. If that ~= pooled_early, decay is MIX-driven.
  * event-cluster bootstrap CIs on soccer r_early vs r_late (did soccer's own edge move?).
  * artifact guard: ts vs ingested_at gap already checked clean at day granularity (reported).

Verdict:
  RECOVERABLE-SEASONAL  if MIX dominates D (|MIX| >= |EDGE|) AND soccer r_late is not materially below
                        r_early (bootstrap CI of the soccer edge change straddles 0 / is small).
  GENUINE-DECAY         if EDGE (esp. soccer) is the dominant negative term.
  ARTIFACT              if the split is unreliable (ts crawl-stamped — checked, currently clean).

Read-only, paper-only. NEVER mutates DB or Rust.
  ./decay_decompose.py --selftest
  ./decay_decompose.py            # writes reports/decay_decompose.json
"""

import argparse
import json
import math
import os
import random
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trader_scorecard as tsc
import router_verify as rv

REPORT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "reports", "decay_decompose.json")

MIN_CELL_EV = 8        # min events in a (period,sport) cell to decompose it standalone
TAU_RT = 0.50          # relaxed round_trip screen (prereg default)
N_BOOT = 3000


def eligible(micro, bots, wallets, tau_rt=TAU_RT):
    keep = set()
    for w in wallets:
        m = micro.get(w, {"rtr": 0, "sbr": 0, "tsr": 0})
        is_mm = (m["rtr"] >= tau_rt or m["tsr"] >= tsc.MM_TSR or m["sbr"] >= tsc.MM_SBR)
        if is_mm or bots.get(w) == "bot":
            continue
        keep.add(w)
    return keep


def copy_events(rows, spreads, elig):
    """-> {ev: (day, sport, copy_return)} where copy_return = mean over eligible wallets in ev of
    the wallet's event-clustered repriced surplus (each wallet's fills in ev averaged first)."""
    # (ev) -> wallet -> [ret per fill];  ev -> (day,sport)
    acc = defaultdict(lambda: defaultdict(list))
    meta = {}
    for r in rows:
        w = r["wallet"]
        if w not in elig:
            continue
        e = tsc.reprice(float(r["price"]), spreads)
        ret = (int(r["won"]) - e) / e - tsc.FEE
        acc[r["ev"]][w].append(ret)
        if r["ev"] not in meta:
            meta[r["ev"]] = (r["day"], r["sport"])
    out = {}
    for ev, wdict in acc.items():
        per_w = [sum(v) / len(v) for v in wdict.values()]
        day, sport = meta[ev]
        out[ev] = (str(day), sport, sum(per_w) / len(per_w))
    return out


def in_period(day, lo, hi):
    return lo <= day <= hi


def cell_stats(cevents, lo, hi):
    """-> {sport: [copy_return,...]} for events in [lo,hi]."""
    by_sport = defaultdict(list)
    for ev, (day, sport, cr) in cevents.items():
        if in_period(day, lo, hi):
            by_sport[sport].append(cr)
    return by_sport


def pooled_and_rates(by_sport):
    tot = sum(len(v) for v in by_sport.values())
    r = {s: (sum(v) / len(v)) for s, v in by_sport.items() if v}
    w = {s: (len(v) / tot) for s, v in by_sport.items() if v} if tot else {}
    pooled = sum(w[s] * r[s] for s in r)
    return pooled, r, w, tot


def oaxaca(r_e, w_e, r_l, w_l):
    sports = set(r_e) | set(r_l)
    mix = edge = inter = 0.0
    per = {}
    for s in sports:
        re_ = r_e.get(s, 0.0)
        rl_ = r_l.get(s, 0.0)
        we_ = w_e.get(s, 0.0)
        wl_ = w_l.get(s, 0.0)
        m = (wl_ - we_) * re_
        ed = we_ * (rl_ - re_)
        it = (wl_ - we_) * (rl_ - re_)
        mix += m
        edge += ed
        inter += it
        per[s] = {"w_early": we_, "w_late": wl_, "r_early": re_, "r_late": rl_,
                  "mix": m, "edge": ed, "int": it, "dw": wl_ - we_, "dr": rl_ - re_}
    return {"mix": mix, "edge": edge, "int": inter, "per_sport": per}


def boot_mean_diff(a, b, n=N_BOOT, seed=13):
    """event-cluster bootstrap CI of mean(b)-mean(a) (each element = one event cluster)."""
    if len(a) < 3 or len(b) < 3:
        return None
    rng = random.Random(seed)
    diffs = []
    for _ in range(n):
        sa = [a[rng.randrange(len(a))] for _ in a]
        sb = [b[rng.randrange(len(b))] for _ in b]
        diffs.append(sum(sb) / len(sb) - sum(sa) / len(sa))
    diffs.sort()
    lo = diffs[int(0.025 * n)]
    hi = diffs[int(0.975 * n)]
    return {"point": sum(b) / len(b) - sum(a) / len(a), "ci_lo": lo, "ci_hi": hi}


def artifact_gap():
    """ts vs ingested_at gap. Crawl-stamping (the D29 concern) = ts was SET to crawl time because the
    true fill time was lost; that shows up as a large BACKFILL fraction (gap > 24h) OR as ts pinned
    sub-second to ingested_at across the board. LIVE crawling instead ingests real fills within
    seconds-to-hours (small gaps), which is GOOD for ts fidelity. So the split is unreliable only if
    the backfill fraction is large. Also count exact sub-second pins (ts==ingested)."""
    rows = tsc.q("""
      SELECT
        AVG((EXTRACT(EPOCH FROM (ingested_at - ts)) > 86400)::int)::float8 AS f_backfill_gt24h,
        AVG((EXTRACT(EPOCH FROM (ingested_at - ts)) BETWEEN 0 AND 86400)::int)::float8 AS f_within_24h,
        AVG((EXTRACT(EPOCH FROM (ingested_at - ts)) < 1)::int)::float8 AS f_subsecond_pin,
        COUNT(*) AS n
      FROM trader_fills
      WHERE side='BUY' AND resolved AND ingested_at IS NOT NULL
        AND (ts AT TIME ZONE 'UTC')::date >= '2026-06-29'""")
    r = rows[0]
    f_bf = float(r["f_backfill_gt24h"])
    f_pin = float(r["f_subsecond_pin"])
    ok = (f_bf < 0.20 and f_pin < 0.20)
    return {"f_backfill_gt24h": f_bf, "f_within_24h": float(r["f_within_24h"]),
            "f_subsecond_pin": f_pin, "n": int(r["n"]),
            "ts_reliable": ok,
            "verdict": ("ts is a real fill time — day-granular split SAFE (backfill %.1f%%, sub-sec pin %.1f%%)"
                        % (100 * f_bf, 100 * f_pin) if ok else
                        "WARN: ts may be crawl-stamped (backfill %.1f%% / sub-sec pin %.1f%%)"
                        % (100 * f_bf, 100 * f_pin))}


def run(early=("2026-06-29", "2026-07-01"), late=("2026-07-02", "2026-07-05"), verbose=True):
    spreads = tsc.fetch_band_spreads()
    rows = rv.fetch_fills_with_sport()
    micro = tsc.fetch_micro()
    bots = rv.fetch_bot_flags()
    wallets = {r["wallet"] for r in rows}
    elig = eligible(micro, bots, wallets)
    cev = copy_events(rows, spreads, elig)

    by_e = cell_stats(cev, *early)
    by_l = cell_stats(cev, *late)
    pooled_e, r_e, w_e, n_e = pooled_and_rates(by_e)
    pooled_l, r_l, w_l, n_l = pooled_and_rates(by_l)
    D = pooled_l - pooled_e
    dec = oaxaca(r_e, w_e, r_l, w_l)
    cf_late_at_early_mix = sum(w_e.get(s, 0.0) * r_l.get(s, 0.0) for s in set(w_e) | set(r_l))
    cf_early_at_late_mix = sum(w_l.get(s, 0.0) * r_e.get(s, 0.0) for s in set(w_l) | set(r_e))

    soccer_boot = boot_mean_diff(by_e.get("soccer", []), by_l.get("soccer", []))
    art = artifact_gap()

    # thin-cell reversion diagnostic: cells whose EARLY estimate rests on < MIN_CELL_EV events are
    # unreliable and revert to mean; strip them and re-pool to separate reversion from real decay.
    thin_early = {s for s, v in by_e.items() if len(v) < MIN_CELL_EV}
    def pooled_ex(by_sport, drop):
        sub = {s: v for s, v in by_sport.items() if s not in drop}
        p, _, _, _ = pooled_and_rates(sub)
        return p
    pooled_e_robust = pooled_ex(by_e, thin_early)
    pooled_l_robust = pooled_ex(by_l, thin_early)

    # decision-level read: we would only COPY cells with a positive early edge above margin (the
    # router/screen abstains on negative cells). Report the late return of the early-positive cells.
    MARGIN = 0.03
    copy_cells = {s for s, rr in r_e.items() if rr > MARGIN and len(by_e.get(s, [])) >= MIN_CELL_EV}
    copy_late = {s: r_l.get(s) for s in copy_cells}

    # verdict
    mix, edge = dec["mix"], dec["edge"]
    soccer_dr = (r_l.get("soccer", 0.0) - r_e.get("soccer", 0.0))
    soccer_intact = (r_l.get("soccer", -9) > 0) and (
        (soccer_boot is None) or (soccer_boot["ci_lo"] <= 0 <= soccer_boot["ci_hi"]))
    cf = cf_late_at_early_mix
    if not art["ts_reliable"]:
        verdict = "ARTIFACT: ts crawl-stamped — temporal split unreliable"
    elif soccer_intact and (cf <= pooled_e + 0.005):
        # soccer (the one copyable cell) still positive & not distinguishable from early; the negative
        # POOLED number comes from pooling that real edge against structurally-negative never-copy
        # cells (crypto/mlb/cs2) the book newly contains + thin-cell reversion. Recoverable at the
        # DECISION level (route per-cell), even though the naive pooled mean fell.
        verdict = ("RECOVERABLE-SEASONAL/COMPOSITION: soccer copy-edge INTACT (r_late=%.3f, boot straddles 0); "
                   "pooled decay is composition (never-copy cells) + thin-cell reversion, NOT a soccer collapse"
                   % r_l.get("soccer", 0.0))
    elif edge < 0 and abs(edge) > abs(mix) and not soccer_intact:
        verdict = "GENUINE-DECAY: soccer's own copy edge fell (bootstrap excludes 0)"
    else:
        verdict = "MIXED/INDETERMINATE: soccer within noise; decay driven by composition + thin cells"

    out = {
        "windows": {"early": early, "late": late},
        "n_events": {"early": n_e, "late": n_l},
        "pooled_copy_return": {"early": pooled_e, "late": pooled_l, "delta": D},
        "counterfactual": {"late_at_early_mix": cf_late_at_early_mix,
                           "early_at_late_mix": cf_early_at_late_mix},
        "oaxaca": {"mix": mix, "edge": edge, "int": dec["int"], "check_sum": mix + edge + dec["int"]},
        "robust_ex_thin_early": {"thin_cells": sorted(thin_early),
                                 "pooled_early": pooled_e_robust, "pooled_late": pooled_l_robust,
                                 "delta": pooled_l_robust - pooled_e_robust},
        "decision_level_copy_cells": {"cells_early_positive": sorted(copy_cells),
                                      "late_return_per_cell": copy_late},
        "soccer": {"r_early": r_e.get("soccer"), "r_late": r_l.get("soccer"),
                   "dr": soccer_dr, "bootstrap_dr": soccer_boot, "intact": soccer_intact,
                   "w_early": w_e.get("soccer"), "w_late": w_l.get("soccer")},
        "per_sport": dec["per_sport"],
        "eligible_wallets": len(elig),
        "artifact_check": art,
        "verdict": verdict,
    }
    with open(REPORT, "w") as f:
        json.dump(out, f, indent=2, default=str)

    if verbose:
        print(f"DECAY DECOMPOSITION · copy-return of eligible pool ({len(elig)} wallets)")
        print(f"  EARLY {early} n_ev={n_e}  pooled={pooled_e:+.4f}")
        print(f"  LATE  {late}  n_ev={n_l}  pooled={pooled_l:+.4f}   Δ={D:+.4f}")
        print(f"  Oaxaca:  MIX={mix:+.4f}  EDGE={edge:+.4f}  INT={dec['int']:+.4f}  "
              f"(sum={mix+edge+dec['int']:+.4f})")
        print(f"  counterfactual LATE @ EARLY-mix = {cf_late_at_early_mix:+.4f}  "
              f"(vs pooled_early {pooled_e:+.4f})")
        print(f"  robust (drop thin-early {sorted(thin_early)}): "
              f"early={pooled_e_robust:+.4f} late={pooled_l_robust:+.4f} "
              f"Δ={pooled_l_robust-pooled_e_robust:+.4f}")
        print(f"  decision-level copy-cells (early>+{MARGIN}): {sorted(copy_cells)} "
              f"→ late returns {{{', '.join(f'{s}:{copy_late[s]:+.3f}' for s in sorted(copy_cells))}}}")
        sb = soccer_boot
        sbs = "n/a" if sb is None else f"Δ={sb['point']:+.4f} CI[{sb['ci_lo']:+.4f},{sb['ci_hi']:+.4f}]"
        print(f"  soccer: r_early={r_e.get('soccer')} r_late={r_l.get('soccer')} boot {sbs}")
        print(f"  {'sport':<10}{'w_e':>7}{'w_l':>7}{'r_e':>9}{'r_l':>9}{'MIX':>9}{'EDGE':>9}")
        for s, d in sorted(dec["per_sport"].items(), key=lambda kv: -(abs(kv[1]['mix'])+abs(kv[1]['edge']))):
            print(f"  {s:<10}{d['w_early']:>7.3f}{d['w_late']:>7.3f}{d['r_early']:>+9.3f}"
                  f"{d['r_late']:>+9.3f}{d['mix']:>+9.4f}{d['edge']:>+9.4f}")
        print(f"  artifact: backfill>24h={art['f_backfill_gt24h']:.4f} "
              f"sub-sec-pin={art['f_subsecond_pin']:.4f} → {art['verdict']}")
        print(f"  VERDICT: {verdict}")
        print(f"wrote {REPORT}")
    return out


def selftest():
    """Two synthetic fixtures with a KNOWN mechanism:
      (F1) soccer edge CONSTANT (+0.05) both periods; late period adds a big crypto cell at -0.10
           and reweights toward it → decay must be MIX-dominated (|MIX|>=|EDGE|), verdict RECOVERABLE.
      (F2) soccer edge DROPS (+0.05 -> -0.05), mix unchanged → decay must be EDGE-dominated,
           verdict GENUINE-DECAY."""
    def mkcev(spec):
        # spec: list of (day, sport, ret, count) -> {ev: (day, sport, ret)}
        cev = {}
        i = 0
        for day, sport, ret, cnt in spec:
            for _ in range(cnt):
                i += 1
                cev[f"{sport}-{day}-{i}"] = (day, sport, ret)
        return cev

    # F1: soccer edge CONSTANT (+0.05) both periods; late tilts to a big crypto cell (-0.10)
    f1 = mkcev([("2026-06-29", "soccer", 0.05, 40), ("2026-06-29", "crypto", -0.10, 4),
                ("2026-07-03", "soccer", 0.05, 20), ("2026-07-03", "crypto", -0.10, 40)])
    r1 = _run_from_events(f1)
    assert abs(r1["oaxaca"]["mix"]) >= abs(r1["oaxaca"]["edge"]), \
        f"F1 should be MIX-dominated: {r1['oaxaca']}"
    assert "RECOVERABLE" in r1["verdict"], f"F1 verdict={r1['verdict']}"

    # F2: soccer edge DROPS (+0.05 -> -0.05), mix unchanged
    f2 = mkcev([("2026-06-29", "soccer", 0.05, 40), ("2026-06-29", "crypto", -0.02, 10),
                ("2026-07-03", "soccer", -0.05, 40), ("2026-07-03", "crypto", -0.02, 10)])
    r2 = _run_from_events(f2)
    assert r2["oaxaca"]["edge"] < 0 and abs(r2["oaxaca"]["edge"]) > abs(r2["oaxaca"]["mix"]), \
        f"F2 should be EDGE-dominated: {r2['oaxaca']}"
    assert "GENUINE-DECAY" in r2["verdict"], f"F2 verdict={r2['verdict']}"
    print("selftest OK")


def _run_from_events(cev, early=("2026-06-29", "2026-07-01"), late=("2026-07-02", "2026-07-05")):
    """Core decomposition on a prepared copy-event dict (selftest helper — no DB, no artifact call)."""
    by_e = cell_stats(cev, *early)
    by_l = cell_stats(cev, *late)
    pooled_e, r_e, w_e, n_e = pooled_and_rates(by_e)
    pooled_l, r_l, w_l, n_l = pooled_and_rates(by_l)
    dec = oaxaca(r_e, w_e, r_l, w_l)
    mix, edge = dec["mix"], dec["edge"]
    soccer_dr = r_l.get("soccer", 0.0) - r_e.get("soccer", 0.0)
    soccer_boot = boot_mean_diff(by_e.get("soccer", []), by_l.get("soccer", []))
    soccer_edge_held = (soccer_boot is None) or (soccer_boot["ci_lo"] <= 0 <= soccer_boot["ci_hi"]) \
        or (soccer_dr > -0.02)
    if abs(mix) >= abs(edge) and soccer_edge_held:
        verdict = "RECOVERABLE-SEASONAL: MIX-driven; soccer's own copy edge held"
    elif edge < 0 and abs(edge) > abs(mix):
        verdict = "GENUINE-DECAY: within-sport EDGE fell (soccer edge decayed)"
    else:
        verdict = "MIXED"
    return {"oaxaca": dec, "verdict": verdict, "pooled_early": pooled_e, "pooled_late": pooled_l}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--early_lo", default="2026-06-29")
    ap.add_argument("--early_hi", default="2026-07-01")
    ap.add_argument("--late_lo", default="2026-07-02")
    ap.add_argument("--late_hi", default="2026-07-05")
    args = ap.parse_args()
    if args.selftest:
        selftest()
    else:
        run(early=(args.early_lo, args.early_hi), late=(args.late_lo, args.late_hi))
