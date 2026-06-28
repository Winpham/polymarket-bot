use anyhow::{Context, Result};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

/// A single price tick from CLOB history.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PriceTick {
    /// Unix timestamp
    pub t: i64,
    /// Price (0.0 - 1.0)
    pub p: f64,
}

/// Response from the CLOB prices-history endpoint.
#[derive(Debug, Deserialize)]
pub struct PriceHistoryResponse {
    pub history: Vec<PriceTick>,
}

/// A fully resolved market with its history, ready for backtesting.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HistoricalMarket {
    pub market_id: String,
    pub question: String,
    pub token_id: String,
    pub end_date: DateTime<Utc>,
    /// true = YES won, false = NO won
    pub resolved_yes: bool,
    pub price_history: Vec<PriceTick>,
}

impl HistoricalMarket {
    /// Duration of the market in hours based on first and last price tick.
    pub fn duration_hours(&self) -> f64 {
        if self.price_history.len() < 2 {
            return 0.0;
        }
        let first = self.price_history.first().unwrap().t;
        let last = self.price_history.last().unwrap().t;
        (last - first) as f64 / 3600.0
    }
}

/// Compact market info from Gamma API for crawling.
#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct GammaMarket {
    #[serde(rename = "id")]
    pub market_id: String,
    pub question: String,
    #[serde(default)]
    pub clob_token_ids: Option<String>,
    #[serde(default)]
    pub end_date: Option<String>,
    #[serde(default)]
    pub outcome_prices: Option<String>,
    #[serde(default)]
    pub outcomes: Option<String>,
    #[serde(default)]
    pub slug: Option<String>,
    #[serde(default)]
    pub category: Option<String>,
    #[serde(default)]
    pub volume_num: f64,
    #[serde(default)]
    #[allow(dead_code)]
    pub liquidity_num: f64,
    #[serde(default)]
    pub one_day_price_change: Option<f64>,
    #[serde(default)]
    pub one_week_price_change: Option<f64>,
    #[serde(default)]
    pub created_at: Option<String>,
    #[serde(default)]
    pub events: Vec<GammaEvent>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct GammaEvent {
    pub slug: String,
}

impl GammaMarket {
    pub fn event_slug(&self) -> Option<&str> {
        self.events.first().map(|e| e.slug.as_str())
    }

    pub fn resolved_yes(&self) -> Option<bool> {
        let prices_str = self.outcome_prices.as_ref()?;
        let prices: Vec<String> = serde_json::from_str(prices_str).ok()?;
        let yes_price: f64 = prices.first()?.parse().ok()?;
        let no_price: f64 = prices.get(1)?.parse().ok()?;

        if yes_price == 1.0 && no_price == 0.0 {
            Some(true)
        } else if yes_price == 0.0 && no_price == 1.0 {
            Some(false)
        } else {
            None
        }
    }

    /// Per-outcome resolution for consensus forward-tracking. Returns whether the
    /// outcome at `outcome_index` won (`Some(true)`), lost (`Some(false)`), or the
    /// market is not yet resolved / index out of range (`None`). Generalises
    /// [`resolved_yes`] to multi-outcome markets via `outcomePrices[idx]`.
    pub fn resolved_outcome_won(&self, outcome_index: i32) -> Option<bool> {
        if outcome_index < 0 {
            return None;
        }
        let prices_str = self.outcome_prices.as_ref()?;
        let prices: Vec<String> = serde_json::from_str(prices_str).ok()?;
        let p: f64 = prices.get(outcome_index as usize)?.parse().ok()?;
        if p >= 0.99 {
            Some(true)
        } else if p <= 0.01 {
            Some(false)
        } else {
            None
        }
    }

    pub fn yes_token_id(&self) -> Option<String> {
        let ids_str = self.clob_token_ids.as_ref()?;
        let ids: Vec<String> = serde_json::from_str(ids_str).ok()?;
        ids.into_iter().next().filter(|s| !s.is_empty())
    }

    /// True if this is a binary YES/NO market (exactly 2 outcomes).
    /// Multi-outcome markets (e.g. "Who will win?" with 5 candidates) return false.
    pub fn is_binary(&self) -> bool {
        // Check outcomes field: should be ["Yes","No"]
        if let Some(outcomes_str) = &self.outcomes
            && let Ok(outcomes) = serde_json::from_str::<Vec<String>>(outcomes_str)
        {
            return outcomes.len() == 2;
        }
        // Fallback: check token IDs count (binary markets have exactly 2)
        if let Some(ids_str) = &self.clob_token_ids
            && let Ok(ids) = serde_json::from_str::<Vec<String>>(ids_str)
        {
            return ids.len() == 2;
        }
        false
    }

