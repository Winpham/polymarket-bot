#!/usr/bin/env python3
"""
audit_pnl_books.py -- ADVERSARIAL re-derivation of the favorite-strategy paper P&L.

Attacks the claims (K1-K3) from FAVCONSENSUS-DEEPEN by re-deriving everything from
raw consensus_signals rows with fresh code. NO reuse of any existing accounting code.

Accounting convention (as stated in the claim under attack):
  strategy = 'favorite', 100 shares/pick,
  entry    = COALESCE(initial_mean_price, mean_price) + 0.005   (+0.5 cent)
  fee      = 0.02 * entry * 100                                  (2% of entry, per 100 sh)
  win  pnl = 100*(1 - entry) - fee
  loss pnl = 100*(0 - entry) - fee
  staked / capital-at-risk = 100 * entry

DB read-only via `docker exec ... psql`. scipy + stdlib only. No network, no LLM.

Usage:
  python3 audit_pnl_books.py --self-test     # asserts on synthetic fixtures
  python3 audit_pnl_books.py                 # run live audit, writes reports/audit_pnl_books.json
"""
import subprocess, csv, io, json, sys, os
from datetime import datetime, timezone
from collections import defaultdict

SHARES = 100.0
EDGE = 0.005          # +0.5c entry slippage
FEE_RATE = 0.02       # 2% of entry
STRAT = 'favorite'

# ----------------------------------------------------------------------------- core math
def entry_price(initial_mean, mean):
    p = initial_mean if initial_mean is not None else mean
    return None if p is None else p + EDGE

def pnl_resolved(entry, won):
    """Realized paper P&L for one resolved pick, 100 shares."""
    fee = FEE_RATE * entry * SHARES
    if won:
        return SHARES * (1.0 - entry) - fee
    return SHARES * (0.0 - entry) - fee

def staked(entry):
    return SHARES * entry

def mtm_open(entry, last_market_price):
    """Mark-to-market P&L for an OPEN pick: current mark = last_market_price.
    Value of position now = 100*last_price; cost basis = 100*entry; fee already sunk."""
    fee = FEE_RATE * entry * SHARES
    if last_market_price is None:
        return None
    return SHARES * (last_market_price - entry) - fee

# ----------------------------------------------------------------------------- interval sweep
def peak_concurrent(intervals):
    """intervals: list of (start_epoch, end_epoch, capital). Returns (peak_capital, peak_count)."""
    evs = []
    for s, e, cap in intervals:
        evs.append((s, +1, cap))
        evs.append((e, -1, cap))
    # process closes before opens at identical ts (a pick freeing capital at t frees before a new one at t)
    evs.sort(key=lambda x: (x[0], x[1]))
    cur_cap = 0.0; cur_n = 0; peak_cap = 0.0; peak_n = 0
    for _, d, cap in evs:
        cur_cap += d * cap
        cur_n += d
        if cur_cap > peak_cap: peak_cap = cur_cap
        if cur_n > peak_n: peak_n = cur_n
    return peak_cap, peak_n

# ----------------------------------------------------------------------------- db
def parse_ts(s):
    """Robust parser for psql timestamptz text, e.g. '2026-07-06 15:52:01.83535+00'.
    Handles fractional seconds of any digit-count (fromisoformat<3.11 needs exactly 3/6)
    and short tz offsets ('+00' -> '+00:00')."""
    if not s: return None
    s = s.strip()
    if not s: return None
    s = s.replace(' ', 'T', 1)
    # split off tz offset (last +/- after the time portion, or trailing Z)
    tz = ''
    if s.endswith('Z'):
        tz = '+00:00'; s = s[:-1]
    else:
        for i in range(len(s)-1, 10, -1):
            if s[i] in '+-':
                tz = s[i:]; s = s[:i]; break
        if tz and len(tz) == 3:      # '+00' -> '+00:00'
            tz = tz + ':00'
    # normalize fractional seconds to exactly 6 digits
    if '.' in s:
        head, frac = s.split('.', 1)
        frac = (frac + '000000')[:6]
        s = head + '.' + frac
    try:
        return datetime.fromisoformat(s + tz)
    except ValueError:
        return None

def fnum(s):
    s = (s or '').strip()
    return float(s) if s else None

