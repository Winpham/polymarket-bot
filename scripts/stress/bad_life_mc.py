#!/usr/bin/env python3
"""
PHASE 2 — THE COMPOSITE "REALISTIC BAD LIFE" MONTE CARLO.

Isolated failure modes flatter the system; a real 1-3 year run has SEVERAL happening at once and
partially. This draws a WORLD and runs the ACTUAL recommended sizing policy (kelly_eighth_capped,
flat-SHARES, caps + stop-loss, on favorite) end-to-end through it.

A world = (edge-decay path lambda(t)) x (cost level 1-3x + adverse fill) x (a regime sequence with
>=1 UPSET stretch the record never saw and >=1 drought) x (missed-fire + adverse-selection rate)
x (leaderboard-cohort persistence c). Calibrated to observed favorite (band mix, entries, per-band
raw edge, slate-size distribution) THEN stressed beyond anything in the 4-day record — the whole
point (the record has no losing slate, so the empirical bootstrap CANNOT price a bad regime).

CRITICAL: the sizing (per-band Kelly fractions) is FROZEN from the good data — it is overconfident
in bad worlds, exactly as it would be live.

Outputs the full tail incl. the HUMAN FACTOR: P(a reasonable operator pulls the plug after K red
weeks) x whether that pull was CORRECT (edge truly gone) or a FALSE ALARM (edge intact, just
variance). That matrix separates "risky but survivable" from "unrunnable by a human".

Modes:
  ./bad_life_mc.py            # >=10k worlds -> reports/stress/bad_life_mc.json
  ./bad_life_mc.py --selftest # intact-world profits; costs-only world loses; caps bound DD;
                              # upset injection produces losing slates the base record lacks
"""
import json
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import selection_null as sn
import risk_engine as re
from cost_stress import favorite_events

SEED = 20260702
N_WORLDS = 10_000
HAIRCUT = 0.005
FEE = 0.02
STAKE = 100.0                 # 1 unit = $100 notional
BANKROLLS = [1_000.0, 5_000.0, 25_000.0]
KELLY_MULT = 0.125            # eighth Kelly
CAP_PER_SLATE = 3
CAP_STOP_LOSS_UNITS = 5.0
RUIN_FRAC = 0.20
DD_CEIL = 0.30
DAYS_PER_YEAR = 365
WEEKS = 52
# operator-pull rule: pull after K consecutive red review-weeks
PULL_K = 4


def calibrate(strategy="favorite"):
    """Derive the generative parameters from observed favorite (paper-only, read-only)."""
    events = favorite_events(strategy=strategy)
    kelly_full = re.kelly_by_band(
        [{"c": min(0.999, e["entry"] + HAIRCUT), "won": e["won"], "band": e["band"]}
         for e in events])
    # per-band: entry, raw edge (winrate - entry), share of events
    by_band = defaultdict(list)
    for e in events:
        by_band[e["band"]].append(e)
    bands = {}
    for b, evs in by_band.items():
        entry = float(np.mean([e["entry"] for e in evs]))
        winrate = float(np.mean([e["won"] for e in evs]))
        bands[b] = {"entry": entry, "winrate": winrate, "raw_edge": winrate - entry,
                    "share": len(evs) / len(events), "kelly_full": kelly_full.get(b, 0.0)}
    # slate-size distribution (favorites per regime x day)
    slates = defaultdict(int)
    for e in events:
        slates[e["slate"]] += 1
    sizes = np.array(sorted(slates.values()))
    return {"bands": bands, "band_keys": sorted(bands), "slate_sizes": sizes,
            "mean_slate": float(sizes.mean()), "n_events": len(events)}


