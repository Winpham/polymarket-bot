#!/usr/bin/env python3
"""Phase C backtest: does the consensus OUTCOME win more than its entry price implied?

Mirrors the Rust engine's gates (net-directional, drop two-sided MM wallets,
price-coherence, min backers) but DROPS the freshness gate (we want resolved
markets). Resolution via Gamma outcomePrices[outcome_index] == 1.0.

Honest metric: edge = hit_rate - mean_entry_price (market-implied prob).
"""
import json, urllib.request, time, collections, statistics, sys

DATA="https://data-api.polymarket.com"; GAMMA="https://gamma-api.polymarket.com"
def get(u):
    for _ in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"bt/1"}),timeout=20) as r:
                return json.load(r)
        except Exception:
            time.sleep(0.4)
    return None

MIN_BACKERS=3; MAX_OPPOSERS=1; MAX_PSTD=0.10

# 1. universe (union top-50 across periods, like the bot but wider for sample size)
uni={}
for p in ("DAY","WEEK","MONTH","ALL"):
    for e in (get(f"{DATA}/v1/leaderboard?timePeriod={p}&limit=50") or []):
        w=e["proxyWallet"]; rk=int(e.get("rank",999))
        if w not in uni or rk<uni[w]["rank"]:
            uni[w]={"name":e.get("userName") or w[:8],"rank":rk}
print(f"universe={len(uni)} traders", file=sys.stderr)

# 2. pull each trader's available history (most-recent 500), key by market.
mkt=collections.defaultdict(lambda: collections.defaultdict(list))  # cond -> oidx -> votes
meta={}
for i,(w,m) in enumerate(uni.items()):
    acts=get(f"{DATA}/activity?user={w}&type=TRADE&limit=500"); time.sleep(0.08)
    if not acts: continue
    for a in acts:
        if a.get("side")!="BUY": continue
        cond=a.get("conditionId"); oidx=a.get("outcomeIndex")
        if cond is None or oidx is None: continue
        pr=a.get("price")
        if not pr or not (0<pr<1): continue
        mkt[cond][oidx].append({"w":w,"price":pr,"usd":a.get("usdcSize",0) or 0,"ts":a.get("timestamp",0)})
        meta[cond]={"title":a.get("title","?"),"slug":a.get("slug",""),
                    "outcomes":meta.get(cond,{}).get("outcomes",{})}
        meta[cond]["outcomes"][oidx]=a.get("outcome",str(oidx))
    if (i+1)%30==0: print(f"  polled {i+1}",file=sys.stderr)

def is_sports(t,s):
    s=(s+" "+t).lower()
    return any(p in s for p in ["fifwc","nba-","nfl-","mlb-","nhl-"," vs","spread:","o/u ","win on 20","-cs2-","lol-"])

# 3. build consensus signals (net-directional, drop two-sided), score price-coherence
sigs=[]
for cond,book in mkt.items():
    wallet_outs=collections.defaultdict(set)
    for o,vs in book.items():
        for v in vs: wallet_outs[v["w"]].add(o)
    two_sided={w for w,os in wallet_outs.items() if len(os)>1}
    for oidx,vs in book.items():
        backers={v["w"] for v in vs if v["w"] not in two_sided}
        if len(backers)<MIN_BACKERS: continue
        opp={v["w"] for o2,vs2 in book.items() if o2!=oidx for v in vs2 if v["w"] not in two_sided}
        if len(opp)>MAX_OPPOSERS: continue
        prices=[v["price"] for v in vs if v["w"] not in two_sided]
        if len(prices)<2: continue
        pstd=statistics.pstdev(prices)
        if pstd>MAX_PSTD: continue
        sigs.append({"cond":cond,"oidx":oidx,"slug":meta[cond]["slug"],
                     "title":meta[cond]["title"],"outcome":meta[cond]["outcomes"].get(oidx,str(oidx)),
                     "n_back":len(backers),"n_opp":len(opp),"net":len(backers)-len(opp),
                     "mean_price":statistics.mean(prices),"pstd":pstd,
                     "usd":sum(v["usd"] for v in vs),"sport":is_sports(meta[cond]["title"],meta[cond]["slug"])})
print(f"consensus signals (all ages): {len(sigs)}  sports={sum(s['sport'] for s in sigs)}",file=sys.stderr)

# 4. resolve via Gamma
def resolve(slug,oidx):
    m=get(f"{GAMMA}/markets?slug={slug}")
    if not (isinstance(m,list) and m): return None
    mk=m[0]
    if not mk.get("closed"): return None
    op=mk.get("outcomePrices")
    try:
        p=json.loads(op) if isinstance(op,str) else op
        if p is None: return None
        if oidx>=len(p): return None
        return float(p[oidx])>=0.99
    except Exception: return None

resolved=[]
for s in sigs:
    won=resolve(s["slug"],s["oidx"]); time.sleep(0.04)
    if won is None: continue
    s["won"]=won
    p=s["mean_price"]
    s["roi"]= (1.0/p-1.0) if won else -1.0   # per-$ at mean entry, fee-free
    resolved.append(s)

def report(rows,label):
    if not rows:
        print(f"\n{label}: 0 resolved signals"); return
    n=len(rows); hr=sum(r["won"] for r in rows)/n
    mp=statistics.mean(r["mean_price"] for r in rows)
    roi=statistics.mean(r["roi"] for r in rows)
    edge=hr-mp
    print(f"\n{label}: N={n}  hit={hr:.1%}  mean_entry(implied)={mp:.1%}  edge={edge:+.1%}  ROI/$={roi:+.2f}")

print("\n"+"="*60+"\nBACKTEST RESULTS (resolved consensus signals)\n"+"="*60)
report(resolved,"ALL resolved")
report([r for r in resolved if not r["sport"]],"NON-SPORTS")
report([r for r in resolved if r["sport"]],"SPORTS")
report([r for r in resolved if r["net"]>=4],"net>=4 (STRONG+)")
report([r for r in resolved if r["net"]>=6],"net>=6 (ELITE)")
print("\nsample resolved signals:")
for r in sorted(resolved,key=lambda x:-x["net"])[:15]:
    tag="W" if r["won"] else "L"
    sp="⚽" if r["sport"] else "  "
    print(f"  [{tag}] net{r['net']:+d} {sp} {r['title'][:42]:42} BUY {r['outcome'][:10]:10} @{r['mean_price']:.2f} roi{r['roi']:+.2f}")
