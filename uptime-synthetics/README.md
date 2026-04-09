# up_synthetics — Pi-hole Stack Health Monitor

Monitors all services running on the Raspberry Pi and sends a daily report + instant alerts via **Telegram** and **Email**.

---

## What It Checks (18 Checks)

| Category | Service | Check Type |
|---|---|---|
| **Pi-hole** | DNS | TCP port 53 reachable |
| **Pi-hole** | Admin UI | HTTP reachable |
| **Analytics** | Dashboard | HTTP reachable |
| **Analytics** | Dashboard | systemd service active |
| **Timers** | pihole-analytics-fetch.timer | systemd active |
| **Timers** | pihole-analytics-daily.timer | systemd active |
| **Timers** | pihole-analytics-weekly.timer | systemd active |
| **Timers** | pihole-analytics-monthly.timer | systemd active |
| **Timers** | pihole-analytics-download.timer | systemd active |
| **Timers** | pihole-analytics-sysupdate.timer | systemd active |
| **MCP Bot** | pihole-mcp-watch | systemd service active |
| **NAS** | Samba | TCP port 445 reachable |
| **NAS** | smbd | systemd service active |
| **NAS** | Drive mount | `/mnt/nas` mounted + free space |
| **Network** | Tailscale VPN | connected + peer count |
| **System** | Root disk (/) | usage % (warn >80%, fail >90%) |
| **System** | NAS disk (/mnt/nas) | usage % (warn >80%, fail >90%) |
| **System** | RAM | usage % (warn >80%, fail >90%) |
| **System** | CPU temperature | (warn >70°C, fail >80°C) |

---

## Notifications

### Daily Report (8:00 AM every day)
Always sends — whether everything is healthy or not.

**Telegram** — compact summary grouped by category:
```
✅ Daily Health Report — 2026-04-08 08:00

📊 Summary: 19 OK  |  0 warnings  |  0 failures

✅ Pi-hole
  ✅ Pi-hole DNS: port 53 reachable
  ✅ Pi-hole Admin UI: HTTP 200 OK

✅ NAS
  ✅ Samba NAS (port 445): port 445 reachable
  ✅ NAS drive (/mnt/nas): mounted, 850G free
...
```

**Email** — full HTML report with stat cards (passing / warnings / failures) and a colour-coded table of all 18 checks. Sent to `sumitr@outlook.com`.

### Failure Alerts (every 30 min — disabled by default)
Only sends when something is down. No spam when all is healthy.

To enable:
```bash
ENABLE_ALERTS=yes bash deploy_monitor.sh
```

Or enable manually on the Pi:
```bash
sudo systemctl enable --now pihole-uptime-alert.timer
```

---

## Files

| File | Purpose |
|---|---|
| `monitor.py` | The monitor script — runs all checks, sends notifications |
| `deploy_monitor.sh` | Run on your **laptop** — deploys to the Pi via SSH |
| `install_monitor.sh` | Runs **on the Pi** — installs venv, systemd timers |
| `config.example.yaml` | Config template — copy to `config.yaml` and fill in credentials |
| `config.yaml` | Your actual config (gitignored — never committed) |

---

## Setup (First Time)

### Step 1 — Configure

```bash
cd uptime-synthetics/
cp config.example.yaml config.yaml
nano config.yaml
```

Fill in:
```yaml
pi_host: "localhost"
dashboard_url: "http://localhost:8080"
pihole_url: "http://localhost/admin"
nas_mount: "/mnt/nas"

telegram:
  bot_token: "YOUR_BOT_TOKEN"      # same bot as pihole-mcp-server
  chat_id: "YOUR_CHAT_ID"

email:
  smtp_server: smtp.gmail.com
  smtp_port: 587
  sender_email: you@gmail.com
  sender_password: YOUR_APP_PASSWORD
  recipient_emails:
    - you@example.com
```

### Step 2 — Deploy

```bash
PI_HOST=192.168.68.102 PI_USER=pi bash deploy_monitor.sh
```

The script will:
1. Copy files to the Pi via SSH
2. Set up a Python virtual environment
3. Install systemd timers for daily reports
4. Run a test check immediately

---

## Running On Demand

### From your laptop (via SSH)
```bash
ssh pi@192.168.68.102 "~/uptime-synthetics/venv/bin/python3 ~/uptime-synthetics/monitor.py --mode daily"
```

### Directly on the Pi
```bash
cd ~/uptime-synthetics
venv/bin/python3 monitor.py --mode daily
```

### Modes

| Mode | Command | When it notifies |
|---|---|---|
| `daily` | `monitor.py --mode daily` | Always — full report regardless of status |
| `alert-only` | `monitor.py --mode alert-only` | Only if something is down |

---

## Scheduled Timers

| Timer | Schedule | Mode |
|---|---|---|
| `pihole-uptime-monitor.timer` | Daily at 8:00 AM | `daily` — always sends |
| `pihole-uptime-alert.timer` | Every 30 min *(disabled by default)* | `alert-only` — only on failure |

### View timer status on the Pi
```bash
systemctl list-timers pihole-uptime*
```

### Manually trigger the daily report now
```bash
sudo systemctl start pihole-uptime-monitor.service
```

### View logs
```bash
tail -f ~/uptime-synthetics/logs/monitor.log
```

---

## Redeploying / Updating

```bash
# Redeploy after code changes
PI_HOST=192.168.68.102 PI_USER=pi bash deploy_monitor.sh

# Change daily report time to 9 AM
REPORT_TIME=09:00 PI_HOST=192.168.68.102 PI_USER=pi bash deploy_monitor.sh

# Enable 30-min failure alerts
ENABLE_ALERTS=yes PI_HOST=192.168.68.102 PI_USER=pi bash deploy_monitor.sh
```

---

## Troubleshooting

**No Telegram message received**
- Check bot token and chat ID in `config.yaml`
- Test manually: `venv/bin/python3 monitor.py --mode daily`
- Check logs: `tail -50 ~/uptime-synthetics/logs/monitor.log`

**No email received**
- Check Gmail App Password (not your account password)
- Make sure 2-Step Verification is enabled on the Gmail account
- Check spam/junk folder

**Timer not running**
```bash
systemctl status pihole-uptime-monitor.timer
journalctl -u pihole-uptime-monitor.service -n 30
```

**Check what the last run reported**
```bash
cat ~/uptime-synthetics/logs/monitor.log | tail -30
```