def draw_world(rng):
    """Draw one world's failure parameters. Ranges pre-registered in 01-pre-registration.md."""
    # F2 decay
    decaying = rng.random() < 0.5
    hl_mo = rng.choice([3, 6, 12]) if decaying else 1e9
    # F4 cost
    hc_mult = rng.choice([1, 2, 3])
    fill = rng.choice([0.0, 0.01, 0.02])
    fee_mult = rng.choice([1, 2])
    # F5 upset regime
    pi_upset = rng.uniform(0.05, 0.20)
    upset_shock = rng.uniform(0.15, 0.30)     # favorites priced e win at e - shock (whole slate)
    # F6 drought (fraction of the year with ~no fires)
    drought_frac = rng.uniform(0.0, 0.35)
    # F8 missed-fire + adverse selection
    miss = rng.uniform(0.0, 0.40)
    adv_sel = rng.uniform(0.5, 1.0)           # captured fires keep this fraction of their edge
    # F7 cohort persistence
    cohort = rng.uniform(0.4, 1.0)
    # fire rate events/day (post-WC realistic band)
    fire_rate = rng.choice([3, 8, 20])
    return dict(hl_mo=hl_mo, hc_mult=hc_mult, fill=fill, fee_mult=fee_mult, pi_upset=pi_upset,
                upset_shock=upset_shock, drought_frac=drought_frac, miss=miss, adv_sel=adv_sel,
                cohort=cohort, fire_rate=fire_rate, decaying=decaying)


def simulate_world(cal, w, rng, B, months=12, kelly=True, edge_mult=1.0, cap_frac=None,
                   flat_frac=None):
    """Run kelly_eighth_capped (or flat-shares if kelly=False) through one world for `months`.
    cap_frac: if set (flat-shares only), stake = min(STAKE, cap_frac*bank) — the guardrail
    per-bet cap; auto-deleverages as the bankroll shrinks (a $1k bank at 2% bets $20, not $100).
    flat_frac: if set, stake = flat_frac*bank every bet — clean FIXED-% policy (overrides
    kelly/cap_frac); risk fractions become bankroll-independent (scale-invariant).
    edge_mult scales the base per-band raw edge (F1 clean-edge scenarios; Phase-3 posterior
    draws of "is the edge even real"). Returns terminal P&L, maxDD frac, min-bankroll frac,
    weekly P&L series, and edge-intact flag."""
    # Two favorite bands (4,5) -> unpack to scalars; fast inline draws (no np.random.choice).
    bk = cal["band_keys"]
    sh = np.array([cal["bands"][b]["share"] for b in bk]); sh = sh / sh.sum()
    p_hi = float(sh[-1])                                   # P(band == highest, i.e. band 5)
    lo, hi = cal["bands"][bk[0]], cal["bands"][bk[-1]]
    fee_c = FEE * w["fee_mult"]
    cpay_lo = min(0.999, lo["entry"] + HAIRCUT * w["hc_mult"] + w["fill"])
    cpay_hi = min(0.999, hi["entry"] + HAIRCUT * w["hc_mult"] + w["fill"])
    rwin_lo, rwin_hi = 1.0 / cpay_lo - 1.0 - fee_c, 1.0 / cpay_hi - 1.0 - fee_c
    rlose = -1.0 - fee_c
    f_lo, f_hi = KELLY_MULT * lo["kelly_full"], KELLY_MULT * hi["kelly_full"]
    base_mult = edge_mult * w["cohort"] * w["adv_sel"]
    sizes = cal["slate_sizes"]; nsz = len(sizes)
    mean_slate = cal["mean_slate"]
    n_days = int(DAYS_PER_YEAR * months / 12)
    drought_len = int(w["drought_frac"] * n_days)
    drought_start = int(rng.integers(0, max(1, n_days - drought_len))) if drought_len else -1
    hl_ev = w["hl_mo"] * 30 * w["fire_rate"]
    decaying = hl_ev < 1e11
    ln_half = -0.6931471805599453
    bank = B; peak = B; maxdd = 0.0; minb = B
    weekly = np.zeros(WEEKS)
    t_ev = 0; lam_sum = 0.0; lam_n = 0
    R = rng.random
    for d in range(n_days):
        in_drought = drought_start >= 0 and drought_start <= d < drought_start + drought_len
        rate = w["fire_rate"] * (0.1 if in_drought else 1.0)
        n_slates_today = rng.poisson(max(0.01, rate / mean_slate))
        week = int(d / n_days * WEEKS)
        if week >= WEEKS:
            week = WEEKS - 1
        for _s in range(int(n_slates_today)):
            size = int(sizes[int(R() * nsz)])
            is_upset = R() < w["pi_upset"]
            slate_start_bank = bank
            stopped = False
            n_bet = 0
            for _k in range(size):
                if n_bet >= CAP_PER_SLATE or stopped:
                    break
                is_hi = R() < p_hi
                entry = hi["entry"] if is_hi else lo["entry"]
                raw = hi["raw_edge"] if is_hi else lo["raw_edge"]
                lam = 2.718281828 ** (ln_half * t_ev / hl_ev) if decaying else 1.0
                t_ev += 1
                if R() < w["miss"]:
                    continue
                if is_upset:
                    p_win = entry - w["upset_shock"]
                else:
                    p_win = entry + raw * base_mult * lam
                p_win = 0.01 if p_win < 0.01 else (0.999 if p_win > 0.999 else p_win)
                lam_sum += w["cohort"] * lam; lam_n += 1
                won = R() < p_win
                if is_hi:
                    unit_ret = rwin_hi if won else rlose
                    f = f_hi
                else:
                    unit_ret = rwin_lo if won else rlose
                    f = f_lo
                if flat_frac is not None:
                    stake_amt = flat_frac * bank          # fixed % of bankroll (same every bet)
                elif kelly:
                    stake_amt = f * bank
                else:
                    stake_amt = STAKE if cap_frac is None else min(STAKE, cap_frac * bank)
                delta = stake_amt * unit_ret
                bank += delta
                weekly[week] += delta
                n_bet += 1
                if bank > peak:
                    peak = bank
                else:
                    dd = (peak - bank) / peak
                    if dd > maxdd:
                        maxdd = dd
                if bank < minb:
                    minb = bank
                # slate stop-loss: pause after slate loss exceeds 10% of slate-start bank
                # (== the -5 unit / -$500 stop at $5k; made relative so kelly is scale-invariant)
                if bank - slate_start_bank <= -0.10 * slate_start_bank:
                    stopped = True
    edge_intact = (lam_sum / lam_n if lam_n else 1.0) >= 0.5
    return {"pnl": bank - B, "maxdd": maxdd, "minb_frac": minb / B, "weekly": weekly,
            "edge_intact": bool(edge_intact), "terminal": bank}


