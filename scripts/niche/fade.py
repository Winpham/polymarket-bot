#!/usr/bin/env python3
"""
FADE THE RELIABLY BAD -- the inversion the data actually supports.

The panel said: no ranker finds copyable WINNERS within a niche (0/32 cells). But the
attenuation check said something subtler -- among high-activity wallets (>=50 markets in
window A) the A->B rank correlation is significantly POSITIVE (esports +0.188 [+0.05,+0.32];
tennis +0.193 [+0.09,+0.29]). So trader quality IS persistent and rankable.

Reconciling the two: the top-50's out-of-sample edge is ~0 while the REST OF THE FIELD runs
at -1.5% to -1.8%. The ranking persists because the BAD TRADERS RELIABLY STAY BAD -- not
because the good ones make money. You cannot copy your way to profit here. The question this
script asks is whether you can FADE your way there.

THE ARITHMETIC OF FADING (why it is not merely "copying with a minus sign"):

1. P&L is an exact negation. They BUY outcome o at price p; we buy the COMPLEMENT at (1-p).
   our advantage = (1 - won_o) - (1 - p) = p - won_o = -(their advantage).   Exactly minus.

2. *** THE FOLLOWER TAX FLIPS SIGN. *** This is the crux. When copying, their buy pushes o's
   price UP and we pay ~1.3c worse -- the tax that has killed every copy strategy this
   project has tested. When FADING, their buy pushes o UP, which pushes the COMPLEMENT DOWN,
   so we buy our side ~1.3c CHEAPER. The same market impact that taxes a copier SUBSIDISES a
   fader. The 1.3c headwind becomes a 1.3c tailwind -- a ~2.6c swing in the economics.

3. It must be NEW edge, not the favourite bias in disguise. If bad traders are simply
   longshot-lovers, then "fade them" = "buy favourites", which this project already knows
   and exploits. So the fade is scored as SURPLUS OVER THE BLIND BASELINE OF THE SIDE WE
   TAKE: be_fade(niche, band-of-(1-p)) = population mean of (p - won) in that band. Only
   edge ABOVE that baseline is genuinely new.

Bankability bar (pre-registered): fees ~2% + slippage ~1% = 3% capture cost. Fading is
bankable only if the fade surplus's market-clustered 95% CI lies ENTIRELY ABOVE +3%,
measured OUT OF SAMPLE (ranked in window A, paid in window B).
"""
import argparse
import csv
import io
import json
import os
import statistics
import subprocess
import sys
from collections import defaultdict

import numpy as np

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]

CAPTURE_COST = 0.03     # fees + slippage: the bar a fade must clear
FADE_SUBSIDY = 0.013    # the follower tax, which works FOR us when fading (see above)
N_FLOOR_SPLIT = 8
SEED = 20260714


