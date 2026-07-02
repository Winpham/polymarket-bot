//! Rank-cohort model: a first-class, config-driven way to slice the tracked
//! universe by leaderboard rank band.
//!
//! The FIRST band is the **trusted** top cohort (rank ≤ the consensus cutoff —
//! today's top-40); every deeper band is a captured/profiled **candidate** cohort,
//! clearly labeled EXPERIMENTAL and never feeding live alerts. This is the single
//! seam every verification surface (trust, forward record, P&L, capture health)
//! filters and groups by, so the same analytics can be viewed as "top-50 only",
//! "top-250", "all", or "most profitable within each 50-band" without new schema —
//! bands derive from the `rank` we already store.

/// One rank band: `[lo, hi]` inclusive (`hi = None` ⇒ open-ended tail), with a
/// stable label and a `trusted` flag (only the first band is trusted).
#[derive(Debug, Clone, PartialEq)]
pub struct Band {
    /// 0 = the trusted top band; larger = deeper (more experimental).
    pub index: usize,
    /// Inclusive lower rank bound (≥ 1).
    pub lo: i32,
    /// Inclusive upper rank bound; `None` for the open-ended tail (e.g. "501+").
    pub hi: Option<i32>,
    /// Stable display/query label: "1-40", "41-100", …, "251-500", "501+".
    pub label: String,
    /// Only the first (top) band is trusted; all others are candidate cohorts.
    pub trusted: bool,
}

impl Band {
    /// Does `rank` fall in this band? An unranked trader (`None`) never matches a
    /// bounded band — it lands in the open tail via [`band_of`].
    pub fn contains(&self, rank: i32) -> bool {
        rank >= self.lo && self.hi.is_none_or(|hi| rank <= hi)
    }
}

/// Parse a comma-separated list of inclusive upper bounds ("40,100,250,500") into
/// ordered bands plus an open-ended tail. Robust to junk: non-numeric/≤0 entries
/// are dropped, bounds are sorted + deduped. An empty/garbage spec falls back to a
/// single trusted-only split at rank 40. Always yields ≥1 band; the last band is
/// always the open tail so every rank maps somewhere.
pub fn parse_bands(spec: &str) -> Vec<Band> {
    let mut bounds: Vec<i32> = spec
        .split(',')
        .filter_map(|s| s.trim().parse::<i32>().ok())
        .filter(|&n| n >= 1)
        .collect();
    bounds.sort_unstable();
    bounds.dedup();
    if bounds.is_empty() {
        bounds.push(40); // sane fallback: trusted top-40 + tail
    }

    let mut bands = Vec::with_capacity(bounds.len() + 1);
    let mut lo = 1i32;
    for (i, &hi) in bounds.iter().enumerate() {
        bands.push(Band {
            index: i,
            lo,
            hi: Some(hi),
            label: format!("{lo}-{hi}"),
            trusted: i == 0,
        });
        lo = hi + 1;
    }
    // Open-ended tail for anything past the last bound (and unranked traders).
    bands.push(Band {
        index: bounds.len(),
        lo,
        hi: None,
        label: format!("{lo}+"),
        trusted: false,
    });
    bands
}

/// The band a given rank falls into. Unranked (`None`) or ranks past the last
/// bound land in the open tail band (guaranteed to exist). `bands` must come from
/// [`parse_bands`] (ordered, contiguous, tail-terminated).
pub fn band_of(rank: Option<i32>, bands: &[Band]) -> &Band {
    match rank {
        Some(r) => bands
            .iter()
            .find(|b| b.contains(r))
            .unwrap_or_else(|| bands.last().expect("parse_bands yields ≥1 band")),
        None => bands.last().expect("parse_bands yields ≥1 band"),
    }
}

/// A cohort selector for filtering the tracked universe. Maps to a rank predicate
/// so any query/surface can slice consistently: trusted-only (today's top-40),
/// rank ≤ N (e.g. top-250), a single band, or everything captured.
#[derive(Debug, Clone, PartialEq)]
pub enum CohortFilter {
    /// The trusted top band only (rank ≤ the first bound).
    Trusted,
    /// Rank ≤ N (e.g. `Through(250)` = "top-250 only").
    Through(i32),
    /// Exactly one band by index.
    Band(usize),
    /// Everything tracked (trusted + all candidate cohorts).
    All,
}

