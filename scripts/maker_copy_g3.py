#!/usr/bin/env python3
"""
MAKER-COPY G3 — forward maker-fill simulator. Measures, does not assume, whether copying a followed
sharp with a MAKER order (a resting BUY at the sharp's fill price P) beats paying the taker spread —
and how much of any apparent gain is adverse selection. Extends D26 (Market-making KILL+PARK) with
the forward-tape evidence G2/G2b explicitly punted here. Paper-only, read-only, promotes nothing.

THE TRAP (why this exists): we are COPIERS — we act after the sharp fills and has already lifted the
ask. Posting a maker BUY "at their price" means resting a bid BELOW the current market. A resting bid
only fills when price comes BACK DOWN — i.e. when the position moves AGAINST us: favorites that WIN
drift to $1 and our bid NEVER fills (we miss the winners); ones that revert come back and our bid
fills (we catch the losers). That is adverse selection and it is the whole verdict. This idea was
wrong twice (G2 v1 "+4.8% LB" = a units bug × a backwards complement rule). We report a MENU of fill
models + the adverse-selection gap + a cluster-robust LB — never a single maker number.

DATA-SEMANTICS FINDING (see PREREG ADDENDUM): clob_price_tape is a faithful top-of-book
(best_bid/best_ask) inflection series with NO trade tape — on a price_change event last_price/last_size
are order-BOOK-LEVEL churn, not executed trades (live_tape.rs:141-142, :222-223). So a volume-based
fill model is NOT measurable here (it would count quote flicker as volume — the very trap). We bracket
the unknowable queue position with three best_ask-only models:
  OPTIMISTIC (touch)  filled if best_ask ≤ P ever in the rest window          (100% queue capture; ceiling)
  DWELL      (realistic) best_ask ≤ P across ≥2 inflections spanning ≥DWELL_S  (offer sat long enough)
  PESSIMISTIC (through) best_ask < P strictly (price traded THROUGH our level) (last-in-queue)
The realized volume / partial-fill / queue-capture fraction remains OPEN (needs a real trade tape).

JOIN: signal fires at T=consensus_signals.first_detected_at on (condition_id,outcome_index); P = the
EARLIEST followed-sharp BUY fill (trader_fills) in [T−5m,T+5m]; walk clob_price_tape on that leg after
T. Fill-timing anchors on exch_ts (price_change) / recv_at (book, NULL exch_ts) — same exchange clock
as trader_fills.ts (≈zero skew). Decision-lag sweep drops any fill before T+lag (no look-ahead).

COST: flat_stake=$100, fee=2% buffer (also fee=0; Polymarket's posted trade fee is currently 0). Maker
P&L booked ONLY on signals a model FILLED: stake·((won−P)/P − fee). Taker reference on the SAME signals:
COALESCE(entry_ask, initial_mean_price+0.01). Cluster-robust LB: event-cluster (event_slug|condition_id)
via effective_n.cluster_robust read at small-cluster t(G−1) (regime_edge.lb_small_cluster); day-cluster
LB surfaced as the persistence wall.

VERDICT BANDS (prereg §7): INDETERMINATE-BY-POWER if n_filled<30 OR day-clusters<5. GO needs adequate
power AND filled-LB>0 after fees AND adverse-gap≥0 AND survives the audit AND maker≥taker. Expected
today: INDETERMINATE-BY-POWER (tape ~2d deep) — it accrues; re-run as the tape deepens.

  ./maker_copy_g3.py                 # live DB → reports/maker_copy_g3.json + printed menu
  ./maker_copy_g3.py --all-strategies  # robustness universe (all non-_blind arms), context only
  ./maker_copy_g3.py --selftest      # fixtures incl. the anti-regression guards (units/look-ahead/clock/adverse)
"""

import argparse
import csv
import io
import json
import math
import os
import subprocess
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import effective_n as en          # cluster_robust()
import regime_edge as reg         # lb_small_cluster, FEE, REPORT_DIR

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q", "-v", "ON_ERROR_STOP=1"]

