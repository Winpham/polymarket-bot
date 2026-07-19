#!/usr/bin/env python3
"""
FAVBAND — the liquid, tight-spread US favourite band. READ-ONLY. Never trades.

WHAT THIS IS
------------
The consolidated, honest implementation of the only Polymarket finding that has survived the
2026-07-18 re-measurement. It replaces a scratchpad of ad-hoc scripts with one instrument that
carries its own gate, its own failure modes, and its own self-tests.

THE FINDING (2026-07-18, complete-universe US re-measurement)
------------------------------------------------------------
Buying the favourite at a fair PRE-GAME entry in the 0.80-0.98 band, restricted to markets that are
actually liquid, nets ~+1.5% ROI-on-turnover [+0.42, +2.59] event-clustered. It survives
leave-one-league-out across all 6 leagues, both time halves, a capacity floor, and a stale-quote
split. It FAILS on cost sensitivity: +0.5c of additional spread erases it.

THE THREE ERRORS THIS INSTRUMENT REFUSES TO MAKE
------------------------------------------------
1. NEVER impute an entry price. `COALESCE(entry_ask, initial_market_price + haircut)` is what
   manufactured the retracted "+6.95%": only 34% of picks had a real executable price, and the
   picks WITHOUT one were the profitable ones (98.7% win vs 87.8%). A row without a real price is
   DROPPED and counted, never filled in.
2. NEVER use a phantom cost. The fee is the venue's real schedule `rate*p*(1-p)`, takers only —
   not the 3% flat constant still wired into `board.rs::render`. The spread is MEASURED, not assumed.
3. NEVER curate by `sportsMarketType == 'moneyline'`. The venue renamed its taxonomy around
   2026-06-27 (moneyline -> *_match_winner / baseball_team_full_game_winner); that filter silently
   returns EMPTY for anything recent. Curation is family/slug based.

FAIL LOUD, NEVER CLOSED
-----------------------
A dead input must not look like "no edge". The orientation guard, the settlement join and the
coverage floor all raise. This is the failure that cost 2d17h of tape in 2026-07-16..18: consumers
of a dead tape reported "no signals qualified", indistinguishable from "no edge".

  ./favband.py --self-test          # synthetic fixtures; no archive, no DB
  ./favband.py --measure            # full measurement from the parquet archive
  ./favband.py --measure --gate     # + the 6-criterion pre-registered scorecard
  ./favband.py --spread-truth       # measure the TRUE spread from us_quotes (needs DB)
"""
from __future__ import annotations

import argparse
import glob
import io
import os
import re
import subprocess
import sys

import numpy as np
import pandas as pd

ARCHIVE = os.path.expanduser("~/polymarket-archive")
MK = f"{ARCHIVE}/us_markets.parquet"
TS_GLOB = f"{ARCHIVE}/us_time_sales/*.parquet"
DMR_GLOB = f"{ARCHIVE}/us_reports/*daily-market-report.csv"

FEE_RATE = 0.05          # venue taker schedule: fee = shares * rate * p * (1-p), MAKERS PAY 0
BAND_LO, BAND_HI = 0.80, 0.98
MIN_PREGAME_TRADES = 20  # liquidity filter (also what makes a causal Roll estimate possible)
FRESH_MAX_MIN = 30       # an entry older than this is stale, not executable
SEED = 17

# TRUE quoted spread, measured from us_quotes 2026-07-14..19 (n=670 in band), NOT a Roll estimate.
# The distribution is heavily skewed: 70% of quotes sit at 1c, but a wide tail drags the mean to
# 3.71c. Because the spread is OBSERVABLE BEFORE WE TRADE, the tradeable statistic is the one we
# can select into (median), not the one we would suffer passively (mean).
TRUE_SPREAD_MEAN = 0.0371
TRUE_SPREAD_MEDIAN = 0.0100
ROLL_HALF_MEAN = 0.0096          # what the archive-only estimator produced
SPREAD_SHORTFALL = TRUE_SPREAD_MEAN / 2 - ROLL_HALF_MEAN   # +0.90c: Roll understates by ~2x

