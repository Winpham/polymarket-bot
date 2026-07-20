"""Tue's question: markets change — should we use LESS history and weight recency?

The principle is right in general. Here it is testable, and there is a hard tension:
  - if the gap DRIFTS, recency-weighting is correct and pooling 21 days is wrong
  - if the gap is STABLE, recency-weighting throws away the one thing we are shortest of: POWER
    (H2 already fails only because 10 days cannot resolve it)

So: measure drift directly, then price what shortening the window would actually cost.
"""
import sys, numpy as np, pandas as pd
sys.path.insert(0, '/Users/tuepham/polymarket-bot/wt/favband/scripts')
import favband as FB

FEE = FB.FEE_RATE
e = FB.build_entries()
s = FB.apply_strategy(e)
s = s.sort_values('day').copy()
days = sorted(s.day.unique())
print(f"\nstrategy entries {len(s):,} | events {s.event.nunique():,} | days {len(days)}")


def net(sub, seed=31, n=3000):
    if len(sub) < 40:
        return np.nan, np.nan, np.nan, 0
    p = sub.p0.values
    cost = sub.half.values + FEE * p * (1 - p)
    turn = p + cost
    g = pd.DataFrame({"p": sub.win.values - turn, "t": turn, "ev": sub.event.values}) \
        .groupby("ev").agg(s=("p", "sum"), c=("t", "sum"))
    a, c = g.s.values, g.c.values
    k = len(a)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, k, size=(n, k))
    b = a[idx].sum(1) / c[idx].sum(1)
    return a.sum() / c.sum(), np.percentile(b, 2.5), np.percentile(b, 97.5), k


print("\n" + "=" * 92)
print("(1) DAY-BY-DAY calibration gap — is there visible drift?")
rows = []
for d in days:
    sd = s[s.day == d]
    if len(sd) < 30:
        continue
    gap = (sd.win - sd.p0).mean()
    rows.append((d, len(sd), sd.event.nunique(), gap))
for d, n, k, gap in rows:
    bar = "#" * max(int(abs(gap) * 400), 0)
    print(f"  {d}  n={n:>5,} ev={k:>4}  gap {gap*100:>+6.2f}pp  {'+' if gap>=0 else '-'}{bar}")

g = np.array([r[3] for r in rows])
w = np.array([r[2] for r in rows], dtype=float)
x = np.arange(len(g), dtype=float)
print(f"\n  daily gaps: mean {g.mean()*100:+.2f}pp  sd {g.std(ddof=1)*100:.2f}pp  "
      f"positive on {int((g>0).sum())}/{len(g)} days")

print("\n" + "=" * 92)
print("(2) TREND TEST — is the gap systematically declining? (event-weighted OLS + block boot)")
slope = np.polyfit(x, g, 1, w=w)[0]
rng = np.random.default_rng(7)
sl = []
for _ in range(4000):
    pick = rng.integers(0, len(g), len(g))
    if len(set(pick.tolist())) < 3:
        continue
    sl.append(np.polyfit(x[pick], g[pick], 1, w=w[pick])[0])
sl = np.array(sl)
lo, hi = np.percentile(sl, [2.5, 97.5])
print(f"  slope {slope*100:+.4f}pp/day   95% CI [{lo*100:+.4f}, {hi*100:+.4f}]")
print(f"  -> {'DRIFT DETECTED' if (lo>0 or hi<0) else 'NO detectable drift (CI spans 0)'}")
print(f"  over the whole 21-day window that trend implies "
      f"{slope*len(g)*100:+.2f}pp of total change")

print("\n" + "=" * 92)
print("(3) WHAT WOULD SHORTENING THE WINDOW COST? (recency vs power)")
print(f'{"window":>16} {"days":>5} {"events":>7} {"net":>9} {"95% CI":>20} {"CI width":>9}')
for lab, k in [("last 5 days", 5), ("last 7 days", 7), ("last 10 days", 10),
               ("last 14 days", 14), ("ALL days", len(days))]:
    keep = set(days[-k:])
    sub = s[s.day.isin(keep)]
    r, l, h, ev = net(sub)
    if ev == 0:
        continue
    print(f'{lab:>16} {k:>5} {ev:>7,} {r*100:>+8.2f}% '
          f'[{l*100:>+7.2f},{h*100:>+7.2f}] {(h-l)*100:>8.2f}pp')

print("\n" + "=" * 92)
print("(4) EXPONENTIAL RECENCY WEIGHTING — does it change the answer?")
idx = {d: i for i, d in enumerate(days)}
s["age"] = s.day.map(lambda d: len(days) - 1 - idx[d])
for hl in (3, 5, 10, 1e9):
    wt = 0.5 ** (s.age / hl)
    p = s.p0.values
    cost = s.half.values + FEE * p * (1 - p)
    turn = p + cost
    pnl = s.win.values - turn
    roi = (pnl * wt).sum() / (turn * wt).sum()
    lab = "no weighting" if hl > 1e8 else f"half-life {hl:.0f}d"
    print(f"  {lab:>16}: net {roi*100:+.2f}%")

print("\n" + "=" * 92)
print("(5) IS THE *GAP* ITSELF STATIONARY? (variance ratio: real drift vs sampling noise)")
# If daily gaps were pure sampling noise around a constant, their variance would be ~ the
# average within-day sampling variance. Excess variance = genuine regime movement.
within = []
for d, n, k, gap in rows:
    sd = s[s.day == d]
    ev = sd.groupby("event").apply(lambda t: (t.win - t.p0).mean())
    if len(ev) > 2:
        within.append(ev.var(ddof=1) / len(ev))
exp_var = np.mean(within)
obs_var = g.var(ddof=1)
print(f"  observed variance of daily gaps : {obs_var*1e4:.3f} (pp^2)")
print(f"  expected from sampling alone    : {exp_var*1e4:.3f} (pp^2)")
print(f"  variance ratio                  : {obs_var/exp_var:.2f}")
print("  ratio ~1 => daily swings are pure noise; the gap is STATIONARY and pooling is correct.")
print("  ratio >>1 => genuine regime movement; recency-weighting is justified.")