def operator_pulls(weekly, k=PULL_K):
    """Reasonable operator pulls after k consecutive red review-weeks (cum weekly P&L < 0)."""
    run = 0
    for wk in weekly:
        if wk < 0:
            run += 1
            if run >= k:
                return True
        else:
            run = 0
    return False


def run(n_worlds=N_WORLDS, seed=SEED):
    cal = calibrate()
    rng = np.random.default_rng(seed)
    out = {"meta": {"seed": seed, "n_worlds": n_worlds, "months": 12, "pull_k": PULL_K,
                    "kelly_mult": KELLY_MULT, "bankrolls": BANKROLLS,
                    "note": "kelly_eighth_capped is scale-invariant (relative stop-loss) -> "
                            "risk FRACTIONS are bankroll-independent; only $ terminal scales",
                    "calibration": {"bands": {str(k): {kk: round(vv, 4) for kk, vv in v.items()}
                                              for k, v in cal["bands"].items()},
                                    "mean_slate": cal["mean_slate"]}},
           "by_bankroll": {}, "human_factor": {}, "policy_compare": {}}
    REF = 10_000.0
    pnl_frac, dd_arr, min_arr = [], [], []
    pull_matrix = {"pull_edge_gone": 0, "pull_edge_intact": 0,
                   "hold_edge_gone": 0, "hold_edge_intact": 0}
    underwater_weeks = []
    flat_pnl = []
    for i in range(n_worlds):
        w = draw_world(rng)
        r = simulate_world(cal, w, rng, REF, kelly=True)
        pnl_frac.append(r["pnl"] / REF)
        dd_arr.append(r["maxdd"])
        min_arr.append(r["minb_frac"])
        pulled = operator_pulls(r["weekly"])
        key = ("pull" if pulled else "hold") + ("_edge_intact" if r["edge_intact"] else "_edge_gone")
        pull_matrix[key] += 1
        cum = np.cumsum(r["weekly"])
        run_uw = mx = 0
        pk = 0.0
        for v in cum:
            pk = max(pk, v)
            if v < pk:
                run_uw += 1
                mx = max(mx, run_uw)
            else:
                run_uw = 0
        underwater_weeks.append(mx)
        rf = simulate_world(cal, w, rng, 5_000.0, kelly=False)
        flat_pnl.append(rf["pnl"])
    pnl_frac = np.array(pnl_frac); dd = np.array(dd_arr); mn = np.array(min_arr)
    p_neg = float(np.mean(pnl_frac < 0))
    p_dd = float(np.mean(dd > DD_CEIL))
    p_ruin = float(np.mean(mn <= RUIN_FRAC))
    med_dd = float(np.median(dd))
    for B in BANKROLLS:
        out["by_bankroll"][str(int(B))] = {
            "median_pnl": float(np.median(pnl_frac) * B),
            "p_net_negative_12mo": p_neg,                 # scale-invariant
            "worst_decile_terminal": float((np.percentile(pnl_frac, 10) + 1.0) * B),
            "p5_pnl": float(np.percentile(pnl_frac, 5) * B),
            "p_maxdd_over_30pct": p_dd,                   # scale-invariant
            "median_maxdd": med_dd,
            "p_ruin_20pct": p_ruin}                       # scale-invariant
    tot = sum(pull_matrix.values())
    intact_worlds = pull_matrix["pull_edge_intact"] + pull_matrix["hold_edge_intact"]
    out["human_factor"] = {
        "matrix": pull_matrix, "total": tot,
        "p_operator_pulls": (pull_matrix["pull_edge_gone"] + pull_matrix["pull_edge_intact"]) / tot,
        "p_pull_is_false_alarm_among_intact":
            (pull_matrix["pull_edge_intact"] / intact_worlds) if intact_worlds else None,
        "p_pull_is_false_alarm_among_all_pulls":
            (pull_matrix["pull_edge_intact"] /
             (pull_matrix["pull_edge_intact"] + pull_matrix["pull_edge_gone"]))
            if (pull_matrix["pull_edge_intact"] + pull_matrix["pull_edge_gone"]) else None,
        "median_longest_underwater_weeks": float(np.median(underwater_weeks)),
        "p90_longest_underwater_weeks": float(np.percentile(underwater_weeks, 90))}
    fp = np.array(flat_pnl)
    out["policy_compare"] = {"flat_shares_5k": {
        "median_pnl": float(np.median(fp)), "p_net_negative": float(np.mean(fp < 0)),
        "p5_pnl": float(np.percentile(fp, 5))}}
    return out


