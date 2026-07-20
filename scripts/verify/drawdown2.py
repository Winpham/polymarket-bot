"""DRAWDOWN, corrected — and the constraint that actually decides everything.

The first attempt compounded each bet SEQUENTIALLY on the full bankroll and produced 35x-462,986x.
That is not a result, it is a bug: ~49 events fire per day CONCURRENTLY. You size them all before
any resolves. Correct model: each of the day's N events gets f of bankroll, so

    daily return = f * sum(returns of that day's events)

and total deployment f*N must be <= 1 or you are levered.

Then the second, larger correction: percentage compounding assumes you can always deploy the
bankroll. You cannot. Capacity is fixed in DOLLARS by book depth, so as the bankroll grows the
deployable fraction falls and returns become LINEAR, not exponential.
"""
import sys, numpy as np, pandas as pd
sys.path.insert(0, '/Users/tuepham/polymarket-bot/wt/favband/scripts')
import favband as FB

FEE = FB.FEE_RATE
CUTOFF = 10.0

mk = FB.load_markets()
ts = FB.load_trades()
j = ts.merge(mk[['slug', 'gst']], left_on='symbol', right_on='slug', how='inner')
pre = j[j.tt < j.gst].copy()
pre['lead'] = (pre.gst - pre.tt).dt.total_seconds() / 60
pre = pre.sort_values('tt')
src = pre[pre.lead >= CUTOFF]
ent = src.groupby('symbol').agg(p_raw=('price', 'last'), n_pre=('price', 'size'),
                                t_entry=('tt', 'last')).reset_index()
rs = src.groupby('symbol').price.apply(lambda g: FB.roll_spread(g.values)).rename('roll')
ent = ent.merge(rs, left_on='symbol', right_index=True, how='left')
e = ent.merge(mk[['slug', 'won0', 'gst', 'event']], left_on='symbol', right_on='slug', how='inner')
fav0 = e.p_raw > 0.5
e['p0'] = np.where(fav0, e.p_raw, 1 - e.p_raw)
e['win'] = np.where(fav0, e.won0, 1 - e.won0)
e['half'] = e.roll / 2
e['day'] = e.t_entry.dt.date
e = e[(e.p0 >= FB.BAND_LO) & (e.p0 <= FB.BAND_HI)]
e = e[(e.n_pre >= FB.MIN_PREGAME_TRADES) & e.half.notna()].copy()
ev = e.sort_values('t_entry').groupby('event').agg(
    p0=('p0', 'first'), win=('win', 'first'), half=('half', 'first'), day=('day', 'first'))
ev['stake'] = ev.p0 + ev.half + FEE * ev.p0 * (1 - ev.p0)
ev['ret'] = (ev.win - ev.stake) / ev.stake

days = sorted(ev.day.unique())
by_day = [ev[ev.day == d].ret.values for d in days]
n_per_day = np.array([len(x) for x in by_day])
print(f"events {len(ev):,} | days {len(days)} | events/day median {np.median(n_per_day):.0f}")
print(f"per-bet: mean {ev.ret.mean()*100:+.2f}%  sd {ev.ret.std()*100:.1f}%  "
      f"win {ev.win.mean():.4f}")

daysum = np.array([x.sum() for x in by_day])
daymean = np.array([x.mean() for x in by_day])
print(f"per-day SUM of returns: mean {daysum.mean():+.3f}  sd {daysum.std():.3f}")
print(f"  (this is what a f-per-bet strategy multiplies by; NOT the per-bet mean)")

rng = np.random.default_rng(3)


