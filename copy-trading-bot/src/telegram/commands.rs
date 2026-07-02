//! Telegram command dispatch for the copy-trading bot.

use crate::config::CopyTradingConfig;
use crate::cycles::copy_trade::COPY_TRADER_STARTING_BANKROLL;
use crate::scanner::copy_trader::{
    CopyTraderMonitor, fetch_leaderboard, fetch_trader_username, format_multi_leaderboard,
};
use crate::scanner::trader_trust::{TraderTrust, TrustVerdict, trust_verdict};
use crate::storage::postgres::PgPortfolio;
use crate::telegram::notifier::TelegramNotifier;
use polymarket_common::storage::consensus::TraderSliceStat;

/// Dispatch a single Telegram command and return the reply string.
#[allow(clippy::too_many_arguments)]
pub async fn handle_command(
    cmd: &str,
    chat_id: &str,
    full_text: &str,
    first_name: Option<&str>,
    portfolio: &PgPortfolio,
    notifier: &TelegramNotifier,
    _monitor: &CopyTraderMonitor,
    http: &reqwest::Client,
    cfg: &CopyTradingConfig,
) -> String {
    match cmd {
        "start" => {
            let name = first_name.unwrap_or("there");
            format!(
                "👋 Hi {name}! I'm the Polymarket Copy Trading Bot.\n\n\
                 Commands:\n\
                 /stats — copy trading results\n\
                 /copy — open copy-trade positions\n\
                 /traders — followed traders\n\
                 /leaderboard — top traders\n\
                 /follow — follow a trader (owner)\n\
                 /unfollow — unfollow a trader (owner)\n\
                 /help — show commands"
            )
        }
        "stats" => match portfolio.stats_summary_copy().await {
            Ok(s) => s,
            Err(e) => {
                tracing::warn!(err = %e, "Failed to build copy stats");
                "⚠️ Failed to load stats".to_string()
            }
        },
        "copy" => match portfolio.open_copy_summary().await {
            Ok(s) => s,
            Err(e) => {
                tracing::warn!(err = %e, "Failed to build copy positions");
                "⚠️ Failed to load copy positions".to_string()
            }
        },
        "traders" => match portfolio.traders_summary().await {
            Ok(s) => s,
            Err(e) => {
                tracing::warn!(err = %e, "Failed to build traders summary");
                "⚠️ Failed to load traders".to_string()
            }
        },
        "consensus" => {
            // Headline = the alerting `strict` strategy's live signals.
            let summary = portfolio
                .consensus_summary("strict", 10)
                .await
                .unwrap_or_else(|e| format!("⚠️ Failed to load consensus: {e}"));
            // Per-strategy forward-tracking scoreboard (the portfolio ranking).
            match portfolio.consensus_scoreboard_by_strategy().await {
                Ok(rows) if rows.iter().any(|r| r.resolved > 0) => {
                    use crate::scanner::enrich::family;
                    use crate::scanner::promotion::{
                        PromotionParams, promotion_verdict, selection_null_p_for,
                    };
                    // Bonferroni denominator PER FAMILY: experimental arms are
                    // corrected among themselves, never tightening core's bar.
                    let mut fam_n: std::collections::HashMap<&str, usize> =
                        std::collections::HashMap::new();
                    for r in &rows {
                        *fam_n.entry(family(&r.strategy)).or_default() += 1;
                    }
                    // Same bar as the web board (DECISIONS D3/D6): gate at the
                    // margin a FOLLOWER actually captures (slippage + fee), not
                    // the sharp's own edge (margin 0). The two surfaces must
                    // agree — a promotion read off a looser Telegram ✅ over-promotes.
                    let pp = PromotionParams {
                        margin: cfg.slippage_pct + cfg.fee_pct,
                        ..PromotionParams::default()
                    };
                    let mut board = String::from(
                        "\n\n📊 *Strategy scoreboard* (sorted by surplus-over-blind)\n",
                    );
                    for r in rows.iter().filter(|r| r.resolved > 0) {
                        let hr = r.won as f64 / r.resolved as f64 * 100.0;
                        let fmt_pct = |x: Option<f64>| {
                            x.map(|e| format!("{:+.1}%", e * 100.0))
                                .unwrap_or_else(|| "—".into())
                        };
                        let n_fam = fam_n.get(family(&r.strategy)).copied().unwrap_or(1);
                        let v = promotion_verdict(
                            r.distinct_events,
                            r.distinct_days,
                            r.surplus,
                            r.surplus_sd,
                            n_fam,
                            selection_null_p_for(&r.strategy),
                            &pp,
                        );
                        let flag = if v.promotable { "✅" } else { "⏳" };
                        let lb = fmt_pct(v.lower_bound);
                        board.push_str(&format!(
                            "{} `{:<12}` [{}] {} ev ({:.0}%) · surplus {} (lb {}) · edge {} · clv {} lag {}\n",
                            flag,
                            r.strategy,
                            family(&r.strategy),
                            r.distinct_events,
                            hr,
                            fmt_pct(r.surplus),
                            lb,
                            fmt_pct(r.edge),
                            fmt_pct(r.our_clv),
                            fmt_pct(r.capture_lag),
                        ));
                        if v.promotable {
                            board.push_str(&format!("   └ {}\n", v.reason));
                        }
                    }
                    board.push_str(
                        "\n_✅ = passes the belief-blind promotion gate (Bonferroni-corrected surplus lower-bound > 0 over ≥30 distinct events); ⏳ = not yet. *surplus* = favorite-longshot-neutralized edge. *clv* = edge vs the first captured mid; *lag* < 0 means faster polling has value. Promotion to alerting is a gated human call — never automatic._",
                    );
                    format!("{summary}{board}")
                }
                _ => summary,
            }
        }
        "tracked" => match portfolio.count_tracked_traders().await {
            Ok(n) => format!(
                "🛰 Auto-tracking *{n}* leaderboard traders.\nUse /traders for the full list, /consensus for live signals, /trustedtraders for earned-trust ranking."
            ),
            Err(e) => format!("⚠️ Failed to count tracked traders: {e}"),
        },
        // Earned-trust profile for one wallet (who to actually follow).
        "trader" => {
            let arg = full_text.split_whitespace().nth(1).unwrap_or("");
            if arg.is_empty() {
                "Usage: `/trader <wallet_address>` — earned-trust profile (how profitable, when, with what games).".to_string()
            } else {
                match portfolio.trader_profile(arg).await {
                    Ok((slices, gap)) if !slices.is_empty() => {
                        format_trader_profile(arg, &slices, gap)
                    }
                    Ok(_) => format!(
                        "🪪 No resolved fills captured yet for `{}…` — its profile builds forward as its markets close.",
                        short_id(arg, 8)
                    ),
                    Err(e) => format!("⚠️ Failed to load trader profile: {e}"),
                }
            }
        }
        // Tracked traders ranked by EARNED trust (not leaderboard rank). TTL-cached
        // (shared with the board) — this is a full-archive aggregation.
        "trustedtraders" | "traders-by-trust" => {
            match crate::scanner::trader_trust::cached_slice_scores(
                portfolio,
                std::time::Duration::from_secs(30),
            )
            .await
            {
                Ok(scores) if !scores.is_empty() => format_traders_by_trust(scores),
                Ok(_) => "🏅 No resolved trader fills yet — the earned-trust ranking builds forward as markets close.".to_string(),
                Err(e) => format!("⚠️ Failed to load earned-trust ranking: {e}"),
            }
        }
        "leaderboard" => {
            let (day_res, month_res, all_res) = tokio::join!(
                fetch_leaderboard(http, "DAY"),
                fetch_leaderboard(http, "MONTH"),
                fetch_leaderboard(http, "ALL"),
            );
            match (day_res, month_res, all_res) {
                (Ok(day), Ok(month), Ok(all)) => format_multi_leaderboard(&[
                    ("Today", day.as_slice()),
                    ("This Month", month.as_slice()),
                    ("All Time", all.as_slice()),
                ]),
                (day_res, month_res, all_res) => {
                    if let Err(e) = day_res.as_ref() {
                        tracing::warn!(err = %e, "Failed to fetch DAY leaderboard");
                    }
                    if let Err(e) = month_res.as_ref() {
                        tracing::warn!(err = %e, "Failed to fetch MONTH leaderboard");
                    }
                    if let Err(e) = all_res.as_ref() {
                        tracing::warn!(err = %e, "Failed to fetch ALL leaderboard");
                    }
                    "⚠️ Could not fetch leaderboard — try again shortly.".to_string()
                }
            }
        }
        "follow" => {
            if !notifier.is_owner(chat_id) {
                "🔒 Only the bot owner can follow traders.".to_string()
            } else {
                let arg = full_text.split_whitespace().nth(1).unwrap_or("");
                if arg.is_empty() {
                    "Usage: `/follow <wallet_address>`\n\nTip: use /leaderboard to browse top traders — wallet addresses are shown there for easy copy.".to_string()
                } else {
                    let wallet = arg.to_string();
                    let short = short_id(&wallet, 8);
                    let strat_key = format!("copy:{short}");
                    if let Err(e) = portfolio
                        .ensure_key(
                            &format!("bankroll:{strat_key}"),
                            COPY_TRADER_STARTING_BANKROLL,
                        )
                        .await
                    {
                        tracing::warn!(err = %e, "Failed to init copy trader bankroll");
                    }
                    if let Err(e) = portfolio
                        .ensure_key(
                            &format!("starting_bankroll:{strat_key}"),
                            COPY_TRADER_STARTING_BANKROLL,
                        )
                        .await
                    {
                        tracing::warn!(err = %e, "Failed to init copy trader starting bankroll");
                    }
                    let username = fetch_trader_username(http, &wallet).await;
                    let display = username.as_deref().unwrap_or(&short);
                    match portfolio
                        .add_followed_trader(
                            &wallet,
                            username.as_deref(),
                            "manual",
                            None,
                            None,
                            None,
                        )
                        .await
                    {
                        Ok(()) => format!(
                            "✅ Now following *{display}* (`{short}...`)\n💰 Bankroll: €{:.0}",
                            COPY_TRADER_STARTING_BANKROLL
                        ),
                        Err(e) => format!("⚠️ Failed to follow: {e}"),
                    }
                }
            }
        }
        "unfollow" => {
            if !notifier.is_owner(chat_id) {
                "🔒 Only the bot owner can unfollow traders.".to_string()
            } else {
                let arg = full_text.split_whitespace().nth(1).unwrap_or("");
                if arg.is_empty() {
                    "Usage: `/unfollow <wallet_address>`".to_string()
                } else {
                    match portfolio.deactivate_trader(arg).await {
                        Ok(()) => {
                            let short = short_id(arg, 8);
                            format!("✅ Unfollowed `{short}...`")
                        }
                        Err(e) => format!("⚠️ Failed to unfollow: {e}"),
                    }
                }
            }
        }
        "help" => "📖 *Commands*\n\n\
                 /stats — copy trading results\n\
                 /consensus — live consensus signals + hit-rate\n\
                 /tracked — auto-tracked trader count\n\
                 /trader <wallet> — earned-trust profile for one trader\n\
                 /trustedtraders — traders ranked by earned trust\n\
                 /copy — open copy-trade positions\n\
                 /traders — followed traders\n\
                 /leaderboard — top Polymarket traders\n\
                 /follow — follow a trader (owner)\n\
                 /unfollow — unfollow a trader (owner)\n\
                 /help — this message"
            .to_string(),
        _ => format!("❓ Unknown command: /{cmd}\nTry /help"),
    }
}

