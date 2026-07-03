# 2026-07-03 · WS-C — the alert leak: the winners fire silently (build OFF-by-default + shadow + $ cost)

**One line:** the ONLY strategy that has ever pushed an alert is `strict` (243 alerts); `favorite`
and `elite_fresh_fav` — the +EV selection edges — have fired **334 signals and produced 0 alerts**.
An alert-follower therefore acts on the stream that CONTAINS the reliably-losing DODGE residue
(entry 10) and never sees the clean winners. The realizable value leaking out is **≈ +$2,122** (per
$100/bet, resolved net-new winners). The fix needs **no code** — the default-OFF D12 env override
already exists and was never deployed. **Live flip is Tue's call; this run PROPOSES + STOPS.**

## The mechanism (why they're silent)
- `favorite`/`elite_fresh_fav` carry **`alerting: false`** in `default_portfolio()`
  (`consensus.rs`); the alert set is built from `d.alerting` unless the env override
  `CONSENSUS_ALERT_STRATEGIES` is set (`consensus_cycle.rs` L1028), and the push gate
  `if !alerting.contains(sig.strategy) { continue; }` (L474) drops them.
- The intended fix — `CONSENSUS_ALERT_STRATEGIES=strict,favorite,elite_fresh_fav` +
  `CONSENSUS_ALERT_WATCH_FOR=favorite,elite_fresh_fav` (D12) — lives in an untracked `.env.consensus`
  that is **absent from this checkout**, so the built-in `strict`-only default governs. It is a
  **default-OFF flag that already exists**; deploying it IS the fix. Adding new Rust would be
  redundant (extend-don't-rebuild) — so this run builds the SHADOW EVIDENCE, not new code.

## What was built
`scripts/alert_leak_shadow.py` — read-only, `--selftest` (cost-model fixtures PASS). Measures the leak
on the resolved record with the real `consensus_alerts` history, accounting for the cross-strategy
dedup (±60 min, `CONSENSUS_ALERT_CROSS_DEDUP_MINS`) so we count only **net-new** alerts a follower
would actually gain.

## The leak, measured

| | fired | covered by strict (dedup) | **net-new leaked** | resolved | WR | realizable P&L |
|---|---:|---:|---:|---:|---:|---:|
| favorite | 251 | 26 | **225** | 206 | 93.7% | +$1,802 |
| elite_fresh_fav | 83 | 10 | **73** | 64 | 96.9% | +$319 |
| **total** | 334 | 36 | **298** | 270 | — | **+$2,122** |

- **Realized-P&L cost of the leak: ≈ +$2,122** (per $100/bet, flat-shares, entry+1¢ haircut + 2% fee)
  of clean-winner value an alert-follower currently cannot see. For contrast, the entire `strict`
  stream that IS surfaced realized **+$1,052** over its 216 resolved alerts — a mixed stream whose
  non-favorite residue is the DODGE. The winners were worth **~2× the surfaced stream**, silently.
- **Dedup intact:** 298 net-new < 334 fired — 36 winner-signals on markets `strict` already alerted
  are correctly suppressed. Enabling does not double-fire.
- **Spam check:** enabling adds ~59.6 alerts/day to strict's 48.6/day = **2.23× volume** — a sane
  increase, not a blow-up. No rate-limit needed before the flip (revisit if post-WC calendar changes
  volume).

## Caveats (honest)
- The +$2,122 is **realizable** paper P&L on the resolved record — it is the value a follower *left on
  the table*, NOT a certified edge. It is still conditional on δ/λ (WS-A: λ̂ small and INDETERMINATE);
  the leak is a **realized-P&L delivery** problem (right signal reaches the human), separate from the
  edge-reality question.
- The dedup overlap uses a symmetric ±window as a shadow approximation of the runtime's
  fire-time-ordered check; the direction of the estimate is conservative (it can only *remove* alerts).

## Proposal → STOP (Tue's decision)
Deploy the default-OFF override (no code change, no migration):
```
CONSENSUS_ALERT_STRATEGIES=strict,favorite,elite_fresh_fav
CONSENSUS_ALERT_WATCH_FOR=favorite,elite_fresh_fav
```
This surfaces the +EV winners to the alert stream at 2.23× volume with dedup intact. **Flipping alerts
live is one of the two Tue-only decisions — this run merges only the shadow instrument + evidence and
stops here.**
