#!/usr/bin/env python3
"""WIDE-VOTER REPLAY — does widening the consensus voter set (top-40 -> C) add REAL edge?

Faithful DB replay of the REAL consensus.rs `favorite` arm (band 0.65-0.98) at a
sweep of voter-rank cutoffs C in {40,60,80,100,150,200}. The ONLY thing that
changes across cutoffs is who is eligible to vote (rank <= C); every other gate is
the champion's (min_backers=3, max_opposers=1, max_price_std=0.10, price band,
two-sided MM exclusion, 48h recency -> auto-passes at fire).

Faithfulness (mirrors copy-trading-bot/src/scanner/consensus.rs::score_market):
  * voter set  = followed_traders.rank <= C  (rank = the stored per-wallet min rank;
                 rank<=40 == consensus_eligible == prod's live voter set).
  * two-sided wallets (fills on >1 outcome of the same cond, up to fire) dropped both sides.
  * distinct one-sided backers >= min_backers; opposers <= max_opposers.
  * mean_price / price_std over ALL one-sided backer fills (fill-count weighted -> exact),
    at FIRE time (= arrival of the 3rd distinct backer); no look-ahead.
  * price band gate on mean_price.
Fills come from the durable `trader_fills` archive (the vote_window is pruned to ~4d),
aggregated per (cond,oidx,wallet,price@3dp) so same-price laddering collapses exactly.

Honesty rails (learned the hard way):
  * entry = at-fire initial_mean_price (backer fill prices) — never live recency/total_usd.
  * corrected fee = catrate*(1-entry) per stake (sports 0.03), entry-only. flat $100.
  * belief-blind surplus vs a SAME-CUTOFF `_blind` band baseline (rebuilt at each C),
    event-clustered on the match-level super_event key; permutation null (selection_null).
  * multiple-testing correction across the 6-cutoff sweep (Bonferroni).
  * by-regime + non-FIFWC + time-split reported.

Read-only. Writes only reports/. Usage:
  python3 scripts/wide_voter_replay.py --data <scratchdir> [--json reports/wide_voter_replay.json]
"""
import argparse
import csv
import io
import json
import math
import os
import random
import subprocess
import sys
from collections import defaultdict
from statistics import NormalDist

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from superkey import super_event  # noqa: E402
import selection_null as sn  # noqa: E402  (band(), null_pvalue(), clustered_surplus())

CUTOFFS = [40, 60, 80, 100, 150, 200]
FAV_BAND = (0.65, 0.98)
MIN_BACKERS = 3
MAX_OPP = 1
MAX_PSTD = 0.10
N_PERM = 2000
SEED = 20260710
PG = ["docker", "exec", "polymarket-bot-postgres-1", "psql", "-U", "bot", "-d", "polymarket"]

# corrected taker fee per stake = catrate*(1-p); sports 0.03 (fee_schedule_sensitivity.py)
REGIME_FEE = {"crypto": 0.07, "tennis": 0.03, "soccer": 0.03, "mlb": 0.03, "cs2": 0.03,
              "other": 0.05}


def wmean_std(pairs):
    """(price, weight) pairs -> population mean/std weighted by weight (fill count)."""
    W = sum(w for _, w in pairs)
    if W <= 0:
        return 0.0, 0.0
    m = sum(p * w for p, w in pairs) / W
    v = sum(w * (p - m) ** 2 for p, w in pairs) / W
    return m, math.sqrt(max(v, 0.0))


def regime(event_slug):
    s = event_slug or ""
    for prefixes, name in sn.REGIMES:
        if s.startswith(prefixes):
            return name
    return "other"


