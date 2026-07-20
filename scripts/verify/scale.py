"""Can this scale? Two separable questions:

  A. SUPPLY  — are there more events in NFL/NBA season than in our summer trough? MEASURABLE:
               us_markets.parquet spans Oct 2025 -> Jul 2026, covering full NFL and NBA seasons.
  B. EDGE    — does the favourite-band mispricing SURVIVE in those leagues? NOT measurable here:
               we only have tape (prices) for 21 summer days. Supply is not profit.

Also checks the uncomfortable possibility: the biggest, most liquid markets are the SHARPEST, and
favourite-longshot bias is classically largest in thin/retail-heavy books. More volume could mean
less edge per bet.
"""
import sys, re, numpy as np, pandas as pd
sys.path.insert(0, '/Users/tuepham/polymarket-bot/wt/favband/scripts')
import favband as FB

MK = FB.MK
EVENT_RE = FB.EVENT_RE

d = pd.read_parquet(MK)
d = d[d.closed.astype(str) == 'True'].copy()
d['gst'] = pd.to_datetime(d.gameStartTime, errors='coerce', utc=True)
d = d.dropna(subset=['gst'])
d['event'] = d.slug.map(FB.event_key)
d['league'] = d.event.str.split('-').str[0]
d['month'] = d.gst.dt.to_period('M')
d['day'] = d.gst.dt.date

print("=" * 96)
print("(A) SUPPLY — distinct EVENTS per day, by league, across the whole year")
big = ['nfl', 'nba', 'mlb', 'nhl', 'cbb', 'cfb', 'fwc', 'atp', 'wta', 'ufc', 'mls', 'wnba']
piv = (d[d.league.isin(big)]
       .groupby(['month', 'league']).event.nunique().unstack(fill_value=0))
# events per DAY in that month
days_in = d.groupby('month').day.nunique()
piv_pd = piv.div(days_in, axis=0).round(1)
print("\nEVENTS PER DAY by month:")
print(piv_pd.to_string())

print("\n" + "=" * 96)
print("(B) OUR WINDOW vs THE REST OF THE YEAR")
win_lo, win_hi = pd.Timestamp('2026-06-23', tz='UTC'), pd.Timestamp('2026-07-13', tz='UTC')
inwin = d[(d.gst >= win_lo) & (d.gst <= win_hi)]
outwin = d[(d.gst < win_lo)]
print(f"  our 21-day window : {inwin.event.nunique():,} events "
      f"({inwin.event.nunique()/21:.1f}/day)")
nd = outwin.day.nunique()
print(f"  Oct25-Jun26 rest  : {outwin.event.nunique():,} events over {nd} days "
      f"({outwin.event.nunique()/max(nd,1):.1f}/day)")
print(f"  => the rest of the year runs "
      f"{(outwin.event.nunique()/max(nd,1)) / (inwin.event.nunique()/21):.2f}x our window's rate")

print("\n  league mix — our window vs the rest:")
a = inwin.league.value_counts(normalize=True).head(8) * 100
b = outwin.league.value_counts(normalize=True)
print(f"  {'league':>8} {'window %':>10} {'rest %':>9}")
for lg in a.index:
    print(f"  {lg:>8} {a[lg]:>9.1f}% {b.get(lg,0)*100:>8.1f}%")

print("\n" + "=" * 96)
print("(C) PEAK SEASON — busiest months and what a full-season day looks like")
tot = d.groupby('month').event.nunique()
per = (tot / days_in).round(1).sort_values(ascending=False)
print("  events/day by month (all leagues, top 8):")
for m, v in per.head(8).items():
    print(f"    {m}: {v:>6.1f} events/day")
print(f"\n  our window: {inwin.event.nunique()/21:.1f} events/day")
print(f"  best month: {per.max():.1f} events/day  ({per.idxmax()})")
print(f"  => headroom on SUPPLY alone: {per.max()/(inwin.event.nunique()/21):.1f}x")

print("\n" + "=" * 96)
print("(D) THE CATCH — does the edge hold where the volume is?")
print("    Measured in OUR window only (the only period with prices):")
e = FB.build_entries()
s = FB.apply_strategy(e)
s = s.assign(league=s.event.str.split('-').str[0])
print(f"    {'league':>8} {'events':>8} {'net':>9} {'95% CI':>20}")
for lg in s.league.value_counts().head(8).index:
    sub = s[s.league == lg]
    if sub.event.nunique() < 40:
        continue
    r, lo, hi, k = FB.net_of_cost(sub)
    star = '*' if lo > 0 else ' '
    print(f"    {lg:>8} {k:>8,} {r*100:>+8.2f}% [{lo*100:>+7.2f},{hi*100:>+7.2f}]{star}")

print("\n  NOTE: mlb is the only major US league in our window with real volume, and it is the")
print("  WEAKEST major cell. NFL/NBA are the sharpest, highest-volume US books in existence.")
print("  Favourite-longshot bias is classically LARGEST in thin, retail-heavy markets.")
print("  So supply headroom is real and measurable; edge transfer to NFL/NBA is NOT established")
print("  and the prior should be that it is SMALLER there, not larger.")