    pub fn polymarket_url(&self) -> String {
        let event_slug = self.events.first().map(|e| e.slug.as_str());
        let market_slug = self.slug.as_deref();
        match event_slug {
            Some(ev) => match market_slug {
                Some(mk) if mk != ev => format!("https://polymarket.com/event/{ev}/{mk}"),
                _ => format!("https://polymarket.com/event/{ev}"),
            },
            None => match market_slug {
                Some(slug) => format!("https://polymarket.com/event/{slug}"),
                None => format!("https://polymarket.com/event/{}", self.market_id),
            },
        }
    }

    pub fn is_crypto_related(&self) -> bool {
        let q = self.question.to_lowercase();
        let cat = self.category.as_deref().unwrap_or_default().to_lowercase();

        const KEYWORDS: &[&str] = &[
            "bitcoin",
            "btc",
            "ethereum",
            "eth",
            "solana",
            "sol",
            "crypto",
            "defi",
            "nft",
            "blockchain",
            "dogecoin",
            "doge",
            "xrp",
            "ripple",
            "cardano",
            "polkadot",
            "avalanche",
            "chainlink",
            "bnb",
            "binance",
            "coinbase",
            "stablecoin",
            "memecoin",
        ];

        KEYWORDS.iter().any(|kw| q.contains(kw)) || cat.contains("crypto")
    }

    /// Returns true for short-duration noise markets (5-min up/down, etc).
    pub fn is_short_duration_noise(&self) -> bool {
        let q = self.question.to_lowercase();
        q.contains("up or down")
    }

    /// Returns true for sports/esports competitive matchups where
    /// prediction models have no edge over market price.
    pub fn is_sports_or_esports(&self) -> bool {
        let q = self.question.to_lowercase();
        q.contains(" vs.")
            || q.contains(" vs ")
            || q.contains("spread:")
            || q.contains("o/u ")
            || q.contains("over/under")
            || q.contains("win on 2")
    }

    /// Extract the YES outcome price from `outcomePrices` / `outcome_prices`.
    pub fn yes_price(&self) -> Option<f64> {
        let s = self.outcome_prices.as_ref()?;
        let p: Vec<String> = serde_json::from_str(s).ok()?;
        p.first().and_then(|v| v.parse::<f64>().ok())
    }
}

const GAMMA_API: &str = "https://gamma-api.polymarket.com";

/// Fetch current YES prices for a batch of market IDs concurrently.
///
/// Returns a `Vec<Option<f64>>` aligned with the input slice.
pub async fn fetch_yes_prices(http: &reqwest::Client, market_ids: &[&str]) -> Vec<Option<f64>> {
    let futs: Vec<_> = market_ids
        .iter()
        .map(|id| {
            let url = format!("{GAMMA_API}/markets/{id}");
            async move {
                let resp = http.get(&url).send().await.ok()?;
                let text = resp.text().await.ok()?;
                let market: GammaMarket = serde_json::from_str(&text).ok()?;
                market.yes_price()
            }
        })
        .collect();
    futures_util::future::join_all(futs).await
}

const CLOB_API: &str = "https://clob.polymarket.com";

/// One outcome token from the CLOB `/markets/{condition_id}` response.
#[derive(Debug, Clone, Deserialize)]
pub struct ClobToken {
    #[serde(default)]
    pub outcome: String,
    /// Live mid price of this outcome in [0,1] — the "stock price" of the outcome.
    #[serde(default)]
    pub price: f64,
    /// True once the market resolves and this outcome won.
    #[serde(default)]
    pub winner: bool,
}

/// CLOB market view keyed by `condition_id`. This is the canonical resolution +
/// live-price source: it works for EVERY market (including sports markets whose
/// slug is absent from Gamma), and gives both `winner` (resolution) and per-token
/// `price` (the live trajectory) in one call.
#[derive(Debug, Clone, Deserialize)]
pub struct ClobMarket {
    #[serde(default)]
    pub closed: bool,
    #[serde(default)]
    pub condition_id: String,
    #[serde(default)]
    pub tokens: Vec<ClobToken>,
}

