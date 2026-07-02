//! Minimal read-only web scoreboard — the ntfy-only replacement for the Telegram
//! `/consensus` query. A hand-rolled tokio HTTP server (no extra deps) serves one
//! dark, auto-refreshing page showing each strategy's distinct-event N, hit-rate,
//! surplus-over-blind, and the belief-blind promotion-gate verdict.

use std::sync::Arc;

use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpListener;

use crate::scanner::enrich::family;
use crate::scanner::promotion::{PromotionParams, promotion_verdict, surplus_bounds};
use crate::scanner::trader_trust::{TraderTrust, TrustVerdict, trust_verdict};
use crate::storage::postgres::PgPortfolio;
use polymarket_common::storage::consensus::HonestPnl;

/// Read-only honest-P&L tracker parameters threaded to the board (never touches
/// the live path). `exec_haircut` + `fee_pct` define the realizable entry price
/// (`entry = mid + haircut`, minus `fee_pct` on ROI); the rest parameterize the
/// conservative pilot verdict + capacity sizing.
#[derive(Clone, Copy)]
pub struct HonestBoardParams {
    pub exec_haircut: f64,
    pub fee_pct: f64,
    pub flat_stake: f64,
    pub capacity_frac: f64,
    pub min_pilot_roi: f64,
    pub pilot_min_events: i64,
    pub pilot_min_regimes: i64,
    pub regime_frac: f64,
    pub min_liquidity_usd: f64,
    /// Max `entry_ask_at − first_detected_at` (secs) for a capture to count as
    /// decision-time in the REALIZED (vs modeled) honest ROI column.
    pub realized_decision_lag_secs: f64,
}

impl HonestBoardParams {
    fn thresholds(&self) -> crate::scanner::honest::PilotThresholds {
        crate::scanner::honest::PilotThresholds {
            min_pilot_roi: self.min_pilot_roi,
            min_events: self.pilot_min_events,
            min_regimes: self.pilot_min_regimes,
            regime_frac: self.regime_frac,
            min_liquidity_usd: self.min_liquidity_usd,
            alpha: crate::scanner::promotion::PromotionParams::default().alpha,
        }
    }
}

/// Serve the board on `0.0.0.0:port` forever. Best-effort; logs and retries binds.
pub async fn serve(
    portfolio: Arc<PgPortfolio>,
    port: u16,
    capture_margin: f64,
    honest: HonestBoardParams,
) {
    let listener = match TcpListener::bind(("0.0.0.0", port)).await {
        Ok(l) => l,
        Err(e) => {
            tracing::error!(err = %e, port, "Board server failed to bind");
            return;
        }
    };
    tracing::info!(port, "Read-only scoreboard at http://localhost:{port}/");
    loop {
        let (mut socket, _) = match listener.accept().await {
            Ok(c) => c,
            Err(e) => {
                tracing::warn!(err = %e, "Board accept failed");
                continue;
            }
        };
        let pf = Arc::clone(&portfolio);
        tokio::spawn(async move {
            // Drain the request line (we serve the same page for any GET).
            let mut buf = [0u8; 1024];
            let _ = socket.read(&mut buf).await;
            let html = render(&pf, capture_margin, honest).await;
            let resp = format!(
                "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n\
                 Content-Length: {}\r\nConnection: close\r\n\r\n{}",
                html.len(),
                html
            );
            let _ = socket.write_all(resp.as_bytes()).await;
        });
    }
}

fn pct(x: Option<f64>) -> String {
    x.map(|v| format!("{:+.1}%", v * 100.0))
        .unwrap_or_else(|| "—".into())
}

/// Minimal HTML-attribute escaping for the pilot-reason tooltip (no deps).
fn html_escape(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
}

