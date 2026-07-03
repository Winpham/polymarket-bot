#!/usr/bin/env python3
"""
MM STAGE-0 · RUNG 0 — the existing-data reward-vs-hazard read (the cheapest MM kill test).

Question (the market-making precondition): is the bid-ask half-spread a passive two-sided
quoter could EARN larger than the adverse-selection cost (adverse mid-move against a resting
quote over its hold horizon) in any reachable niche? If reward < hazard everywhere we can see,
the branch is dead for the visible market — and (per the forge verdict + Tue's ruling that live
Polymarket deployment is off the table on US-person ToS) that is where MM formally STOPS.

This is Rung 0 of the forge blueprint (run-prompts/RUN-MARKET-MAKING.FORGE_PLAN.md): a ~$0,
~1-hour read over data we ALREADY hold — NO capture, NO Rust, NO order placement, NO capital.
It KILLS what it can see; it cannot greenlight (its data is favorite-triggered/taker-side/
change-only — see the honest biases below). A NULL here is a successful, publishable run (D23 posture).

Reward proxy (per niche): consensus_signals.(entry_ask - entry_ask_mid) — the taker-quoted
half-spread. BIASED: taker-side + only on FIRED favorite markets. It is a FLOOR-ish read of the
spread a maker could post, on the wrong (favorite-consensus) markets.
Hazard proxy (per niche): |Δ market_price| over consensus_snapshots — the adverse mid drift a
resting quote eats. BIASED UP: change-only snapshots log a point only when price moved, so this
OVERSTATES the per-tick hazard a maker faces (conservative for a KILL, dangerous for a greenlight).

Net (per niche): median(half_spread) − E[|adverse_drift|]. If < 0 for EVERY stratum → KILL.

Also de-biases the one bullish datapoint (maker wallets' realized sell−buy round-trip spread):
report frac_roundtripped and the held-to-resolution win-rate, so the survivorship bias is explicit.

Usage:
  ./mm_rung0.py --self-test     # injected + null fixtures (no DB)
  ./mm_rung0.py                 # live read + pre-registered verdict
"""
import argparse
import csv
import io
import subprocess
import sys
from statistics import median, mean

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]

# Pre-registered decision constants.
MARGIN_CUSHION = 0.002     # 0.2c unmodeled-cost cushion (fees/slippage a maker still pays)
# Adverse-selection reward ceiling: nothing in the visible reward data exceeds ~0.75c.

REWARD_SQL = r"""
SELECT (is_sports::int) AS sports,
       width_bucket(entry_ask_mid, 0, 1, 5) AS band,
       count(*) AS n,
       avg(entry_ask - entry_ask_mid) AS hs_mean,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY entry_ask - entry_ask_mid) AS hs_med
FROM consensus_signals
WHERE entry_ask IS NOT NULL AND entry_ask_mid IS NOT NULL
GROUP BY 1, 2
HAVING count(*) >= 20
ORDER BY hs_mean DESC;
"""

# Hazard = mean |Δ mid| between consecutive change-only snapshots of the same signal.
# Reported overall and split by whether the step is within 10 min (a maker's short hold).
HAZARD_SQL = r"""
WITH steps AS (
  SELECT signal_id,
         market_price - lag(market_price) OVER (PARTITION BY signal_id ORDER BY ts) AS dp,
         EXTRACT(EPOCH FROM (ts - lag(ts) OVER (PARTITION BY signal_id ORDER BY ts)))/60.0 AS gap_min
  FROM consensus_snapshots WHERE market_price IS NOT NULL
)
SELECT count(*) AS n,
       avg(abs(dp)) AS drift_mean,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY abs(dp)) AS drift_med,
       percentile_cont(0.9) WITHIN GROUP (ORDER BY abs(dp)) AS drift_p90,
       avg(abs(dp)) FILTER (WHERE gap_min <= 10) AS drift_mean_10m,
       count(*) FILTER (WHERE gap_min <= 10) AS n_10m
FROM steps WHERE dp IS NOT NULL;
"""

