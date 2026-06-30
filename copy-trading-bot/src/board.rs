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

/// Serve the board on `0.0.0.0:port` forever. Best-effort; logs and retries binds.
pub async fn serve(portfolio: Arc<PgPortfolio>, port: u16) {
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
            let html = render(&pf).await;
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

/// Render the earned trader-trust table ("who to actually follow"): each tracked
/// trader with resolved fills, ranked by earned trust, with best/worst games,
/// surplus ± bound, and capture completeness. Empty until fills resolve.
async fn render_trust(portfolio: &PgPortfolio) -> String {
    let scores = portfolio.trader_slice_scores().await.unwrap_or_default();
    if scores.is_empty() {
        return String::new();
    }
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
        let short = &t.wallet[..12.min(t.wallet.len())];
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

async fn render(portfolio: &PgPortfolio) -> String {
    let rows = portfolio
        .consensus_scoreboard_by_strategy()
        .await
        .unwrap_or_default();
    let tracked = portfolio.count_tracked_traders().await.unwrap_or(0);
    let pp = PromotionParams::default();
    let n = rows.len();
    // Bonferroni denominator PER FAMILY: experimental arms are corrected among
    // themselves, so adding them never tightens the core portfolio's bar.
    let mut fam_n: std::collections::HashMap<&str, usize> = std::collections::HashMap::new();
    for r in &rows {
        *fam_n.entry(family(&r.strategy)).or_default() += 1;
    }

    let mut body = String::new();
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

    // --- Second table: earned trader trust ("who to actually follow") ---
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
         </style></head><body>\
         <h1>🤝 Consensus scoreboard</h1>\
         <p class=sub>Tracking {tracked} top traders · {n} strategies forward · auto-refresh 30s</p>\
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

        let html = render(&pf).await;
        assert!(html.contains("Trader trust"), "trust table rendered");
        assert!(html.contains("bd_good"), "skilled trader appears");
        assert!(
            html.contains('\u{2705}'),
            "a Trusted trader shows the check mark"
        );
        println!("board_trust_render: trust table renders with a Trusted trader — OK");

        sqlx::query("DELETE FROM trader_fills WHERE wallet LIKE 'bd_%'")
            .execute(&pool)
            .await
            .unwrap();
    }
}
