# Deployment Guide

Deploy Pi-hole Analytics from your Linux box to a Raspberry Pi running Ubuntu.

> **Shortcut:** `bash deploy.sh` walks through every step interactively.

---

## Prerequisites

**Linux box:** `ssh`, `rsync`

**Raspberry Pi:**
- Ubuntu 22.04/24.04 (64-bit), Pi-hole v6 installed and running
- SSH enabled, internet access, known IP address

---

## Fresh Install

### 1. Get your credentials

**Pi-hole admin password**
The password you use to log into `http://PI_IP/admin`. Add to `config/config.yaml` → `pihole.password`.

**Pi-hole API token** *(legacy v5 fallback)*
Admin → Settings → API → Show API token. Add to `config/config.yaml` → `pihole.api_token`.

**Gmail App Password**
1. myaccount.google.com → Security → 2-Step Verification must be ON
2. Search "App passwords" → Create → name it "Pi-hole Analytics"
3. Copy the 16-char password into `config/config.yaml` → `email.sender_password`

**Device names** *(optional but recommended)*
Find device IPs in your router's DHCP table or at `http://PI_IP/admin` → Network.
Add to `config/config.yaml` under `clients`.

> Assign static DHCP leases in your router so IPs never change.

---

### 2. Edit config

```bash
nano config/config.yaml
```

Minimum required fields:
```yaml
pihole:
  host: http://localhost
  api_token: PASTE_LEGACY_TOKEN_HERE
  password: PASTE_ADMIN_PASSWORD_HERE   # Pi-hole v6 — same as web UI login

email:
  sender_email: you@gmail.com
  sender_password: xxxx xxxx xxxx xxxx
  recipient_emails:
    - you@gmail.com

clients:
  "192.168.68.100": "Dad's iPhone"
```

---

### 3. Copy files to Pi

```bash
rsync -az --exclude='.git/' --exclude='.claude/' --exclude='venv/' \
    . USER@PI_IP:~/pihole-analytics/
```

---

### 4. Run the installer

```bash
ssh USER@PI_IP "cd ~/pihole-analytics && sudo bash install.sh"
```

The installer:
- Installs `python3-venv`, `sqlite3` via apt
- Creates a Python venv and installs dependencies
- Writes and enables all systemd services and timers
- Downloads UT1 third-party domain DB (~50 MB)
- Adds adult content blocklist to Pi-hole
- Blocks DoH providers so browsers can't bypass Pi-hole
- Runs the first data fetch

---

### 5. Lock down permissions

```bash
ssh USER@PI_IP "sudo chown -R USER:USER ~/pihole-analytics && \
    chmod 600 ~/pihole-analytics/config/config.yaml && \
    chmod 700 ~/pihole-analytics/data/ ~/pihole-analytics/logs/"
```

---

### 6. Verify

```bash
# Dashboard is running
ssh USER@PI_IP "systemctl status pihole-analytics-dashboard"

# Timers are scheduled
ssh USER@PI_IP "systemctl list-timers pihole-analytics*"

# Data was fetched
ssh USER@PI_IP "sqlite3 ~/pihole-analytics/data/analytics.db 'SELECT COUNT(*) FROM queries;'"

# Open dashboard
open http://PI_IP:8080
```

---

### 7. Test email

```bash
ssh USER@PI_IP "sudo -u USER /home/USER/pihole-analytics/venv/bin/python3 \
    /home/USER/pihole-analytics/scripts/reporter.py --period daily"
```

Or click **📧 Send Report** in the dashboard.

---

### 8. Configure Pi-hole upstream DNS

1. Open `http://PI_IP/admin` → Settings → DNS
2. Under **Upstream DNS Servers** check both IPv4 and IPv6 for **Cloudflare (DNSSEC)**
3. Save

This ensures Pi-hole resolves non-blocked domains reliably.

---

### 9. Set your router to use Pi-hole as DNS

In your router's DHCP settings, set the DNS server to `PI_IP`. This ensures all devices on your network use Pi-hole automatically — including phones and smart TVs.

---

## Adult Content Blocking

The installer handles this automatically. To set it up manually:

