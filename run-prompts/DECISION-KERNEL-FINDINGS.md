# Decision-Kernel Run — findings log (one line per item)

Branch `feat/decision-kernel` off `feat/garbage-policy`. Paper-only, promotes/arms nothing.
Honest ceiling: this WIRES orphaned intelligence into one auditable `decide()` kernel + a sized
shadow book that runs at **k=0 today** (coarse λ̂ ≈ 0.14 leans the favorite surplus toward variance,
not information). It manufactures NO edge; the only verdict-mover is MLB skill persisting forward.

- **Item 1 (kernel + sized append + super_event mirror):** DONE. New pure `scanner/decide.rs`
  (`decide()`, `price_band`, `sport_of`, `KernelCtx`; frozen `KELLY_K=1/12`, `KELLY_BAND{4:.1933,
  5:.5584}`, `BANKROLL=10000` — applied never re-fit), `append_sized_paper_bet` sibling in
  `consensus.rs` (writes `{strategy}__k12` shadow label, byte-identical P&L math, `ON CONFLICT DO
  NOTHING`, no migration), `common/superkey.rs` Rust mirror of `superkey.py` (parity-tested vs its
  self-test cases), `event_slug` added to the `UnresolvedConsensus` SELECT (additive). Wired at the
  housekeeping append seam behind `sized_books=false` (default). 16 new Rust tests + full suite green
  (139 bin + 93 common), clippy clean. With the flag off, `kernel_ctx=None` → the sized block is
  skipped entirely → champion `honest_paper_ledger` writes are byte-identical (only additive change is
  reading one extra column). k=0 proven in-test: `gate_zero_books_nothing_today`.