def load(data_dir):
    ranks = {}
    with open(os.path.join(data_dir, "ranks.tsv")) as f:
        for line in f:
            w, r = line.rstrip("\n").split("\t")
            ranks[w] = int(r)
    meta = {}
    with open(os.path.join(data_dir, "meta.tsv")) as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 8:
                continue
            cond, oidx, spo, ev, slug, title, res, won = parts
            if not cond or not oidx:
                continue
            try:
                oidx = int(oidx)
            except ValueError:
                continue
            if oidx < 0 or oidx > 50:
                continue
            meta[(cond, oidx)] = {
                "is_sports": spo == "t",
                "event_slug": ev or None,
                "slug": slug or None,
                "title": title or "",
                "resolved": res == "t",
                "won": (int(won) if won != "" else None),
            }
    # book: cond -> oidx -> wallet -> {"groups": [(price,n,ts,size)], "rank": rank}
    # Each price-group keeps its OWN timestamp so the trailing-48h window at fire
    # time can roll off stale fills exactly (matches prod's vote_window since=now-48h).
    book = defaultdict(lambda: defaultdict(dict))
    nfill = 0
    with open(os.path.join(data_dir, "fills.tsv")) as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 7:
                continue
            cond, oidx, wallet, price, n, ts, size = parts
            if not cond or not oidx:
                continue
            try:
                oidx = int(oidx)
            except ValueError:
                continue
            if oidx < 0 or oidx > 50:
                continue
            rk = ranks.get(wallet)
            if rk is None:
                continue
            price = float(price); n = int(n); ts = int(ts); size = float(size)
            if not (0.0 < price < 1.0):
                continue
            w = book[cond][oidx].get(wallet)
            if w is None:
                book[cond][oidx][wallet] = {"groups": [(price, n, ts, size)], "rank": rk}
            else:
                w["groups"].append((price, n, ts, size))
            nfill += 1
    return ranks, meta, book, nfill


WINDOW = 48 * 3600  # trailing consensus window (max_age_mins=2880), seconds


import bisect as _bisect


def build_events(book_c, cutoff):
    """Per outcome: sorted lists (ts, ts_arr, wallet, price, n, size, rank) for eligible voters."""
    ev = {}
    for o, wallets in book_c.items():
        lst = []
        for w, e in wallets.items():
            if e["rank"] > cutoff:
                continue
            for pr, n, gts, sz in e["groups"]:
                lst.append((gts, w, pr, n, sz, e["rank"]))
        if lst:
            lst.sort()
            ev[o] = (lst, [x[0] for x in lst])
    return ev


def window_wallets(ev, o, t):
    """set of wallets with a fill in (t-48h, t] on outcome o."""
    lst, tsarr = ev[o]
    lo = _bisect.bisect_right(tsarr, t - WINDOW)
    hi = _bisect.bisect_right(tsarr, t)
    return {lst[i][1] for i in range(lo, hi)}


def fire_one(cond, oidx, ev, min_backers, max_opp, max_pstd, band):
    """Faithful fire reconstruction with a TRAILING 48h window (sweep-line).

    The book at fire time t = fills in (t-48h, t] from eligible voters — exactly
    prod's per-cycle vote_window (since = now-48h). Fires the FIRST t where the
    champion gates pass; at-fire mean/std/total from that window only. No look-ahead."""
    if oidx not in ev:
        return None
    tgt, tsarr = ev[oidx]
    others = [o for o in ev if o != oidx]
    # two-pointer sliding window over target fills → earliest t with >=min_backers distinct
    cnt = defaultdict(int)
    left = 0
    for r in range(len(tgt)):
        t = tgt[r][0]
        lo = t - WINDOW
        cnt[tgt[r][1]] += 1
        while tgt[left][0] <= lo:
            wl = tgt[left][1]
            cnt[wl] -= 1
            if cnt[wl] == 0:
                del cnt[wl]
            left += 1
        if len(cnt) < min_backers:
            continue
        # full gate at t (evaluated only at candidate times)
        tgt_w = set(cnt.keys())
        other_w = set()
        for o in others:
            other_w |= window_wallets(ev, o, t)
        two_sided = tgt_w & other_w
        backers = tgt_w - two_sided
        if len(backers) < min_backers:
            continue
        opposers = other_w - two_sided - tgt_w
        if len(opposers) > max_opp:
            continue
        # mean/std/total over in-window backer fills (fill-count weighted)
        pairs = []
        total = 0.0
        best_rank = 999
        for i in range(left, r + 1):
            gts, w, pr, n, sz, rk = tgt[i]
            if w in backers:
                pairs.append((pr, n))
                total += sz
                if rk < best_rank:
                    best_rank = rk
        if not pairs:
            continue
        mean, std = wmean_std(pairs)
        if std > max_pstd:
            continue
        if band is not None and (mean < band[0] or mean > band[1]):
            continue
        return {"cond": cond, "oidx": oidx, "fire_ts": t, "n_backers": len(backers),
                "n_opposers": len(opposers), "mean": mean, "std": std,
                "total_usd": total, "best_rank": best_rank}
    return None


def replay(book, meta, cutoff, min_backers, max_opp, max_pstd, band):
    out = {}
    for cond, book_c in book.items():
        ev = build_events(book_c, cutoff)
        for oidx in ev:
            if (cond, oidx) not in meta:
                continue
            sig = fire_one(cond, oidx, ev, min_backers, max_opp, max_pstd, band)
            if sig:
                out[(cond, oidx)] = sig
    return out


