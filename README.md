# Raspberry Pi Home Server

A self-hosted home network stack running on a Raspberry Pi — combining DNS-level ad blocking, network analytics, AI-powered insights, NAS file storage, and automated health monitoring.

---

## Projects

### Pi-hole Web Surveillance — [`pi_hole_web_survillance/`](pi_hole_web_survillance/)
Analytics dashboard on top of Pi-hole. Tracks every DNS query across all home devices and visualises it in a web UI.

- Real-time dashboard on port `8080`
- Per-device traffic breakdown, top domains, hourly trends
- Security alerts (adult content, VPN, crypto, excessive usage)
- Daily / weekly / monthly HTML email reports with AI summaries (Gemini)
- System health monitoring (disk, RAM, CPU, temperature)

---

### MCP Telegram Bot — [`pihole-mcp-server/`](pihole-mcp-server/)
Telegram bot that lets you query and control Pi-hole using natural language.

- 29 MCP tools exposed to an LLM (Gemini)
- Ask questions in plain English: *"which device used the most data today?"*
- Block/unblock domains via Telegram
- Automatic security alerts every 6 hours
- Connects to the analytics dashboard API

---

### NAS Setup — [`nas-setup/`](nas-setup/)
Turns a USB drive into a network-accessible file share (Samba/SMB).

- 931.5 GB USB drive shared as `celerity12-NAS`
- Password-protected — accessible from Windows, Linux, iOS, Android
- LAN access via `192.168.68.102` and remote access via Tailscale VPN (`100.119.186.7`)
- Fully isolated — does not affect Pi-hole or any other service
- See [`nas-setup/NAS.md`](nas-setup/NAS.md) for connection instructions

---

### Uptime Monitor — [`uptime-synthetics/`](uptime-synthetics/)
Health monitor that checks all 18 services and sends daily reports.

- Checks Pi-hole DNS, admin UI, analytics dashboard, MCP bot, NAS, Tailscale, system resources
- Daily Telegram + email report at 8:00 AM
- Optional 30-min failure alerts (off by default)
- Run on demand via SSH or directly on the Pi

---

## Infrastructure

| Service | Port | Access |
|---|---|---|
| Pi-hole DNS | 53 | All devices |
| Pi-hole Admin | 80 / 443 | LAN only |
| Analytics Dashboard | 8080 | LAN + Tailscale |
| Samba NAS | 139 / 445 | LAN + Tailscale |
| Tailscale VPN | — | Encrypted tunnel |

**Pi IP:** `192.168.68.102` (LAN) · `100.119.186.7` (Tailscale)

---

## Deployment

Each project has its own deploy script. Run from your laptop:

```bash
# Analytics dashboard + MCP bot
bash 3_deploy.sh

# NAS
source nas-setup/config.sh && bash nas-setup/deploy_nas.sh

# Uptime monitor
PI_HOST=192.168.68.102 PI_USER=pi bash uptime-synthetics/deploy_monitor.sh
```

---

## Docs

| Doc | Description |
|---|---|
| [`nas-setup/NAS.md`](nas-setup/NAS.md) | NAS setup, access instructions, family sharing |
| [`uptime-synthetics/README.md`](uptime-synthetics/README.md) | Health monitor setup, on-demand runs, timers |
| [`pi_hole_web_survillance/README.md`](pi_hole_web_survillance/README.md) | Analytics dashboard setup |
| [`pihole-mcp-server/README.md`](pihole-mcp-server/README.md) | Telegram bot setup |