- **Item 2+3 (sport_multiplier.py → kernel_gate.json + readiness_fraction):** DONE. New
  `scripts/sport_multiplier.py` composes the REAL instruments — `selection_null` (belief-blind
  selection-matched null, ≥1000 draws, p≤0.01), an event-clustered skill + SE, a ≥2 NON-EXPIRING
  time-regime persistence wall (World Cup/Wimbledon pre-registered expiring → 0 regimes), K_POOL=40
  partial pooling + Bonferroni(×#sports) lower bound > 0. Sports are keyed by `kernel_sport()`, an
  EXACT mirror of Rust `sport_of`, so every JSON key is kernel-lookupable (mis-partition would
  silently fail-closed a real edge). `--selftest` (no DB) proves the gate says BOTH no (fail-closed:
  soft soccer, single-week MLB) AND yes (multi-week efficient+skilled MLB → 1.0). **Live output
  (honest):** `sport_mult` all 0.0, `certified_cells: []`, `readiness_fraction: 0.0` (edge_reality
  INDETERMINATE, coverage 20% < 50%, λ̂=0.1357). MLB IS the forward candidate — +13.2% skill in a
  near-efficient market — but at only 20 events the belief-blind null gives p=0.067 > 0.01 (power-
  limited), so it correctly certifies NOTHING yet. Rust `on_disk_gate_json_yields_k0_today` confirms
  the real JSON books stake=0 for every sport/band (k=0). This is the human-review checkpoint: MLB
  flips to 1.0 once it clears p≤0.01 across ≥2 non-expiring regimes forward.

- **Item 5 (surface the sized shadow book):** DONE. New read-only `scripts/sized_book.py` reads
  `honest_paper_ledger WHERE strategy ~ '__k'` and reports the SAME stats as Rust
  `LedgerStats::from_rows` (STAKE-WEIGHTED ROI-on-turnover Σpnl/Σstake, maxDD $, daily Sharpe,
  win-rate) — repairs the blueprint's noted gap that shadow labels don't auto-appear in the
  `consensus_signals`-grouped scoreboard panel. `--selftest` (no DB) proves the stat math. Live: no
  `%__k%` rows yet (correct — k=0). **End-to-end WRITE-path verified against real data, fully
  reversibly:** in a single ROLLBACK'd psql transaction the exact `append_sized_paper_bet` SQL wrote a
  `favorite__k12` shadow row off a real resolved champion signal (entry 0.725 = 0.715+0.01 haircut,
  won, pnl=+71.86 = 200×((1−0.725)/0.725−0.02)); champion `favorite` count unchanged (234 before /
  during / after); ROLLBACK left 0 persistent shadow rows. Champion book byte-untouched.

- **Item 4 (flag-gated resolution-close capture):** DONE. ~4-line reuse of `insert_trajectory_point`
  in the resolution branch, using the mid already fetched that pass, behind `capture_resolution_close`
  (default OFF). Flag off = the live resolution path is byte-identical (guarded, block skipped). Left
  OFF and HUMAN-REVIEW-DEFERRED: enabling writes resolution mids that change a gate INPUT mid-run (a
  tape-budget touch to coordinate with `feat/maker-copy-g3`), so it stays off until a human reviews
  the first weeks of true-close λ̂. Full workspace green (140 bin + 93 common + 73 trading-bot),
  clippy clean.

## Double-check + hardening (adversarial review pass)

An adversarial review CONFIRMED the two headline safety claims: **byte-identical-when-off is sound**
(the only unconditional change is verified-additive column reads on the unresolved SELECT), and
**`append_sized_paper_bet` cannot read/write/overwrite champion rows** and reproduces the champion PnL
math exactly — nothing can touch real money. It found latent bugs that fire ONLY once the gate is
armed; since arming is meant to be "a JSON flip on correct code," all were fixed now:

- **band-6 Kelly collapse (MEDIUM, fixed):** `price_band` returns 6 for entry ≥ $1 but `KELLY_BAND`
  had 6 slots and `[band.min(5)]` silently sized band-6 at band-5's full Kelly. `KELLY_BAND` is now 7
  wide with index 6 = 0.0 (matching the Python cert, which gives band-6 zero) → never size an
  un-bettable ≥$1 entry. New test `band6_entry_ge_one_books_zero_even_when_armed`.
- **`game_n` undercount (MEDIUM, fixed):** counted only the cycle-start UNRESOLVED snapshot, so a
  cluster whose siblings resolved earlier over-sized the survivor. Now counts distinct
  (condition,outcome) per (strategy, super-key) over the FULL signal history via new
  `signal_cluster_rows` — verified real soccer matches carry up to **20** correlated markets under one
  key (the old path would have over-sized ~20× once armed).
- **band-entry fallback (LOW, fixed):** the band now derives from the SAME entry the PnL SQL prices at
  (`COALESCE(entry_ask, initial_market_price + haircut)`, added `initial_market_price` to the SELECT),
  not `mean_price`.
- **`sport_of` whitespace (LOW, fixed):** now trims the classified value, matching Python `kernel_sport`.
- **should_ledger footgun (LOW, fixed):** the sized block now also respects `should_ledger`, so a
  `ledger_strategies` allowlist that excludes `favorite` won't leak a shadow row.

Post-fix: 141 bin + 93 common tests green, clippy clean, release build green. Flags-off byte-identical
guarantee UNCHANGED (the two new SELECT columns are additive; `signal_cluster_rows` runs only when
`sized_books` is on).

## "See how it performs" — in-sample sizing replay (read-only, no deploy)

`scripts/sized_book_replay.py` re-sizes every resolved `favorite` signal with the kernel's exact
ungated formula and compares paper P&L vs the deployed flat-$100 champion, on identical fills. **The
sizing does NOT prove itself in-sample:**

| sizing | legs | ROI-turn | P&L | maxDD | Sharpe |
|---|---|---|---|---|---|
| kernel Kelly-per-game (uncapped) | 324 | **+3.35%** | +$1227 | **$1300** | 0.25 |
| flat $100 (champion) | 351 | +2.91% | +$1021 | $644 | **0.27** |
| flat 100-shares | 351 | +2.72% | +$783 | $497 | 0.28 |

Kelly-per-game posts a higher raw ROI/P&L ONLY by concentrating into a few large band-5 singleton
bets (~$465 each) — which **doubles the drawdown** and leaves Sharpe slightly BELOW flat. Capping to
tame the drawdown destroys the return (cap $100 → +1.01% ROI, Sharpe 0.08; cap $300 → +2.08%). So on
the history we have, **flat-$100 is competitive-to-better risk-adjusted**; the sizing has not earned
promotion. (Caveat: IN-SAMPLE, same summer/tournament window — and it says nothing about edge
durability, which only the forward gate answers.) The verdict-mover remains the FORWARD edge, not the
sizing mechanics — which is exactly why the kernel is correctly parked at k=0.

## Verdict (one paragraph)

The orphaned intelligence is now WIRED into ONE auditable pure `decide()` kernel at the single seam
paper P&L is created, and the sized shadow book (`{strategy}__k12` labels in the existing
`honest_paper_ledger`, no migration) is READY to Kelly-size the moment `edge_reality` clears — but it
runs at **k = 0 today** because the coarse λ̂ ≈ 0.14 leans the favorite surplus toward variance, not
information (`readiness_fraction = 0.0`). The per-sport multiplier is fail-closed and certifies
**nothing** yet: MLB is the standout forward candidate (+13.2% skill in a near-efficient market) but at
only 20 events the belief-blind selection-null gives p = 0.067 > 0.01 (power-limited), and soccer/
tennis are pre-registered expiring (World Cup / Wimbledon) → 0 non-expiring regimes. Everything new is
behind default-off flags (`sized_books`, `capture_resolution_close`) or new files/labels, so with the
flags off the binary is byte-identical and the champion `favorite`/`favorite_liq`/`favorite_v2`/… arms
and their ledger are UNTOUCHED (verified: reversible real-DB write test, champion count 234 unchanged).
This manufactures **no edge** and proves nothing about the edge — the forward clock is the only
arbiter. **What flips `readiness_fraction` to 1.0:** a human reviews the first forward weeks of
true-close λ̂ (unlock `capture_resolution_close`) and finds coverage ≥ 50% with the λ CI lower bound
> 0 (information, not variance); **what flips `sport_mult["mlb"]` to 1.0:** MLB skill persisting to
p ≤ 0.01 across ≥ 2 non-expiring regimes as its sample grows past 20 events. Both are JSON-field
changes the kernel already consumes — no code change, no re-deploy. Branch `feat/decision-kernel` left
UNMERGED for human review (paper-only; promotes/arms nothing).
