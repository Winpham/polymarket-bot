#!/usr/bin/env python3
"""
RELIABILITY FACTOR LIBRARY + GATED COMPOSITE (Thread R1, cycle-3 reliability-portfolio run).

The reframe (TRADER-RELIABILITY-PORTFOLIO-PLAN.md): our prior "everyone is negative" verdict was an
OBJECTIVE-FUNCTION artifact (variance-punishing, our-price, thin-data LB), not a fact. 46% of
≥30-event traders are POSITIVE at their own price. This instrument selects on SKILL × RELIABILITY at
THE TRADER'S OWN FILL PRICE (copyability at OUR price is a separate downstream filter, Thread R3), via
a GATED composite (clear a floor on EVERY axis, then rank qualifiers by a risk-adjusted-consistency
metric — Sortino) — NOT a variance-punished weighted sum.

PRICE / UNIT. Everything is at the trader's own fill price, flat-SHARES, event-clustered at
COALESCE(event_slug, condition_id). Per-event return r_e = mean_fills(outcome_won - price) — the
per-$1-face-share P&L, which is exactly the per-event CALIBRATION GAP (realized hit-rate minus the
price paid). No follower tax, no reprice, no fee: this measures the trader's skill, not our copy cost.

FACTORS (per wallet, event-clustered, their price):
  RISK/VARIANCE  downside deviation (Sortino denom), max-drawdown + Ulcer index of the flat-shares
                 cumulative-equity curve, tail CVaR5. (NOT per-bet sd — irreducible in binaries; we
                 measure smoothness of the AGGREGATE.)
  CONSISTENCY    positive-window fraction (share of active DAYS with positive clustered return);
                 CALIBRATION GAP (the +EV-by-skill signal); clustered-loss-streak (max consec neg days).
  STRENGTH       best (sport x band) cell calibration-gap edge + skill concentration (share of positive
                 PnL from the top cell); DIRECTIONAL only (MM/bot wallets excluded via the same screen
                 as trader_scorecard — strength must come from prediction, not two-sided rebate capture).
  CONFIDENCE     n_events, n_days, cross-regime stability (positive in >=2 disjoint sports AND both
                 time-halves), and a per-wallet BELIEF-BLIND NULL: under H0 each fill's outcome ~
                 Bernoulli(their fill price) (a fair-coin at the price they paid), so the calibration
                 gap has null MEAN = 0 EXACTLY; sigma is analytic (sum of price*(1-price) variance,
                 event-clustered). p = P(gap >= observed | H0). This is the exact "do they beat the
                 prices they pay by more than luck" skill test — no threshold tuned, mean pinned at 0.

GATE (enter the shortlist iff ALL): n_events>=30 AND n_days>=5 AND directional (not MM, not bot) AND
  cal_gap>0 AND null_p<=0.05 AND pos_window_frac>=0.50 AND >=2 positive disjoint sports AND both
  time-halves positive. Qualifiers ranked by SORTINO (cal_gap / downside_dev); cal_gap-per-drawdown
  reported as a secondary. Gating (not averaging) is what stops a huge-but-lumpy PnL wallet or a
  one-week wonder from ranking above a smooth consistent specialist.

SANITY (printed): the durable specialists (johndegen, Sportbetting76, master-wuji, PatienceCapital,
  sport-intelligence) should surface on the shortlist; lumpy high-PnL arbers / one-week wonders should not.

Read-only, paper-only, promotes nothing. Emits reports/reliability_score.json.
  ./reliability_score.py            # live read
  ./reliability_score.py --selftest # synthetic fixtures with known answers; no DB
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
                      "reports", "reliability_score.json")

# ---- gate floors (frozen; NOT tuned to force any wallet in/out) ----
MIN_EVENTS = 30          # charter's ">=30 resolved events" power floor
MIN_DAYS = 5             # a positive-window / time-half split needs days
NULL_P_BAR = 0.05        # per-wallet belief-blind skill null
POSWIN_BAR = 0.50        # positive more days than not
MIN_POS_SPORTS = 2       # cross-regime stability: positive in >=2 disjoint sports
MIN_CELL_EV = 8          # a (sport x band) cell / a sport needs >=8 events to count
CVAR_TAIL = 0.05

# Named durable specialists (username -> wallet) for the sanity print (from followed_traders).
KNOWN = {
    "johndegen":          "0x4f1af091d122e76fa5b1a8ec115c554ec481bc89",
    "Sportbetting76":     "0xe5241830e8876c115d7dc8311ad9f43d85fdd34f",
    "master-wuji":        "0x96a3a4d0f0a91074a43ce8dc39d1f092a717d944",
    "PatienceCapital":    "0x34f62ce5beaf9b3b325726ec4b6c733df8534535",
    "sport-intelligence": "0xc289082ddba5a95e95efa216adbed7cc8ab4ab37",
}


def fetch_fills():
    """One row per scored fill with the trader's own price + sport + genuine fill ts."""
    return tsc.q(f"""
      SELECT lower(wallet) AS wallet, COALESCE(event_slug, condition_id) AS ev,
             (ts AT TIME ZONE 'UTC')::date AS day, EXTRACT(EPOCH FROM ts) AS ts,
             price, outcome_won::int AS won, COALESCE(sport, 'other') AS sport
      FROM trader_fills
      WHERE side = 'BUY' AND resolved AND outcome_won IS NOT NULL
        AND price >= {tsc.BAND_LO} AND price < {tsc.BAND_HI}
        AND ts >= NOW() - INTERVAL '{tsc.WINDOW_DAYS} days'""")


