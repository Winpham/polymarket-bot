# Deploy the Consensus Engine (ntfy-only)

The consensus bot is **alert/paper-only** — it reads public APIs and pushes you alerts.
**No wallet, no private key, no funds, nothing at risk.**

This setup reuses your **existing brainstem ntfy phone channel** — consensus alerts buzz the phone
you already have subscribed, no Telegram bot. The `/consensus` scoreboard (surplus + promotion gate)
is served as a **read-only web page** at `http://localhost:9002/`.

> Deploys the code on `feat/consensus-engine` (NOT the upstream GHCR image). Stack is just
> Postgres + the bot via Docker — no Rust install needed.

## Prerequisites
- **Docker Desktop** running.
- `cd ~/polymarket-bot && git checkout feat/consensus-engine`.
- The **ntfy app** on your phone, subscribed to your brainstem topic (you already have this).

## Step 1 — Get your ntfy topic
It's the same secret brainstem uses (a 160-bit secret — don't share it):
```bash
python3 -c "import json;print(json.load(open('$HOME/.brainstem/notify.config.json'))['ntfy']['topic'])"
```
Copy the value.

## Step 2 — Configure
```bash
cd ~/polymarket-bot
cp .env.consensus.example .env.consensus
# edit .env.consensus → paste the topic into NTFY_TOPIC
```

## Step 3 — Launch
```bash
docker compose -f docker-compose.consensus.yml --env-file .env.consensus up -d --build
```
First run builds the image (~3–5 min) then starts Postgres + the bot. Within ~20s your **phone
gets two ntfy pushes**: "🤝 Consensus bot started" and "🛰 Tracking live".

## Step 4 — Verify
- **Phone:** you got the two startup pushes above.
- **Scoreboard:** open **http://localhost:9002/** — a dark page showing the 14 strategies, their
  distinct-event N, surplus, and the ✅/⏳ promotion gate (auto-refreshes every 30s).
- **Logs:** `docker compose -f docker-compose.consensus.yml logs -f copy-trading-bot`
  → `Alert channels telegram=false ntfy=true` and `Consensus cycle complete … strategies=14`.

## What to expect over time
- 14 strategies run forward **silently**; only the `strict` strategy pushes a phone alert on
  STRONG/ELITE consensus (🟢/🔥) — no spam.
- The scoreboard at `:9002` is empty of *results* until markets resolve (sports next-day, others
  over days). As they do, **surplus** (the favorite-longshot-neutralized edge) and a ✅/⏳ gate
  appear per strategy.
- **Nothing auto-promotes.** A strategy turning ✅ (positive surplus lower-bound over ≥30 distinct
  events) is your cue to consider promoting it — your call.

## Operations
- **Stop** (data persists in the `pgdata` volume): `docker compose -f docker-compose.consensus.yml down`
- **Restart:** rerun Step 3 (drop `--build` if code unchanged).
- **Update after `git pull`:** rerun Step 3 *with* `--build`.
- **Back up the forward record:**
  `docker compose -f docker-compose.consensus.yml exec postgres pg_dump -U bot polymarket > backup.sql`
- **View the board from your phone too:** it's on your Mac's `:9002`; reach it over your Tailscale
  IP (same way brainstem's dashboard is reached) — e.g. `http://<tailscale-ip>:9002/`.

## Running 24/7
Keep Docker Desktop open and prevent Mac sleep while plugged in (`caffeinate -s`, or Battery
settings). For always-on, the same two commands run on any ~$5/mo VPS with Docker.

## Optional: add Telegram too
If you later want the interactive Telegram commands in addition to ntfy, set `TELEGRAM_BOT_TOKEN`
and `TELEGRAM_CHAT_ID` in `.env.consensus` (uncomment them in the compose). Both channels then fire.

## Safety
Paper/alert-only by design — no real-money orders, no keys. The only outbound actions are reading
public Polymarket APIs, POSTing alerts to your ntfy topic, and serving the local board page.
