#!/usr/bin/env python3
"""
UNIVERSE CURATION (beat-best-trader, Cycle 9) — score the FULL tracked trader universe on BOTH
roles, flag the leaderboard-inflated bad traders to IGNORE, and surface the genuinely durable
high-quality tail cohort. Read-only, paper-only, promotes/prunes NOTHING (the DB is never written;
every prune/add is a DEFERRED human-review recommendation).

THE TWO-ROLE NUANCE (Cycle-8, load-bearing — do NOT violate):
  * CONSENSUS BACKER — feeds the favorite-consensus STANDARD. The favorite edge RIDES ON
    high-volume/MM-flagged backers; screening them out turned the edge NEGATIVE. So a wallet being
    MM/high-volume is NOT grounds to prune it — U5 guard-checks backer-criticality separately.
  * TAIL / COPY CANDIDATE — a durable directional predictor we'd tail. Curate aggressively HERE:
    long-term, consistent, high REALIZABLE ROI at OUR price, non-longshot, directional (not pure-arb).

TWO PRICE BASES, always LABELED (never conflated):
  * THEIR-PRICE SKILL  (reliability_score factor library): per-event calibration gap at the trader's
    OWN fill price, flat-shares, event-clustered. Belief-blind per-wallet null (H0: each fill won ~
    Bernoulli(fill price); null mean 0 exact). This detects skill NOW. Reused verbatim from
    scripts/reliability_score.py — no logic dup.
  * OUR-PRICE REALIZABLE (trader_scorecard reprice): copy_return at our_entry = price + FOLLOWER_TAX
    (0.013) + band_spread(band), minus FEE, event-clustered. This is the tax-gated copyable edge.
    Skill at their price does NOT imply a copyable edge at ours — that gap is the whole game.

Everything flat-SHARES, event-clustered at COALESCE(event_slug, condition_id), scored over the same
band (0.45–0.90) and window (365d) as the standing instruments so numbers reconcile. Longshot
exposure is measured over ALL resolved BUY fills (not band-restricted).

  ./universe_curation.py            # live read; writes reports/universe_scorecard.json
  ./universe_curation.py --selftest # synthetic fixtures with known answers; no DB
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
                      "reports", "universe_scorecard.json")

# ---- U3 durable-quality gate floors (FROZEN; not tuned to force any wallet in/out) ----
Q_MIN_EVENTS = 100        # long-term: charter's ">=100 events"
Q_MIN_DAYS = 20           # active days with band fills
Q_MIN_SPAN = 20           # active span (last-first day) — a real track record, not a burst
Q_POSWIN = 0.50           # positive more days than not (their-price consistency)
Q_NULL_P = 0.05           # their-price skill beyond luck
Q_MAX_LONGSHOT = 0.35     # <=35% of ALL fills below 0.35 price (non-longshot)
Q_MIN_POS_SPORTS = 2      # cross-regime stability
Q_MIN_REALIZABLE = 0.0    # OUR-PRICE realizable copy_return must clear 0 (copyable, not just skilled)

# scoring floor to attempt the full skill factor set (below this only coarse metrics are emitted)
SKILL_MIN_EVENTS = 30


# ------------------------------------------------------------------ data
def fetch_leaderboard():
    """Per-wallet leaderboard fields (the 'inflated' inputs U2 cross-tabs against)."""
    rows = tsc.q("""
      SELECT lower(proxy_wallet) AS w, username, rank, pnl, volume, trader_type, periods, active
      FROM followed_traders""")
    out = {}
    for r in rows:
        out[r["w"]] = {
            "username": r["username"] or None,
            "rank": int(r["rank"]) if r["rank"] else None,
            "pnl": float(r["pnl"]) if r["pnl"] else None,
            "volume": float(r["volume"]) if r["volume"] else None,
            "trader_type": r["trader_type"] or None,
            "periods": r["periods"] or None,
            "active_flag": r["active"] == "t",
        }
    return out


def fetch_allfill_profile():
    """Longshot exposure + full directional profile over ALL resolved BUY fills (365d, all bands)."""
    rows = tsc.q("""
      SELECT lower(wallet) AS w,
             COUNT(*) AS n_all,
             AVG((price < 0.35)::int)::float8 AS longshot_frac,
             AVG((price >= 0.65)::int)::float8 AS favorite_frac,
             COUNT(DISTINCT COALESCE(event_slug, condition_id)) AS nev_all,
             (MAX((ts AT TIME ZONE 'UTC')::date) - MIN((ts AT TIME ZONE 'UTC')::date)) AS span_days,
             COUNT(DISTINCT sport) FILTER (WHERE sport IS NOT NULL) AS n_sports
      FROM trader_fills
      WHERE side = 'BUY' AND resolved AND outcome_won IS NOT NULL
        AND ts >= NOW() - INTERVAL '365 days'
      GROUP BY 1""")
    return {r["w"]: {"n_all": int(r["n_all"]),
                     "longshot_frac": float(r["longshot_frac"]),
                     "favorite_frac": float(r["favorite_frac"]),
                     "nev_all": int(r["nev_all"]),
                     "span_days": int(r["span_days"] or 0),
                     "n_sports": int(r["n_sports"] or 0)} for r in rows}


# ------------------------------------------------------------------ our-price realizable
def realizable_events(rows, spreads):
    """Per-event OUR-PRICE repriced returns (list) + per-day aggregation for a single wallet.
    ret_e = mean_fills((won - our_entry)/our_entry - FEE), our_entry = reprice(price)."""
    ev = defaultdict(list)
    ev_day = {}
    ev_ts = {}
    for r in rows:
        e = tsc.reprice(float(r["price"]), spreads)
        ev[r["ev"]].append((int(r["won"]) - e) / e - tsc.FEE)
        ev_day.setdefault(r["ev"], r["day"])
        ev_ts[r["ev"]] = min(ev_ts.get(r["ev"], float("inf")), float(r["ts"]))
    evs = []
    for k, rets in ev.items():
        evs.append({"ev": k, "ret": sum(rets) / len(rets), "day": ev_day[k], "ts": ev_ts[k]})
    evs.sort(key=lambda e: (e["ts"], e["ev"]))
    return evs


def realizable_metrics(rows, spreads):
    evs = realizable_events(rows, spreads)
    rets = [e["ret"] for e in evs]
    n = len(rets)
    if n == 0:
        return {"realizable_roi": None, "n_events": 0}
    roi = sum(rets) / n
    dn = [min(0.0, r) for r in rets]
    ddev = math.sqrt(sum(x * x for x in dn) / n)
    # positive-window over active days
    byday = defaultdict(list)
    for e in evs:
        byday[e["day"]].append(e["ret"])
    day_ret = [sum(v) / len(v) for v in byday.values()]
    poswin = sum(1 for x in day_ret if x > 0) / len(day_ret) if day_ret else 0.0
    maxdd, ulcer = rs._max_drawdown_ulcer(rets)
    # jackknife: drop the 3 best events (robustness to a few lucky longshot bombs)
    drop3 = sum(sorted(rets)[:-3]) / (n - 3) if n > 3 else roi
    return {"realizable_roi": roi, "realizable_downside_dev": ddev,
            "realizable_poswin_frac": poswin, "realizable_maxdd": maxdd,
            "realizable_drop_best3": drop3, "n_events": n}


# ------------------------------------------------------------------ buckets (U2)
def classify_bucket(skill, real, ls_frac, is_mm, is_bot, judgeable):
    """Priority-ordered WHY-inflated bucket for a leaderboard wallet.
    Returns (bucket, reason)."""
    if not judgeable:
        return "unjudgeable", "too few band-scored events to judge directional skill"
    if is_bot or is_mm:
        return "mm_arber", ("profit from two-sided spread/rebate capture, ~0 directional skill "
                            f"(is_mm={is_mm}, is_bot={is_bot})")
    cal = skill["cal_gap"]
    drop3 = real.get("realizable_drop_best3")
    roi = real.get("realizable_roi")
    if cal is None or cal <= 0:
        return "bad_predictor", f"negative/zero calibration gap at their OWN price (cal_gap={cal})"
    # longshot-lucky: leans on longshots AND collapses when the best 3 events are removed
    if ls_frac is not None and ls_frac > 0.5 and (drop3 is None or drop3 <= 0):
        return "longshot_lucky", (f"{ls_frac:.0%} longshot fills; realizable dies on drop-best-3 "
                                  f"(drop3={drop3})")
    if skill["null_p"] != skill["null_p"] or skill["null_p"] > Q_NULL_P:
        return "skill_within_luck", f"positive cal_gap but not beyond luck (null_p={skill['null_p']})"
    if roi is None or roi <= 0:
        return "skilled_not_copyable", (f"real skill at THEIR price (cal_gap={cal:+.3f}) but "
                                        f"realizable<=0 at OUR price (roi={roi}) — tax-gated")
    return "genuinely_skilled", f"positive & copyable (cal_gap={cal:+.3f}, realizable_roi={roi:+.3f})"


# ------------------------------------------------------------------ quality gate (U3)
def quality_gate(rec):
    """Durable-quality TAIL screen over the FULL scorecard record. ALL must clear."""
    s = rec.get("skill") or {}
    r = rec.get("realizable") or {}
    checks = {
        "longterm_events": (s.get("n_events") or 0) >= Q_MIN_EVENTS,
        "longterm_days": (s.get("n_days") or 0) >= Q_MIN_DAYS,
        "active_span": (rec.get("span_days") or 0) >= Q_MIN_SPAN,
        "directional_not_mm": not rec.get("is_mm"),
        "directional_not_bot": not rec.get("is_bot"),
        "positive_skill": (s.get("cal_gap") or 0) > 0,
        "skill_beyond_luck": (s.get("null_p") is not None and s.get("null_p") == s.get("null_p")
                              and s.get("null_p") <= Q_NULL_P),
        "consistency_poswin": (s.get("pos_window_frac") or 0) >= Q_POSWIN,
        "cross_sport_stable": (s.get("n_pos_sports") or 0) >= Q_MIN_POS_SPORTS,
        "both_halves_positive": bool(s.get("both_halves_pos")),
        "non_longshot": (rec.get("longshot_frac") is not None
                         and rec["longshot_frac"] <= Q_MAX_LONGSHOT),
        "realizable_copyable": (r.get("realizable_roi") is not None
                                and r["realizable_roi"] > Q_MIN_REALIZABLE),
    }
    fails = [k for k, v in checks.items() if not v]
    return (len(fails) == 0), fails, checks


# ------------------------------------------------------------------ live
def build(rows, micro, bots, lb, allprof, spreads):
    by_wallet = defaultdict(list)
    for r in rows:
        by_wallet[r["wallet"]].append(r)

    records = {}
    # union of every tracked wallet (from leaderboard) with any that have fills
    wallets = set(lb) | set(by_wallet) | set(allprof)
    for w in wallets:
        rs_rows = by_wallet.get(w, [])
        n_band_ev = len({r["ev"] for r in rs_rows})
        is_mm = tsc.is_mm(micro.get(w, {"rtr": 0, "sbr": 0, "tsr": 0}))
        is_bot = bots.get(w) == "bot"
        prof = allprof.get(w, {})
        rec = {
            "wallet": w,
            "username": lb.get(w, {}).get("username"),
            "leaderboard": lb.get(w),
            "is_mm": is_mm, "is_bot": is_bot,
            "micro": {k: round(v, 4) for k, v in micro.get(w, {}).items()},
            "n_band_events": n_band_ev,
            "n_all_fills": prof.get("n_all"),
            "n_all_events": prof.get("nev_all"),
            "span_days": prof.get("span_days"),
            "longshot_frac": prof.get("longshot_frac"),
            "favorite_frac": prof.get("favorite_frac"),
            "n_sports_all": prof.get("n_sports"),
        }
        # OUR-PRICE realizable (any band events)
        rec["realizable"] = realizable_metrics(rs_rows, spreads) if rs_rows else {
            "realizable_roi": None, "n_events": 0}
        # THEIR-PRICE skill factor set (only when the power floor is cleared)
        if n_band_ev >= SKILL_MIN_EVENTS:
            rec["skill"] = rs.score_wallet(rs_rows)
        else:
            rec["skill"] = None
        judgeable = rec["skill"] is not None
        rec["judgeable"] = judgeable
        bucket, reason = classify_bucket(rec["skill"] or {}, rec["realizable"],
                                         rec.get("longshot_frac"), is_mm, is_bot, judgeable)
        rec["bucket"], rec["bucket_reason"] = bucket, reason
        gpass, gfails, gchecks = quality_gate(rec)
        rec["quality_pass"], rec["quality_fails"], rec["quality_checks"] = gpass, gfails, gchecks
        records[w] = rec
    return records


def _rnd(o):
    if isinstance(o, float):
        if math.isnan(o):
            return None
        if math.isinf(o):
            return "inf" if o > 0 else "-inf"
        return round(o, 5)
    if isinstance(o, dict):
        return {k: _rnd(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_rnd(v) for v in o]
    return o


def run_live():
    spreads = tsc.fetch_band_spreads()
    rows = rs.fetch_fills()
    micro = tsc.fetch_micro()
    bots = tsc.fetch_bot_flags()
    lb = fetch_leaderboard()
    allprof = fetch_allfill_profile()
    records = build(rows, micro, bots, lb, allprof, spreads)

    # aggregate persistence (H1->H2 corr) over the durable cohort's band fills, where estimable
    persistence = tsc.persistence(rows, spreads, micro, exclude_mm=False)

    n_tracked = len(lb)
    judgeable = [r for r in records.values() if r["judgeable"]]
    shortlist = sorted((r for r in records.values() if r["quality_pass"]),
                       key=lambda r: -(r["realizable"]["realizable_roi"] or -9))

    # bucket tally over judgeable leaderboard wallets
    bucket_tally = defaultdict(int)
    for r in judgeable:
        bucket_tally[r["bucket"]] += 1

    out = {
        "meta": {
            "cycle": 9, "band": [tsc.BAND_LO, tsc.BAND_HI], "window_days": tsc.WINDOW_DAYS,
            "follower_tax": tsc.FOLLOWER_TAX, "fee": tsc.FEE,
            "band_spreads": {str(k): round(v, 4) for k, v in sorted(spreads.items())},
            "quality_floors": {"min_events": Q_MIN_EVENTS, "min_days": Q_MIN_DAYS,
                               "min_span": Q_MIN_SPAN, "poswin": Q_POSWIN, "null_p": Q_NULL_P,
                               "max_longshot": Q_MAX_LONGSHOT, "min_pos_sports": Q_MIN_POS_SPORTS,
                               "min_realizable": Q_MIN_REALIZABLE},
            "n_tracked": n_tracked, "n_with_fills": len([r for r in records.values()
                                                         if (r["n_all_fills"] or 0) > 0]),
            "n_judgeable": len(judgeable), "n_quality_pass": len(shortlist),
            "roles": "CONSENSUS-BACKER (do not prune for MM/volume) vs TAIL/COPY (curate here)",
            "labels": "skill=THEIR price (detect now); realizable=OUR price (tax-gated copyable)",
        },
        "bucket_tally_judgeable": dict(bucket_tally),
        "persistence_h1h2": _rnd(persistence),
        "quality_cohort": [_rnd(r) for r in shortlist],
        "records": [_rnd(r) for r in sorted(records.values(),
                    key=lambda r: -((r["skill"] or {}).get("cal_gap") or -9)
                    if r["judgeable"] else 9)],
    }
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w") as f:
        json.dump(out, f, indent=2, default=str)

    print(f"tracked={n_tracked}  with_fills={out['meta']['n_with_fills']}  "
          f"judgeable(>= {SKILL_MIN_EVENTS} band ev)={len(judgeable)}  "
          f"quality_pass={len(shortlist)}")
    print("bucket tally (judgeable):", dict(bucket_tally))
    print(f"\nQUALITY COHORT (durable TAIL screen, ranked by OUR-PRICE realizable_roi) n={len(shortlist)}")
    hdr = (f"  {'name':<20}{'ev':>5}{'d':>4}{'span':>5}{'cal_gap':>9}{'null_p':>8}"
           f"{'real_roi':>9}{'drop3':>8}{'ls%':>6}{'pw%':>6}{'sports':>7}")
    print(hdr)
    for r in shortlist:
        s, rl = r["skill"], r["realizable"]
        nm = (r["username"] or r["wallet"][:12])[:20]
        print(f"  {nm:<20}{s['n_events']:>5}{s['n_days']:>4}{r['span_days']:>5}"
              f"{s['cal_gap']:>+9.3f}{s['null_p']:>8.4f}{rl['realizable_roi']:>+9.3f}"
              f"{rl['realizable_drop_best3']:>+8.3f}{r['longshot_frac']*100:>5.0f}%"
              f"{s['pos_window_frac']*100:>5.0f}%{s['n_pos_sports']:>7}")
    print(f"\nwrote {REPORT}")
    return out


# ------------------------------------------------------------------ selftest
def selftest():
    spreads = {}  # reprice = price + tax (0.013)

    def mk(wallet, n, hit, price=0.70, sport="soccer", days=25, ev_prefix=None):
        rows = []
        pre = ev_prefix or wallet
        for i in range(n):
            won = 1 if (i * int(hit * 100)) % 100 < hit * 100 else 0
            rows.append({"wallet": wallet, "ev": f"{pre}-e{i}", "day": f"2026-06-{(i % days)+1:02d}",
                         "ts": i, "price": price, "won": won, "sport": sport})
        return rows

    # SKILLED + COPYABLE: hits 0.86 at 0.70 across 2 sports → cal_gap>0, realizable>0 (tax 1.3c),
    # 110 events, 25 days, both halves positive, cross-sport → quality PASS.
    n = 110
    sk = (mk("good", n // 2, 0.86, 0.70, "soccer", 25, "good-soc")
          + mk("good", n - n // 2, 0.86, 0.66, "tennis", 25, "good-ten"))
    # NOISE at own price: hits ~price → cal_gap ~ 0 → bad_predictor, quality FAIL.
    noise = mk("noise", 110, 0.70, 0.70, "soccer", 25)
    # SKILLED-NOT-COPYABLE: small edge eaten by tax → cal_gap>0 tiny, realizable<0.
    thin = (mk("thin", 55, 0.715, 0.70, "soccer", 25, "thin-soc")
            + mk("thin", 55, 0.715, 0.66, "tennis", 25, "thin-ten"))

    rows = sk + noise + thin
    micro = {"good": {"rtr": 0.02, "sbr": 0.03, "tsr": 0.01},
             "noise": {"rtr": 0.02, "sbr": 0.03, "tsr": 0.01},
             "thin": {"rtr": 0.02, "sbr": 0.03, "tsr": 0.01},
             "arb": {"rtr": 0.9, "sbr": 0.9, "tsr": 0.9}}
    bots = {}
    lb = {w: {"username": w, "rank": 5, "pnl": 1e6, "volume": 1e7, "trader_type": "human",
              "periods": "WEEK", "active_flag": True} for w in ("good", "noise", "thin", "arb")}
    # arb: MM-flagged skilled wallet with fills → must bucket mm_arber, never quality-pass.
    rows += mk("arb", 110, 0.86, 0.70, "soccer", 25)
    allprof = {w: {"n_all": 200, "longshot_frac": 0.1, "favorite_frac": 0.6, "nev_all": 110,
                   "span_days": 25, "n_sports": 2} for w in ("good", "noise", "thin", "arb")}

    recs = build(rows, micro, bots, lb, allprof, spreads)
    assert recs["good"]["quality_pass"], f"good must pass: {recs['good']['quality_fails']}"
    assert recs["good"]["bucket"] == "genuinely_skilled", recs["good"]["bucket"]
    assert not recs["noise"]["quality_pass"] and recs["noise"]["bucket"] in (
        "bad_predictor", "skill_within_luck"), recs["noise"]["bucket"]
    assert not recs["thin"]["quality_pass"], "thin (tax-eaten) must fail quality"
    assert recs["thin"]["realizable"]["realizable_roi"] < recs["good"]["realizable"]["realizable_roi"]
    assert recs["arb"]["bucket"] == "mm_arber" and not recs["arb"]["quality_pass"], \
        f"arb must be mm_arber & fail: {recs['arb']['bucket']}"
    # longshot-lucky bucket: >50% longshots, marginally positive cal carried by a few longshot
    # bombs, so realizable DIES on drop-best-3 (>=30 events to be judgeable).
    ll = []
    for i in range(32):  # small losses at cheap price
        ll.append({"wallet": "ll", "ev": f"ll-e{i}", "day": f"2026-06-{(i % 25)+1:02d}",
                   "ts": i, "price": 0.20, "won": 0, "sport": "soccer"})
    for i in range(8):   # a handful of huge longshot wins carry the headline
        ll.append({"wallet": "ll", "ev": f"ll-w{i}", "day": "2026-06-20", "ts": 500 + i,
                   "price": 0.15, "won": 1, "sport": "tennis"})
    recs2 = build(ll, {"ll": {"rtr": 0, "sbr": 0, "tsr": 0}}, {},
                  {"ll": {"username": "ll", "rank": 3, "pnl": 5e6, "volume": 1e7,
                          "trader_type": "human", "periods": "WEEK", "active_flag": True}},
                  {"ll": {"n_all": 74, "longshot_frac": 0.95, "favorite_frac": 0.0, "nev_all": 74,
                          "span_days": 25, "n_sports": 2}}, spreads)
    assert recs2["ll"]["bucket"] == "longshot_lucky", recs2["ll"]["bucket"]
    # unjudgeable: a wallet with <30 band events
    recs3 = build(mk("tiny", 10, 0.9, 0.70, "soccer", 5),
                  {"tiny": {"rtr": 0, "sbr": 0, "tsr": 0}}, {},
                  {"tiny": {"username": "tiny", "rank": 1, "pnl": 9e6, "volume": 1e8,
                            "trader_type": "human", "periods": "WEEK", "active_flag": True}},
                  {"tiny": {"n_all": 10, "longshot_frac": 0.1, "favorite_frac": 0.6, "nev_all": 10,
                            "span_days": 5, "n_sports": 1}}, spreads)
    assert recs3["tiny"]["bucket"] == "unjudgeable" and not recs3["tiny"]["judgeable"]
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
