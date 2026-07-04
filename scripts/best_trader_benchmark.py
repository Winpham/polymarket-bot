#!/usr/bin/env python3
"""
BEST-TRADER BENCHMARK — "are we at least as profitable as the most profitable players?",
answered the only fair way (BEAT-THE-BEST-TRADER-RUN.md step 3, lean build).

A benchmark at the trader's OWN fill price is unbeatable-by-a-follower and therefore useless;
and the max of 400+ noisy point estimates is selection noise by construction. So per context
(overall + sport), over the trailing-365d favorite-band record:

  B_LB(c)    = max over eligible wallets of a Bonferroni-corrected day-clustered LOWER BOUND on
               the wallet's MODELED copy-return at OUR realizable entry (price + follower tax +
               band spread, fee). "A wallet we could provably have tailed for ≥ this exists."
               THE ONLY NUMBER GATED ON.
  B_point(c) = max point estimate — the "most profitable player" headline. REPORT-ONLY,
               labelled selection-inflated: it is what ranking 400 wallets and reading the top
               always produces, real skill or not.
  Wallets flagged market-maker (UNION: microstructure ∨ trader_type='bot') are EXCLUDED from
  B_LB (structurally uncopyable) but shown in the headline table so the gap is visible.

OUR side: each paper arm's day-clustered mean/LB from honest_paper_ledger (realizable entries,
same fee) — compared against B_LB per context, and the GAP DECOMPOSED for the top wallets:
  raw @ their price  →  repriced @ OUR entry (the copyability tax)  →  LB (the noise haircut)
  →  MM flag (the structurally-uncopyable share).

Read-only, paper-only. ./best_trader_benchmark.py [--selftest]
Writes reports/best_trader_benchmark.json.
"""

import argparse
import json
import math
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trader_scorecard as tsc

REPORT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "reports", "best_trader_benchmark.json")
MIN_EVENTS = 30          # run-plan eligibility floor
MIN_DAYS = 5             # a day-clustered LB needs days
ALPHA = 0.05             # one-sided, Bonferroni-split over N_elig per context


def z_upper(p):
    """Inverse normal CDF (upper-tail z for one-sided level p). scipy if present."""
    try:
        from scipy.stats import norm
        return float(norm.ppf(1.0 - p))
    except Exception:
        # Acklam-lite fallback over the range we use (p in [1e-6, 0.05]).
        t = math.sqrt(-2.0 * math.log(p))
        return t - (2.30753 + 0.27061 * t) / (1.0 + 0.99229 * t + 0.04481 * t * t)


def fetch_fills_with_sport():
    return tsc.q(f"""
      SELECT lower(wallet) AS wallet, COALESCE(event_slug, condition_id) AS ev,
             (ts AT TIME ZONE 'UTC')::date AS day, price, outcome_won::int AS won,
             COALESCE(sport, 'other') AS sport
      FROM trader_fills
      WHERE side = 'BUY' AND resolved AND outcome_won IS NOT NULL
        AND price >= {tsc.BAND_LO} AND price < {tsc.BAND_HI}
        AND ts >= NOW() - INTERVAL '{tsc.WINDOW_DAYS} days'""")


def wallet_day_returns(rows, spreads, repriced=True):
    """(wallet, context) -> day -> [event returns]; contexts = overall + sport."""
    ev_acc = defaultdict(list)   # (wallet, ctx, ev) -> per-fill rets ; day/sport ride along
    ev_day = {}
    for r in rows:
        price = float(r["price"])
        e = tsc.reprice(price, spreads) if repriced else price
        ret = (int(r["won"]) - e) / e - tsc.FEE
        for ctx in ("overall", r["sport"]):
            key = (r["wallet"], ctx, r["ev"])
            ev_acc[key].append(ret)
            ev_day[key] = r["day"]
    out = defaultdict(lambda: defaultdict(list))   # (wallet, ctx) -> day -> [ev rets]
    for key, rets in ev_acc.items():
        w, ctx, _ = key
        out[(w, ctx)][ev_day[key]].append(sum(rets) / len(rets))
    return out