def _print(o):
    m = o["meta"]
    print(f"COMPOSITE BAD-LIFE MC · {m['n_worlds']} worlds · 12 mo · kelly_eighth_capped · "
          f"operator pulls after {m['pull_k']} red weeks")
    print(f"{'bankroll':>10}{'med P&L':>10}{'P(net<0)':>10}{'P(DD>30%)':>11}{'medDD':>8}"
          f"{'P(ruin)':>9}{'wrst-dec term':>14}")
    for B, s in o["by_bankroll"].items():
        print(f"{'$'+B:>10}{s['median_pnl']:>+10.0f}{s['p_net_negative_12mo']:>10.1%}"
              f"{s['p_maxdd_over_30pct']:>11.1%}{s['median_maxdd']:>8.1%}"
              f"{s['p_ruin_20pct']:>9.1%}{s['worst_decile_terminal']:>+14.0f}")
    h = o["human_factor"]
    pm = h["matrix"]
    print(f"\nHUMAN-FACTOR MATRIX (B=$5k, {h['total']} worlds):")
    print(f"  PULL & edge-gone (correct kill) : {pm['pull_edge_gone']:>5}")
    print(f"  PULL & edge-intact (FALSE ALARM): {pm['pull_edge_intact']:>5}")
    print(f"  HOLD & edge-gone (missed)       : {pm['hold_edge_gone']:>5}")
    print(f"  HOLD & edge-intact (correct)    : {pm['hold_edge_intact']:>5}")
    print(f"  P(operator pulls) = {h['p_operator_pulls']:.1%}")
    fa = h["p_pull_is_false_alarm_among_all_pulls"]
    print(f"  P(a pull is a FALSE ALARM | pulled) = {fa:.1%}" if fa is not None else "  (no pulls)")
    print(f"  longest underwater: median {h['median_longest_underwater_weeks']:.0f} wk, "
          f"p90 {h['p90_longest_underwater_weeks']:.0f} wk")
    fc = o["policy_compare"]["flat_shares_5k"]
    print(f"\nflat-shares @ $5k: med P&L {fc['median_pnl']:+.0f}, P(net<0) {fc['p_net_negative']:.1%}")


