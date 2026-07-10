//! MATCH-LEVEL SUPER-KEY — the honest event-clustering key.
//!
//! A Rust mirror of `scripts/superkey.py::super_event` (the parity oracle). The
//! incumbent cluster key is `COALESCE(event_slug, condition_id)`, but `event_slug`
//! only groups the OUTCOME variants of ONE sub-market. A single real-world match
//! spans several `event_slug`s (game-winner, exact-score, more-markets, …), so
//! clustering on `event_slug` treats one match as up to ~4 "independent events"
//! and inflates N. The honest unit is the MATCH.
//!
//! Rule (documented, deterministic, NO fitting — identical to the Python):
//!   base = event_slug if non-empty else slug
//!   if base contains a YYYY-MM-DD date:
//!       super_key = base up-to-and-INCLUDING the first date
//!   else:
//!       super_key = base                        (dateless markets stay 1:1)
//!
//! Parity with `superkey.py --self-test` is unit-tested below.

/// Return the match-level cluster key. `event_slug` may be empty/None; `slug` is
/// the fallback. Returns `None` when both are empty (the caller then falls back
/// to `condition_id`, matching the incumbent behaviour).
pub fn super_event(event_slug: Option<&str>, slug: &str) -> Option<String> {
    let mut base = event_slug.unwrap_or("").trim();
    if base.is_empty() {
        base = slug.trim();
    }
    if base.is_empty() {
        return None;
    }
    match first_date_end(base) {
        // stem through (and including) the first YYYY-MM-DD; drop the market-type suffix
        Some(end) => Some(base[..end].to_string()),
        // dateless market: 1:1, never coarser than the incumbent key
        None => Some(base.to_string()),
    }
}

/// Byte offset just past the first `\d{4}-\d{2}-\d{2}` substring, or `None`.
/// Mirrors Python's `re.search(r"(\d{4}-\d{2}-\d{2})", base).end()`. ASCII slugs,
/// so byte offsets == char offsets.
fn first_date_end(s: &str) -> Option<usize> {
    let b = s.as_bytes();
    // pattern length is 10: DDDD-DD-DD
    if b.len() < 10 {
        return None;
    }
    for i in 0..=(b.len() - 10) {
        if b[i].is_ascii_digit()
            && b[i + 1].is_ascii_digit()
            && b[i + 2].is_ascii_digit()
            && b[i + 3].is_ascii_digit()
            && b[i + 4] == b'-'
            && b[i + 5].is_ascii_digit()
            && b[i + 6].is_ascii_digit()
            && b[i + 7] == b'-'
            && b[i + 8].is_ascii_digit()
            && b[i + 9].is_ascii_digit()
        {
            return Some(i + 10);
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    // Parity cases copied verbatim from superkey.py `_CASES`:
    // (event_slug, slug, expected, why)
    #[test]
    fn parity_with_python_self_test() {
        let cases: &[(Option<&str>, &str, &str)] = &[
            (
                Some("fifwc-bel-sen-2026-07-01"),
                "fifwc-bel-sen-2026-07-01-bel",
                "fifwc-bel-sen-2026-07-01",
            ),
            (
                Some("fifwc-bel-sen-2026-07-01-exact-score"),
                "fifwc-bel-sen-2026-07-01-exact-score-2-0",
                "fifwc-bel-sen-2026-07-01",
            ),
            (
                Some("fifwc-bel-sen-2026-07-01-more-markets"),
                "fifwc-bel-sen-2026-07-01-spread-home-1pt5",
                "fifwc-bel-sen-2026-07-01",
            ),
            (
                Some(""),
                "fifwc-bel-sen-2026-07-01-total-1pt5",
                "fifwc-bel-sen-2026-07-01",
            ),
            (
                Some("atp-jong-hijikat-2026-06-29"),
                "atp-jong-hijikat-2026-06-29-set-handicap-away-1pt5",
                "atp-jong-hijikat-2026-06-29",
            ),
            (
                Some("mlb-laa-sea-2026-06-30"),
                "mlb-laa-sea-2026-06-30-total-5pt5",
                "mlb-laa-sea-2026-06-30",
            ),
            (
                Some("co-01-democratic-primary-winner"),
                "will-diana-degette-be-the-nominee",
                "co-01-democratic-primary-winner",
            ),
            (
                Some("btc-updown-5m-1782784500"),
                "btc-updown-5m-1782784500",
                "btc-updown-5m-1782784500",
            ),
            (
                Some("lol-t1-tl2-2026-07-01"),
                "lol-t1-tl2-2026-07-01-game3",
                "lol-t1-tl2-2026-07-01",
            ),
            (
                None,
                "fifwc-civ-nor-2026-06-30-exact-score-3-0",
                "fifwc-civ-nor-2026-06-30",
            ),
        ];
        for (evt, slug, want) in cases {
            assert_eq!(
                super_event(*evt, slug).as_deref(),
                Some(*want),
                "super_event({evt:?}, {slug:?})"
            );
        }
    }

    #[test]
    fn belgium_senegal_slugs_collapse_to_one_key() {
        let keys: std::collections::HashSet<_> = [
            super_event(Some("fifwc-bel-sen-2026-07-01"), "x"),
            super_event(Some("fifwc-bel-sen-2026-07-01-exact-score"), "x"),
            super_event(Some("fifwc-bel-sen-2026-07-01-more-markets"), "x"),
            super_event(Some(""), "fifwc-bel-sen-2026-07-01-total-1pt5"),
        ]
        .into_iter()
        .collect();
        assert_eq!(keys.len(), 1);
    }

    #[test]
    fn distinct_dateless_markets_stay_distinct() {
        let a = super_event(Some("co-01-democratic-primary-winner"), "");
        let b = super_event(Some("colorado-governor-democratic-primary-winner"), "");
        assert_ne!(a, b);
    }

    #[test]
    fn idempotent() {
        for (evt, slug) in [
            (Some("fifwc-bel-sen-2026-07-01-exact-score"), "x"),
            (Some("mlb-laa-sea-2026-06-30"), "y"),
            (Some("btc-updown-5m-1782784500"), "z"),
        ] {
            let once = super_event(evt, slug);
            let twice = super_event(once.as_deref(), "");
            assert_eq!(once, twice);
        }
    }

    #[test]
    fn both_empty_returns_none() {
        assert_eq!(super_event(None, ""), None);
        assert_eq!(super_event(Some("  "), "  "), None);
    }
}
