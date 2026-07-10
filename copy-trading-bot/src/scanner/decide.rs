//! The `decide()` kernel — the single, pure decision point that folds the
//! ORPHANED sizing/gating instruments into the one seam where paper P&L is
//! created (`housekeeping.rs`, after the champion `append_paper_bet`).
//!
//! # Why this exists
//! Every resolved signal used to book a flat `$100` to `honest_paper_ledger`,
//! while all the Kelly / capacity / per-sport / readiness machinery sat as
//! report-only scripts that never fed back. This kernel wires them in as a
//! **pure function** so the sizing decision is deterministic, unit-tested, and
//! auditable — and writes a SIZED SHADOW book under a strategy LABEL
//! (`favorite__k12`) in the EXISTING ledger, alongside the untouched champion.
//!
//! # The k=0 posture (LOAD-BEARING — do not "test with k>0")
//! `KELLY_K`, `KELLY_BAND`, and `BANKROLL` are FROZEN constants sourced from
//! `corr_risk_delever.json` — applied, NEVER re-fit. The book runs at **k=0**
//! today because `readiness_fraction` (from `reports/kernel_gate.json`) is `0.0`
//! while the coarse λ̂ ≈ 0.14 leans the favorite surplus toward variance, not
//! information. With `gate == 0` (or an uncertified sport's `m_sport == 0`),
//! `decide()` books `stake == 0` → the shadow book accrues NOTHING until an edge
//! certifies forward. The kernel flips to Kelly by a JSON field change ALONE — no
//! code change, no re-deploy. It is *ready* to size; it does not size a λ→0 edge.

use std::collections::HashMap;

/// Kelly fraction — SETTLED at 1/12 (`corr_risk_delever`: recommended de-levered
/// knee). Applied as a const; NEVER re-fit (a fitted k re-inflates the
/// multiplicity the pinning dissolved).
pub const KELLY_K: f64 = 1.0 / 12.0;

/// Per-band full-Kelly fraction, indexed by `price_band` (0..=5). Bands 4 and 5
/// are the favorite arm (0.6–0.8, 0.8–1.0); the values are `corr_risk_delever`'s
/// `kelly_by_band` {4: 0.1933, 5: 0.5584}. Bands 0–3 are 0 (not the favorite
/// regime this book shadows).
pub const KELLY_BAND: [f64; 6] = [0.0, 0.0, 0.0, 0.0, 0.1933, 0.5584];

/// Headline paper bankroll — `= corr_risk_engine.B_HEADLINE` (10_000), the B on
/// which the k=1/12 knee was pinned. Recorded per row (`sized_bankroll`) so the
/// book is re-scalable if the frontier is ever re-pinned on a different B.
pub const BANKROLL: f64 = 10_000.0;

/// Price → band, an exact mirror of `selection_null.band` / `sport_edge_tracker.band`
/// (`int(p*5)+1`), clamped to `[0, 6]`. `p < 0 → 0`; `p >= 1 → 6`.
pub fn price_band(p: f64) -> usize {
    if p < 0.0 {
        0
    } else if p >= 1.0 {
        6
    } else {
        (p * 5.0) as usize + 1
    }
}

/// Derive the sport cell from the slug, an exact mirror of the SQL `sport_key`
/// CASE in `honest_pnl_by_strategy` (applied to `COALESCE(event_slug, slug)`).
/// First match wins, matching the SQL branch order. Unknown → `"other"`.
pub fn sport_of(event_slug: Option<&str>, slug: &str) -> String {
    let s = event_slug.filter(|e| !e.trim().is_empty()).unwrap_or(slug);
    const CRYPTO: [&str; 9] = [
        "btc", "eth", "sol", "xrp", "bnb", "doge", "hype", "bitcoin", "ethereum",
    ];
    const TENNIS: [&str; 3] = ["atp", "wta", "itf"];
    if CRYPTO.iter().any(|p| s.starts_with(p)) {
        "crypto".into()
    } else if TENNIS.iter().any(|p| s.starts_with(p)) {
        "tennis".into()
    } else if s.starts_with("fifwc") {
        "soccer".into()
    } else if s.starts_with("mlb") {
        "mlb".into()
    } else if s.starts_with("cs") {
        "cs2".into()
    } else {
        "other".into()
    }
}