impl CohortFilter {
    /// Parse a board/query token into a filter. `trusted`/`top50`, `top<N>`/`<N>`,
    /// `band<i>`, or `all` (default). Case-insensitive; unknown ⇒ `All`.
    pub fn parse(token: &str) -> CohortFilter {
        let t = token.trim().to_lowercase();
        match t.as_str() {
            "" | "all" => CohortFilter::All,
            "trusted" | "top50" | "hot" => CohortFilter::Trusted,
            _ => {
                if let Some(n) = t.strip_prefix("top").and_then(|s| s.parse::<i32>().ok()) {
                    CohortFilter::Through(n)
                } else if let Some(i) = t.strip_prefix("band").and_then(|s| s.parse::<usize>().ok())
                {
                    CohortFilter::Band(i)
                } else if let Ok(n) = t.parse::<i32>() {
                    CohortFilter::Through(n)
                } else {
                    CohortFilter::All
                }
            }
        }
    }

    /// Does a trader at `rank` pass this filter? Unranked traders pass only `All`.
    pub fn matches(&self, rank: Option<i32>, bands: &[Band]) -> bool {
        match self {
            CohortFilter::All => true,
            CohortFilter::Trusted => {
                rank.is_some_and(|r| bands.first().is_some_and(|b| b.contains(r)))
            }
            CohortFilter::Through(n) => rank.is_some_and(|r| r <= *n),
            CohortFilter::Band(i) => {
                rank.is_some_and(|r| bands.get(*i).is_some_and(|b| b.contains(r)))
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_bands_default_shape() {
        let b = parse_bands("40,100,250,500");
        assert_eq!(b.len(), 5, "4 bounds + open tail");
        assert_eq!(b[0].label, "1-40");
        assert!(b[0].trusted);
        assert_eq!((b[0].lo, b[0].hi), (1, Some(40)));
        assert_eq!(b[1].label, "41-100");
        assert!(!b[1].trusted);
        assert_eq!(b[4].label, "501+");
        assert_eq!(b[4].hi, None);
        // Contiguous, no gaps.
        for w in b.windows(2) {
            assert_eq!(w[1].lo, w[0].hi.unwrap() + 1, "bands are contiguous");
        }
    }

    #[test]
    fn parse_bands_robust_to_junk() {
        let b = parse_bands(" 100, x, -5, 40 ,40, 100 "); // dupes, junk, unordered
        assert_eq!(
            b.iter().map(|x| x.label.clone()).collect::<Vec<_>>(),
            vec!["1-40", "41-100", "101+"]
        );
        assert!(
            parse_bands("").first().unwrap().trusted,
            "empty spec still yields trusted band"
        );
        assert_eq!(
            parse_bands("garbage").len(),
            2,
            "fallback = trusted(1-40) + tail"
        );
    }

    #[test]
    fn band_of_maps_every_rank() {
        let b = parse_bands("40,100,250,500");
        assert_eq!(band_of(Some(1), &b).label, "1-40");
        assert_eq!(band_of(Some(40), &b).label, "1-40");
        assert_eq!(band_of(Some(41), &b).label, "41-100");
        assert_eq!(band_of(Some(250), &b).label, "101-250");
        assert_eq!(band_of(Some(9999), &b).label, "501+");
        assert_eq!(band_of(None, &b).label, "501+", "unranked → open tail");
    }

    #[test]
    fn cohort_filter_slices() {
        let b = parse_bands("40,100,250,500");
        assert!(CohortFilter::Trusted.matches(Some(40), &b));
        assert!(!CohortFilter::Trusted.matches(Some(41), &b));
        assert!(CohortFilter::Through(250).matches(Some(250), &b));
        assert!(!CohortFilter::Through(250).matches(Some(251), &b));
        assert!(CohortFilter::Band(1).matches(Some(41), &b));
        assert!(!CohortFilter::Band(1).matches(Some(40), &b));
        assert!(CohortFilter::All.matches(None, &b));
        assert!(
            !CohortFilter::Trusted.matches(None, &b),
            "unranked isn't trusted"
        );
    }

    #[test]
    fn cohort_filter_parse_tokens() {
        assert_eq!(CohortFilter::parse("trusted"), CohortFilter::Trusted);
        assert_eq!(CohortFilter::parse("top50"), CohortFilter::Trusted);
        assert_eq!(CohortFilter::parse("top250"), CohortFilter::Through(250));
        assert_eq!(CohortFilter::parse("250"), CohortFilter::Through(250));
        assert_eq!(CohortFilter::parse("band2"), CohortFilter::Band(2));
        assert_eq!(CohortFilter::parse(""), CohortFilter::All);
        assert_eq!(CohortFilter::parse("nonsense"), CohortFilter::All);
    }
}