def enrich(sigs, meta):
    """attach resolution + event key + fee; return list of resolved pick dicts."""
    picks = []
    for (cond, oidx), s in sigs.items():
        m = meta[(cond, oidx)]
        if not m["resolved"] or m["won"] is None:
            continue
        entry = s["mean"]
        won = m["won"]
        rg = regime(m["event_slug"])
        fee = REGIME_FEE.get(rg, 0.05) * (1 - entry) if m["is_sports"] or rg != "other" else 0.0
        # sports fee always applies for sports; non-sports uses regime map (crypto/other)
        if m["is_sports"]:
            fee = REGIME_FEE.get(rg, 0.03) * (1 - entry)
        ev = super_event(m["event_slug"], m["slug"])
        day = None  # fill day from fire_ts
        import datetime
        day = datetime.datetime.utcfromtimestamp(s["fire_ts"]).strftime("%Y-%m-%d")
        picks.append({
            "cond": cond, "oidx": oidx, "ev": ev, "event_slug": m["event_slug"],
            "regime": rg, "is_sports": m["is_sports"], "day": day,
            "entry": entry, "won": won, "pnl_frac": (won - entry) / entry - fee,
            "a": won - entry, "band": sn.band(entry),
            "total_usd": s["total_usd"], "best_rank": s["best_rank"],
            "fire_ts": s["fire_ts"],
        })
    return picks


def ev_clustered_mean(vals_by_ev):
    means = [sum(v) / len(v) for v in vals_by_ev.values()]
    return (sum(means) / len(means)) if means else float("nan"), len(means)


def roi_stats(picks):
    """event-clustered ROI/turn + pooled + hit + entry."""
    if not picks:
        return {"n": 0, "n_ev": 0}
    by_ev_roi = defaultdict(list)
    for p in picks:
        by_ev_roi[p["ev"]].append(p["pnl_frac"])
    roi_ev, n_ev = ev_clustered_mean(by_ev_roi)
    pooled = sum(p["pnl_frac"] for p in picks) / len(picks)
    hit = sum(p["won"] for p in picks) / len(picks)
    entry = sum(p["entry"] for p in picks) / len(picks)
    return {"n": len(picks), "n_ev": n_ev, "roi_ev": roi_ev, "roi_pooled": pooled,
            "hit": hit, "entry": entry}


