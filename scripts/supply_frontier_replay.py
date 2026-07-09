#!/usr/bin/env python3
"""
SUPPLY-FRONTIER REPLAY — the belief-blind judge for the supply-frontier build run.

Replays candidate consensus-supply configurations over the raw tracked-wallet fill
record with WINDOW-ACCURATE gate semantics (the same gates `score_market` applies:
distinct one-sided backers, opposer cap, two-sided-MM drop, price coherence, price
band, anchor rank — plus the new ECHO-INDEPENDENCE collapse under test), and prices
every detected signal TWO ways:

  proxy entry  mean backer fill price at detection + 1c haircut  (full replay range;
               the stated-bias proxy of the wide-consensus retrospective)
  tape entry   the FIRST clob_price_tape best_ask at/after detection (<=10 min stale,
               strictly causal) — OUR realizable decision-time price. This is the
               number that decides; proxy is context.

Scoring is adversarial by construction: per-signal ROI ledger-style
(stake*((won-entry)/entry - fee)), event-cluster and day-cluster robust LBs
(effective_n.cluster_robust at t(G-1)), per-sport splits, band-x-day-matched
surplus over the >=1-backer BLIND population at the SAME entry pricing, echo
diagnostics (backer inter-arrival), and overlap vs the live champion's actual
fires (incremental-only stats). Paper-only, read-only, promotes nothing.

KNOWN BIASES (stated, not hidden):
- Wallet pool membership (active/bot/rank) is read from followed_traders TODAY and
  applied to the whole replay range — rank drift and churn are not reconstructed.
- resolved/outcome_won come from the trader_fills grading pass (same source as the
  house scoreboards); unresolved signals are DROPPED and counted.
- Two-sided (MM) detection uses the trailing window at each evaluation, matching
  score_market; but the fill record only contains TRACKED wallets' fills.
- The proxy haircut (1c) is the measured real-tax scale (real_tax.json ~1.0-1.3c);
  tape mode exists precisely because the proxy is not our price.

  ./supply_frontier_replay.py --sweep          # frontier grid -> table + JSON
  ./supply_frontier_replay.py --config v1      # one named version
  ./supply_frontier_replay.py --selftest       # pure fixtures, no DB
"""

import argparse
import csv
import io
import json
import math
import os
import subprocess
import sys
from bisect import bisect_left
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import effective_n as en  # cluster_robust()
import regime_edge as reg  # lb_small_cluster, FEE, REPORT_DIR

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q", "-v", "ON_ERROR_STOP=1"]

STAKE = 100.0
FEE = reg.FEE                      # 0.02 modeled buffer (house ledger formula)
HAIRCUT = 0.01                     # proxy-entry haircut (stated bias)
WINDOW_H = 48                      # consensus rolling window (CONSENSUS_WINDOW_HOURS)
REPLAY_DAYS = 10                   # fill-record depth to replay
TAPE_STALE_S = 600                 # max staleness of the first causal tape ask
MAX_PRICE_STD = 0.10               # champion coherence gate (fixed across configs)
REPORT = os.path.join(reg.REPORT_DIR, "supply_frontier_replay.json")

# ---------------------------------------------------------------------------
# Named versions (the iteration trail) + the sweep grid.
# pool: 'eligible' = consensus_eligible only (champion voters)
#       'wide'     = all tracked active non-bot (the wide-consensus pool)
# echo_s: collapse a backer whose first window fill lands within echo_s seconds
#         AFTER an already-counted backer's fill on the same side (0 = off).
# anchor: require >=1 backer with rank <= anchor (None = off).
# ---------------------------------------------------------------------------
VERSIONS = {
    # v1 — the starting line: wide pool, champion gates, measured at OUR price.
    "v1": dict(pool="wide", min_backers=3, max_opposers=1,
               band=(0.65, 0.98), anchor=None, echo_s=0),
    # v2 — echo-independent counting (the named v1 weakness: bot-echo/herding
    # can synthesize "3 backers" from 1 decision).
    "v2": dict(pool="wide", min_backers=3, max_opposers=1,
               band=(0.65, 0.98), anchor=None, echo_s=60),
    # v3 — spend the quality budget bought by echo-independence on wider supply:
    # anchored net>=2-independent + band floor extended to 0.60.
    "v3": dict(pool="wide", min_backers=2, max_opposers=1,
               band=(0.60, 0.98), anchor=40, echo_s=60),
    # champion replica (context row): eligible pool, champion gates.
    "champ": dict(pool="eligible", min_backers=3, max_opposers=1,
                  band=(0.65, 0.98), anchor=None, echo_s=0),
}

