"""What does +1.33% ROI-on-turnover actually PAY?

ROI-on-turnover is per dollar STAKED, per bet. Converting it to a business requires three more
numbers the headline hides:
   1. how many bets per day (signal supply)
   2. how much capital is tied up at once (the bankroll, not the turnover)
   3. how fast capital recycles (hold time)

Daily return on bankroll = turnover_per_day x ROI_on_turnover / bankroll.

The correlated unit is the EVENT, not the submarket: a game bundles many submarkets whose outcomes
move together, so staking each one separately is leverage, not diversification.
"""
import sys, numpy as np, pandas as pd
sys.path.insert(0, '/Users/tuepham/polymarket-bot/wt/favband/scripts')
import favband as FB

FEE = FB.FEE_RATE
e = FB.build_entries()
s = FB.apply_strategy(e).sort_values('t_entry').copy()
days = sorted(s.day.unique())
n_days = len(days)

roi, lo, hi, k = FB.net_of_cost(s)
print(f"\nstrategy: {len(s):,} submarket entries | {k:,} EVENTS | {n_days} days")
print(f"net ROI-on-turnover {roi*100:+.2f}%  CI [{lo*100:+.2f}, {hi*100:+.2f}]")

# ---------------------------------------------------------------- signal supply
ev_per_day = s.groupby('day').event.nunique()
sub_per_day = s.groupby('day').size()
print("\n" + "=" * 86)
print("(1) SIGNAL SUPPLY")
print(f"  events/day  : median {ev_per_day.median():.0f}  mean {ev_per_day.mean():.1f}  "
      f"min {ev_per_day.min()}  max {ev_per_day.max()}")
print(f"  submarkets/day: median {sub_per_day.median():.0f}  mean {sub_per_day.mean():.1f}")
print(f"  submarkets per event: {len(s)/k:.1f}  <- staking each is CORRELATED risk, not diversification")

# ---------------------------------------------------------------- capital tied up
# exposure runs from entry until the game resolves. No US resolution timestamps exist, so use
# gameStart + a sport-typical duration. Flagged as an assumption, not a measurement.
HOLD_H = 3.0
s['t_out'] = s.gst + pd.Timedelta(hours=HOLD_H)

print("\n" + "=" * 86)
print(f"(2) CAPITAL AT RISK  (hold = gameStart + {HOLD_H}h — ASSUMED, not measured)")

for STAKE, unit in [(50.0, 'event'), (50.0, 'submarket')]:
    if unit == 'event':
        # one stake per event, entered at the first qualifying submarket
        pos = s.groupby('event').agg(t_in=('t_entry', 'min'), t_out=('t_out', 'max'))
    else:
        pos = s[['t_entry', 't_out']].rename(columns={'t_entry': 't_in'})
    ev_in = pd.DataFrame({'t': pos.t_in, 'd': STAKE})
    ev_out = pd.DataFrame({'t': pos.t_out, 'd': -STAKE})
    tl = pd.concat([ev_in, ev_out]).sort_values('t')
    tl['open'] = tl.d.cumsum()
    peak = tl.open.max()
    turnover = STAKE * len(pos)
    per_day = turnover / n_days
    profit = turnover * roi
    print(f"\n  ${STAKE:.0f} per {unit.upper():<10} : {len(pos):,} positions")
    print(f"    turnover total      ${turnover:>12,.0f}   per day ${per_day:>10,.0f}")
    print(f"    PEAK capital at risk ${peak:>11,.0f}   <- this is the bankroll you must hold")
    print(f"    profit over {n_days}d     ${profit:>12,.0f}   per day ${profit/n_days:>10,.0f}")
    print(f"    daily return on bankroll: {profit/n_days/peak*100:>6.2f}%")
    print(f"    over {n_days}d on bankroll : {profit/peak*100:>6.2f}%")
    lo_p, hi_p = turnover * lo, turnover * hi
    print(f"    CI on total profit   ${lo_p:>+11,.0f} .. ${hi_p:>+,.0f}"
          f"   ({lo_p/peak*100:+.1f}% .. {hi_p/peak*100:+.1f}% of bankroll)")

# ---------------------------------------------------------------- recycling
print("\n" + "=" * 86)
print("(3) CAPITAL RECYCLING")
pos = s.groupby('event').agg(t_in=('t_entry', 'min'), t_out=('t_out', 'max'))
span_h = (s.t_entry.max() - s.t_entry.min()).total_seconds() / 3600
hold_h = (pos.t_out - pos.t_in).dt.total_seconds().mean() / 3600
print(f"  mean hold: {hold_h:.1f}h  => theoretical recycles/day: {24/hold_h:.1f}x")
print(f"  actual turnover multiple (turnover/day ÷ peak capital): "
      f"{(50.0*len(pos)/n_days) / max(tl.open.max(),1):.2f}x/day")

# ---------------------------------------------------------------- the honest annualisation
print("\n" + "=" * 86)
print("(4) WHAT IT WOULD PAY — one stake per EVENT, the correct correlated unit")
pos_ev = s.groupby('event').agg(t_in=('t_entry', 'min'), t_out=('t_out', 'max'))
for STAKE in (50, 100, 250):
    ev_in = pd.DataFrame({'t': pos_ev.t_in, 'd': float(STAKE)})
    ev_out = pd.DataFrame({'t': pos_ev.t_out, 'd': -float(STAKE)})
    tl2 = pd.concat([ev_in, ev_out]).sort_values('t')
    tl2['open'] = tl2.d.cumsum()
    peak = tl2.open.max()
    turn = STAKE * len(pos_ev)
    prof_d = turn * roi / n_days
    print(f"  ${STAKE:>3}/event -> bankroll ${peak:>8,.0f} | "
          f"profit ${prof_d:>7,.1f}/day (${turn*lo/n_days:>7,.1f} .. ${turn*hi/n_days:>6,.1f}) | "
          f"{prof_d/peak*100:>5.2f}%/day on bankroll")
print("\n  NOTE: these scale linearly in stake ONLY while the book can absorb it. Depth per")
print("  signal is still being measured — at $250 you are likely walking the book.")
