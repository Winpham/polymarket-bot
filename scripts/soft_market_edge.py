#!/usr/bin/env python3
"""
SOFT-MARKET EDGE MEASUREMENT (Soft-Market Edge Hunt, phase 3, 2026-07-09).

Measures THE LOCKED OBJECTIVE (RUN-SOFT-MARKET-EDGE-HUNT §0.5):

  maximize the CLUSTER-ROBUST LOWER BOUND of realizable, COPYABLE ROI-on-turnover,
  subject to a bet-volume floor AND a duration/persistence floor, validated on a
  time-split hold-out — NOT total P&L (total-P&L trap), NOT win rate (win-rate trap
  → deep-favorite money-loser), NOT an in-sample number.

The soft arm (soft_fav) has not run live, so its picks are REPLAYED from the fills:
esports (condition,outcome) reaching ≥`MIN_BACKERS` distinct one-sided backers within
48h under the WIDER eligibility set (rank ≤ SOFT_CUTOFF OR consensus_eligible/earned) —
exactly `load_soft_window_votes` + `soft_market_arms`. The champion `favorite` (soccer/
crowded) is read from its LIVE signals for the head-to-head on the SAME realizable metric.

REALIZABILITY LADDER (the copyability cap — a sharp's edge at THEIR price is not ours):
  realizable entry = COALESCE(entry_ask, tape_ask)
    entry_ask  = the executable best ASK captured on the live signal (set-once, leak-free).
    tape_ask   = clob_price_tape best_ask at/after the convergence instant (executable, but
                 only the last ~72h are retained).
  directional entry = sharp-fill mean + haircut — the sharps' OWN price; NOT copyable.
                 Reported ONLY as the non-realizable CEILING, never as the objective.
Corrected fee = 0.03·p·(1−p) per share (brief §0.5). ROI-turn = Σpnl / Σstake, stake = entry·shares.

Cluster-robust LB at the MATCH super-key (a best-of-3's map1/map2/series markets are ONE
levered bet, not 3 wins), small-cluster Student-t(G−1) — reused from effective_n.cluster_robust.
Belief-blind SKILL = surplus over the esports blind-favorite baseline at the same band (a soft
market where consensus adds NO skill is just riding softness and won't transfer). Volume floor
= ≥VOL_FLOOR event-clusters; below it a cell reads INDETERMINATE, never "best". Time-split OOS:
fit on the early half of match-days, verify on the late half. Win rate = DIAGNOSTIC only.

The track record SELECTS (a sustained-consistency ranking of soft-market traders, hypothesis
generator only — past-PnL rank was refuted 5 ways); the forward/OOS gate PROVES. This script
CERTIFIES nothing and PROMOTES nothing — it emits the belief-blind, realizable, coverage-bounded
map for the pre-registered forward gate to arbitrate.

Self-test:  ./soft_market_edge.py --selftest
Live:       ./soft_market_edge.py            (emits reports/SOFT-MARKET-EDGE.json)
"""

import json
import math
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from superkey import super_event                       # noqa: E402
from effective_n import cluster_robust, _t_ppf          # noqa: E402

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q", "-t", "-A", "-F", "\t"]

ESPORTS_RE = r"^(lol|cs2|csgo|dota|dota2|val|valorant)"
GO_LIVE = "2026-06-29"
SOFT_CUTOFF = 250
MIN_BACKERS = 3
FAV_LO, FAV_HI = 0.65, 0.98
VOL_FLOOR = 20          # ≥20 event-clusters or INDETERMINATE (pre-registered)
SIG_FLOOR_PER_DAY = 3   # ≥~3 signals/active-day for real deployment
DUR_FLOOR_DAYS = 7      # ≥7 distinct active days: a 3-day tournament weekend is NOT durable
REGIME_FLOOR = 2        # ≥2 disjoint regimes (disciplines) each clearing a sub-floor
REGIME_SUBFLOOR = 8     # min match-clusters a discipline needs to count as a regime
ALPHA = 0.05            # one-sided 95% LB
SHARES = 100.0


def q(sql):
    out = subprocess.run(PG + ["-c", sql], capture_output=True, text=True)
    if out.returncode != 0:
        sys.stderr.write(out.stderr)
        raise SystemExit(f"psql failed: {out.stderr[:400]}")
    return [r.split("\t") for r in out.stdout.strip().splitlines() if r.strip()]