def _events(rows):
    """Collapse a wallet's fills to per-event records (event-clustered at their price).
    Returns list of dicts sorted by time: {ev, ret, price, sport, band, day, ts, n_fills, sumvar}."""
    acc = defaultdict(list)
    for r in rows:
        acc[r["ev"]].append(r)
    evs = []
    for ev, fs in acc.items():
        n = len(fs)
        won_mean = sum(int(f["won"]) for f in fs) / n
        price_mean = sum(float(f["price"]) for f in fs) / n
        # null variance contribution of this event's mean-won under Bernoulli(price):
        #   Var(mean_f won) = (1/n^2) sum_f p_f(1-p_f)
        sumvar = sum(float(f["price"]) * (1.0 - float(f["price"])) for f in fs) / (n * n)
        ts0 = min(float(f["ts"]) for f in fs)
        # modal sport + day of the earliest fill (deterministic tiebreak)
        earliest = min(fs, key=lambda f: (float(f["ts"]), f["sport"]))
        evs.append({"ev": ev, "ret": won_mean - price_mean, "price": price_mean,
                    "sport": earliest["sport"], "band": tsc.band(price_mean),
                    "day": earliest["day"], "ts": ts0, "n_fills": n, "sumvar": sumvar})
    evs.sort(key=lambda e: (e["ts"], e["ev"]))
    return evs


def _max_drawdown_ulcer(rets):
    """Max drawdown + Ulcer index of the flat-shares cumulative-equity curve (return units)."""
    peak = 0.0
    eq = 0.0
    maxdd = 0.0
    dd2 = []
    for r in rets:
        eq += r
        peak = max(peak, eq)
        dd = peak - eq            # >= 0, in return units
        maxdd = max(maxdd, dd)
        dd2.append(dd * dd)
    ulcer = math.sqrt(sum(dd2) / len(dd2)) if dd2 else 0.0
    return maxdd, ulcer


def _cvar(rets, tail=CVAR_TAIL):
    if not rets:
        return 0.0
    k = max(1, int(round(tail * len(rets))))
    worst = sorted(rets)[:k]
    return sum(worst) / len(worst)


