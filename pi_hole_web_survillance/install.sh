#!/usr/bin/env bash
# ============================================================
# Pi-hole Analytics - Installer for Raspberry Pi 5 (Ubuntu)
# Run as: sudo bash install.sh
# ============================================================
set -euo pipefail

# Default to the invoking user's home dir so install.sh works standalone.
# deploy.sh patches these values via sed before running remotely.
SERVICE_USER="${SUDO_USER:-$(logname 2>/dev/null || echo ubuntu)}"
INSTALL_DIR="/home/${SERVICE_USER}/pihole-analytics"
PYTHON="python3"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

[[ $EUID -ne 0 ]] && error "Please run as root: sudo bash install.sh"

info "=== Pi-hole Analytics Installer ==="

# ── 1. System packages ─────────────────────────────────────
info "Installing system dependencies..."
apt-get update -qq || error "apt-get update failed — check internet connection"
apt-get install -y -qq python3 python3-pip python3-venv sqlite3 curl || error "apt-get install failed"

# ── 2. Create directory structure ──────────────────────────
info "Creating install directory at $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"/{config,data,reports,logs,scripts}

# Copy scripts from current directory (skip if already in the install dir)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ "$SCRIPT_DIR" != "$INSTALL_DIR" ]]; then
    cp -r "$SCRIPT_DIR/scripts/."      "$INSTALL_DIR/scripts/"
    cp -r "$SCRIPT_DIR/config/."       "$INSTALL_DIR/config/"
    cp -f "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/requirements.txt" 2>/dev/null || true
fi

# ── 3. Python virtual environment ──────────────────────────
info "Setting up Python virtual environment..."
sudo -u "$SERVICE_USER" $PYTHON -m venv "$INSTALL_DIR/venv"
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install -q --upgrade pip
# Install from requirements.txt; fall back to known-good set if file absent
if [[ -f "$INSTALL_DIR/requirements.txt" ]]; then
    sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install -q \
        -r "$INSTALL_DIR/requirements.txt"
else
    sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install -q \
        "flask>=3.0" "pyyaml>=6.0" "requests>=2.31"
fi

PYTHON_BIN="$INSTALL_DIR/venv/bin/python3"

# Chown after venv creation so all files (including venv) are owned by service user
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

# ── 4. Systemd services ────────────────────────────────────
info "Installing systemd services..."

# -- Fetcher timer (every 15 minutes) --
cat > /etc/systemd/system/pihole-analytics-fetch.service <<EOF
[Unit]
Description=Pi-hole Analytics - Data Fetcher
After=network.target

[Service]
Type=oneshot
User=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONPATH=$INSTALL_DIR
ExecStart=$PYTHON_BIN $INSTALL_DIR/scripts/data/fetcher.py
StandardOutput=append:$INSTALL_DIR/logs/fetcher.log
StandardError=append:$INSTALL_DIR/logs/fetcher.log
EOF

cat > /etc/systemd/system/pihole-analytics-fetch.timer <<EOF
[Unit]
Description=Pi-hole Analytics - Fetch every 15 min
Requires=pihole-analytics-fetch.service

[Timer]
OnCalendar=*:0/15
Persistent=true

[Install]
WantedBy=timers.target
EOF

# -- Daily Report (last 24 hours — every day at 7 PM) --
cat > /etc/systemd/system/pihole-analytics-daily.service <<EOF
[Unit]
Description=Pi-hole Analytics - Daily Email Report (last 24 hours)
After=network.target pihole-analytics-fetch.service

[Service]
Type=oneshot
User=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONPATH=$INSTALL_DIR
ExecStart=$PYTHON_BIN $INSTALL_DIR/scripts/core/reporter.py --period daily
StandardOutput=append:$INSTALL_DIR/logs/reporter.log
StandardError=append:$INSTALL_DIR/logs/reporter.log
EOF

cat > /etc/systemd/system/pihole-analytics-daily.timer <<EOF
[Unit]
Description=Pi-hole Analytics - Daily report every day at 7 PM

[Timer]
OnCalendar=*-*-* 19:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

# -- Weekly Report (last 7 days — Saturday and Sunday at 7 PM) --
cat > /etc/systemd/system/pihole-analytics-weekly.service <<EOF
[Unit]
Description=Pi-hole Analytics - Weekly Email Report (last 7 days)
After=network.target

[Service]
Type=oneshot
User=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONPATH=$INSTALL_DIR
ExecStart=$PYTHON_BIN $INSTALL_DIR/scripts/core/reporter.py --period weekly
StandardOutput=append:$INSTALL_DIR/logs/reporter.log
StandardError=append:$INSTALL_DIR/logs/reporter.log
EOF

cat > /etc/systemd/system/pihole-analytics-weekly.timer <<EOF
[Unit]
Description=Pi-hole Analytics - Weekly report Saturday and Sunday at 7 PM

[Timer]
OnCalendar=Sat,Sun *-*-* 19:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

# -- Monthly Report (last 30 days — 30th of each month at 7 PM) --
cat > /etc/systemd/system/pihole-analytics-monthly.service <<EOF
[Unit]
Description=Pi-hole Analytics - Monthly Email Report (last 30 days)
After=network.target

[Service]
Type=oneshot
User=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONPATH=$INSTALL_DIR
ExecStart=$PYTHON_BIN $INSTALL_DIR/scripts/core/reporter.py --period monthly
StandardOutput=append:$INSTALL_DIR/logs/reporter.log
StandardError=append:$INSTALL_DIR/logs/reporter.log
EOF

cat > /etc/systemd/system/pihole-analytics-monthly.timer <<EOF
[Unit]
Description=Pi-hole Analytics - Monthly report on 30th of each month at 7 PM