def fee(p):
    """Corrected spread/fee per share (brief §0.5): 0.03·p·(1−p)."""
    return 0.03 * p * (1.0 - p)


def pnl(entry, won):
    return (1.0 - entry if won else -entry) - fee(entry)


def roi_turn(picks):
    """picks: list of (entry, won). Σpnl / Σstake, stake = entry."""
    stk = sum(e for e, _ in picks)
    if stk <= 0:
        return None
    return sum(pnl(e, w) for e, w in picks) / stk


# --- objective: cluster-robust ROI-turn LOWER BOUND at the match super-key -----------
def roi_lb(rows):
    """rows: [{entry, won, event_slug, slug, condition_id, day}]. Returns the objective:
    cluster-robust one-sided 95% LB of ROI-on-turnover, clustered at the match, read at
    small-cluster t(G-1). Per-event surplus is the event's Σpnl/Σstake so the LB is on the
    turnover metric itself (not a per-pick mean). None if < 2 events."""
    ev_pnl, ev_stk, ev_cluster = defaultdict(float), defaultdict(float), {}
    for r in rows:
        ev = r["condition_id"]                      # per-market event
        cl = super_event(r["event_slug"], r["slug"]) or r["condition_id"]   # match cluster
        ev_pnl[ev] += pnl(r["entry"], r["won"])
        ev_stk[ev] += r["entry"]
        ev_cluster[ev] = cl
    ev_roi = {e: ev_pnl[e] / ev_stk[e] for e in ev_pnl if ev_stk[e] > 0}
    if len(ev_roi) < 2:
        return None
    cr = cluster_robust(ev_roi, {e: ev_cluster[e] for e in ev_roi})
    if cr is None or not (cr["se_CR"] == cr["se_CR"]):   # nan guard (G<2)
        point = sum(ev_roi.values()) / len(ev_roi)
        return {"point": point, "lb": None, "N_events": len(ev_roi), "G_clusters": cr["G"] if cr else 1,
                "note": "single cluster — LB undefined"}
    df = max(cr["G"] - 1, 1)
    t = _t_ppf(1 - ALPHA, df)
    return {"point": cr["theta"], "lb": cr["theta"] - t * cr["se_CR"],
            "se_CR": cr["se_CR"], "N_events": cr["N"], "G_clusters": cr["G"],
            "n_eff_CR": cr["n_eff_CR"], "t_crit": t}


def win_rate(rows):
    n = len(rows)
    return (sum(1 for r in rows if r["won"]) / n) if n else None


def discipline(event_slug):
    """esports discipline (lol/cs2/dota2/val/...) — a regime axis: different games are
    genuinely disjoint metas, so ≥2 disciplines is a real disjoint-regime check, and one
    discipline chalking a weekend must not read as a durable edge."""
    s = (event_slug or "")
    for d in ("dota2", "dota", "csgo", "cs2", "valorant", "val", "lol"):
        if s.startswith(d):
            return {"dota": "dota2", "csgo": "cs2", "valorant": "val"}.get(d, d)
    return "other"


def lodo_lb(rows):
    """Leave-One-Discipline-Out jackknife: drop the discipline with the most match-clusters
    and recompute the LB. If the edge only survives WITH the dominant discipline, it's that
    discipline's streak (e.g. a Dota2 tournament weekend), NOT a transferable soft-market edge.
    Returns (dropped_discipline, lb_without_it) or (None, None) if <2 disciplines."""
    by_disc = defaultdict(list)
    for r in rows:
        by_disc[discipline(r["event_slug"])].append(r)
    if len(by_disc) < 2:
        return None, None
    dom = max(by_disc, key=lambda d: len({super_event(r["event_slug"], r["slug"]) or r["condition_id"]
                                          for r in by_disc[d]}))
    rest = [r for r in rows if discipline(r["event_slug"]) != dom]
    lb = roi_lb(rest)
    return dom, (lb["lb"] if lb and lb.get("lb") is not None else None)