def selftest():
    ok = True
    cal = calibrate()
    rng = np.random.default_rng(SEED)
    # intact world (no stress) profits
    intact = dict(hl_mo=1e9, hc_mult=1, fill=0.0, fee_mult=1, pi_upset=0.0, upset_shock=0.2,
                  drought_frac=0.0, miss=0.0, adv_sel=1.0, cohort=1.0, fire_rate=8, decaying=False)
    pnls = [simulate_world(cal, intact, rng, 5000.0, kelly=True)["pnl"] for _ in range(300)]
    prof = np.median(pnls) > 0
    print(f"  intact world median P&L {np.median(pnls):+.0f} (>0) [{'ok' if prof else 'FAIL'}]")
    ok = ok and prof
    # costs-only + zero edge world loses
    dead = dict(intact, cohort=0.0)   # no edge -> win at price -> costs lose
    pnls2 = [simulate_world(cal, dead, rng, 5000.0, kelly=True)["pnl"] for _ in range(300)]
    loses = np.median(pnls2) < 0
    print(f"  zero-edge world median P&L {np.median(pnls2):+.0f} (<0) [{'ok' if loses else 'FAIL'}]")
    ok = ok and loses
    # upset regime injects losing slates the base record lacks: heavy upset world has fat left tail
    ups = dict(intact, pi_upset=0.6, upset_shock=0.3)
    pnls3 = [simulate_world(cal, ups, rng, 5000.0, kelly=True)["pnl"] for _ in range(300)]
    worse = np.percentile(pnls3, 5) < np.percentile(pnls, 5)
    print(f"  upset-world 5th-pct P&L {np.percentile(pnls3,5):+.0f} < intact 5th-pct "
          f"{np.percentile(pnls,5):+.0f} [{'ok' if worse else 'FAIL'}]")
    ok = ok and worse
    # caps bound drawdown: capped kelly maxDD < 1.0 even in a brutal world
    brutal = dict(intact, pi_upset=0.5, upset_shock=0.3, hc_mult=3, fill=0.02)
    dds = [simulate_world(cal, brutal, rng, 5000.0, kelly=True)["maxdd"] for _ in range(200)]
    bounded = np.percentile(dds, 95) < 1.0
    print(f"  brutal-world 95th-pct maxDD {np.percentile(dds,95):.1%} (<100%) [{'ok' if bounded else 'FAIL'}]")
    ok = ok and bounded
    # operator-pull detects a sustained red streak
    pulled = operator_pulls(np.array([-10.0] * 6 + [5.0] * 46))
    print(f"  operator pulls on 6 red weeks: {pulled} [{'ok' if pulled else 'FAIL'}]")
    ok = ok and pulled
    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def main():
    if "--selftest" in sys.argv:
        selftest()
        return
    o = run()
    _print(o)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "..", "reports", "stress", "bad_life_mc.json"), "w") as f:
        json.dump(o, f, indent=1, default=str)
    print("\nartifact -> reports/stress/bad_life_mc.json")


if __name__ == "__main__":
    main()