def wallet_stats(day_map):
    """Day-clustered mean/sd/n over one (wallet, ctx)."""
    dm = [sum(v) / len(v) for v in day_map.values()]
    n_ev = sum(len(v) for v in day_map.values())
    n = len(dm)
    mean = sum(dm) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in dm) / (n - 1)) if n > 1 else float("nan")
    return {"mean": mean, "sd_day": sd, "n_days": n, "n_events": n_ev}


def benchmark(day_maps, mm_flagged):
    """Per context: B_LB over eligible copyable wallets + the selection-inflated headline."""
    by_ctx = defaultdict(dict)
    for (w, ctx), dmap in day_maps.items():
        s = wallet_stats(dmap)
        if s["n_events"] >= MIN_EVENTS and s["n_days"] >= MIN_DAYS:
            by_ctx[ctx][w] = s
    out = {}
    for ctx, wallets in by_ctx.items():
        copyable = {w: s for w, s in wallets.items() if w not in mm_flagged}
        n_elig = len(copyable)
        best_lb, best_lb_w = None, None
        for w, s in copyable.items():
            if s["n_days"] < 2 or math.isnan(s["sd_day"]):
                continue
            lb = s["mean"] - z_upper(ALPHA / max(n_elig, 1)) * s["sd_day"] / math.sqrt(s["n_days"])
            s["lb"] = lb
            if best_lb is None or lb > best_lb:
                best_lb, best_lb_w = lb, w
        pt = max(wallets.items(), key=lambda kv: kv[1]["mean"]) if wallets else (None, None)
        out[ctx] = {
            "n_eligible": len(wallets), "n_copyable": n_elig,
            "B_LB": best_lb, "B_LB_wallet": best_lb_w,
            "B_point_selection_inflated": pt[1]["mean"] if pt[1] else None,
            "B_point_wallet": pt[0],
            "B_point_is_mm": pt[0] in mm_flagged if pt[0] else None,
        }
    return out, by_ctx


def our_arms():
    rows = tsc.q("""
      SELECT strategy, (resolved_at AT TIME ZONE 'UTC')::date AS day,
             AVG((outcome_won::int - entry) / entry - 0.02) AS day_roi, COUNT(*) AS n
      FROM honest_paper_ledger WHERE entry > 0
      GROUP BY 1, 2 ORDER BY 1, 2""")
    per = defaultdict(list)
    for r in rows:
        per[r["strategy"]].append(float(r["day_roi"]))
    out = {}
    for strat, dm in per.items():
        n = len(dm)
        mean = sum(dm) / n
        sd = math.sqrt(sum((x - mean) ** 2 for x in dm) / (n - 1)) if n > 1 else float("nan")
        out[strat] = {"mean": mean, "n_days": n,
                      "lb95": mean - 1.6449 * sd / math.sqrt(n) if n > 1 else None}
    return out


def gap_table(day_maps_raw, day_maps_rep, mm_flagged, top=6):
    """Top wallets by RAW overall mean → the decomposition of why we can't just 'be them'."""
    rows = []
    for (w, ctx), dmap in day_maps_raw.items():
        if ctx != "overall":
            continue
        s = wallet_stats(dmap)
        if s["n_events"] >= MIN_EVENTS and s["n_days"] >= MIN_DAYS:
            rep = wallet_stats(day_maps_rep[(w, ctx)])
            rows.append({"wallet": w, "raw_at_their_price": round(s["mean"], 4),
                         "repriced_at_ours": round(rep["mean"], 4),
                         "copyability_tax": round(s["mean"] - rep["mean"], 4),
                         "n_events": s["n_events"], "n_days": s["n_days"],
                         "mm_flagged": w in mm_flagged})
    rows.sort(key=lambda r: -r["raw_at_their_price"])
    return rows[:top]


