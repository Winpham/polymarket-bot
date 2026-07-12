#!/usr/bin/env python3
"""
paper_tracker.py -- side-by-side PAPER-trading tracker: favorite (champion, reference) vs
favorite_liq vs favorite_v2. A thin READ-ONLY orchestrator over the existing honest instruments;
it computes NO new P&L math of its own -- it reads honest_paper_ledger (the authoritative,
idempotent, corrected-fee accrual ledger written by copy-trading-bot's housekeeping cycle) and
composes the existing scripts into one side-by-side surface:

  - audit_pnl_books.py   -- imports entry_price/pnl_resolved/staked/mtm_open/peak_concurrent for
                            the open-position MTM view and the cross-check self-test. NOT re-derived.
  - sport_edge_tracker.py -- imports fetch()/analyze() (REGIMES map) for the by-sport split.
  - standard_guard.py    -- imports measure() for the belief-blind reference/challenger verdict
                            per arm (the SAME gate the champion is judged against).
  - honest_pnl_by_strategy (common/src/storage/consensus.rs) -- its exact SQL (event-clustered
    honest_roi/clv_roi/hit-rate CTEs) is PORTED VERBATIM below (Python can't call the Rust async
    fn directly), parameterized with the SAME constants the Rust binary uses
    (EXEC_HAIRCUT=0.01, FEE_PCT=0.02 -- copy-trading-bot/src/config.rs defaults). If those defaults
    change, update HAIRCUT/FEE_PCT here too.

READ-ONLY DB via `docker exec polymarket-bot-postgres-1 psql` (the postgres port is not exposed on
the host; DATABASE_URL is tried first only if it happens to be reachable). Writes NO rows anywhere.
Paper-only. Deploys/arms/merges NOTHING.

Usage:
  ./paper_tracker.py --self-test         # pure offline unit tests, no DB (fast, CI-friendly)
  ./paper_tracker.py                     # live run: verifies the champion anchor, then writes
                                          #   reports/PAPER-TRACKER.json + reports/PAPER-TRACKER.md
  ./paper_tracker.py --strategies favorite,favorite_liq,favorite_v2,favorite_v3
  ./paper_tracker.py --window 14 --json-only
"""
import argparse
import csv
import io
import json
import os
import re
import socket
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REPORT_DIR = os.path.join(ROOT, "reports")
sys.path.insert(0, HERE)

from audit_pnl_books import (  # noqa: E402  -- extend, don't rebuild: reuse the existing P&L math
    entry_price as audit_entry_price,
    pnl_resolved as audit_pnl_resolved,
    staked as audit_staked,
    mtm_open as audit_mtm_open,
    peak_concurrent as audit_peak_concurrent,
    parse_ts as audit_parse_ts,
)
import sport_edge_tracker as sport_mod  # noqa: E402 -- REGIMES map + analyze() reused verbatim
import standard_guard as guard_mod  # noqa: E402 -- belief-blind reference reused verbatim

PG_CONTAINER = os.environ.get("PG_CONTAINER", "polymarket-bot-postgres-1")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgres://bot:bot@localhost:5432/polymarket")

DEFAULT_STRATEGIES = ["favorite", "favorite_liq", "favorite_v2"]
AUTO_INCLUDE_PREFIX = "favorite"   # auto-pick up favorite_v3 etc. without a code change
DEFAULT_WINDOW_DAYS = 7
POWER_FLOOR = 30                  # matches standard_guard.py's pre-registered event floor

# Mirrors copy-trading-bot/src/config.rs EXEC_HAIRCUT / FEE_PCT defaults -- the SAME constants
# append_paper_bet() and honest_pnl_by_strategy() use live. Keep in sync if those change.
EXEC_HAIRCUT = 0.01
FEE_PCT = 0.02
REALIZED_DECISION_LAG_SECS = 900.0  # matches REALIZED_DECISION_LAG_SECS default

CENSORING_NOTE = (
    "Winners resolve roughly 2x faster than losers (see audit_pnl_books.py's B3 hold-time "
    "asymmetry, reproduced live in this report's cross-check) -- so a FRESH day's still-open book "
    "is winner-enriched almost by construction. Never read a fresh day's open-MTM as a floor on "
    "eventual resolved P&L; it is a snapshot mid-flight, not a settled record."
)
NEW_ARM_NOTE = (
    "favorite_liq / favorite_v2 have ZERO honest_paper_ledger rows: they are built on the unmerged "
    "feat/garbage-policy branch and have not been deployed, so no signals for them exist yet. This "
    "tracker deliberately does NOT backfill-evaluate them on favorite's pre-snapshot history -- doing "
    "so is the exact coverage artifact that already inflated an in-sample '+9.66%' for this family. "
    "Their honest scope is forward-from-first-row-only, once Tue deploys feat/garbage-policy."
)


def zero_row_note(strategy):
    """Per-arm zero-ledger-row explanation. The two named new arms get the specific deploy-pending
    story; any OTHER auto-discovered favorite_* strategy (e.g. a stray one-off signal) gets a
    generic honest note instead of a copy-pasted, strategy-mismatched sentence."""
    if strategy in ("favorite_liq", "favorite_v2"):
        return NEW_ARM_NOTE
    return (
        "'%s' has ZERO honest_paper_ledger rows (0 resolved bets have ever been appended for it). "
        "No ROI is computed -- a fake/backfilled number would repeat the known coverage-artifact "
        "mistake. If this strategy is expected to be live, check should_ledger()/LEDGER_STRATEGIES "
        "and whether it has ever resolved a signal." % strategy
    )