/// Phase 4 (deep leaderboard): "who's efficient below the whales." Runs the SAME
/// belief-blind trust gate (`trust_verdict`) over the CAPTURED deep pool (rank >
/// cutoff, `consensus_eligible = FALSE` — profiled but not voting) and surfaces
/// any deep trader whose forward-measured surplus clears the gate. Read-only; NO
/// new gate, and nothing here promotes — a deep trader earns a consensus vote only
/// by a deliberate human flip. Renders only when a deep pool is actually tracked,
/// and an honest NULL until it accrues resolved history.
async fn render_deep_efficiency(portfolio: &PgPortfolio) -> String {
    let traders = match portfolio.get_active_traders().await {
        Ok(t) => t,
        Err(_) => return String::new(),
    };
    // Provenance for the depth question: lower-cased wallet → (rank, eligible),
    // leaderboard rows only (manual follows aren't part of hot-vs-deep).
    let mut prov: std::collections::HashMap<String, (Option<i32>, bool)> =
        std::collections::HashMap::new();
    for t in &traders {
        if t.source == "leaderboard" {
            prov.insert(
                t.proxy_wallet.to_lowercase(),
                (t.rank, t.consensus_eligible),
            );
        }
    }
    // No deep (ineligible) traders ⇒ depth widening isn't on ⇒ nothing to render
    // (keeps the board byte-identical at the top-40 default).
    if !prov.values().any(|(_, eligible)| !*eligible) {
        return String::new();
    }

    let scores = match crate::scanner::trader_trust::cached_slice_scores(
        portfolio,
        std::time::Duration::from_secs(30),
    )
    .await
    {
        Ok(s) => s,
        Err(_) => return String::new(),
    };
    let mut by: std::collections::HashMap<String, Vec<_>> = std::collections::HashMap::new();
    for s in scores {
        by.entry(s.wallet.clone()).or_default().push(s);
    }

    struct DeepRow {
        wallet: String,
        rank: Option<i32>,
        t: TraderTrust,
    }
    let mut deep_rows: Vec<DeepRow> = Vec::new();
    let (mut hot_certified, mut deep_profiled, mut deep_certified) = (0usize, 0usize, 0usize);
    for (w, slices) in by {
        let (rank, eligible) = match prov.get(&w) {
            Some(x) => *x,
            None => continue, // manual / untracked — not part of the depth question
        };
        let t = trust_verdict(&slices);
        if t.n_events == 0 {
            continue;
        }
        if eligible {
            if matches!(t.verdict, TrustVerdict::Trusted) {
                hot_certified += 1;
            }
        } else {
            deep_profiled += 1;
            if matches!(t.verdict, TrustVerdict::Trusted) {
                deep_certified += 1;
            }
            deep_rows.push(DeepRow { wallet: w, rank, t });
        }
    }

    // Deep pool tracked but NO resolved history yet — the honest NULL.
    if deep_profiled == 0 {
        return String::from(
            "<h1 style='margin-top:34px'>🔎 Efficient below the whales</h1>\
             <p class=sub>Deep pool (rank &gt; cutoff) is captured but has no resolved history \
             yet — the efficiency verdict pends forward accrual. NULL for now, by construction.</p>",
        );
    }

    let key = |t: &TraderTrust| match t.verdict {
        TrustVerdict::Trusted => 10.0 + t.lower_bound,
        TrustVerdict::Indeterminate => t.surplus,
        TrustVerdict::Avoid => -10.0 + t.surplus,
    };
    deep_rows.sort_by(|a, b| {
        key(&b.t)
            .partial_cmp(&key(&a.t))
            .unwrap_or(std::cmp::Ordering::Equal)
    });

    let mut out = format!(
        "<h1 style='margin-top:34px'>🔎 Efficient below the whales</h1>\
         <p class=sub>Deep pool profiled: {deep_profiled} · certified (Trusted): {deep_certified} · \
         top-50 certified: {hot_certified}. Same belief-blind gate; nothing here promotes.</p>\
         <table><thead><tr><th>trust</th><th>wallet</th><th class=r>lb rank</th>\
         <th class=r>events (N)</th><th class=r>surplus</th><th class=r>bound</th></tr></thead><tbody>",
    );
    for r in deep_rows.iter().take(25) {
        let (marker, scls) = match r.t.verdict {
            TrustVerdict::Trusted => ("✅", "pos"),
            TrustVerdict::Avoid => ("⛔", "neg"),
            TrustVerdict::Indeterminate => ("⏸", "muted"),
        };
        let bound = match r.t.verdict {
            TrustVerdict::Avoid => pct(Some(r.t.upper_bound)),
            TrustVerdict::Trusted => pct(Some(r.t.lower_bound)),
            TrustVerdict::Indeterminate => "—".into(),
        };
        let rank = r.rank.map(|x| x.to_string()).unwrap_or_else(|| "—".into());
        let short: String = r.wallet.chars().take(12).collect();
        out.push_str(&format!(
            "<tr><td>{marker}</td><td class=mono>{short}…</td><td class=r>{rank}</td>\
             <td class=r>{ev}</td><td class=\"r {scls}\">{surplus}</td><td class=r>{bound}</td></tr>",
            ev = r.t.n_events,
            surplus = pct(Some(r.t.surplus)),
        ));
    }
    out.push_str(
        "</tbody></table>\
         <p class=note>The deep pool is a CANDIDATE universe, not trust. A ✅ here means a \
         sub-whale trader's forward surplus clears the same gate the top-50 face — a candidate to \
         earn a consensus vote, by a deliberate human flip, never automatically. An empty/all-⏸ \
         list is an honest finding: depth 51+ carries no certified edge the top-50 lacked (yet).</p>",
    );
    out
}

