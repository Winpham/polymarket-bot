#!/usr/bin/env python3
"""
SIZED-BOOK REPLAY — does Kelly-per-game SIZING beat flat-$ on the history we have?

Read-only, offline "see how it performs" for the decide() kernel — NO deploy, NO
prod write, NO real money. It re-sizes every resolved `favorite` signal with the
kernel's exact formula and compares the resulting paper P&L against the deployed
flat-$100 champion (and flat-100-shares), on the identical fills/outcomes.

  kernel stake (UNGATED) = KELLY_K · KELLY_BAND[band] · BANKROLL / game_n
                           (m_sport = gate = earned = 1; cap = SIZED_CAP_USD)
  pnl                    = stake · ((won − entry)/entry − fee)
  entry                  = COALESCE(entry_ask, initial_market_price + haircut)
  band                   = int(entry·5)+1   (kelly 0 outside bands 4,5 and at ≥$1)
  game_n                 = distinct (condition,outcome) in the match super-key

HONEST SCOPE (state it every time): this is the SIZING question ONLY, measured
IN-SAMPLE on the same summer window the edge was observed on. It says whether
per-game Kelly + capacity reshapes P&L better than a flat stake; it says NOTHING
about whether the edge is REAL or will persist — that is the forward gate's job,
and the live kernel stays k=0 until it certifies. "Kelly beats flat here" is
necessary, not sufficient, and is not a promotion.

Usage:
  ./sized_book_replay.py                 # live replay vs the DB
  ./sized_book_replay.py --cap 250       # apply a $250 per-leg capacity clamp
  ./sized_book_replay.py --selftest      # no DB: verify the sizing/PnL math
"""

import csv
import io
import math
import os
import subprocess
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from superkey import super_event  # noqa: E402

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]

# FROZEN kernel constants — mirror scanner::decide (applied, never fit).
KELLY_K = 1.0 / 12.0
KELLY_BAND = [0.0, 0.0, 0.0, 0.0, 0.1933, 0.5584, 0.0]  # index 6 (entry≥$1) = 0
BANKROLL = 10_000.0
HAIRCUT = 0.01
FEE = 0.02
FLAT = 100.0
STRAT = "favorite"


def band(p):
    if p < 0:
        return 0
    if p >= 1:
        return 6
    return int(p * 5) + 1


SQL = """
SELECT event_slug, COALESCE(slug,'') AS slug, condition_id, outcome_index,
       entry_ask, initial_market_price, mean_price,
       (outcome_won::int) AS won,
       to_char(COALESCE(resolved_at, first_detected_at) AT TIME ZONE 'UTC','YYYY-MM-DD') AS day
FROM consensus_signals
WHERE strategy = 'favorite' AND resolved AND outcome_won IS NOT NULL
  AND (entry_ask IS NOT NULL OR initial_market_price IS NOT NULL)
"""


