//! Minimal read-only web scoreboard — the ntfy-only replacement for the Telegram
//! `/consensus` query. A hand-rolled tokio HTTP server (no extra deps) serves one
//! dark, auto-refreshing page showing each strategy's distinct-event N, hit-rate,
//! surplus-over-blind, and the belief-blind promotion-gate verdict.

use std::sync::Arc;

use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpListener;

use crate::scanner::enrich::family;
use crate::scanner::promotion::{PromotionParams, promotion_verdict};
use crate::scanner::trader_trust::{TraderTrust, TrustVerdict, trust_verdict};
use crate::storage::postgres::PgPortfolio;

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

/// Render the **honest, realizable** P&L panel (read-only): per strategy the
/// CLV-based ROI net of the execution haircut, event-clustered, shown alongside
/// the old sharp `edge` for reference. Realizable, not flattering. The
/// conservative pilot verdict + regime/equity detail arrive in later phases.
async fn render_honest(portfolio: &PgPortfolio, honest: HonestBoardParams) -> String {
    let rows = match portfolio
        .honest_pnl_by_strategy(honest.exec_haircut, honest.fee_pct)
        .await
    {
        Ok(r) if r.iter().any(|x| x.resolved > 0) => r,
        _ => return String::new(),
    };
    // Per-strategy day-regime persistence (positive/total) from the segment table.
    let segs = portfolio
        .honest_pnl_segments(honest.exec_haircut, honest.fee_pct)
        .await
        .unwrap_or_default();
    let mut regimes: std::collections::HashMap<String, (i64, i64)> =
        std::collections::HashMap::new();
    for s in &segs {
        if s.seg_kind == "day" {
            let e = regimes.entry(s.strategy.clone()).or_insert((0, 0));
            e.1 += 1; // total distinct day-regimes
            if s.honest_roi.unwrap_or(0.0) > 0.0 {
                e.0 += 1; // positive day-regimes
            }
        }
    }
    // Bonferroni family sizes over the honest rows (experimental vs core).
    let mut fam_n: std::collections::HashMap<&str, usize> = std::collections::HashMap::new();
    for r in &rows {
        if r.resolved > 0 {
            *fam_n.entry(family(&r.strategy)).or_default() += 1;
        }
    }
    let th = honest.thresholds();

    // Build (row, verdict, capacity), then sort GO-first, then by corrected LB.
    let mut items: Vec<_> = rows
        .iter()
        .filter(|r| r.resolved > 0)
        .map(|r| {
            let (rp, rt) = regimes.get(&r.strategy).copied().unwrap_or((0, 0));
            let inp = crate::scanner::honest::PilotInputs {
                honest_roi: r.honest_roi,
                honest_roi_sd: r.honest_roi_sd,
                distinct_events: r.distinct_events,
                regimes_positive: rp,
                regimes_total: rt,
                median_sharp_usd: r.median_sharp_usd,
                n_family: fam_n.get(family(&r.strategy)).copied().unwrap_or(1),
            };
            let verdict = crate::scanner::honest::pilot_verdict(&inp, &th);
            let cap = crate::scanner::honest::capacity(
                honest.flat_stake,
                honest.capacity_frac,
                r.median_sharp_usd,
                r.bets_per_day,
                r.avg_hours_to_resolve,
                r.honest_roi,
            );
            (r, verdict, cap, rp, rt)
        })
        .collect();
    // Sort GO-first, then by corrected lower bound descending.
    items.sort_by(|a, b| {
        b.1.go.cmp(&a.1.go).then(
            b.1.corrected_lower_bound
                .unwrap_or(f64::NEG_INFINITY)
                .partial_cmp(&a.1.corrected_lower_bound.unwrap_or(f64::NEG_INFINITY))
                .unwrap_or(std::cmp::Ordering::Equal),
        )
    });

    let mut out = String::from(
        "<h1 style='margin-top:34px'>💵 Honest P&amp;L (realizable · paper)</h1>\
         <p class=sub>Outcome vs the mid we saw while OPEN (CLV), net of the execution haircut — \
         the edge we could actually realize. Event-clustered, multi-regime. Paper only, NO real money.</p>\
         <table><thead><tr><th>pilot</th><th>strategy</th><th class=r>events (N)</th>\
         <th class=r>honest ROI</th><th class=r>corrected LB</th><th class=r>regimes+</th>\
         <th class=r>CLV</th><th class=r>sharp edge</th><th class=r>median $</th>\
         <th class=r>stake</th><th class=r>proj $/wk</th></tr></thead><tbody>",
    );
    for (r, verdict, cap, rp, rt) in &items {
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
        let med = r
            .median_sharp_usd
            .map(|v| format!("${v:.0}"))
            .unwrap_or_else(|| "—".into());
        let tip = format!(
            "{}  ·  working capital ≈ ${:.0}  ·  real-ask coverage {}",
            verdict.reason,
            cap.working_capital,
            r.ask_coverage
                .map(|c| format!("{:.0}%", c * 100.0))
                .unwrap_or_else(|| "0% (heuristic haircut)".into()),
        );
        out.push_str(&format!(
            "<tr title=\"{reason}\"><td class={mcls}>{marker}</td><td class=mono>{strat}</td>\
             <td class=r>{ev}</td><td class=\"r {hrcls}\">{hroi}</td><td class=r>{lb}</td>\
             <td class=r>{rp}/{rt}</td><td class=r>{clv}</td><td class=\"r muted\">{sharp}</td>\
             <td class=\"r muted\">{med}</td><td class=\"r muted\">${stake:.0}</td>\
             <td class=\"r muted\">${projwk:.0}</td></tr>",
            reason = html_escape(&tip),
            strat = r.strategy,
            ev = r.distinct_events,
            hroi = pct(r.honest_roi),
            lb = pct(verdict.corrected_lower_bound),
            clv = pct(r.clv_share),
            sharp = pct(r.sharp_edge),
            stake = cap.suggested_stake,
            projwk = cap.projected_weekly,
        ));
    }
    out.push_str(&format!(
        "</tbody></table>\
         <p class=note><b>honest ROI</b> = event-clustered `AVG((outcome − entry)/entry − fee)` where \
         <b>entry = captured mid + {hc:.0}¢ haircut</b> — the realizable per-$ edge (NOT the sharps' fill). \
         <b>corrected LB</b> = Bonferroni-corrected 1-sided lower bound on honest ROI. ✅ GO requires ALL: \
         LB &gt; {bar:+.0}%, N ≥ {ev} events, ≥{regfrac:.0}% of day-regimes positive (≥{minreg}), and \
         liquidity ≥ ${liq:.0}. Conservative by design — a false GO risks real money, so the default is HOLD \
         (hover a row for the binding reason). <b>sharp edge</b> = outcome − sharps' mean price, reference only \
         (overstates what we can capture). <b>stake</b> = min(flat, {capfrac:.0}% × median $); <b>proj $/wk</b> = \
         paper. Promotion to real money is a deliberate human call — never automatic. NO real money is placed.</p>",
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
    let n429 = polymarket_common::metrics::data_api_429_count();
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
         <p class=sub>Tracking {tracked} top traders · {n} strategies forward · data-api 429s: {n429} · auto-refresh 30s</p>\
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
}
