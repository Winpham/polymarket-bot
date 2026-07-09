# How to read PAPER-TRACKER.md / .json

`scripts/paper_tracker.py` is a **read-only reporting instrument**. It never writes a DB row,
deploys nothing, arms nothing. It is a thin orchestrator over instruments that already exist
(`audit_pnl_books.py`, `sport_edge_tracker.py`, `standard_guard.py`, and the
`honest_pnl_by_strategy` SQL from `common/src/storage/consensus.rs`) — it composes their views
into one side-by-side surface for {`favorite` (champion, reference), `favorite_liq`,
`favorite_v2`}, and generalizes to any other `favorite_*` strategy that shows up later.

Regenerate it any time with:

```
python3 scripts/paper_tracker.py                 # writes both reports/PAPER-TRACKER.{json,md}
python3 scripts/paper_tracker.py --self-test      # pure offline unit tests, no DB (~1s)
python3 scripts/paper_tracker.py --window 14      # 14-day rolling window instead of the 7d default
```

`scripts/daily_run.sh` wraps the above for a cron/launchd cadence (see that file's header — no
OS-level schedule is wired to it yet; adding one is a deliberate call for Tue, matching this run's
"no launchd/cron edits" guardrail).

## The two honesty landmines this tracker is built to never trip

1. **The new-arm coverage artifact.** `favorite_liq` / `favorite_v2` are built on the unmerged
   `feat/garbage-policy` branch and have **zero rows** in `honest_paper_ledger` — they haven't been
   deployed yet, so no signal has ever fired for them. A past analysis backfill-evaluated this
   family on pre-snapshot history and got an inflated in-sample "+9.66%" that did not survive
   forward. This tracker refuses to repeat that mistake: zero-row arms always render as
   `status: awaiting-forward-data (deploy pending)`, `n: 0`, **no ROI number at all** — not a
   blank, not a zero, not a borrowed historical figure. The moment Tue deploys
   `feat/garbage-policy` and rows start landing in the ledger, this tracker lights the arm up
   automatically on its next run — no code change needed.

2. **Fresh-day censoring on open positions.** Winners resolve roughly 2x faster than losers (see
   `audit_pnl_books.py`'s B3 hold-time asymmetry, reproduced live by this tracker's own
   cross-check). That means a *fresh* day's still-open book is winner-enriched almost by
   construction — the losers just haven't had time to resolve yet. Never read a fresh open-MTM
   total as a floor on what that day will eventually settle to. The tracker labels every open-MTM
   number with this censoring note; treat open positions as "a mid-flight snapshot," not a record.

## What each section means