/// Render the earned trader-trust table ("who to actually follow"): each tracked
/// trader with resolved fills, ranked by earned trust, with best/worst games,
/// surplus ± bound, and capture completeness. Empty until fills resolve.
async fn render_trust(portfolio: &PgPortfolio) -> String {
    // TTL-cached: the board auto-refreshes every 30s, and this is a full-archive
    // aggregation — recomputing it per render would re-scan the whole table. On a
    // DB error, render nothing for this section (the rest of the board still shows).
    let scores = match crate::scanner::trader_trust::cached_slice_scores(
        portfolio,
        std::time::Duration::from_secs(30),
    )
    .await
    {
        Ok(s) if !s.is_empty() => s,
        _ => return String::new(),
    };
    let gaps = portfolio.capture_gaps().await.unwrap_or_default();

    let mut by: std::collections::HashMap<String, Vec<_>> = std::collections::HashMap::new();
    for s in scores {
        by.entry(s.wallet.clone()).or_default().push(s);
    }
    let mut verdicts: Vec<TraderTrust> = by
        .into_values()
        .map(|v| trust_verdict(&v))
        .filter(|t| t.n_events > 0)
        .collect();
    if verdicts.is_empty() {
        return String::new();
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

    let mut out = String::from(
        "<h1 style='margin-top:34px'>👥 Trader trust</h1>\
         <p class=sub>Who to actually follow — earned, not leaderboard rank. Forward-measured.</p>\
         <table><thead><tr><th>trust</th><th>wallet</th><th class=r>events (N)</th>\
         <th class=r>surplus</th><th class=r>bound</th><th>best games</th><th>capture</th>\
         </tr></thead><tbody>",
    );
    for t in verdicts.iter().take(50) {
        let (marker, scls) = match t.verdict {
            TrustVerdict::Trusted => ("✅", "pos"),
            TrustVerdict::Avoid => ("⛔", "neg"),
            TrustVerdict::Indeterminate => ("⏸", "muted"),
        };
        let bound = match t.verdict {
            TrustVerdict::Avoid => pct(Some(t.upper_bound)),
            TrustVerdict::Trusted => pct(Some(t.lower_bound)),
            TrustVerdict::Indeterminate => "—".into(),
        };
        let best: String = t
            .best_slices
            .iter()
            .filter(|(_, _, s)| *s > 0.0)
            .take(2)
            .map(|(k, v, s)| format!("{}:{} {}", k, v, pct(Some(*s))))
            .collect::<Vec<_>>()
            .join(", ");
        let cap = match gaps.get(&t.wallet) {
            Some(g) if *g > 0 => format!("⚠ {g} gaps"),
            _ => "✓".to_string(),
        };
        let short: String = t.wallet.chars().take(12).collect();
        out.push_str(&format!(
            "<tr><td>{marker}</td><td class=mono>{short}…</td><td class=r>{ev}</td>\
             <td class=\"r {scls}\">{surplus}</td><td class=r>{bound}</td>\
             <td class=muted>{best}</td><td class=muted>{cap}</td></tr>",
            ev = t.n_events,
            surplus = pct(Some(t.surplus)),
        ));
    }
    out.push_str(
        "</tbody></table>\
         <p class=note>✅ Trusted (surplus lower bound &gt; 0 over ≥30 distinct events, Bonferroni \
         across the wallet's slices) · ⏸ indeterminate · ⛔ Avoid (upper bound &lt; 0). \
         <b>surplus</b> = edge over the trader's-own-band blind baseline (favorite-longshot-neutralized). \
         <b>capture</b> ⚠ = the data-api dropped trades between polls (partial history).</p>",
    );
    out
}

/// A unicode block sparkline (▁▂▃▄▅▆▇█) from a series — the equity curve at a glance.
fn sparkline(series: &[f64]) -> String {
    if series.len() < 2 {
        return "—".into();
    }
    const BARS: [char; 8] = ['▁', '▂', '▃', '▄', '▅', '▆', '▇', '█'];
    let (mut lo, mut hi) = (f64::INFINITY, f64::NEG_INFINITY);
    for &v in series {
        lo = lo.min(v);
        hi = hi.max(v);
    }
    let span = (hi - lo).max(1e-9);
    series
        .iter()
        .map(|&v| {
            let idx = (((v - lo) / span) * 7.0).round().clamp(0.0, 7.0) as usize;
            BARS[idx]
        })
        .collect()
}

/// Render the **honest, realizable** P&L panel (read-only): per strategy the
/// CLV-based ROI net of the execution haircut, the conservative pilot GO/HOLD
/// verdict (corrected bound + regime persistence + liquidity), capacity sizing,
/// and the PAPER equity sparkline + max drawdown. Realizable, not flattering.
async fn render_honest(portfolio: &PgPortfolio, honest: HonestBoardParams) -> String {
    let rows = match portfolio
        .honest_pnl_by_strategy(
            honest.exec_haircut,
            honest.fee_pct,
            honest.realized_decision_lag_secs,
        )
        .await
    {
        Ok(r) if r.iter().any(|x| x.resolved > 0) => r,
        _ => return String::new(),
    };
    let segs = portfolio
        .honest_pnl_segments(honest.exec_haircut, honest.fee_pct)
        .await
        .unwrap_or_default();
    let th = honest.thresholds();
    // Shared verdict machinery (identical to the digest — they can't drift).
    let verdicts = crate::scanner::honest::verdicts_by_strategy(&rows, &segs, &th);

    // REALIZED corrected lower bound per strategy — the belief-blind gate's exact
    // z/SE machinery (same as the modeled verdict), but computed on the MEASURED
    // decision-time real-ask ROI (`realized_roi` over `realized_events`). Bonferroni
    // family = strategies-with-resolved-rows per family, identical to the modeled
    // verdict, so the two LBs are apples-to-apples.
    let mut fam_n: std::collections::HashMap<&str, usize> = std::collections::HashMap::new();
    for r in rows.iter().filter(|r| r.resolved > 0) {
        *fam_n.entry(family(&r.strategy)).or_default() += 1;
    }
    let realized_params = PromotionParams {
        min_events: th.min_events,
        margin: th.min_pilot_roi,
        alpha: th.alpha,
    };
    let realized_lb = |r: &HonestPnl| -> Option<f64> {
        let n = r.realized_events.filter(|&n| n > 0)?;
        let roi = r.realized_roi?;
        let nf = fam_n.get(family(&r.strategy)).copied().unwrap_or(1);
        let (lb, _) = surplus_bounds(n, roi, r.realized_roi_sd, nf, &realized_params);
        Some(lb)
    };

    // Build (row, verdict, capacity, ledger-stats), then sort GO-first / LB desc.
    let mut items = Vec::new();
    for r in rows.iter().filter(|r| r.resolved > 0) {
        let Some(sv) = verdicts.get(&r.strategy) else {
            continue;
        };
        let cap = crate::scanner::honest::capacity(
            honest.flat_stake,
            honest.capacity_frac,
            r.median_sharp_usd,
            r.bets_per_day,
            r.avg_hours_to_resolve,
            r.honest_roi,
        );
        let ledger = portfolio.ledger_stats(&r.strategy).await.unwrap_or(None);
        items.push((r, sv.clone(), cap, ledger));
    }
    items.sort_by(|a, b| {
        b.1.verdict.go.cmp(&a.1.verdict.go).then(
            b.1.verdict
                .corrected_lower_bound
                .unwrap_or(f64::NEG_INFINITY)
                .partial_cmp(
                    &a.1.verdict
                        .corrected_lower_bound
                        .unwrap_or(f64::NEG_INFINITY),
                )
                .unwrap_or(std::cmp::Ordering::Equal),
        )
    });

    let mut out = String::from(
        "<h1 style='margin-top:34px'>💵 Honest P&amp;L (realizable · paper)</h1>\
         <p class=sub>Outcome vs the mid we saw while OPEN (CLV), net of the execution haircut — \
         the edge we could actually realize. Event-clustered, multi-regime. Paper only, NO real money.</p>\
         <table><thead><tr><th>pilot</th><th>strategy</th><th class=r>events (N)</th>\
         <th class=r>honest ROI<br><span class=muted>(modeled)</span></th>\
         <th class=r>realized ROI<br><span class=muted>(real ask)</span></th>\
         <th class=r>corrected LB<br><span class=muted>(modeled)</span></th>\
         <th class=r>realized LB</th><th class=r>regimes+</th>\
         <th class=r>CLV</th><th class=r>sharp edge</th><th class=r>stake</th>\
         <th class=r>proj $/wk</th><th>paper equity</th><th class=r>max DD</th>\
         </tr></thead><tbody>",
    );
    for (r, sv, cap, ledger) in &items {
        let verdict = &sv.verdict;
        let (marker, mcls) = if verdict.go {
            ("✅ GO", "pos")
        } else {
            ("⏳ HOLD", "muted")
        };
        let hrcls = match r.honest_roi {
            Some(v) if v > 0.0 => "pos",
            Some(_) => "neg",
            None => "muted",
        };
        let (spark, dd, equity) = match ledger {
            Some(l) => (
                sparkline(&l.curve),
                format!("${:.0}", l.max_drawdown),
                format!("${:+.0}", l.total_pnl),
            ),
            None => ("—".into(), "—".into(), String::new()),
        };
        let rroi = realized_lb(r); // realized corrected LB (None ⇒ no real-ask data)
        // Measured real haircut vs the assumed EXEC_HAIRCUT — the whole point.
        let haircut_txt = r
            .median_haircut
            .map(|h| {
                format!(
                    "real haircut {:+.1}¢ (assumed {:.1}¢)",
                    h * 100.0,
                    honest.exec_haircut * 100.0
                )
            })
            .unwrap_or_else(|| "real haircut n/a (no ask captured)".into());
        let tip = format!(
            "{}  ·  working capital ≈ ${:.0}  ·  real-ask coverage {}  ·  decision-time coverage {}  ·  {}  ·  paper equity {}",
            verdict.reason,
            cap.working_capital,
            r.ask_coverage
                .map(|c| format!("{:.0}%", c * 100.0))
                .unwrap_or_else(|| "0% (heuristic haircut)".into()),
            r.decision_coverage
                .map(|c| format!("{:.0}% (N={})", c * 100.0, r.realized_events.unwrap_or(0)))
                .unwrap_or_else(|| "0%".into()),
            haircut_txt,
            if equity.is_empty() {
                "no bets".into()
            } else {
                equity
            },
        );
        let rrcls = match r.realized_roi {
            Some(v) if v > 0.0 => "pos",
            Some(_) => "neg",
            None => "muted",
        };
        out.push_str(&format!(
            "<tr title=\"{reason}\"><td class={mcls}>{marker}</td><td class=mono>{strat}</td>\
             <td class=r>{ev}</td><td class=\"r {hrcls}\">{hroi}</td>\
             <td class=\"r {rrcls}\">{rroi_v}</td><td class=r>{lb}</td><td class=r>{rlb}</td>\
             <td class=r>{rp}/{rt}</td><td class=r>{clv}</td><td class=\"r muted\">{sharp}</td>\
             <td class=\"r muted\">${stake:.0}</td><td class=\"r muted\">${projwk:.0}</td>\
             <td class=mono>{spark}</td><td class=\"r muted\">{dd}</td></tr>",
            reason = html_escape(&tip),
            strat = r.strategy,
            ev = r.distinct_events,
            hroi = pct(r.honest_roi),
            rroi_v = pct(r.realized_roi),
            lb = pct(verdict.corrected_lower_bound),
            rlb = pct(rroi),
            rp = sv.regimes_positive,
            rt = sv.regimes_total,
            clv = pct(r.clv_share),
            sharp = pct(r.sharp_edge),
            stake = cap.suggested_stake,
            projwk = cap.projected_weekly,
        ));
    }
    out.push_str(&format!(
        "</tbody></table>\
         <p class=note><b>honest ROI (modeled)</b> = event-clustered `AVG((outcome − entry)/entry − fee)` with \
         <b>entry = captured mid + {hc:.0}¢ assumed haircut</b> — the realizable per-$ edge (NOT the sharps' fill). \
         <b>realized ROI (real ask)</b> = the SAME formula but entry = the REAL decision-time book ask \
         (`entry_ask`, captured within the decision-time window), over just those rows — the MEASURED edge, \
         no haircut assumption. When realized &lt; modeled, the assumed haircut was too kind (the tooltip shows \
         the measured real haircut vs assumed, and decision-time coverage). Both LBs are Bonferroni-corrected \
         1-sided lower bounds on their own ROI. “—” = no real decision-time ask captured yet. \
         ✅ GO requires ALL: LB &gt; {bar:+.0}%, N ≥ {ev} events, ≥{regfrac:.0}% of day-regimes positive \
         (≥{minreg}), and liquidity ≥ ${liq:.0}. Conservative by design — a false GO risks real money, so the \
         default is HOLD (hover a row for the binding reason + working capital). <b>sharp edge</b> = outcome − \
         sharps' mean price, reference only. <b>stake</b> = min(flat, {capfrac:.0}% × median $); <b>paper equity</b> \
         = cumulative paper P&amp;L sparkline; <b>max DD</b> = peak-to-trough $. Promotion to real money is a \
         deliberate human call — never automatic. NO real money is placed.</p>",
        hc = honest.exec_haircut * 100.0,
        bar = honest.min_pilot_roi * 100.0,
        ev = honest.pilot_min_events,
        regfrac = honest.regime_frac * 100.0,
        minreg = honest.pilot_min_regimes,
        liq = honest.min_liquidity_usd,
        capfrac = honest.capacity_frac * 100.0,
    ));
    out
}

async fn render(portfolio: &PgPortfolio, capture_margin: f64, honest: HonestBoardParams) -> String {
    let rows = portfolio
        .consensus_scoreboard_by_strategy()
        .await
        .unwrap_or_default();
    let tracked = portfolio.count_tracked_traders().await.unwrap_or(0);
    let (hot, deep) = portfolio.count_tracked_split().await.unwrap_or((0, 0));
    let n429 = polymarket_common::metrics::data_api_429_count();
    let (poll_n, poll_ms) = polymarket_common::metrics::consensus_last_poll();
    // Phase 0 (capture margin): gate arms at the bar a *follower* actually captures —
    // `slippage_pct + fee_pct` — not the sharp's own edge (margin 0). Only edges whose
    // Bonferroni lower bound clears the fees+slippage cushion render ✅. This raises the
    // bar for every arm; it does NOT touch `strict` alerting or `trader_trust` (a
    // deliberately different "better than blind" question, margin 0). See DECISIONS.md D3.
    let pp = PromotionParams {
        margin: capture_margin,
        ..PromotionParams::default()
    };
    let n = rows.len();
    // Bonferroni denominator PER FAMILY: experimental arms are corrected among
    // themselves, so adding them never tightens the core portfolio's bar.
    let mut fam_n: std::collections::HashMap<&str, usize> = std::collections::HashMap::new();
    for r in &rows {
        *fam_n.entry(family(&r.strategy)).or_default() += 1;
    }

    let mut body = String::new();

    // --- market_resid accrual line: how close the price-LEVEL-free arm is to its
    //     first honest gate read (≥30 distinct resolved events). ---
    let (mr_events, mr_rows) = portfolio
        .market_feature_log_accrual()
        .await
        .unwrap_or((0, 0));
    let mr_skipped = polymarket_common::metrics::market_multi_outcome_skipped_count();
    // If the arm has emitted resolved rows it is loaded + non-placeholder (a
    // placeholder is refused at load), so its promotion verdict is meaningful.
    let mr_gate = rows
        .iter()
        .find(|r| r.strategy == "market_resid" && r.resolved > 0)
        .map(|r| {
            let fn_exp = fam_n.get("experimental").copied().unwrap_or(1);
            let v = promotion_verdict(r.distinct_events, r.surplus, r.surplus_sd, fn_exp, &pp);
            if v.promotable {
                format!("✅ PROMOTABLE (LB {})", pct(v.lower_bound))
            } else {
                format!("⏳ not yet (LB {})", pct(v.lower_bound))
            }
        })
        .unwrap_or_else(|| "— arm silent / not accruing arm rows".into());
    let mr_floor = if mr_events >= 30 { "✓" } else { "…" };
    body.push_str(&format!(
        "<p class=accrual><b>market_resid accrual</b> (price-LEVEL-free residual arm): \
         <b>{mr_events}/30</b> resolved events {mr_floor} · {mr_rows} feature rows logged · \
         {mr_skipped} multi-outcome markets skipped · gate: {mr_gate}</p>"
    ));

    let have_results = rows.iter().any(|r| r.resolved > 0);
    if !have_results {
        body.push_str(
            "<p class=muted>No resolved signals yet. Strategies are tracking forward silently — \
             this table fills in as markets close (sports next-day, others over days).</p>",
        );
    } else {
        body.push_str(
            "<table><thead><tr><th>gate</th><th>strategy</th><th>family</th><th class=r>events (N)</th>\
             <th class=r>hit-rate</th><th class=r>surplus</th><th class=r>lower bound</th>\
             <th class=r>raw edge</th><th class=r>our CLV</th><th class=r>capture lag</th>\
             </tr></thead><tbody>",
        );
        for r in rows.iter().filter(|r| r.resolved > 0) {
            let hr = r.won as f64 / r.resolved as f64 * 100.0;
            let n = fam_n.get(family(&r.strategy)).copied().unwrap_or(1);
            let v = promotion_verdict(r.distinct_events, r.surplus, r.surplus_sd, n, &pp);
            let gate = if v.promotable { "✅" } else { "⏳" };
            let scls = match r.surplus {
                Some(s) if s > 0.0 => "pos",
                Some(_) => "neg",
                None => "muted",
            };
            // CLV: positive is good (we'd beat the captured mid). capture lag:
            // negative means the mid had already moved past the sharps' entry.
            let clvcls = match r.our_clv {
                Some(c) if c > 0.0 => "pos",
                Some(_) => "neg",
                None => "muted",
            };
            body.push_str(&format!(
                "<tr><td>{gate}</td><td class=mono>{strat}</td><td class=muted>{fam}</td>\
                 <td class=r>{ev}</td>\
                 <td class=r>{hr:.0}%</td><td class=\"r {scls}\">{surplus}</td>\
                 <td class=r>{lb}</td><td class=\"r muted\">{edge}</td>\
                 <td class=\"r {clvcls}\">{clv}</td><td class=\"r muted\">{lag}</td></tr>",
                strat = r.strategy,
                fam = family(&r.strategy),
                ev = r.distinct_events,
                surplus = pct(r.surplus),
                lb = pct(v.lower_bound),
                edge = pct(r.edge),
                clv = pct(r.our_clv),
                lag = pct(r.capture_lag),
            ));
        }
        body.push_str("</tbody></table>");
    }

    // --- Honest, realizable P&L panel (CLV − execution haircut; read-only) ---
    body.push_str(&render_honest(portfolio, honest).await);

    // --- Earned trader trust ("who to actually follow") ---
    body.push_str(&render_trust(portfolio).await);

    // --- Deep-pool efficiency ("who's efficient below the whales") ---
    body.push_str(&render_deep_efficiency(portfolio).await);

    format!(
        "<!doctype html><html><head><meta charset=utf-8>\
         <meta name=viewport content='width=device-width,initial-scale=1'>\
         <meta http-equiv=refresh content=30><title>Consensus scoreboard</title>\
         <style>\
         body{{background:#0b0d10;color:#e6e9ef;font:15px/1.5 -apple-system,Inter,system-ui,sans-serif;margin:0;padding:28px;max-width:820px}}\
         h1{{font-size:19px;margin:0 0 2px}} .sub{{color:#8a93a3;font-size:13px;margin:0 0 20px}}\
         table{{border-collapse:collapse;width:100%}} th,td{{padding:8px 10px;border-bottom:1px solid #1c2128;text-align:left}}\
         th{{color:#8a93a3;font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.04em}}\
         .r{{text-align:right;font-variant-numeric:tabular-nums}} .mono{{font-family:ui-monospace,Menlo,monospace}}\
         .pos{{color:#3fb950}} .neg{{color:#f85149}} .muted{{color:#8a93a3}}\
         .note{{color:#8a93a3;font-size:12px;margin-top:18px;border-top:1px solid #1c2128;padding-top:14px}}\
         .accrual{{background:#11151b;border:1px solid #1c2128;border-radius:8px;padding:10px 12px;font-size:13px;color:#c3cad6;margin:0 0 18px}}\
         </style></head><body>\
         <h1>🤝 Consensus scoreboard</h1>\
         <p class=sub>Tracking {tracked} traders ({hot} hot · {deep} deep) · {n} strategies forward · last poll: {poll_n} in {poll_ms}ms · data-api 429s: {n429} · auto-refresh 30s</p>\
         {body}\
         <p class=note><b>surplus</b> = edge over the band-matched blind baseline (favorite-longshot-neutralized) — \
         the real signal. <b>lower bound</b> = Bonferroni-corrected 1-sided bound. ✅ = passes the belief-blind \
         promotion gate (lower bound &gt; 0 over ≥30 distinct events); ⏳ = not yet. Promotion to alerting is a \
         deliberate human call — never automatic. <b>our CLV</b> = edge if we'd entered at the first live mid we \
         captured (event-clustered). <b>capture lag</b> = first mid − sharps' entry; materially negative means \
         faster polling has real value. <b>family</b> = Bonferroni group: <i>experimental</i> cross-check arms are \
         corrected among themselves, so they never tighten the <i>core</i> portfolio's bar.</p>\
         </body></html>",
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    // Live: seed a resolved fill population, render the board, assert the trust
    // table appears with a Trusted trader. `#[ignore]`d (needs $DATABASE_URL):
    //
    //   DATABASE_URL=postgres://bot:bot@localhost:55432/polymarket \
    //     cargo test -p copy-trading-bot board_trust_render -- --ignored --nocapture
    #[tokio::test]
    #[ignore = "requires a live Postgres at $DATABASE_URL with migrations applied"]
    async fn board_trust_render() {
        let url = std::env::var("DATABASE_URL").expect("DATABASE_URL");
        let pool = sqlx::PgPool::connect(&url).await.unwrap();
        let pf = PgPortfolio::new(pool.clone()).await.unwrap();
        sqlx::query("DELETE FROM trader_fills WHERE wallet LIKE 'bd_%'")
            .execute(&pool)
            .await
            .unwrap();

        // A skilled wallet (b3 @ 0.5, 75% over 60 events) against a balanced
        // baseline so its surplus clears the gate => Trusted on the board.
        for (w, wins) in [("bd_base", 100), ("bd_good", 45)] {
            let n = if w == "bd_base" { 200 } else { 60 };
            for i in 0..n {
                let won = i < wins;
                let adv = (won as i32) as f64 - 0.5;
                let cond = format!("{w}_c{i}");
                sqlx::query(
                    "INSERT INTO trader_fills (wallet, condition_id, outcome_index, outcome, side, \
                       price, size_usd, title, slug, event_slug, is_sports, sport, ts, resolved, \
                       outcome_won, advantage, resolved_at) \
                     VALUES ($1,$2,0,'Yes','BUY',0.5,100,'t','s',$3,false,'other', \
                       NOW()-INTERVAL '1 hour',true,$4,$5,NOW())",
                )
                .bind(w)
                .bind(&cond)
                .bind(&cond)
                .bind(won)
                .bind(adv)
                .execute(&pool)
                .await
                .unwrap();
            }
        }

        let html = render(
            &pf,
            0.0,
            HonestBoardParams {
                exec_haircut: 0.01,
                fee_pct: 0.02,
                flat_stake: 100.0,
                capacity_frac: 0.05,
                min_pilot_roi: 0.02,
                pilot_min_events: 50,
                pilot_min_regimes: 5,
                regime_frac: 0.7,
                min_liquidity_usd: 2000.0,
                realized_decision_lag_secs: 900.0,
            },
        )
        .await;
        assert!(html.contains("Trader trust"), "trust table rendered");
        assert!(html.contains("bd_good"), "skilled trader appears");
        assert!(
            html.contains('\u{2705}'),
            "a Trusted trader shows the check mark"
        );
        // Phase 4: the market_resid accrual line always renders (events/30, rows,
        // multi-outcome skipped, gate) — even with zero accrual it shows 0/30.
        assert!(
            html.contains("market_resid accrual") && html.contains("/30"),
            "accrual line renders with the ≥30-event floor"
        );
        println!("board_trust_render: trust table + market_resid accrual line render — OK");

        sqlx::query("DELETE FROM trader_fills WHERE wallet LIKE 'bd_%'")
            .execute(&pool)
            .await
            .unwrap();
    }

    // Live: seed a deep (rank > cutoff, consensus_eligible=FALSE) trader with a
    // Trusted forward record, render, and assert the "Efficient below the whales"
    // panel surfaces it under the SAME belief-blind gate. `#[ignore]`d (needs DB).
    #[tokio::test]
    #[ignore = "requires a live Postgres at $DATABASE_URL with migrations applied"]
    async fn board_deep_efficiency_render() {
        let url = std::env::var("DATABASE_URL").expect("DATABASE_URL");
        let pool = sqlx::PgPool::connect(&url).await.unwrap();
        let pf = PgPortfolio::new(pool.clone()).await.unwrap();
        pf.run_migrations().await.unwrap();
        sqlx::query("DELETE FROM trader_fills WHERE wallet LIKE 'de\\_%'")
            .execute(&pool)
            .await
            .unwrap();
        sqlx::query("DELETE FROM followed_traders WHERE proxy_wallet LIKE 'de\\_%'")
            .execute(&pool)
            .await
            .unwrap();

        // Blind baseline population + a skilled deep wallet (75% over 60 events).
        for (w, wins) in [("de_base", 100), ("de_deep", 45)] {
            let n = if w == "de_base" { 200 } else { 60 };
            for i in 0..n {
                let won = i < wins;
                let adv = (won as i32) as f64 - 0.5;
                let cond = format!("{w}_c{i}");
                sqlx::query(
                    "INSERT INTO trader_fills (wallet, condition_id, outcome_index, outcome, side, \
                       price, size_usd, title, slug, event_slug, is_sports, sport, ts, resolved, \
                       outcome_won, advantage, resolved_at) \
                     VALUES ($1,$2,0,'Yes','BUY',0.5,100,'t','s',$3,false,'other', \
                       NOW()-INTERVAL '1 hour',true,$4,$5,NOW())",
                )
                .bind(w)
                .bind(&cond)
                .bind(&cond)
                .bind(won)
                .bind(adv)
                .execute(&pool)
                .await
                .unwrap();
            }
        }
        // Mark de_deep a DEEP (ineligible) leaderboard trader; de_base just supplies
        // the baseline population and needs no provenance.
        sqlx::query(
            "INSERT INTO followed_traders (proxy_wallet, source, rank, active, consensus_eligible) \
             VALUES ('de_deep', 'leaderboard', 120, TRUE, FALSE)",
        )
        .execute(&pool)
        .await
        .unwrap();

        let html = render(
            &pf,
            0.0,
            HonestBoardParams {
                exec_haircut: 0.01,
                fee_pct: 0.02,
                flat_stake: 100.0,
                capacity_frac: 0.05,
                min_pilot_roi: 0.02,
                pilot_min_events: 50,
                pilot_min_regimes: 5,
                regime_frac: 0.7,
                min_liquidity_usd: 2000.0,
            },
        )
        .await;
        assert!(
            html.contains("Efficient below the whales"),
            "deep-efficiency panel renders once a deep pool is tracked"
        );
        assert!(html.contains("de_deep"), "the deep sharp is surfaced");
        assert!(
            html.contains("Deep pool profiled:"),
            "the hot/deep aggregate verdict line renders"
        );
        println!("board_deep_efficiency_render: deep sharp surfaced under the trust gate — OK");

        sqlx::query("DELETE FROM trader_fills WHERE wallet LIKE 'de\\_%'")
            .execute(&pool)
            .await
            .unwrap();
        sqlx::query("DELETE FROM followed_traders WHERE proxy_wallet LIKE 'de\\_%'")
            .execute(&pool)
            .await
            .unwrap();
    }

    // Sparkline is a pure function — unit-test it without a DB.
    #[test]
    fn sparkline_maps_range_to_blocks() {
        assert_eq!(sparkline(&[1.0]), "—", "needs ≥2 points");
        let s = sparkline(&[0.0, 1.0, 2.0]);
        assert_eq!(s.chars().count(), 3);
        assert!(s.starts_with('▁'), "min → lowest block: {s}");
        assert!(s.ends_with('█'), "max → highest block: {s}");
    }

    // Live: seed resolved consensus signals + a paper ledger, render the board,
    // assert the honest panel renders with GO/HOLD, the corrected bound, and an
    // equity sparkline. `#[ignore]`d (needs $DATABASE_URL).
    #[tokio::test]
    #[ignore = "requires a live Postgres at $DATABASE_URL with migrations applied"]
    async fn board_honest_panel_render() {
        let url = std::env::var("DATABASE_URL").expect("DATABASE_URL");
        let pool = sqlx::PgPool::connect(&url).await.unwrap();
        let pf = PgPortfolio::new(pool.clone()).await.unwrap();
        pf.run_migrations().await.unwrap();
        sqlx::query("DELETE FROM consensus_signals WHERE condition_id LIKE 'bh_%'")
            .execute(&pool)
            .await
            .unwrap();
        sqlx::query("DELETE FROM honest_paper_ledger WHERE strategy = 'bh_str'")
            .execute(&pool)
            .await
            .unwrap();

        // Two resolved signals over two days with a captured mid, then a paper
        // ledger so the equity sparkline has ≥2 points.
        for (i, (cond, won, day)) in [("bh_c1", true, 1), ("bh_c2", false, 0)]
            .into_iter()
            .enumerate()
        {
            sqlx::query(&format!(
                "INSERT INTO consensus_signals \
                   (strategy, condition_id, outcome_index, event_slug, n_backers, n_opposers, \
                    net_count, net_quality, mean_price, price_std, recency_mins, total_usd, \
                    score, tier, initial_market_price, resolved, outcome_won, \
                    first_detected_at, resolved_at) \
                 VALUES ('bh_str',$1,0,$2,5,0,5,5.0,0.50,0.02,10,2000,1.0,'WATCH',0.50,TRUE,$3, \
                         NOW() - INTERVAL '{day} days 2 hours', NOW() - INTERVAL '{day} days')"
            ))
            .bind(cond)
            .bind(format!("bh_ev{i}"))
            .bind(won)
            .execute(&pool)
            .await
            .unwrap();
            pf.append_paper_bet("bh_str", cond, 0, 100.0, 0.01, 0.02)
                .await
                .unwrap();
        }

        let params = HonestBoardParams {
            exec_haircut: 0.01,
            fee_pct: 0.02,
            flat_stake: 100.0,
            capacity_frac: 0.05,
            min_pilot_roi: 0.02,
            pilot_min_events: 50,
            pilot_min_regimes: 5,
            regime_frac: 0.7,
            min_liquidity_usd: 2000.0,
            realized_decision_lag_secs: 900.0,
        };
        let html = render(&pf, 0.0, params).await;
        assert!(
            html.contains("Honest P&amp;L (realizable"),
            "honest panel renders"
        );
        assert!(html.contains("bh_str"), "the seeded strategy appears");
        // Small N → HOLD; the binding reason should be in the row tooltip.
        assert!(html.contains("HOLD"), "conservative default verdict shows");
        // The paper equity sparkline (≥2 ledger points) renders block glyphs.
        assert!(
            html.contains('▁') || html.contains('█') || html.contains('▄'),
            "equity sparkline renders"
        );
        println!("board_honest_panel_render: honest panel + verdict + sparkline — OK");

        sqlx::query("DELETE FROM consensus_signals WHERE condition_id LIKE 'bh_%'")
            .execute(&pool)
            .await
            .unwrap();
        sqlx::query("DELETE FROM honest_paper_ledger WHERE strategy = 'bh_str'")
            .execute(&pool)
            .await
            .unwrap();
    }
}