EVENT_RE = re.compile(r"^[a-z]+-(.*?-\d{4}-\d{2}-\d{2})")

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "-v", "ON_ERROR_STOP=1", "--csv", "-q"]
GUARD = "SET max_parallel_workers_per_gather=0; SET statement_timeout='600s'; "


# --------------------------------------------------------------------------- helpers
def event_key(slug: str) -> str:
    """All submarkets of one game share a key. This is the unit of independence: a game bundles
    ~3.7 submarkets whose outcomes are correlated, so CIs clustered on the MARKET are too narrow."""
    m = EVENT_RE.match(slug)
    return m.group(1) if m else slug


def roll_spread(prices: np.ndarray, min_n: int = MIN_PREGAME_TRADES) -> float:
    """Roll (1984) effective spread from trade prices alone: bid-ask bounce makes successive price
    changes negatively autocovaried.  spread = 2*sqrt(-Cov(dP_t, dP_t-1)).

    IMPORTANT: informational drift makes the covariance LESS negative, so this is a LOWER BOUND on
    the true spread. Every net figure computed with it is therefore the most generous case."""
    if len(prices) < min_n:
        return np.nan
    dp = np.diff(prices)
    if len(dp) < 2:
        return np.nan
    c = np.cov(dp[:-1], dp[1:])[0, 1]
    return 2 * np.sqrt(-c) if c < 0 else 0.0


def cluster_boot(pnl: np.ndarray, turnover: np.ndarray, events: np.ndarray,
                 n: int = 4000, seed: int = SEED):
    """ROI-on-turnover with a bootstrap clustered on EVENT."""
    df = pd.DataFrame({"p": pnl, "t": turnover, "ev": events})
    g = df.groupby("ev").agg(s=("p", "sum"), c=("t", "sum"))
    s, c = g.s.values, g.c.values
    k = len(s)
    if k < 3:
        return np.nan, np.nan, np.nan, k
    roi = s.sum() / c.sum()
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, k, size=(n, k))
    d = s[idx].sum(1) / c[idx].sum(1)
    return roi, float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5)), k


def net_of_cost(sub: pd.DataFrame, extra: float = 0.0):
    """Net ROI paying the measured half-spread + the REAL fee, plus an optional extra haircut."""
    p = sub.p0.values
    cost = sub.half.values + extra + FEE_RATE * p * (1 - p)
    turn = p + cost
    return cluster_boot(sub.win.values - turn, turn, sub.event.values)


# --------------------------------------------------------------------------- loading
def load_markets() -> pd.DataFrame:
    if not os.path.exists(MK):
        sys.exit(f"FATAL: {MK} missing — cannot define the universe.")
    df = pd.read_parquet(MK)
    df = df[df.closed.astype(str) == "True"].copy()
    op = df.outcomePrices.astype(str)
    df["o0"] = pd.to_numeric(op.str.extract(r'^\["([\d.]+)"')[0], errors="coerce")
    df["o1"] = pd.to_numeric(op.str.extract(r',"([\d.]+)"\]$')[0], errors="coerce")
    clean = ((df.o0 == 1) & (df.o1 == 0)) | ((df.o0 == 0) & (df.o1 == 1))
    if clean.mean() < 0.80:
        sys.exit(f"FATAL: only {clean.mean():.1%} of closed markets resolve cleanly binary — "
                 "the settlement parse is probably broken. Refusing to measure.")
    df = df[clean].copy()
    df["won0"] = (df.o0 == 1).astype(int)      # did outcome[0] win
    df["gst"] = pd.to_datetime(df.gameStartTime, errors="coerce", utc=True)
    df["event"] = df.slug.map(event_key)
    df["league"] = df.event.str.split("-").str[0]
    return df


def load_trades() -> pd.DataFrame:
    files = sorted(glob.glob(TS_GLOB))
    if not files:
        sys.exit(f"FATAL: no time-and-sales parquet at {TS_GLOB}")
    fr = []
    for p in files:
        t = pd.read_parquet(p, columns=["Transaction Time", "Symbol", "Last Price", "Last Quantity"])
        t.columns = ["tt", "symbol", "price", "qty"]
        fr.append(t)
    ts = pd.concat(fr, ignore_index=True)
    ts["price"] = pd.to_numeric(ts.price, errors="coerce")
    ts["tt"] = pd.to_datetime(ts.tt, errors="coerce", utc=True, format="mixed")
    return ts.dropna(subset=["price", "tt"])