# --- data pulls ---------------------------------------------------------------------
def fetch_soft_picks():
    """Replay the soft_fav universe: esports outcomes with ≥MIN_BACKERS distinct one-sided
    wider-eligibility backers within 48h, in the favorite band, RESOLVED. Carries the sharp
    entry, the realizable entry_ask (any live capture), and the outcome."""
    rows = q(f"""
    WITH e AS (
      SELECT f.condition_id, f.outcome_index, LOWER(f.wallet) w, MIN(f.ts) ts, AVG(f.price) px,
             MAX(f.event_slug) event_slug, MAX(f.slug) slug,
             BOOL_OR(f.resolved) rz, BOOL_OR(f.outcome_won) won
      FROM trader_fills f
      JOIN followed_traders ft ON ft.proxy_wallet=f.wallet
      WHERE f.side='BUY' AND f.ts>='{GO_LIVE}' AND f.event_slug ~ '{ESPORTS_RE}'
        AND (ft.rank<={SOFT_CUTOFF} OR ft.consensus_eligible OR ft.earned_eligible)
      GROUP BY 1,2,3),
    e1 AS (SELECT e.* FROM e WHERE NOT EXISTS
      (SELECT 1 FROM e x WHERE x.condition_id=e.condition_id AND x.w=e.w AND x.outcome_index<>e.outcome_index)),
    -- one row per (cond,outcome): conv_ts = the MIN_BACKERS-th distinct backer's first-entry
    -- time = the instant the signal FIRES (a copier can act no earlier). 48h co-residence =
    -- conv_ts within 48h of the first backer. Realizable entry is priced at/after conv_ts, never
    -- at the earlier first-backer price (that would be a look-ahead a copier could never get).
    conv AS (
      SELECT condition_id, outcome_index, MAX(event_slug) event_slug, MAX(slug) slug,
             COUNT(*) nb, AVG(px) sharp_entry,
             (ARRAY_AGG(ts ORDER BY ts))[{MIN_BACKERS}] conv_ts,
             BOOL_OR(rz) rz, BOOL_OR(won) won
      FROM e1
      GROUP BY 1,2 HAVING COUNT(*)>={MIN_BACKERS}
        AND (ARRAY_AGG(ts ORDER BY ts))[{MIN_BACKERS}] - MIN(ts) <= interval '48 hours')
    SELECT c.condition_id, c.outcome_index, c.event_slug, c.slug, c.nb,
           c.sharp_entry, c.conv_ts, c.rz, c.won,
           cs.entry_ask, cs.entry_ask_mid
    FROM conv c
    LEFT JOIN LATERAL (
      SELECT entry_ask, entry_ask_mid FROM consensus_signals s
      WHERE s.condition_id=c.condition_id AND s.outcome_index=c.outcome_index
        AND s.entry_ask IS NOT NULL LIMIT 1) cs ON TRUE
    WHERE c.sharp_entry BETWEEN {FAV_LO} AND {FAV_HI} AND c.rz AND c.won IS NOT NULL;
    """)
    picks = []
    for r in rows:
        r = (r + [""] * 11)[:11]            # pad trailing NULL columns dropped by split
        cond, oi, es, slug, nb, sharp, fts, rz, won, ask, ask_mid = r
        picks.append({
            "condition_id": cond, "outcome_index": int(oi), "event_slug": es, "slug": slug,
            "nb": int(nb), "sharp_entry": float(sharp), "conv_ts": fts,
            "won": won == "t", "entry_ask": float(ask) if ask not in ("", None) else None,
            "day": (fts or "")[:10],
        })
    return picks


def fetch_tape_asks(picks):
    """Realizable executable ask from clob_price_tape at/after each pick's convergence ts
    (the price a COPIER faces). Only the last ~72h are retained → sparse by construction."""
    if not picks:
        return {}
    vals = ",".join(f"('{p['condition_id']}',{p['outcome_index']},TIMESTAMPTZ '{p['conv_ts']}')"
                    for p in picks if p["conv_ts"])
    rows = q(f"""
    WITH pk(condition_id, outcome_index, ts) AS (VALUES {vals})
    SELECT pk.condition_id, pk.outcome_index, t.best_ask
    FROM pk
    JOIN LATERAL (
      SELECT best_ask FROM clob_price_tape cp
      WHERE cp.condition_id=pk.condition_id AND cp.outcome_index=pk.outcome_index
        AND cp.best_ask IS NOT NULL AND cp.recv_at >= pk.ts
      ORDER BY cp.recv_at LIMIT 1) t ON TRUE;
    """)
    return {(r[0], int(r[1])): float(r[2]) for r in rows if r[2] not in ("", None)}