def belief_blind(picks, blind_picks, rng):
    """surplus vs same-cutoff _blind band baseline, event-clustered + permutation null."""
    blind_band = defaultdict(list)
    blind_cells = defaultdict(list)
    for r in blind_picks:
        blind_band[r["band"]].append(r["a"])
        blind_cells[(r["band"], r["day"])].append((r["ev"], r["a"]))
    blind_edge = {b: sum(v) / len(v) for b, v in blind_band.items()}
    if not picks:
        return None
    triples = [(p["ev"], p["band"], p["a"]) for p in picks]
    obs, n_ev = sn.clustered_surplus(triples, blind_edge)
    if n_ev < 5:
        return {"n_ev": n_ev, "obs": obs, "underpowered": True}
    meta_cells = [(p["band"], p["day"]) for p in picks]
    draws = sn.null_pvalue(meta_cells, blind_cells, blind_edge, rng, N_PERM)
    if len(draws) < 500:
        return {"n_ev": n_ev, "obs": obs, "null_unmatchable": True}
    mu = sum(draws) / len(draws)
    sd = math.sqrt(sum((x - mu) ** 2 for x in draws) / (len(draws) - 1))
    z = (obs - mu) / sd if sd > 0 else float("nan")
    p = sum(1 for x in draws if x >= obs) / len(draws)
    lb = obs - 1.64 * sd  # belief-blind lower bound
    return {"n_ev": n_ev, "obs": obs, "null_mu": mu, "null_sd": sd, "z": z,
            "p_emp": p, "lb": lb, "draws": len(draws)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--json", default=None)
    ap.add_argument("--prod-fav", default=None,
                    help="prod_fav.tsv (cond\\toidx\\t...) — the REAL top-40 favorite set")
    ap.add_argument("--prod-fav-full", default=None,
                    help="prod_fav_full.tsv — prod favorite resolved picks for baseline ROI")
    args = ap.parse_args()

    ranks, meta, book, nfill = load(args.data)
    print(f"loaded: ranks={len(ranks)} meta={len(meta)} conds={len(book)} fill-groups={nfill}",
          file=sys.stderr)

    rng = random.Random(SEED)
    # replay favorite + _blind at each cutoff
    fav = {}
    blind = {}
    for C in CUTOFFS:
        fav[C] = replay(book, meta, C, MIN_BACKERS, MAX_OPP, MAX_PSTD, FAV_BAND)
        blind[C] = replay(book, meta, C, 1, 10**9, 10.0, None)
        print(f"  C={C}: favorite={len(fav[C])} blind={len(blind[C])}", file=sys.stderr)

    # Anchor the top-40 baseline on prod's REAL favorite set (faithful, +7% ev-clustered),
    # and purge top-40 contamination from every marginal set by subtracting BOTH the
    # replayed-40 set AND prod's real set. What remains genuinely needs rank 41..C voters.
    prod_set = set()
    if args.prod_fav:
        with open(args.prod_fav) as f:
            for line in f:
                p = line.rstrip("\n").split("\t")
                if len(p) >= 2 and p[0]:
                    try:
                        prod_set.add((p[0], int(p[1])))
                    except ValueError:
                        pass
    base_set = set(fav[40].keys()) | prod_set

    # prod baseline ROI (the real champion top-40), my exact honest metric
    prod_baseline = None
    if args.prod_fav_full:
        pp = []
        for line in open(args.prod_fav_full):
            p = line.rstrip("\n").split("\t")
            if len(p) < 9:
                continue
            _ev, slug, eslug, spo, entry, won, day, tot, br = p
            entry = float(entry); won = int(won); spo = (spo == "t")
            rg = regime(eslug or None)
            fee = (REGIME_FEE.get(rg, 0.03) if spo else REGIME_FEE.get(rg, 0.05)) * (1 - entry)
            pp.append({"ev": super_event(eslug or None, slug or None), "entry": entry,
                       "won": won, "pnl_frac": (won - entry) / entry - fee, "a": won - entry,
                       "day": day, "regime": rg, "band": sn.band(entry)})
        prod_baseline = {
            "all": roi_stats(pp),
            "A": roi_stats([p for p in pp if p["day"] <= "2026-07-01"]),
            "B": roi_stats([p for p in pp if p["day"] >= "2026-07-02"]),
            "per_day": len(pp) / max(1, len({p["day"] for p in pp})),
        }

    result = {"cutoffs": {}, "fidelity": {}, "prod_baseline": prod_baseline,
              "meta": {"n_perm": N_PERM, "seed": SEED, "prod_fav_n": len(prod_set),
              "window": "2026-06-27..2026-07-10", "fee": "corrected catrate*(1-p) entry-only",
              "entry": "at-fire initial_mean_price",
              "marginal_def": "replay_fav(C) - replay_fav(40) - prod_fav_set"}}

    # day span for turnover
    all_days = sorted({datetime_day(s["fire_ts"]) for s in fav[200].values()})
    n_days = max(1, len(all_days))

    for C in CUTOFFS:
        full = fav[C]
        full_picks = enrich(full, meta)
        blind_picks = enrich(blind[C], meta)
        marginal = {k: v for k, v in full.items() if k not in base_set}
        marg_picks = enrich(marginal, meta)

        entry = {
            "n_signals": len(full), "n_marginal": len(marginal),
            "n_days": n_days,
            "signals_per_day": len(full) / n_days,
            "marginal_per_day": len(marginal) / n_days,
            "full_roi": roi_stats(full_picks),
            "marginal_roi": roi_stats(marg_picks),
            "marginal_bb": belief_blind(marg_picks, blind_picks, random.Random(SEED + C)),
            "full_bb": belief_blind(full_picks, blind_picks, random.Random(SEED + C + 1)),
        }
        # with/without quality gates on the MARGINAL set
        marg_liq = [p for p in marg_picks if p["total_usd"] >= 1000.0]
        marg_liq_rank = [p for p in marg_liq if p["best_rank"] <= 40]
        entry["marginal_liq_roi"] = roi_stats(marg_liq)
        entry["marginal_liq_bb"] = belief_blind(marg_liq, blind_picks, random.Random(SEED + C + 2))
        entry["marginal_liq_rank_roi"] = roi_stats(marg_liq_rank)
        entry["marginal_liq_rank_bb"] = belief_blind(marg_liq_rank, blind_picks,
                                                     random.Random(SEED + C + 3))
        # by regime (marginal)
        by_reg = defaultdict(list)
        for p in marg_picks:
            by_reg[p["regime"]].append(p)
        entry["marginal_by_regime"] = {rg: roi_stats(ps) for rg, ps in by_reg.items()}
        # non-FIFWC holdout (marginal)
        non_fifwc = [p for p in marg_picks if (p["event_slug"] or "")[:5] != "fifwc"]
        entry["marginal_non_fifwc_roi"] = roi_stats(non_fifwc)
        entry["marginal_non_fifwc_bb"] = belief_blind(non_fifwc, blind_picks,
                                                      random.Random(SEED + C + 4))
        # time-split A(<=07-01) / B(>=07-02)
        A = [p for p in marg_picks if p["day"] <= "2026-07-01"]
        B = [p for p in marg_picks if p["day"] >= "2026-07-02"]
        entry["marginal_split_A"] = roi_stats(A)
        entry["marginal_split_B"] = roi_stats(B)
        result["cutoffs"][str(C)] = entry

    # multiplicity note
    result["meta"]["n_tested"] = len(CUTOFFS) - 1  # marginal sets at 60..200 (40 has no marginal)

    if args.json:
        with open(args.json, "w") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"wrote {args.json}", file=sys.stderr)
    print_report(result)