def fbool(s):
    s = (s or '').strip().lower()
    if s in ('t', 'true'): return True
    if s in ('f', 'false'): return False
    return None

def fetch_rows():
    q = ("SELECT id, condition_id, outcome_index, event_slug, "
         "first_detected_at, resolved, outcome_won, resolved_at, "
         "initial_mean_price, mean_price, last_market_price "
         "FROM consensus_signals WHERE strategy='%s';" % STRAT)
    cmd = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
           "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q", "-c", q]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    rows = []
    for r in csv.DictReader(io.StringIO(out)):
        rows.append({
            'id': r['id'], 'condition_id': r['condition_id'],
            'outcome_index': r['outcome_index'], 'event_slug': r['event_slug'],
            'first_detected_at': parse_ts(r['first_detected_at']),
            'resolved': fbool(r['resolved']),
            'outcome_won': fbool(r['outcome_won']),
            'resolved_at': parse_ts(r['resolved_at']),
            'initial_mean_price': fnum(r['initial_mean_price']),
            'mean_price': fnum(r['mean_price']),
            'last_market_price': fnum(r['last_market_price']),
        })
    return rows

# ----------------------------------------------------------------------------- audit
def is_resolved_clean(r):
    return r['resolved'] is True and r['outcome_won'] is not None and r['resolved_at'] is not None

