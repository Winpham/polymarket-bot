# ADDENDUM to PREREG_20260709T011424Z_maker_copy_g3 — data-semantics deviation

**UTC stamp:** 2026-07-09T01:14:24Z pre-reg + this addendum written during implementation, still
**blind to outcomes** (no win/loss composition inspected). Records a forced deviation from §3/§6.

## Finding (from the Rust source, not the data)

`copy-trading-bot/src/cycles/live_tape.rs:119-147` + comment at `:222-223`: on a Polymarket CLOB
`price_change` event, the fields `clob_price_tape.last_price` / `last_size` / `side` are the
**order-book LEVEL that changed** (price of the level, its new resting size, and which book side) —
they are **NOT an executed trade**. The comment is explicit: *"`last_price` in a price_change is
order-BOOK-LEVEL churn (not a trade)."* The ingested tape is therefore a faithful **top-of-book
(`best_bid`/`best_ask`) inflection series** (lossless on-change, coalesced ≤1 row/asset/s) with
**no trade tape**.

The pre-reg §2/§3 (echoing the run brief) assumed `last_size` was trade volume in shares. It is not.

## Consequence

The pre-registered **REALISTIC (trade-through with size)** model — "cumulative `last_size × price ≥
stake`" — is **not measurable** from this tape. Summing `last_size` would count resting book-depth
churn as if it were executed volume crossing our price, i.e. it would fill on **quote flickers with
no real trade volume** — the precise §5 trap and a cousin of the G2 units bug. Building it would
manufacture exactly the artifact this run exists to avoid.

## Deviation (forced, documented, blind to outcomes)

1. **Keep** OPTIMISTIC (touch: `best_ask ≤ P`) and PESSIMISTIC (through: `best_ask < P` strict).
   Both use genuine top-of-book `best_ask`; both stand exactly as pre-registered.
2. **Replace** the volume-REALISTIC with **DWELL-REALISTIC**: `best_ask ≤ P` observed across ≥2 tape
   inflections spanning ≥ `DWELL_S = 30 s` — an offer sat at/below our price long enough that a
   resting order plausibly matched. Uses only `best_ask`. It is a middle bracket between touch and
   through, **not** a volume/queue-capture measurement.
3. **Report the realized volume / partial-fill / queue-capture dimension (§6 metric 4) as NOT
   MEASURABLE with this tape** — it still needs a true trade tape (data-api `/trades`, which G2b
   showed is offset-capped for busy markets). This is an honest OPEN, not a faked number. The
   `--selftest` **units** fixture is repurposed to assert the simulator's fill decision does NOT
   depend on `last_size` (so book churn can never be mistaken for a fill).

Everything else in the pre-reg (universe, P definition, lag/cancel sweeps, adverse-selection primary,
cost contract, cluster-robust LB, verdict bands, audit gate) stands unchanged.
