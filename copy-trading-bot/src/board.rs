//! Minimal read-only web scoreboard — the ntfy-only replacement for the Telegram
//! `/consensus` query. A hand-rolled tokio HTTP server (no extra deps) serves one
//! dark, auto-refreshing page showing each strategy's distinct-event N, hit-rate,
//! surplus-over-blind, and the belief-blind promotion-gate verdict.

use std::sync::Arc;

use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpListener;

use crate::scanner::promotion::{PromotionParams, promotion_verdict};
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

async fn render(portfolio: &PgPortfolio) -> String {
    let rows = portfolio
        .consensus_scoreboard_by_strategy()
        .await
        .unwrap_or_default();
    let tracked = portfolio.count_tracked_traders().await.unwrap_or(0);
    let pp = PromotionParams::default();
    let n = rows.len();

    let mut body = String::new();
    let have_results = rows.iter().any(|r| r.resolved > 0);
    if !have_results {
        body.push_str(
            "<p class=muted>No resolved signals yet. Strategies are tracking forward silently — \
             this table fills in as markets close (sports next-day, others over days).</p>",
        );
    } else {
        body.push_str(
            "<table><thead><tr><th>gate</th><th>strategy</th><th class=r>events (N)</th>\
             <th class=r>hit-rate</th><th class=r>surplus</th><th class=r>lower bound</th>\
             <th class=r>raw edge</th></tr></thead><tbody>",
        );
        for r in rows.iter().filter(|r| r.resolved > 0) {
            let hr = r.won as f64 / r.resolved as f64 * 100.0;
            let v = promotion_verdict(r.distinct_events, r.surplus, r.surplus_sd, n, &pp);
            let gate = if v.promotable { "✅" } else { "⏳" };
            let scls = match r.surplus {
                Some(s) if s > 0.0 => "pos",
                Some(_) => "neg",
                None => "muted",
            };
            body.push_str(&format!(
                "<tr><td>{gate}</td><td class=mono>{strat}</td><td class=r>{ev}</td>\
                 <td class=r>{hr:.0}%</td><td class=\"r {scls}\">{surplus}</td>\
                 <td class=r>{lb}</td><td class=\"r muted\">{edge}</td></tr>",
                strat = r.strategy,
                ev = r.distinct_events,
                surplus = pct(r.surplus),
                lb = pct(v.lower_bound),
                edge = pct(r.edge),
            ));
        }
        body.push_str("</tbody></table>");
    }

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
         deliberate human call — never automatic.</p>\
         </body></html>",
    )
}