def _pos_window(evs):
    """Positive-window fraction over active DAYS + max consecutive-negative-day streak."""
    byday = defaultdict(list)
    for e in evs:
        byday[e["day"]].append(e["ret"])
    days = sorted(byday)
    day_ret = [sum(byday[d]) / len(byday[d]) for d in days]
    pos_frac = sum(1 for x in day_ret if x > 0) / len(day_ret) if day_ret else 0.0
    streak = mx = 0
    for x in day_ret:
        streak = streak + 1 if x < 0 else 0
        mx = max(mx, streak)
    return pos_frac, mx, len(days)


def _cells(evs):
    """(sport x band) calibration-gap cells (>=MIN_CELL_EV events): best gap + skill concentration."""
    cell = defaultdict(list)
    sport = defaultdict(list)
    for e in evs:
        cell[(e["sport"], e["band"])].append(e["ret"])
        sport[e["sport"]].append(e["ret"])
    cells = {f"{s}|b{b}": {"gap": sum(v) / len(v), "n": len(v)}
             for (s, b), v in cell.items() if len(v) >= MIN_CELL_EV}
    best = max(cells.items(), key=lambda kv: kv[1]["gap"], default=(None, {"gap": None, "n": 0}))
    # skill concentration = top positive-PnL cell's share of total positive-cell PnL.
    pos_pnl = {k: v["gap"] * v["n"] for k, v in cells.items() if v["gap"] > 0}
    tot = sum(pos_pnl.values())
    conc = (max(pos_pnl.values()) / tot) if tot > 0 else None
    # cross-sport stability: sports with >=MIN_CELL_EV events and positive clustered gap
    pos_sports = [s for s, v in sport.items() if len(v) >= MIN_CELL_EV and sum(v) / len(v) > 0]
    return cells, best[0], (best[1]["gap"] if best[0] else None), conc, sorted(pos_sports)


def _null_p(evs):
    """Belief-blind per-wallet skill null. H0: each fill's outcome ~ Bernoulli(its fill price).
    Then cal_gap = mean_e(won_mean_e - price_mean_e) has null MEAN = 0 EXACTLY, and
    Var(cal_gap) = (1/n_events^2) sum_e Var(mean_won_e) = (1/n_events^2) sum_e sumvar_e.
    p = P(cal_gap >= observed | H0) via the normal (CLT over events). No parameter tuned; the
    null mean is pinned at 0 by construction, so this cannot be gamed by a threshold."""
    n = len(evs)
    if n == 0:
        return float("nan"), float("nan")
    obs = sum(e["ret"] for e in evs) / n
    var = sum(e["sumvar"] for e in evs) / (n * n)
    sd = math.sqrt(var)
    if sd == 0:
        return obs, (0.0 if obs > 0 else 1.0)
    z = obs / sd
    p = 0.5 * math.erfc(z / math.sqrt(2.0))
    return z, p


def score_wallet(rows):
    return score_evs(_events(rows))


def score_evs(evs):
    """Score from pre-built per-event records (shape of _events output). Split out of score_wallet
    so an event-pre-aggregated pipeline (drawdown_optimization.py) can reuse the IDENTICAL math."""
    rets = [e["ret"] for e in evs]
    n = len(rets)
    n_fills = sum(e["n_fills"] for e in evs)
    n_days = len({e["day"] for e in evs})
    cal_gap = sum(rets) / n if n else float("nan")
    dn = [min(0.0, r) for r in rets]
    downside_dev = math.sqrt(sum(x * x for x in dn) / n) if n else float("nan")
    sortino = (cal_gap / downside_dev) if downside_dev > 0 else (
        float("inf") if cal_gap > 0 else float("nan"))
    maxdd, ulcer = _max_drawdown_ulcer(rets)
    cvar5 = _cvar(rets)
    pos_frac, loss_streak, n_win = _pos_window(evs)
    cells, best_cell, best_gap, conc, pos_sports = _cells(evs)
    # time-halves (by time-ordered events)
    half = n // 2
    h1 = rets[:half]
    h2 = rets[half:]
    h1g = sum(h1) / len(h1) if h1 else float("nan")
    h2g = sum(h2) / len(h2) if h2 else float("nan")
    both_halves_pos = (h1g > 0 and h2g > 0)
    z, null_p = _null_p(evs)
    cal_per_dd = (cal_gap / (maxdd / n)) if (n and maxdd > 0) else (
        float("inf") if cal_gap > 0 else None)
    return {
        "n_events": n, "n_fills": n_fills, "n_days": n_days,
        "cal_gap": cal_gap, "sortino": sortino, "downside_dev": downside_dev,
        "max_drawdown": maxdd, "ulcer": ulcer, "cvar5": cvar5,
        "pos_window_frac": pos_frac, "loss_streak_days": loss_streak,
        "best_cell": best_cell, "best_cell_gap": best_gap, "skill_concentration": conc,
        "n_pos_sports": len(pos_sports), "pos_sports": pos_sports,
        "half1_gap": h1g, "half2_gap": h2g, "both_halves_pos": both_halves_pos,
        "null_z": z, "null_p": null_p, "cal_gap_per_drawdown": cal_per_dd,
    }


