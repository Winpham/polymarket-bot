#!/usr/bin/env python3
"""
RELIABILITY-WEIGHTED, CORRELATION-DIVERSIFIED BOOK (Thread R3, cycle-3) — only reached because R2
verdict = GO (reliability persists). §3 of TRADER-RELIABILITY-PORTFOLIO-PLAN.md.

From the Thread-R1 gated shortlist (reliability_score.json), build the "congregation done right":
  1. Event/day-level return-correlation matrix across the shortlist (the diversification substrate).
  2. Assemble a LOW-correlation book; reliability-WEIGHT by inverse-downside (equal-risk), cap any
     single name. Portfolio variance below any single member is the one valid route to a higher
     risk-adjusted return than the best single trader (the top-1 router failed for lack of exactly
     this; k=3 worked in SHAPE, Cycle-2).
  3. Blended flat-SHARES equity curve + risk-adjusted stats (Sortino / max-drawdown / positive-window).
  4. COPYABILITY LAST: re-price at OUR entry (follower tax + band spread + fee), show the book BEFORE
     and AFTER the copyability trim (drop/downweight names underwater at our price). Copyability trims
     the book; it never selects it (skill/reliability at their price does).
  5. BENCHMARK: does the reliable book beat the BEST SINGLE reliable trader on risk-adjusted,
     consistency terms — IN-sample (descriptive) and OUT-of-sample (weights from EARLY, evaluated on
     the held-out LATE days; the honest, leak-free test)?
  6. Belief-blind gate on any copyability/promotion claim: a matched-random-subset null (random books
     of the same size from the scored pool) — is the reliability SELECTION better than a random book,
     or just the diversification arithmetic?

Unit: flat-SHARES per-$1-face-share P&L, event-clustered then day-aggregated. their price = won-price;
our entry = (won - (price + follower_tax + band_spread)) - fee*our_entry. Read-only, paper-only,
promotes NOTHING (if anything cleared every gate we HALT and escalate — it does not).

  ./reliability_portfolio.py            # live
  ./reliability_portfolio.py --selftest # low-corr book beats best single on downside; wiring checks
"""

import argparse
import json
import math
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trader_scorecard as tsc
import reliability_score as rs

REPORT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "reports", "reliability_portfolio.json")
WEIGHT_CAP = 0.40        # no single name > 40% of the book
N_NULL = 2000
SEED = 20260705
FEE = tsc.FEE


def _event_pnl(rows, spreads, mode):
    """Per-event flat-shares P&L for a wallet's rows. mode 'their' -> won-price;
    'our' -> (won - reprice) - fee*reprice. Returns list of (day, ts, pnl) time-sorted."""
    acc = defaultdict(list)
    for r in rows:
        acc[r["ev"]].append(r)
    out = []
    for ev, fs in acc.items():
        n = len(fs)
        if mode == "their":
            pnl = sum(int(f["won"]) - float(f["price"]) for f in fs) / n
        else:
            pv = []
            for f in fs:
                e = tsc.reprice(float(f["price"]), spreads)
                pv.append((int(f["won"]) - e) - FEE * e)
            pnl = sum(pv) / n
        ts0 = min(float(f["ts"]) for f in fs)
        day = min(fs, key=lambda f: float(f["ts"]))["day"]
        out.append((day, ts0, pnl))
    out.sort(key=lambda x: (x[1],))
    return out


def _daily(evpnl):
    """day -> mean per-event pnl that day (flat-shares day return)."""
    byday = defaultdict(list)
    for day, _, pnl in evpnl:
        byday[day].append(pnl)
    return {d: sum(v) / len(v) for d, v in byday.items()}


def _series_stats(daily):
    """Risk-adjusted stats of a daily flat-shares return series."""
    days = sorted(daily)
    r = [daily[d] for d in days]
    n = len(r)
    if n == 0:
        return {"n_days": 0}
    mean = sum(r) / n
    dn = [min(0.0, x) for x in r]
    dd = math.sqrt(sum(x * x for x in dn) / n)
    sortino = (mean / dd) if dd > 0 else (float("inf") if mean > 0 else float("nan"))
    # equity curve max drawdown (return units)
    peak = eq = maxdd = 0.0
    for x in r:
        eq += x
        peak = max(peak, eq)
        maxdd = max(maxdd, peak - eq)
    pos = sum(1 for x in r if x > 0) / n
    return {"n_days": n, "mean_day": mean, "downside_dev": dd, "sortino": sortino,
            "max_drawdown": maxdd, "pos_window_frac": pos, "total_pnl": sum(r)}


