# Pi-hole Deployment Guide

Deploy both projects to your Raspberry Pi — **pi_hole_web_survillance first**, then **pihole-mcp-server**.

Use the automated script (`3_deploy.sh`) for a one-command deploy, or follow the manual steps below.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Raspberry Pi running Pi-hole | See `1_analytics.md` for Pi setup from scratch |
| Pi-hole Analytics dashboard deployed | Part 1 below |
| SSH key auth to the Pi | `ssh-copy-id pi@YOUR_PI_IP` |
| Gemini API key | [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) — free |
| Telegram bot token | [@BotFather](https://t.me/BotFather) → `/newbot` |
| Your Telegram chat ID | [@userinfobot](https://t.me/userinfobot) |
| Gmail App Password | myaccount.google.com → Security → App passwords |

---

## Automated Deploy

```bash
# Full deploy (first time)
bash 3_deploy.sh

# Quick update (code changes only, no reinstall)
bash 3_deploy.sh --update
```

The script handles everything: rsync, config copy, install, systemd service, verification.

---

## Manual Steps

### Part 1 — pi_hole_web_survillance (Analytics Dashboard)

#### Step 1 — Configure

```bash
cp pi_hole_web_survillance/config/config.example.yaml \
   pi_hole_web_survillance/config/config.yaml
```

Fill in `config/config.yaml`:

```yaml
pihole:
  host: http://localhost        # Pi-hole runs on the same Pi
  password: YOUR_PIHOLE_ADMIN_PASSWORD
  api_token: YOUR_API_TOKEN     # Pi-hole v5 only — Admin → Settings → API

email:
  sender_email: you@gmail.com
  sender_password: xxxx xxxx xxxx xxxx   # Gmail App Password (16 chars)
  recipient_emails:
    - you@email.com

gemini:
  api_key: YOUR_GEMINI_API_KEY
  model: gemini-2.5-flash

dashboard:
  port: 8080
  host: 0.0.0.0
  password: YOUR_DASHBOARD_PASSWORD
  url: http://YOUR_PI_IP:8080
```

#### Step 2 — Deploy to Pi

```bash
rsync -az --exclude='.git/' --exclude='venv/' --exclude='__pycache__/' \
    pi_hole_web_survillance/ pi@YOUR_PI_IP:~/pihole-analytics/

scp pi_hole_web_survillance/config/config.yaml \
    pi@YOUR_PI_IP:~/pihole-analytics/config/config.yaml
```

#### Step 3 — Install

```bash
ssh pi@YOUR_PI_IP "cd ~/pihole-analytics && sudo bash install.sh"
```

The installer:
- Creates a Python venv and installs dependencies
- Sets up all systemd services and timers
- Downloads the UT1 domain category database (~50 MB)
- Adds adult content blocklist to Pi-hole
- Runs the first data fetch

#### Step 4 — Lock permissions

```bash
ssh pi@YOUR_PI_IP "
  sudo chown -R pi:pi ~/pihole-analytics &&
  chmod 600 ~/pihole-analytics/config/config.yaml &&
  chmod 700 ~/pihole-analytics/data/ ~/pihole-analytics/logs/
"
```

#### Step 5 — Fix PYTHONPATH in systemd service

The dashboard service needs `PYTHONPATH` set or it won't start:

```bash
ssh pi@YOUR_PI_IP "
  sudo sed -i '/^ExecStart=/i Environment=PYTHONPATH=/home/pi/pihole-analytics' \
      /etc/systemd/system/pihole-analytics-dashboard.service &&
  sudo systemctl daemon-reload &&
  sudo systemctl restart pihole-analytics-dashboard
"
```

#### Step 6 — Verify

```bash
ssh pi@YOUR_PI_IP "systemctl status pihole-analytics-dashboard"
ssh pi@YOUR_PI_IP "curl -s http://localhost:8080/api/summary"
```

Open dashboard: **http://YOUR_PI_IP:8080**

---

### Part 2 — pihole-mcp-server (Telegram Bot)

> Deploy **after** Part 1 — the bot connects to the dashboard at `http://localhost:8080`.

#### Step 1 — Configure

```bash
cp pihole-mcp-server/config/connectors/pihole.example.yaml \
   pihole-mcp-server/config/connectors/pihole.yaml

cp pihole-mcp-server/config/connectors/telegram.example.yaml \
   pihole-mcp-server/config/connectors/telegram.yaml

cp pihole-mcp-server/config/llm/gemini.example.yaml \
   pihole-mcp-server/config/llm/gemini.yaml
```

**`config/connectors/pihole.yaml`**
```yaml
url: http://localhost:8080          # same Pi as dashboard
password: YOUR_DASHBOARD_PASSWORD   # must match dashboard.password above
```

**`config/connectors/telegram.yaml`**
```yaml
bot_token: YOUR_BOT_TOKEN           # from @BotFather
default_chat_id: "YOUR_CHAT_ID"     # from @userinfobot
```

**`config/llm/gemini.yaml`**
```yaml
api_key: YOUR_GEMINI_API_KEY
model: gemini-2.5-flash
```

#### Step 2 — Deploy to Pi

```bash
rsync -az --exclude='.git/' --exclude='.venv/' --exclude='__pycache__/' \
    pihole-mcp-server/ pi@YOUR_PI_IP:~/pihole-mcp-server/

scp pihole-mcp-server/config/connectors/pihole.yaml \
    pi@YOUR_PI_IP:~/pihole-mcp-server/config/connectors/pihole.yaml
scp pihole-mcp-server/config/connectors/telegram.yaml \
    pi@YOUR_PI_IP:~/pihole-mcp-server/config/connectors/telegram.yaml
scp pihole-mcp-server/config/llm/gemini.yaml \
    pi@YOUR_PI_IP:~/pihole-mcp-server/config/llm/gemini.yaml
```

#### Step 3 — Install dependencies

```bash
ssh pi@YOUR_PI_IP "
  cd ~/pihole-mcp-server &&
  python3 -m venv .venv &&
  .venv/bin/pip install -r requirements.txt
"
```

If blocked by PEP 668:
```bash
ssh pi@YOUR_PI_IP "pip3 install --break-system-packages -r ~/pihole-mcp-server/requirements.txt"
```

#### Step 4 — Verify

```bash
ssh pi@YOUR_PI_IP "
  cd ~/pihole-mcp-server &&
  .venv/bin/python3 llm/gemini_agent.py --prompt 'Is my network healthy?'
"
```

Expected: a plain-English summary. `ConnectionRefusedError` means the dashboard isn't running.

#### Step 5 — Install as a systemd service

```bash
ssh pi@YOUR_PI_IP "sudo tee /etc/systemd/system/pihole-mcp-watch.service > /dev/null" << 'EOF'
[Unit]
Description=Pi-hole Telegram Bot + Watch Agent
After=network.target pihole-analytics-dashboard.service

[Service]
ExecStart=/home/pi/pihole-mcp-server/.venv/bin/python3 /home/pi/pihole-mcp-server/llm/gemini_agent.py --telegram --watch
WorkingDirectory=/home/pi/pihole-mcp-server
Restart=on-failure
RestartSec=30
User=pi

[Install]
WantedBy=multi-user.target
EOF

ssh pi@YOUR_PI_IP "
  sudo systemctl daemon-reload &&
  sudo systemctl enable --now pihole-mcp-watch
"
```

#### Step 6 — Test Telegram

Send `/help` to your bot. You should receive the command list. Then try `/status`.

---

## Scheduled Timers (installed by install.sh)

| Timer | Schedule | Purpose |
|---|---|---|
| `pihole-analytics-fetch` | Every 15 min | Pull DNS queries from Pi-hole into SQLite |
| `pihole-analytics-daily` | 7:00 AM daily | Send daily email report |
| `pihole-analytics-weekly` | 7:10 AM Monday | Send weekly email report |
| `pihole-analytics-monthly` | 7:20 AM on 1st | Send monthly email report |
| `pihole-analytics-download` | Sunday 3:00 AM | Refresh UT1 domain category database |
| `pihole-analytics-sysupdate` | Sunday 4:00 AM | System package updates |

---

## Updating After Code Changes

```bash
# Quick update (no reinstall)
bash 3_deploy.sh --update

# Manual quick update
rsync -az scripts/ config/ pi@YOUR_PI_IP:~/pihole-analytics/
ssh pi@YOUR_PI_IP "sudo systemctl restart pihole-analytics-dashboard"

rsync -az --exclude='.git/' --exclude='.venv/' --exclude='__pycache__/' \
    pihole-mcp-server/ pi@YOUR_PI_IP:~/pihole-mcp-server/
ssh pi@YOUR_PI_IP "sudo systemctl restart pihole-mcp-watch"
```

---

## Useful SSH Commands

```bash
# Dashboard logs
ssh pi@YOUR_PI_IP "journalctl -u pihole-analytics-dashboard -f"

# Telegram bot logs
ssh pi@YOUR_PI_IP "journalctl -u pihole-mcp-watch -f"

# Check all timers
ssh pi@YOUR_PI_IP "systemctl list-timers pihole-analytics*"

# Manual data fetch
ssh pi@YOUR_PI_IP "~/pihole-analytics/venv/bin/python3 ~/pihole-analytics/scripts/data/fetcher.py"

# Test the bot manually
ssh pi@YOUR_PI_IP "cd ~/pihole-mcp-server && .venv/bin/python3 llm/gemini_agent.py --prompt 'Who is on my network?'"
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Dashboard not loading at `:8080` | `sudo systemctl restart pihole-analytics-dashboard` |
| Dashboard crashes on startup | Add `Environment=PYTHONPATH=/home/pi/pihole-analytics` to service — see Step 5 above |
| No data in dashboard | Run fetcher manually; check `logs/fetcher.log` |
| Email not arriving | Verify Gmail App Password (not your Gmail login password) |
| MCP `ConnectionRefusedError` | Dashboard not running — check Part 1 |
| MCP `401 Unauthorized` | `password` in `pihole.yaml` must match `dashboard.password` in `config.yaml` |
| Telegram bot not responding | Check `bot_token` in `telegram.yaml`; verify bot exists |
| Gemini quota error | Wait 1 min; increase `watch_interval_minutes` in `prompts.yaml` |
| `Permission denied` on files | `sudo chown -R pi:pi ~/pihole-analytics ~/pihole-mcp-server` |

---

## Security Notes

```bash
# Lock all config files containing credentials
chmod 600 ~/pihole-analytics/config/config.yaml
chmod 600 ~/pihole-mcp-server/config/connectors/*.yaml
chmod 600 ~/pihole-mcp-server/config/llm/gemini.yaml

# Port 8080 must NOT be exposed to the internet — local network only
# Pi-hole ports 80/443 must NOT be port-forwarded
```

Revoke credentials:
- **Pi-hole password** → Pi-hole admin → Settings → Change password
- **Dashboard password** → update `dashboard.password` in both `config.yaml` files
- **Gmail App Password** → myaccount.google.com → Security → App passwords → delete
- **Gemini API key** → aistudio.google.com → API keys → revoke
- **Telegram bot token** → @BotFather → `/revoke` → update `telegram.yaml`