# The one bullish datapoint, de-biased: the flagged maker wallets' round-trip realized spread,
# plus the disposition bias (what fraction they actually sold) and the held subset's win-rate.
ROUNDTRIP_SQL = r"""
WITH mm AS (SELECT unnest(ARRAY['0xe9076a','0x204f72','0x2005d1','0xb27bc9']) AS pfx),
buys AS (
  SELECT left(t.wallet,8) w, t.condition_id, t.outcome_index,
         sum(t.size_usd)/NULLIF(sum(t.size_usd/NULLIF(t.price,0)),0) AS buy_px,
         bool_or(t.outcome_won) AS won
  FROM trader_fills t JOIN mm ON left(t.wallet,8)=mm.pfx
  WHERE t.side='BUY' AND t.resolved GROUP BY 1,2,3),
sells AS (
  SELECT left(t.wallet,8) w, t.condition_id, t.outcome_index,
         sum(t.size_usd)/NULLIF(sum(t.size_usd/NULLIF(t.price,0)),0) AS sell_px
  FROM trader_fills t JOIN mm ON left(t.wallet,8)=mm.pfx
  WHERE t.side='SELL' GROUP BY 1,2,3)
SELECT b.w,
  count(*) AS bought_tokens,
  count(s.sell_px) AS sold_tokens,
  round((count(s.sell_px)::numeric/count(*)),3) AS frac_roundtripped,
  round(avg(s.sell_px - b.buy_px) FILTER (WHERE s.sell_px IS NOT NULL)::numeric,4) AS rt_spread_meansold,
  round(avg((b.won)::int) FILTER (WHERE s.sell_px IS NULL)::numeric,3) AS held_winrate
FROM buys b LEFT JOIN sells s USING (w, condition_id, outcome_index)
GROUP BY b.w ORDER BY bought_tokens DESC;
"""