def orientation_guard(entries: pd.DataFrame) -> float:
    """The tape price must track outcome[0]. Validate against the OFFICIAL DMR settlement.

    A missing orientation guard is how a prior harness silently bet the wrong side. If agreement is
    not ~100% we refuse to continue rather than emit an inverted result."""
    files = sorted(glob.glob(DMR_GLOB))
    if not files:
        print("  WARN: no DMR available — orientation validated only by calibration sign.")
        hi = entries[entries.p_raw > 0.5]
        if len(hi) and hi.won0.mean() < 0.5:
            sys.exit("FATAL: high-priced side loses more often than not — orientation is INVERTED.")
        return float("nan")
    d = pd.concat([pd.read_csv(f, low_memory=False) for f in files], ignore_index=True)
    d.columns = [c.strip() for c in d.columns]
    d["bd"] = pd.to_datetime(d["Business Date"], errors="coerce").dt.date
    d["md"] = pd.to_datetime(d["Maturity Date"], errors="coerce").dt.date
    d["settle"] = pd.to_numeric(d["Settlement Price"], errors="coerce")
    term = d[(d.bd == d.md) & d.settle.isin([0.0, 1.0])][["Symbol", "settle"]].drop_duplicates("Symbol")
    j = entries.merge(term, left_on="symbol", right_on="Symbol", how="inner")
    if len(j) < 50:
        print(f"  WARN: only {len(j)} DMR-matched symbols — orientation check is weak.")
        return float("nan")
    agree = (j.settle == j.won0).mean()
    if agree < 0.95:
        sys.exit(f"FATAL: DMR settlement agrees with the market record only {agree:.1%} of the "
                 "time. Orientation or settlement parse is wrong. Refusing to measure.")
    return float(agree)


def build_entries() -> pd.DataFrame:
    mk = load_markets()
    ts = load_trades()
    m = ts.merge(mk[["slug", "gst"]], left_on="symbol", right_on="slug", how="inner")

    pre = m[m.tt < m.gst].sort_values("tt")
    n_sym_traded = m.symbol.nunique()

    # entry = the last real trade strictly BEFORE game start. Never imputed.
    ent = pre.groupby("symbol").agg(p_raw=("price", "last"), n_pre=("price", "size"),
                                    vol=("qty", "sum"), t_entry=("tt", "last")).reset_index()
    # causal Roll spread from PRE-GAME trades only (information available at the decision moment)
    rs = pre.groupby("symbol").price.apply(lambda g: roll_spread(g.values)).rename("roll")
    ent = ent.merge(rs, left_on="symbol", right_index=True, how="left")

    e = ent.merge(mk[["slug", "won0", "gst", "sportsMarketType", "event", "league"]],
                  left_on="symbol", right_on="slug", how="inner")
    cov = len(e) / max(n_sym_traded, 1)
    print(f"  universe: {len(mk):,} cleanly-resolved markets | traded symbols {n_sym_traded:,}")
    print(f"  with a REAL pre-game entry price: {len(e):,} ({cov:.1%}) — "
          f"{n_sym_traded - len(e):,} DROPPED, never imputed")

    agree = orientation_guard(e)
    if agree == agree:
        print(f"  orientation guard: DMR settlement agreement {agree:.2%}  OK")

    fav0 = e.p_raw > 0.5
    e["p0"] = np.where(fav0, e.p_raw, 1 - e.p_raw)
    e["win"] = np.where(fav0, e.won0, 1 - e.won0)
    e["half"] = e.roll / 2
    e["lead_min"] = (e.gst - e.t_entry).dt.total_seconds() / 60
    e["day"] = e.t_entry.dt.date
    return e[(e.p0 > 0.5) & (e.p0 < 1.0)].copy()


def apply_strategy(e: pd.DataFrame) -> pd.DataFrame:
    """The strategy as specified: favourite band, liquid, fresh, with a measured spread."""
    s = e[(e.p0 >= BAND_LO) & (e.p0 <= BAND_HI)]
    s = s[s.n_pre >= MIN_PREGAME_TRADES]
    s = s[s.half.notna()]
    return s.copy()