/// Plain-English, honesty-first earned-trust profile for one wallet. Always
/// prints the event count and the bound; never presents a thin slice as fact
/// (grey/indeterminate is shown as such). Capture gaps are flagged.
fn format_trader_profile(wallet: &str, slices: &[TraderSliceStat], gap: i32) -> String {
    let t = trust_verdict(slices);
    let short = short_id(wallet, 10);
    let pct = |x: f64| format!("{:+.1}%", x * 100.0);

    let mut out = format!(
        "👤 *Trader* `{short}…`\n{} *{}*",
        t.verdict.marker(),
        t.verdict.as_str()
    );
    if t.n_events > 0 {
        // Show the bound that decided the verdict (lower for Trusted, upper for
        // Avoid) so the headline number is the one that matters.
        let bound = match t.verdict {
            TrustVerdict::Avoid => format!("upper bound {}", pct(t.upper_bound)),
            _ => format!("lower bound {}", pct(t.lower_bound)),
        };
        out.push_str(&format!(
            "\n📈 Surplus {} ({bound}) over {} events",
            pct(t.surplus),
            t.n_events
        ));
    } else {
        out.push_str("\n_No resolved events yet._");
    }

    let best: Vec<String> = t
        .best_slices
        .iter()
        .filter(|(_, _, s)| *s > 0.0)
        .map(|(k, v, s)| format!("{} {}", slice_tag(k, v), pct(*s)))
        .collect();
    if !best.is_empty() {
        out.push_str(&format!("\n✅ Best: {}", best.join(", ")));
    }
    let worst: Vec<String> = t
        .worst_slices
        .iter()
        .filter(|(_, _, s)| *s < 0.0)
        .map(|(k, v, s)| format!("{} {}", slice_tag(k, v), pct(*s)))
        .collect();
    if !worst.is_empty() {
        out.push_str(&format!("\n🔻 Worst: {}", worst.join(", ")));
    }

    for (kind, label) in [("recency7d", "7d"), ("recency30d", "30d")] {
        if let Some(s) = slices.iter().find(|s| s.slice_kind == kind)
            && let Some(su) = s.surplus
        {
            out.push_str(&format!("\n⏱ {label}: {} ({} ev)", pct(su), s.n_events));
        }
    }

    if gap > 0 {
        out.push_str(&format!("\n⚠ partial capture ({gap} gaps)"));
    } else {
        out.push_str("\n✓ capture complete");
    }
    out.push_str(
        "\n\n_Trust is the gate's call: surplus over the trader's-own-band blind baseline, ≥30 distinct events, Bonferroni across slices, one-sided bound. Forward-measured (accrues); grey = indeterminate._",
    );
    out
}

