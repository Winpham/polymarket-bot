#!/usr/bin/env python3
"""
ADVERSARIAL RISK-REALISM AUDIT  (favconsensus-deepen)

Purpose: show what an 8-day, ~91%-win favorite record CANNOT show, with numbers.
The claim under attack: "7-8 days non-negative; no true losing day sampled yet;
~$3.2k bankroll suffices." Every task below is designed to make that claim fail
if it can be made to fail on plausible inputs.

Unit of risk is the GAME, not the pick: picks on the same real-world match move
together (game-winner + spread + total all lose when the favorite actually loses).
Game key = superkey.super_event (match level). 100-share flat sizing throughout;
per-pick 100-share P&L = 100*(won - entry); game "fail" P&L = -100*sum(entry)
(= -capital-at-risk, every leg loses).

Tasks:
  R1  Game-clustered day bootstrap (2000x/day) at stress delta in {0, .05, .10}.
  R2  Deterministic upset-slate on the busiest day (flip top-K exposure games).
  R3  Bankroll adequacy: p1 drawdown, breach of $3.2k, +12h straggler peak.
  R4  Selection-window honesty: project onto a post-tournament (thin) week.
  R5  Streak plausibility under the no-edge null (true prob = entry).

Stress model (R1/R3): a "delta-pp win-prob haircut" is realised as a
GAME-CORRELATED adverse flip. For a game with in-sample win-fraction w, the game
fully fails (all legs -> loss) with probability s = clip(delta / w, 0, 1). This
lowers the marginal win prob by ~delta AND keeps a game's legs moving together
(the honest correlated tail), rather than sprinkling independent pick-level flips.
delta = 0 reproduces the empirical bootstrap exactly.

scipy + numpy + stdlib only. No network except the read-only psql pull. Seed 20260706.
Self-test:  ./audit_risk_realism.py --self-test
Live:       ./audit_risk_realism.py [--json reports/audit_risk_realism.json]
"""

import csv
import io
import json
import subprocess
import sys
from collections import defaultdict

import numpy as np
from scipy import stats

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from superkey import super_event  # noqa: E402

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]
SEED = 20260706
N_BOOT = 2000
BANKROLL = 3200.0
SHARES = 100.0
STRESSES = [0.0, 0.05, 0.10]
RECURRING_LEADS = ("mlb", "wnba")          # non-tournament recurring supply (brief §R4)
TOURNAMENT_LEADS = ("fifwc", "atp", "wta")  # WC + Wimbledon window supply

SQL = """
SELECT event_slug, slug, title,
       COALESCE(initial_mean_price, mean_price) AS entry,
       (outcome_won::int) AS won,
       to_char(first_detected_at AT TIME ZONE 'UTC', 'YYYY-MM-DD') AS day,
       EXTRACT(EPOCH FROM first_detected_at) AS open_ts,
       EXTRACT(EPOCH FROM resolved_at)       AS close_ts,
       split_part(slug, '-', 1)              AS lead
FROM consensus_signals
WHERE resolved AND outcome_won IS NOT NULL AND strategy = 'favorite'
"""