def run_audit(rows, now_epoch):
    resolved = [r for r in rows if is_resolved_clean(r)]
    open_picks = [r for r in rows if r['resolved'] is not True]
    void = [r for r in rows if r['resolved'] is True and r['outcome_won'] is None]
    res_no_ts = [r for r in rows if r['resolved'] is True and r['resolved_at'] is None]

    # --- B1: day table keyed on first_detected_at UTC date ---
    day_det = defaultdict(lambda: {'bets': 0, 'wins': 0, 'net': 0.0, 'staked': 0.0})
    total_net = 0.0; total_wins = 0
    for r in resolved:
        e = entry_price(r['initial_mean_price'], r['mean_price'])
        pl = pnl_resolved(e, r['outcome_won'])
        d = r['first_detected_at'].astimezone(timezone.utc).date().isoformat()
        c = day_det[d]
        c['bets'] += 1; c['wins'] += 1 if r['outcome_won'] else 0
        c['net'] += pl; c['staked'] += staked(e)
        total_net += pl; total_wins += 1 if r['outcome_won'] else 0
    det_table = {d: {k: (round(v, 2) if isinstance(v, float) else v)
                     for k, v in c.items()} for d, c in sorted(day_det.items())}

    # --- B1 peak concurrent (global) via interval sweep over resolved picks ---
    intervals = []
    for r in resolved:
        e = entry_price(r['initial_mean_price'], r['mean_price'])
        s = r['first_detected_at'].timestamp()
        en = r['resolved_at'].timestamp()
        if en < s: en = s
        intervals.append((s, en, staked(e)))
    peak_cap, peak_n = peak_concurrent(intervals)

    # --- B2: exclusions ---
    open_entries = [entry_price(r['initial_mean_price'], r['mean_price']) for r in open_picks]
    open_ages_h = [(now_epoch - r['first_detected_at'].timestamp())/3600.0 for r in open_picks]
    exclusions = {
        'open_unresolved': len(open_picks),
        'open_entry_min': round(min(open_entries), 3) if open_entries else None,
        'open_entry_max': round(max(open_entries), 3) if open_entries else None,
        'open_entry_mean': round(sum(open_entries)/len(open_entries), 3) if open_entries else None,
        'open_age_h_min': round(min(open_ages_h), 1) if open_ages_h else None,
        'open_age_h_max': round(max(open_ages_h), 1) if open_ages_h else None,
        'resolved_void_null': len(void),
        'resolved_no_ts': len(res_no_ts),
    }
    # what if voids counted as losses:
    void_as_loss = sum(pnl_resolved(entry_price(r['initial_mean_price'], r['mean_price']), False)
                       for r in void)
    exclusions['void_as_loss_pnl'] = round(void_as_loss, 2)

    # --- B3: resolution-lag bias, won vs lost hold times ---
    def hold_h(r):
        return (r['resolved_at'].timestamp() - r['first_detected_at'].timestamp())/3600.0
    holds_won = sorted(hold_h(r) for r in resolved if r['outcome_won'])
    holds_lost = sorted(hold_h(r) for r in resolved if not r['outcome_won'])
    def median(x):
        if not x: return None
        n = len(x); return x[n//2] if n % 2 else (x[n//2-1]+x[n//2])/2
    lag = {
        'n_won': len(holds_won), 'n_lost': len(holds_lost),
        'median_hold_won_h': round(median(holds_won), 2) if holds_won else None,
        'median_hold_lost_h': round(median(holds_lost), 2) if holds_lost else None,
        'mean_hold_won_h': round(sum(holds_won)/len(holds_won), 2) if holds_won else None,
        'mean_hold_lost_h': round(sum(holds_lost)/len(holds_lost), 2) if holds_lost else None,
    }

    # --- B3: mark-to-market on open picks (are we sitting on losers?) ---
    mtm_vals = []
    for r in open_picks:
        e = entry_price(r['initial_mean_price'], r['mean_price'])
        m = mtm_open(e, r['last_market_price'])
        if m is not None:
            mtm_vals.append((r, m))
    mtm_total = round(sum(m for _, m in mtm_vals), 2)
    mtm_losers = sum(1 for _, m in mtm_vals if m < 0)
    # last-2-day recompute counting open picks at MTM
    all_days = sorted({r['first_detected_at'].astimezone(timezone.utc).date() for r in resolved})
    last2 = set(all_days[-2:]) if len(all_days) >= 2 else set(all_days)
    last2_resolved_net = sum(pnl_resolved(entry_price(r['initial_mean_price'], r['mean_price']), r['outcome_won'])
                             for r in resolved
                             if r['first_detected_at'].astimezone(timezone.utc).date() in last2)
    last2_open_mtm = sum(m for r, m in mtm_vals
                         if r['first_detected_at'].astimezone(timezone.utc).date() in last2)
    b3_mtm = {
        'open_with_mark': len(mtm_vals), 'open_missing_mark': len(open_picks)-len(mtm_vals),
        'mtm_total_open_pnl': mtm_total, 'mtm_open_losers': mtm_losers,
        'last2_days': [d.isoformat() for d in sorted(last2)],
        'last2_resolved_net': round(last2_resolved_net, 2),
        'last2_open_mtm': round(last2_open_mtm, 2),
        'last2_combined': round(last2_resolved_net + last2_open_mtm, 2),
    }

    # --- B4: grading-lag / resolved_at clustering ---
    # bucket resolved_at to the minute; count picks graded in same minute (backlog sweeps)
    minute_bkt = defaultdict(int)
    for r in resolved:
        minute_bkt[r['resolved_at'].replace(second=0, microsecond=0)] += 1
    top_sweeps = sorted(minute_bkt.items(), key=lambda x: -x[1])[:5]
    b4 = {
        'distinct_grade_minutes': len(minute_bkt),
        'max_graded_one_minute': max(minute_bkt.values()) if minute_bkt else 0,
        'top_sweeps': [{'minute': k.isoformat(), 'n': v} for k, v in top_sweeps],
        'note': 'resolved_at = OUR grading pass, not market resolution; sweeps of many rows/min => backlog housekeeping, holds are grade-lag inflated.',
    }

    # --- B5: double-count + super-event collapse (game stacking) ---
    key_seen = defaultdict(int)
    for r in rows:
        key_seen[(r['condition_id'], r['outcome_index'])] += 1
    dup_keys = {k: v for k, v in key_seen.items() if v > 1}
    # per-game (event_slug) exposure among resolved: total staked and PEAK CONCURRENT staked
    game_intervals = defaultdict(list)
    game_total_stake = defaultdict(float)
    game_picks = defaultdict(int)
    for r in resolved:
        e = entry_price(r['initial_mean_price'], r['mean_price'])
        g = r['event_slug'] or '(none)'
        game_intervals[g].append((r['first_detected_at'].timestamp(),
                                  max(r['resolved_at'].timestamp(), r['first_detected_at'].timestamp()),
                                  staked(e)))
        game_total_stake[g] += staked(e)
        game_picks[g] += 1
    game_peak = {}
    for g, iv in game_intervals.items():
        pc, pn = peak_concurrent(iv)
        game_peak[g] = (pc, pn, game_picks[g], game_total_stake[g])
    top_game_total = max(game_peak.items(), key=lambda x: x[1][3])
    top_game_concurrent = max(game_peak.items(), key=lambda x: x[1][0])
    b5 = {
        'duplicate_key_count': len(dup_keys),
        'max_picks_one_game': max(game_picks.values()) if game_picks else 0,
        'game_max_total_stake': {'event': top_game_total[0], 'total_staked': round(top_game_total[1][3], 0),
                                 'picks': top_game_total[1][2]},
        'game_max_concurrent_stake': {'event': top_game_concurrent[0],
                                      'peak_concurrent_staked': round(top_game_concurrent[1][0], 0),
                                      'peak_concurrent_positions': top_game_concurrent[1][1],
                                      'picks': top_game_concurrent[1][2]},
    }

    # --- B6: rebuild day table keyed on RESOLVED_AT date (cash accounting) ---
    day_cash = defaultdict(lambda: {'bets': 0, 'wins': 0, 'net': 0.0})
    for r in resolved:
        e = entry_price(r['initial_mean_price'], r['mean_price'])
        pl = pnl_resolved(e, r['outcome_won'])
        d = r['resolved_at'].astimezone(timezone.utc).date().isoformat()
        c = day_cash[d]
        c['bets'] += 1; c['wins'] += 1 if r['outcome_won'] else 0; c['net'] += pl
    cash_table = {d: {'bets': c['bets'], 'wins': c['wins'], 'net': round(c['net'], 2)}
                  for d, c in sorted(day_cash.items())}
    det_neg_days = [d for d, c in det_table.items() if c['net'] < 0]
    cash_neg_days = [d for d, c in cash_table.items() if c['net'] < 0]
    flipped = [d for d in cash_neg_days if d not in det_neg_days]

    summary = {
        'n_resolved_clean': len(resolved),
        'total_net_pnl': round(total_net, 2),
        'win_rate': round(total_wins/len(resolved), 4) if resolved else None,
        'n_days_detection': len(det_table),
        'peak_concurrent_capital': round(peak_cap, 0),
        'peak_concurrent_positions': peak_n,
        'detection_negative_days': det_neg_days,
        'cash_negative_days': cash_neg_days,
        'positive_days_flipped_negative_on_cash': flipped,
    }
    return {
        'summary': summary,
        'B1_day_table_detection': det_table,
        'B2_exclusions': exclusions,
        'B3_resolution_lag': lag,
        'B3_mark_to_market_open': b3_mtm,
        'B4_grading_lag': b4,
        'B5_double_count_gamestack': b5,
        'B6_day_table_cash': cash_table,
    }

# ----------------------------------------------------------------------------- self test
def self_test():
    # entry / pnl math
    assert abs(entry_price(0.80, None) - 0.805) < 1e-12
    assert entry_price(None, 0.60) == 0.605
    # win at entry 0.805: 100*(1-0.805) - 0.02*0.805*100 = 19.5 - 1.61 = 17.89
    assert abs(pnl_resolved(0.805, True) - 17.89) < 1e-9, pnl_resolved(0.805, True)
    # loss at entry 0.805: -80.5 - 1.61 = -82.11
    assert abs(pnl_resolved(0.805, False) - (-82.11)) < 1e-9, pnl_resolved(0.805, False)
    assert abs(staked(0.805) - 80.5) < 1e-9
    # mtm: open at entry 0.80(+edge=0.805), mark 0.90 -> 100*(0.9-0.805)-1.61 = 9.5-1.61=7.89
    assert abs(mtm_open(0.805, 0.90) - 7.89) < 1e-9, mtm_open(0.805, 0.90)
    assert mtm_open(0.805, None) is None
    # peak concurrent: two overlapping [0,10]@50 and [5,15]@30 -> peak 80 / 2 positions
    pc, pn = peak_concurrent([(0, 10, 50.0), (5, 15, 30.0)])
    assert abs(pc - 80.0) < 1e-9 and pn == 2, (pc, pn)
    # non-overlapping [0,5]@50 [10,15]@30 -> peak 50 / 1
    pc, pn = peak_concurrent([(0, 5, 50.0), (10, 15, 30.0)])
    assert abs(pc - 50.0) < 1e-9 and pn == 1, (pc, pn)
    # touching intervals: close-before-open at shared ts -> no overlap
    pc, pn = peak_concurrent([(0, 5, 50.0), (5, 10, 30.0)])
    assert pn == 1, pn
    # ts parse
    t = parse_ts('2026-07-06 15:52:01.363928+00')
    assert t.year == 2026 and t.tzinfo is not None, t
    assert parse_ts('') is None and parse_ts(None) is None
    # end-to-end run_audit on a synthetic fixture
    now = parse_ts('2026-01-02 00:00:00+00').timestamp()
    fx = [
        # win, detected day1, resolved day1
        {'id': '1', 'condition_id': 'c1', 'outcome_index': '0', 'event_slug': 'g1',
         'first_detected_at': parse_ts('2026-01-01 01:00:00+00'), 'resolved': True,
         'outcome_won': True, 'resolved_at': parse_ts('2026-01-01 03:00:00+00'),
         'initial_mean_price': 0.80, 'mean_price': 0.79, 'last_market_price': 1.0},
        # loss, detected day1, resolved day2 (lag)
        {'id': '2', 'condition_id': 'c2', 'outcome_index': '0', 'event_slug': 'g1',
         'first_detected_at': parse_ts('2026-01-01 02:00:00+00'), 'resolved': True,
         'outcome_won': False, 'resolved_at': parse_ts('2026-01-02 00:30:00+00'),
         'initial_mean_price': 0.70, 'mean_price': None, 'last_market_price': 0.0},
        # open pick
        {'id': '3', 'condition_id': 'c3', 'outcome_index': '1', 'event_slug': 'g2',
         'first_detected_at': parse_ts('2026-01-01 12:00:00+00'), 'resolved': None,
         'outcome_won': None, 'resolved_at': None,
         'initial_mean_price': 0.60, 'mean_price': None, 'last_market_price': 0.50},
    ]
    res = run_audit(fx, now)
    assert res['summary']['n_resolved_clean'] == 2, res['summary']
    # win pnl entry .805 = 17.89 ; loss pnl entry .705 = -70.5-1.41 = -71.91
    assert abs(res['summary']['total_net_pnl'] - (17.89 - 71.91)) < 1e-6, res['summary']['total_net_pnl']
    assert res['summary']['win_rate'] == 0.5
    # B6: loss lands on 2026-01-02 (cash) but detected 2026-01-01. detection day1 has both.
    assert '2026-01-02' in res['B6_day_table_cash'], res['B6_day_table_cash']
    # detection day1 net = 17.89-71.91 <0 ; cash: day1=+17.89(win only), day2=-71.91
    assert res['B6_day_table_cash']['2026-01-01']['net'] > 0
    assert res['B6_day_table_cash']['2026-01-02']['net'] < 0
    # B2 open exclusion count
    assert res['B2_exclusions']['open_unresolved'] == 1
    # B3 mtm open: entry .605, mark .50 -> 100*(.5-.605)-1.21 = -10.5-1.21=-11.71
    assert abs(res['B3_mark_to_market_open']['mtm_total_open_pnl'] - (-11.71)) < 1e-6
    print("SELF-TEST PASSED")

# ----------------------------------------------------------------------------- main
def main():
    if '--self-test' in sys.argv:
        self_test(); return
    rows = fetch_rows()
    # now: use max resolved_at as clock proxy (no network); adversarially, open ages measured to it
    max_ts = max((r['resolved_at'].timestamp() for r in rows if r['resolved_at']), default=0)
    max_det = max((r['first_detected_at'].timestamp() for r in rows if r['first_detected_at']), default=0)
    now_epoch = max(max_ts, max_det)
    res = run_audit(rows, now_epoch)
    res['_meta'] = {'strategy': STRAT, 'n_rows_total': len(rows),
                    'now_proxy_utc': datetime.fromtimestamp(now_epoch, timezone.utc).isoformat(),
                    'convention': 'entry=COALESCE(initial_mean,mean)+0.005; fee=0.02*entry*100; 100sh'}
    outdir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'reports')
    os.makedirs(outdir, exist_ok=True)
    outpath = os.path.join(outdir, 'audit_pnl_books.json')
    with open(outpath, 'w') as f:
        json.dump(res, f, indent=2, default=str)
    print(json.dumps(res, indent=2, default=str))
    print("\nWROTE", outpath)

if __name__ == '__main__':
    main()
