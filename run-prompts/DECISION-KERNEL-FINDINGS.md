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
