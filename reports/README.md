# Polymarket Consensus Engine — Reports & Notes

Organized, dated record of everything we learn building and running the consensus
copy-trading alert engine. **Append-only journal of entries** — never rewrite history,
add a new entry.

## How this folder is organized

- `entries/` — dated entries, one per work session or finding. Naming:
  `YYYY-MM-DD-NN-short-slug.md`. Each entry is self-contained: what we did, what we
  found, what's next.
- `strategies/` — one file per **forward-tested strategy variant** (the portfolio).
  Each holds the strategy's hypothesis, exact config, and a running log of its live
  forward results (hit-rate, edge vs entry price) as markets resolve.
- The living design doc is `../CONSENSUS-ENGINE-PLAN.md` (architecture + progress log).

## Why a strategy *portfolio* (the core methodology)

There is **no usable backtest** — tracked traders' available activity is almost
entirely on live, unresolved markets, and the activity API won't page back far enough
to assemble resolved history (see `entries/2026-06-28-02-empirical-findings.md`). So we
cannot rank strategies offline. The scientifically honest response: **run many strategy
variants simultaneously, forward, and let real resolved outcomes decide.** Each variant
is a standing hypothesis; the engine tags every signal with its strategy, resolves it on
market close, and we compare hit-rate / edge per strategy over time.

## Index

| Date | Entry | Summary |
|------|-------|---------|
| 2026-06-28 | [01 — Run 1 foundation](entries/2026-06-28-01-run1-foundation.md) | Built + verified the consensus engine end-to-end (Phases A–C foundation) |
| 2026-06-28 | [02 — Empirical findings](entries/2026-06-28-02-empirical-findings.md) | Live-API probes: naive consensus is noise; net-directional/price-coherent is the signal; no backtest possible |
| 2026-06-28 | [03 — Strategy portfolio plan](entries/2026-06-28-03-strategy-portfolio-plan.md) | Forge-validated design for N simultaneous forward-tested strategies |
| 2026-06-28 | [04 — Portfolio shipped](entries/2026-06-28-04-portfolio-shipped.md) | 10-strategy forward portfolio built + verified live (10 strategies, 25 signals, atom log, constraint swap proven) |

## Live strategy portfolio
See `strategies/` once the multi-strategy engine ships. Each strategy's live scoreboard
is updated from `/consensus` + Prometheus `consensus_resolved_total{strategy,...}`.