```bash
# Add adult content blocklist
ssh USER@PI_IP "sqlite3 /etc/pihole/gravity.db \
    \"INSERT OR IGNORE INTO adlist (address, enabled, comment) \
    VALUES ('https://blocklistproject.github.io/Lists/porn.txt', 1, 'Adult content');\" \
    && pihole -g"

# Block DoH providers (prevents browsers bypassing Pi-hole)
ssh USER@PI_IP "sudo pihole denylist add dns.google dns64.dns.google \
    one.one.one.one 1dot1dot1dot1.cloudflare-dns.com \
    mozilla.cloudflare-dns.com dns.quad9.net dns10.quad9.net"
```

**Note on Chrome:** Chrome has built-in DNS-over-HTTPS (DoH) that can bypass Pi-hole even after blocking DoH domains. Disable it per browser:
- Chrome → Settings → Privacy and Security → Security → **Use secure DNS** → Off
- Firefox → Settings → Privacy & Security → DNS over HTTPS → **Off**

Safari and most mobile browsers use system DNS and are blocked automatically.

---

## Upgrade (after code changes)

```bash
# Push changed scripts and config
rsync -az scripts/ USER@PI_IP:~/pihole-analytics/scripts/
rsync -az config/  USER@PI_IP:~/pihole-analytics/config/

# Fix ownership and restart
ssh USER@PI_IP "sudo chown -R USER:USER ~/pihole-analytics && \
    sudo systemctl restart pihole-analytics-dashboard"
```

To upgrade the full install (new systemd units, new dependencies):
```bash
rsync -az --exclude='.git/' --exclude='.claude/' --exclude='venv/' \
    . USER@PI_IP:~/pihole-analytics/
ssh USER@PI_IP "cd ~/pihole-analytics && sudo bash install.sh && \
    sudo chown -R USER:USER ~/pihole-analytics"
```

> `install.sh` is idempotent — safe to re-run on an existing install.

---

## Ongoing Management

| Task | Command (run on Pi or via ssh) |
|------|-------------------------------|
| Manual fetch | `sudo -u USER VENV/python3 scripts/fetcher.py` |
| Restart dashboard | `sudo systemctl restart pihole-analytics-dashboard` |
| View fetch log | `journalctl -u pihole-analytics-fetch -f` |
| Add a device | `nano ~/pihole-analytics/config/config.yaml` (no restart needed) |
| Update config | Edit `config.yaml` → restart dashboard |
| Refresh UT1 DB | `sudo -u USER VENV/python3 scripts/downloader.py` |
| Block a domain | Use 🚫 button in dashboard or `sudo pihole denylist add DOMAIN` |
| Unblock a domain | Use ✅ Unblock in dashboard or `sudo pihole denylist remove DOMAIN` |

`VENV` = `/home/USER/pihole-analytics/venv/bin`

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `Permission denied` on log files | `sudo chown -R USER:USER ~/pihole-analytics/` |
| Dashboard 502 / not starting | `journalctl -u pihole-analytics-dashboard -n 50` |
| No data after install | Run fetcher manually, check `logs/fetcher.log` |
| Email fails: "Username and Password not accepted" | Wrong App Password or 2-Step Verification not enabled |
| Email fails: connection timeout | Firewall blocking port 587 outbound |
| `no such table: daily_summary` | Run fetcher once: it creates all tables |
| UT1 download failed during install | Re-run `downloader.py` manually — not critical |
| Block button shows ❌ Failed | Add `password:` to config.yaml (Pi-hole v6 admin password) |
| Site not blocked despite being in deny list | Browser DoH bypassing Pi-hole — disable DoH in browser settings |
| Pi-hole DNS not applying to a device | Check router DHCP DNS setting points to PI_IP |
| `dig DOMAIN +short` returns real IP not 0.0.0.0 | Device using a non-Pi-hole DNS (check `/etc/resolv.conf`) |

---

## Security Checklist

```bash
# Lock config (contains API token + Gmail password)
chmod 600 ~/pihole-analytics/config/config.yaml
chown USER:USER ~/pihole-analytics/config/config.yaml

# Restrict data and logs
chmod 700 ~/pihole-analytics/data/ ~/pihole-analytics/logs/

# Verify config.yaml is gitignored (on Linux box)
grep config.yaml .gitignore

# Pi-hole port 80 must NOT be port-forwarded to the internet
# Only trusted users should have SSH access to the Pi
```

Revoke credentials if compromised:
- **Pi-hole password:** Pi-hole admin → Settings → Change password → update config.yaml
- **Gmail App Password:** myaccount.google.com → Security → App passwords → trash icon