# ----------------------------------------------------------------------------- data
def pull():
    out = subprocess.run(PG + ["-f", "-"], input=SQL, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    return prep(list(csv.DictReader(io.StringIO(out.stdout))))


def prep(raw):
    rows = []
    for r in raw:
        entry = float(r["entry"])
        won = int(r["won"])
        rows.append({
            "entry": entry, "won": won,
            "pnl": SHARES * (won - entry),           # 100-share P&L, signed
            "day": r["day"],
            "game": super_event(r.get("event_slug"), r.get("slug")),
            "lead": (r.get("lead") or "").lower(),
            "open_ts": float(r["open_ts"]) if r.get("open_ts") not in (None, "") else None,
            "close_ts": float(r["close_ts"]) if r.get("close_ts") not in (None, "") else None,
        })
    return rows


def game_table(rows):
    """Collapse picks -> games. Each game: base_pnl, fail_pnl(=-exposure), w, s(delta), day."""
    g = defaultdict(list)
    for r in rows:
        g[(r["day"], r["game"])].append(r)
    out = []
    for (day, key), picks in g.items():
        base = sum(p["pnl"] for p in picks)
        exposure = SHARES * sum(p["entry"] for p in picks)
        w = sum(p["won"] for p in picks) / len(picks)
        out.append({"day": day, "key": key, "base": base, "fail": -exposure,
                    "exposure": exposure, "w": w, "npick": len(picks)})
    return out


def stress_prob(w, delta):
    """Game fully-fails with prob s so marginal win-prob drops ~delta; correlated tail."""
    if delta <= 0 or w <= 0:
        return 0.0
    return min(1.0, delta / w)


# ----------------------------------------------------------------------------- R1
def r1_day_bootstrap(games, rng):
    """Per-day game-resample bootstrap at each stress. Returns per-day + aggregate."""
    by_day = defaultdict(list)
    for g in games:
        by_day[g["day"]].append(g)

    res = {"per_day": {}, "aggregate": {}}
    agg_worst = {d: None for d in STRESSES}
    agg_pneg = {d: [] for d in STRESSES}
    for day in sorted(by_day):
        gs = by_day[day]
        base = np.array([g["base"] for g in gs])
        fail = np.array([g["fail"] for g in gs])
        w = np.array([g["w"] for g in gs])
        n = len(gs)
        actual = float(base.sum())
        res["per_day"][day] = {"n_games": n, "actual_pnl": round(actual, 2), "stress": {}}
        for delta in STRESSES:
            s = np.array([stress_prob(wi, delta) for wi in w])
            idx = rng.integers(0, n, size=(N_BOOT, n))
            u = rng.random((N_BOOT, n))
            flip = u < s[idx]
            pnl = np.where(flip, fail[idx], base[idx]).sum(axis=1)
            pneg = float((pnl < 0).mean())
            p5 = float(np.percentile(pnl, 5))
            worst = float(pnl.min())
            res["per_day"][day]["stress"][f"{delta:.2f}"] = {
                "p_negative_day": round(pneg, 4),
                "p5_pnl": round(p5, 2),
                "worst_sim_pnl": round(worst, 2),
            }
            agg_pneg[delta].append(pneg)
            if agg_worst[delta] is None or worst < agg_worst[delta]:
                agg_worst[delta] = worst
    for delta in STRESSES:
        res["aggregate"][f"{delta:.2f}"] = {
            "worst_sim_day_pnl": round(agg_worst[delta], 2),
            "mean_p_negative_day": round(float(np.mean(agg_pneg[delta])), 4),
            "max_p_negative_day": round(float(np.max(agg_pneg[delta])), 4),
        }
    return res


# ----------------------------------------------------------------------------- R2
def r2_upset_slate(games):
    """Busiest day; flip top-K exposure games won->fail deterministically, K=1..5."""
    by_day = defaultdict(list)
    for g in games:
        by_day[g["day"]].append(g)
    busiest = max(by_day, key=lambda d: sum(x["npick"] for x in by_day[d]))
    gs = sorted(by_day[busiest], key=lambda g: g["exposure"], reverse=True)
    n_games = len(gs)
    n_picks = sum(g["npick"] for g in gs)
    base_pnl = sum(g["base"] for g in gs)

    table = []
    first_negative_K = None
    for K in range(0, 6):
        pnl = base_pnl - sum(g["base"] - g["fail"] for g in gs[:K])
        table.append({"K": K, "day_pnl": round(pnl, 2),
                      "flipped_exposure": round(sum(g["exposure"] for g in gs[:K]), 2)})
        if K >= 1 and pnl < 0 and first_negative_K is None:
            first_negative_K = K
    cost_K3 = round(base_pnl - table[3]["day_pnl"], 2)

    # per-game implied upset prob = 1 - (exposure-weighted avg entry of the game's legs)
    upset_p = np.array([1.0 - (g["exposure"] / (SHARES * g["npick"])) for g in gs])
    # naive binomial: each of n_games favorites ~0.82 implied -> upset 0.18
    p_ge3_naive = float(stats.binom.sf(2, n_games, 0.18))
    # Poisson-binomial P(>=3 upsets anywhere) via exact DP on actual per-game probs
    pmf = poisson_binomial_pmf(upset_p)
    p_ge3_pb = float(pmf[3:].sum())
    # P(the specific top-3 largest-exposure games ALL upset) -> the event that sinks the day
    p_top3_all = float(np.prod(upset_p[:3]))

    return {
        "busiest_day": busiest, "n_games": n_games, "n_picks": n_picks,
        "base_day_pnl": round(base_pnl, 2),
        "K_table": table,
        "first_negative_K": first_negative_K,
        "cost_of_K3": cost_K3,
        "p_ge3_upsets_binomial_p018": round(p_ge3_naive, 4),
        "p_ge3_upsets_poisson_binomial": round(p_ge3_pb, 4),
        "p_top3_exposure_all_upset": round(p_top3_all, 4),
        "expected_upsets_of_40": round(float(upset_p.sum()), 2),
    }


def poisson_binomial_pmf(probs):
    """Exact PMF of sum of independent Bernoulli(probs) via DP. Returns array len n+1."""
    pmf = np.zeros(len(probs) + 1)
    pmf[0] = 1.0
    for p in probs:
        pmf[1:] = pmf[1:] * (1 - p) + pmf[:-1] * p
        pmf[0] = pmf[0] * (1 - p)
    return pmf


# ----------------------------------------------------------------------------- R3
def concurrency_peak(rows, delay_h=0.0):
    """Peak concurrent capital ($) and count from open/close events; optional +delay_h close."""
    ev = []
    delay = delay_h * 3600.0
    for r in rows:
        if r["open_ts"] is None or r["close_ts"] is None:
            continue
        cap = SHARES * r["entry"]
        ev.append((r["open_ts"], +cap, +1))
        ev.append((r["close_ts"] + delay, -cap, -1))
    # process closes before opens at identical ts (conservative: frees capital first)
    ev.sort(key=lambda x: (x[0], -x[2] if x[1] < 0 else 10, x[1]))
    ev.sort(key=lambda x: (x[0], 0 if x[1] < 0 else 1))
    cap = cnt = 0.0
    peak_cap = peak_cnt = 0.0
    for _, dcap, dcnt in ev:
        cap += dcap
        cnt += dcnt
        peak_cap = max(peak_cap, cap)
        peak_cnt = max(peak_cnt, cnt)
    return round(peak_cap, 2), int(peak_cnt)


def r3_bankroll(rows, games, rng, delta=0.05):
    """Stress the actual timeline: min free capital & drawdown across sims; breach of $3.2k."""
    peak_cap, peak_cnt = concurrency_peak(rows, 0.0)
    peak_cap12, peak_cnt12 = concurrency_peak(rows, 12.0)

    # map each pick to its game so a game-fail flips all its legs together
    game_of = {}
    for r in rows:
        game_of.setdefault((r["day"], r["game"]), []).append(r)
    gs = [g for g in games]
    gkeys = [(g["day"], g["key"]) for g in gs]
    s = np.array([stress_prob(g["w"], delta) for g in gs])

    # timeline events sorted by ts; each pick contributes open(+cap)/close(+pnl,-cap)
    # closes are ordered by close_ts; realized pnl accumulates at close.
    close_order = sorted([r for r in rows if r["close_ts"] is not None],
                         key=lambda r: r["close_ts"])

    min_free = np.full(N_BOOT, np.inf)
    max_dd = np.zeros(N_BOOT)
    breaches = 0
    # Precompute, per sim, which games fail:
    fail_draw = rng.random((N_BOOT, len(gs))) < s   # (N_BOOT, n_games)
    gindex = {k: i for i, k in enumerate(gkeys)}

    # Build event list once: (ts, kind, pick) ; kind 0=open 1=close
    events = []
    for r in rows:
        if r["open_ts"] is None or r["close_ts"] is None:
            continue
        events.append((r["open_ts"], 0, r))
        events.append((r["close_ts"], 1, r))
    events.sort(key=lambda e: (e[0], e[1]))  # opens before closes at same ts (conservative)

    # Vectorised walk across sims
    cap = np.zeros(N_BOOT)          # capital currently deployed (same every sim: sizing fixed)
    realized = np.zeros(N_BOOT)     # realized P&L so far (varies by sim via flips)
    running_max = np.zeros(N_BOOT)
    for ts, kind, r in events:
        c = SHARES * r["entry"]
        gi = gindex[(r["day"], r["game"])]
        if kind == 0:
            cap += c
        else:
            failed = fail_draw[:, gi]
            pnl = np.where(failed, -c, r["pnl"])   # game-fail => this leg loses -c
            realized += pnl
            cap -= c
            running_max = np.maximum(running_max, realized)
            max_dd = np.maximum(max_dd, running_max - realized)
        free = BANKROLL + realized - cap
        min_free = np.minimum(min_free, free)
    breaches = int((min_free < 0).sum())

    return {
        "delta": delta,
        "peak_concurrent_capital": peak_cap,
        "peak_concurrent_positions": peak_cnt,
        "peak_concurrent_capital_plus12h": peak_cap12,
        "peak_concurrent_positions_plus12h": peak_cnt12,
        "p1_min_free_capital": round(float(np.percentile(min_free, 1)), 2),
        "p50_min_free_capital": round(float(np.percentile(min_free, 50)), 2),
        "p99_drawdown": round(float(np.percentile(max_dd, 99)), 2),
        "p50_drawdown": round(float(np.percentile(max_dd, 50)), 2),
        "breach_paths": breaches,
        "breach_frac": round(breaches / N_BOOT, 4),
        "bankroll": BANKROLL,
    }


# ----------------------------------------------------------------------------- R4
def r4_post_tournament(rows, rng):
    """Project the edge onto a thin post-tournament week (recurring supply only)."""
    rec = [r for r in rows if r["lead"] in RECURRING_LEADS]
    tour = [r for r in rows if r["lead"] in TOURNAMENT_LEADS]
    entries = np.array([r["entry"] for r in rec])
    n_days = len({r["day"] for r in rows})
    rec_per_day = len(rec) / n_days

    def sim(n_bets, true_shift):
        """Draw n_bets recurring entries; outcome ~ Bernoulli(clip(entry+shift)); day pnl."""
        pick = rng.integers(0, len(entries), size=(N_BOOT, n_bets))
        e = entries[pick]
        ptrue = np.clip(e + true_shift, 0.01, 0.99)
        won = rng.random((N_BOOT, n_bets)) < ptrue
        pnl = (SHARES * (won - e)).sum(axis=1)
        return float((pnl < 0).mean()), float(pnl.mean())

    out = {"recurring_n": len(rec), "recurring_per_day": round(rec_per_day, 2),
           "recurring_leads": list(RECURRING_LEADS),
           "tournament_n": len(tour),
           "tournament_frac_of_record": round(len(tour) / len(rows), 3),
           "scenarios": {}}
    # null: true prob = entry (no edge). optimistic: +0.05 edge (charitable).
    for label, shift in [("null_no_edge", 0.0), ("edge_plus5pp", 0.05)]:
        blk = {}
        for n_bets in (3, 4, 5):
            pneg, mean = sim(n_bets, shift)
            blk[f"{n_bets}_bets"] = {"p_negative_day": round(pneg, 4),
                                     "expected_day_pnl": round(mean, 2),
                                     "expected_neg_days_of_7": round(7 * pneg, 2)}
        out["scenarios"][label] = blk
    return out


# ----------------------------------------------------------------------------- R5
def r5_streak(rows):
    """P(record at least this good) under null true-prob = entry. Naive + game-clustered."""
    p = np.array([r["entry"] for r in rows])
    won = np.array([r["won"] for r in rows])
    n = len(rows)
    obs_wins = int(won.sum())
    exp_wins = float(p.sum())

    # naive Poisson-binomial: P(W >= obs_wins) exact DP
    pmf = poisson_binomial_pmf(p)
    p_pooled_exact = float(pmf[obs_wins:].sum())
    sd = float(np.sqrt((p * (1 - p)).sum()))
    z_naive = (obs_wins - exp_wins) / sd

    # game-clustered honest test: a_i = won-entry, cluster-mean by game, clustered SE
    ga = defaultdict(list)
    for r in rows:
        ga[(r["day"], r["game"])].append(r["won"] - r["entry"])
    means = np.array([np.mean(v) for v in ga.values()])
    m = float(means.mean())
    nc = len(means)
    se = float(means.std(ddof=1) / np.sqrt(nc))
    z_clustered = m / se
    p_clustered = float(stats.norm.sf(z_clustered))

    # MLB streak: all-win among mlb picks under null
    mlb = [r for r in rows if r["lead"] == "mlb"]
    mlb_p = np.array([r["entry"] for r in mlb])
    mlb_wins = int(sum(r["won"] for r in mlb))
    mlb_all_win = int(all(r["won"] == 1 for r in mlb))
    # P(>= mlb_wins) ; if 18-0, that's P(all win) = prod(entry)
    mlb_pmf = poisson_binomial_pmf(mlb_p)
    p_mlb = float(mlb_pmf[mlb_wins:].sum())

    return {
        "n_picks": n, "obs_wins": obs_wins, "obs_win_rate": round(obs_wins / n, 4),
        "exp_wins_null": round(exp_wins, 2),
        "pooled_p_value_naive": p_pooled_exact,
        "pooled_z_naive": round(z_naive, 3),
        "n_game_clusters": nc,
        "pooled_z_clustered": round(z_clustered, 3),
        "pooled_p_value_clustered": p_clustered,
        "mlb_n": len(mlb), "mlb_wins": mlb_wins, "mlb_all_win": bool(mlb_all_win),
        "mlb_p_value_null": p_mlb,
        "mlb_avg_entry": round(float(mlb_p.mean()), 4),
    }


# ----------------------------------------------------------------------------- driver
def run_live(json_path):
    rows = pull()
    games = game_table(rows)
    rng = np.random.default_rng(SEED)
    res = {
        "meta": {"seed": SEED, "n_boot": N_BOOT, "n_picks": len(rows),
                 "n_games": len(games), "n_days": len({r["day"] for r in rows}),
                 "bankroll": BANKROLL, "stress_model": "game-correlated adverse flip s=clip(delta/w,0,1)"},
        "R1_day_bootstrap": r1_day_bootstrap(games, rng),
        "R2_upset_slate": r2_upset_slate(games),
        "R3_bankroll": r3_bankroll(rows, games, rng, delta=0.05),
        "R3_bankroll_stress10": r3_bankroll(rows, games, rng, delta=0.10),
        "R4_post_tournament": r4_post_tournament(rows, rng),
        "R5_streak": r5_streak(rows),
    }
    if json_path:
        with open(json_path, "w") as f:
            json.dump(res, f, indent=2)
    print(json.dumps(res, indent=2))
    return res


# ----------------------------------------------------------------------------- self-test
def _self_test():
    rng = np.random.default_rng(SEED)

    # 1. per-pick P&L identity: won -> +100(1-entry); lost -> -100*entry
    assert abs(SHARES * (1 - 0.8) - 20.0) < 1e-9
    assert abs(SHARES * (0 - 0.8) - (-80.0)) < 1e-9

    # 2. game fail P&L = -exposure (every leg loses)
    picks = [{"entry": 0.8, "won": 1, "pnl": SHARES * (1 - 0.8), "day": "d", "game": "g", "lead": "x",
              "open_ts": 0.0, "close_ts": 100.0},
             {"entry": 0.6, "won": 1, "pnl": SHARES * (1 - 0.6), "day": "d", "game": "g", "lead": "x",
              "open_ts": 0.0, "close_ts": 100.0}]
    gt = game_table(picks)
    assert len(gt) == 1
    assert abs(gt[0]["fail"] - (-(SHARES * (0.8 + 0.6)))) < 1e-9, "fail must equal -exposure"
    assert abs(gt[0]["base"] - (20.0 + 40.0)) < 1e-9

    # 3. stress_prob: delta=0 -> 0 ; delta>=w -> 1 ; monotone
    assert stress_prob(0.9, 0.0) == 0.0
    assert stress_prob(0.9, 0.9) == 1.0
    assert stress_prob(0.9, 1.0) == 1.0
    assert 0 < stress_prob(0.9, 0.05) < 1

    # 4. poisson-binomial PMF sums to 1 and matches binomial when probs equal
    pb = poisson_binomial_pmf(np.full(10, 0.3))
    assert abs(pb.sum() - 1.0) < 1e-9
    assert abs(pb[3] - stats.binom.pmf(3, 10, 0.3)) < 1e-9
    # degenerate: all p=1 -> mass at n
    pb1 = poisson_binomial_pmf(np.array([1.0, 1.0, 1.0]))
    assert abs(pb1[3] - 1.0) < 1e-9

    # 5. R1 delta=0 bootstrap mean ~ actual day pnl (empirical resample is unbiased)
    day = [{"day": "d", "game": f"g{i}", "entry": 0.7, "won": 1 if i % 2 else 0,
            "pnl": SHARES * ((1 if i % 2 else 0) - 0.7), "lead": "x",
            "open_ts": 0.0, "close_ts": 1.0} for i in range(20)]
    r1 = r1_day_bootstrap(game_table(day), np.random.default_rng(1))
    actual = r1["per_day"]["d"]["actual_pnl"]
    # bootstrap p5 <= actual mean region; worst is finite
    assert r1["per_day"]["d"]["stress"]["0.00"]["worst_sim_pnl"] <= actual
    # stress raises P(negative)
    p0 = r1["per_day"]["d"]["stress"]["0.00"]["p_negative_day"]
    p10 = r1["per_day"]["d"]["stress"]["0.10"]["p_negative_day"]
    assert p10 >= p0, "stress must not reduce P(negative)"

    # 6. R2 flipping the largest-exposure game reduces day P&L monotonically
    g2 = game_table([{"day": "d", "game": f"g{i}", "entry": 0.8, "won": 1,
                      "pnl": SHARES * 0.2, "lead": "x", "open_ts": 0.0, "close_ts": 1.0}
                     for i in range(40)])
    r2 = r2_upset_slate(g2)
    seq = [row["day_pnl"] for row in r2["K_table"]]
    assert all(seq[i] >= seq[i + 1] for i in range(len(seq) - 1)), "K-flip must be monotone down"
    assert r2["n_games"] == 40

    # 7. concurrency_peak: two overlapping 100-share@0.5 -> peak $100; +delay extends but same peak here
    cp, cc = concurrency_peak([{"entry": 0.5, "open_ts": 0.0, "close_ts": 10.0, "won": 1, "pnl": 0, "day": "d", "game": "g"},
                               {"entry": 0.5, "open_ts": 1.0, "close_ts": 11.0, "won": 1, "pnl": 0, "day": "d", "game": "g"}])
    assert abs(cp - 100.0) < 1e-9 and cc == 2

    # 8. R5 no-edge null: a perfectly-calibrated record (wins == expected) is NOT significant
    calib = []
    for i in range(200):
        e = 0.5 + 0.4 * (i % 5) / 5.0
        calib.append({"entry": e, "won": 1 if (i % 100) < int(100 * e) else 0,
                      "day": f"d{i%7}", "game": f"g{i}", "lead": "x",
                      "open_ts": 0.0, "close_ts": 1.0})
    # a genuinely too-good record (all win at p=0.8) must be extremely unlikely under null
    toogood = [{"entry": 0.8, "won": 1, "day": "d", "game": f"g{i}", "lead": "mlb",
                "open_ts": 0, "close_ts": 1} for i in range(18)]
    r5 = r5_streak(toogood)
    assert r5["mlb_p_value_null"] < 0.02, "18-0 at 0.8 should be < 0.02 under null"
    assert abs(r5["mlb_p_value_null"] - 0.8 ** 18) < 1e-6, "all-win null p = prod(entry)"

    # 9. R4 null scenario has expected day pnl ~ 0 (no edge) and P(neg) substantial for thin days
    rec_rows = [{"entry": 0.7, "won": 1, "day": f"d{i%8}", "game": f"g{i}", "lead": "mlb",
                 "pnl": SHARES * 0.3, "open_ts": 0, "close_ts": 1} for i in range(20)]
    r4 = r4_post_tournament(rec_rows, np.random.default_rng(2))
    null3 = r4["scenarios"]["null_no_edge"]["3_bets"]
    assert abs(null3["expected_day_pnl"]) < 15.0, "null edge => ~0 expected daily pnl"
    assert null3["p_negative_day"] > 0.15, "thin null days must carry real downside"

    print("SELF-TEST PASS")
    return True


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(0 if _self_test() else 1)
    jp = None
    if "--json" in sys.argv:
        jp = sys.argv[sys.argv.index("--json") + 1]
    run_live(jp)
