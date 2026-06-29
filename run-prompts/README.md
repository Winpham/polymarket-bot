# Long-autonomous-run prompts — ML + "every-minute" levers

Forge-validated workstreams (`../FORGE_PLAN_LEVERS.md`) to make highest use of the repo's unused assets,
each a self-contained brief to paste as a fresh long-running session. **Forward-tested via the existing
belief-blind gate — no lever is assumed to add edge; the data decides.**

## How to run (parallel vs sequenced)
| Run | When | Parallel with | Gates |
|-----|------|---------------|-------|
| **[RUN-A — CLV instrumentation](RUN-A-clv-instrumentation.md)** | now | RUN-B | its `capture_lag` output decides RUN-C |
| **[RUN-B — Consensus-native ML arm](RUN-B-consensus-ml-arm.md)** | now | RUN-A | independent |
| **[RUN-C — L1 incremental polling](RUN-C-l1-incremental-polling.md)** | **only if** RUN-A shows `capture_lag` materially negative | after A & B merge | conditional |
| **[RUN-D — Deferred: Bayesian + import-probe](RUN-D-deferred.md)** | later, when A/B have forward data | — | optional |

A and B touch disjoint files (B adds one line to `consensus_cycle.rs`; A doesn't touch it) → **safe to run
in parallel**. C rewrites `consensus_cycle.rs` ingestion → land it after A & B. See FORGE_PLAN_LEVERS.md §"can
we do these in parallel?".

## Shared workflow (every run must follow)
1. **Isolate:** the live bot auto-deploys from `feat/consensus-engine` HEAD — so DON'T commit broken/half work
   there. Work in a dedicated git worktree + branch off `feat/consensus-engine`:
   `git worktree add ../pmkt-<run> -b lever/<run> feat/consensus-engine` and do all edits in `../pmkt-<run>/`.
2. **Stay in your lane:** edit ONLY the files listed in your run's "Owned files". If you must touch a shared
   file (`consensus_cycle.rs`, `config.rs`), make the smallest possible additive change and say so.
3. **Gate before merge (mandatory, the repo's CI):**
   `RUSTFLAGS="--cfg tokio_unstable -Dwarnings" cargo fmt --check --all && cargo clippy --workspace --all-targets && cargo test --workspace`
   For Python (training scripts): `python3 -m py_compile <script>` + a smoke run on a tiny fixture.
4. **Verify live** where it matters (spin a throwaway Postgres via Docker, apply migrations, exercise the path) —
   the repo's established pattern; see DATA-MODEL.md / earlier runs.
5. **Merge the safe way:** rebase onto fresh `feat/consensus-engine` → re-run the gate → `git merge --no-ff` →
   the auto-updater redeploys. Then `git worktree remove`.
6. **Default OFF:** every new variant/flag must leave the live `strict` alerting behavior byte-identical until
   explicitly enabled. New strategy arms are SILENT (`alerting=false`), judged by the gate, never auto-promoted.

## Standing disciplines (from the whole project arc)
- Judge variants on **surplus-over-blind** at the **distinct-EVENT** level (never raw edge / raw N).
- **Forward-only:** skip any signal whose `first_detected_at` precedes a model's `trained_through`.
- Every new silent variant raises the gate's Bonferroni denominator for ALL strategies — keep the count lean;
  if it grows, split the gate into families (FORGE_PLAN_LEVERS.md §"Bonferroni family split").
- Paper/alert-only, free public data only.