/// Tracked traders ranked by EARNED trust (not leaderboard rank): Trusted first
/// (by lower bound), then Indeterminate (by surplus), then Avoid.
fn format_traders_by_trust(scores: Vec<TraderSliceStat>) -> String {
    use std::collections::HashMap;
    let mut by: HashMap<String, Vec<TraderSliceStat>> = HashMap::new();
    for s in scores {
        by.entry(s.wallet.clone()).or_default().push(s);
    }
    let mut verdicts: Vec<TraderTrust> = by
        .into_values()
        .map(|v| trust_verdict(&v))
        .filter(|t| t.n_events > 0)
        .collect();
    if verdicts.is_empty() {
        return "🏅 No traders with resolved fills yet — the ranking builds forward.".to_string();
    }
    let key = |t: &TraderTrust| match t.verdict {
        TrustVerdict::Trusted => 10.0 + t.lower_bound,
        TrustVerdict::Indeterminate => t.surplus,
        TrustVerdict::Avoid => -10.0 + t.surplus,
    };
    verdicts.sort_by(|a, b| {
        key(b)
            .partial_cmp(&key(a))
            .unwrap_or(std::cmp::Ordering::Equal)
    });

    let pct = |x: f64| format!("{:+.1}%", x * 100.0);
    let mut out = String::from("🏅 *Traders by earned trust* (forward-measured)\n");
    for t in verdicts.iter().take(25) {
        let short = short_id(&t.wallet, 10);
        let bound = match t.verdict {
            TrustVerdict::Avoid => format!("ub {}", pct(t.upper_bound)),
            TrustVerdict::Trusted => format!("lb {}", pct(t.lower_bound)),
            TrustVerdict::Indeterminate => "—".to_string(),
        };
        out.push_str(&format!(
            "\n{} `{short}…` {} ({} · {} ev)",
            t.verdict.marker(),
            pct(t.surplus),
            bound,
            t.n_events
        ));
    }
    out.push_str(
        "\n\n_✅ Trusted · ⏸ indeterminate (not enough events / straddles 0) · ⛔ Avoid. Earned, not leaderboard rank. Surplus = favorite-longshot-neutralized edge._",
    );
    out
}