SWEEP = [
    ("champ", VERSIONS["champ"]),
    ("v1", VERSIONS["v1"]),
    ("v2", VERSIONS["v2"]),
    ("wide_k2_anch", dict(pool="wide", min_backers=2, max_opposers=1,
                          band=(0.65, 0.98), anchor=40, echo_s=60)),
    ("wide_k2_plain", dict(pool="wide", min_backers=2, max_opposers=1,
                           band=(0.65, 0.98), anchor=None, echo_s=60)),
    ("v3", VERSIONS["v3"]),
    ("band60_only", dict(pool="wide", min_backers=3, max_opposers=1,
                         band=(0.60, 0.65), anchor=None, echo_s=60)),
    ("wide_k4", dict(pool="wide", min_backers=4, max_opposers=1,
                     band=(0.65, 0.98), anchor=None, echo_s=60)),
]


def q(sql):
    out = subprocess.run(PG + ["-f", "-"], input=sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    return list(csv.DictReader(io.StringIO(out.stdout)))


# ---------------------------------------------------------------------------
# Data pull
# ---------------------------------------------------------------------------

def fetch_fills():
    """All BUY sports fills of tracked-active wallets in the replay range, on
    conditions where any outcome ever gathers >=2 distinct tracked backers
    (cheap pre-filter; gates re-derive everything window-accurately)."""
    return q(f"""
      WITH tracked AS (
        -- ALL tracked wallets, active or lapsed: fills only exist for periods a
        -- wallet was polled, and excluding the churned tournament cohort would
        -- bias the replay toward the post-cliff regime.
        SELECT LOWER(proxy_wallet) AS w, consensus_eligible AS elig, rank,
               COALESCE(trader_type,'') = 'bot' AS bot
        FROM followed_traders
      ),
      f AS (
        SELECT tf.condition_id AS cond, tf.outcome_index AS oidx,
               LOWER(tf.wallet) AS wallet, t.elig, t.bot, t.rank,
               extract(epoch FROM tf.ts)::float8 AS ts, tf.price,
               tf.resolved, tf.outcome_won AS won,
               COALESCE(tf.sport,'other') AS sport,
               COALESCE(tf.event_slug, tf.condition_id) AS ev
        FROM trader_fills tf JOIN tracked t ON LOWER(tf.wallet) = t.w
        WHERE tf.side = 'BUY' AND tf.is_sports
          AND tf.ts > now() - interval '{REPLAY_DAYS} days'
          AND tf.price BETWEEN 0.02 AND 0.995
      ),
      cands AS (
        SELECT cond FROM f GROUP BY cond, oidx
        HAVING COUNT(DISTINCT wallet) >= 2
      )
      SELECT f.* FROM f WHERE f.cond IN (SELECT cond FROM cands)
      ORDER BY f.cond, f.ts
    """)


def fetch_tape(conds):
    """Causal ask series for the candidate conditions inside the tape range."""
    if not conds:
        return []
    lst = ",".join("'" + c.replace("'", "") + "'" for c in sorted(conds))
    return q(f"""
      SELECT condition_id AS cond, outcome_index AS oidx,
             extract(epoch FROM recv_at)::float8 AS ts, best_ask
      FROM clob_price_tape
      WHERE best_ask IS NOT NULL AND condition_id IN ({lst})
      ORDER BY condition_id, outcome_index, recv_at
    """)


def fetch_live_favorite():
    """(cond,oidx) pairs the live champion actually fired — overlap marking."""
    return {(r["cond"], int(r["oidx"])) for r in q(
        "SELECT condition_id AS cond, outcome_index AS oidx "
        "FROM consensus_signals WHERE strategy = 'favorite'")}


# ---------------------------------------------------------------------------
# Replay engine (pure — selftest fixtures drive exactly this code)
# ---------------------------------------------------------------------------

def independent_backers(first_fills, echo_s):
    """Echo collapse: walk backers by first-fill time; one whose first fill lands
    within echo_s seconds after an already-COUNTED backer's first fill is an echo
    (does not increment). Returns the independent wallets, in arrival order."""
    indep = []
    for w, t in sorted(first_fills.items(), key=lambda kv: kv[1]):
        if echo_s > 0 and indep and (t - indep[-1][1]) < echo_s:
            continue
        indep.append((w, t))
    return [w for w, _ in indep]


def replay_condition(fills, cfg):
    """Walk one condition's fills in event time; return signals as dicts.
    A (cond,outcome) fires at most once — at the first fill instant where every
    gate passes on the trailing window. No look-ahead anywhere.

    DELIBERATE CONSERVATIVE DEVIATION from score_market: two-sided (MM) wallets
    are dropped GLOBALLY per condition (any wallet ever on >1 outcome of this
    condition in the replay range), not window-accurately. Strictly stricter —
    it can only REMOVE backers/signals, never add them — and it collapses the
    MM-churned heavy books that make window-accurate replay intractable."""
    lo, hi = cfg["band"]
    win = WINDOW_H * 3600.0
    fills = sorted(fills, key=lambda g: g["ts"])  # event time — never trust input order

    # global two-sided drop (before pool filter: stricter than score_market's
    # post-filter window view — stated bias, conservative direction)
    sides = defaultdict(set)
    for g in fills:
        sides[g["wallet"]].add(g["oidx"])
    two_sided = {w for w, s in sides.items() if len(s) > 1}
    if cfg["pool"] == "eligible":
        clean = [g for g in fills if g["wallet"] not in two_sided and g["elig"]]
    else:  # wide: eligible ∪ deep non-bot (labeled bots out of the extension)
        clean = [g for g in fills if g["wallet"] not in two_sided
                 and (g["elig"] or not g["bot"])]
    if not clean:
        return []

    # distinct-wallet prefix counters for the lazy gate (cheap upper bound —
    # window ⊆ prefix, so prefix_distinct < K ⇒ window can never pass)
    seen_by_o = defaultdict(set)
    fired = set()
    out = []
    start = 0  # two-pointer window start over `clean`
    for i, f in enumerate(clean):
        o = f["oidx"]
        seen_by_o[o].add(f["wallet"])
        if o in fired or len(seen_by_o[o]) < cfg["min_backers"]:
            continue
        t = f["ts"]
        while clean[start]["ts"] <= t - win:
            start += 1
        window = clean[start: i + 1]
        mine = [g for g in window if g["oidx"] == o]
        # backers: distinct wallets, echo-collapsed on first fill in window
        first = {}
        for g in mine:
            first.setdefault(g["wallet"], g["ts"])
        indep = independent_backers(first, cfg["echo_s"])
        if len(indep) < cfg["min_backers"]:
            continue
        # opposers: distinct one-sided wallets on other outcomes. Gates mirror
        # score_market exactly: n_backers >= K and n_opposers <= M (net is
        # tiering, not a gate).
        opp = {g["wallet"] for g in window if g["oidx"] != o}
        if len(opp) > cfg["max_opposers"]:
            continue
        prices = [g["price"] for g in mine]
        mean_p = sum(prices) / len(prices)
        var = sum((p - mean_p) ** 2 for p in prices) / len(prices)
        if math.sqrt(var) > MAX_PRICE_STD:
            continue
        if not (lo <= mean_p <= hi):
            continue
        if cfg["anchor"] is not None:
            ranks = [g["rank"] for g in mine if g["rank"] is not None]
            if not ranks or min(ranks) > cfg["anchor"]:
                continue
        firsts = sorted(first.values())
        out.append(dict(
            cond=f["cond"], oidx=o, det=t, mean_p=mean_p,
            n_backers=len(indep), n_raw_backers=len(first),
            spread_1_3=(firsts[min(2, len(firsts) - 1)] - firsts[0]),
            resolved=f["resolved"], won=f["won"], sport=f["sport"], ev=f["ev"],
        ))
        fired.add(o)
    return out


def tape_entry(ticks, det):
    """First causal ask at/after detection, capped at TAPE_STALE_S staleness."""
    if not ticks:
        return None
    times = [t for t, _ in ticks]
    i = bisect_left(times, det)
    if i == len(times) or times[i] - det > TAPE_STALE_S:
        return None
    return ticks[i][1]


def roi(entry, won):
    return (won - entry) / entry - FEE


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def day_of(ts):
    import datetime as dt
    return dt.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")


def cluster_lb(rows, key):
    """Cluster-robust one-sided 95% LB on the EVENT-mean ROI, clustered by `key`
    ('ev' = event-level, 'day' = day-level persistence wall), t(G-1) small-cluster.
    Mirrors effective_n.cluster_robust's contract: per-event surplus dicts.
    Returns None only for G<2 (no between-cluster information) — never on error."""
    by_ev, cl = defaultdict(list), {}
    for r in rows:
        by_ev[r["ev"]].append(r["roi"])
        cl.setdefault(r["ev"], r["ev"] if key == "ev" else r[key])
    if len(by_ev) < 2:
        return None
    ev_surplus = {e: sum(v) / len(v) for e, v in by_ev.items()}
    res = en.cluster_robust(ev_surplus, cl)
    if not res:
        return None
    return reg.lb_small_cluster(res["theta"], res.get("se_CR"), res.get("G"))


def score(signals, tape_by_leg, live_fav, blind_cells, tape_start=None):
    """signals -> the honest per-config block. Every signal is scored at the
    proxy entry; the tape subset additionally at OUR causal ask. Tape coverage
    is reported over TAPE-ERA signals only (det >= tape_start), not the full
    replay range — conflating the two understates coverage 3x."""
    resolved = [s for s in signals if s["resolved"] and s["won"] is not None]
    dropped_unresolved = len(signals) - len(resolved)
    rows, tape_rows = [], []
    n_tape_era = 0
    for s in resolved:
        won = 1.0 if s["won"] in (True, "t", "True") else 0.0
        e_proxy = min(s["mean_p"] + HAIRCUT, 0.995)
        r = dict(s, won=won, entry=e_proxy, roi=roi(e_proxy, won),
                 day=day_of(s["det"]),
                 overlap=(s["cond"], s["oidx"]) in live_fav)
        rows.append(r)
        if tape_start is not None and s["det"] >= tape_start:
            n_tape_era += 1
        ask = tape_entry(tape_by_leg.get((s["cond"], s["oidx"]), []), s["det"])
        if ask is not None and 0.02 <= ask <= 0.995:
            tape_rows.append(dict(r, entry=ask, roi=roi(ask, won)))

    def block(rr):
        if not rr:
            return dict(n=0)
        n = len(rr)
        mean_roi = sum(r["roi"] for r in rr) / n
        wr = sum(r["won"] for r in rr) / n
        by_sport = defaultdict(list)
        for r in rr:
            by_sport[r["sport"]].append(r["roi"])
        # band-x-day matched blind surplus at the SAME pricing basis
        surp = None
        if blind_cells:
            tot, acc = 0, 0.0
            for r in rr:
                cell = blind_cells.get((band_of(r["mean_p"]), r["day"]))
                if cell:
                    acc += r["roi"] - cell
                    tot += 1
            surp = (acc / tot, tot) if tot else None
        return dict(
            n=n, events=len({r["ev"] for r in rr}), days=len({r["day"] for r in rr}),
            win_rate=round(wr, 4), roi=round(mean_roi, 4),
            roi_lb_event=rnd(cluster_lb(rr, "ev")), roi_lb_day=rnd(cluster_lb(rr, "day")),
            surplus_over_blind=(round(surp[0], 4), surp[1]) if surp else None,
            per_sport={k: (len(v), round(sum(v) / len(v), 4))
                       for k, v in sorted(by_sport.items(), key=lambda kv: -len(kv[1]))},
            incremental_n=sum(1 for r in rr if not r["overlap"]),
            incremental_roi=rnd(avg([r["roi"] for r in rr if not r["overlap"]])),
        )

    echo = [s["spread_1_3"] for s in resolved]
    return dict(
        dropped_unresolved=dropped_unresolved,
        proxy=block(rows),
        tape=dict(block(tape_rows),
                  n_tape_era=n_tape_era,
                  coverage=round(len(tape_rows) / n_tape_era, 3) if n_tape_era else 0),
        echo_median_1to3_s=round(sorted(echo)[len(echo) // 2], 1) if echo else None,
    )


def band_of(p):
    return "b60" if p < 0.65 else ("b65" if p < 0.80 else "b80")


def avg(xs):
    return sum(xs) / len(xs) if xs else None


def rnd(x):
    return round(x, 4) if isinstance(x, float) else x


def build_blind_cells(by_cond):
    """The >=1-backer blind population priced at the SAME proxy basis:
    every (cond,outcome,day-of-first-tracked-fill) with a resolution, entry =
    first fill price + haircut. Returns mean ROI per (band, day) cell."""
    cells = defaultdict(list)
    for cond, fills in by_cond.items():
        seen = set()
        for f in fills:
            leg = (cond, f["oidx"])
            if leg in seen:
                continue
            seen.add(leg)
            if not f["resolved"] or f["won"] is None:
                continue
            won = 1.0 if f["won"] in (True, "t", "True") else 0.0
            e = min(f["price"] + HAIRCUT, 0.995)
            cells[(band_of(f["price"]), day_of(f["ts"]))].append(roi(e, won))
    return {k: sum(v) / len(v) for k, v in cells.items() if len(v) >= 5}


# ---------------------------------------------------------------------------
# Selftest — pure fixtures through the exact replay path
# ---------------------------------------------------------------------------

def _mk(cond, oidx, wallet, ts, price, elig=True, bot=False, rank=10,
        resolved=True, won=True, sport="mlb", ev=None):
    return dict(cond=cond, oidx=oidx, wallet=wallet, ts=float(ts), price=price,
                elig=elig, bot=bot, rank=rank, resolved=resolved, won=won,
                sport=sport, ev=ev or cond)


def selftest():
    base = dict(pool="wide", min_backers=3, max_opposers=1,
                band=(0.65, 0.98), anchor=None, echo_s=0)
    ok = 0

    # 1. three independent backers fire once, at the third fill
    fills = [_mk("c1", 0, "a", 0, 0.80), _mk("c1", 0, "b", 100, 0.81),
             _mk("c1", 0, "c", 200, 0.79), _mk("c1", 0, "d", 300, 0.80)]
    s = replay_condition(fills, base)
    assert len(s) == 1 and s[0]["det"] == 200 and s[0]["n_backers"] == 3, s
    ok += 1

    # 2. echo collapse: b,c within 60s of a -> only 1 independent -> no fire;
    #    a later slow backer chain still fires
    fills = [_mk("c2", 0, "a", 0, 0.80), _mk("c2", 0, "b", 10, 0.80),
             _mk("c2", 0, "c", 20, 0.80),
             _mk("c2", 0, "d", 400, 0.80), _mk("c2", 0, "e", 800, 0.80)]
    cfg = dict(base, echo_s=60)
    s = replay_condition(fills, cfg)
    assert len(s) == 1 and s[0]["det"] == 800, ("echo", s)
    # sanity: without echo the same book fires at t=20
    assert replay_condition(fills, base)[0]["det"] == 20
    ok += 1

    # 3. two-sided wallet is dropped from both sides
    fills = [_mk("c3", 0, "a", 0, 0.80), _mk("c3", 0, "b", 50, 0.80),
             _mk("c3", 1, "b", 60, 0.20), _mk("c3", 0, "c", 100, 0.80),
             _mk("c3", 0, "d", 150, 0.81)]
    s = replay_condition(fills, base)
    assert len(s) == 1 and s[0]["det"] == 150 and s[0]["n_backers"] == 3, ("mm", s)
    ok += 1

    # 4. opposer cap blocks; band blocks; anchor blocks unranked (fail-closed)
    fills = [_mk("c4", 0, "a", 0, 0.80), _mk("c4", 0, "b", 10, 0.80),
             _mk("c4", 0, "c", 20, 0.80),
             _mk("c4", 1, "x", 5, 0.2), _mk("c4", 1, "y", 6, 0.2)]
    assert replay_condition(fills, base) == [], "opposers>1 must block"
    fills = [_mk("c5", 0, w, t, 0.50) for w, t in [("a", 0), ("b", 1), ("c", 2)]]
    assert replay_condition(fills, base) == [], "band must block 0.50"
    fills = [_mk("c6", 0, w, t, 0.80, rank=None) for w, t in [("a", 0), ("b", 1), ("c", 2)]]
    assert replay_condition(fills, dict(base, anchor=40)) == [], "anchor fail-closed"
    ok += 1

    # 5. pool filters: bot excluded from wide, deep excluded from eligible
    fills = [_mk("c7", 0, "a", 0, 0.80, elig=False),
             _mk("c7", 0, "b", 10, 0.80, elig=False, bot=True),
             _mk("c7", 0, "c", 20, 0.80, elig=False),
             _mk("c7", 0, "d", 30, 0.80, elig=False)]
    s = replay_condition(fills, base)
    assert len(s) == 1 and s[0]["det"] == 30 and s[0]["n_backers"] == 3, ("bot", s)
    assert replay_condition(fills, dict(base, pool="eligible")) == [], "deep out of eligible"
    ok += 1

    # 6. tape entry is strictly causal and staleness-capped
    ticks = [(100.0, 0.82), (200.0, 0.83)]
    assert tape_entry(ticks, 150.0) == 0.83
    assert tape_entry(ticks, 90.0) == 0.82
    assert tape_entry(ticks, 201.0) is None  # nothing after det
    assert tape_entry([(1000.0, 0.9)], 100.0) is None  # > TAPE_STALE_S ahead
    ok += 1

    # 7. window expiry: stale first backer ages out of the 48h window
    late = WINDOW_H * 3600 + 10
    fills = [_mk("c8", 0, "a", 0, 0.80), _mk("c8", 0, "b", late, 0.80),
             _mk("c8", 0, "c", late + 1, 0.80), _mk("c8", 0, "d", late + 2, 0.80)]
    s = replay_condition(fills, base)
    assert len(s) == 1 and s[0]["det"] == late + 2, ("window", s)
    ok += 1

    print(f"selftest: {ok}/7 blocks OK")


# ---------------------------------------------------------------------------

def run(configs):
    print("pulling fills…", file=sys.stderr)
    raw = fetch_fills()
    by_cond = defaultdict(list)
    for r in raw:
        by_cond[r["cond"]].append(dict(
            cond=r["cond"], oidx=int(r["oidx"]), wallet=r["wallet"],
            elig=r["elig"] == "t", bot=r["bot"] == "t",
            rank=int(r["rank"]) if r["rank"] else None,
            ts=float(r["ts"]), price=float(r["price"]),
            resolved=r["resolved"] == "t",
            won=(r["won"] == "t") if r["won"] else None,
            sport=r["sport"], ev=r["ev"]))
    print(f"fills: {len(raw)} on {len(by_cond)} conditions", file=sys.stderr)

    live_fav = fetch_live_favorite()
    blind_cells = build_blind_cells(by_cond)

    # detect once per config, then tape-join the union of detected legs
    detected = {}
    for name, cfg in configs:
        sigs = []
        for fills in by_cond.values():
            sigs.extend(replay_condition(fills, cfg))
        detected[name] = sigs
    legs = {(s["cond"], s["oidx"]) for sigs in detected.values() for s in sigs}
    conds = {c for c, _ in legs}
    print(f"tape pull for {len(conds)} conditions…", file=sys.stderr)
    tape_by_leg = defaultdict(list)
    for r in fetch_tape(conds):
        leg = (r["cond"], int(r["oidx"]))
        if leg in legs:
            tape_by_leg[leg].append((float(r["ts"]), float(r["best_ask"])))

    tape_start_row = q("SELECT extract(epoch FROM min(recv_at))::float8 AS t FROM clob_price_tape")
    tape_start = float(tape_start_row[0]["t"]) if tape_start_row and tape_start_row[0]["t"] else None

    out = {}
    for name, cfg in configs:
        out[name] = dict(cfg=str(cfg),
                         **score(detected[name], tape_by_leg, live_fav, blind_cells, tape_start))
        p, t = out[name]["proxy"], out[name]["tape"]
        print(f"\n== {name} :: {cfg}")
        print(f"  proxy: n={p.get('n')} ev={p.get('events')} d={p.get('days')} "
              f"wr={p.get('win_rate')} roi={p.get('roi')} lb_ev={p.get('roi_lb_event')} "
              f"lb_day={p.get('roi_lb_day')} surplus={p.get('surplus_over_blind')}")
        print(f"  TAPE : n={t.get('n')} cov={t.get('coverage')} wr={t.get('win_rate')} "
              f"roi={t.get('roi')} lb_ev={t.get('roi_lb_event')} lb_day={t.get('roi_lb_day')}")
        print(f"  sports(proxy): {p.get('per_sport')}")
        print(f"  incremental(non-champion): n={p.get('incremental_n')} roi={p.get('incremental_roi')} "
              f"echo_med_1to3={out[name]['echo_median_1to3_s']}s")
    os.makedirs(reg.REPORT_DIR, exist_ok=True)
    with open(REPORT, "w") as fh:
        json.dump(out, fh, indent=2, default=str)
    print(f"\nwrote {REPORT}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--config", help="named version (v1/v2/v3/champ)")
    ap.add_argument("--sweep", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    if args.config:
        run([(args.config, VERSIONS[args.config])])
    else:
        run(SWEEP)


if __name__ == "__main__":
    main()
