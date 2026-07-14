#!/usr/bin/env python3
"""
MARKET-SIDE POPULATION HARVEST — enumerate every trader in a niche.

Why: every wallet we know (3,085) came from a leaderboard that sorts by ABSOLUTE PnL
(corr(rank, ROI) = -0.05) -- a whale sort, not a skill sort. One median esports market
contains 447 distinct wallets; our entire universe is 3,085. We are not sampling niches,
we are sampling whales.

The inversion: /trades?market=<condition_id> enumerates EVERY participant in a market.
Cost is O(markets), not O(wallets).

API facts VERIFIED live 2026-07-14 (do not trust these without re-verifying -- this API
returns 200 OK for params it silently ignores):
  * limit=1000 IS honored here (the leaderboard's 50-cap does NOT apply to /trades).
  * offset HARD-CAPS at 3000 => max ~4000 trades/market, newest-first.
  * EVERY time param is IGNORED -- before/after/startTs/endTs and even an invented
    `bogusParamXYZ` return the byte-identical page. There is NO time-slice escape from
    the 4000 cap. (This is the same class of bug as the startTs burn that once cost us
    96.8% of history.) Markets over the cap are flagged `truncated` and reported, never
    silently treated as complete.

SAFETY -- discovery must never become trust. Harvested rows go to `harvest_fills`, a
table the live consensus path DOES NOT READ. This is deliberate and structural: in the
live schema `consensus_eligible` DEFAULTS TRUE (a naive insert would hand thousands of
strangers a vote) and `active=TRUE` would drag them into the per-cycle wallet poll
(~167 req/s, 4x the API ceiling). Writing to a separate table makes that entire class of
landmine impossible rather than merely avoided.

Resolutions need no extra API calls: harvest_fills joins our existing trader_fills on
(condition_id, outcome_index) -> outcome_won.

Idempotent + resumable by design (long runs get reaped; the work must survive that):
each market is harvested in one transaction and recorded in `harvest_markets`; a re-run
skips what is already done.

Usage:
  ./harvest.py --self-test                  # K1 fidelity battery (hits API, no writes)
  ./harvest.py --niches weather,esports     # harvest those niches
  ./harvest.py --niches all --limit 500     # cap markets per niche (smoke test)
"""
import argparse
import csv
import io
import json
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

API = "https://data-api.polymarket.com/trades"
PAGE = 1000          # honored by /trades (verified)
MAX_OFFSET = 3000    # hard server cap (verified) => <=4000 rows/market
WORKERS = 16         # stays under the ~40 req/s measured ceiling
UA = {"User-Agent": "Mozilla/5.0 (compatible; polymarket-bot/niche-harvest)"}

# THE PARAM THAT CHANGES EVERYTHING: /trades defaults to takerOnly=TRUE and silently
# serves only the TAKER side of each trade -- ~60% of all fills are hidden. Verified:
# one market returned 272 rows by default and 671 with takerOnly=false. A default
# harvest would structurally miss the entire MAKER-side population, including the
# patient limit-order traders who are often the sharpest.
#
# Note params are NOT uniformly honored on this endpoint: the TIME params
# (before/after/startTs/endTs) are silently ignored, but takerOnly is real. Every param
# must be tested individually -- never assumed.
FULL = "takerOnly=false"

# The maker/taker LABEL is recoverable and worth the 2nd fetch: each tx = 1 taker + N
# makers (up to 11 observed), so any (tx_hash, wallet) present in the taker-only tape is
# the TAKER and every other full-tape row is a MAKER. This is the cleanest possible
# uncopyable-profit classifier -- far better than the churn proxy -- which matters
# because this project has already found that the leaderboard's "sharps" ARE makers and
# their spread-capture edge cannot be copied by a taker-follower.

PG = ["docker", "exec", "-i", "polymarket-bot-postgres-1",
      "psql", "-U", "bot", "-d", "polymarket", "--csv", "-q"]