def psql(sql):
    out = subprocess.run(PG, input=sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("psql failed:\n" + out.stderr)
    return list(csv.DictReader(io.StringIO(out.stdout)))


SQL = r"""
WITH res AS (
  SELECT condition_id, outcome_index, BOOL_OR(outcome_won) AS won
  FROM trader_fills WHERE resolved AND outcome_won IS NOT NULL GROUP BY 1,2
),
ok AS (SELECT condition_id FROM harvest_markets WHERE NOT truncated),
f AS (
  SELECT h.wallet, h.niche, h.condition_id, h.price, h.size_usd, h.is_maker,
         EXTRACT(EPOCH FROM h.ts) ts, (r.won::int)::float8 won,
         h.outcome_index,
         width_bucket(h.price, 0.0, 1.0, 20)       AS band,
         width_bucket(1.0 - h.price, 0.0, 1.0, 20) AS fband   -- the band of OUR side
  FROM harvest_fills h
  JOIN ok USING (condition_id)
  JOIN res r ON r.condition_id=h.condition_id AND r.outcome_index=h.outcome_index
  WHERE h.side='BUY'
),
blind      AS (SELECT niche, band,  AVG(won - price) be  FROM f GROUP BY 1,2),
blind_fade AS (SELECT niche, fband, AVG(price - won) bef FROM f GROUP BY 1,2)
SELECT f.wallet, f.niche, f.condition_id,
       AVG(f.won - f.price - b.be)            AS surplus,       -- THEIR skill (rank on this)
       AVG(f.price - f.won - bf.bef)          AS fade_surplus,  -- OUR edge over blind, if we fade
       AVG(f.price - f.won)                   AS fade_raw,      -- OUR raw P&L if we fade
       AVG(f.price)                           AS price,
       SUM(f.size_usd)                        AS usd,
       AVG((f.is_maker)::int::float8)         AS maker_frac,
       COUNT(DISTINCT f.outcome_index)        AS n_sides,
       MAX(f.ts)                              AS ts
FROM f
JOIN blind      b  ON b.niche=f.niche  AND b.band=f.band
JOIN blind_fade bf ON bf.niche=f.niche AND bf.fband=f.fband
GROUP BY f.wallet, f.niche, f.condition_id;
"""


def cluster_boot(recs, n_boot=4000, seed=SEED):
    if not recs:
        return 0.0, 0.0, 0.0, 0
    by = defaultdict(list)
    for m, v in recs:
        by[m].append(v)
    keys = list(by)
    sums = np.array([sum(by[k]) for k in keys], float)
    lens = np.array([len(by[k]) for k in keys], float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(keys), (n_boot, len(keys)))
    means = sums[idx].sum(1) / np.maximum(lens[idx].sum(1), 1)
    return (float(sums.sum() / lens.sum()),
            float(np.percentile(means, 2.5)),
            float(np.percentile(means, 97.5)), len(keys))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-a", type=int, default=8,
                    help="min window-A markets (the attenuation check says quality is "
                         "only reliably rankable at high N)")
    ap.add_argument("--bottom", type=int, default=50)
    ap.add_argument("--out", default="reports/niche")
    ap.add_argument("--niche", default=None)
    a = ap.parse_args()

    # One niche at a time: the full tape is now ~45M fills, and materialising every niche
    # at once in Python dicts exhausts memory.
    sql = SQL if not a.niche else SQL.replace(
        "WHERE h.side='BUY'", f"WHERE h.side='BUY' AND h.niche = '{a.niche}'")
    rows = psql(sql)
    recs = defaultdict(list)
    for r in rows:
        try:
            recs[(r["wallet"], r["niche"])].append({
                "mkt": r["condition_id"], "surplus": float(r["surplus"]),
                "fade_surplus": float(r["fade_surplus"]), "fade_raw": float(r["fade_raw"]),
                "price": float(r["price"]), "usd": float(r["usd"]),
                "maker_frac": float(r["maker_frac"] or 0), "n_sides": int(r["n_sides"]),
                "ts": float(r["ts"])})
        except (ValueError, TypeError):
            continue

    def is_mm(mk):
        maker = statistics.fmean([m["maker_frac"] for m in mk])
        two = sum(1 for m in mk if m["n_sides"] >= 2) / len(mk)
        return maker >= 0.80 or (two >= 0.50 and maker >= 0.5)

    out = []
    for nz in sorted({n for (_, n) in recs}):
        mkt_ts = {}
        for (w, x), mk in recs.items():
            if x != nz:
                continue
            for m in mk:
                mkt_ts[m["mkt"]] = max(mkt_ts.get(m["mkt"], 0.0), m["ts"])
        if not mkt_ts:
            continue
        cut = sorted(mkt_ts.values())[len(mkt_ts) // 2]
        win_A = {k for k, v in mkt_ts.items() if v <= cut}

        pool = {}
        for (w, x), mk in recs.items():
            if x != nz or is_mm(mk):
                continue
            A = [m for m in mk if m["mkt"] in win_A]
            B = [m for m in mk if m["mkt"] not in win_A]
            if len(A) >= a.min_a and len(B) >= N_FLOOR_SPLIT:
                pool[w] = (A, B)
        if len(pool) < 40:
            print(f"\n{nz}: {len(pool)} testable wallets -- UNDERPOWERED, skipped")
            continue

        ranked = sorted(pool.items(),
                        key=lambda kv: statistics.fmean([m["surplus"] for m in kv[1][0]]))
        k = min(a.bottom, max(10, len(ranked) // 4))
        worst = ranked[:k]                    # the reliably BAD, ranked in window A only

        # OUT-OF-SAMPLE: what we would have earned fading them in window B
        fs = [(m["mkt"], m["fade_surplus"]) for _, (A, B) in worst for m in B]
        fr = [(m["mkt"], m["fade_raw"]) for _, (A, B) in worst for m in B]
        s_obs, s_lo, s_hi, nclu = cluster_boot(fs)
        r_obs, r_lo, r_hi, _ = cluster_boot(fr)

        # control: fading a RANDOM wallet in the niche (is the selection doing any work?)
        rest = [(m["mkt"], m["fade_surplus"]) for w, (A, B) in ranked[k:] for m in B]
        c_obs, c_lo, c_hi, _ = cluster_boot(rest)

        # BANKABILITY MUST BE COMPUTED ON THE RAW P&L, NOT ON SURPLUS-OVER-BLIND.
        # If we fade, our realised P&L per $1 is exactly (p - won_o) = fade_raw. The blind
        # baseline is a BENCHMARK, not something we are paid; using it here would credit us
        # with money we never receive. Surplus-over-blind answers "is the selection real?";
        # only raw answers "does it make money?". They can disagree sharply -- and here they
        # do, because a trader can lose to the blind favourite baseline while still being
        # roughly fairly priced in absolute terms (mediocre, not a donor).
        net = r_obs + FADE_SUBSIDY - CAPTURE_COST
        bankable = (r_lo + FADE_SUBSIDY) > CAPTURE_COST
        selection_real = s_lo > 0

        print(f"\n{'='*76}\nNICHE: {nz}   (bottom-{k} of {len(pool)} wallets, "
              f">= {a.min_a} markets in window A)")
        print(f"  fade surplus over blind (OUT-OF-SAMPLE, window B):")
        print(f"     {s_obs:+.4f}  95% CI [{s_lo:+.4f}, {s_hi:+.4f}]  "
              f"({nclu} markets, clustered)")
        print(f"     control (fade everyone else) : {c_obs:+.4f} [{c_lo:+.4f}, {c_hi:+.4f}]")
        print(f"     => selection is "
              f"{'REAL (CI excludes 0, control flat)' if selection_real else 'not distinguishable from the field'}")
        print(f"  fade RAW P&L -- THE MONEY        : {r_obs:+.4f} [{r_lo:+.4f}, {r_hi:+.4f}]")
        print(f"     + follower-tax subsidy        : {FADE_SUBSIDY:+.4f}  (their impact "
              f"cheapens OUR side)")
        print(f"     - capture cost (fees+slippage): {-CAPTURE_COST:+.4f}")
        print(f"     = NET                         : {net:+.4f}")
        print(f"  => {'*** BANKABLE ***' if bankable else 'NOT BANKABLE -- the signal is real but too small to pay for itself'}")
        out.append({"niche": nz, "n_pool": len(pool), "bottom_k": k, "min_a": a.min_a,
                    "fade_surplus": s_obs, "ci": [s_lo, s_hi], "fade_raw": r_obs,
                    "fade_raw_ci": [r_lo, r_hi], "control": c_obs, "net": net,
                    "bankable": bankable, "selection_real": selection_real,
                    "n_markets": nclu,
                    "wallets": [w for w, _ in worst]})

    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, f"fade_minA{a.min_a}.json"), "w") as f:
        json.dump(out, f, indent=2)
    n_bank = sum(1 for o in out if o["bankable"])
    print(f"\n{'='*76}\nFADE RESULT: {n_bank} of {len(out)} niches bankable "
          f"(CI clears the 3% capture cost, out-of-sample)")


if __name__ == "__main__":
    main()
