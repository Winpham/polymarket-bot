# Always-on + auto-update

The consensus bot is set up to **stay running** and **auto-deploy new code** with no manual steps,
via two macOS launchd agents (in `~/Library/LaunchAgents/`).

## What's running
- **`com.tue.consensus.updater`** — runs `scripts/consensus-autoupdate.sh` at login and every 5 min:
  - starts Docker Desktop if it isn't running (so it recovers after a reboot),
  - fast-forwards the repo to its upstream if one is configured (safe, ff-only),
  - **rebuilds + recreates the stack whenever code changes land** (new commits touching
    `common/`, `copy-trading-bot/`, `migrations/`, `Cargo.*`, the Dockerfile, or the compose file),
  - brings the stack back up if it's ever down.
  - Doc/report-only commits are recorded but do **not** trigger a rebuild.
- **`com.tue.consensus.caffeinate`** — `caffeinate -s`, kept alive: prevents the Mac from sleeping
  **while on power** (unplugged, it still sleeps, to save battery).
- The containers themselves use `restart: unless-stopped`, and Postgres data persists in the
  `pgdata` volume.

So: code you (or a future session) commit auto-deploys within ~5 min; a reboot recovers on its own
once you log in; sleep-on-power is prevented.

## The one honest limit
A laptop isn't a server. This keeps it running whenever the Mac is **on and logged in** (awake on
power). It will NOT run while the Mac is shut down or asleep on battery. For genuine 24/7, run the
same `docker compose -f docker-compose.consensus.yml --env-file .env.consensus up -d` on a small
always-on box (any ~$5/mo VPS with Docker) — the auto-update agent works there too (it's a launchd
agent on macOS; on Linux use a cron or systemd timer calling the same script).

## Optional: make Docker start instantly at login
The updater launches Docker itself, but for zero startup lag enable it in
**Docker Desktop → Settings → General → "Start Docker Desktop when you sign in."**

## Managing the agents
```bash
# status
launchctl list | grep consensus
# see what the updater is doing
tail -f ~/polymarket-bot/.autoupdate.log
# pause auto-update / keep-alive
launchctl unload ~/Library/LaunchAgents/com.tue.consensus.updater.plist
launchctl unload ~/Library/LaunchAgents/com.tue.consensus.caffeinate.plist
# resume
launchctl load -w ~/Library/LaunchAgents/com.tue.consensus.updater.plist
launchctl load -w ~/Library/LaunchAgents/com.tue.consensus.caffeinate.plist
# force an update check now
bash ~/polymarket-bot/scripts/consensus-autoupdate.sh
```

## Manual stop (and it won't auto-restart)
`launchctl unload` the updater first (else it brings the stack back up within 5 min), then
`docker compose -f docker-compose.consensus.yml --env-file .env.consensus down`.