def _pearson_common(a, b):
    """Pearson correlation of two daily dicts over their common days."""
    common = sorted(set(a) & set(b))
    if len(common) < 3:
        return None, len(common)
    xs = [a[d] for d in common]
    ys = [b[d] for d in common]
    return tsc.pearson(xs, ys), len(common)


def _weights(dd_by_wallet, cap=WEIGHT_CAP):
    """Inverse-downside (equal-risk) weights, capped, renormalized (iterated to respect the cap)."""
    inv = {w: (1.0 / dd if dd > 0 else 1.0 / 1e-6) for w, dd in dd_by_wallet.items()}
    tot = sum(inv.values())
    w = {k: v / tot for k, v in inv.items()}
    for _ in range(50):
        over = {k: v for k, v in w.items() if v > cap + 1e-12}
        if not over:
            break
        for k in over:
            w[k] = cap
        rem = 1.0 - cap * len(over)
        free = {k: inv[k] for k in w if k not in over}
        ftot = sum(free.values()) or 1.0
        for k in free:
            w[k] = rem * inv[k] / ftot
    return w


def book_daily(dailies, weights):
    """Blend per-wallet daily series into a book daily series; weights renormalized among the
    wallets active each day (flat-shares, missing wallet = not trading that day)."""
    alldays = sorted(set().union(*[set(d) for d in dailies.values()])) if dailies else []
    out = {}
    for day in alldays:
        active = [(w, dailies[w][day]) for w in dailies if day in dailies[w]]
        wsum = sum(weights[w] for w, _ in active)
        if wsum <= 0:
            continue
        out[day] = sum(weights[w] * r for w, r in active) / wsum
    return out


def build(wallet_rows, shortlist, spreads, mode="their", days_filter=None,
          dd_override=None, cap=WEIGHT_CAP):
    """Build the book over `shortlist` in price `mode`. days_filter(set) restricts to those days
    (for out-of-sample). Returns (book_daily, weights, per_wallet_daily, per_wallet_stats)."""
    dailies, stats, dd = {}, {}, {}
    for w in shortlist:
        ep = _event_pnl(wallet_rows[w], spreads, mode)
        dl = _daily(ep)
        if days_filter is not None:
            dl = {d: v for d, v in dl.items() if d in days_filter}
        if not dl:
            continue
        dailies[w] = dl
        stats[w] = _series_stats(dl)
        dd[w] = stats[w]["downside_dev"]
    if dd_override:
        dd = {w: dd_override.get(w, dd.get(w, 1.0)) for w in dailies}
    weights = _weights(dd, cap) if dailies else {}
    bd = book_daily(dailies, weights)
    return bd, weights, dailies, stats


