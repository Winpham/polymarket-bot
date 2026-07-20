"""FAVBAND vs THE STANDING 4-BAR CERTIFICATION (feedback-confidence-certification-bar).

  1. WALK-FORWARD  >=3 expanding folds, each test block strictly later, pooled LB>0
  2. LAMBDA        CLV/surplus, CI LB>0 at >=50% coverage
  3. BRIER-BEAT    our corrected probability must beat the raw market price OOS
  4. REALIZABLE    ROI LB>0 at the venue on official settlement   [already held]

Entry uses the LIVE-IMPLEMENTABLE 10-minute cutoff (no lookahead), not the last-print definition.

On bar 2: lambda asks "does the market come to agree with us before resolution?" That is the right
test for an INFORMATION edge and arguably the wrong one for a RISK-PREMIUM harvester, which earns
at settlement by construction. We compute it anyway and report it honestly rather than excusing it
in advance — but the interpretation is stated so a lambda of ~0 is not silently read as fatal.
"""
import sys, numpy as np, pandas as pd
sys.path.insert(0, '/Users/tuepham/polymarket-bot/wt/favband/scripts')
import favband as FB

FEE = FB.FEE_RATE
CUTOFF = 10.0

mk = FB.load_markets()
ts = FB.load_trades()
j = ts.merge(mk[['slug', 'gst']], left_on='symbol', right_on='slug', how='inner')
pre = j[(j.tt < j.gst)].copy()
pre['lead'] = (pre.gst - pre.tt).dt.total_seconds() / 60
pre = pre.sort_values('tt')

# ENTRY: last print at least CUTOFF minutes before kickoff
ent_src = pre[pre.lead >= CUTOFF]
ent = ent_src.groupby('symbol').agg(p_raw=('price', 'last'), n_pre=('price', 'size'),
                                    t_entry=('tt', 'last')).reset_index()
rs = ent_src.groupby('symbol').price.apply(lambda g: FB.roll_spread(g.values)).rename('roll')
ent = ent.merge(rs, left_on='symbol', right_index=True, how='left')

# CLOSE: the last pre-kickoff print (the market's final pre-game consensus). This is the fair
# comparison point for a PRE-GAME strategy — using a terminal in-play price would be degenerate.
close = pre.groupby('symbol').agg(p_close=('price', 'last')).reset_index()

e = (ent.merge(close, on='symbol')
        .merge(mk[['slug', 'won0', 'gst', 'event', 'league']], left_on='symbol',
               right_on='slug', how='inner'))
fav0 = e.p_raw > 0.5
e['p0'] = np.where(fav0, e.p_raw, 1 - e.p_raw)
e['close'] = np.where(fav0, e.p_close, 1 - e.p_close)
e['win'] = np.where(fav0, e.won0, 1 - e.won0)
e['half'] = e.roll / 2
e['day'] = e.t_entry.dt.date
e = e[(e.p0 >= FB.BAND_LO) & (e.p0 <= FB.BAND_HI)]
e = e[(e.n_pre >= FB.MIN_PREGAME_TRADES) & e.half.notna()].copy()
days = sorted(e.day.unique())
print(f"entries {len(e):,} | events {e.event.nunique():,} | days {len(days)} | cutoff {CUTOFF}m")


def net(sub, seed=51, n=4000):
    if len(sub) < 40:
        return np.nan, np.nan, np.nan, 0
    p = sub.p0.values
    cost = sub.half.values + FEE * p * (1 - p)
    turn = p + cost
    g = pd.DataFrame({'a': sub.win.values - turn, 't': turn, 'ev': sub.event.values}) \
        .groupby('ev').agg(s=('a', 'sum'), c=('t', 'sum'))
    a, c = g.s.values, g.c.values
    k = len(a)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, k, size=(n, k))
    b = a[idx].sum(1) / c[idx].sum(1)
    return a.sum() / c.sum(), np.percentile(b, 2.5), np.percentile(b, 97.5), k


print("\n" + "=" * 96)
print("BAR 1 — WALK-FORWARD (4 expanding folds, each test block strictly later)")
folds = [(0, 9, 12), (0, 12, 15), (0, 15, 18), (0, 18, 21)]
pooled_a, pooled_t, pooled_ev = [], [], []
ok = True
for i, (a0, a1, a2) in enumerate(folds, 1):
    test = e[e.day.isin(days[a1:a2])]
    r, lo, hi, k = net(test)
    if k == 0:
        print(f"  fold {i}: test days {a1}-{a2} — too thin"); continue
    flag = "" if r > 0 else "   <-- NEGATIVE FOLD"
    ok &= (r > 0)
    print(f"  fold {i}: train d0-{a1}, TEST d{a1}-{a2}  net {r*100:>+6.2f}% "
          f"[{lo*100:>+6.2f},{hi*100:>+6.2f}] ev={k:>4}{flag}")
    p = test.p0.values
    cost = test.half.values + FEE * p * (1 - p)
    pooled_a.append(test.win.values - (p + cost)); pooled_t.append(p + cost)
    pooled_ev.append(test.event.values)