def psql(sql):
    out = subprocess.run(PG, input=sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    return list(csv.DictReader(io.StringIO(out.stdout)))


def fnum(x):
    return float(x) if x not in (None, "") else None


def verdict(reward_cells, hazard_drift):
    """Pre-registered: KILL iff net = median(half_spread) - hazard < 0 for EVERY reward stratum.
    hazard_drift is the representative adverse drift (we use the within-10-min mean as the maker's
    short-hold hazard). Returns (killed: bool, best_net: float, best_cell)."""
    best_net, best_cell = None, None
    for c in reward_cells:
        hs = c["hs_med"]
        net = hs - hazard_drift - MARGIN_CUSHION
        if best_net is None or net > best_net:
            best_net, best_cell = net, c
    killed = best_net is not None and best_net < 0
    return killed, best_net, best_cell


def run_live():
    reward = [{"sports": int(r["sports"]), "band": int(r["band"]), "n": int(r["n"]),
               "hs_mean": fnum(r["hs_mean"]), "hs_med": fnum(r["hs_med"])}
              for r in psql(REWARD_SQL)]
    hz = psql(HAZARD_SQL)[0]
    drift_mean, drift_med = fnum(hz["drift_mean"]), fnum(hz["drift_med"])
    drift_10m = fnum(hz["drift_mean_10m"])
    rt = psql(ROUNDTRIP_SQL)

    print("\n========== MM STAGE-0 · RUNG 0 — reward vs hazard (existing data) ==========\n")
    print("REWARD (taker-quoted half-spread = entry_ask − entry_ask_mid), per niche "
          "[BIASED: taker-side, favorite-fired markets only]:")
    print(f"  {'sports':>6} {'band':>4} {'n':>6} {'hs_mean':>9} {'hs_med':>8}")
    for c in reward:
        print(f"  {c['sports']:>6} {c['band']:>4} {c['n']:>6} "
              f"{c['hs_mean']*100:>7.2f}c {c['hs_med']*100:>6.2f}c")
    best_reward = max((c["hs_med"] for c in reward), default=0.0)
    print(f"\n  best-niche median half-spread earned (reward ceiling): {best_reward*100:.2f}c\n")

    print("HAZARD (adverse mid drift = |Δ market_price| per snapshot step) "
          "[BIASED UP: change-only ⇒ overstates per-tick hazard]:")
    print(f"  mean {drift_mean*100:.2f}c | median {drift_med*100:.2f}c | "
          f"p90 {fnum(hz['drift_p90'])*100:.1f}c | within-10min mean {drift_10m*100:.2f}c\n")

    killed, best_net, best_cell = verdict(reward, drift_10m)
    ratio = drift_10m / best_reward if best_reward > 0 else float("inf")
    print(f"NET (best niche): median half-spread {best_cell['hs_med']*100:.2f}c "
          f"− hazard {drift_10m*100:.2f}c − cushion {MARGIN_CUSHION*100:.1f}c "
          f"= {best_net*100:+.2f}c   (hazard is {ratio:.1f}× the reward)\n")

    print("DE-BIAS the one bullish signal — maker wallets' round-trip spread + disposition bias:")
    print(f"  {'wallet':>8} {'bought':>7} {'sold':>6} {'frac_rt':>8} {'rt_spread':>10} {'held_winrate':>12}")
    for r in rt:
        rts = fnum(r['rt_spread_meansold'])
        hw = fnum(r['held_winrate'])
        print(f"  {r['w']:>8} {r['bought_tokens']:>7} {r['sold_tokens']:>6} "
              f"{fnum(r['frac_roundtripped']):>8.2f} "
              f"{(rts*100 if rts is not None else 0):>8.2f}c "
              f"{(hw if hw is not None else 0):>12.2f}")
    print("  ↑ the +sell−buy spread is measured ONLY on the SOLD (winning) half; the held remainder's\n"
          "    low win-rate is the adverse selection that the round-trip number hides.\n")

    print("=" * 76)
    if killed:
        print(f"VERDICT: KILL — reward < hazard on EVERY visible niche "
              f"(best net {best_net*100:+.2f}c, hazard {ratio:.1f}× reward).")
        print("Per the forge verdict + Tue's ruling (live Polymarket deployment off the table on")
        print("US-person ToS), MM formally STOPS at Rung 0. A NULL is a successful run. No capture,")
        print("no build, no capital. The dominant move (DENSE_CAPTURE→λ) proceeds independently.")
    else:
        print(f"VERDICT: NOT killed on visible data (best net {best_net*100:+.2f}c). The favorite-only/")
        print("taker-side blind spot could still hide a reachable niche — BUT Tue's legal ruling means")
        print("Rungs 1–2 are unactionable; MM parks here regardless.")
    print("=" * 76)
    return {"killed": killed, "best_net": best_net, "best_reward": best_reward,
            "hazard_10m": drift_10m, "ratio": ratio}


def self_test():
    print("=== Rung-0 self-test (synthetic fixtures, no DB) ===\n")
    ok = True
    # Injected: a niche where reward > hazard → NOT killed (a seat could exist).
    inj_reward = [{"sports": 1, "band": 4, "n": 100, "hs_mean": 0.03, "hs_med": 0.03}]
    killed, net, _ = verdict(inj_reward, hazard_drift=0.01)
    p1 = (not killed) and net > 0
    print(f"  [1] injected seat (reward 3c > hazard 1c) -> NOT killed: net={net*100:+.2f}c  "
          f"{'PASS' if p1 else 'FAIL'}")
    ok &= p1
    # Null: reward ≈ hazard → killed (no seat).
    null_reward = [{"sports": 0, "band": 3, "n": 100, "hs_mean": 0.005, "hs_med": 0.005}]
    killed2, net2, _ = verdict(null_reward, hazard_drift=0.02)
    p2 = killed2 and net2 < 0
    print(f"  [2] null niche (reward 0.5c < hazard 2c) -> KILL: net={net2*100:+.2f}c  "
          f"{'PASS' if p2 else 'FAIL'}")
    ok &= p2
    # Boundary: reward just above hazard+cushion → NOT killed (rule is strict).
    edge_reward = [{"sports": 1, "band": 5, "n": 50, "hs_med": 0.013, "hs_mean": 0.013}]
    killed3, net3, _ = verdict(edge_reward, hazard_drift=0.010)  # net = 0.013-0.010-0.002 = +0.001
    p3 = (not killed3) and abs(net3 - 0.001) < 1e-9
    print(f"  [3] boundary (reward 1.3c vs hazard 1.0c + cushion) -> NOT killed: net={net3*100:+.2f}c  "
          f"{'PASS' if p3 else 'FAIL'}")
    ok &= p3
    print(f"\n=== SELF-TEST {'PASS' if ok else 'FAIL'} ===")
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        sys.exit(0 if self_test() else 1)
    run_live()


if __name__ == "__main__":
    main()
