"""THE LOOKAHEAD TEST — is FAVBAND's entry price actually obtainable?

FAVBAND defines entry as "the LAST trade before gameStartTime". At decision time you do not know
which trade will turn out to be last. Picking it is retrospective selection: it systematically
lands you at the moment closest to kickoff, after all pre-game information has arrived.

A live strategy must commit at a FIXED time: "trade at the best price available as of T minutes
before start". That is implementable. This measures the difference.

If the edge only exists at the un-knowable last print, it is not an edge.
"""
import sys, numpy as np, pandas as pd, glob
sys.path.insert(0, '/Users/tuepham/polymarket-bot/wt/favband/scripts')
import favband as FB

FEE = FB.FEE_RATE
MK, TS = FB.MK, sorted(glob.glob(FB.TS_GLOB))

mk = FB.load_markets()
ts = FB.load_trades()
m = ts.merge(mk[['slug', 'gst']], left_on='symbol', right_on='slug', how='inner')
m = m[m.tt < m.gst].copy()
m['lead'] = (m.gst - m.tt).dt.total_seconds() / 60
m = m.sort_values('tt')

meta = mk[['slug', 'won0', 'gst', 'event', 'league']]


def build_at(cutoff_min):
    """Entry = last trade at least `cutoff_min` before kickoff. cutoff=0 reproduces the
    original (lookahead) definition."""
    sub = m[m.lead >= cutoff_min]
    ent = sub.groupby('symbol').agg(p_raw=('price', 'last'), n_pre=('price', 'size'),
                                    vol=('qty', 'sum'), t_entry=('tt', 'last')).reset_index()
    rs = sub.groupby('symbol').price.apply(lambda g: FB.roll_spread(g.values)).rename('roll')
    ent = ent.merge(rs, left_on='symbol', right_index=True, how='left')
    e = ent.merge(meta, left_on='symbol', right_on='slug', how='inner')
    fav0 = e.p_raw > 0.5
    e['p0'] = np.where(fav0, e.p_raw, 1 - e.p_raw)
    e['win'] = np.where(fav0, e.won0, 1 - e.won0)
    e['half'] = e.roll / 2
    e['day'] = e.t_entry.dt.date
    e = e[(e.p0 >= FB.BAND_LO) & (e.p0 <= FB.BAND_HI)]
    e = e[(e.n_pre >= FB.MIN_PREGAME_TRADES) & e.half.notna()]
    return e.copy()


def net(sub, seed=41, n=4000):
    if len(sub) < 50:
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


print("=" * 100)
print("ENTRY-TIME LOOKAHEAD TEST")
print("  cutoff = commit at the last price available at least X minutes before kickoff.")
print("  X=0 is the ORIGINAL definition and is NOT live-implementable.")
print()
print(f'{"cutoff":>10} {"entries":>9} {"events":>8} {"mean px":>9} {"gap pp":>9} {"net":>9} '
      f'{"95% CI":>20}')
rows = []
for cut in [0, 1, 2, 5, 10, 15, 30, 60]:
    e = build_at(cut)
    if len(e) < 100:
        print(f'{cut:>8}m  (too thin: {len(e)})')
        continue
    r, lo, hi, k = net(e)
    gap = (e.win - e.p0).mean()
    star = '*' if lo > 0 else ' '
    rows.append((cut, r, lo, k))
    print(f'{cut:>8}m {len(e):>9,} {k:>8,} {e.p0.mean():>9.4f} {gap*100:>+9.2f} '
          f'{r*100:>+8.2f}% [{lo*100:>+7.2f},{hi*100:>+7.2f}]{star}')

print()
print("=" * 100)
print("INTERPRETATION")
if rows:
    base = rows[0]
    live = [r for r in rows if r[0] >= 5]
    if live:
        best = max(live, key=lambda r: r[1])
        print(f"  lookahead entry (0m) : {base[1]*100:+.2f}%  LB {base[2]*100:+.2f}")
        print(f"  live-implementable   : "
              + ", ".join(f"{r[0]}m {r[1]*100:+.2f}% (LB {r[2]*100:+.2f})" for r in live))
        print()
        drop = base[1] - best[1]
        print(f"  edge lost to removing the lookahead: {drop*100:+.2f}pp "
              f"({drop/base[1]*100:.0f}% of the headline)" if base[1] else "")
        if all(r[2] <= 0 for r in live):
            print("  => NO live-implementable cutoff has LB>0. The edge depends on an entry")
            print("     you cannot actually take. THIS IS FATAL until shown otherwise.")
        else:
            ok = [r for r in live if r[2] > 0]
            print(f"  => survives at cutoffs: {[f'{r[0]}m' for r in ok]}")