allt = pd.DataFrame({'a': np.concatenate(pooled_a), 't': np.concatenate(pooled_t),
                     'ev': np.concatenate(pooled_ev)})
g = allt.groupby('ev').agg(s=('a', 'sum'), c=('t', 'sum'))
a, c = g.s.values, g.c.values
rng = np.random.default_rng(99)
idx = rng.integers(0, len(a), size=(4000, len(a)))
b = a[idx].sum(1) / c[idx].sum(1)
plo, phi = np.percentile(b, [2.5, 97.5])
proi = a.sum() / c.sum()
print(f"  POOLED out-of-time: {proi*100:+.2f}% [{plo*100:+.2f},{phi*100:+.2f}] ev={len(a):,}")
bar1 = plo > 0 and ok
print(f"  BAR 1: {'PASS' if bar1 else 'FAIL'}  (pooled LB>0 and no negative fold)")

print("\n" + "=" * 96)
print("BAR 2 — LAMBDA (CLV / surplus): does the market move TOWARD the pick before kickoff?")
s = e[e.close.notna()].copy()
cov = len(s) / len(e)
s['surplus'] = s.win - s.p0
s['clv'] = s.close - s.p0
tot_s, tot_c = s.surplus.sum(), s.clv.sum()
lam = tot_c / tot_s if tot_s else np.nan
gg = s.groupby('event').agg(sv=('surplus', 'sum'), cv=('clv', 'sum'))
sv, cv = gg.sv.values, gg.cv.values
rng = np.random.default_rng(7)
idx = rng.integers(0, len(sv), size=(4000, len(sv)))
lb = cv[idx].sum(1) / np.where(sv[idx].sum(1) == 0, np.nan, sv[idx].sum(1))
llo, lhi = np.nanpercentile(lb, [2.5, 97.5])
print(f"  trajectory coverage: {cov*100:.1f}%   events {len(sv):,}")
print(f"  mean surplus {s.surplus.mean()*100:+.2f}pp | mean CLV {s.clv.mean()*100:+.2f}pp")
print(f"  LAMBDA = {lam:.3f}  CI [{llo:.3f}, {lhi:.3f}]")
bar2 = llo > 0 and cov >= 0.5
print(f"  BAR 2: {'PASS' if bar2 else 'FAIL'}")
print("  READ: lambda>0 means the market confirms us before kickoff (information).")
print("        lambda~0 with positive surplus = a RISK PREMIUM harvested at settlement.")
print("        For a favourite-longshot harvester, ~0 is EXPECTED, not disqualifying —")
print("        but it does mean the whole return is variance-borne, so drawdowns are real.")

print("\n" + "=" * 96)
print("BAR 3 — BRIER: does a calibration-corrected probability beat the raw market price OOS?")
# fit the gap on an EARLIER block, apply to a LATER one. No in-sample correction.
res = []
for i, (a0, a1, a2) in enumerate(folds, 1):
    tr = e[e.day.isin(days[:a1])]
    te = e[e.day.isin(days[a1:a2])]
    if len(tr) < 200 or len(te) < 100:
        continue
    gap = (tr.win - tr.p0).mean()                    # learned on the past only
    q = np.clip(te.p0.values + gap, 1e-6, 1 - 1e-6)  # corrected probability
    bm = np.mean((te.p0.values - te.win.values) ** 2)
    bo = np.mean((q - te.win.values) ** 2)
    res.append((i, gap, bm, bo))
    print(f"  fold {i}: learned gap {gap*100:+.2f}pp | market Brier {bm:.5f} | "
          f"ours {bo:.5f} | {'BEAT' if bo < bm else 'lost'}")
bar3 = len(res) > 0 and sum(1 for r in res if r[3] < r[2]) > len(res) / 2
if res:
    mb = np.mean([r[2] for r in res]); ob = np.mean([r[3] for r in res])
    print(f"  mean across folds: market {mb:.5f} vs ours {ob:.5f}")
print(f"  BAR 3: {'PASS' if bar3 else 'FAIL'}")

print("\n" + "=" * 96)
r4, lo4, hi4, k4 = net(e)
bar4 = lo4 > 0
print(f"BAR 4 — REALIZABLE: {r4*100:+.2f}% [{lo4*100:+.2f},{hi4*100:+.2f}] ev={k4:,}  "
      f"{'PASS' if bar4 else 'FAIL'}")

print("\n" + "=" * 96)
n = sum([bar1, bar2, bar3, bar4])
print(f"STANDING CERTIFICATION: {n}/4 bars.  "
      f"{'CERTIFIED' if n == 4 else 'NOT CERTIFIED — k=0'}")
for i, (nm, v) in enumerate([("walk-forward", bar1), ("lambda", bar2),
                             ("Brier-beat", bar3), ("realizable", bar4)], 1):
    print(f"  {i}. {nm:<14} {'PASS' if v else 'FAIL'}")
