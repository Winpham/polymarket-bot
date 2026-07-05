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
        // Phase 0: gate arms at the follower's capture bar (slippage + fees).
        let capture_margin = cfg.slippage_pct + cfg.fee_pct;
        // Read-only honest-P&L panel params (CLV − execution haircut + pilot gate).
        let honest = crate::board::HonestBoardParams {
            exec_haircut: cfg.exec_haircut,
            fee_pct: cfg.fee_pct,
            flat_stake: cfg.flat_stake,
            capacity_frac: cfg.capacity_frac,
            min_pilot_roi: cfg.min_pilot_roi,
            pilot_min_events: cfg.pilot_min_events,
            pilot_min_regimes: cfg.pilot_min_regimes,
            regime_frac: cfg.regime_frac,
            min_liquidity_usd: cfg.min_liquidity_usd,
            realized_decision_lag_secs: cfg.realized_decision_lag_secs,
        };
        let cohort_bands = cfg.track_cohort_bands.clone();
        // Shadow-study params (deep-pool edge run, Phase 0): the board diffs what
        // the ACTIVE portfolio would emit if certified deep sharps voted. Read-only.
        let shadow = crate::board::ShadowBoardParams {
            window_hours: cfg.consensus_window_hours,
            portfolio: crate::cycles::consensus_cycle::active_portfolio(&cfg, None),
            earn_flag_on: cfg.earn_deep_sharps,
        };
        tokio::spawn(async move {
            crate::board::serve(
                bd_portfolio,
                port,
                capture_margin,
                honest,
                cohort_bands,
                shadow,
            )
            .await
        });
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
    let hk_cfg = Arc::clone(&cfg);
    let hk_ntfy = ntfy.clone();
    let hk_http = reqwest::Client::builder()
        .timeout(Duration::from_secs(15))
        .build()
        .expect("failed to build housekeeping HTTP client");
    let housekeeping_loop = tokio::spawn(async move {
        loop {
            if let Err(e) = cycles::housekeeping_cycle(
                &hk_portfolio,
                &hk_notifier,
                &hk_http,
                &hk_cfg,
                hk_ntfy.as_deref(),
            )
            .await
            {
                tracing::error!(err = %e, "Copy housekeeping cycle failed");
            }
            tokio::time::sleep(Duration::from_secs(5 * 60)).await;
        }
    });

    // Dense early-life capture (decay Phase 0) — flag-gated: never spawned
    // when off, so the live path is byte-identical. Best-effort, bounded.
    if cfg.dense_capture {
        let dc_portfolio = Arc::clone(&portfolio);
        let dc_cfg = Arc::clone(&cfg);
        let dc_http = reqwest::Client::builder()
            .timeout(Duration::from_secs(15))
            .build()
            .expect("failed to build dense-capture HTTP client");
        tokio::spawn(async move {
            tracing::info!(
                interval_secs = dc_cfg.dense_interval_secs,
                window_mins = dc_cfg.dense_window_mins,
                max_signals = dc_cfg.dense_max_signals,
                strategies = %dc_cfg.dense_strategies,
                "Dense early-life capture ON"
            );
            loop {
                if let Err(e) = cycles::dense_capture_tick(&dc_portfolio, &dc_http, &dc_cfg).await {
                    tracing::warn!(err = %e, "dense capture tick failed");
                }
                tokio::time::sleep(Duration::from_secs(dc_cfg.dense_interval_secs.max(10))).await;
            }
        });
    }

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

    // Silent cross-check arms (Phase 4): load enabled arms' models once at start.
    // All default-OFF — with no flags/models this is an empty no-op set.
    let enrich_models = Arc::new(crate::scanner::enrich::load_models(&cfg));

    // Cached earned-trust map (Phase 4): slow-refreshed (~hourly), read each
    // consensus cycle. When CONSENSUS_TRUST_ARMS is off the refresh task exits
    // immediately and the map stays empty ⇒ earned_quality == quality_weight,
    // trusted == true ⇒ the portfolio is byte-identical.
    let trust_map: Arc<tokio::sync::RwLock<crate::cycles::consensus_cycle::TrustMap>> =
        Arc::new(tokio::sync::RwLock::new(Default::default()));
    {
        let tm = Arc::clone(&trust_map);
        let tp = Arc::clone(&portfolio);
        let tcfg = Arc::clone(&cfg);
        tokio::spawn(async move {
            if !tcfg.consensus_trust_arms && !tcfg.earn_deep_sharps {
                tracing::info!(
                    "Trust arms + earn-deep-sharps off — earned-trust map refresh disabled"
                );
                return;
            }
            loop {
                let m =
                    crate::cycles::consensus_cycle::compute_trust_map(&tp, tcfg.slice_pooled).await;
                let n = m.len();
                // The shared map feeds the trust ARMS' earned_quality — only
                // publish it when those arms are on, so EARN_DEEP_SHARPS alone
                // leaves every live book byte-identical.
                if tcfg.consensus_trust_arms {
                    *tm.write().await = m.clone();
                }
                tracing::info!(traders = n, "Earned-trust map refreshed");

                // Flag-gated EARN pass (deep-pool edge run, Phase 0): durably flip
                // `earned_eligible` for deep traders whose belief-blind verdict is
                // Trusted. Never touches rank-eligible traders; idempotent; logs
                // every flip (the deliberate promotion record).
                if tcfg.earn_deep_sharps {
                    match tp.get_active_traders().await {
                        Ok(traders) => {
                            let pass = crate::scanner::earned::deep_sharp_pass(&traders, &m);
                            let to_earn: Vec<String> =
                                crate::scanner::earned::promotable_deep_sharps(&pass)
                                    .into_iter()
                                    .filter(|d| !d.earned)
                                    .map(|d| d.wallet.clone())
                                    .collect();
                            if !to_earn.is_empty() {
                                match tp.set_earned_eligible(&to_earn).await {
                                    Ok(flipped) => tracing::info!(
                                        flipped,
                                        wallets = ?to_earn,
                                        "EARN_DEEP_SHARPS: certified deep sharps earned into consensus"
                                    ),
                                    Err(e) => {
                                        tracing::warn!(err = %e, "set_earned_eligible failed")
                                    }
                                }
                            }
                        }
                        Err(e) => tracing::warn!(err = %e, "earn pass: get_active_traders failed"),
                    }
                }
                tokio::time::sleep(Duration::from_secs(tcfg.trust_refresh_mins * 60)).await;
            }
        });
    }

    // Proven-trader router follow-set (PREREG 2026-07-04, paper-only): re-scored
    // on the trust cadence and published as EXACTLY the set the arm counts. `None`
    // until the first successful re-score, so the arm isn't even registered before
    // then (fail-closed); an honest empty re-score publishes Some(∅), which
    // registers the arm but counts no votes. Off ⇒ the task exits and the slot
    // stays None ⇒ the live portfolio is byte-identical.
    let router_set: Arc<
        tokio::sync::RwLock<Option<Arc<std::collections::HashSet<String>>>>,
    > = Arc::new(tokio::sync::RwLock::new(None));
    {
        let rs = Arc::clone(&router_set);
        let rp = Arc::clone(&portfolio);
        let rcfg = Arc::clone(&cfg);
        tokio::spawn(async move {
            if !rcfg.proven_router {
                tracing::info!("Proven-router off — follow-set re-scorer disabled");
                return;
            }
            loop {
                match rp.refresh_router_followset().await {
                    Ok(ws) => {
                        let n = ws.len();
                        *rs.write().await = Some(Arc::new(
                            ws.into_iter().map(|w| w.to_lowercase()).collect(),
                        ));
                        tracing::info!(wallets = n, "Router follow-set re-scored");
                    }
                    // Keep the previously-published set on a transient DB error —
                    // a failed re-score must never blank an honest set (and never
                    // fail-open either; the slot only moves on success).
                    Err(e) => tracing::error!(err = %e, "Router follow-set re-score failed"),
                }
                tokio::time::sleep(Duration::from_secs(rcfg.trust_refresh_mins * 60)).await;
            }
        });
    }

    // Survivorship capture fix (2026-07-04 capture-hardening, paper-only): keep
    // polling the fills of DEACTIVATED but scorecard-eligible wallets so the
    // forward scorecard/benchmark isn't conditioned on staying tracked. Writes
    // ONLY the durable `trader_fills` archive (never consensus window votes), so a
    // dropped wallet can't re-enter the live book — on or off, the consensus book
    // is byte-identical. Bounded slow loop on the trust cadence, poll fan-out
    // capped by `consensus_max_concurrency`. Off ⇒ the task exits ⇒ byte-identical.
    if cfg.capture_dropped {
        let cd_portfolio = Arc::clone(&portfolio);
        let cd_monitor = Arc::clone(&monitor);
        let cd_cfg = Arc::clone(&cfg);
        tokio::spawn(async move {
            tracing::info!("Capture-dropped ON — polling deactivated scorecard-eligible wallets");
            loop {
                if let Err(e) =
                    cycles::capture_dropped_tick(&cd_portfolio, &cd_monitor, &cd_cfg).await
                {
                    tracing::warn!(err = %e, "capture-dropped tick failed");
                }
                tokio::time::sleep(Duration::from_secs(cd_cfg.trust_refresh_mins * 60)).await;
            }
        });
    }

    // Hot-lane fast poll for the router follow-set (2026-07-04 capture-hardening,
    // paper-only): fast-poll ONLY the follow-set wallets (from the shared slot the
    // re-scorer publishes), ingest through the same dedup path, and run a scoped
    // `proven_router`-only scoring pass so a routed wallet's fresh BUY becomes a
    // signal in ≲30s instead of 1.5–3 min. Requires PROVEN_ROUTER (so a follow-set
    // exists); off ⇒ never spawned ⇒ byte-identical.
    if cfg.hot_lane && cfg.proven_router {
        let hl_portfolio = Arc::clone(&portfolio);
        let hl_monitor = Arc::clone(&monitor);
        let hl_cfg = Arc::clone(&cfg);
        let hl_router = Arc::clone(&router_set);
        tokio::spawn(async move {
            let interval = hl_cfg.hot_poll_secs.max(5);
            let mut cursors: std::collections::HashMap<
                String,
                chrono::DateTime<chrono::Utc>,
            > = std::collections::HashMap::new();
            tracing::info!(
                interval_secs = interval,
                "Hot lane ON — fast-polling the router follow-set"
            );
            loop {
                // Cheap clone of the shared follow-set; fail-closed while None/∅.
                if let Some(set) = hl_router.read().await.clone()
                    && let Err(e) = cycles::hot_lane_tick(
                        &hl_portfolio,
                        &hl_monitor,
                        &hl_cfg,
                        set,
                        &mut cursors,
                    )
                    .await
                    {
                        tracing::warn!(err = %e, "hot-lane tick failed");
                    }
                tokio::time::sleep(Duration::from_secs(interval)).await;
            }
        });
    }

    // Consensus detection loop.
    let co_portfolio = Arc::clone(&portfolio);
    let co_notifier = Arc::clone(&notifier);
    let co_monitor = Arc::clone(&monitor);
    let co_cfg = Arc::clone(&cfg);
    let co_ntfy = ntfy.clone();
    let co_models = Arc::clone(&enrich_models);
    let co_trust = Arc::clone(&trust_map);
    let co_router = Arc::clone(&router_set);
    let co_http = reqwest::Client::builder()
        .timeout(Duration::from_secs(15))
        .build()
        .expect("failed to build consensus HTTP client");
    let consensus_loop = tokio::spawn(async move {
        if !co_cfg.track_enabled {
            return;
        }
        // Give the first leaderboard refresh a moment to populate the universe.
        tokio::time::sleep(Duration::from_secs(20)).await;
        loop {
            // Cheap snapshot of the slow-refreshed trust map (≤~60 entries); never
            // hold the lock across the cycle's network I/O.
            let trust_snapshot = co_trust.read().await.clone();
            let router_snapshot = co_router.read().await.clone();
            if let Err(e) = cycles::consensus_cycle(
                &co_portfolio,
                &co_notifier,
                &co_monitor,
                &co_cfg,
                co_ntfy.as_deref(),
                &co_http,
                &co_models,
                &trust_snapshot,
                router_snapshot,
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
