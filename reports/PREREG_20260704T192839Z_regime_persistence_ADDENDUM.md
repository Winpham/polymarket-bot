# PRE-REGISTRATION ADDENDUM — transfer-null correction (leg b)

**Frozen:** 2026-07-04T19:28:39Z (UTC). **Supersedes only §4 leg (b)'s null of**
`PREREG_20260704T191458Z_regime_persistence.md`; every other constant in the original prereg stands
unchanged. Written BEFORE leg (b) is used for any real-data verdict (today's live verdict is
PENDING/SOCCER-ARTIFACT, which is decided by leg (a) + concentration and does NOT depend on leg (b)),
so this correction cannot cherry-pick a result.

## Why the original leg-(b) null was mechanically wrong

The original §4 froze: transfer statistic = # of held-out recurring regimes clearing `LB>MARGIN`;
null = permute regime labels `N` times; **PASS at `p ≤ 0.05` where `p = fraction of null draws ≥
real`** (real in the UPPER tail).

Building it revealed this is mechanically incapable of certifying a genuinely persistent
(regime-distributed) edge, for a concrete reason: permuting regime labels **spreads** a strong
edge's events across ALL pseudo-regimes, so MORE pseudo-regimes clear the margin than the true
grouping — the null count sits **at or above** the real count. A uniformly-strong, genuinely
persistent edge therefore gets `p ≈ 1.0` and can never reach the upper tail. Confirmed empirically:
a synthetic edge present in 3 recurring regimes gives real transfer count 3, null count 3 every draw,
`p = 1.000`. The upper-tail "beat" is unachievable by construction.

The label-permutation null's genuine discriminating power runs in the OTHER direction: it detects
**concentration**. A concentrated (one-lucky-regime) edge yields a LOW real transfer count (hold out
the carrier → the fit pool is flat → "edge exists on fit" fails; hold out a flat regime → it doesn't
clear), while permutation spreads the carrier's mass and INFLATES the null count → the real count
sits in the null's LOWER tail. That is the real, detectable failure mode.

Separately: with a globally-positive edge and an ABSOLUTE `+3%` margin, *any* grouping of the pool
tends to clear, so no edge-destroying null can put a distributed edge in an upper tail either. The
transfer statistic fundamentally measures **distribution vs concentration**, not "beats chance."

## Corrected leg (b) — frozen v2

Transfer statistic unchanged: `real_transfer_count` = # of recurring regimes that, held out, leave a
fit pool with matched-baseline surplus `> 0` AND themselves clear `LB > MARGIN`.

Null unchanged in MECHANISM (regime-label permutation, preserving regime SIZES, `N_PERM_REGIME=1000`,
`SEED=20260704`) but used in the correct DIRECTION — as a **concentration guard**:

- `p_conc = fraction of null draws ≤ real_transfer_count` (real in the LOWER tail ⇒ concentration).
- **concentration-flagged** iff `p_conc < 0.05` (real transfer count is anomalously low vs random
  regrouping ⇒ the transfer is a one-regime artifact).

**leg (b) PASS (frozen v2)** iff ALL of:
1. `real_transfer_count ≥ TRANSFER_MIN_REGIMES` (=2 recurring regimes hold out successfully), AND
2. NOT concentration-flagged (`p_conc ≥ 0.05`).

The temporal out-of-sample persistence evidence remains **leg (a)** (PREREG §4 leg a, unchanged);
`PERSISTS` still requires BOTH legs (a AND b) on recurring regimes (verdict ladder, PREREG §6,
unchanged). So leg (b) is precisely: "the edge is distributed across ≥2 recurring regimes and is NOT
a concentration artifact," layered on top of leg (a)'s "the edge holds out-of-sample on ≥10
independent recurring clusters." Both are necessary; neither alone certifies.

The regime-label-permutation null distribution is reported in full either way (`null_dist`), so a
reviewer sees exactly where the real count sits.

## Unchanged

`TRANSFER_MIN_REGIMES=2`, `N_PERM_REGIME=1000`, `SEED=20260704`, `PERSIST_MIN_CLUSTERS=10`,
`MARGIN=0.03`, `Z=1.96`, the regime taxonomy/type classifier, the matched baseline, the net-after-tax
rule, and the verdict ladder all stand as frozen in `PREREG_20260704T191458Z_regime_persistence.md`.
