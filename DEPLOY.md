# Deploy the Consensus Engine

The consensus bot is **alert/paper-only** — it reads public APIs and sends you Telegram alerts.
**No wallet, no private key, no funds, nothing at risk.** All you provide is a Telegram bot token.

> Deploys the code on the `feat/consensus-engine` branch (NOT the upstream GHCR image). The
> minimal stack is just Postgres + the bot, both via Docker — you don't need Rust installed.

## Prerequisites
- **Docker Desktop** running (you have it).
- You're on the `feat/consensus-engine` branch: `cd ~/polymarket-bot && git checkout feat/consensus-engine`.

## Step 1 — Create a Telegram bot (2 min)
1. In Telegram, open a chat with **@BotFather**.
2. Send `/newbot`, pick a name and a username ending in `bot`.
3. BotFather replies with a **token** like `123456789:AAExxxx...`. Copy it.

## Step 2 — Get your chat ID (1 min)
1. Open a chat with your new bot and send it any message (e.g. `/start`). *(This also lets the bot
   message you — Telegram blocks bots from messaging users who haven't opened the chat first.)*
2. Get your numeric chat ID one of two ways:
   - Easiest: message **@userinfobot** — it replies with your `Id`.
   - Or: open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser (after you messaged
     the bot) and read `message.chat.id`.

## Step 3 — Configure
```bash
cd ~/polymarket-bot
cp .env.consensus.example .env.consensus
# edit .env.consensus and paste in TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID
```

## Step 4 — Launch
```bash
docker compose -f docker-compose.consensus.yml --env-file .env.consensus up -d --build
```
First run builds the image (~3–5 min) and starts Postgres + the bot. You should get a Telegram
message: **"👥 Copy Trading Bot started"** and shortly after **"🛰 Tracking N top traders"**.

## Step 5 — Verify it's working
- **Logs:** `docker compose -f docker-compose.consensus.yml logs -f copy-trading-bot`
  Look for `Leaderboard universe refreshed tracked=…` and `Consensus cycle complete … strategies=14`.
- **In Telegram:** send `/tracked` (trader count), `/consensus` (live signals + the strategy
  scoreboard), `/help`.
- **Metrics:** `curl localhost:9001/metrics | grep consensus`.

## What to expect over time
- It runs **14 strategies forward, silently** — only the `strict` strategy pushes Telegram alerts
  (STRONG/ELITE consensus); the rest accrue evidence without spamming you.
- `/consensus` shows a per-strategy scoreboard. It's empty of *results* until markets resolve
  (sports next-day, others over days/weeks). As signals resolve, you'll see **surplus** (the real,
  favorite-longshot-neutralized edge) and a ✅/⏳ **promotion-gate** flag per strategy.
- **Nothing gets promoted automatically.** When a strategy goes ✅ (positive surplus lower-bound over
  ≥30 distinct events), that's your signal to consider promoting it — a deliberate call, not the bot's.

## Operations
- **Stop:** `docker compose -f docker-compose.consensus.yml down` (Postgres data persists in the
  `pgdata` volume).
- **Restart:** rerun the Step 4 command (omit `--build` if code unchanged).
- **Update after pulling new code:** `git pull` then rerun Step 4 *with* `--build`.
- **Back up the forward record:**
  `docker compose -f docker-compose.consensus.yml exec postgres pg_dump -U bot polymarket > backup.sql`

## Running 24/7
The bot must stay running for the forward record to build. On your Mac, keep Docker Desktop open and
prevent sleep while plugged in (`caffeinate -s` in a terminal, or System Settings → Battery → keep
awake on power). For true always-on, run the same compose on a small cloud VPS (any \$5/mo box with
Docker) — identical commands.

## Safety
Paper/alert-only by design — the consensus path places **no real-money orders** and holds no keys.
The only outbound actions are reading public Polymarket APIs and sending you Telegram messages.
