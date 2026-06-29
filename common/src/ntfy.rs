//! ntfy push channel — reuses the user's existing brainstem phone channel.
//!
//! Brainstem already delivers phone push via ntfy (`~/.brainstem/notify.config.json`:
//! `{ server, topic }`). This sends consensus alerts to the SAME topic, so they
//! land on the phone the user already has subscribed — no Telegram bot needed.
//!
//! Uses ntfy's JSON publishing API (POST the server base with a `{topic,...}`
//! body) so UTF-8 titles/emoji are handled cleanly (HTTP headers are latin-1).
//! ntfy.sh is a public relay; only public market data is ever sent.

use std::time::Duration;

/// A configured ntfy publisher. `None` when no topic is set (push disabled).
#[derive(Clone)]
pub struct Ntfy {
    http: reqwest::Client,
    server: String,
    topic: String,
}

impl Ntfy {
    /// Build a publisher, or `None` if `topic` is empty (push disabled).
    pub fn new(server: &str, topic: &str) -> Option<Self> {
        let topic = topic.trim();
        if topic.is_empty() {
            return None;
        }
        let server = {
            let s = server.trim().trim_end_matches('/');
            if s.is_empty() {
                "https://ntfy.sh".to_string()
            } else {
                s.to_string()
            }
        };
        Some(Self {
            http: reqwest::Client::builder()
                .timeout(Duration::from_secs(8))
                .build()
                .unwrap_or_default(),
            server,
            topic: topic.to_string(),
        })
    }

    /// Push one notification. Best-effort: failures are logged, never fatal.
    /// `priority` 1..=5 (5 = max). `tags` are ntfy tag names (emoji shortcodes).
    pub async fn push(&self, title: &str, message: &str, priority: u8, tags: &[&str]) {
        let payload = serde_json::json!({
            "topic": self.topic,
            "title": title,
            "message": message,
            "priority": priority.clamp(1, 5),
            "tags": tags,
            "markdown": true,
        });
        match self.http.post(&self.server).json(&payload).send().await {
            Ok(resp) if resp.status().is_success() => {}
            Ok(resp) => {
                tracing::warn!(status = %resp.status(), "ntfy push non-2xx")
            }
            Err(e) => tracing::warn!(err = %e, "ntfy push failed"),
        }
    }
}
