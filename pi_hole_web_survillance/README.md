# Pi-hole Analytics

Self-hosted home network analytics for Pi-hole. Fetches DNS query data every 15 minutes, stores it in SQLite, and serves a real-time web dashboard plus scheduled HTML email reports. Everything stays on your device — no cloud, no third parties.

---

## What It Does

- **Real-time dashboard** — traffic overview, per-device activity, category breakdown, hourly charts, blocked domains, health panel
- **Email reports** — daily, weekly, and monthly HTML reports with charts, device cards, alerts, and system health
- **Device deep-dive** — click any device to see hourly activity, all domains accessed, flagged categories, time-of-day breakdown
- **Smart categorization** — classifies every domain into 20+ categories (streaming, social media, gaming, adult, educational, etc.) using config rules + UT1 database (~3M domains)
- **Security alerts** — flags adult content, VPN/proxy usage, crypto, excessive social media
- **System health** — disk, RAM, CPU, temperature, Pi-hole blocking status, service states, data gaps
- **Security hardening** — one-command script to lock down the Pi (firewall, fail2ban, SSH keys, kernel hardening)

---

## Prerequisites — Raspberry Pi 5 + Pi-hole Setup

If you already have a Pi with Pi-hole running, skip to [Quick Start](#quick-start).

### What you need

- Raspberry Pi 5 (4GB or 8GB recommended)
- MicroSD card (32GB+) or USB SSD
- Power supply (official 27W USB-C for Pi 5)
- Network cable (recommended over Wi-Fi for a DNS server)

### Step 1 — Install Raspberry Pi OS

1. Download **Raspberry Pi Imager**: https://www.raspberrypi.com/software/
2. Insert your SD card and open Imager
3. Choose OS → **Raspberry Pi OS Lite (64-bit)** — no desktop needed
4. Click the ⚙️ gear icon before writing and pre-configure:
   - Hostname: `pihole`
   - Enable SSH: yes
   - Username / password: `pi` / your choice
   - Configure Wi-Fi if not using ethernet
5. Write to SD card, insert into Pi, power on

### Step 2 — Connect to the Pi

```bash
ssh pi@pihole.local
# or use IP directly if .local doesn't resolve:
ssh pi@YOUR_PI_IP
```

### Step 3 — Assign a Static IP

Pi-hole must have a fixed IP — if it changes, all devices lose DNS.

**Option A — DHCP Reservation on your router (easiest):**
In your router admin panel find "DHCP Reservation" or "Static Lease" and bind your Pi's MAC address to a fixed IP. No changes needed on the Pi.

**Option B — Static IP on the Pi itself:**
```bash
sudo nano /etc/dhcpcd.conf
```
Add at the bottom (adjust to your network):
```
interface eth0
static ip_address=192.168.68.102/24
static routers=192.168.68.1
static domain_name_servers=127.0.0.1 8.8.8.8
```
```bash
sudo reboot
```

### Step 4 — Update the system

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl git python3 python3-pip
```

### Step 5 — Install Pi-hole

```bash
curl -sSL https://install.pi-hole.net | bash
```

Walk through the installer:
- Network interface: `eth0` (ethernet) or `wlan0` (Wi-Fi)
- Upstream DNS: **Cloudflare** (1.1.1.1) or **Google** (8.8.8.8)
- Install web admin interface: **yes**
- Install lighttpd: **yes**
- Log queries: **yes**
- Privacy mode: **0** (show everything — required for analytics)

Note your **Pi-hole admin password** shown at the end.

### Step 6 — Get your Pi-hole API credentials

Open `http://YOUR_PI_IP/admin` in a browser:
- **Pi-hole v6**: your web interface password is the API credential — set it under Settings → Change Password
- **Pi-hole v5**: Settings → API → Show API token → copy it

### Step 7 — Set up Gmail App Password (for email reports)

1. Enable 2-Step Verification on your Google account
2. Go to https://myaccount.google.com/apppasswords
3. Create a new app password → name it `pihole-analytics`
4. Copy the 16-character password shown

### Step 8 — Point your router DNS to Pi-hole

In your router admin panel → DHCP / LAN Settings:
- **Primary DNS** → your Pi's IP (e.g. `192.168.68.102`)
- **Secondary DNS** → `8.8.8.8` (fallback if Pi is down)

Save and restart router. All devices now route DNS through Pi-hole automatically.

---

## Architecture

```
Pi-hole API  ──(every 15 min)──▶  fetcher.py  ──▶  analytics.db (SQLite)
                                                           │
                                       ┌───────────────────┼────────────────┐
                                       ▼                   ▼                ▼
                                 reporter.py         dashboard.py     analytics.py
                                (email reports)     (Flask entry)    (shared queries)
                                       │                   │
                                  health.py          routes_api.py
                               (system metrics)      routes_auth.py
                                                     routes_pages.py
                                                     dashboard_html.py
                                                     summarizer.py (AI)
```

---

## Quick Start

### 1. Prerequisites

- Raspberry Pi running Pi-hole v5 or v6
- Linux/Mac machine to run deploy scripts from
- Gmail account with 2-Step Verification enabled (for email reports)

### 2. Configure

```bash
cp config/config.example.yaml config/config.yaml
nano config/config.yaml
```

Fill in:
- `pihole.password` — your Pi-hole web interface password
- `pihole.api_token` — Pi-hole admin → Settings → API → Show token
- `email.sender_email` / `sender_password` — Gmail + App Password
- `email.recipient_emails` — who receives the reports
- `dashboard.url` — `http://YOUR_PI_IP:8080`
- `dashboard.password` — password to protect the web dashboard

### 3. Deploy

```bash
bash deploy.sh
```

Or if already installed, update with:

```bash
bash update.sh
```

Both scripts ask for Pi IP/user once, then handle everything via SSH.

---

## Router Setup — Point All Devices to Pi-hole

For Pi-hole to see and filter **all** devices on your network, your router must use the Pi as its DNS server.

### Option A — Router DHCP (recommended, covers all devices automatically)

1. Log into your router admin panel (usually `http://192.168.1.1` or `http://192.168.68.1`)
2. Find **DHCP Settings** or **LAN Settings**
3. Set **Primary DNS** to your Pi IP: `192.168.68.102`
4. Set **Secondary DNS** to `8.8.8.8` (fallback if Pi is down)
5. Save and restart router
6. Reconnect all devices — they will now use Pi-hole automatically

> **Tip:** Assign your Pi a **static IP** in the router's DHCP reservation list so it never changes. Look for "DHCP Reservation", "Static Lease", or "Address Reservation" — bind the Pi's MAC address to `192.168.68.102`.

### Option B — Per-device (manual, less ideal)

On each device, manually set DNS to `192.168.68.102` in Wi-Fi settings. Useful for testing before changing the router.

### Option C — Disable DNS-over-HTTPS (DoH) on browsers

Modern browsers bypass Pi-hole using their own encrypted DNS. Disable this:

**Chrome:** Settings → Privacy → Security → Use secure DNS → **Off**

**Firefox:** Settings → Privacy → DNS over HTTPS → **Off**

**Or** block DoH providers at the Pi-hole level (already done by `install.sh`):
- `dns.google`, `one.one.one.one`, `dns.quad9.net`, `mozilla.cloudflare-dns.com`

### Verify Pi-hole is working

After router change, visit any device's browser and go to:
```
http://192.168.68.102/admin
```
You should see DNS queries flowing in the Pi-hole dashboard.

---

## Device Identification

Pi-hole sees devices by IP. Since IPs change (DHCP) and MACs rotate (Apple/Android privacy), use **hostname matching** — the most reliable method.

Find your device hostnames:
```bash
ssh pi@192.168.68.102 'sqlite3 /home/pi/pihole-analytics/data/analytics.db \
  "SELECT DISTINCT client_name, client_ip FROM queries ORDER BY client_name;"'
```

Then in `config/config.yaml`:
```yaml
# Hostname pattern → friendly name (survives MAC randomization + IP changes)
client_hostnames:
  "johns-iphone": "John's iPhone"
  "sarahs-ipad": "Sarah's iPad"
  "sarahs-macbook": "Sarah's MacBook"
  "dads-macbook": "Dad's MacBook"

# MAC address → name (most reliable, survives everything)
# Disable "Private Wi-Fi Address" on Apple devices to use this
client_macs:
  "AA:BB:CC:DD:EE:FF": "John's iPhone"
```

**Resolution priority:**
1. MAC-based name (best)
2. Hostname pattern match (good — works with MAC randomization)
3. IP-based name (unreliable)
4. Auto-detected type (iPhone, iPad, MacBook, Xbox, etc.)
5. Raw hostname
6. Raw IP

---

## Email Reports

| Report | Schedule | Period Covered |
|--------|----------|----------------|
| Daily | 7:00 AM every day | Last 24 hours |
| Weekly | 7:10 AM every Monday | Last 7 days |
| Monthly | 7:20 AM on the 1st of the month | Last 30 days |

Each report includes:
- Network overview (total/blocked queries, unique domains, active devices)
- Alert banner (adult content, VPN, crypto detected)
- Risky category detail with top domains
- Per-device cards with activity summary
- Category chart and breakdown table
- Protection stats (top blocked domains)
- New domains seen for first time
- Trend table (weekly/monthly)
- System health (Pi-hole status, disk/RAM/CPU, service states, errors)

Send on-demand from the dashboard **📧 Send Report** button, or via SSH:
```bash
ssh pi@192.168.68.102 '/home/pi/pihole-analytics/venv/bin/python3 \
    /home/pi/pihole-analytics/scripts/reporter.py --period daily'
```

---

## Dashboard

Access at `http://PI_IP:8080` — password protected.

**Sections:**
- **Summary cards** — total requests, blocked %, unique domains, active devices
- **System Health** — Pi-hole blocking status, gravity count, disk/RAM/CPU/temp, all service states
- **Alert banners** — flagged categories with top offending domains
- **Device cards** — per-device activity with category breakdown; click "View Details" for deep-dive
- **Category chart** — donut chart of traffic by category
- **Hourly chart** — query volume by hour
- **Top blocked domains** — what Pi-hole stopped
- **New domains** — first-seen domains today
- **Trend chart** — 30-day daily traffic

**API endpoints:**

| Endpoint | Description |
|----------|-------------|
| `GET /api/summary` | Network totals |
| `GET /api/devices` | Per-device stats |
| `GET /api/categories` | Category breakdown |
| `GET /api/alerts` | Alert categories |
| `GET /api/hourly` | Per-hour counts |
| `GET /api/trend` | Daily totals (30d) |
| `GET /api/new_domains` | First-seen domains |
| `GET /api/blocked_top` | Top blocked domains |
| `GET /api/health` | System health metrics |
| `GET /api/device_detail` | Deep-dive for one device |
| `POST /api/send_report` | Trigger email report |

---

## Scheduling (Systemd Timers)

| Timer | Schedule | Purpose |
|-------|----------|---------|
| `pihole-analytics-fetch.timer` | Every 15 min | Fetch DNS queries from Pi-hole API |
| `pihole-analytics-aisummary.timer` | 5:00 AM daily | Generate AI summary (Gemini) |
| `pihole-analytics-daily.timer` | 7:00 AM daily | Send daily email report |
| `pihole-analytics-weekly.timer` | 7:10 AM every Monday | Send weekly email report |
| `pihole-analytics-monthly.timer` | 7:20 AM on 1st of month | Send monthly email report |
| `pihole-analytics-download.timer` | Sunday 3:00 AM | Refresh UT1 category database |
| `pihole-analytics-sysupdate.timer` | Sunday 4:00 AM | System package updates |
| `pihole-analytics-dashboard.service` | Always on | Web dashboard |

```bash
# Check all timers
systemctl list-timers pihole-analytics*

# Check dashboard
systemctl status pihole-analytics-dashboard

# Watch live logs
journalctl -u pihole-analytics-fetch -f
journalctl -u pihole-analytics-dashboard -f
```

---

## Security Hardening

Run once from your Linux box:
```bash
bash harden.sh
```

**What it does:**
1. Updates all system packages
2. Enables automatic security updates (unattended-upgrades)
3. Sets up SSH key authentication, disables password login
4. Installs fail2ban — blocks IPs after 3 failed SSH attempts for 24h
5. Configures ufw firewall — only SSH + DNS + LAN ports open
6. Disables unused services (Bluetooth, CUPS, Avahi)
7. Kernel hardening — blocks MITM, SYN flood, hides kernel pointers
8. Restricts Pi-hole admin to LAN only
9. Configures log rotation

After hardening, SSH uses key auth automatically:
```bash
ssh pi@192.168.68.102   # no password needed
```

---

## Categorization

Each domain is classified in order:

1. **Cache** — previously seen domain, instant lookup
2. **Config rules** — `categories` block in `config.yaml` (20+ categories, domain + keyword matching)
3. **UT1 database** — University of Toulouse ~3M domains, 90 categories, refreshed weekly
4. **Fallback** — `other`

Categories include: streaming, social_media, gaming, adult, educational, ads_tracking, tech, shopping, finance, health, news, travel, music, food, productivity, smart_home, vpn_proxy, crypto, sports, government

---

## Troubleshooting

**Dashboard shows 0% blocked**
```bash
# Check Pi-hole blocking is enabled
ssh pi@192.168.68.102 'python3 -c "
import requests
r = requests.post(\"http://localhost/api/auth\", json={\"password\":\"YOUR_PASSWORD\"})
sid = r.json()[\"session\"][\"sid\"]
print(requests.get(\"http://localhost/api/dns/blocking\", headers={\"X-FTL-SID\": sid}).json())
"'

# Rebuild daily summaries
ssh pi@192.168.68.102 'cd /home/pi/pihole-analytics && venv/bin/python3 -c "
import sqlite3, sys; sys.path.insert(0,\"scripts\")
from fetcher import rebuild_daily_summary
conn = sqlite3.connect(\"data/analytics.db\"); conn.row_factory = sqlite3.Row
[rebuild_daily_summary(conn, r[0]) for r in conn.execute(\"SELECT DISTINCT date FROM queries\")]
conn.close(); print(\"Done\")
"'
```

**No data in dashboard**
```bash
ssh pi@192.168.68.102 'cd /home/pi/pihole-analytics && venv/bin/python3 scripts/fetcher.py'
tail -f /home/pi/pihole-analytics/logs/fetcher.log
```

**Email not sending**
```bash
tail -f /home/pi/pihole-analytics/logs/reporter.log
# Causes: wrong Gmail App Password, 2FA not enabled, port 587 blocked by ISP
```

**Device names showing as IPs**
```bash
# Find device hostnames
ssh pi@192.168.68.102 'sqlite3 /home/pi/pihole-analytics/data/analytics.db \
  "SELECT DISTINCT client_name, client_ip FROM queries ORDER BY client_name;"'
# Add to client_hostnames in config/config.yaml then run: bash update.sh
```

**SSH locked out**
```bash
# Mount SD card on Linux box
sudo sed -i 's/PasswordAuthentication no/PasswordAuthentication yes/' \
    /media/USER/rootfs/etc/ssh/sshd_config
# Eject, reboot Pi, then: ssh-copy-id pi@PI_IP
```

**Check database**
```bash
sqlite3 /home/pi/pihole-analytics/data/analytics.db \
    "SELECT date, SUM(total_queries), SUM(blocked_queries) FROM daily_summary GROUP BY date ORDER BY date DESC LIMIT 7;"
```

---

## Privacy

All data stays on your Pi. The only external connections are:
- **Gmail SMTP** — outbound only, to addresses you configure
- **UT1 domain database** — weekly download from University of Toulouse (dsi.ut-capitole.fr)
- **Pi-hole API** — localhost only

---

## Files

```
pihole-analytics/
├── scripts/
│   ├── fetcher.py          # Fetches queries from Pi-hole API, stores in SQLite
│   ├── analytics.py        # All database queries used by dashboard + reporter
│   ├── dashboard.py        # Flask app entry point, auth, blueprint registration
│   ├── dashboard_html.py   # Dashboard HTML/CSS/JS template
│   ├── routes_api.py       # /api/* endpoints Blueprint
│   ├── routes_auth.py      # Login / logout Blueprint
│   ├── routes_pages.py     # Page routes Blueprint
│   ├── reporter.py         # HTML email report generator
│   ├── summarizer.py       # AI-powered daily summary (Gemini)
│   ├── health.py           # System health metrics (disk, RAM, CPU, services)
│   ├── downloader.py       # Downloads UT1 third-party category database
│   ├── device_resolver.py  # MAC/hostname → friendly device name resolution
│   ├── constants.py        # Shared category icons, colours, alert thresholds
│   └── config.py           # Config loader and validator
├── config/
│   ├── config.yaml         # Your settings (gitignored — contains secrets)
│   └── config.example.yaml # Template — copy to config.yaml to start
├── data/                   # SQLite databases (gitignored)
├── logs/                   # Log files (gitignored)
├── reports/                # Saved HTML reports (gitignored)
├── apphealth.sh            # Quick on-Pi health check script
├── install.sh              # Full installer for fresh Pi
├── update.sh               # Update existing deployment
├── harden.sh               # Security hardening script
└── deploy.sh               # First-time deploy from Linux box
```