/// Char-safe short id: first `n` CHARS, never a byte slice. `&s[..n]` panics on a
/// non-char-boundary, and `/trader <arg>` (not owner-gated) takes arbitrary user
/// text — a multibyte arg would otherwise crash the command task and the process.
fn short_id(s: &str, n: usize) -> String {
    s.chars().take(n).collect()
}

/// Friendly display token for a slice (kind, key) in profile output.
fn slice_tag(kind: &str, key: &str) -> String {
    match kind {
        "sport" => key.to_string(),
        "band" => format!("price {key}"),
        _ => key.to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn short_id_is_char_safe_on_multibyte() {
        // Byte-slicing `&s[..8]` would panic mid-char here; short_id must not.
        assert_eq!(short_id("你好世界", 8), "你好世界"); // fewer than 8 chars → whole string
        assert_eq!(short_id("🎰x🎰yz", 3), "🎰x🎰");
        assert_eq!(short_id("0xabcdef1234", 8), "0xabcdef");
        assert_eq!(short_id("", 8), "");
    }

    fn slice(
        kind: &str,
        key: &str,
        n: i64,
        surplus: Option<f64>,
        sd: Option<f64>,
    ) -> TraderSliceStat {
        TraderSliceStat {
            wallet: "0xprofiletest".into(),
            slice_kind: kind.into(),
            slice_key: key.into(),
            n_events: n,
            n_days: n, // one day per event ⇒ no clustering deflation in the fixture
            n_resolved: n,
            surplus,
            surplus_sd: sd,
            mean_adv: surplus,
            hit_rate: Some(0.55),
        }
    }

    #[test]
    fn trader_profile_text_is_honest_and_complete() {
        let slices = vec![
            slice("overall", "", 60, Some(0.12), Some(0.10)),
            slice("sport", "nba", 40, Some(0.18), Some(0.10)),
            slice("sport", "soccer", 30, Some(-0.10), Some(0.10)),
            slice("recency7d", "7d", 12, Some(0.09), Some(0.10)),
        ];
        let out = format_trader_profile("0xprofiletestWALLET", &slices, 0);
        assert!(out.contains("TRUSTED"), "verdict shown: {out}");
        assert!(out.contains("over 60 events"), "N always printed");
        assert!(out.contains("lower bound"), "decisive bound shown");
        assert!(out.contains("nba"), "best game surfaced");
        assert!(out.contains("soccer"), "worst game surfaced");
        assert!(out.contains("7d"), "recency surfaced");
        assert!(out.contains("capture complete"));
    }

    #[test]
    fn trader_profile_flags_partial_capture() {
        let slices = vec![slice("overall", "", 10, Some(0.3), Some(0.05))];
        let out = format_trader_profile("0xpartialwallet", &slices, 4);
        // 10 events < floor ⇒ INDETERMINATE regardless of the point estimate.
        assert!(out.contains("INDETERMINATE"));
        assert!(out.contains("partial capture (4 gaps)"));
    }

    #[test]
    fn traders_by_trust_ranks_trusted_first() {
        let scores = vec![
            // trusted wallet
            TraderSliceStat {
                wallet: "0xgood".into(),
                slice_kind: "overall".into(),
                slice_key: "".into(),
                n_events: 60,
                n_days: 60,
                n_resolved: 60,
                surplus: Some(0.15),
                surplus_sd: Some(0.08),
                mean_adv: Some(0.15),
                hit_rate: Some(0.6),
            },
            // indeterminate wallet
            TraderSliceStat {
                wallet: "0xmeh".into(),
                slice_kind: "overall".into(),
                slice_key: "".into(),
                n_events: 10,
                n_days: 10,
                n_resolved: 10,
                surplus: Some(0.05),
                surplus_sd: Some(0.2),
                mean_adv: Some(0.05),
                hit_rate: Some(0.5),
            },
        ];
        let out = format_traders_by_trust(scores);
        let good = out.find("0xgood").unwrap();
        let meh = out.find("0xmeh").unwrap();
        assert!(good < meh, "trusted trader ranked above indeterminate");
        assert!(out.contains("✅") && out.contains("⏸"));
    }
}
