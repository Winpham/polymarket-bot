use anyhow::Result;
use std::sync::Arc;
use std::time::Duration;

use sqlx::PgPool;

use crate::config::CopyTradingConfig;
use crate::cycles;
use crate::metrics;
use crate::scanner::copy_trader::CopyTraderMonitor;
use crate::storage::postgres::PgPortfolio;
use crate::telegram::notifier::TelegramNotifier;
use polymarket_common::ntfy::Ntfy;

/// Broadcast a message to the owner and all subscribers.
pub async fn broadcast(notifier: &TelegramNotifier, portfolio: &PgPortfolio, message: &str) {
    let subs = portfolio.telegram_subscribers().await.unwrap_or_default();
    notifier.broadcast(&subs, message).await;
}

pub async fn run_live(cfg: Arc<CopyTradingConfig>) -> Result<()> {
    tracing::info!(
        interval_mins = cfg.copy_trade_interval_mins,
        "Copy Trading Bot starting..."
    );

    // Start Prometheus metrics server
    metrics::init(cfg.metrics_port);

    let pool = {
        let mut attempts = 0;
        loop {
            match PgPool::connect(&cfg.database_url).await {
                Ok(p) => break p,
                Err(e) => {
                    attempts += 1;
                    if attempts >= 10 {
                        return Err(e.into());
                    }
                    tracing::warn!(attempt = attempts, err = %e, "DB connect failed, retrying in 3s...");
                    tokio::time::sleep(Duration::from_secs(3)).await;
                }
            }
        }
    };
    let portfolio = Arc::new(PgPortfolio::new(pool.clone()).await?);
    portfolio.run_migrations().await?;
    tracing::info!("Database connected and migrations applied");

    let notifier = Arc::new(TelegramNotifier::new(
        &cfg.telegram_bot_token,
        &cfg.telegram_chat_id,
    ));
    let telegram_on = !cfg.telegram_bot_token.trim().is_empty();

    // ntfy phone push (reuses the brainstem channel). None when no topic set.
    let ntfy: Option<Arc<Ntfy>> = Ntfy::new(&cfg.ntfy_server, &cfg.ntfy_topic).map(Arc::new);
    tracing::info!(
        telegram = telegram_on,
        ntfy = ntfy.is_some(),
        board_port = cfg.board_port,
        "Alert channels"
    );

    let monitor = Arc::new(CopyTraderMonitor::new(
        reqwest::Client::builder()
            .timeout(Duration::from_secs(15))
            .build()
            .expect("failed to build HTTP client"),
    ));

    if telegram_on {
        let _ = notifier
            .send(&format!(
                "👥 *Copy Trading Bot* started\n\n⏱ Poll interval: every {}min",
                cfg.copy_trade_interval_mins,
            ))
            .await;
    }
    if let Some(n) = &ntfy {
        n.push(
            "🤝 Consensus bot started",
            &format!(
                "Tracking the top {} traders. Scoreboard: http://localhost:{}/",
                cfg.track_top_n, cfg.board_port
            ),
            3,
            &["satellite"],
        )
        .await;
    }

    // Read-only web scoreboard (the ntfy-only replacement for /consensus).
    {
        let bd_portfolio = Arc::clone(&portfolio);
        let port = cfg.board_port;
        tokio::spawn(async move { crate::board::serve(bd_portfolio, port).await });
    }

    // Spawn Telegram command polling loop
    let cmd_portfolio = Arc::clone(&portfolio);
    let cmd_notifier = Arc::clone(&notifier);
    let cmd_cfg = Arc::clone(&cfg);
    let cmd_monitor = Arc::clone(&monitor);
    let cmd_http = reqwest::Client::builder()
        .timeout(Duration::from_secs(15))
        .build()
        .expect("failed to build command HTTP client");
    let command_loop = tokio::spawn(async move {
        if !telegram_on {
            // ntfy-only / headless: no Telegram interface to poll.
            std::future::pending::<()>().await;
        }
        loop {
            let commands = cmd_notifier.poll_commands().await;
            for (chat_id, cmd, username, first_name, full_text) in &commands {
                if let Err(e) = cmd_portfolio
                    .upsert_telegram_user(chat_id, username.as_deref(), first_name.as_deref())
                    .await
                {
                    tracing::warn!(err = %e, "Failed to upsert telegram user");
                }

                tracing::info!(cmd = cmd.as_str(), chat_id, "Handling Telegram command");
                let reply = crate::telegram::commands::handle_command(
                    cmd,
                    chat_id,
                    full_text,
                    first_name.as_deref(),
                    &cmd_portfolio,
                    &cmd_notifier,
                    &cmd_monitor,
                    &cmd_http,
                    &cmd_cfg,
                )
                .await;

                if let Err(e) = cmd_notifier.send_to(chat_id, &reply).await {
                    tracing::warn!(err = %e, chat_id = chat_id, "Failed to reply to command");
                }
            }
            tokio::time::sleep(Duration::from_secs(3)).await;
        }
    });

    // Copy trade main loop
    let ct_portfolio = Arc::clone(&portfolio);
    let ct_notifier = Arc::clone(&notifier);
    let ct_monitor = Arc::clone(&monitor);
    let ct_cfg = Arc::clone(&cfg);
    let copy_trade_loop = tokio::spawn(async move {
        if !ct_cfg.copy_trade_enabled {
            tracing::info!("Legacy per-trader copy loop disabled (COPY_TRADE_ENABLED=false)");
            std::future::pending::<()>().await;
        }
        loop {
            if let Err(e) =
                cycles::copy_trade_cycle(&ct_portfolio, &ct_notifier, &ct_monitor, &ct_cfg).await
            {
                tracing::error!(err = %e, "Copy trade cycle failed");
            }
            tokio::time::sleep(Duration::from_secs(ct_cfg.copy_trade_interval_mins * 60)).await;
        }
    });

    // Housekeeping loop — resolves copy bets independently
    let hk_portfolio = Arc::clone(&portfolio);
    let hk_notifier = Arc::clone(&notifier);
    let hk_http = reqwest::Client::builder()
        .timeout(Duration::from_secs(15))
        .build()
        .expect("failed to build housekeeping HTTP client");
    let housekeeping_loop = tokio::spawn(async move {
        loop {
            if let Err(e) = cycles::housekeeping_cycle(&hk_portfolio, &hk_notifier, &hk_http).await
            {
                tracing::error!(err = %e, "Copy housekeeping cycle failed");
            }
            tokio::time::sleep(Duration::from_secs(5 * 60)).await;
        }
    });

    // Leaderboard auto-tracker: keep the followed universe synced to the top-N.
    let tr_portfolio = Arc::clone(&portfolio);
    let tr_notifier = Arc::clone(&notifier);
    let tr_cfg = Arc::clone(&cfg);
    let tr_ntfy = ntfy.clone();
    let mut tr_first = true;
    let tr_http = reqwest::Client::builder()
        .timeout(Duration::from_secs(15))
        .build()
        .expect("failed to build tracker HTTP client");
    let tracker_loop = tokio::spawn(async move {
        if !tr_cfg.track_enabled {
            tracing::info!("Auto-tracking disabled (TRACK_ENABLED=false)");
            return;
        }
        loop {
            match crate::scanner::leaderboard_tracker::refresh_universe(
                &tr_http,
                &tr_portfolio,
                &tr_cfg,
            )
            .await
            {
                Ok((up, deact)) => {
                    if up > 0 {
                        let _ = tr_notifier
                            .send(&format!(
                                "🛰 Tracking *{up}* top traders (top {} × {})",
                                tr_cfg.track_top_n, tr_cfg.track_periods
                            ))
                            .await;
                        // Phone confirmation once, on the first successful sync.
                        if tr_first && let Some(n) = &tr_ntfy {
                            n.push(
                                "🛰 Tracking live",
                                &format!(
                                    "Now tracking {up} top traders (top {} × {}).",
                                    tr_cfg.track_top_n, tr_cfg.track_periods
                                ),
                                3,
                                &["satellite"],
                            )
                            .await;
                        }
                        tr_first = false;
                        let _ = deact;
                    }
                }
                Err(e) => tracing::error!(err = %e, "Leaderboard refresh failed"),
            }
            tokio::time::sleep(Duration::from_secs(tr_cfg.track_refresh_mins * 60)).await;
        }
    });

    // Consensus detection loop.
    let co_portfolio = Arc::clone(&portfolio);
    let co_notifier = Arc::clone(&notifier);
    let co_monitor = Arc::clone(&monitor);
    let co_cfg = Arc::clone(&cfg);
    let co_ntfy = ntfy.clone();
    let consensus_loop = tokio::spawn(async move {
        if !co_cfg.track_enabled {
            return;
        }
        // Give the first leaderboard refresh a moment to populate the universe.
        tokio::time::sleep(Duration::from_secs(20)).await;
        loop {
            if let Err(e) = cycles::consensus_cycle(
                &co_portfolio,
                &co_notifier,
                &co_monitor,
                &co_cfg,
                co_ntfy.as_deref(),
            )
            .await
            {
                tracing::error!(err = %e, "Consensus cycle failed");
            }
            tokio::time::sleep(Duration::from_secs(co_cfg.consensus_interval_mins * 60)).await;
        }
    });

    tokio::select! {
        _ = shutdown_signal() => {
            tracing::info!("Shutdown signal received, stopping gracefully...");
        }
        r = command_loop => {
            tracing::error!("Command loop exited: {:?}", r);
        }
        r = copy_trade_loop => {
            tracing::error!("Copy trade loop exited: {:?}", r);
        }
        r = housekeeping_loop => {
            tracing::error!("Housekeeping loop exited: {:?}", r);
        }
        r = tracker_loop => {
            tracing::error!("Tracker loop exited: {:?}", r);
        }
        r = consensus_loop => {
            tracing::error!("Consensus loop exited: {:?}", r);
        }
    }

    tracing::info!("Sending shutdown notification...");
    if telegram_on {
        let _ = notifier
            .send("🛑 Copy Trading Bot shutting down gracefully")
            .await;
    }

    Ok(())
}

/// Wait for SIGINT (Ctrl-C) or SIGTERM (docker stop).
async fn shutdown_signal() {
    let ctrl_c = tokio::signal::ctrl_c();
    #[cfg(unix)]
    {
        let mut sigterm = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
            .expect("failed to register SIGTERM handler");
        tokio::select! {
            _ = ctrl_c => {}
            _ = sigterm.recv() => {}
        }
    }
    #[cfg(not(unix))]
    {
        ctrl_c.await.ok();
    }
}