def sim_pct(f, n_days=250, sims=4000, cap=1.0):
    """CONCURRENT within-day allocation. f per event, capped so total deployment <= cap."""
    out, dd_out, ruin = [], [], 0
    for _ in range(sims):
        eq, peak, dd = 1.0, 1.0, 0.0
        idx = rng.integers(0, len(days), n_days)
        for i in idx:
            n = n_per_day[i]
            f_eff = min(f, cap / max(n, 1))       # cannot deploy more than the bankroll
            eq *= (1 + f_eff * daysum[i])
            if eq <= 0.01:
                ruin += 1
                break
            peak = max(peak, eq)
            dd = max(dd, 1 - eq / peak)
        out.append(eq)
        dd_out.append(dd)
    a = np.array(out)
    return np.median(a), np.percentile(a, 5), np.median(dd_out), np.percentile(dd_out, 95), ruin / sims


print("\n" + "=" * 96)
print("CORRECTED PERCENTAGE COMPOUNDING (concurrent, deployment capped at 100% of bankroll)")
print(f"{'f per event':>13} {'median x':>10} {'p5':>9} {'med maxDD':>11} {'p95 maxDD':>11} {'ruin':>7}")
for lab, f in [("2.0%", 0.020), ("1.0%", 0.010), ("0.5%", 0.005), ("0.25%", 0.0025)]:
    med, p5, mdd, p95dd, ru = sim_pct(f)
    print(f"{lab:>13} {med:>10.2f} {p5:>9.2f} {mdd*100:>10.1f}% {p95dd*100:>10.1f}% {ru*100:>6.1f}%")
print("\n  These are still enormous — because a +1.7%/bet edge compounded daily IS enormous.")
print("  That is the tell: if this were deployable at scale it would not exist. Capacity binds.")

print("\n" + "=" * 96)
print("THE CONSTRAINT THAT ACTUALLY BINDS — capacity is fixed in DOLLARS, so returns go LINEAR")
print("  Depth measured on the tradeable (<=1c) band book: order $10^2, not $10^5.")
for stake in (50, 100, 250):
    daily_profit = stake * n_per_day.mean() * ev.ret.mean()
    print(f"\n  ${stake}/event, {n_per_day.mean():.0f} events/day:")
    print(f"    profit/day        ${daily_profit:>8,.2f}")
    print(f"    profit/year (250d) ${daily_profit*250:>8,.0f}   <- LINEAR, not compounding")
    sd_day = stake * daysum.std()
    print(f"    daily P&L sd      ${sd_day:>8,.2f}   worst observed day "
          f"${stake*daysum.min():>8,.2f}")

print("\n" + "=" * 96)
print("HOW BAD DOES IT GET? (fixed dollar stake, day-block bootstrap, 250 days)")
STAKE = 50.0
sims, mdd_list, worst = 4000, [], []
for _ in range(sims):
    idx = rng.integers(0, len(days), 250)
    pnl = STAKE * daysum[idx]
    eq = np.cumsum(pnl)
    peak = np.maximum.accumulate(np.maximum(eq, 0))
    dd = peak - eq
    mdd_list.append(dd.max())
    worst.append(eq[-1])
mdd_list, worst = np.array(mdd_list), np.array(worst)
print(f"  ${STAKE:.0f}/event, 250 days:")
print(f"    median year-end profit  ${np.median(worst):>9,.0f}")
print(f"    5th percentile          ${np.percentile(worst,5):>9,.0f}")
print(f"    prob of a LOSING year   {(worst<0).mean()*100:>8.1f}%")
print(f"    median max drawdown     ${np.median(mdd_list):>9,.0f}")
print(f"    95th pct max drawdown   ${np.percentile(mdd_list,95):>9,.0f}")
print(f"    => you must be able to sit through a ${np.percentile(mdd_list,95):,.0f} "
      f"drawdown on a ~$2,200 bankroll")

print("\n" + "=" * 96)
print("STATISTICAL HONESTY")
t = daymean.mean() / (daymean.std() / np.sqrt(len(daymean)))
print(f"  daily mean per-bet return {daymean.mean()*100:+.2f}%  t = {t:.2f} on {len(daymean)} days")
print(f"  5 of {len(daymean)} days negative; worst day {daymean.min()*100:+.2f}%")
print(f"  A t of {t:.2f} on 21 correlated days is NOT 'full confidence'. It is suggestive.")
