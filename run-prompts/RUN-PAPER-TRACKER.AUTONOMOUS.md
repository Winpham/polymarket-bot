# Autonomous Run: A real, accurate, reliable side-by-side paper-trading tracker — champion vs favorite_liq vs favorite_v2

> **Read this whole brief before touching anything.** You are an autonomous build worker on
> `~/polymarket-bot`, cwd = this worktree `wt/paper-tracker` (branch `feat/paper-tracker`, off fresh
> `main`). Tue's ask: *"real accurate reliable paper-trading tracking for the new strategies
> (`favorite_liq`, `favorite_v2`) as well as the champion (`favorite`) as a reference."* This is a
> **read-only reporting instrument** — you build the tracker, you do NOT deploy anything, arm anything,
> or touch strategy selection. If you find yourself making a number look good instead of making the
> tracker **honest and trustworthy**, stop: the entire value here is a surface Tue can trust when the
> forward record decides whether these arms are real.

---

## 0. Context you must not re-derive wrong (state of play, 2026-07-09)

- **`favorite`** (champion, price_band 0.65–0.98) is LIVE and accruing — 218 rows in
  `honest_paper_ledger` through today. It is the REFERENCE.
- **`favorite_liq`** (= favorite + `initial_total_usd ≥ $1000`) and **`favorite_v2`** (= favorite_liq +
  `initial_best_backer_rank < 5`) are built on the **unmerged `feat/garbage-policy` branch** → NOT
  deployed → **zero ledger rows yet.** They start accruing only after Tue merges/deploys that branch.
  Your tracker must render them as **"registered, awaiting forward data (deploy pending)"**, NOT omit
  them, and light them up automatically the moment rows land.
- **Accrual is automatic** (`housekeeping.rs::should_ledger`: every non-`_blind` strategy ledgers when
  `LEDGER_STRATEGIES=""`), **idempotent** (`append_paper_bet` = `ON CONFLICT DO NOTHING`), at the
  **realizable entry** (`entry_ask` else mid+haircut) with the **corrected fee** and flat stake. So the
  ledger is already the honest instrument — your job is a trustworthy READ over it, not a new ledger.
- **Snapshot fields are captured at 100% forward** (`initial_total_usd`/`initial_best_backer_rank`,
  07-08: 17/17, 07-09: 11/11) — so forward filtering for the new arms will be clean. The in-sample
  coverage gap (only ~15/139 good-window bets carry snapshots) is HISTORICAL; **do not backfill-evaluate
  the new arms on pre-snapshot history and present it as their record** — that is the coverage artifact
  that already inflated an in-sample "+9.66%". The tracker's honest scope for the new arms is
  **forward-from-first-row only.**

## 0a. EXTEND, do not rebuild

The honest per-strategy logic already exists — reuse it, do not re-implement P&L math:
- `scripts/audit_pnl_books.py` → `reports/audit_pnl_books.json` (authoritative cash-basis P&L, corrected
  fee, self-test). This is your P&L source-of-truth convention; match it or call it.
- `honest_pnl_by_strategy` logic (used by `standard_guard.py`, `unified_book.py`, `board.rs`,
  `honest_digest.rs`) = the realizable/CLV event-clustered view. Reuse it for the CLV column.
- `regime_cell_scoreboard.py` / `sport_edge_tracker.py` REGIMES map for the by-sport split.
Build ONE new thin orchestrator (`scripts/paper_tracker.py`) that composes these into the side-by-side
surface. If you find yourself copying P&L formulae, stop and import instead.

---

## 1. What "real accurate reliable" means here — the tracker's required content

`scripts/paper_tracker.py` (read-only DB; `docker exec polymarket-bot-postgres-1 psql -U bot -d polymarket`
or `DATABASE_URL`), emitting `reports/PAPER-TRACKER.json` + a readable `reports/PAPER-TRACKER.md`, for the
tracked set **{favorite (reference), favorite_liq, favorite_v2}** (strategy-agnostic: accept a
`--strategies` list, default these three; auto-include any others present so it generalizes).