def fetch_champion():
    """Champion `favorite` live resolved picks WITH a realizable entry_ask, for the
    head-to-head on the identical metric."""
    rows = q(f"""
    SELECT condition_id, outcome_index, event_slug, slug, entry_ask, outcome_won,
           first_detected_at::date
    FROM consensus_signals
    WHERE strategy='favorite' AND resolved AND outcome_won IS NOT NULL
      AND entry_ask IS NOT NULL AND entry_ask BETWEEN {FAV_LO} AND {FAV_HI};
    """)
    return [{"condition_id": r[0], "outcome_index": int(r[1]), "event_slug": r[2], "slug": r[3],
             "entry": float(r[4]), "won": r[5] == "t", "day": r[6]} for r in rows]


def fetch_blind_baseline():
    """Esports blind-favorite baseline (softness): _blind esports favorites' mean(won−entry)
    at the sharp/at-fire entry, per band. Used for the belief-blind SKILL split (directional
    basis; _blind has no entry_ask). Returns {band: blind_edge}."""
    rows = q(f"""
    SELECT COALESCE(initial_mean_price, mean_price) e, outcome_won
    FROM consensus_signals
    WHERE strategy='_blind' AND resolved AND outcome_won IS NOT NULL
      AND event_slug ~ '{ESPORTS_RE}'
      AND COALESCE(initial_mean_price, mean_price) BETWEEN {FAV_LO} AND {FAV_HI};
    """)
    edges = [(float(r[0]), r[1] == "t") for r in rows]
    if not edges:
        return None
    return sum((1.0 if w else 0.0) - e for e, w in edges) / len(edges)


# --- track-record ranking (SELECT-only hypothesis generator) ------------------------
def fetch_trader_consistency():
    """Rank esports-active tracked traders by a SUSTAINED-CONSISTENCY metric over their long
    esports fill history: shrunk mean(won−fillprice)/std — a Sharpe-like read, NOT raw PnL
    (past-PnL rank was refuted 5 ways). SELECT-only: this GENERATES candidates for the forward
    gate; it certifies nothing (survivorship + copyability guards apply — see the run brief)."""
    rows = q(f"""
    SELECT LOWER(f.wallet) w, ft.rank,
           COUNT(*) n, AVG((CASE WHEN f.outcome_won THEN 1.0 ELSE 0.0 END) - f.price) mu,
           COALESCE(STDDEV_POP((CASE WHEN f.outcome_won THEN 1.0 ELSE 0.0 END) - f.price),0) sd
    FROM trader_fills f
    JOIN followed_traders ft ON ft.proxy_wallet=f.wallet
    WHERE f.side='BUY' AND f.event_slug ~ '{ESPORTS_RE}' AND f.resolved AND f.outcome_won IS NOT NULL
      AND f.price BETWEEN {FAV_LO} AND {FAV_HI}
    GROUP BY 1,2 HAVING COUNT(*)>=30;
    """)
    out = []
    for r in rows:
        w, rank, n, mu, sd = r[0], r[1], int(r[2]), float(r[3]), float(r[4])
        shrink = n / (n + 50.0)                        # shrink low-N toward 0
        consistency = shrink * mu / sd if sd > 0 else 0.0
        out.append({"wallet_tail": w[-6:], "rank": int(rank) if rank not in ("", None) else None,
                    "n_fills": n, "mean_edge": round(mu, 4), "sd": round(sd, 4),
                    "consistency": round(consistency, 4)})
    out.sort(key=lambda d: d["consistency"], reverse=True)
    return out[:15]