impl ClobMarket {
    /// Per-outcome resolution: `Some(true/false)` once `closed`, else `None`.
    pub fn outcome_won(&self, outcome_index: i32) -> Option<bool> {
        if !self.closed || outcome_index < 0 {
            return None;
        }
        self.tokens.get(outcome_index as usize).map(|t| t.winner)
    }

    /// Live price of an outcome (the trajectory data point), if present.
    pub fn outcome_price(&self, outcome_index: i32) -> Option<f64> {
        if outcome_index < 0 {
            return None;
        }
        self.tokens.get(outcome_index as usize).map(|t| t.price)
    }
}

/// Fetch the CLOB market for a `condition_id`. Robust resolution + live price.
pub async fn fetch_clob_market(http: &reqwest::Client, condition_id: &str) -> Result<ClobMarket> {
    let url = format!("{CLOB_API}/markets/{condition_id}");
    let resp = http.get(&url).send().await?;
    let text = resp.text().await?;
    let market: ClobMarket = serde_json::from_str(&text)
        .with_context(|| format!("failed to parse CLOB market cond={condition_id}"))?;
    Ok(market)
}

/// Fetch a single market by its slug from the Gamma API.
pub async fn fetch_market_by_slug(http: &reqwest::Client, slug: &str) -> Result<GammaMarket> {
    let url = format!("{GAMMA_API}/markets?slug={slug}");
    let resp = http.get(&url).send().await?;
    let text = resp.text().await?;
    let markets: Vec<GammaMarket> = serde_json::from_str(&text)
        .with_context(|| format!("failed to parse market slug={slug}"))?;
    markets
        .into_iter()
        .next()
        .with_context(|| format!("market slug={slug} not found"))
}

#[cfg(test)]
mod consensus_resolution_tests {
    use super::GammaMarket;

    fn market(outcome_prices: Option<&str>) -> GammaMarket {
        GammaMarket {
            market_id: "1".into(),
            question: "q".into(),
            clob_token_ids: None,
            end_date: None,
            outcome_prices: outcome_prices.map(String::from),
            outcomes: None,
            slug: None,
            category: None,
            volume_num: 0.0,
            liquidity_num: 0.0,
            one_day_price_change: None,
            one_week_price_change: None,
            created_at: None,
            events: vec![],
        }
    }

    #[test]
    fn outcome_won_binary_and_multi() {
        // Binary: outcome 0 won.
        let m = market(Some(r#"["1","0"]"#));
        assert_eq!(m.resolved_outcome_won(0), Some(true));
        assert_eq!(m.resolved_outcome_won(1), Some(false));
        // Multi-outcome: index 2 won.
        let m = market(Some(r#"["0","0","1","0"]"#));
        assert_eq!(m.resolved_outcome_won(2), Some(true));
        assert_eq!(m.resolved_outcome_won(0), Some(false));
    }

    #[test]
    fn clob_resolution_and_price() {
        use super::{ClobMarket, ClobToken};
        let tok = |o: &str, p: f64, w: bool| ClobToken {
            outcome: o.into(),
            price: p,
            winner: w,
        };
        // Resolved binary: outcome 1 (No) won.
        let m = ClobMarket {
            closed: true,
            condition_id: "0xabc".into(),
            tokens: vec![tok("Yes", 0.0, false), tok("No", 1.0, true)],
        };
        assert_eq!(m.outcome_won(0), Some(false));
        assert_eq!(m.outcome_won(1), Some(true));
        assert_eq!(m.outcome_price(1), Some(1.0));
        assert_eq!(m.outcome_won(5), None, "oob index");
        assert_eq!(m.outcome_won(-1), None);

        // Open market: live prices present, no winner yet.
        let open = ClobMarket {
            closed: false,
            condition_id: "0xdef".into(),
            tokens: vec![tok("Yes", 0.62, false), tok("No", 0.38, false)],
        };
        assert_eq!(open.outcome_won(0), None, "open => no resolution");
        assert_eq!(
            open.outcome_price(0),
            Some(0.62),
            "live price still available"
        );
    }

    #[test]
    fn outcome_unresolved_or_oob() {
        // Not yet resolved (prices not 0/1).
        let m = market(Some(r#"["0.55","0.45"]"#));
        assert_eq!(m.resolved_outcome_won(0), None);
        // Out of range / negative / missing prices.
        let m = market(Some(r#"["1","0"]"#));
        assert_eq!(m.resolved_outcome_won(5), None);
        assert_eq!(m.resolved_outcome_won(-1), None);
        assert_eq!(market(None).resolved_outcome_won(0), None);
    }
}