/// Per-signal features fed to the kernel. Impure gathering (DB/config) happens in
/// the caller; `decide()` itself only reads this struct + the ctx.
#[derive(Debug, Clone)]
pub struct SigFeatures {
    /// The champion strategy being shadowed (e.g. `"favorite"`). The shadow label
    /// is `{source}__k12`.
    pub source: String,
    /// Price band (0..=5) of the realizable entry.
    pub band: usize,
    /// Realizable entry price (for provenance/logging).
    pub entry: f64,
    /// Sport cell (`mlb`/`tennis`/`soccer`/`crypto`/`cs2`/`other`), from the slug.
    pub sport: String,
    /// Number of same-arm unresolved signals sharing this signal's match key —
    /// the correlated cluster size the per-game budget is split across.
    pub game_n: i64,
    /// Capacity ceiling ($). `<= 0.0` means UNSET → no capacity clamp (v1: the
    /// per-market taker depth curve is GAP-6, deferred while λ̂ is bearish).
    pub cap_usd: f64,
    /// Earned-trust multiplier (GAP-8), clamped to [0.5, 1.5] inside `decide()`.
    /// v1 passes 1.0 (neutral); per-signal earned weighting is a later refinement.
    pub earned: f64,
}

/// A single shadow book to append: which ledger label, and the sized stake.
#[derive(Debug, Clone, PartialEq)]
pub struct Book {
    pub label: String,
    pub stake: f64,
}

/// The kernel's decision: the books to append (0 or 1 while k=0) + a recomputable
/// provenance string echoed to logs (band/kelly/mults/cap → stake).
#[derive(Debug, Clone)]
pub struct Decision {
    pub books: Vec<Book>,
    pub reason: String,
}

/// Per-cycle context, built once from `reports/kernel_gate.json`. Absent/unreadable
/// → all-zero (the safe floor: every sport `m_sport = 0`, `readiness_fraction = 0`
/// → k=0). Belief-blind + paper-only invariants live in how this is populated:
/// a nonzero `sport_mult` is written ONLY by `sport_multiplier.py` after clearing
/// the null / entry_ask / holdout / pooling / Bonferroni gate.
#[derive(Debug, Clone, Default)]
pub struct KernelCtx {
    /// Per-sport size coefficient. Unlisted sport → 0.0 (fail-closed).
    pub sport_mult: HashMap<String, f64>,
    /// Edge-readiness fraction: 0.0 = shadow (k=0); 1.0 = Kelly engaged.
    pub readiness_fraction: f64,
}

impl KernelCtx {
    /// Fail-closed sport lookup: unlisted → 0.0.
    pub fn sport_mult(&self, sport: &str) -> f64 {
        self.sport_mult.get(sport).copied().unwrap_or(0.0)
    }

    /// Load from `reports/kernel_gate.json`. ANY error (missing file, bad JSON,
    /// missing fields) → the all-zero floor (k=0). Pure-ish: reads one file, no
    /// network, no mutation.
    pub fn load(path: &str) -> Self {
        match std::fs::read_to_string(path) {
            Ok(s) => Self::from_json(&s).unwrap_or_default(),
            Err(_) => Self::default(),
        }
    }

    /// Parse the gate JSON. Tolerant: any missing/malformed field falls back to
    /// the zero floor for that field.
    pub fn from_json(s: &str) -> Option<Self> {
        let v: serde_json::Value = serde_json::from_str(s).ok()?;
        let sport_mult = v
            .get("sport_mult")
            .and_then(|m| m.as_object())
            .map(|obj| {
                obj.iter()
                    .filter_map(|(k, val)| val.as_f64().map(|f| (k.clone(), f)))
                    .collect()
            })
            .unwrap_or_default();
        let readiness_fraction = v
            .get("readiness_fraction")
            .and_then(|f| f.as_f64())
            .unwrap_or(0.0);
        Some(Self {
            sport_mult,
            readiness_fraction,
        })
    }
}