def gate(s, is_mm, is_bot):
    """Gated composite: clear a floor on EVERY axis to enter the shortlist. Returns (pass, reasons)."""
    checks = {
        "power_events": s["n_events"] >= MIN_EVENTS,
        "power_days": s["n_days"] >= MIN_DAYS,
        "directional_not_mm": not is_mm,
        "directional_not_bot": not is_bot,
        "positive_skill": s["cal_gap"] > 0,
        "skill_beyond_luck": (s["null_p"] == s["null_p"]) and s["null_p"] <= NULL_P_BAR,
        "consistency_poswin": s["pos_window_frac"] >= POSWIN_BAR,
        "cross_sport_stable": s["n_pos_sports"] >= MIN_POS_SPORTS,
        "both_halves_positive": s["both_halves_pos"],
    }
    fails = [k for k, v in checks.items() if not v]
    return (len(fails) == 0), fails, checks


def _fnum(x, spec="+.3f"):
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "  n/a" if x is None or math.isnan(x) else ("  inf" if x > 0 else " -inf")
    return format(x, spec)


# ---------------------------------------------------------------- selftest
def selftest():
    import random
    rng = random.Random(7)

    def mk(wallet, n, hit, price=0.70, sport="soccer", days=20, start=0, events_per_day=1,
           won_seq=None):
        """n events; each event = 1 fill (event id unique). hit = P(win) if won_seq None."""
        rows = []
        for i in range(n):
            won = won_seq[i] if won_seq is not None else (1 if rng.random() < hit else 0)
            d = start + (i // events_per_day) % days
            rows.append({"wallet": wallet, "ev": f"{wallet}-{sport}-e{i}", "day": f"2026-06-{d:02d}",
                         "ts": start * 1e6 + i, "price": price, "won": won, "sport": sport})
        return rows

    # (1) SKILLED wallet: pays 0.70, hits ~0.82, across 2 sports, both halves positive → PASS gate.
    n = 240
    won = [1 if (i * 82) % 100 < 82 else 0 for i in range(n)]
    skilled = (mk("skilled", n // 2, 0.82, price=0.70, sport="soccer", days=12, won_seq=won[:n // 2])
               + mk("skilled", n // 2, 0.82, price=0.65, sport="tennis", days=12,
                    won_seq=won[n // 2:]))
    s = score_wallet(skilled)
    ok, fails, _ = gate(s, is_mm=False, is_bot=False)
    assert ok, f"skilled should PASS gate, fails={fails} (cal_gap={s['cal_gap']:.3f}, p={s['null_p']:.3g})"
    assert s["cal_gap"] > 0.05 and s["null_p"] < 0.01 and s["sortino"] > 0

    # (2) FAIR (fair-coin at price) wallet: won ~ Bernoulli(price) exactly → cal_gap ~ 0, null p high → FAIL.
    fair = mk("fair", 240, 0.70, price=0.70, sport="soccer", days=12)
    fair += mk("fair", 120, 0.70, price=0.70, sport="tennis", days=12)
    sf = score_wallet(fair)
    okf, failsf, _ = gate(sf, is_mm=False, is_bot=False)
    assert not okf, f"fair-coin wallet must FAIL (cal_gap={sf['cal_gap']:.3f}, p={sf['null_p']:.3g})"
    assert "skill_beyond_luck" in failsf or "positive_skill" in failsf

    # (3) LUMPY wallet: one giant longshot win carries a positive mean but most days negative →
    #     fails the consistency (positive-window) gate even though cal_gap>0.
    lump = []
    for i in range(60):                      # 60 losing days at price 0.55 (all losses)
        lump.append({"wallet": "lumpy", "ev": f"lumpy-e{i}", "day": f"2026-06-{(i % 20)+1:02d}",
                     "ts": i, "price": 0.55, "won": 0, "sport": "soccer"})
    for i in range(6):                       # a few huge wins at cheap price on a couple of days
        lump.append({"wallet": "lumpy", "ev": f"lumpy-w{i}", "day": "2026-06-25",
                     "ts": 1000 + i, "price": 0.46, "won": 1, "sport": "tennis"})
    sl = score_wallet(lump)
    okl, failsl, _ = gate(sl, is_mm=False, is_bot=False)
    assert not okl and "consistency_poswin" in failsl, f"lumpy must fail consistency: {failsl}"

    # (4) MM wallet: genuinely skilled but flagged market-maker → excluded (directional gate).
    okm, failsm, _ = gate(s, is_mm=True, is_bot=False)
    assert not okm and "directional_not_mm" in failsm

    # (5) null mean is pinned at 0: a wallet with won == round(price) noise gives p ~ uniform-ish,
    #     never systematically < 0.05. Check a fair wallet's z is small.
    assert abs(sf["null_z"]) < 3.0, f"fair wallet null_z should be small: {sf['null_z']}"

    # (6) single-sport skilled wallet fails cross_sport_stable (needs >=2 positive sports).
    one = mk("onesport", 120, 0.82, price=0.70, sport="soccer", days=12,
             won_seq=[1 if (i * 82) % 100 < 82 else 0 for i in range(120)])
    oko, failso, _ = gate(score_wallet(one), is_mm=False, is_bot=False)
    assert not oko and "cross_sport_stable" in failso, f"one-sport must fail cross-sport: {failso}"

    print("selftest OK")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return

    rows = fetch_fills()
    micro = tsc.fetch_micro()
    bots = tsc.fetch_bot_flags()

    by_wallet = defaultdict(list)
    for r in rows:
        by_wallet[r["wallet"]].append(r)

    scored = {}
    for w, rs in by_wallet.items():
        # only score wallets with a chance of clearing the event floor (cheap prefilter on fills)
        if len({r["ev"] for r in rs}) < MIN_EVENTS:
            continue
        s = score_wallet(rs)
        is_mm = tsc.is_mm(micro.get(w, {"rtr": 0, "sbr": 0, "tsr": 0}))
        is_bot = bots.get(w) == "bot"
        passed, fails, checks = gate(s, is_mm, is_bot)
        scored[w] = {"wallet": w, **s, "is_mm": is_mm, "is_bot": is_bot,
                     "gate_pass": passed, "gate_fails": fails, "gate_checks": checks}

    shortlist = sorted((v for v in scored.values() if v["gate_pass"]),
                       key=lambda v: -(v["sortino"] if v["sortino"] == v["sortino"] else -9))

    # username map for readability / sanity
    name_rows = tsc.q("SELECT lower(proxy_wallet) AS w, username FROM followed_traders")
    names = {r["w"]: r["username"] for r in name_rows}

    def rnd(v):
        if isinstance(v, float):
            if math.isinf(v):
                return "inf" if v > 0 else "-inf"
            if math.isnan(v):
                return None
            return round(v, 5)
        return v

    out = {
        "meta": {"price": "trader_own_fill", "unit": "flat_shares_per_event_calibration_gap",
                 "band": [tsc.BAND_LO, tsc.BAND_HI], "window_days": tsc.WINDOW_DAYS,
                 "gate_floors": {"min_events": MIN_EVENTS, "min_days": MIN_DAYS,
                                 "null_p_bar": NULL_P_BAR, "poswin_bar": POSWIN_BAR,
                                 "min_pos_sports": MIN_POS_SPORTS, "min_cell_ev": MIN_CELL_EV},
                 "null": "per-wallet Bernoulli(fill price); H0 mean=0 exact; analytic sigma; one-sided",
                 "n_wallets_scored": len(scored), "n_shortlist": len(shortlist),
                 "charter": "TRADER-RELIABILITY-PORTFOLIO-PLAN.md"},
        "shortlist": [{"username": names.get(v["wallet"]),
                       **{k: rnd(x) for k, x in v.items() if k != "gate_checks"}}
                      for v in shortlist],
        "all_scored": sorted(({"username": names.get(v["wallet"]),
                               **{k: rnd(x) for k, x in v.items() if k != "gate_checks"}}
                              for v in scored.values()),
                             key=lambda v: -(v["cal_gap"] if v["cal_gap"] is not None else -9)),
    }
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w") as f:
        json.dump(out, f, indent=2, default=str)

    # ---- console ----
    print(f"scored {len(scored)} wallets (>= {MIN_EVENTS} events, trailing {tsc.WINDOW_DAYS}d, their price)")
    pos = sum(1 for v in scored.values() if v["cal_gap"] > 0)
    print(f"  positive cal_gap at their price: {pos}/{len(scored)} ({pos/max(1,len(scored)):.0%})  "
          f"— the reframe's '46% are positive' claim, on the scored band")
    print(f"\nSHORTLIST (gate-clearing, ranked by Sortino) — n={len(shortlist)}")
    hdr = (f"  {'wallet/name':<22}{'ev':>5}{'d':>4}{'cal_gap':>9}{'sortino':>8}{'maxDD':>8}"
           f"{'ulcer':>7}{'CVaR5':>8}{'pw%':>6}{'null_p':>8}{'sports':>7}{'bestcell':>16}")
    print(hdr)
    for v in shortlist:
        nm = names.get(v["wallet"]) or v["wallet"][:10]
        print(f"  {nm[:22]:<22}{v['n_events']:>5}{v['n_days']:>4}{_fnum(v['cal_gap']):>9}"
              f"{_fnum(v['sortino'],'+.2f'):>8}{_fnum(v['max_drawdown'],'.2f'):>8}"
              f"{_fnum(v['ulcer'],'.2f'):>7}{_fnum(v['cvar5'],'+.2f'):>8}"
              f"{v['pos_window_frac']*100:>5.0f}%{_fnum(v['null_p'],'.4f'):>8}"
              f"{v['n_pos_sports']:>7}{str(v['best_cell'] or '-')[:16]:>16}")

    print("\nSANITY — the named durable specialists (should surface on the shortlist):")
    set_sl = {v["wallet"] for v in shortlist}
    for nm, w in KNOWN.items():
        w = w.lower()
        if w not in scored:
            print(f"  {nm:<20} {w[:10]}  NOT SCORED (<{MIN_EVENTS} events in band/window)")
            continue
        v = scored[w]
        tag = "SHORTLIST" if w in set_sl else ("scored, gate-FAIL: " + ",".join(v["gate_fails"]))
        print(f"  {nm:<20} {w[:10]}  cal_gap {_fnum(v['cal_gap'])}  sortino {_fnum(v['sortino'],'+.2f')}"
              f"  null_p {_fnum(v['null_p'],'.4f')}  -> {tag}")

    print(f"\nwrote {REPORT}")


if __name__ == "__main__":
    main()