STAKE = 100.0
FEE = reg.FEE                     # 0.02 modeled buffer (also report fee=0)
TAPE_START = "2026-07-07 10:47:00+00"   # first clob_price_tape row; before this there is no forward tape
FILL_WINDOW_MIN = 5              # sharp-fill match window [T−5m, T+5m]
LAGS_S = [0, 12, 60]            # decision lag: hot-lane (12s) vs poll (60s) vs instant
CANCELS_MIN = [5, 15, 60, None]  # cancel-after; None = rest until tape coverage ends (~hours, not settlement)
DWELL_S = 30                     # DWELL model: best_ask ≤ P must persist ≥ this, across ≥2 inflections
MAX_TAPE_H = 24                  # bound the tape pull per leg
MIN_FILLED = 30                  # power floor (prereg §7)
MIN_DAYS = 5                     # persistence floor (prereg §7)
FILL_MODELS = ["optimistic", "dwell", "pessimistic"]
REPORT = os.path.join(reg.REPORT_DIR, "maker_copy_g3.json")


def q(sql):
    out = subprocess.run(PG + ["-f", "-"], input=sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    return list(csv.DictReader(io.StringIO(out.stdout)))


def _universe_cte(all_strategies):
    strat = "s.strategy <> '_blind'" if all_strategies else "s.strategy = 'favorite'"
    return f"""
      WITH sig AS (
        SELECT s.id, s.condition_id, s.outcome_index, s.first_detected_at AS t0,
               COALESCE(s.event_slug, s.condition_id) AS ev, date(s.first_detected_at)::text AS day,
               s.initial_mean_price AS anchor, s.entry_ask, s.outcome_won::int AS won
        FROM consensus_signals s
        WHERE {strat} AND s.resolved AND s.outcome_won IS NOT NULL
          AND s.initial_mean_price IS NOT NULL AND s.condition_id IS NOT NULL
          AND s.first_detected_at >= '{TAPE_START}'
          AND EXISTS (SELECT 1 FROM trader_fills f
                      WHERE f.condition_id = s.condition_id AND f.outcome_index = s.outcome_index
                        AND f.side = 'BUY'
                        AND f.ts BETWEEN s.first_detected_at - interval '{FILL_WINDOW_MIN} min'
                                     AND s.first_detected_at + interval '{FILL_WINDOW_MIN} min')
          AND EXISTS (SELECT 1 FROM clob_price_tape p
                      WHERE p.condition_id = s.condition_id AND p.outcome_index = s.outcome_index
                        AND p.recv_at > s.first_detected_at)
      )"""


def fetch_signals(all_strategies):
    return q(_universe_cte(all_strategies) + """
      SELECT id, condition_id, outcome_index, extract(epoch FROM t0)::float AS t0,
             ev, day, anchor::float AS anchor,
             entry_ask::float AS entry_ask, anchor::float AS anchor2, won
      FROM sig ORDER BY t0""")


def fetch_sharp_fills(all_strategies):
    """Every followed-sharp BUY fill in [T−5m, T+5m] per signal — P computed in Python (earliest fill)."""
    return q(_universe_cte(all_strategies) + f"""
      SELECT sig.id, extract(epoch FROM f.ts)::float AS ts, f.price::float AS price, f.size_usd::float AS size_usd
      FROM sig JOIN trader_fills f
        ON f.condition_id = sig.condition_id AND f.outcome_index = sig.outcome_index
       AND f.side = 'BUY'
       AND f.ts BETWEEN sig.t0 - interval '{FILL_WINDOW_MIN} min' AND sig.t0 + interval '{FILL_WINDOW_MIN} min'
      ORDER BY sig.id, f.ts""")


def fetch_tape(all_strategies):
    """Top-of-book inflections per leg after T. eff_ts = exch_ts (price_change) else recv_at (book)."""
    return q(_universe_cte(all_strategies) + f"""
      SELECT sig.id, p.event_type, p.best_ask::float AS best_ask, p.last_size,
             extract(epoch FROM p.exch_ts)::float AS exch_ts,
             extract(epoch FROM p.recv_at)::float  AS recv_at
      FROM sig JOIN clob_price_tape p
        ON p.condition_id = sig.condition_id AND p.outcome_index = sig.outcome_index
      WHERE p.recv_at > sig.t0 AND p.recv_at < sig.t0 + interval '{MAX_TAPE_H} hours'
      ORDER BY sig.id, COALESCE(p.exch_ts, p.recv_at)""")


# --------------------------------------------------------------------------------------------
# Core fill decision — best_ask-only (the tape has no trade tape; last_size is book churn, unused).
# --------------------------------------------------------------------------------------------
def leg_fills(tape_rows, P, t0, lag_s, cancel_s):
    """tape_rows: list of {best_ask, eff_ts} for one leg. Returns {model: (filled_bool, first_fill_secs)}.
    Window = [t0+lag, t0+cancel] on eff_ts (the exchange/observation clock). NEVER reads last_size."""
    lo = t0 + lag_s
    hi = None if cancel_s is None else t0 + cancel_s
    at_or_below = []   # secs-after-T of rows with best_ask ≤ P, within window
    below = []         # strictly-below rows within window
    for r in tape_rows:
        ts = r["eff_ts"]
        if ts < lo or (hi is not None and ts > hi):
            continue
        ba = r["best_ask"]
        if ba is None:
            continue
        if ba <= P:
            at_or_below.append(ts - t0)
        if ba < P:
            below.append(ts - t0)
    opt = len(at_or_below) >= 1
    dwell = len(at_or_below) >= 2 and (max(at_or_below) - min(at_or_below)) >= DWELL_S
    pess = len(below) >= 1
    return {
        "optimistic": (opt, min(at_or_below) if at_or_below else None),
        "dwell": (dwell, min(at_or_below) if dwell else None),
        "pessimistic": (pess, min(below) if below else None),
    }


def _median(xs):
    if not xs:
        return None
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0


def _cluster_lb(surplus_by_id, cluster_by_id):
    """Event/day-clustered mean + small-cluster t(G−1) LB via the shared libs (byte-identical to gate)."""
    if len(surplus_by_id) < 2:
        return None, None, len(set(cluster_by_id.get(i) for i in surplus_by_id))
    cr = en.cluster_robust(surplus_by_id, {i: cluster_by_id[i] for i in surplus_by_id})
    if not cr:
        return None, None, 0
    theta, G = cr["theta"], cr["G"]
    lb = reg.lb_small_cluster(theta, cr["se_CR"], G)
    return theta, lb, G


def evaluate(sigs, P_by_id, tape_by_id, fee):
    """Full menu: per fill_model × lag × cancel, the metrics prereg §6 freezes."""
    ids = [s["id"] for s in sigs]
    won = {s["id"]: int(s["won"]) for s in sigs}
    ev = {s["id"]: s["ev"] for s in sigs}
    day = {s["id"]: s["day"] for s in sigs}
    entry_taker = {s["id"]: (s["entry_ask"] if s["entry_ask"] is not None else s["anchor"] + 0.01)
                   for s in sigs}
    P = P_by_id
    n_total = len(ids)
    won_ids = [i for i in ids if won[i] == 1]

    # taker book on ALL fillable signals (the incumbent we compare against), event-clustered.
    taker_roi = {i: (won[i] - entry_taker[i]) / entry_taker[i] - fee for i in ids}
    t_theta, t_lb, t_G = _cluster_lb(taker_roi, ev)
    taker_block = {
        "roi_mean": round(sum(taker_roi.values()) / n_total, 5) if n_total else None,
        "roi_cluster_lb": None if t_lb is None else round(t_lb, 5),
        "win_rate": round(sum(won.values()) / n_total, 4) if n_total else None,
        "n": n_total, "event_clusters": t_G, "mean_entry": round(sum(entry_taker.values()) / n_total, 4),
    }

    out = {"fee": fee, "n_total": n_total, "n_won": len(won_ids), "taker": taker_block, "models": {}}
    for model in FILL_MODELS:
        cells = {}
        for lag in LAGS_S:
            for cancel in CANCELS_MIN:
                cancel_s = None if cancel is None else cancel * 60
                filled_ids, fill_secs = [], []
                for s in sigs:
                    i = s["id"]
                    res = leg_fills(tape_by_id.get(i, []), P[i], s["t0"], lag, cancel_s)
                    ok, secs = res[model]
                    if ok:
                        filled_ids.append(i)
                        if secs is not None:
                            fill_secs.append(secs)
                missed_ids = [i for i in ids if i not in set(filled_ids)]
                nf = len(filled_ids)

                # maker ROI booked at P on the FILLED set (fractional, fee-charged)
                maker_roi_filled = {i: (won[i] - P[i]) / P[i] - fee for i in filled_ids}
                # hypothetical maker ROI on the MISSED set (booked at P too — ONLY to isolate selection)
                maker_roi_missed = {i: (won[i] - P[i]) / P[i] - fee for i in missed_ids}

                m_theta, m_lb, m_G = _cluster_lb(maker_roi_filled, ev)
                _, m_lb_day, m_Gday = _cluster_lb(maker_roi_filled, day)

                wr_filled = (sum(won[i] for i in filled_ids) / nf) if nf else None
                wr_missed = (sum(won[i] for i in missed_ids) / len(missed_ids)) if missed_ids else None
                roi_missed_mean = (sum(maker_roi_missed.values()) / len(missed_ids)) if missed_ids else None

                # head-to-head vs taker on the SAME filled subset
                taker_on_filled = (sum(taker_roi[i] for i in filled_ids) / nf) if nf else None
                # per-signal maker edge (abstain on missed = 0), for the "does it beat taker overall" read
                maker_edge_per_signal = (sum(maker_roi_filled.values()) / n_total) if n_total else None

                miss_win_frac = (sum(1 for i in won_ids if i in set(missed_ids)) / len(won_ids)
                                 if won_ids else None)

                cells[_cell_name(lag, cancel)] = {
                    "lag_s": lag, "cancel_min": cancel,
                    "n_filled": nf, "fill_rate": round(nf / n_total, 4) if n_total else None,
                    "median_fill_secs": _median(fill_secs),
                    "mean_entry_P": round(sum(P[i] for i in filled_ids) / nf, 4) if nf else None,
                    "roi_filled_mean": round(m_theta, 5) if m_theta is not None else None,
                    "roi_filled_cluster_lb": None if m_lb is None else round(m_lb, 5),
                    "roi_filled_event_clusters": m_G,
                    "roi_filled_day_cluster_lb": None if m_lb_day is None else round(m_lb_day, 5),
                    "roi_filled_day_clusters": m_Gday,
                    "maker_edge_per_signal": round(maker_edge_per_signal, 5) if maker_edge_per_signal is not None else None,
                    "wr_filled": round(wr_filled, 4) if wr_filled is not None else None,
                    "wr_missed": round(wr_missed, 4) if wr_missed is not None else None,
                    "adverse_gap_wr": (round(wr_filled - wr_missed, 4)
                                       if (wr_filled is not None and wr_missed is not None) else None),
                    "adverse_gap_roi": (round(m_theta - roi_missed_mean, 5)
                                        if (m_theta is not None and roi_missed_mean is not None) else None),
                    "roi_missed_hypothetical": round(roi_missed_mean, 5) if roi_missed_mean is not None else None,
                    "miss_the_winners_frac": round(miss_win_frac, 4) if miss_win_frac is not None else None,
                    "taker_roi_on_filled": round(taker_on_filled, 5) if taker_on_filled is not None else None,
                    "maker_minus_taker_on_filled": (round(m_theta - taker_on_filled, 5)
                                                    if (m_theta is not None and taker_on_filled is not None) else None),
                }
        out["models"][model] = cells
    return out


def _cell_name(lag, cancel):
    return f"lag{lag}s_cancel{'RES' if cancel is None else str(cancel) + 'm'}"


def _build(all_strategies):
    sigs = fetch_signals(all_strategies)
    for s in sigs:
        s["t0"] = float(s["t0"]); s["anchor"] = float(s["anchor"])
        s["entry_ask"] = float(s["entry_ask"]) if s["entry_ask"] not in ("", None) else None
        s["won"] = int(s["won"])
    # P = earliest sharp BUY fill price per signal (fills come back time-ordered)
    P_by_id, wsum, wnum = {}, defaultdict(float), defaultdict(float)
    for f in fetch_sharp_fills(all_strategies):
        i = f["id"]
        if i not in P_by_id:
            P_by_id[i] = float(f["price"])          # earliest (query is ORDER BY ts)
        sz = float(f["size_usd"]); wsum[i] += float(f["price"]) * sz; wnum[i] += sz
    # tape rows grouped by signal, eff_ts = exch_ts else recv_at
    tape_by_id = defaultdict(list)
    for r in fetch_tape(all_strategies):
        exch = r["exch_ts"]
        eff = float(exch) if exch not in ("", None) else float(r["recv_at"])
        ba = r["best_ask"]
        tape_by_id[r["id"]].append({"best_ask": float(ba) if ba not in ("", None) else None, "eff_ts": eff})
    return sigs, P_by_id, tape_by_id


def run(all_strategies):
    sigs, P_by_id, tape_by_id = _build(all_strategies)
    sigs = [s for s in sigs if s["id"] in P_by_id]   # need a sharp P
    n = len(sigs)
    n_days = len({s["day"] for s in sigs})
    res_fee = evaluate(sigs, P_by_id, tape_by_id, FEE)
    res_zero = evaluate(sigs, P_by_id, tape_by_id, 0.0)

    # verdict on the DWELL (realistic) model, headline cell lag12s_cancel15m — pick best n_filled anyway
    powered = False
    for model in FILL_MODELS:
        for cell in res_fee["models"][model].values():
            if cell["n_filled"] >= MIN_FILLED and n_days >= MIN_DAYS:
                powered = True
    verdict = ("INDETERMINATE-BY-POWER: max n_filled < %d and/or %d day-clusters < %d — accruing; "
               "no execution-policy claim certified. Extends D26 (KILL+PARK); nothing promoted."
               % (MIN_FILLED, n_days, MIN_DAYS)) if not powered else \
              "POWERED — read the menu + audit gate before any wording strengthens"
    out = {
        "meta": {
            "universe": "all_non_blind" if all_strategies else "favorite",
            "n_signals": n, "n_day_clusters": n_days, "tape_start": TAPE_START,
            "stake": STAKE, "fee_buffer": FEE, "lags_s": LAGS_S, "cancels_min": CANCELS_MIN,
            "dwell_s": DWELL_S, "min_filled_floor": MIN_FILLED, "min_days_floor": MIN_DAYS,
            "P_definition": "earliest followed-sharp BUY fill in [T-5m,T+5m] (the fill we copy)",
            "prereg": "reports/PREREG_20260709T011424Z_maker_copy_g3.md (+ _ADDENDUM data-semantics deviation)",
            "fill_models": {
                "optimistic": "best_ask ≤ P touched (100% queue capture; fantasy ceiling)",
                "dwell": f"best_ask ≤ P across ≥2 inflections spanning ≥{DWELL_S}s (realistic middle)",
                "pessimistic": "best_ask < P strict — price traded THROUGH our level (last-in-queue)"},
            "NOT_MEASURABLE": "realized volume / partial-fill / queue-capture fraction — the tape is "
                              "top-of-book only (last_size = book-level churn, NOT trades; live_tape.rs:222). "
                              "Still OPEN; needs a real trade tape. NEVER inferred from last_size here.",
            "clock": "fill-timing on exch_ts (price_change) / recv_at (book, NULL exch_ts); same exchange "
                     "clock as trader_fills.ts (≈zero skew). book rows carry NULL exch_ts (recv_at fallback).",
            "caveats": [
                "tape ~2 days deep → FORWARD-ACCRUING; re-run as it deepens (idempotent, read-only)",
                "'cancel=until-resolution' is bounded by TAPE COVERAGE (~hours, universe=hot 6h), not settlement",
                "adverse-selection gap uses hypothetical maker-P booking on the MISSED set to isolate selection",
                "event clusters ≈ signal count (≈1 signal/event); the BINDING wall is the ~2 day-clusters"],
        },
        "fee_buffer_2pct": res_fee, "fee_zero": res_zero, "verdict": verdict,
    }
    os.makedirs(reg.REPORT_DIR, exist_ok=True)
    with open(REPORT, "w") as f:
        json.dump(out, f, indent=1, default=str)
    _print(out)
    print(f"\nartifact → {REPORT}")
    return out


def _f(x, s="+.2%"):
    return "   —  " if x is None or (isinstance(x, float) and x != x) else format(x, s)


def _print(o):
    m = o["meta"]
    print("=" * 100)
    print(f"MAKER-COPY G3 · universe={m['universe']} · {m['n_signals']} resolved fillable signals · "
          f"{m['n_day_clusters']} day-clusters · tape from {m['tape_start']}")
    print("⚠ top-of-book tape only — no trade tape; realized volume/queue-capture NOT measurable (still OPEN).")
    print(f"  P = {m['P_definition']}")
    tk = o['fee_buffer_2pct']['taker']
    print(f"  TAKER reference (same signals, fee 2%): ROI {_f(tk['roi_mean'])} "
          f"(cluster-LB {_f(tk['roi_cluster_lb'])}) · win {_f(tk['win_rate'],'.0%')} · entry {tk['mean_entry']:.3f}")
    print(f"  VERDICT: {o['verdict']}")
    for model in FILL_MODELS:
        print("\n" + "-" * 100)
        print(f"FILL MODEL: {model.upper()}  [{m['fill_models'][model]}]  (fee 2% buffer)")
        print(f"  {'cell':<20}{'nfill':>6}{'fill%':>7}{'roi/fill':>10}{'evLB':>9}{'dayLB':>9}"
              f"{'wr_fil':>8}{'wr_mis':>8}{'advWR':>8}{'missWin':>8}{'mkr−tkr':>9}")
        for name, c in o["fee_buffer_2pct"]["models"][model].items():
            print(f"  {name:<20}{c['n_filled']:>6}{_f(c['fill_rate'],'.0%'):>7}"
                  f"{_f(c['roi_filled_mean']):>10}{_f(c['roi_filled_cluster_lb']):>9}"
                  f"{_f(c['roi_filled_day_cluster_lb']):>9}{_f(c['wr_filled'],'.0%'):>8}"
                  f"{_f(c['wr_missed'],'.0%'):>8}{_f(c['adverse_gap_wr'],'+.0%'):>8}"
                  f"{_f(c['miss_the_winners_frac'],'.0%'):>8}{_f(c['maker_minus_taker_on_filled']):>9}")


# ============================================================================================
# SELF-TEST — the anti-regression guards (prereg §9 / ADDENDUM). Must fail loudly on any historical bug.
# ============================================================================================
def _selftest():
    ok = True

    def sig(i, won, anchor=0.80, entry_ask=0.82, ev=None, day="2026-07-07"):
        return {"id": i, "won": won, "anchor": anchor, "entry_ask": entry_ask,
                "ev": ev or f"ev{i}", "day": day, "t0": 1000.0}

    # (A) ADVERSE SELECTION visible: runaway winner never touches (missed); reverting loser fills.
    #     P = 0.80. Winner's ask runs 0.83→0.90 (never ≤0.80). Loser's ask reverts 0.83→0.78 (touches).
    sigs = [sig("win", 1), sig("lose", 0)]
    P = {"win": 0.80, "lose": 0.80}
    tape = {
        "win":  [{"best_ask": 0.83, "eff_ts": 1030.0}, {"best_ask": 0.90, "eff_ts": 1200.0}],
        "lose": [{"best_ask": 0.83, "eff_ts": 1030.0}, {"best_ask": 0.78, "eff_ts": 1120.0}],
    }
    r = evaluate(sigs, P, tape, fee=0.0)
    cell = r["models"]["optimistic"]["lag0s_cancel60m"]
    a1 = cell["n_filled"] == 1 and cell["wr_filled"] == 0.0 and cell["wr_missed"] == 1.0
    a2 = cell["adverse_gap_wr"] == -1.0 and cell["miss_the_winners_frac"] == 1.0
    ok = ok and a1 and a2
    print(f"  [{'ok' if a1 and a2 else 'FAIL'}] adverse selection: filled={cell['n_filled']} (the loser), "
          f"wr_filled {cell['wr_filled']:.0%} < wr_missed {cell['wr_missed']:.0%}, "
          f"advWR {cell['adverse_gap_wr']:+.0%}, miss-winners {cell['miss_the_winners_frac']:.0%}")

    # (B) UNITS / flicker guard: a huge last_size at an ask ABOVE P must NOT create a fill. The fill
    #     decision reads best_ask only; last_size (book churn) is never summed into a fill. (G2 units bug.)
    tape_big = {"x": [{"best_ask": 0.95, "eff_ts": 1050.0, "last_size": 1e9}]}  # last_size ignored by leg_fills
    res_b = leg_fills(tape_big["x"], P=0.80, t0=1000.0, lag_s=0, cancel_s=3600)
    b_ok = res_b["optimistic"][0] is False and res_b["dwell"][0] is False and res_b["pessimistic"][0] is False
    ok = ok and b_ok
    print(f"  [{'ok' if b_ok else 'FAIL'}] units/flicker guard: ask>P with last_size=1e9 → NO fill "
          f"(book churn is never counted as volume)")

    # (C) NO LOOK-AHEAD: a touch strictly BEFORE T+lag must be dropped. Ask ≤ P only at t_rel=5s;
    #     with lag=12s the window starts at t_rel=12 → no capturable fill.
    tape_early = [{"best_ask": 0.79, "eff_ts": 1005.0}]   # t_rel = 5s < lag 12s
    pre = leg_fills(tape_early, P=0.80, t0=1000.0, lag_s=0, cancel_s=3600)     # lag0 → fills
    post = leg_fills(tape_early, P=0.80, t0=1000.0, lag_s=12, cancel_s=3600)   # lag12 → dropped
    c_ok = pre["optimistic"][0] is True and post["optimistic"][0] is False
    ok = ok and c_ok
    print(f"  [{'ok' if c_ok else 'FAIL'}] no look-ahead: touch at t+5s fills at lag=0 but is dropped at lag=12s")

    # (D) CLOCK DOMAIN: window membership uses eff_ts (=exch_ts for price_change), not recv_at. Build a
    #     row whose eff_ts is INSIDE the window; a divergent recv_at must not change the decision (leg_fills
    #     only sees eff_ts, proving the caller resolved exch_ts→eff_ts, never recv_at, for price_change).
    tape_clock = [{"best_ask": 0.79, "eff_ts": 1100.0}]   # eff_ts t_rel=100s, inside [12, 900]
    d = leg_fills(tape_clock, P=0.80, t0=1000.0, lag_s=12, cancel_s=900)
    d_ok = d["optimistic"][0] is True
    # and the ADDENDUM contract: _build must resolve eff_ts = exch_ts when present (assert on a raw row)
    raw = {"best_ask": "0.79", "exch_ts": "1100.0", "recv_at": "9999.0", "id": "z", "event_type": "price_change", "last_size": ""}
    eff = float(raw["exch_ts"]) if raw["exch_ts"] not in ("", None) else float(raw["recv_at"])
    d_ok = d_ok and eff == 1100.0
    ok = ok and d_ok
    print(f"  [{'ok' if d_ok else 'FAIL'}] clock domain: eff_ts=exch_ts drives the window (recv_at ignored for price_change)")

    # (E) DWELL vs TOUCH vs THROUGH bracket ordering: through ⊆ dwell? no — through needs strict-below;
    #     construct: one touch at =P (opt yes, dwell no [single], pess no); then two touches spanning 40s
    #     at =P (dwell yes, pess no); then a strict-below (pess yes).
    only_touch = leg_fills([{"best_ask": 0.80, "eff_ts": 1050.0}], 0.80, 1000.0, 0, 3600)
    e1 = only_touch["optimistic"][0] and not only_touch["dwell"][0] and not only_touch["pessimistic"][0]
    two_touch = leg_fills([{"best_ask": 0.80, "eff_ts": 1050.0}, {"best_ask": 0.80, "eff_ts": 1095.0}], 0.80, 1000.0, 0, 3600)
    e2 = two_touch["optimistic"][0] and two_touch["dwell"][0] and not two_touch["pessimistic"][0]
    through = leg_fills([{"best_ask": 0.79, "eff_ts": 1050.0}], 0.80, 1000.0, 0, 3600)
    e3 = through["optimistic"][0] and through["pessimistic"][0]
    e_ok = e1 and e2 and e3
    ok = ok and e_ok
    print(f"  [{'ok' if e_ok else 'FAIL'}] bracket: touch@=P→opt only; 2×@=P/40s→+dwell; <P→+through (opt⊇dwell, opt⊇through)")

    # (F) cluster LB plumbing: reuses effective_n/regime_edge; 2 winners at P<1 give +roi, LB defined.
    f_theta, f_lb, f_G = _cluster_lb({"a": 0.10, "b": 0.12}, {"a": "e1", "b": "e2"})
    f_ok = f_theta is not None and f_lb is not None and f_G == 2
    ok = ok and f_ok
    print(f"  [{'ok' if f_ok else 'FAIL'}] cluster-robust LB plumbing: theta {f_theta:+.3f}, t(1) LB {f_lb:+.3f}, G={f_G}")

    print("selftest:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--all-strategies", action="store_true", help="robustness universe (context only)")
    a = ap.parse_args()
    if a.selftest:
        _selftest()
    else:
        run(a.all_strategies)