# The niche taxonomy. Weather is split out of `other` by slug (it has no `sport` tag but
# is a real, distinct, and per memory unusually promising space). Esports collapses
# cs2/dota/lol -- they share a trader population.
NICHE_SQL = r"""
CASE WHEN slug ~* 'temperature|rain|snow|weather|highest-temp|lowest-temp' THEN 'weather'
     WHEN sport IN ('cs2','dota','lol') THEN 'esports'
     WHEN sport IS NOT NULL THEN sport
     WHEN slug ~* '^(bitcoin|ethereum|solana|xrp|crypto)' THEN 'crypto'
     ELSE 'other' END
"""

DDL = f"""
CREATE TABLE IF NOT EXISTS harvest_markets (
  condition_id text PRIMARY KEY,
  niche        text NOT NULL,
  slug         text,
  n_trades     integer NOT NULL,
  n_wallets    integer NOT NULL,
  truncated    boolean NOT NULL DEFAULT false,
  harvested_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS harvest_fills (
  condition_id  text NOT NULL,
  wallet        text NOT NULL,
  outcome_index integer NOT NULL,
  side          text NOT NULL,
  price         double precision NOT NULL,
  size_usd      double precision NOT NULL,
  ts            timestamptz NOT NULL,
  tx_hash       text,
  niche         text NOT NULL,
  is_maker      boolean          -- NULL only on truncated markets (label not derivable)
);
CREATE INDEX IF NOT EXISTS idx_hf_cond   ON harvest_fills (condition_id, outcome_index);
CREATE INDEX IF NOT EXISTS idx_hf_wallet ON harvest_fills (wallet, niche);
CREATE INDEX IF NOT EXISTS idx_hm_niche  ON harvest_markets (niche);
"""

_print_lock = threading.Lock()