def selftest():
    # One dominating wallet (many days, high ret) vs noise wallets ⇒ B_LB positive and his.
    dm = {}
    for w, mu in [("champ", 0.30), ("noise1", 0.01), ("noise2", -0.02)]:
        m = defaultdict(list)
        for d in range(40):
            m[f"d{d}"] = [mu + (0.02 if d % 2 else -0.02)]
        dm[(w, "overall")] = m
    bench, _ = benchmark(dm, mm_flagged=set())
    assert bench["overall"]["B_LB_wallet"] == "champ" and bench["overall"]["B_LB"] > 0.2
    # All-noise ⇒ B_LB near/below zero; champ flagged MM ⇒ excluded from B_LB.
    bench2, _ = benchmark(dm, mm_flagged={"champ"})
    assert bench2["overall"]["B_LB_wallet"] != "champ"
    assert bench2["overall"]["B_point_wallet"] == "champ" and bench2["overall"]["B_point_is_mm"]
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return

    spreads = tsc.fetch_band_spreads()
    rows = fetch_fills_with_sport()
    micro = tsc.fetch_micro()
    bots = tsc.fetch_bot_flags()
    wallets = {r["wallet"] for r in rows}
    mm_flagged = {w for w in wallets
                  if tsc.is_mm(micro.get(w, {"rtr": 0, "sbr": 0, "tsr": 0}))
                  or bots.get(w) == "bot"}

    rep = wallet_day_returns(rows, spreads, repriced=True)
    raw = wallet_day_returns(rows, spreads, repriced=False)
    bench, _ = benchmark(rep, mm_flagged)
    ours = our_arms()
    gaps = gap_table(raw, rep, mm_flagged)

    # The verdict per context: do ANY of our arms provably clear the provable best?
    comparisons = {}
    for ctx, b in bench.items():
        if b["B_LB"] is None:
            comparisons[ctx] = "INDETERMINATE — no copyable wallet has a meaningful LB"
            continue
        beat = [s for s, v in ours.items()
                if v["lb95"] is not None and v["lb95"] > b["B_LB"] + 0.03]
        comparisons[ctx] = {"B_LB": round(b["B_LB"], 4), "our_arms_clearing_B_LB+3pct": beat}

    out = {"meta": {"min_events": MIN_EVENTS, "min_days": MIN_DAYS, "alpha": ALPHA,
                    "mm_flagged_n": len(mm_flagged),
                    "reprice": "price + 0.013 + band_spread, fee 0.02 (copyability conv.)"},
           "benchmark": bench, "our_arms": ours, "gap_decomposition_top": gaps,
           "comparisons": comparisons}
    with open(REPORT, "w") as f:
        json.dump(out, f, indent=2, default=str)

    print("BEST-TRADER BENCHMARK (fair: repriced at OUR entry, Bonferroni over eligible)")
    for ctx in sorted(bench):
        b = bench[ctx]
        lb = f"{b['B_LB']:+.3f} ({b['B_LB_wallet'][:10] if b['B_LB_wallet'] else '—'}…)" \
            if b["B_LB"] is not None else "INDETERMINATE"
        print(f"  {ctx:>10}: B_LB={lb} | headline B_point={b['B_point_selection_inflated']:+.3f}"
              f" (MM={b['B_point_is_mm']}) | eligible={b['n_eligible']} copyable={b['n_copyable']}")
    print("OUR ARMS (day-clustered, honest ledger):")
    for s in ("favorite", "strict", "elite_fresh_fav", "proven_router"):
        if s in ours:
            v = ours[s]
            lb = f"{v['lb95']:+.3f}" if v["lb95"] is not None else "—"
            print(f"  {s:>16}: mean {v['mean']:+.3f}, LB95 {lb}, {v['n_days']} days")
    print("WHY-GAP (top raw wallets → what survives to OUR price):")
    for g in gaps:
        print(f"  {g['wallet'][:12]}… raw {g['raw_at_their_price']:+.3f} → ours "
              f"{g['repriced_at_ours']:+.3f} (tax {g['copyability_tax']:+.3f}) "
              f"MM={g['mm_flagged']} n={g['n_events']}ev/{g['n_days']}d")
    print(f"wrote {REPORT}")


if __name__ == "__main__":
    main()