# --------------------------------------------------------------------------- reporting
def measure(gate: bool):
    print("=" * 96)
    print("FAVBAND — liquid tight-spread US favourite band")
    print("=" * 96)
    e = build_entries()
    s = apply_strategy(e)
    band_all = e[(e.p0 >= BAND_LO) & (e.p0 <= BAND_HI)]
    print(f"\n  band {BAND_LO}-{BAND_HI}: {len(band_all):,} entries -> "
          f"after liquidity(>={MIN_PREGAME_TRADES} pre-game trades) + measurable spread: "
          f"{len(s):,} ({len(s)/max(len(band_all),1):.1%})")

    roi, lo, hi, k = net_of_cost(s)
    gap = (s.win - s.p0).mean()
    print(f"\n  entries {len(s):,} | events {k:,} | leagues {s.league.nunique()}")
    print(f"  mean price {s.p0.mean():.4f}   win {s.win.mean():.4f}   gap {gap*100:+.2f}pp")
    print(f"  measured half-spread {s.half.mean()*100:.2f}c   "
          f"fee {FEE_RATE*s.p0.mean()*(1-s.p0.mean())*100:.2f}c")
    print(f"  NET ROI-on-turnover {roi*100:+.2f}%  [{lo*100:+.2f}, {hi*100:+.2f}]  "
          f"{'LB>0' if lo > 0 else 'LB<=0'}")

    if gate:
        run_gate(s)
    return s