# ---------------------------------------------------------------- selftest
def selftest():
    spreads = {}

    def rows_from_daily(w, day_ret_map, sport="soccer"):
        """Make one event per day at price 0.50 so won-price == +/-0.5 sign matches day_ret sign;
        scale via number of wins/losses. Simplest: 1 event/day, won chosen to hit target sign."""
        rows = []
        i = 0
        for day, r in day_ret_map.items():
            won = 1 if r > 0 else 0
            price = 0.5 - r if won else 0.5 - r     # won-price = r  (won=1 -> price=1-r; won=0 -> price=-r)
            price = (1.0 - r) if won else (-r)
            price = min(0.89, max(0.46, price))
            rows.append({"wallet": w, "ev": f"{w}-{day}", "day": day, "ts": i,
                         "price": price, "won": won, "sport": sport})
            i += 1
        return rows

    # Two ANTI-correlated wallets: on odd days A up/B down, even days A down/B up -> book smoother.
    days = [f"2026-06-{d:02d}" for d in range(1, 21)]
    a = {d: (+0.20 if i % 2 == 0 else -0.10) for i, d in enumerate(days)}
    b = {d: (-0.10 if i % 2 == 0 else +0.20) for i, d in enumerate(days)}
    wr = {"A": rows_from_daily("A", a), "B": rows_from_daily("B", b)}
    bd, wts, dl, st = build(wr, ["A", "B"], spreads, mode="their")
    bs = _series_stats(bd)
    # book downside deviation must be below the mean of the two singles' downside (diversification)
    mean_single_dd = (st["A"]["downside_dev"] + st["B"]["downside_dev"]) / 2
    assert bs["downside_dev"] < mean_single_dd, \
        f"anti-corr book should cut downside: book {bs['downside_dev']:.3f} vs single {mean_single_dd:.3f}"
    # correlation must be negative
    c, ncommon = _pearson_common(dl["A"], dl["B"])
    assert c is not None and c < -0.5 and ncommon == 20, f"anti-corr expected, got {c}"

    # weight cap respected
    ddm = {"A": 0.01, "B": 1.0, "C": 1.0}   # A would dominate uncapped
    w = _weights(ddm, cap=0.40)
    assert w["A"] <= 0.40 + 1e-9 and abs(sum(w.values()) - 1.0) < 1e-9, f"cap/renorm failed: {w}"

    # our-entry pnl <= their-price pnl (copyability tax only subtracts)
    ep_their = _event_pnl(wr["A"], spreads, "their")
    ep_our = _event_pnl(wr["A"], {3: 0.03, 4: 0.03, 5: 0.03}, "our")
    assert sum(p for _, _, p in ep_our) < sum(p for _, _, p in ep_their), "our-entry must be <= their-price"

    # days_filter (out-of-sample) restricts the series
    bd2, _, _, _ = build(wr, ["A", "B"], spreads, mode="their", days_filter=set(days[10:]))
    assert _series_stats(bd2)["n_days"] == 10, "days_filter must restrict"

    print("selftest OK")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return

    import random
    rng = random.Random(SEED)
    rows = rs.fetch_fills()
    micro = tsc.fetch_micro()
    bots = tsc.fetch_bot_flags()
    spreads = tsc.fetch_band_spreads()
    name_rows = tsc.q("SELECT lower(proxy_wallet) AS w, username FROM followed_traders")
    names = {r["w"]: r["username"] for r in name_rows}

    wallet_rows = defaultdict(list)
    for r in rows:
        wallet_rows[r["wallet"]].append(r)

    # rebuild the R1 shortlist + all scored wallets (self-contained)
    scored, shortlist = {}, []
    for w, rr in wallet_rows.items():
        if len({r["ev"] for r in rr}) < rs.MIN_EVENTS:
            continue
        s = rs.score_wallet(rr)
        is_mm = tsc.is_mm(micro.get(w, {"rtr": 0, "sbr": 0, "tsr": 0}))
        is_bot = bots.get(w) == "bot"
        passed, fails, _ = rs.gate(s, is_mm, is_bot)
        scored[w] = {"score": s, "pass": passed, "is_mm": is_mm, "is_bot": is_bot}
        if passed:
            shortlist.append(w)
    shortlist.sort(key=lambda w: -scored[w]["score"]["sortino"])
    dd_ev = {w: scored[w]["score"]["downside_dev"] for w in shortlist}

    # ---- correlation matrix (their-price daily) ----
    dailies_their = {w: _daily(_event_pnl(wallet_rows[w], spreads, "their")) for w in shortlist}
    cormat = {}
    for i, a in enumerate(shortlist):
        for bwt in shortlist[i + 1:]:
            c, ncom = _pearson_common(dailies_their[a], dailies_their[bwt])
            cormat[f"{names.get(a,a[:8])}|{names.get(bwt,bwt[:8])}"] = {
                "corr": c, "common_days": ncom}

    # ---- book (their price, full sample) ----
    bd, weights, dl, wstats = build(wallet_rows, shortlist, spreads, mode="their", dd_override=dd_ev)
    book_stats = _series_stats(bd)
    best_single = max(shortlist, key=lambda w: wstats[w]["sortino"]
                      if wstats[w]["sortino"] == wstats[w]["sortino"] else -9)
    best_stats = wstats[best_single]

    # ---- copyability LAST: re-price at OUR entry ----
    bd_our, weights_our_pre, dl_our, wstats_our = build(wallet_rows, shortlist, spreads, mode="our",
                                                        dd_override=dd_ev)
    book_our_pre = _series_stats(bd_our)
    # trim: drop names underwater (negative total pnl) at our entry
    keep = [w for w in shortlist if wstats_our.get(w, {}).get("total_pnl", -1) > 0]
    if keep:
        dd_keep = {w: dd_ev[w] for w in keep}
        bd_our_trim, weights_trim, _, wstats_our_trim = build(
            wallet_rows, keep, spreads, mode="our", dd_override=dd_keep)
        book_our_trim = _series_stats(bd_our_trim)
    else:
        book_our_trim, weights_trim = {"n_days": 0}, {}

    # ---- out-of-sample benchmark: weights from EARLY, evaluate LATE (leak-free) ----
    oos = {}
    # per-wallet median-day split shared grid: use each wallet's own median day for its early/late
    all_days = sorted({d for w in shortlist for d in dailies_their[w]})
    if len(all_days) >= 6:
        cut = all_days[len(all_days) // 2]
        early_days = set(d for d in all_days if d < cut)
        late_days = set(d for d in all_days if d >= cut)
        # downside from EARLY only for weighting
        dd_early = {}
        for w in shortlist:
            e_dl = {d: v for d, v in dailies_their[w].items() if d in early_days}
            dd_early[w] = _series_stats(e_dl)["downside_dev"] if e_dl else 1.0
        bd_late, w_late, _, wstats_late = build(wallet_rows, shortlist, spreads, mode="their",
                                                days_filter=late_days, dd_override=dd_early)
        book_late = _series_stats(bd_late)
        # best single on late = the early-best-sortino single, evaluated on late
        dd_e_stats = {w: _series_stats({d: v for d, v in dailies_their[w].items() if d in early_days})
                      for w in shortlist}
        best_early = max(shortlist, key=lambda w: dd_e_stats[w].get("sortino", -9)
                         if dd_e_stats[w].get("sortino", -9) == dd_e_stats[w].get("sortino", -9) else -9)
        best_late = wstats_late.get(best_early, {"n_days": 0})
        oos = {"cut_day": cut, "book_late": book_late,
               "best_single_early": names.get(best_early, best_early[:10]),
               "best_single_late": best_late,
               "book_beats_best_single_sortino": (book_late.get("sortino", -9) or -9) >
                                                 (best_late.get("sortino", -9) or -9),
               "book_beats_best_single_maxdd": (book_late.get("max_drawdown", 9) or 9) <
                                               (best_late.get("max_drawdown", 9) or 9)}

    # ---- belief-blind null: is the reliability SELECTION better than a random book? ----
    pool = list(scored.keys())
    k = len(shortlist)
    obs_sortino = book_stats["sortino"] if book_stats["sortino"] == book_stats["sortino"] else -9
    ge = 0
    null_sortinos = []
    dailies_all = {}
    for _ in range(N_NULL):
        pick = rng.sample(pool, k)
        for w in pick:
            if w not in dailies_all:
                dailies_all[w] = _daily(_event_pnl(wallet_rows[w], spreads, "their"))
        ddp = {w: _series_stats(dailies_all[w])["downside_dev"] for w in pick}
        wts = _weights(ddp)
        bdp = book_daily({w: dailies_all[w] for w in pick}, wts)
        so = _series_stats(bdp)["sortino"]
        # honest/conservative clamp: a no-downside positive-mean random book (Sortino +inf) is
        # genuinely smoother in-sample and COUNTS as beating the reliable book's finite Sortino;
        # a NaN/degenerate non-positive book does not.
        if so != so:                       # NaN
            counts = False
            store = -9.0
        elif so == float("inf"):
            counts = True
            store = float("inf")
        else:
            counts = so >= obs_sortino
            store = so
        null_sortinos.append(store if store != float("inf") else None)
        if counts:
            ge += 1
    null_p = (ge + 1) / (N_NULL + 1)
    finite_null = [x for x in null_sortinos if x is not None]
    n_inf = sum(1 for x in null_sortinos if x is None)
    null_mean = (sum(finite_null) / len(finite_null)) if finite_null else float("nan")

    def clean(x):
        if isinstance(x, float):
            if math.isinf(x):
                return "inf" if x > 0 else "-inf"
            if math.isnan(x):
                return None
            return round(x, 5)
        return x

    def cs(d):
        return {k: clean(v) for k, v in d.items()}

    out = {
        "meta": {"weight_cap": WEIGHT_CAP, "unit": "flat_shares_daily_return", "fee": FEE,
                 "n_null": N_NULL, "seed": SEED,
                 "shortlist": [names.get(w, w) for w in shortlist],
                 "gate_r2_verdict": "GO (reliability_persistence.json)",
                 "charter": "TRADER-RELIABILITY-PORTFOLIO-PLAN.md §3"},
        "correlation_matrix": {k: {"corr": clean(v["corr"]), "common_days": v["common_days"]}
                               for k, v in cormat.items()},
        "weights_their_price": {names.get(w, w): round(weights.get(w, 0), 4) for w in shortlist},
        "book_their_price": cs(book_stats),
        "best_single_reliable": {"name": names.get(best_single, best_single),
                                 "stats": cs(best_stats)},
        "book_vs_best_single_insample": {
            "sortino_book": clean(book_stats["sortino"]), "sortino_best": clean(best_stats["sortino"]),
            "book_wins_sortino": (book_stats["sortino"] or -9) > (best_stats["sortino"] or -9),
            "maxdd_book": clean(book_stats["max_drawdown"]), "maxdd_best": clean(best_stats["max_drawdown"]),
            "book_wins_maxdd": (book_stats["max_drawdown"]) < (best_stats["max_drawdown"]),
            "poswin_book": clean(book_stats["pos_window_frac"]),
            "poswin_best": clean(best_stats["pos_window_frac"])},
        "copyability": {
            "book_before_trim_our_entry": cs(book_our_pre),
            "names_kept_after_trim": [names.get(w, w) for w in keep],
            "names_dropped": [names.get(w, w) for w in shortlist if w not in keep],
            "book_after_trim_our_entry": cs(book_our_trim),
            "per_wallet_our_entry_total_pnl": {names.get(w, w): clean(wstats_our.get(w, {}).get("total_pnl"))
                                               for w in shortlist}},
        "out_of_sample": {kk: (cs(vv) if isinstance(vv, dict) else clean(vv)) for kk, vv in oos.items()},
        "belief_blind_null": {"book_sortino": clean(obs_sortino),
                              "random_book_sortino_mean_finite": clean(null_mean),
                              "random_no_downside_share": round(n_inf / N_NULL, 4),
                              "selection_beats_random_p": null_p,
                              "note": "p = P(random equal-size inverse-dd book Sortino >= reliable book); "
                                      "no-downside random books count as beating (conservative)"},
    }
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w") as f:
        json.dump(out, f, indent=2, default=str)

    # ---- console ----
    print(f"RELIABILITY BOOK · shortlist n={len(shortlist)}: {[names.get(w,w[:8]) for w in shortlist]}")
    print("  correlation (their-price daily, common days):")
    for k, v in out["correlation_matrix"].items():
        print(f"    {k:<40} corr {str(v['corr']):>7}  (n_common={v['common_days']})")
    print(f"  weights (inverse-downside, cap {WEIGHT_CAP}): {out['weights_their_price']}")
    b, bs = book_stats, best_stats
    print(f"\n  BOOK (their price):  Sortino {b['sortino']:+.3f}  maxDD {b['max_drawdown']:.2f}  "
          f"posWin {b['pos_window_frac']:.0%}  meanDay {b['mean_day']:+.4f}  ({b['n_days']} days)")
    print(f"  BEST SINGLE ({names.get(best_single, best_single)}): Sortino {bs['sortino']:+.3f}  "
          f"maxDD {bs['max_drawdown']:.2f}  posWin {bs['pos_window_frac']:.0%}  ({bs['n_days']} days)")
    iw = out["book_vs_best_single_insample"]
    print(f"  -> in-sample: book wins Sortino={iw['book_wins_sortino']}, wins maxDD={iw['book_wins_maxdd']}")
    print(f"\n  COPYABILITY (re-priced at OUR entry): book BEFORE trim Sortino "
          f"{_g(book_our_pre,'sortino')} totalPnL {_g(book_our_pre,'total_pnl')}")
    print(f"    kept {out['copyability']['names_kept_after_trim']}  dropped {out['copyability']['names_dropped']}")
    print(f"    book AFTER trim Sortino {_g(book_our_trim,'sortino')} totalPnL {_g(book_our_trim,'total_pnl')}")
    if oos:
        print(f"\n  OUT-OF-SAMPLE (weights from EARLY, eval LATE, cut {oos['cut_day']}): "
              f"book_late Sortino {_g(oos['book_late'],'sortino')}  best_single_late Sortino "
              f"{_g(oos['best_single_late'],'sortino')}  -> book beats best (Sortino)="
              f"{oos['book_beats_best_single_sortino']}, (maxDD)={oos['book_beats_best_single_maxdd']}")
    nb = out["belief_blind_null"]
    print(f"\n  BELIEF-BLIND: reliable-book Sortino {nb['book_sortino']} vs random-book finite-mean "
          f"{nb['random_book_sortino_mean_finite']} (no-downside share {nb['random_no_downside_share']:.0%}) "
          f"-> selection beats random p={nb['selection_beats_random_p']:.4f}")
    print(f"\nwrote {REPORT}")


def _g(d, k):
    v = d.get(k) if isinstance(d, dict) else None
    if v is None:
        return "n/a"
    if isinstance(v, str):
        return v
    return f"{v:+.3f}"


if __name__ == "__main__":
    main()
