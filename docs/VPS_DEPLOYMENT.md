# WeatherWatch VPS Deployment

## Overview

WeatherWatch is deployed through a ZIP release.

This is the recommended first deployment method because the GitHub repo is private. The ZIP contains the app code, installer scripts, service template, docs, caption template config, tests, version files, and example environment file.

Real secrets are not included.

## Local Build Steps

From your local WeatherWatch project root:

```bash
./scripts/build_release_zip.sh v0.7.6
```

Expected output:

```text
dist/WeatherWatch-v0.7.6.zip
```

## Upload ZIP To VPS

Upload the ZIP using whichever method is easiest:

- SCP
- SFTP
- hosting provider file manager
- Google Drive download, if preferred

Example SCP:

```bash
scp dist/WeatherWatch-v0.7.6.zip user@server:/tmp/
```

## Prepare Install Directory On VPS

```bash
sudo mkdir -p /opt/weatherwatch
sudo chown $USER:$USER /opt/weatherwatch
```

## Unzip Release

```bash
unzip /tmp/WeatherWatch-v0.7.6.zip -d /opt/weatherwatch
cd /opt/weatherwatch
```

Important: if the ZIP extracts into a nested folder, move into the actual project root before running the install script. The project root contains `requirements.txt`, `.env.example`, and `core/service.py`.

## Run Installer

```bash
chmod +x scripts/install_vps.sh scripts/verify_install.sh
./scripts/install_vps.sh --install-service
```

The installer:

- installs apt packages: `git`, `python3`, `python3-venv`, `python3-pip`, `curl`, `unzip`, `ufw`
- creates `.venv` if missing
- upgrades pip inside `.venv`
- installs Python dependencies from `requirements.txt`
- creates runtime folders
- creates `.env` from `.env.example` only if `.env` does not exist
- applies `chmod 600 .env`
- installs and enables the systemd service if `--install-service` is supplied
- does not start the service automatically

Runtime folders created:

```text
state/
data/
data/template_backups/
data/template_uploads/
output/
logs/
backups/
```

The installer is safe to run multiple times. It never overwrites `.env` and never deletes runtime folders.

## Configure `.env`

```bash
nano .env
```

Required values:

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_ALLOWED_CHAT_IDS=
TELEGRAM_ALLOWED_USER_IDS=
FACEBOOK_PAGE_ID=
FACEBOOK_PAGE_ACCESS_TOKEN=
FACEBOOK_APP_ID=
FACEBOOK_APP_SECRET=
FACEBOOK_REDIRECT_URI=
OPENAI_API_KEY=
ADMIN_DASHBOARD_ENABLED=true
ADMIN_DASHBOARD_HOST=127.0.0.1
ADMIN_DASHBOARD_PORT=8787
```

Security notes:

- Never commit `.env`.
- Never upload `.env` publicly.
- Keep `.env` permissions at `chmod 600 .env`.
- Dashboard should stay bound to `127.0.0.1`.

## Verify Install

```bash
./scripts/verify_install.sh
```

Result meanings:

- `PASS`: check succeeded
- `WARN`: check is not fatal, but needs attention
- `FAIL`: install is incomplete or broken

The verifier checks project root, Python, `.venv`, `.env`, runtime folders, caption template config, Python compile, parser/template verification scripts, systemd status if installed, and `/health` if the dashboard is running.

It never prints secrets.

## Start Service

```bash
sudo systemctl start weatherwatch
sudo systemctl status weatherwatch
```

Logs:

```bash
journalctl -u weatherwatch -f
```

Restart:

```bash
sudo systemctl restart weatherwatch
```

Stop:

```bash
sudo systemctl stop weatherwatch
```

## Dashboard Access

The dashboard is local-only by default.

Use an SSH tunnel:

```bash
ssh -L 8787:127.0.0.1:8787 user@server
```

Open locally:

```text
http://127.0.0.1:8787/admin
http://127.0.0.1:8787/health
```

The dashboard page updates dynamically without a full browser refresh:

- uptime updates locally in the browser every second
- dashboard status refreshes from `/health` every 10 seconds
- `/health` returns local state summaries only and does not expose secrets

Warning: do not expose port `8787` publicly unless authentication, firewall, and reverse proxy protection are added later.

If `ADMIN_DASHBOARD_HOST` is changed to `0.0.0.0`, protect it with a firewall, reverse proxy authentication, or another access control layer before deploying.

## Telegram Verification Checklist

After the service starts, test these commands in Telegram:

```text
/start
/status
/fbstatus
/template_status
/update
```

Use `/approve` only if you are ready to publish to Facebook.

## Process Restart Safety

WeatherWatch uses Telegram polling with indefinite bootstrap retries. If Telegram is unreachable when the app starts, it keeps retrying until the connection works.

On VPS, still run WeatherWatch under `systemd` so the app restarts if Python exits unexpectedly. The service template includes:

```ini
Restart=always
RestartSec=10
```

## Backup Notes

Important runtime files:

```text
state/approval_state.json
state/facebook_token_state.json
config/caption_templates.pagasa.json
data/template_backups/
```

Back up:

```text
state/
config/caption_templates.pagasa.json
data/template_backups/
```

Do not back up:

```text
.env
.venv/
logs/
output/generated/
secrets
```

The `state/` folder is gitignored because it can contain operational secrets.

## Rollback Notes

Basic rollback:

```bash
sudo systemctl stop weatherwatch
cp -a state /tmp/weatherwatch-state-backup
unzip /tmp/WeatherWatch-previous-version.zip -d /opt/weatherwatch-rollback
```

Then restore the previous release into `/opt/weatherwatch`, restore `state/`, ensure `.env` exists, and restart:

```bash
sudo systemctl restart weatherwatch
```

Keep the previous ZIP release available before upgrading.

## What Not To Expose

Never expose:

- `.env`
- `state/`
- dashboard port `8787`
- Facebook tokens
- Telegram bot token
- OpenAI API key

## Future Deployment Improvements

Possible future improvements, not implemented in v0.7.6:

- GitHub deploy key installer
- private repo bootstrap installer
- auto-update
- Docker
- public dashboard with auth
- database migration