[Timer]
OnCalendar=*-*-30 19:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

# -- Third-party category DB downloader (weekly, Sundays 3 AM) --
cat > /etc/systemd/system/pihole-analytics-download.service <<EOF
[Unit]
Description=Pi-hole Analytics - Download third-party category DB
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONPATH=$INSTALL_DIR
ExecStart=$PYTHON_BIN $INSTALL_DIR/scripts/data/downloader.py
StandardOutput=append:$INSTALL_DIR/logs/downloader.log
StandardError=append:$INSTALL_DIR/logs/downloader.log
EOF

cat > /etc/systemd/system/pihole-analytics-download.timer <<EOF
[Unit]
Description=Pi-hole Analytics - Refresh third-party category DB weekly

[Timer]
OnCalendar=Sun *-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

# -- Weekly system update (Sundays 4 AM) --
cat > /etc/systemd/system/pihole-analytics-sysupdate.service <<EOF
[Unit]
Description=Pi-hole Analytics - Weekly system package update
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=root
ExecStart=/usr/bin/apt-get update -qq
ExecStart=/usr/bin/apt-get upgrade -y -qq
ExecStart=/usr/bin/apt-get autoremove -y -qq
StandardOutput=append:$INSTALL_DIR/logs/sysupdate.log
StandardError=append:$INSTALL_DIR/logs/sysupdate.log
EOF

cat > /etc/systemd/system/pihole-analytics-sysupdate.timer <<EOF
[Unit]
Description=Pi-hole Analytics - Weekly system update Sunday 4 AM

[Timer]
OnCalendar=Sun *-*-* 04:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

# -- Dashboard web server --
cat > /etc/systemd/system/pihole-analytics-dashboard.service <<EOF
[Unit]
Description=Pi-hole Analytics Dashboard
After=network.target
Wants=network.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONPATH=$INSTALL_DIR
ExecStart=$PYTHON_BIN $INSTALL_DIR/scripts/web/app.py
Restart=always
RestartSec=5
StandardOutput=append:$INSTALL_DIR/logs/dashboard.log
StandardError=append:$INSTALL_DIR/logs/dashboard.log

[Install]
WantedBy=multi-user.target
EOF

# ── 5. Enable and start ────────────────────────────────────
info "Enabling and starting services..."
systemctl daemon-reload

systemctl enable  pihole-analytics-fetch.timer
systemctl enable  pihole-analytics-daily.timer
systemctl enable  pihole-analytics-weekly.timer
systemctl enable  pihole-analytics-monthly.timer
systemctl enable  pihole-analytics-download.timer
systemctl enable  pihole-analytics-sysupdate.timer
systemctl enable  pihole-analytics-dashboard.service

systemctl start   pihole-analytics-fetch.timer
systemctl start   pihole-analytics-daily.timer
systemctl start   pihole-analytics-weekly.timer
systemctl start   pihole-analytics-monthly.timer
systemctl start   pihole-analytics-download.timer
systemctl start   pihole-analytics-sysupdate.timer
systemctl start   pihole-analytics-dashboard.service

# ── 6. Adult content blocking ─────────────────────────────
info "Adding adult content blocklist to Pi-hole..."
sqlite3 /etc/pihole/gravity.db \
    "INSERT OR IGNORE INTO adlist (address, enabled, comment) \
     VALUES ('https://blocklistproject.github.io/Lists/porn.txt', 1, 'Adult content');" 2>/dev/null \
    && pihole -g 2>/dev/null \
    || warn "Could not add adult blocklist — add manually via Pi-hole admin → Settings → Adlists"

info "Blocking DNS-over-HTTPS providers to prevent browsers bypassing Pi-hole..."
for doh_domain in dns.google dns64.dns.google one.one.one.one \
    1dot1dot1dot1.cloudflare-dns.com mozilla.cloudflare-dns.com \
    dns.quad9.net dns10.quad9.net; do
    pihole denylist add "$doh_domain" 2>/dev/null || true
done
info "DoH provider blocking complete"

# ── 8. Download third-party category DB (initial) ─────────
info "Downloading third-party category DB (UT1 blacklist) — this may take a minute..."
sudo -u "$SERVICE_USER" "$PYTHON_BIN" "$INSTALL_DIR/scripts/data/downloader.py" || warn "Initial category DB download failed — will retry next Sunday at 3 AM."

# ── 9. Run first fetch ─────────────────────────────────────
info "Running initial data fetch..."
sudo -u "$SERVICE_USER" "$PYTHON_BIN" "$INSTALL_DIR/scripts/data/fetcher.py" || warn "First fetch failed — check config."

# ── 10. Fix ownership (initial fetch/download may create files as root) ────────
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

# ── 11. Done ───────────────────────────────────────────────
PI_IP=$(hostname -I | awk '{print $1}')
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     Pi-hole Analytics installed successfully!    ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo "  📊 Dashboard:   http://$PI_IP:8080"
echo "  📁 Install dir: $INSTALL_DIR"
echo "  ⚙️  Config:      $INSTALL_DIR/config/config.yaml"
echo "  📋 Logs:        $INSTALL_DIR/logs/"
echo ""
echo -e "${YELLOW}NEXT STEPS:${NC}"
echo "  1. Edit config:   nano $INSTALL_DIR/config/config.yaml"
echo "  2. Add Pi-hole API token (Admin > Settings > API)"
echo "  3. Add Gmail App Password for email reports"
echo "  4. Map your client IPs to names in the config"
echo "  5. Test email:  sudo -u $SERVICE_USER $PYTHON_BIN $INSTALL_DIR/scripts/core/reporter.py --period daily"
echo ""
echo "  Service status: systemctl status pihole-analytics-dashboard"
echo "  View timers:    systemctl list-timers pihole-analytics*"