def fetch():
    out = subprocess.run(PG + ["-f", "-"], input=SQL, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    rows = []
    for r in csv.DictReader(io.StringIO(out.stdout)):
        def f(x):
            return float(x) if x not in ("", None) else None
        rows.append(dict(
            event_slug=r["event_slug"] or None, slug=r["slug"],
            condition_id=r["condition_id"], outcome_index=int(r["outcome_index"]),
            entry_ask=f(r["entry_ask"]), initial=f(r["initial_market_price"]),
            mean=f(r["mean_price"]), won=int(r["won"]), day=r["day"],
        ))
    return rows


def entry_of(r):
    if r["entry_ask"] is not None:
        return r["entry_ask"]
    if r["initial"] is not None:
        return r["initial"] + HAIRCUT
    return r["mean"]


def clusters(rows):
    """(super-key) → distinct (condition,outcome) count = game_n."""
    g = defaultdict(set)
    for r in rows:
        k = super_event(r["event_slug"], r["slug"]) or r["condition_id"]
        g[k].add((r["condition_id"], r["outcome_index"]))
    return {k: len(v) for k, v in g.items()}


def kernel_stake(r, game_n, cap):
    e = entry_of(r)
    b = band(e)
    raw = KELLY_K * KELLY_BAND[b] * BANKROLL / max(game_n, 1)
    return min(raw, cap) if cap > 0 else raw


def pnl(stake, entry, won):
    return stake * (((won - entry) / entry) - FEE) if entry and entry > 0 else 0.0


def book_stats(rows, stake_fn):
    """Return dict(bets, turnover, pnl, roi, win, maxdd, sharpe) for a sizing rule."""
    by_day = defaultdict(float)
    equity = 0.0
    peak = float("-inf")
    maxdd = 0.0
    turnover = tot = wins = 0.0
    n = 0
    for r in sorted(rows, key=lambda x: x["day"]):
        e = entry_of(r)
        s = stake_fn(r)
        if s <= 0:
            continue
        p = pnl(s, e, r["won"])
        turnover += s
        tot += p
        wins += r["won"]
        n += 1
        equity += p
        peak = max(peak, equity)
        maxdd = max(maxdd, peak - equity)
        by_day[r["day"]] += p
    days = list(by_day.values())
    if len(days) >= 2:
        m = sum(days) / len(days)
        sd = math.sqrt(sum((d - m) ** 2 for d in days) / (len(days) - 1))
        sharpe = m / sd if sd > 0 else 0.0
    else:
        sharpe = 0.0
    roi = tot / turnover if turnover > 0 else float("nan")
    return dict(bets=n, turnover=turnover, pnl=tot, roi=roi,
                win=wins / n if n else float("nan"), maxdd=maxdd, sharpe=sharpe)


def run_live(cap):
    rows = fetch()
    gn = clusters(rows)

    def keyfn(r):
        return super_event(r["event_slug"], r["slug"]) or r["condition_id"]

    kelly = book_stats(rows, lambda r: kernel_stake(r, gn[keyfn(r)], cap))
    flat_d = book_stats(rows, lambda r: FLAT)                      # flat $100
    flat_sh = book_stats(rows, lambda r: FLAT * entry_of(r))       # 100 shares = $ = 100·entry

    print("SIZED-BOOK REPLAY · favorite · IN-SAMPLE sizing comparison (paper, read-only)")
    print(f"  cap={'none' if cap <= 0 else f'${cap:.0f}/leg'} · k=1/12 · bankroll=${BANKROLL:.0f} · "
          f"{kelly['bets']} sized legs\n")
    hdr = f"{'sizing':<22} {'legs':>5} {'turnover$':>12} {'pnl$':>11} {'ROI-turn':>9} {'win%':>5} {'maxDD$':>10} {'sharpe':>7}"
    print(hdr)
    for name, s in [("kernel Kelly-per-game", kelly), ("flat $100 (champion)", flat_d),
                    ("flat 100-shares", flat_sh)]:
        print(f"{name:<22} {s['bets']:>5} {s['turnover']:>12.0f} {s['pnl']:>+11.0f} "
              f"{s['roi']:>+8.2%} {s['win']:>4.0%} {s['maxdd']:>10.0f} {s['sharpe']:>7.2f}")
    print("\nHONEST SCOPE: IN-SAMPLE sizing mechanics only (same summer window the edge was seen on).")
    print("It does NOT show the edge is real or will persist — the live kernel stays k=0 until the")
    print("forward gate certifies. 'Kelly beats flat here' is necessary, not sufficient, not a promote.")
    # a compact machine-readable tail for logging
    print(f"\nSUMMARY roi_kelly={kelly['roi']:.4f} roi_flat={flat_d['roi']:.4f} "
          f"pnl_kelly={kelly['pnl']:.1f} pnl_flat={flat_d['pnl']:.1f} "
          f"dd_kelly={kelly['maxdd']:.1f} dd_flat={flat_d['maxdd']:.1f}")
    return 0


def _self_test():
    ok = True
    # band-5 singleton MLB (game_n=1) @0.80 win: raw = 1/12·.5584·10000 = 465.33
    r_mlb = dict(event_slug="mlb-a-b-2026-07-01", slug="mlb-a-b-2026-07-01",
                 condition_id="c1", outcome_index=0, entry_ask=0.80, initial=None,
                 mean=0.80, won=1, day="2026-07-01")
    s = kernel_stake(r_mlb, 1, 0)
    c1 = abs(s - (KELLY_K * 0.5584 * BANKROLL)) < 1e-6 and abs(s - 465.333) < 1e-2
    print(f"  [{'ok' if c1 else 'FAIL'}] band-5 singleton stake = {s:.2f} (~465.33)")
    ok = ok and c1
    # game_n splits: same signal in a 20-leg match → /20
    c2 = abs(kernel_stake(r_mlb, 20, 0) - s / 20) < 1e-9
    print(f"  [{'ok' if c2 else 'FAIL'}] game_n=20 splits stake to {kernel_stake(r_mlb,20,0):.2f}")
    ok = ok and c2
    # cap clamps
    c3 = abs(kernel_stake(r_mlb, 1, 50) - 50.0) < 1e-9
    print(f"  [{'ok' if c3 else 'FAIL'}] cap $50 clamps to 50.00")
    ok = ok and c3
    # entry >= $1 (band 6) → 0 stake
    r_hi = dict(r_mlb, entry_ask=1.0)
    c4 = kernel_stake(r_hi, 1, 0) == 0.0
    print(f"  [{'ok' if c4 else 'FAIL'}] entry ≥ $1 (band 6) → 0 stake")
    ok = ok and c4
    # pnl math: win at 0.725, stake 200 → 200·((1-.725)/.725 - .02) = 71.86
    c5 = abs(pnl(200.0, 0.725, 1) - 71.86) < 0.01
    print(f"  [{'ok' if c5 else 'FAIL'}] pnl(200,0.725,win) = {pnl(200.0,0.725,1):.2f} (~71.86)")
    ok = ok and c5
    # clusters: two markets same match → game_n 2
    rows = [dict(event_slug="mlb-a-b-2026-07-01", slug="mlb-a-b-2026-07-01-ml",
                 condition_id="x", outcome_index=0),
            dict(event_slug="mlb-a-b-2026-07-01-total", slug="mlb-a-b-2026-07-01-total-5",
                 condition_id="y", outcome_index=1)]
    g = clusters(rows)
    c6 = list(g.values()) == [2]
    print(f"  [{'ok' if c6 else 'FAIL'}] two markets of one match → game_n {list(g.values())}")
    ok = ok and c6
    print("SELF-TEST", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(0 if _self_test() else 1)
    cap = 0.0
    if "--cap" in sys.argv:
        cap = float(sys.argv[sys.argv.index("--cap") + 1])
    sys.exit(run_live(cap))
