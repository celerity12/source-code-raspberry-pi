# Pi-hole Analytics

Self-hosted home network analytics for Pi-hole. Fetches DNS query data every 15 minutes, stores it in SQLite, and serves a real-time web dashboard plus scheduled HTML email reports. Everything stays on your device — no cloud, no third parties.

---

## What It Does

- **Real-time dashboard** — traffic overview, per-device activity, category breakdown, hourly charts, blocked domains, health panel
- **Email reports** — daily, weekly, and monthly HTML reports with charts, device cards, alerts, and system health
- **Device deep-dive** — click any device to see hourly activity, all domains accessed, flagged categories
- **Smart categorization** — classifies every domain into 20+ categories (streaming, social media, gaming, adult, educational, etc.)
- **Security alerts** — flags adult content, VPN/proxy usage, crypto, excessive social media
- **System health** — disk, RAM, CPU, temperature, Pi-hole blocking status, service states
- **Security hardening** — one-command script to lock down the Pi (firewall, fail2ban, SSH keys)

---

## Prerequisites — Raspberry Pi + Pi-hole Setup

If you already have a Pi with Pi-hole running, skip to [Deploy](#deploy).

### What you need

- Raspberry Pi 4 or 5 (4GB+ recommended)
- MicroSD card (32GB+) or USB SSD
- Network cable (recommended over Wi-Fi for a DNS server)

### 1. Install Raspberry Pi OS

1. Download **Raspberry Pi Imager**: https://www.raspberrypi.com/software/
2. Choose OS → **Raspberry Pi OS Lite (64-bit)**
3. Click the ⚙️ gear icon and pre-configure:
   - Hostname: `pihole`
   - Enable SSH: yes
   - Username / password: `pi` / your choice
4. Write to SD card, insert into Pi, power on

### 2. Connect and update

```bash
ssh pi@pihole.local
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl git python3 python3-pip
```

### 3. Assign a static IP

**Easiest — router DHCP reservation:** In your router admin panel, bind the Pi's MAC address to a fixed IP (e.g. `192.168.68.102`). No changes needed on the Pi.

**Alternative — static IP on the Pi:**
```bash
sudo nano /etc/dhcpcd.conf
```
```
interface eth0
static ip_address=192.168.68.102/24
static routers=192.168.68.1
static domain_name_servers=127.0.0.1 8.8.8.8
```
```bash
sudo reboot
```

### 4. Install Pi-hole

```bash
curl -sSL https://install.pi-hole.net | bash
```

Walk through the installer:
- Upstream DNS: **Cloudflare** (1.1.1.1)
- Install web admin: **yes**
- Log queries: **yes**
- Privacy mode: **0** (show everything — required for analytics)

Note your **Pi-hole admin password** shown at the end.

### 5. Point your router DNS to Pi-hole

In your router admin panel → DHCP / LAN Settings:
- **Primary DNS** → Pi's IP (e.g. `192.168.68.102`)
- **Secondary DNS** → `8.8.8.8` (fallback)

Save and restart router. All devices now route DNS through Pi-hole automatically.

### 6. Disable DNS-over-HTTPS in browsers

Modern browsers bypass Pi-hole using encrypted DNS. Disable it:

- **Chrome:** Settings → Privacy → Security → Use secure DNS → **Off**
- **Firefox:** Settings → Privacy → DNS over HTTPS → **Off**

The installer also blocks DoH providers at the Pi-hole level automatically.

---

## Deploy

### 1. Get your credentials

**Pi-hole password** — the password you use to log into `http://PI_IP/admin`

**Pi-hole API token** *(v5 only)* — Admin → Settings → API → Show API token

**Gmail App Password** *(for email reports)*
1. Enable 2-Step Verification at myaccount.google.com
2. Go to https://myaccount.google.com/apppasswords → create → name it `pihole-analytics`
3. Copy the 16-character password

### 2. Configure

```bash
cp config/config.example.yaml config/config.yaml
nano config/config.yaml
```

Minimum required fields:
```yaml
pihole:
  host: http://localhost
  password: YOUR_PIHOLE_ADMIN_PASSWORD
  api_token: YOUR_API_TOKEN           # v5 only

email:
  sender_email: you@gmail.com
  sender_password: xxxx xxxx xxxx xxxx   # Gmail App Password
  recipient_emails:
    - you@gmail.com

dashboard:
  password: CHOOSE_A_DASHBOARD_PASSWORD
  url: http://192.168.68.102:8080
```

### 3. Deploy from your Linux box

```bash
bash deploy.sh
```

The script will ask for Pi IP/user once, then handle everything via SSH. What it does:
- Installs Python venv + sqlite3
- Creates all systemd services and timers
- Downloads UT1 domain category database (~50 MB)
- Adds adult content blocklist to Pi-hole
- Blocks DoH providers
- Runs the first data fetch

Or deploy manually:
```bash
rsync -az --exclude='.git/' --exclude='venv/' . pi@192.168.68.102:~/pihole-analytics/
ssh pi@192.168.68.102 "cd ~/pihole-analytics && sudo bash install.sh"
```

### 4. Lock down permissions

```bash
ssh pi@192.168.68.102 "
  sudo chown -R pi:pi ~/pihole-analytics &&
  chmod 600 ~/pihole-analytics/config/config.yaml &&
  chmod 700 ~/pihole-analytics/data/ ~/pihole-analytics/logs/
"
```

### 5. Verify

```bash
# Dashboard is running
ssh pi@192.168.68.102 "systemctl status pihole-analytics-dashboard"

# Timers are scheduled
ssh pi@192.168.68.102 "systemctl list-timers pihole-analytics*"

# Data was fetched
ssh pi@192.168.68.102 "sqlite3 ~/pihole-analytics/data/analytics.db 'SELECT COUNT(*) FROM queries;'"
```

Open dashboard: **http://192.168.68.102:8080**

### 6. Security hardening *(optional but recommended)*

```bash
bash harden.sh
```

What it does: SSH key auth, disables password login, fail2ban, ufw firewall, kernel hardening, log rotation.

### Updating after code changes

```bash
# Quick update
rsync -az scripts/ config/ pi@192.168.68.102:~/pihole-analytics/
ssh pi@192.168.68.102 "sudo systemctl restart pihole-analytics-dashboard"

# Full reinstall (new deps or systemd units) — safe to re-run
rsync -az --exclude='.git/' --exclude='venv/' . pi@192.168.68.102:~/pihole-analytics/
ssh pi@192.168.68.102 "cd ~/pihole-analytics && sudo bash install.sh"
```

---

## Dashboard

Access at `http://PI_IP:8080` — password protected.

**Sections:**
- Summary cards — total requests, blocked %, unique domains, active devices
- System health — Pi-hole status, disk/RAM/CPU/temp, all service states
- Alert banners — flagged categories with top offending domains
- Device cards — per-device activity; click "View Details" for deep-dive
- Category chart, hourly chart, 30-day trend
- Top blocked domains, new domains seen today

---

## Email Reports

| Report | Schedule | Period |
|---|---|---|
| Daily | 7:00 AM every day | Last 24 hours |
| Weekly | 7:10 AM every Monday | Last 7 days |
| Monthly | 7:20 AM on the 1st | Last 30 days |

Send on-demand: click **📧 Send Report** in the dashboard, or:
```bash
ssh pi@192.168.68.102 '/home/pi/pihole-analytics/venv/bin/python3 \
    /home/pi/pihole-analytics/scripts/reporter.py --period daily'
```

---

## Scheduled Timers

| Timer | Schedule | Purpose |
|---|---|---|
| `pihole-analytics-fetch` | Every 15 min | Fetch DNS queries from Pi-hole |
| `pihole-analytics-daily` | 7:00 AM daily | Send daily email report |
| `pihole-analytics-weekly` | 7:10 AM Monday | Send weekly email report |
| `pihole-analytics-monthly` | 7:20 AM on 1st | Send monthly email report |
| `pihole-analytics-download` | Sunday 3:00 AM | Refresh UT1 category database |
| `pihole-analytics-sysupdate` | Sunday 4:00 AM | System package updates |
| `pihole-analytics-dashboard` | Always on | Web dashboard |

```bash
systemctl list-timers pihole-analytics*
journalctl -u pihole-analytics-dashboard -f
```

---

## Device Identification

Pi-hole sees devices by IP. Add friendly names in `config/config.yaml`:

```bash
# Find your device hostnames
ssh pi@192.168.68.102 'sqlite3 /home/pi/pihole-analytics/data/analytics.db \
  "SELECT DISTINCT client_name, client_ip FROM queries ORDER BY client_name;"'
```

```yaml
# config/config.yaml
client_hostnames:
  "johns-iphone": "John's iPhone"
  "sarahs-ipad": "Sarah's iPad"

client_macs:
  "AA:BB:CC:DD:EE:FF": "John's iPhone"   # most reliable
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Dashboard shows 0 queries | Run fetcher manually; check `logs/fetcher.log` |
| Email not arriving | Wrong Gmail App Password or 2FA not enabled |
| Block button ❌ Failed | Add `password:` to config.yaml (Pi-hole v6) |
| Browser bypassing Pi-hole | Disable DoH in browser (Chrome/Firefox) |
| Device showing as IP | Add hostname to `client_hostnames` in config |
| `Permission denied` on logs | `sudo chown -R pi:pi ~/pihole-analytics/` |
| Dashboard 502 | `journalctl -u pihole-analytics-dashboard -n 50` |

---

## REST API Reference

All endpoints served at `http://PI_IP:8080`. 🔐 = requires session cookie. 🔓 = public.

### Authentication

```
POST /login
Content-Type: application/x-www-form-urlencoded
Body: password=YOUR_DASHBOARD_PASSWORD
```

Sets a session cookie. The MCP connector handles this automatically.

### Overview

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/api/stats` | 🔐 | All-in-one snapshot — summary, categories, top domains, 7d trend |
| GET | `/api/summary` | 🔓 | Network totals — total/blocked queries, unique domains, active devices |
| GET | `/api/health` | 🔐 | System health — disk, RAM, CPU, temp, Pi-hole status |
| GET | `/api/alerts` | 🔓 | Security alerts — adult, VPN, crypto, excessive usage |
| GET | `/api/trend` | 🔓 | Daily query totals over N days |
| GET | `/api/compare` | 🔓 | Today vs yesterday |
| GET | `/api/hourly` | 🔓 | Query counts by hour |

### Devices

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/api/devices` | 🔓 | All active devices with stats |
| GET | `/api/device_registry` | 🔐 | All known devices from MAC registry |
| GET | `/api/device_detail?ip=` | 🔐 | Deep summary + categories for one device |
| GET | `/api/device_domains?ip=` | 🔐 | All domains accessed by one device |
| GET | `/api/device_hourly?ip=` | 🔐 | Hourly counts for one device |
| GET | `/api/date_range` | 🔐 | Per-device summary over date range |
| GET | `/api/all_clients_hourly` | 🔐 | Hourly counts for every device |
| GET | `/api/excessive_usage` | 🔐 | Devices exceeding usage thresholds |

### Categories

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/api/categories` | 🔓 | Category breakdown for a date |
| GET | `/api/category_detail?category=` | 🔓 | Top domains for a category |
| GET | `/api/top_by_category?category=` | 🔐 | Top domains for a category (with IP filter) |
| GET | `/api/client_category_usage` | 🔐 | Category breakdown per device |
| GET | `/api/uncategorized_domains` | 🔐 | Domains not matched to any category |

### Blocking & Search

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/api/blocked_top` | 🔐 | Top domains blocked by Pi-hole |
| GET | `/api/blocked_summary` | 🔐 | Blocked vs allowed counts |
| GET | `/api/manually_blocked` | 🔐 | Domains manually blocked via dashboard |
| POST | `/api/block_domain` | 🔐 | Block a domain |
| POST | `/api/unblock_domain` | 🔐 | Unblock a domain |
| GET | `/api/search?q=` | 🔐 | Search domains by keyword |
| GET | `/api/query_log` | 🔐 | Raw DNS query log with filters |
| GET | `/api/new_domains` | 🔓 | Domains seen for the first time today |

### Reports & AI

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/api/send_report` | 🔓 | Trigger email report (`daily`/`weekly`/`monthly`) |
| POST | `/api/ai_summary` | 🔐 | Generate AI summary via Gemini (on-demand) |
| GET | `/api/ai_summary_stored` | 🔐 | Return last stored AI summary without calling Gemini |
| GET | `/api/ai_eta` | 🔐 | Estimated time for AI summary generation |

### Common query parameters

| Parameter | Description |
|---|---|
| `date` | `YYYY-MM-DD` (default: today) |
| `end_date` | End of date range |
| `start_ts` / `end_ts` | Unix timestamps (alternative to date) |
| `limit` | Max results returned |
| `ip` | Filter by device IP |

---

## Security Notes

```bash
# Lock config (contains credentials)
chmod 600 ~/pihole-analytics/config/config.yaml

# Port 8080 must NOT be exposed to the internet — local network only
# Pi-hole port 80 must NOT be port-forwarded

# Revoke credentials if compromised:
# Pi-hole password → Pi-hole admin → Settings → Change password
# Gmail App Password → myaccount.google.com → Security → App passwords → delete
```