def psql(sql, csv_out=True):
    out = subprocess.run(PG if csv_out else PG[:-2] + ["-q"],
                         input=sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(f"psql failed:\n{out.stderr}")
    return list(csv.DictReader(io.StringIO(out.stdout))) if csv_out else out.stdout


def get(url, tries=4):
    """GET with backoff. A 400 means we walked past the offset ceiling -> end of tape."""
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 400:
                return []            # offset ceiling
            if e.code == 429:
                time.sleep(2 ** i)   # backoff and retry
                continue
            time.sleep(1 + i)
        except Exception:
            time.sleep(1 + i)
    return None                      # give up -> caller records the failure, no silent zero


def _paginate(cid, extra=""):
    """Walk one tape to the offset ceiling. Returns (rows, hit_ceiling) or (None, False)
    on hard failure -- never a silent empty (that is how you lose 96.8% of history)."""
    rows, off = [], 0
    while off <= MAX_OFFSET:
        page = get(f"{API}?market={cid}&limit={PAGE}&offset={off}" + (f"&{extra}" if extra else ""))
        if page is None:
            return None, False
        if not page:
            return rows, False           # tape genuinely ran out -> COMPLETE
        rows.extend(page)
        if len(page) < PAGE:
            return rows, False           # short page -> COMPLETE
        off += PAGE
    return rows, True                    # walked off the ceiling -> TRUNCATED


def fetch_market(cid):
    """Full (maker+taker) tape for one market, each row labelled is_maker.

    Truncated markets are still harvested (they count for POPULATION discovery) but are
    flagged so the scorer can exclude them: the tape is newest-first, so truncation drops
    the EARLIEST entrants -- precisely the informed early money we are hunting. Scoring a
    truncated market would bias every number computed from it. We do not pay for the
    taker tape there, since the label cannot be derived consistently anyway (the two tapes
    truncate at different points).

    Returns (rows, truncated) or (None, False) on hard failure.
    """
    full, truncated = _paginate(cid, FULL)
    if full is None:
        return None, False
    if truncated:
        for r in full:
            r["_is_maker"] = None        # honest unknown, never a guessed label
        return full, True

    taker, t_trunc = _paginate(cid)      # default = takerOnly, the labelling key
    if taker is None or t_trunc:
        for r in full:
            r["_is_maker"] = None
        return full, truncated
    tkey = {(r.get("transactionHash"), r.get("proxyWallet")) for r in taker}
    for r in full:
        r["_is_maker"] = (r.get("transactionHash"), r.get("proxyWallet")) not in tkey
    return full, False


def sql_lit(s):
    return "'" + str(s).replace("'", "''") + "'"


def persist(cid, niche, slug, trades, truncated):
    """One market, one transaction. Delete-then-insert = idempotent re-harvest."""
    wallets = {t["proxyWallet"] for t in trades}
    rows = []
    for t in trades:
        try:
            price = float(t["price"])
            size = float(t["size"]) * price          # size is shares; usd = shares * price
            mk = t.get("_is_maker")
            rows.append("(" + ",".join([
                sql_lit(cid), sql_lit(t["proxyWallet"]), str(int(t["outcomeIndex"])),
                sql_lit(t["side"]), repr(price), repr(size),
                f"to_timestamp({int(t['timestamp'])})",
                sql_lit(t.get("transactionHash") or ""), sql_lit(niche),
                "NULL" if mk is None else ("true" if mk else "false"),
            ]) + ")")
        except (KeyError, ValueError, TypeError):
            continue                                  # malformed row: skip, never guess
    stmt = ["BEGIN;", f"DELETE FROM harvest_fills WHERE condition_id = {sql_lit(cid)};"]
    for i in range(0, len(rows), 1000):               # chunk: avoid a giant single stmt
        stmt.append(
            "INSERT INTO harvest_fills (condition_id,wallet,outcome_index,side,price,"
            "size_usd,ts,tx_hash,niche,is_maker) VALUES " + ",".join(rows[i:i + 1000]) + ";")
    stmt.append(
        "INSERT INTO harvest_markets (condition_id,niche,slug,n_trades,n_wallets,truncated) "
        f"VALUES ({sql_lit(cid)},{sql_lit(niche)},{sql_lit(slug or '')},{len(trades)},"
        f"{len(wallets)},{'true' if truncated else 'false'}) "
        "ON CONFLICT (condition_id) DO UPDATE SET n_trades=EXCLUDED.n_trades,"
        "n_wallets=EXCLUDED.n_wallets,truncated=EXCLUDED.truncated,harvested_at=now();")
    stmt.append("COMMIT;")
    psql("\n".join(stmt), csv_out=False)
    return len(trades), len(wallets)


def inventory(niches, limit):
    """Resolved markets we can score (resolution comes from our own trader_fills)."""
    filt = ""
    if niches != ["all"]:
        filt = "WHERE niche IN (" + ",".join(sql_lit(n) for n in niches) + ")"
    cap = f"AND rn <= {int(limit)}" if limit else ""
    return psql(f"""
    WITH m AS (
      SELECT condition_id, MIN(slug) slug, MIN(sport) sport,
             BOOL_OR(resolved AND outcome_won IS NOT NULL) has_res
      FROM trader_fills GROUP BY condition_id
    ),
    n AS (SELECT condition_id, slug, has_res, {NICHE_SQL} AS niche FROM m),
    r AS (
      SELECT n.condition_id, n.slug, n.niche,
             ROW_NUMBER() OVER (PARTITION BY n.niche ORDER BY n.condition_id) rn
      FROM n
      LEFT JOIN harvest_markets h USING (condition_id)
      WHERE n.has_res AND h.condition_id IS NULL      -- resumable: skip done markets
    )
    SELECT condition_id, slug, niche FROM r
    {filt.replace('WHERE niche', 'WHERE niche') if filt else ''}
    {cap if cap else ''}
    ORDER BY niche, rn;
    """)


# --------------------------------------------------------------------------------
# K1 -- harvest fidelity. The market-side tape MUST agree with our own wallet-side
# tape for wallets we already track. If it does not, the harvest is not measuring
# what we think it is, and the whole run is void.
# --------------------------------------------------------------------------------
def self_test():
    print("K1 harvest-fidelity battery\n" + "=" * 60)
    rows = psql("""
      SELECT condition_id, COUNT(*) n FROM trader_fills
      WHERE resolved AND outcome_won IS NOT NULL
      GROUP BY 1 HAVING COUNT(*) BETWEEN 20 AND 300
      ORDER BY condition_id LIMIT 3;
    """)
    if not rows:
        sys.exit("K1 FAIL: no suitable markets to reconcile")
    ok = True
    for r in rows:
        cid = r["condition_id"]
        trades, trunc = fetch_market(cid)
        if trades is None:
            print(f"  {cid[:12]}  API FAILED"); ok = False; continue
        api_w = {t["proxyWallet"].lower() for t in trades}
        ours = {x["wallet"].lower() for x in psql(
            f"SELECT DISTINCT wallet FROM trader_fills WHERE condition_id={sql_lit(cid)}")}
        # Every wallet WE recorded in this market must appear in the market-side tape.
        # (The converse is the whole point: the tape has far MORE wallets than we knew.)
        missing = ours - api_w
        cover = 1 - len(missing) / max(len(ours), 1)
        verdict = "PASS" if not missing else f"FAIL missing={len(missing)}"
        if missing and not trunc:
            ok = False
        elif missing and trunc:
            verdict += " (market TRUNCATED -- expected)"
        print(f"  {cid[:12]}  ours={len(ours):4d} tape={len(api_w):5d} "
              f"cover={cover:6.1%}  new_wallets={len(api_w - ours):5d}  {verdict}")
    print("=" * 60)
    print("K1", "PASS -- market-side tape contains our wallet-side tape" if ok else "FAIL -- STOP")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--niches", default="weather,esports,tennis")
    ap.add_argument("--limit", type=int, default=0, help="max markets per niche (0=all)")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()

    psql(DDL, csv_out=False)
    if a.self_test:
        sys.exit(self_test())

    todo = inventory([n.strip() for n in a.niches.split(",")], a.limit)
    if not todo:
        print("nothing to harvest (all done?)"); return
    print(f"harvesting {len(todo)} markets across "
          f"{len(set(r['niche'] for r in todo))} niches ...", flush=True)

    t0 = time.time()
    stat = {"mkts": 0, "trades": 0, "trunc": 0, "fail": 0}

    def work(r):
        trades, trunc = fetch_market(r["condition_id"])
        if trades is None:
            with _print_lock:
                stat["fail"] += 1
            return
        nt, nw = persist(r["condition_id"], r["niche"], r["slug"], trades, trunc)
        with _print_lock:
            stat["mkts"] += 1
            stat["trades"] += nt
            stat["trunc"] += int(trunc)
            if stat["mkts"] % 100 == 0:
                el = time.time() - t0
                print(f"  {stat['mkts']:6d}/{len(todo)}  trades={stat['trades']:9,d}  "
                      f"trunc={stat['trunc']:4d} fail={stat['fail']:3d}  "
                      f"{stat['mkts']/el:5.1f} mkt/s", flush=True)

    with ThreadPoolExecutor(WORKERS) as ex:
        list(ex.map(work, todo))

    print(f"\nDONE {stat['mkts']} markets, {stat['trades']:,} trades, "
          f"{stat['trunc']} truncated, {stat['fail']} failed in {time.time()-t0:.0f}s")
    for r in psql("""SELECT niche, COUNT(*) markets, SUM(n_trades) trades,
                     SUM(truncated::int) truncated FROM harvest_markets
                     GROUP BY 1 ORDER BY 3 DESC NULLS LAST;"""):
        print(f"  {r['niche']:10s} markets={r['markets']:>6s} trades={r['trades']:>10s} "
              f"truncated={r['truncated']:>4s}")


if __name__ == "__main__":
    main()