- **Champion anchor self-test.** Before rendering anything, the tracker cross-checks the
  `favorite` strategy's corrected-fee ROI-on-turnover two independent ways over the *identical*
  resolved-bet population: (a) the ledger's own recorded `pnl`/`stake` columns (entry =
  `entry_ask` or mid+1¢ haircut, fee 2% — the exact convention `append_paper_bet` uses live), and
  (b) `audit_pnl_books.py`'s independently-derived formula (entry = mean+0.5¢ haircut, fee 2% of
  entry×shares — same corrected-fee *shape*, different haircut/price basis). They won't match to
  the decimal (different haircut conventions), but both must be **positive** and within a few
  points of each other. If they diverge in sign or by more than the tolerance, the script **stops
  and refuses to write a report** rather than ship numbers that don't tie out. As of this build:
  ledger-native ≈ +2.2%, audit-formula-on-same-population ≈ +1.6% — both positive, same order of
  magnitude, the residual difference fully explained by the haircut convention. (A separate, much
  larger figure comes from running `audit_pnl_books.py` *standalone*: it covers a bigger
  population that includes pre-ledger history from before Phase 3 shipped, which never got
  appended to `honest_paper_ledger`. That's a real, understood, documented population gap — not a
  contradiction with the tracker's own cross-check, which is always population-matched.)

- **Resolved P&L (canonical), cash vs detection basis.** Two ways to bucket the SAME
  `honest_paper_ledger.pnl` figures by date: `cash` = `resolved_at` (when the paper bet was
  appended — a true cash event), `detection` = `first_detected_at` (when the underlying signal
  first fired, joined from `consensus_signals`). They can disagree on which days are red —
  `day_table_basis_divergence.days_flip_sign_between_bases` lists the days that flip sign
  depending which clock you use. Always know which basis a number is quoted in.

- **Rolling window vs since-first-row.** A 7-day (default; `--window` to change) trailing view
  next to the full since-accrual-began view, so one hot week can't be mistaken for the durable
  record, and vice versa.

- **Throughput.** Bets/day, turnover $/day, peak concurrent capital (interval-sweep, reused from
  `audit_pnl_books.py`), and a turnover-multiple (turnover-per-day ÷ peak concurrent capital) —
  how many times capital effectively "turns over" in a day.

- **Realizable/CLV.** The event-clustered `honest_roi` / `clv_roi` / hit-rate view, ported
  verbatim from `honest_pnl_by_strategy` (`common/src/storage/consensus.rs` — Python can't call
  the async Rust fn directly, so its exact CTEs are reproduced with the same bound constants
  `append_paper_bet` uses: `EXEC_HAIRCUT=0.01`, `FEE_PCT=0.02`).

- **Open positions (MTM).** Still-open picks marked to `last_market_price`, clearly separated from
  resolved P&L, always carrying the censoring note above.

- **By-regime split.** Softness (blind-favorite edge — is this sport's market soft/inefficient?)
  vs skill (surplus over the blind baseline — does the strategy add real selection beyond just
  riding a soft market?) per sport, via `sport_edge_tracker.py`'s `REGIMES` map. A single hot
  tournament (soccer, tennis) showing up as "total edge" isn't durable evidence by itself — skill
  in an *efficient* sport (softness ≈ 0) is the strong signal.

- **Belief-blind reference.** Every arm — champion included — is judged against the exact same
  gate via `standard_guard.py`: `measure()` for the champion (its own selection-null surplus,
  belief-blind lower bound, regression status), `measure(challenger=arm)` for the others (adopt
  vs `CHAMPION-STANDS` verdict). Zero-row arms correctly report "challenger not measurable (below
  readout floor / no rows)" — never a fabricated verdict.

- **Capacity / rarity flag.** Tue's open question — "is `favorite_v2` even deployable or a
  bench-sitter?" — answered on **real, current, forward-snapshot data** from the champion's own
  signal pool (the `initial_total_usd` / `initial_best_backer_rank` snapshot fields, which are
  ~100% forward-captured since 2026-07-03): what fraction of the champion's own currently-firing
  signals would *also* clear the `favorite_liq` ($1k total) and `favorite_v2` (+top-5-backer)
  gates. This is a rarity **diagnostic** on the champion's pool, explicitly **not** a P&L estimate
  for the new arms (see landmine #1) — it only tells you how often the gate would fire, not what
  it would have earned.

- **Power flag.** Below 30 resolved events (the same pre-registered floor `standard_guard.py`
  uses), a number reads "not yet readable" rather than a false-precision percentage.

## Extending this tracker

Add a new strategy by passing `--strategies favorite,favorite_liq,favorite_v2,favorite_v3`, or do
nothing — any `favorite_*` strategy that starts appearing in `honest_paper_ledger` or
`consensus_signals` is auto-discovered and rendered (with an honest zero-row note if it hasn't
ledgered anything yet). Don't add new P&L math here; if a new view is needed, extend or import
from the underlying instrument (`audit_pnl_books.py`, `standard_guard.py`,
`sport_edge_tracker.py`, or the ledger/`honest_pnl_by_strategy` SQL) the same way this script
already does — that's the whole point of it being a thin orchestrator.