/// THE KERNEL. Pure: no DB, no network, no clock. `stake = clamp(KELLY_K ·
/// kelly_band[band] · m_sport · gate · earned · BANKROLL / game_n, 0, cap_usd)`.
///
/// While `gate == 0` (today) or `m_sport == 0` (uncertified cell), `stake == 0`
/// and no book is emitted — the shadow book accrues nothing. That is the design.
pub fn decide(f: &SigFeatures, ctx: &KernelCtx) -> Decision {
    let m_sport = ctx.sport_mult(&f.sport);
    let gate = ctx.readiness_fraction;
    let earned = f.earned.clamp(0.5, 1.5);
    let kelly_full = KELLY_BAND[f.band.min(5)];
    let raw = KELLY_K * kelly_full * m_sport * gate * earned * BANKROLL;
    let per_game = raw / (f.game_n.max(1) as f64);
    // Capacity clamp: cap_usd <= 0 means UNSET (no clamp); otherwise clamp down.
    let stake = if f.cap_usd > 0.0 {
        per_game.min(f.cap_usd)
    } else {
        per_game
    }
    .max(0.0);
    let books = if stake > 0.0 {
        vec![Book {
            label: format!("{}__k12", f.source),
            stake,
        }]
    } else {
        vec![]
    };
    let reason = format!(
        "src={} band{} entry={:.3} kelly={:.4} m_sport={:.3} gate={:.3} earned={:.3} \
         game_n={} cap={:.2} -> stake={:.2}",
        f.source, f.band, f.entry, kelly_full, m_sport, gate, earned, f.game_n, f.cap_usd, stake
    );
    Decision { books, reason }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn feat(band: usize, game_n: i64, cap_usd: f64) -> SigFeatures {
        SigFeatures {
            source: "favorite".into(),
            band,
            entry: 0.75,
            sport: "mlb".into(),
            game_n,
            cap_usd,
            earned: 1.0,
        }
    }

    fn ctx_open(sport_mult: f64, gate: f64) -> KernelCtx {
        let mut m = HashMap::new();
        m.insert("mlb".to_string(), sport_mult);
        KernelCtx {
            sport_mult: m,
            readiness_fraction: gate,
        }
    }

    #[test]
    fn sport_of_mirrors_sql_case() {
        assert_eq!(sport_of(Some("mlb-laa-sea-2026-06-30"), "x"), "mlb");
        assert_eq!(sport_of(Some("fifwc-bel-sen-2026-07-01"), "x"), "soccer");
        assert_eq!(sport_of(Some("atp-jong-2026-06-29"), "x"), "tennis");
        assert_eq!(sport_of(Some("btc-updown-5m-1"), "x"), "crypto");
        assert_eq!(sport_of(Some("ethereum-updown"), "x"), "crypto");
        assert_eq!(sport_of(Some("cs2-major-2026"), "x"), "cs2");
        assert_eq!(sport_of(Some("nba-lal-bos-2026"), "x"), "other");
        // empty event_slug falls back to slug
        assert_eq!(sport_of(Some(""), "mlb-nyy-bos-2026-07-01"), "mlb");
        assert_eq!(sport_of(None, "fifwc-civ-nor-2026-06-30"), "soccer");
    }

    #[test]
    fn price_band_matches_int_p5_plus_1() {
        assert_eq!(price_band(-0.1), 0);
        assert_eq!(price_band(0.0), 1);
        assert_eq!(price_band(0.19), 1);
        assert_eq!(price_band(0.65), 4); // favorite low
        assert_eq!(price_band(0.79), 4);
        assert_eq!(price_band(0.8), 5); // favorite high
        assert_eq!(price_band(0.98), 5);
        assert_eq!(price_band(1.0), 6);
        assert_eq!(price_band(1.5), 6);
    }

    #[test]
    fn gate_zero_books_nothing_today() {
        // The mandatory k=0 posture: readiness_fraction = 0 → stake 0 everywhere.
        let ctx = ctx_open(1.0, 0.0);
        for band in [4usize, 5] {
            for game_n in [1i64, 17] {
                let d = decide(&feat(band, game_n, 0.0), &ctx);
                assert!(d.books.is_empty(), "band{band} game_n{game_n} must book 0");
            }
        }
    }

    #[test]
    fn uncertified_sport_books_nothing() {
        // gate open, but sport multiplier 0 (cell not certified) → stake 0.
        let ctx = ctx_open(0.0, 1.0);
        assert!(decide(&feat(5, 1, 0.0), &ctx).books.is_empty());
        // and an unlisted sport is fail-closed 0.0
        let ctx_full = KernelCtx {
            sport_mult: HashMap::new(),
            readiness_fraction: 1.0,
        };
        let mut f = feat(5, 1, 0.0);
        f.sport = "curling".into();
        assert!(decide(&f, &ctx_full).books.is_empty());
    }

    #[test]
    fn band5_full_gate_books_exact_kelly() {
        // gate=1, m_sport=1, earned=1, game_n=1, no cap → exact clamped Kelly.
        let ctx = ctx_open(1.0, 1.0);
        let d = decide(&feat(5, 1, 0.0), &ctx);
        let want = KELLY_K * KELLY_BAND[5] * 1.0 * 1.0 * 1.0 * BANKROLL; // 1/12 * .5584 * 10000
        assert_eq!(d.books.len(), 1);
        assert_eq!(d.books[0].label, "favorite__k12");
        assert!((d.books[0].stake - want).abs() < 1e-9, "got {}", d.books[0].stake);
        assert!((want - 465.333_333).abs() < 1e-3, "sanity: {want}");
    }

    #[test]
    fn band4_full_gate_books_exact_kelly() {
        let ctx = ctx_open(1.0, 1.0);
        let d = decide(&feat(4, 1, 0.0), &ctx);
        let want = KELLY_K * KELLY_BAND[4] * BANKROLL; // 1/12 * .1933 * 10000
        assert!((d.books[0].stake - want).abs() < 1e-9);
    }

    #[test]
    fn game_n_splits_the_budget() {
        let ctx = ctx_open(1.0, 1.0);
        let one = decide(&feat(5, 1, 0.0), &ctx).books[0].stake;
        let seventeen = decide(&feat(5, 17, 0.0), &ctx).books[0].stake;
        assert!((seventeen - one / 17.0).abs() < 1e-9);
    }

    #[test]
    fn capacity_clamps_down() {
        let ctx = ctx_open(1.0, 1.0);
        // uncapped band-5 stake ~465; cap at 50 → 50.
        let d = decide(&feat(5, 1, 50.0), &ctx);
        assert!((d.books[0].stake - 50.0).abs() < 1e-9);
        // cap above the raw stake does not bind.
        let d2 = decide(&feat(5, 1, 10_000.0), &ctx);
        let uncapped = decide(&feat(5, 1, 0.0), &ctx).books[0].stake;
        assert!((d2.books[0].stake - uncapped).abs() < 1e-9);
    }

    #[test]
    fn earned_is_bounded() {
        let ctx = ctx_open(1.0, 1.0);
        let mut hi = feat(5, 1, 0.0);
        hi.earned = 100.0; // clamps to 1.5
        let mut lo = feat(5, 1, 0.0);
        lo.earned = 0.0; // clamps to 0.5
        let base = decide(&feat(5, 1, 0.0), &ctx).books[0].stake;
        assert!((decide(&hi, &ctx).books[0].stake - base * 1.5).abs() < 1e-9);
        assert!((decide(&lo, &ctx).books[0].stake - base * 0.5).abs() < 1e-9);
    }

    #[test]
    fn from_json_all_zero_on_empty_or_bad() {
        assert_eq!(KernelCtx::default().readiness_fraction, 0.0);
        assert!(KernelCtx::from_json("not json").is_none());
        let c = KernelCtx::from_json("{}").unwrap();
        assert_eq!(c.readiness_fraction, 0.0);
        assert_eq!(c.sport_mult("mlb"), 0.0);
    }

    #[test]
    fn on_disk_gate_json_yields_k0_today() {
        // Verify the ACTUAL reports/kernel_gate.json (written by sport_multiplier.py)
        // books stake 0 everywhere — the k=0 posture. Robust when the file is absent
        // (CI without it) → the default all-zero floor also books 0. This test failing
        // means a human flipped readiness_fraction>0 with a certified sport; that is
        // the intended human-review checkpoint, not a spurious failure.
        let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../reports/kernel_gate.json");
        let ctx = KernelCtx::load(path);
        assert_eq!(
            ctx.readiness_fraction, 0.0,
            "today's gate must be k=0 (readiness 0.0); flip is human-review gated"
        );
        for band in [4usize, 5] {
            for sport in ["mlb", "soccer", "tennis", "other", "crypto"] {
                let mut f = feat(band, 1, 0.0);
                f.sport = sport.into();
                assert!(
                    decide(&f, &ctx).books.is_empty(),
                    "on-disk gate must book 0 for {sport} band{band}"
                );
            }
        }
    }

    #[test]
    fn from_json_reads_gate_fields() {
        let j = r#"{"sport_mult":{"mlb":1.0,"soccer":0.0},"readiness_fraction":0.0}"#;
        let c = KernelCtx::from_json(j).unwrap();
        assert_eq!(c.sport_mult("mlb"), 1.0);
        assert_eq!(c.sport_mult("soccer"), 0.0);
        assert_eq!(c.sport_mult("tennis"), 0.0); // unlisted fail-closed
        assert_eq!(c.readiness_fraction, 0.0);
        // With today's readiness 0.0 the kernel still books nothing even though mlb=1.0
        let mut f = feat(5, 1, 0.0);
        f.sport = "mlb".into();
        assert!(decide(&f, &c).books.is_empty());
    }
}