Per arm, both honest views (LABELED, never one blended number):
1. **Resolved P&L (canonical)** — from `honest_paper_ledger`, corrected fee, flat stake, event-dedup:
   bets, turnover, net P&L, ROI-on-turnover, win%. Cross-checked to `audit_pnl_books.py` convention
   (reproduce the champion ~+2.8% corrected-fee anchor as a self-test — if you can't, STOP and report).
2. **Realizable / CLV** — event-clustered `honest_pnl_by_strategy` view (honest_roi, clv_roi, hit-rate).
3. **Throughput** — fire-rate (signals/day), turnover-multiple context, and **capacity flag**: for
   `favorite_v2`, report how rare the top-5-backer + $1k condition is (Tue's open "is it even
   deployable or a bench-sitter?" question).
4. **By-regime split** (sport) and a **rolling-window** view (e.g. 7d / since-first-row), so a single
   hot tournament can't masquerade as durable edge.
5. **Open positions (MTM)** — honest mark, clearly separated from resolved, and **never quote a fresh
   day as a floor** (winners resolve ~2× faster → fresh days are winner-enriched; label the censoring).

**Honesty guards baked into the surface (not optional):**
- Label the accounting basis on every P&L (detection-day vs cash-day/resolved) — they give different
  worst days; a tracker that hides the basis is untrustworthy.
- For arms with 0 rows: show `status: awaiting-forward-data (deploy pending)`, `n=0`, and DO NOT compute
  a fake ROI or borrow the in-sample number.
- Show the belief-blind reference: reuse `standard_guard.py --challenger <arm>` / `selection_null.py` so
  each arm's forward record is judged against the same gate the champion is, not a vanity P&L.
- Power/label every number with N and a clustered CI where the instruments provide one; flag anything
  below the power floor (e.g. <30 resolved events) as "not yet readable."

## 2. Deliverables & make it repeatable

- `scripts/paper_tracker.py` (+ `--strategies`, `--window`, `--json`/`--md`), self-test that reproduces
  the champion anchor.
- `reports/PAPER-TRACKER.md` rendered now (champion populated; new arms shown awaiting-data) +
  `reports/PAPER-TRACKER.json`.
- **Wire it into the existing daily cadence** so tracking is ONGOING, not a one-off: add the script to
  `daily_run.sh` (or the `honest_digest` path) so the surface refreshes daily. If a dashboard surface
  exists (`board.rs`), note how it would consume the JSON — but do NOT modify Rust/board unless it's a
  pure read-only addition with green tests; the Python surface is the MVP.
- A short `reports/PAPER-TRACKER-README.md`: how to read it, what each number means, the two honesty
  landmines (coverage artifact for new arms; censoring for fresh days).

## 3. Guardrails (violating any = failed run)

- **Read-only DB** (except none — you write no rows). **Paper-only. Deploy nothing, arm nothing, merge
  nothing.** No `.env` edits. No Rust strategy changes.
- **Cost-zero / Max-only:** no child `claude` spawns, never set `ANTHROPIC_API_KEY`. Read-only analysis
  subagents OK; no concurrent write/git subagents.
- **Stay in this worktree on `feat/paper-tracker`.** Never commit to `main` (prod runs local main). Commit
  incrementally (a reaped long run must be salvageable from the branch). Do NOT touch files owned by the
  active `feat/maker-copy-g3` (tape/fills) or `feat/garbage-policy` (consensus.rs) work — you build only
  `scripts/` + `reports/` + at most a `daily_run.sh` append. If a change would collide, yield.
- **Extend, don't rebuild** (§0a). Any P&L math must come from the existing instruments.

## 4. Completion criteria (honest definition of done)

Green = ALL of: (1) `paper_tracker.py` runs read-only and reproduces the champion corrected-fee anchor in
its self-test; (2) `PAPER-TRACKER.md`/`.json` render the 3-arm side-by-side with both labeled P&L views,
fire-rate/capacity, by-regime + rolling windows, and open-MTM — champion populated, `favorite_liq`/
`favorite_v2` shown as `awaiting-forward-data`; (3) belief-blind reference wired per arm; (4) honesty
guards visible (basis labels, censoring note, power flags, no fake ROI on empty arms); (5) refresh wired
into the daily cadence; (6) README; (7) committed on `feat/paper-tracker` with a one-paragraph status.

State plainly in the status: the tracker is BUILT and reliable, champion is tracked now, and the new arms
will produce a trustworthy forward record **only after Tue deploys `feat/garbage-policy`** — the tracker
does not and cannot manufacture their record before then. If any criterion can't be met, STOP, commit,
and write exactly what's missing. A timed-out run is "incomplete + resumable", never "done".