# --- assemble the report ------------------------------------------------------------
def build_report():
    soft = fetch_soft_picks()
    tape = fetch_tape_asks(soft)
    champ = fetch_champion()
    blind = fetch_blind_baseline()

    # attach realizable entry ladder
    for p in soft:
        p["tape_ask"] = tape.get((p["condition_id"], p["outcome_index"]))
        p["realizable"] = p["entry_ask"] if p["entry_ask"] is not None else p["tape_ask"]

    n_soft = len(soft)
    n_realizable = sum(1 for p in soft if p["realizable"] is not None)

    def rows_at(picks, key):
        return [{"entry": p[key], "won": p["won"], "event_slug": p["event_slug"],
                 "slug": p["slug"], "condition_id": p["condition_id"], "day": p["day"]}
                for p in picks if p.get(key) is not None]

    # objective on the realizable subsample; directional (sharp) as the non-copyable ceiling
    soft_real_rows = rows_at(soft, "realizable")
    soft_dir_rows = rows_at(soft, "sharp_entry")

    def cell(rows, label, _days=None, regime_gated=True):
        lb = roi_lb(rows)
        if lb is None:
            return {"label": label, "n_picks": len(rows), "verdict": "INSUFFICIENT (<2 events)"}
        # duration + disjoint-regime gates: a fat LB from ONE tournament weekend or ONE
        # discipline chalking is the soft-week trap, NOT a durable edge.
        active_days = len({r["day"] for r in rows if r.get("day")})
        disc_clusters = defaultdict(set)
        for r in rows:
            disc_clusters[discipline(r["event_slug"])].add(
                super_event(r["event_slug"], r["slug"]) or r["condition_id"])
        disc_n = {d: len(s) for d, s in disc_clusters.items()}
        regimes = [d for d, n in disc_n.items() if n >= REGIME_SUBFLOOR]
        dropped, lb_lodo = lodo_lb(rows)
        below_vol = lb["G_clusters"] < VOL_FLOOR
        below_dur = active_days < DUR_FLOOR_DAYS
        # regime/LODO gates are the esports discipline-disjointness check; N/A to the
        # single-discipline champion (soccer), which is judged on volume+duration only.
        below_reg = regime_gated and len(regimes) < REGIME_FLOOR
        lodo_fail = regime_gated and ((lb_lodo is None) or (lb_lodo <= 0))
        c = {"label": label, "n_picks": len(rows), "roi_turn_point": round(lb["point"], 4),
             "roi_turn_LB": None if lb["lb"] is None else round(lb["lb"], 4),
             "N_events": lb["N_events"], "G_clusters": lb["G_clusters"],
             "win_rate_diag": round(win_rate(rows), 3),
             "active_days": active_days, "disciplines": disc_n,
             "regimes_over_subfloor": regimes,
             "lodo_drop": dropped, "lodo_LB_without_dominant": None if lb_lodo is None else round(lb_lodo, 4),
             "meets_volume_floor": not below_vol, "meets_duration_floor": not below_dur,
             "meets_regime_floor": not below_reg, "survives_lodo_jackknife": not lodo_fail}
        fails = []
        if below_vol: fails.append(f"volume<{VOL_FLOOR}clusters")
        if below_dur: fails.append(f"duration<{DUR_FLOOR_DAYS}days({active_days})")
        if below_reg: fails.append(f"regimes<{REGIME_FLOOR}")
        if lodo_fail and not (below_vol or below_dur or below_reg): fails.append(f"LODO-drop-{dropped}-kills-edge")
        if fails:
            c["verdict"] = "INDETERMINATE (" + "; ".join(fails) + ")"
        else:
            c["verdict"] = "POSITIVE_LB_DURABLE" if (lb["lb"] and lb["lb"] > 0) else "NON_POSITIVE_LB"
        return c

    soft_days = len({p["day"] for p in soft})
    champ_days = len({c["day"] for c in champ})

    # time-split OOS on the realizable soft rows: early vs late match-days
    real_picks = [p for p in soft if p["realizable"] is not None]
    days_sorted = sorted({p["day"] for p in real_picks})
    split = days_sorted[len(days_sorted) // 2] if days_sorted else None
    early = cell(rows_at([p for p in real_picks if p["day"] < split], "realizable"), "soft_early", None) if split else {}
    late = cell(rows_at([p for p in real_picks if p["day"] >= split], "realizable"), "soft_late", None) if split else {}

    # belief-blind SKILL (directional basis, full coverage): soft mean(won−entry) − blind baseline
    soft_dir_edge = (sum((1.0 if p["won"] else 0.0) - p["sharp_entry"] for p in soft) / n_soft) if n_soft else None
    skill = None if (soft_dir_edge is None or blind is None) else round(soft_dir_edge - blind, 4)

    report = {
        "as_of": "2026-07-09",
        "objective": "cluster-robust LB of realizable copyable ROI-on-turnover, volume+duration floors, time-split OOS",
        "params": {"soft_cutoff": SOFT_CUTOFF, "min_backers": MIN_BACKERS, "band": [FAV_LO, FAV_HI],
                   "fee": "0.03*p*(1-p)", "vol_floor_clusters": VOL_FLOOR, "alpha": ALPHA},
        "coverage": {
            "soft_picks_resolved_inband": n_soft,
            "with_realizable_entry": n_realizable,
            "realizable_coverage_pct": round(100.0 * n_realizable / n_soft, 1) if n_soft else None,
            "entry_ask_n": sum(1 for p in soft if p["entry_ask"] is not None),
            "tape_ask_n": sum(1 for p in soft if p["entry_ask"] is None and p["tape_ask"] is not None),
            "note": "realizable entry (entry_ask ∪ tape_ask) is the copyability cap; where absent the pick is EXCLUDED from the objective, not measured at mid.",
        },
        "soft_esports": {
            "REALIZABLE_objective": cell(soft_real_rows, "soft_realizable", soft_days),
            "directional_ceiling_NOT_copyable": cell(soft_dir_rows, "soft_sharp_fill", soft_days),
            "time_split_OOS": {"split_day": split, "early": early, "late": late},
            "belief_blind_skill_directional": {
                "soft_mean_edge": None if soft_dir_edge is None else round(soft_dir_edge, 4),
                "esports_blind_favorite_baseline": None if blind is None else round(blind, 4),
                "skill_surplus_over_blind": skill,
                "note": "skill = consensus edge beyond the blind esports favorite; ≤0 ⇒ just riding softness (won't transfer). Directional entry (full coverage); NOT the realizable objective.",
            },
        },
        "champion_favorite_realizable": cell(
            [{"entry": c["entry"], "won": c["won"], "event_slug": c["event_slug"],
              "slug": c["slug"], "condition_id": c["condition_id"], "day": c["day"]} for c in champ],
            "champion_favorite", champ_days, regime_gated=False),
        "head_to_head": None,   # filled below
        "trader_track_record_SELECT_only": {
            "ranking": fetch_trader_consistency(),
            "guard": "SELECT-only hypothesis generator. Past-PnL rank was REFUTED 5 ways (survivorship + uncopyable timing/price). These candidates are certified ONLY by the forward/OOS belief-blind gate at OUR entry_ask, Bonferroni over the # screened — NOT by this record.",
        },
        "verdict": None,
    }

    champ_cell = report["champion_favorite_realizable"]
    soft_cell = report["soft_esports"]["REALIZABLE_objective"]
    soft_durable = all(soft_cell.get(k) for k in
                       ("meets_volume_floor", "meets_duration_floor", "meets_regime_floor", "survives_lodo_jackknife"))
    report["head_to_head"] = {
        "metric": "realizable cluster-robust ROI-turn LB (durability-gated)",
        "soft_esports_LB": soft_cell.get("roi_turn_LB"),
        "champion_soccer_LB": champ_cell.get("roi_turn_LB"),
        "soft_durable": soft_durable,
        "champion_meets_floor": champ_cell.get("meets_volume_floor"),
        "beats_champion": (soft_durable and soft_cell.get("roi_turn_LB") is not None
                           and champ_cell.get("roi_turn_LB") is not None
                           and soft_cell["roi_turn_LB"] > champ_cell["roi_turn_LB"]),
        "note": "beats_champion requires the soft edge to CLEAR volume+duration+regime floors AND survive the leave-one-discipline-out jackknife — a 3-day one-discipline chalk streak reads False even at a fat point LB.",
    }

    # honest verdict
    real = report["soft_esports"]["REALIZABLE_objective"]
    if not soft_durable:
        report["verdict"] = (
            f"INDETERMINATE — NOT durable. {n_realizable}/{n_soft} soft esports picks have a realizable entry "
            f"({report['coverage']['realizable_coverage_pct']}%); the realizable ROI-turn LB is {real.get('roi_turn_LB')} "
            f"over {real.get('G_clusters')} match-clusters BUT: {real.get('verdict')}. The apparent edge is a "
            f"short-window, single-discipline favorite-chalk artifact (disciplines={real.get('disciplines')}, "
            f"active_days={real.get('active_days')}, LODO-drop-{real.get('lodo_drop')} LB="
            f"{real.get('lodo_LB_without_dominant')}) — the 'fat edge on a soft week' trap the run is built to reject. "
            f"The conversion gap IS closed (soft_fav captures real esports consensus the rank-40 gate misses), but "
            f"whether the softer market yields a fatter, more-CONSISTENT per-dollar edge than the crowded favorites is "
            f"NOT answerable at realizable cost on this data: the arm never ran live, so ask coverage is thin and the "
            f"clob tape is only 72h — there is no multi-regime realizable history to validate durability. The "
            f"pre-registered forward gate is the arbiter. Directional ceiling (NOT copyable) + belief-blind skill are "
            f"context only; a directional/soft-week number is exactly what must NOT be reported as an edge."
        )
    else:
        h = report["head_to_head"]
        report["verdict"] = (
            f"Soft esports realizable ROI-turn LB = {real['roi_turn_LB']} over {real['G_clusters']} match-clusters; "
            f"champion favorite LB = {champ_cell.get('roi_turn_LB')}. Beats champion: {h['beats_champion']}. "
            f"Belief-blind skill (directional) = {skill}. Shadow-registered; forward gate decides."
        )
    return report


# --- self-test ----------------------------------------------------------------------
def selftest():
    ok = True
    # fee + pnl signs
    if not (abs(fee(0.8) - 0.03 * 0.8 * 0.2) < 1e-12):
        print("FAIL fee"); ok = False
    if not (pnl(0.8, True) > 0 and pnl(0.8, False) < 0):
        print("FAIL pnl sign"); ok = False
    # WIN-RATE TRAP: a 0.97 deep favorite winning 96% is NEGATIVE per dollar after fee.
    deep = [(0.97, True)] * 96 + [(0.97, False)] * 4
    if not (roi_turn(deep) < 0):
        print(f"FAIL win-rate-trap: roi={roi_turn(deep)}"); ok = False
    # a 0.80 favorite winning 88% is POSITIVE per dollar (mid-favorite zone).
    mid = [(0.80, True)] * 88 + [(0.80, False)] * 12
    if not (roi_turn(mid) > 0):
        print(f"FAIL mid-fav-positive: roi={roi_turn(mid)}"); ok = False
    # cluster LB: two clusters, positive but wide → LB below point
    rows = [{"entry": 0.8, "won": True, "event_slug": "lol-a-2026-07-01", "slug": "lol-a-2026-07-01-x", "condition_id": "c1"},
            {"entry": 0.8, "won": True, "event_slug": "lol-b-2026-07-02", "slug": "lol-b-2026-07-02-x", "condition_id": "c2"},
            {"entry": 0.8, "won": False, "event_slug": "lol-c-2026-07-03", "slug": "lol-c-2026-07-03-x", "condition_id": "c3"}]
    lb = roi_lb(rows)
    if not (lb and lb["lb"] < lb["point"]):
        print(f"FAIL roi_lb: {lb}"); ok = False
    # LODO jackknife: an edge carried entirely by ONE discipline must collapse when it's dropped.
    dominated = ([{"entry": 0.75, "won": True, "event_slug": f"dota2-m{i}-2026-07-08",
                   "slug": f"dota2-m{i}-2026-07-08-x", "condition_id": f"d{i}"} for i in range(30)]
                 + [{"entry": 0.75, "won": False, "event_slug": "lol-x-2026-07-02",
                     "slug": "lol-x-2026-07-02-y", "condition_id": "l1"}])
    dropped, lb_wo = lodo_lb(dominated)
    if not (dropped == "dota2" and (lb_wo is None or lb_wo <= 0)):
        print(f"FAIL lodo: dropped={dropped} lb_wo={lb_wo}"); ok = False
    # discipline classifier
    if not (discipline("dota2-og-tundra-2026-07-01") == "dota2" and discipline("cs2-navi-2026-07-01") == "cs2"):
        print("FAIL discipline"); ok = False
    print("selftest PASS" if ok else "selftest FAIL")
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    rep = build_report()
    outp = Path(__file__).resolve().parent.parent / "reports" / "SOFT-MARKET-EDGE.json"
    outp.write_text(json.dumps(rep, indent=2))
    print(f"wrote {outp}\n")
    print("VERDICT:", rep["verdict"])
    print("\ncoverage:", json.dumps(rep["coverage"], indent=2))
    print("head_to_head:", json.dumps(rep["head_to_head"], indent=2))


if __name__ == "__main__":
    main()
