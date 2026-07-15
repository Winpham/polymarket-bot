#!/usr/bin/env python3
"""Zero-cost validation: does the ATP/WTA final-hour favourite edge survive a LIVE-KNOWABLE anchor
derived from the free ESPN feed (match start + set-count duration estimate), vs the ex-post maturity?"""
import duckdb, os, re, io, glob, json, subprocess, urllib.request, sys, unicodedata, datetime as dt
import numpy as np, pandas as pd
from collections import defaultdict
import pyarrow.parquet as pq
sys.path.insert(0, os.path.expanduser('~/polymarket-bot/scripts/niche')); import us_native_backtest as U

def norm(s):
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z ]', ' ', s)
def toks(s): return {t for t in norm(s).split() if len(t) >= 4}

def espn_comps():
    comps = {}
    for tour in ('atp', 'wta'):
        for date in ('20260624','20260628','20260702','20260706','20260710','20260713'):
            try:
                url = 'https://site.api.espn.com/apis/site/v2/sports/tennis/%s/scoreboard?dates=%s' % (tour, date)
                d = json.load(urllib.request.urlopen(url, timeout=30))
            except Exception as e:
                print('  espn fetch fail', tour, date, e); continue
            for ev in d.get('events', []):
                for g in ev.get('groupings', []):
                    for c in g.get('competitions', []):
                        if c['status']['type']['state'] != 'post': continue
                        cs = c.get('competitors', [])
                        if len(cs) != 2: continue
                        names = [cc.get('athlete', {}).get('displayName', '') for cc in cs]
                        nsets = max((len(cc.get('linescores', [])) for cc in cs), default=0)
                        if nsets < 1: continue
                        comps[c['id']] = {'tour': tour, 'start': c.get('startDate') or c.get('date'),
                                          'names': names, 'nsets': nsets}
    return list(comps.values())

print('fetching ESPN atp/wta...')
comps = espn_comps()
print('ESPN post-state singles competitions:', len(comps))
espn_by_date = defaultdict(list)
for c in comps:
    if c['start']: espn_by_date[str(c['start'])[:10]].append(c)

con = duckdb.connect(); f = os.path.expanduser('~/polymarket-archive/us_markets.parquet')
um = con.execute("SELECT slug, question FROM read_parquet('%s') WHERE slug LIKE 'aec-atp-%%' OR slug LIKE 'aec-wta-%%'" % f).df()
qof = dict(zip(um.slug, um.question))

def psql(sql):
    o = subprocess.run(['docker','exec','-i','polymarket-bot-postgres-1','psql','-U','bot','-d','polymarket','-v','ON_ERROR_STOP=1','--csv','-q'],
                       input='SET max_parallel_workers_per_gather=0; ' + sql, capture_output=True, text=True)
    return pd.read_csv(io.StringIO(o.stdout))
dd = psql("SELECT symbol,settlement_price FROM us_daily_market_report WHERE business_date=maturity_date AND settlement_price IN (0,1) AND (symbol LIKE 'aec-atp-%' OR symbol LIKE 'aec-wta-%');")
won = dict(zip(dd.symbol, dd.settlement_price.astype(float)))
dm = psql("SELECT symbol, maturity_date, maturity_time FROM us_daily_market_report WHERE business_date=maturity_date AND settlement_price IN (0,1) AND (symbol LIKE 'aec-atp-%' OR symbol LIKE 'aec-wta-%') AND maturity_time IS NOT NULL;")
dm['mep'] = pd.to_datetime(dm.maturity_date.astype(str)+' '+dm.maturity_time.astype(str), utc=True, errors='coerce').map(lambda x: x.timestamp() if pd.notna(x) else float('nan'))
matep = dict(zip(dm.symbol, dm.mep))

paths = {}
for fp in sorted(glob.glob(os.path.expanduser('~/polymarket-archive/us_time_sales/*.parquet'))):
    t = pq.read_table(fp, columns=['Transaction Time','Symbol','Last Price']).to_pandas(); t['ep'] = t['Transaction Time'].astype('int64')/1e9
    for s, px, ep in zip(t.Symbol.values, t['Last Price'].values, t.ep.values):
        if s in won and (s.startswith('aec-atp-') or s.startswith('aec-wta-')):
            paths.setdefault(s, []).append((float(ep), float(px)))
paths = {s: sorted(p) for s, p in paths.items() if len(p) >= 50}
print('US atp/wta curated paths with settlement:', len(paths))

def us_date(s):
    m = re.search(r'(\d{4}-\d{2}-\d{2})', s); return m.group(1) if m else None
def price_at(p, tt):
    b = None
    for (t, px) in p:
        if t <= tt: b = px
        else: break
    return b
SETMIN = {'atp': 48, 'wta': 44}
matched = 0; rows_espn = []; rows_mat = []
for s, p in paths.items():
    d = us_date(s); q = qof.get(s)
    if not d or not q: continue
    ut = toks(q); cand = None
    for c in espn_by_date.get(d, []):
        if len(ut & toks(' '.join(c['names']))) >= 2: cand = c; break
    if cand is None: continue
    matched += 1
    start = pd.to_datetime(cand['start'], utc=True).timestamp()
    anchor = start + cand['nsets']*SETMIN[cand['tour']]*60 - 45*60
    px = price_at(p, anchor)
    if px is not None and 0.65 <= px < 0.98:
        rows_espn.append((U.event_key(s), won[s]-px-U.fee_us(px)-0.010))
    if s in matep and matep[s] == matep[s]:
        pxm = price_at(p, matep[s]-3600)
        if pxm is not None and 0.65 <= pxm < 0.98:
            rows_mat.append((U.event_key(s), won[s]-pxm-U.fee_us(pxm)-0.010))
print('matched US<->ESPN:', matched)

def boot(rows):
    be = defaultdict(list); [be[e].append(v) for e, v in rows]
    m = np.array([np.mean(v) for v in be.values()])
    if len(m) < 20: return None
    rng = np.random.default_rng(7); bs = m[rng.integers(0, len(m), (4000, len(m)))].mean(1)
    return m.mean()*100, np.percentile(bs, 2.5)*100, np.percentile(bs, 97.5)*100, (bs <= 0).mean(), len(m)
for lab, rr in [('ESPN-derived LIVE anchor (start+nsets*setmin-45m)', rows_espn),
                ('maturity-1h anchor (ex-post, same matched set)', rows_mat)]:
    r = boot(rr)
    print('  %s: %s' % (lab, ('NET %+.3fc [%+.2f,%+.2f] p=%.3f (%d ev)' % r) if r else 'thin (%d rows)' % len(rr)))
