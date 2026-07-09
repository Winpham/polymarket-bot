# ML "combination of everything" — findings (2026-07-09)

**Hypothesis (Tue):** the hand-thresholded arms lose because each is a univariate silo; a single
model over ALL at-fire features jointly might find interactions the silos miss.

**Test (the generator, judged by the honest gate):** `scripts/ml_edge_model.py`. Population = `loose`
(broadest consensus detection, subsumes every arm). Features = AT-FIRE only (price, price_std,
recency, total_usd, n_backers, net_count, best_backer_rank, n_opposers, net_quality, is_sports,
sport, market_type, entry_ask, spread). Target = **realizable** edge (`won − entry_ask − fee`).
Models = logistic (interpretable) + HistGBM (flexible), calibrated. Judge = time-split holdout +
5-fold walk-forward, realizable entry, event-clustered.

## Result: the hypothesis does NOT hold on current data.

- **Interpretable model just re-learns "bet favorites" and LOSES at realizable** (−2.42% OOS). Top
  drivers = `ask`, `price` — it echoes the market; the "combination" it finds is the price itself.
- **Flexible model (HistGBM) does not beat betting indiscriminately.** Single-split showed +1.58%,
  but 5-fold walk-forward: **model − bet-everything = mean −2.75%, worse in 4/5 folds** (range
  −5.95…+0.09). It also loses to the plain champion favorite rule in most folds.

## Interpretation (honest, not a blanket "ML can't work")
The arms don't lose because they're siloed — they lose because of **execution cost (the spread)** and
the **absence of a durable edge**, neither of which a joint model over the same features can
manufacture. A flexible model, judged at realizable entry OOS, finds nothing the favorite rule
doesn't already capture. This is consistent with every prior edge attempt collapsing at the
belief-blind / realizable gate.

**What it would take for ML to have a real shot (not present today):**
1. **More data** — 11 days / ~1k events is far too little for a flexible model; needs months.
2. **Richer features we don't yet log** — live order-book depth, trader-identity embeddings,
   cross-market/correlated structure. The stored per-signal features are what the rules already use.
3. **A more predictable target** — outcome is ~efficiently priced; CLV / line-movement may be more
   learnable than win/loss.

**Bearing on the cleanup:** the ML experiment CONFIRMS the money-losing arms have no hidden combined
edge to rescue them — so removing them (keeping favorite / favorite_liq / favorite_v2 / elite_fresh_fav
/ _blind, alerting → favorite) is justified. Nothing was promoted or armed; read-only, paper-only.