# ============================================================================ db plumbing
def _db_reachable():
    try:
        host_port = DATABASE_URL.rsplit("@", 1)[-1].split("/")[0]
        host, _, port = host_port.partition(":")
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        s.connect((host, int(port or 5432)))
        s.close()
        return True
    except Exception:
        return False


def q(sql):
    """Read-only query via docker exec psql (the sanctioned path -- no host psql, port not
    exposed). Returns list[dict] via csv.DictReader. Tries DATABASE_URL first only if reachable
    (it never is in this environment, but the brief asks us to prefer it when possible)."""
    if _db_reachable():
        try:
            import psycopg2  # type: ignore
            with psycopg2.connect(DATABASE_URL) as conn, conn.cursor() as cur:
                cur.execute(sql)
                cols = [c.name for c in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception:
            pass  # fall through to docker exec
    cmd = ["docker", "exec", "-i", PG_CONTAINER, "psql", "-U", "bot", "-d", "polymarket",
           "--csv", "-q", "-f", "-"]
    r = subprocess.run(cmd, input=sql, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("psql failed:\n" + r.stderr)
    return list(csv.DictReader(io.StringIO(r.stdout)))


def fnum(s):
    if s is None:
        return None
    s = str(s).strip()
    return float(s) if s else None


def fint(s):
    if s is None:
        return None
    s = str(s).strip()
    return int(s) if s else None


def fbool(s):
    s = str(s or "").strip().lower()
    if s in ("t", "true"):
        return True
    if s in ("f", "false"):
        return False
    return None


def parse_ts(s):
    if s is None:
        return None
    if hasattr(s, "tzinfo"):   # psycopg2 already gives a datetime
        return s
    return audit_parse_ts(s)


def day_key(dt):
    return dt.astimezone(timezone.utc).date().isoformat() if dt else None


# ============================================================================ strategy discovery
def discover_strategies(explicit):
    if explicit:
        return list(explicit)
    strategies = list(DEFAULT_STRATEGIES)
    rows = q(
        "SELECT DISTINCT strategy FROM honest_paper_ledger "
        "UNION SELECT DISTINCT strategy FROM consensus_signals;"
    )
    for r in rows:
        s = r.get("strategy")
        if s and s.startswith(AUTO_INCLUDE_PREFIX) and s not in strategies:
            strategies.append(s)
    return strategies


# ============================================================================ canonical resolved P&L
LEDGER_JOIN_SQL = """
SELECT hpl.strategy, hpl.condition_id, hpl.outcome_index, hpl.resolved_at AS cash_at,
       hpl.stake, hpl.entry, hpl.outcome_won, hpl.pnl,
       cs.first_detected_at AS detect_at, cs.event_slug, cs.slug
FROM honest_paper_ledger hpl
LEFT JOIN consensus_signals cs
  ON cs.strategy = hpl.strategy AND cs.condition_id = hpl.condition_id
 AND cs.outcome_index = hpl.outcome_index
WHERE hpl.strategy IN ({strats});
"""


def fetch_ledger_rows(strategies):
    strat_in = ",".join("'%s'" % s.replace("'", "''") for s in strategies)
    rows = q(LEDGER_JOIN_SQL.format(strats=strat_in))
    out = []
    for r in rows:
        out.append({
            "strategy": r["strategy"],
            "condition_id": r["condition_id"],
            "outcome_index": fint(r["outcome_index"]),
            "cash_at": parse_ts(r["cash_at"]),
            "detect_at": parse_ts(r["detect_at"]),
            "stake": fnum(r["stake"]),
            "entry": fnum(r["entry"]),
            "outcome_won": fbool(r["outcome_won"]) if not isinstance(r["outcome_won"], bool) else r["outcome_won"],
            "pnl": fnum(r["pnl"]),
            "event_slug": r["event_slug"],
            "slug": r["slug"],
        })
    return out


def resolved_summary(rows, basis="cash", since=None):
    """Aggregate the ledger's OWN pnl/stake columns -- never recomputed -- grouped/filtered by
    the chosen date basis. 'cash' = resolved_at (the ledger's native clock, a true cash event:
    the moment the paper bet was appended). 'detection' = first_detected_at (joined from
    consensus_signals) -- when the signal that became this bet first fired. The two bases can
    disagree on which days are red; see day_table_basis_divergence."""
    key = "cash_at" if basis == "cash" else "detect_at"
    filt = [r for r in rows if since is None or (r[key] and r[key] >= since)]
    n = len(filt)
    turnover = sum(r["stake"] for r in filt)
    net = sum(r["pnl"] for r in filt)
    wins = sum(1 for r in filt if r["outcome_won"])
    days = {day_key(r[key]) for r in filt if r[key]}
    return {
        "n": n,
        "turnover_usd": round(turnover, 2),
        "net_pnl_usd": round(net, 2),
        "roi_on_turnover": (net / turnover) if turnover else None,
        "win_rate": (wins / n) if n else None,
        "n_days": len(days),
        "basis": basis,
    }


def day_table(rows, basis):
    key = "cash_at" if basis == "cash" else "detect_at"
    d = defaultdict(lambda: {"n": 0, "net": 0.0})
    for r in rows:
        if not r[key]:
            continue
        c = d[day_key(r[key])]
        c["n"] += 1
        c["net"] += r["pnl"]
    return {k: {"n": v["n"], "net": round(v["net"], 2)} for k, v in sorted(d.items())}


def basis_divergence(rows):
    cash = day_table(rows, "cash")
    detect = day_table(rows, "detection")
    neg_cash = {d for d, c in cash.items() if c["net"] < 0}
    neg_detect = {d for d, c in detect.items() if c["net"] < 0}
    flips = sorted(neg_cash ^ neg_detect)
    return {"cash": cash, "detection": detect, "days_flip_sign_between_bases": flips}


# ============================================================================ open positions (MTM)
OPEN_SQL = """
SELECT strategy, condition_id, outcome_index, event_slug, first_detected_at,
       initial_mean_price, mean_price, last_market_price
FROM consensus_signals
WHERE strategy IN ({strats}) AND resolved IS NOT TRUE;
"""


def fetch_open_rows(strategies):
    strat_in = ",".join("'%s'" % s.replace("'", "''") for s in strategies)
    rows = q(OPEN_SQL.format(strats=strat_in))
    out = []
    for r in rows:
        out.append({
            "strategy": r["strategy"],
            "condition_id": r["condition_id"],
            "first_detected_at": parse_ts(r["first_detected_at"]),
            "initial_mean_price": fnum(r["initial_mean_price"]),
            "mean_price": fnum(r["mean_price"]),
            "last_market_price": fnum(r["last_market_price"]),
        })
    return out


def open_positions_summary(rows, now_epoch):
    mtm = []
    for r in rows:
        e = audit_entry_price(r["initial_mean_price"], r["mean_price"])
        if e is None:
            continue
        m = audit_mtm_open(e, r["last_market_price"])
        age_h = (now_epoch - r["first_detected_at"].timestamp()) / 3600.0 if r["first_detected_at"] else None
        mtm.append((m, age_h))
    n = len(rows)
    with_mark = [m for m, _ in mtm if m is not None]
    fresh_24h = sum(1 for m, age in mtm if m is not None and age is not None and age < 24)
    return {
        "n_open": n,
        "n_with_mark": len(with_mark),
        "mtm_total_open_pnl": round(sum(with_mark), 2) if with_mark else None,
        "mtm_open_losers": sum(1 for m in with_mark if m < 0),
        "n_fresh_24h": fresh_24h,
        "censoring_note": CENSORING_NOTE,
    }


# ============================================================================ realizable / CLV view
# Ported verbatim (structure + formulae) from honest_pnl_by_strategy in
# common/src/storage/consensus.rs -- Python can't call the async Rust fn directly so its exact
# CTEs are reproduced here with the SAME bound constants the live binary uses.
HONEST_PNL_SQL = """
WITH base AS (
    SELECT strategy, COALESCE(event_slug, condition_id) AS ev,
           (outcome_won::int)::double precision AS w,
           COALESCE(entry_ask, initial_market_price + %(haircut)s) AS entry,
           initial_market_price AS p0
    FROM consensus_signals
    WHERE resolved AND initial_market_price IS NOT NULL AND strategy IN (%(strats)s)
),
sig AS (
    SELECT strategy, ev, w, p0, entry,
           (w - p0) AS clv_share,
           (w - p0) / NULLIF(p0, 0) AS clv_roi,
           (w - entry) / NULLIF(entry, 0) - %(fee)s AS honest_roi
    FROM base
),
evt AS (
    SELECT strategy, ev, AVG(w) AS ev_hit, AVG(clv_roi) AS ev_clvroi, AVG(honest_roi) AS ev_hroi
    FROM sig GROUP BY strategy, ev
)
SELECT strategy, COUNT(*) AS distinct_events, AVG(ev_hit) AS hit_rate,
       AVG(ev_clvroi) AS clv_roi, AVG(ev_hroi) AS honest_roi,
       STDDEV_SAMP(ev_hroi) AS honest_roi_sd
FROM evt GROUP BY strategy;
"""


def realizable_clv_view(strategies):
    strat_in = ",".join("'%s'" % s.replace("'", "''") for s in strategies)
    sql = HONEST_PNL_SQL % {"haircut": EXEC_HAIRCUT, "fee": FEE_PCT, "strats": strat_in}
    rows = q(sql)
    out = {}
    for r in rows:
        out[r["strategy"]] = {
            "distinct_events": fint(r["distinct_events"]),
            "hit_rate": fnum(r["hit_rate"]),
            "clv_roi": fnum(r["clv_roi"]),
            "honest_roi": fnum(r["honest_roi"]),
            "honest_roi_sd": fnum(r["honest_roi_sd"]),
        }
    return out


# ============================================================================ capacity / rarity flag
CAP_SQL = """
SELECT to_char(first_detected_at AT TIME ZONE 'UTC', 'YYYY-MM-DD') AS day, count(*) AS n,
       count(*) FILTER (WHERE initial_total_usd IS NOT NULL) AS with_snap,
       count(*) FILTER (WHERE initial_total_usd >= 1000) AS clears_liq,
       count(*) FILTER (WHERE initial_total_usd >= 1000 AND initial_best_backer_rank < 5) AS clears_v2
FROM consensus_signals WHERE strategy = 'favorite'
GROUP BY 1 ORDER BY 1;
"""


def capacity_flag():
    """Tue's open question: 'is favorite_v2 even deployable or a bench-sitter?' Answered on REAL
    forward data -- how often the favorite_liq/favorite_v2 gating conditions (>=$1k total,
    top-5-backer) are cleared by the CHAMPION's OWN currently-firing signals, restricted to the
    trailing run of days where snapshot capture is ~complete (the brief's forward-clean window).
    This is a rarity DIAGNOSTIC, never a P&L estimate for the new arms (see COVERAGE_ARTIFACT_NOTE)."""
    rows = q(CAP_SQL)
    parsed = [{"day": r["day"], "n": int(r["n"]), "with_snap": int(r["with_snap"]),
               "clears_liq": int(r["clears_liq"]), "clears_v2": int(r["clears_v2"])} for r in rows]
    clean = []
    for r in reversed(parsed):
        if r["n"] > 0 and r["with_snap"] / r["n"] >= 0.95:
            clean.append(r)
        else:
            break
    clean.reverse()
    n = sum(r["with_snap"] for r in clean)
    liq = sum(r["clears_liq"] for r in clean)
    v2 = sum(r["clears_v2"] for r in clean)
    return {
        "diagnostic": ("rarity of the favorite_liq/favorite_v2 gates, measured on the CHAMPION's "
                       "own forward-snapshot-covered signal pool -- NOT a P&L estimate for the new arms"),
        "clean_snapshot_window_days": [r["day"] for r in clean],
        "snapshotted_signals_n": n,
        "clears_favorite_liq_pct": (liq / n) if n else None,
        "clears_favorite_v2_pct": (v2 / n) if n else None,
        "clears_favorite_liq_n": liq,
        "clears_favorite_v2_n": v2,
        "verdict": (
            "not a bench-sitter -- roughly {:.0%} of the champion's forward-snapshotted signals would "
            "also clear favorite_v2's top-5-backer+$1k gate".format(v2 / n) if n and v2 / n >= 0.10 else
            "borderline/rare -- fewer than 10% of the champion's forward-snapshotted signals would "
            "clear favorite_v2's gate; watch throughput once deployed"
        ) if n else "no snapshot coverage yet -- cannot assess",
    }


# ============================================================================ throughput / turnover
def turnover_context(rows):
    intervals = []
    for r in rows:
        if r["detect_at"] and r["cash_at"]:
            s = r["detect_at"].timestamp()
            e = r["cash_at"].timestamp()
            if e < s:
                e = s
            intervals.append((s, e, r["stake"]))
    if not intervals:
        return {"peak_concurrent_capital": None, "peak_concurrent_positions": None,
                "turnover_per_day_usd": None, "turnover_multiple": None}
    peak_cap, peak_n = audit_peak_concurrent(intervals)
    total_stake = sum(r["stake"] for r in rows)
    days = {day_key(r["cash_at"]) for r in rows if r["cash_at"]}
    per_day = total_stake / len(days) if days else None
    mult = (per_day / peak_cap) if peak_cap else None
    return {
        "peak_concurrent_capital": round(peak_cap, 2),
        "peak_concurrent_positions": peak_n,
        "turnover_per_day_usd": round(per_day, 2) if per_day is not None else None,
        "turnover_multiple": round(mult, 3) if mult is not None else None,
    }


# ============================================================================ belief-blind reference
def belief_blind_reference(strategies):
    """Reuse standard_guard.measure() verbatim -- the SAME champion-challenger gate everything
    else in this repo is judged against, not a bespoke vanity comparison."""
    out = {}
    champion_key = guard_mod.CHAMPION_KEY_ARM
    champ = guard_mod.measure(None)
    if champion_key in strategies:
        out[champion_key] = {
            "role": "champion (reference)",
            "key_arm_metrics": champ["champion"]["key_arm_metrics"],
            "regression_status": champ["regression"],
            "resolved_ledger_family": champ["champion"]["resolved_ledger"],
        }
    for s in strategies:
        if s == champion_key:
            continue
        chal = guard_mod.measure(s)
        out[s] = {"role": "challenger", "verdict": chal["challenger"]}
    return out


# ============================================================================ regime split
def regime_split(strategies):
    rows = sport_mod.fetch()
    out = {}
    for s in strategies:
        out[s] = sport_mod.analyze(rows, s)
    return out


# ============================================================================ champion anchor cross-check
def verify_champion_anchor():
    """The brief's non-negotiable self-test: reproduce the champion's corrected-fee ROI-on-
    turnover. We cross-check TWO independent formulations over the EXACT SAME resolved-bet
    population (the 'favorite' rows already in honest_paper_ledger):
      1. ledger-native: the ledger's own recorded pnl/stake columns (entry=entry_ask/mkt+1c haircut,
         fee=2%), summed -- this IS the number board.rs/honest_digest would show.
      2. audit_pnl_books.py's independently-derived formula (entry=mean+0.5c haircut, fee=2% of
         entry*shares -- algebraically the same corrected-fee ROI shape, different haircut/price
         basis), recomputed over the SAME population via the imported functions (not reimplemented).
    Both must be POSITIVE and within a generous tolerance of each other -- if they diverge in sign
    or by more than the tolerance, something is actually broken and we STOP rather than ship a
    tracker with numbers that don't tie out.
    Returns (ok: bool, detail: dict).
    """
    rows = fetch_ledger_rows(["favorite"])
    if not rows:
        return False, {"error": "no favorite rows in honest_paper_ledger -- cannot verify anchor"}
    ledger_pnl = sum(r["pnl"] for r in rows)
    ledger_stake = sum(r["stake"] for r in rows)
    ledger_roi = ledger_pnl / ledger_stake if ledger_stake else None

    sql = ("SELECT hpl.condition_id, hpl.outcome_index, cs.initial_mean_price, cs.mean_price "
           "FROM honest_paper_ledger hpl JOIN consensus_signals cs "
           "ON cs.strategy = hpl.strategy AND cs.condition_id = hpl.condition_id "
           "AND cs.outcome_index = hpl.outcome_index WHERE hpl.strategy = 'favorite';")
    joined = q(sql)
    outcome_by_key = {(r["condition_id"], r["outcome_index"]): r["outcome_won"] for r in rows}
    audit_pnl = 0.0
    audit_stake = 0.0
    for r in joined:
        key = (r["condition_id"], fint(r["outcome_index"]))
        won = outcome_by_key.get(key)
        if won is None:
            continue
        e = audit_entry_price(fnum(r["initial_mean_price"]), fnum(r["mean_price"]))
        if e is None:
            continue
        audit_pnl += audit_pnl_resolved(e, won)
        audit_stake += audit_staked(e)
    audit_roi = audit_pnl / audit_stake if audit_stake else None

    detail = {
        "population_n": len(rows),
        "ledger_native_roi_on_turnover": ledger_roi,
        "audit_pnl_books_formula_roi_on_turnover_same_population": audit_roi,
        "tolerance_abs": 0.05,
        "note": ("Both computed over the IDENTICAL 'favorite' resolved-bet population from "
                 "honest_paper_ledger. They use different haircut/entry conventions (ledger: "
                 "entry_ask or mkt+1c, audit: mean+0.5c) so an exact match isn't expected -- both "
                 "positive and within a few points of each other is the honest bar. A separate, "
                 "much LARGER population figure from running audit_pnl_books.py standalone "
                 "(reports/audit_pnl_books.json) is NOT expected to match either: it includes "
                 "pre-Phase-3 history (before the ledger existed) that never got appended to "
                 "honest_paper_ledger -- a real, understood, documented population gap, not a bug."),
    }
    ok = (ledger_roi is not None and audit_roi is not None
          and ledger_roi > 0 and audit_roi > 0
          and abs(ledger_roi - audit_roi) < detail["tolerance_abs"])
    return ok, detail


# ============================================================================ per-arm report
def build_arm_report(strategy, ledger_rows_all, open_rows_all, regime_all, belief_all,
                      clv_all, window_days, now):
    rows = [r for r in ledger_rows_all if r["strategy"] == strategy]
    open_rows = [r for r in open_rows_all if r["strategy"] == strategy]

    if not rows:
        return {
            "strategy": strategy,
            "status": "awaiting-forward-data (deploy pending)",
            "n": 0,
            "note": zero_row_note(strategy),
            "open_positions_mtm": {"n_open": len(open_rows), "n_with_mark": 0,
                                    "note": "signals may exist pre-deploy; strategy has 0 resolved/ledgered bets"},
            "throughput": None,
            "power_flag": "not yet readable (N=0)",
            "regime_split": regime_all.get(strategy, {}),
            "realizable_clv": clv_all.get(strategy),
            "belief_blind": belief_all.get(strategy),
        }

    since_window = now - timedelta(days=window_days)
    resolved_all = resolved_summary(rows, "cash", None)
    resolved_detect_all = resolved_summary(rows, "detection", None)
    resolved_window = resolved_summary(rows, "cash", since_window)
    divergence = basis_divergence(rows)
    open_summ = open_positions_summary(open_rows, now.timestamp())
    turnover = turnover_context(rows)
    n = resolved_all["n"]
    power = ("not yet readable (N=%d < %d power floor)" % (n, POWER_FLOOR)
              if n < POWER_FLOOR else "readable (N=%d >= %d power floor)" % (n, POWER_FLOOR))

    return {
        "strategy": strategy,
        "status": "live" if rows else "awaiting-forward-data (deploy pending)",
        "resolved_pnl_canonical": {
            "cash_basis": resolved_all,
            "detection_basis": resolved_detect_all,
            "basis_note": ("both read the SAME honest_paper_ledger.pnl column (corrected fee, "
                            "event-dedup by the ledger's own UNIQUE constraint) -- only the date "
                            "KEY differs. See day_table_basis_divergence for which days flip sign "
                            "between the two bases."),
        },
        "rolling_window": {
            "last_%dd" % window_days: resolved_window,
            "since_first_row": resolved_all,
        },
        "day_table_basis_divergence": divergence,
        "throughput": {
            "bets_per_day": (n / resolved_all["n_days"]) if resolved_all["n_days"] else None,
            **turnover,
        },
        "open_positions_mtm": open_summ,
        "power_flag": power,
        "regime_split": regime_all.get(strategy, {}),
        "realizable_clv": clv_all.get(strategy),
        "belief_blind": belief_all.get(strategy),
    }


# ============================================================================ markdown rendering
def _pf(x, spec="+.2%"):
    return "n/a" if x is None else format(x, spec)


def render_markdown(report):
    lines = []
    lines.append("# PAPER-TRACKER — champion vs favorite_liq vs favorite_v2 (read-only)")
    lines.append("")
    lines.append("_Generated: %s (UTC). Paper-only. Read-only DB. No rows written; nothing armed, deployed, or merged._" % report["meta"]["generated_at"])
    lines.append("")
    anchor = report["meta"]["champion_anchor_verification"]
    status_word = "TIED OUT" if anchor["ok"] else "DID NOT TIE OUT -- SEE DETAIL"
    lines.append("## Champion anchor self-test: %s" % status_word)
    lines.append("")
    lines.append("- ledger-native ROI-on-turnover (favorite, N=%d): **%s**" % (
        anchor["detail"]["population_n"], _pf(anchor["detail"]["ledger_native_roi_on_turnover"])))
    lines.append("- audit_pnl_books.py formula, SAME population: **%s**" % (
        _pf(anchor["detail"]["audit_pnl_books_formula_roi_on_turnover_same_population"])))
    lines.append("")
    lines.append("> %s" % anchor["detail"]["note"])
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Honesty guards baked into this surface")
    lines.append("")
    lines.append("- **Accounting basis is always labeled** (cash-day = `resolved_at`, i.e. when the paper "
                  "bet was appended to the ledger, vs detection-day = `first_detected_at`, i.e. when the "
                  "signal first fired). They can disagree on which days are red -- see "
                  "`day_table_basis_divergence.days_flip_sign_between_bases` per arm.")
    lines.append("- **Zero-row arms show `awaiting-forward-data (deploy pending)`, N=0, no ROI computed.** "
                  "%s" % NEW_ARM_NOTE)
    lines.append("- **Open positions are MTM-labeled and censoring-flagged.** %s" % CENSORING_NOTE)
    lines.append("- **Every arm is judged against the same belief-blind gate the champion is** "
                  "(`standard_guard.py` measure/challenger), not a vanity P&L.")
    lines.append("- **Power floor: N < %d resolved events reads `not yet readable`.**" % POWER_FLOOR)
    lines.append("")
    lines.append("---")
    lines.append("")

    for arm in report["arms"]:
        s = arm["strategy"]
        lines.append("## `%s`" % s)
        lines.append("")
        if arm["status"].startswith("awaiting"):
            lines.append("**Status: %s**" % arm["status"])
            lines.append("")
            lines.append("> %s" % arm["note"])
            lines.append("")
            bb = arm.get("belief_blind")
            if bb:
                v = bb.get("verdict", {})
                lines.append("Belief-blind challenger check: **%s** -- %s" % (
                    v.get("verdict", "n/a"), "; ".join(v.get("reasons", []))))
            lines.append("")
            continue

        rp = arm["resolved_pnl_canonical"]
        lines.append("**Status: live**  ·  power flag: %s" % arm["power_flag"])
        lines.append("")
        lines.append("| basis | N | turnover | net P&L | ROI-on-turnover | win% | days |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        for basis_name, row in (("cash (resolved_at)", rp["cash_basis"]),
                                 ("detection (first_detected_at)", rp["detection_basis"])):
            lines.append("| %s | %d | $%.2f | $%.2f | %s | %s | %d |" % (
                basis_name, row["n"], row["turnover_usd"], row["net_pnl_usd"],
                _pf(row["roi_on_turnover"]), _pf(row["win_rate"], "+.1%"), row["n_days"]))
        lines.append("")
        flips = rp.get("basis_note")
        flip_days = arm["day_table_basis_divergence"]["days_flip_sign_between_bases"]
        lines.append("basis-flip days (red in one basis, not the other): %s" % (
            ", ".join(flip_days) if flip_days else "none"))
        lines.append("")

        rw = arm["rolling_window"]
        win_key = [k for k in rw if k.startswith("last_")][0]
        lines.append("**Rolling window** (`%s` vs since-first-row):" % win_key)
        lines.append("")
        w, a = rw[win_key], rw["since_first_row"]
        lines.append("| window | N | ROI-on-turnover | win% |")
        lines.append("|---|---:|---:|---:|")
        lines.append("| %s | %d | %s | %s |" % (win_key, w["n"], _pf(w["roi_on_turnover"]), _pf(w["win_rate"], "+.1%")))
        lines.append("| since_first_row | %d | %s | %s |" % (a["n"], _pf(a["roi_on_turnover"]), _pf(a["win_rate"], "+.1%")))
        lines.append("")

        thr = arm["throughput"]
        lines.append("**Throughput:** %.2f bets/day · turnover $%s/day · peak concurrent capital $%s "
                      "(%s positions) · turnover-multiple %s" % (
                          thr["bets_per_day"] or 0.0,
                          thr["turnover_per_day_usd"], thr["peak_concurrent_capital"],
                          thr["peak_concurrent_positions"], thr["turnover_multiple"]))
        lines.append("")

        clv = arm.get("realizable_clv")
        if clv:
            lines.append("**Realizable/CLV** (event-clustered, honest_pnl_by_strategy convention): "
                          "%d distinct events · hit-rate %s · CLV-ROI %s · honest-ROI %s (sd %s)" % (
                              clv["distinct_events"], _pf(clv["hit_rate"], "+.1%"),
                              _pf(clv["clv_roi"]), _pf(clv["honest_roi"]), _pf(clv["honest_roi_sd"], "+.3f")))
        else:
            lines.append("**Realizable/CLV:** no rows yet.")
        lines.append("")

        op = arm["open_positions_mtm"]
        lines.append("**Open positions (MTM):** %d open, %d with a mark, total open MTM $%s, "
                      "%s losers, %d fresh (<24h)" % (
                          op["n_open"], op["n_with_mark"], op.get("mtm_total_open_pnl"),
                          op.get("mtm_open_losers"), op.get("n_fresh_24h", 0)))
        lines.append("")
        lines.append("> %s" % op["censoring_note"])
        lines.append("")

        rs = arm.get("regime_split") or {}
        if rs:
            lines.append("**By-regime split** (softness = blind-favorite edge, skill = surplus over blind):")
            lines.append("")
            lines.append("| sport | events | win% | softness | skill | total |")
            lines.append("|---|---:|---:|---:|---:|---:|")
            for sp, d in sorted(rs.items(), key=lambda kv: -kv[1]["events"]):
                soft = _pf(d["softness"]) if d["softness"] == d["softness"] else "n/a"
                lines.append("| %s | %d | %.0f%% | %s | %s | %s |" % (
                    sp, d["events"], d["win_pct"], soft, _pf(d["skill"]), _pf(d["total"])))
            lines.append("")
        else:
            lines.append("**By-regime split:** no resolved rows yet.")
            lines.append("")

        bb = arm.get("belief_blind")
        if bb:
            if bb.get("role") == "champion (reference)":
                key = bb["key_arm_metrics"] or {}
                lines.append("**Belief-blind reference (champion):** %d ev · surplus %s · LB %s · %s "
                              "non-soccer regimes+ · %s" % (
                                  key.get("events", 0), _pf(key.get("observed")),
                                  _pf(key.get("belief_blind_lb")), key.get("non_soccer_regimes_positive"),
                                  key.get("verdict")))
                lines.append("Regression status: **%s** -- %s" % (
                    bb["regression_status"]["status"], bb["regression_status"]["reason"]))
            else:
                v = bb.get("verdict", {})
                lines.append("**Belief-blind challenger check:** %s -- %s" % (
                    v.get("verdict", "n/a"), "; ".join(v.get("reasons", []))))
        lines.append("")
        lines.append("---")
        lines.append("")

    cap = report.get("capacity_flag")
    if cap:
        lines.append("## Capacity / rarity flag (favorite_v2 deployability)")
        lines.append("")
        lines.append("> %s" % cap["diagnostic"])
        lines.append("")
        lines.append("Clean snapshot window: %s (N=%d snapshotted signals)" % (
            ", ".join(cap["clean_snapshot_window_days"]) or "none", cap["snapshotted_signals_n"]))
        lines.append("")
        lines.append("- clears favorite_liq gate ($1k total): %s (%d/%d)" % (
            _pf(cap["clears_favorite_liq_pct"], "+.0%"), cap["clears_favorite_liq_n"], cap["snapshotted_signals_n"]))
        lines.append("- clears favorite_v2 gate (+top-5-backer): %s (%d/%d)" % (
            _pf(cap["clears_favorite_v2_pct"], "+.0%"), cap["clears_favorite_v2_n"], cap["snapshotted_signals_n"]))
        lines.append("")
        lines.append("**Verdict:** %s" % cap["verdict"])
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("_Next step for the new arms: Tue deploys/merges `feat/garbage-policy`. The moment "
                  "favorite_liq/favorite_v2 start ledgering, this tracker lights them up automatically "
                  "on the next refresh -- no code change needed._")
    return "\n".join(lines) + "\n"


# ============================================================================ offline self-test
def self_test():
    ok = True

    def check(name, cond):
        nonlocal ok
        ok = ok and cond
        print("  [%s] %s" % ("ok" if cond else "FAIL", name))

    # day_key / resolved_summary / day_table on synthetic ledger rows
    t = lambda s: audit_parse_ts(s)
    rows = [
        {"strategy": "x", "condition_id": "c1", "outcome_index": 0,
         "cash_at": t("2026-01-01 10:00:00+00"), "detect_at": t("2025-12-31 23:00:00+00"),
         "stake": 100.0, "entry": 0.8, "outcome_won": True, "pnl": 18.0,
         "event_slug": "g1", "slug": "g1"},
        {"strategy": "x", "condition_id": "c2", "outcome_index": 0,
         "cash_at": t("2026-01-02 03:00:00+00"), "detect_at": t("2026-01-01 22:00:00+00"),
         "stake": 100.0, "entry": 0.7, "outcome_won": False, "pnl": -72.0,
         "event_slug": "g2", "slug": "g2"},
    ]
    s_cash = resolved_summary(rows, "cash")
    check("resolved_summary n=2", s_cash["n"] == 2)
    check("resolved_summary turnover=200", abs(s_cash["turnover_usd"] - 200.0) < 1e-9)
    check("resolved_summary net=-54", abs(s_cash["net_pnl_usd"] - (-54.0)) < 1e-9)
    check("resolved_summary roi", abs(s_cash["roi_on_turnover"] - (-0.27)) < 1e-9)
    check("resolved_summary win_rate 0.5", abs(s_cash["win_rate"] - 0.5) < 1e-9)
    check("resolved_summary n_days (cash) = 2", s_cash["n_days"] == 2)

    div = basis_divergence(rows)
    # cash basis: day1(2026-01-01)=+18 (win only, its cash lands 01-01), day2(2026-01-02)=-72
    check("day_table cash 2026-01-01 positive", div["cash"]["2026-01-01"]["net"] > 0)
    check("day_table cash 2026-01-02 negative", div["cash"]["2026-01-02"]["net"] < 0)
    # detection basis: both detected on/before 2025-12-31/2026-01-01 -> day keys differ from cash
    check("day_table detection has 2025-12-31", "2025-12-31" in div["detection"])
    check("basis_divergence flips computed (no crash, list type)", isinstance(div["days_flip_sign_between_bases"], list))

    # resolved_summary with a `since` filter excludes the earlier row
    since = t("2026-01-02 00:00:00+00")
    s_since = resolved_summary(rows, "cash", since)
    check("resolved_summary since-filter drops row 1", s_since["n"] == 1 and s_since["net_pnl_usd"] == -72.0)

    # open_positions_summary + censoring
    open_rows = [
        {"strategy": "x", "condition_id": "o1", "first_detected_at": t("2026-01-02 00:00:00+00"),
         "initial_mean_price": 0.80, "mean_price": None, "last_market_price": 0.90},
        {"strategy": "x", "condition_id": "o2", "first_detected_at": t("2026-01-01 00:00:00+00"),
         "initial_mean_price": 0.60, "mean_price": None, "last_market_price": 0.50},
    ]
    now_epoch = t("2026-01-02 12:00:00+00").timestamp()
    op = open_positions_summary(open_rows, now_epoch)
    check("open_positions n_open=2", op["n_open"] == 2)
    check("open_positions n_with_mark=2", op["n_with_mark"] == 2)
    check("open_positions has censoring note", "winner-enriched" in op["censoring_note"])
    check("open_positions n_fresh_24h counts o1 (12h old)", op["n_fresh_24h"] == 1)

    # turnover_context peak-concurrent reuse (mirrors audit_pnl_books' own self-test fixture)
    tc_rows = [
        {"detect_at": t("2026-01-01 00:00:00+00"), "cash_at": t("2026-01-01 10:00:00+00"), "stake": 50.0},
        {"detect_at": t("2026-01-01 05:00:00+00"), "cash_at": t("2026-01-01 15:00:00+00"), "stake": 30.0},
    ]
    tc = turnover_context(tc_rows)
    check("turnover_context peak_concurrent_capital=80", abs(tc["peak_concurrent_capital"] - 80.0) < 1e-9)
    check("turnover_context peak_concurrent_positions=2", tc["peak_concurrent_positions"] == 2)

    # discover_strategies without DB call (explicit path only, pure)
    check("discover_strategies explicit passthrough", discover_strategies(["a", "b"]) == ["a", "b"])

    print("SELF-TEST", "PASSED" if ok else "FAILED")
    return ok


# ============================================================================ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true", help="pure offline unit tests, no DB")
    ap.add_argument("--strategies", default=None,
                     help="comma-separated strategy list (default: favorite,favorite_liq,favorite_v2 "
                          "+ auto-discovered favorite_* strategies)")
    ap.add_argument("--window", type=int, default=DEFAULT_WINDOW_DAYS, help="rolling window in days")
    ap.add_argument("--json-only", action="store_true", help="skip writing the .md report")
    ap.add_argument("--md-only", action="store_true", help="skip writing the .json report")
    args = ap.parse_args()

    if args.self_test:
        sys.exit(0 if self_test() else 1)

    strategies = discover_strategies(args.strategies.split(",") if args.strategies else None)

    print("=" * 88)
    print("PAPER-TRACKER — verifying the champion anchor before rendering anything")
    print("=" * 88)
    ok, detail = verify_champion_anchor()
    print("ledger-native ROI-on-turnover (favorite): %s" % _pf(detail.get("ledger_native_roi_on_turnover")))
    print("audit_pnl_books formula, same population: %s" % _pf(detail.get("audit_pnl_books_formula_roi_on_turnover_same_population")))
    if not ok:
        print("\n*** STOP: champion anchor did NOT tie out. Refusing to render a tracker whose numbers")
        print("*** don't cross-check. Detail:")
        print(json.dumps(detail, indent=2, default=str))
        sys.exit(1)
    print("anchor reproduced (both positive, within tolerance of each other). Proceeding.\n")

    now = datetime.now(timezone.utc)
    ledger_rows = fetch_ledger_rows(strategies)
    open_rows = fetch_open_rows(strategies)
    regime_all = regime_split(strategies)
    clv_all = realizable_clv_view(strategies)
    print("computing belief-blind reference per arm (calls selection_null.py -- may take ~15-45s)...")
    belief_all = belief_blind_reference(strategies)

    arms = [build_arm_report(s, ledger_rows, open_rows, regime_all, belief_all, clv_all, args.window, now)
            for s in strategies]

    report = {
        "meta": {
            "generated_at": now.isoformat(),
            "strategies": strategies,
            "window_days": args.window,
            "power_floor_events": POWER_FLOOR,
            "champion_anchor_verification": {"ok": ok, "detail": detail},
            "posture": "READ-ONLY. Paper-only. Writes no rows. Deploys/arms/merges NOTHING.",
        },
        "arms": arms,
        "capacity_flag": capacity_flag() if "favorite_v2" in strategies or "favorite_liq" in strategies else None,
    }

    os.makedirs(REPORT_DIR, exist_ok=True)
    if not args.md_only:
        with open(os.path.join(REPORT_DIR, "PAPER-TRACKER.json"), "w") as f:
            json.dump(report, f, indent=2, default=str)
        print("wrote %s" % os.path.join(REPORT_DIR, "PAPER-TRACKER.json"))
    if not args.json_only:
        md = render_markdown(report)
        with open(os.path.join(REPORT_DIR, "PAPER-TRACKER.md"), "w") as f:
            f.write(md)
        print("wrote %s" % os.path.join(REPORT_DIR, "PAPER-TRACKER.md"))


if __name__ == "__main__":
    main()