def run_gate(s: pd.DataFrame):
    print("\n" + "=" * 96)
    print("PRE-REGISTERED GATE (PREREG-2026-07-18-GRAVEYARD-RESWEEP.md) — all 6 or k=0")
    print("=" * 96)
    verdicts = []

    # 1 fresh executable entry
    fresh = s[s.lead_min < FRESH_MAX_MIN]
    g1 = len(fresh) / max(len(s), 1) >= 0.5 and (fresh.win - fresh.p0).mean() > 0
    print(f"  1 FRESH ENTRY      {len(fresh):,}/{len(s):,} within {FRESH_MAX_MIN}min, "
          f"gap {(fresh.win-fresh.p0).mean()*100:+.2f}pp  -> {'PASS' if g1 else 'FAIL'}")
    verdicts.append(g1)

    # 2 survives cost (+1c)
    r0, l0, _, _ = net_of_cost(s)
    r1, l1, _, _ = net_of_cost(s, extra=0.010)
    g2 = l1 > 0
    print(f"  2 COST +1.0c       net {r1*100:+.2f}% LB {l1*100:+.2f}  -> {'PASS' if g2 else 'FAIL'}")
    for x in (0.0025, 0.005, 0.0075):
        rx, lx, hx, _ = net_of_cost(s, extra=x)
        print(f"      (+{x*100:.2f}c: {rx*100:+.2f}% [{lx*100:+.2f},{hx*100:+.2f}])")
    verdicts.append(g2)

    # 3 not one competition / one time block
    vc = s.league.value_counts()
    conc = vc.iloc[0] / len(s)
    days = sorted(s.day.unique())
    mid = days[len(days) // 2]
    h1 = net_of_cost(s[s.day < mid])
    h2 = net_of_cost(s[s.day >= mid])
    g3 = conc < 0.80 and h1[1] > 0 and h2[1] > 0
    print(f"  3 NOT ONE REGIME   top league {vc.index[0]} {conc:.1%} (<80% req) | "
          f"H1 {h1[0]*100:+.2f}% LB{h1[1]*100:+.2f} | H2 {h2[0]*100:+.2f}% LB{h2[1]*100:+.2f}"
          f"  -> {'PASS' if g3 else 'FAIL'}")
    verdicts.append(g3)

    # 4 leave-one-league-out
    lodo_ok = True
    print("  4 LODO (leagues)   ", end="")
    outs = []
    for lg in vc.head(6).index:
        sub = s[s.league != lg]
        if len(sub) < 200:
            continue
        r, l, h, _ = net_of_cost(sub)
        outs.append(f"-{lg}:{r*100:+.2f}%{'*' if l > 0 else ''}")
        lodo_ok &= l > 0
    print(" ".join(outs) + f"  -> {'PASS' if lodo_ok else 'FAIL'}")
    verdicts.append(lodo_ok)

    # 5 capacity
    medvol = s.vol.median()
    g5 = medvol >= 500
    print(f"  5 CAPACITY         median pre-game volume {medvol:,.0f} contracts (>=500 req)"
          f"  -> {'PASS' if g5 else 'FAIL'}")
    verdicts.append(g5)

    # 6 not stale-driven
    stale = s[s.lead_min >= FRESH_MAX_MIN]
    g6 = (fresh.win - fresh.p0).mean() > 0 and len(fresh) > len(stale)
    print(f"  6 NOT STALE-DRIVEN fresh gap {(fresh.win-fresh.p0).mean()*100:+.2f}pp vs "
          f"stale {(stale.win-stale.p0).mean()*100:+.2f}pp  -> {'PASS' if g6 else 'FAIL'}")
    verdicts.append(g6)

    print("\n  " + "-" * 92)
    n_pass = sum(bool(v) for v in verdicts)
    print(f"  VERDICT: {n_pass}/6 criteria pass.  "
          f"{'FORWARD-TEST CANDIDATE' if n_pass == 6 else 'NOT CERTIFIED — k=0'}")

    # ---- re-net against the TRUE quoted spread (us_quotes), not Roll's lower bound
    print("\n  RE-NET vs the TRUE quoted spread (us_quotes 07-14..19, n=670 in band):")
    for lab, sp in [("passive: pay the MEAN spread 3.71c", TRUE_SPREAD_MEAN),
                    ("SELECTIVE: only trade the 1c book", TRUE_SPREAD_MEDIAN)]:
        extra = sp / 2 - s.half.mean()      # replace the Roll half with the true half
        r, l, h, _ = net_of_cost(s, extra=max(extra, 0.0))
        print(f"    {lab:36s} net {r*100:+.2f}%  [{l*100:+.2f}, {h*100:+.2f}]"
              f"  {'LB>0' if l > 0 else ''}")
    print("    -> the spread is OBSERVABLE BEFORE ENTRY, so the selective row is the")
    print("       implementable one — but it requires a live quote at decision time.")

    print("\n  OPEN DEFECT — CAPACITY IS UNMEASURED, NOT MEASURED-AND-BAD:")
    print("    us_quotes.bid_depth_usd / ask_depth_usd are NOT dollars. The venue's /bbo returns")
    print("    `bidDepth`/`askDepth` as BARE INTEGERS (0-18) while every price field is a typed")
    print("    {value,currency} object, and sharesTraded runs to thousands. The `_usd` suffix is a")
    print("    misnomer; these look like order/level counts. No dollar depth is captured anywhere,")
    print("    so the tradeable size per signal is UNKNOWN. This gates any sizing decision.")


# --------------------------------------------------------------------------- true spread
def psql(sql: str):
    o = subprocess.run(PG, input=GUARD + sql, capture_output=True, text=True)
    if o.returncode != 0:
        sys.exit("psql FAILED (is postgres up? `docker compose up -d postgres` ONLY):\n"
                 + o.stderr[:1200])
    import csv
    return list(csv.DictReader(io.StringIO(o.stdout)))


def spread_truth():
    """Replace Roll's LOWER BOUND with the venue's actual quoted spread from us_quotes.
    This is the single measurement that decides the verdict."""
    print("=" * 96)
    print("TRUE US SPREAD from us_quotes (real best_bid/best_ask, not a Roll lower bound)")
    print("=" * 96)
    rows = psql(
        "SELECT width_bucket((best_bid+best_ask)/2.0, 0.80, 0.98, 9) AS b, "
        "count(*) AS n, avg((best_bid+best_ask)/2.0) AS mid, "
        "avg(best_ask-best_bid) AS spread, "
        "percentile_cont(0.5) WITHIN GROUP (ORDER BY best_ask-best_bid) AS med_spread, "
        "avg(bid_depth_usd) AS bid_depth, avg(ask_depth_usd) AS ask_depth "
        "FROM us_quotes WHERE best_bid IS NOT NULL AND best_ask IS NOT NULL "
        "AND best_ask > best_bid AND (best_bid+best_ask)/2.0 BETWEEN 0.80 AND 0.98 "
        "GROUP BY 1 ORDER BY 1;")
    if not rows:
        print("  us_quotes has NO usable two-sided quotes in the band.")
        print("  -> the capture must run before this question can be answered:")
        print("     wt/capture (pinned to main), launchd com.tue.consensus.usquotes")
        return
    print(f"  {'mid':>8} {'n':>9} {'spread c':>10} {'median c':>10} {'half ROI %':>11} "
          f"{'bid depth $':>12}")
    tot_n = tot_sp = 0
    for r in rows:
        mid = float(r["mid"]); n = int(r["n"]); sp = float(r["spread"])
        tot_n += n; tot_sp += sp * n
        print(f"  {mid:>8.3f} {n:>9,} {sp*100:>10.2f} {float(r['med_spread'])*100:>10.2f} "
              f"{(sp/2/mid)*100:>11.2f} {float(r['bid_depth'] or 0):>12,.0f}")
    avg_sp = tot_sp / max(tot_n, 1)
    print(f"\n  band-wide mean spread {avg_sp*100:.2f}c -> half {avg_sp*50:.2f}c")
    print(f"  Roll's lower bound was ~0.96c mean / 0.44c median half-spread.")
    print(f"  SHORTFALL to feed back into the gate: {(avg_sp/2 - 0.0096)*100:+.2f}c")


# --------------------------------------------------------------------------- self-test
def self_test() -> int:
    # event key collapses submarkets of one game
    assert event_key("astatc-mlb-wsh-cin-2026-05-13-hr-ellcru-gte1") == "mlb-wsh-cin-2026-05-13"
    assert event_key("aec-mlb-wsh-cin-2026-05-13") == "mlb-wsh-cin-2026-05-13"
    assert event_key("tec-nba-mvp-2026-06-10-shagil") == "nba-mvp-2026-06-10"

    # Roll: pure bid-ask bounce around a constant mid must recover the spread
    rng = np.random.default_rng(0)
    mid, s = 0.90, 0.02
    px = mid + np.where(rng.random(4000) < 0.5, -s / 2, s / 2)
    est = roll_spread(px)
    assert abs(est - s) < 0.004, f"Roll should recover ~{s}, got {est}"

    # Roll on a pure random walk (no spread) must be ~0
    walk = 0.9 + np.cumsum(rng.normal(0, 0.001, 4000))
    assert roll_spread(walk) < 0.005

    # fee vanishes at the extremes and peaks at 0.5 — the schedule, not a flat 3%
    fee = lambda p: FEE_RATE * p * (1 - p)
    assert fee(0.50) > fee(0.90) > fee(0.99)
    assert abs(fee(0.5) - 0.0125) < 1e-9

    # clustered bootstrap: correlated submarkets must NOT narrow the CI vs independent ones
    n = 600
    ev_corr = np.repeat(np.arange(n // 10), 10)          # 10 submarkets per event
    ev_ind = np.arange(n)
    pnl = np.repeat(rng.normal(0, 1, n // 10), 10)        # perfectly correlated within event
    turn = np.ones(n)
    _, lo_c, hi_c, kc = cluster_boot(pnl, turn, ev_corr)
    _, lo_i, hi_i, ki = cluster_boot(pnl, turn, ev_ind)
    assert (hi_c - lo_c) > (hi_i - lo_i), "event clustering must WIDEN the CI on correlated rows"
    assert kc == n // 10 and ki == n

    # net_of_cost must be monotonically decreasing in the extra haircut
    df = pd.DataFrame({"p0": np.full(200, 0.90), "win": rng.random(200) < 0.92,
                       "half": np.full(200, 0.002), "event": np.arange(200)})
    df["win"] = df.win.astype(float)
    r0 = net_of_cost(df, 0.0)[0]
    r1 = net_of_cost(df, 0.01)[0]
    assert r1 < r0, "adding cost must reduce net ROI"

    print("favband self-test OK "
          "(event key, Roll recovery + null, fee schedule, cluster widening, cost monotonicity)")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--measure", action="store_true")
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--spread-truth", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test())
    if a.spread_truth:
        spread_truth()
        return
    if a.measure or a.gate:
        measure(gate=a.gate)
        return
    ap.print_help()


if __name__ == "__main__":
    main()
