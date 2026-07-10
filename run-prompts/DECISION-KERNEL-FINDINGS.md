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