def datetime_day(ts):
    import datetime
    return datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")


def fmt(x, pct=True):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "   —  "
    return f"{x:+.2%}" if pct else f"{x}"


def print_report(r):
    print("\n" + "=" * 78)
    print("WIDE-VOTER REPLAY — marginal edge by voter cutoff (at-fire entry, corrected fee)")
    print("=" * 78)
    pb = r.get("prod_baseline")
    if pb:
        a = pb["all"]
        print(f"PROD top-40 favorite baseline (REAL set, my honest metric): "
              f"roi_ev={fmt(a['roi_ev'])} n_ev={a['n_ev']} hit={a['hit']:.0%} "
              f"| splitA={fmt(pb['A']['roi_ev'])} splitB={fmt(pb['B']['roi_ev'])} "
              f"| {pb['per_day']:.0f} picks/day")
    print(f"Marginal def: {r['meta']['marginal_def']}  (prod_fav_n={r['meta'].get('prod_fav_n')})")
    print(f"{'C':>4} {'sigs':>5} {'marg':>5} {'marg/d':>7} {'MARGINAL':>9} {'bb_surp':>8} "
          f"{'bb_LB':>7} {'p_emp':>7} {'full_roi':>9}")
    for C in CUTOFFS:
        e = r["cutoffs"][str(C)]
        mr = e["marginal_roi"]; bb = e["marginal_bb"] or {}
        fr = e["full_roi"]
        roi = fmt(mr.get("roi_ev")) if mr.get("n") else "   n/a "
        print(f"{C:>4} {e['n_signals']:>5} {e['n_marginal']:>5} {e['marginal_per_day']:>7.1f} "
              f"{roi:>9} {fmt(bb.get('obs')):>8} {fmt(bb.get('lb')):>7} "
              f"{(bb.get('p_emp') if bb.get('p_emp') is not None else float('nan')):>7.3f} "
              f"{fmt(fr.get('roi_ev')):>9}")
    print("\nGATE LAYERING on marginal set (roi_ev / n_ev / bb_LB):")
    print(f"{'C':>4} {'raw':>18} {'+liq$1k':>18} {'+liq+top40':>18}")
    for C in CUTOFFS:
        e = r["cutoffs"][str(C)]

        def cell(roi, bb):
            n = roi.get("n_ev", 0)
            lb = (bb or {}).get("lb")
            return f"{fmt(roi.get('roi_ev')):>7}/{n:>3}/{fmt(lb):>6}"
        print(f"{C:>4} {cell(e['marginal_roi'], e['marginal_bb'])} "
              f"{cell(e['marginal_liq_roi'], e['marginal_liq_bb'])} "
              f"{cell(e['marginal_liq_rank_roi'], e['marginal_liq_rank_bb'])}")
    print("\nMarginal set robustness (roi_ev / n_ev):")
    print(f"{'C':>4} {'non-FIFWC':>14} {'splitA<=0701':>14} {'splitB>=0702':>14}")
    for C in CUTOFFS:
        e = r["cutoffs"][str(C)]

        def c2(x):
            return f"{fmt(x.get('roi_ev')):>7}/{x.get('n_ev',0):>3}"
        print(f"{C:>4} {c2(e['marginal_non_fifwc_roi'])} {c2(e['marginal_split_A'])} "
              f"{c2(e['marginal_split_B'])}")
    kt = r["meta"]["n_tested"]
    print(f"\nMultiplicity: {kt} marginal cutoffs tested -> Bonferroni x{kt} before believing any p_emp.")


if __name__ == "__main__":
    main()
