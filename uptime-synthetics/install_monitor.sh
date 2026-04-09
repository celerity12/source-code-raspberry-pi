#!/usr/bin/env bash
# =============================================================================
# up_synthetics Installer — Runs ON the Raspberry Pi (as root via SSH)
# Installs the health monitor and sets up a daily systemd timer
# =============================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

[[ $EUID -ne 0 ]] && error "Run as root: sudo bash install_monitor.sh"

SERVICE_USER="${SUDO_USER:-$(logname 2>/dev/null || echo pi)}"
INSTALL_DIR="/home/${SERVICE_USER}/uptime-synthetics"
PYTHON_BIN="$INSTALL_DIR/venv/bin/python3"
REPORT_TIME="${REPORT_TIME:-08:00}"   # Daily report time (24h). Override via env var.
ENABLE_ALERTS="${ENABLE_ALERTS:-no}"  # Set to "yes" to enable 30-min failure alerts.

info "=== up_synthetics Installer ==="
info "Installing to: $INSTALL_DIR"
info "Daily report time: $REPORT_TIME"

# ── 1. Copy files ─────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$INSTALL_DIR/logs"

cp "$SCRIPT_DIR/monitor.py"           "$INSTALL_DIR/monitor.py"
cp "$SCRIPT_DIR/requirements.txt"     "$INSTALL_DIR/requirements.txt"

# Copy config.yaml only if not already present (preserve existing config)
if [[ ! -f "$INSTALL_DIR/config.yaml" ]]; then
    if [[ -f "$SCRIPT_DIR/config.yaml" ]]; then
        cp "$SCRIPT_DIR/config.yaml" "$INSTALL_DIR/config.yaml"
        info "Config copied."
    else
        cp "$SCRIPT_DIR/config.example.yaml" "$INSTALL_DIR/config.yaml"
        warn "Copied config.example.yaml → config.yaml. Fill in your credentials!"
    fi
else
    info "Existing config.yaml preserved."
fi

# ── 2. Python venv + deps ─────────────────────────────────────────────────────
info "Setting up Python virtual environment..."
sudo -u "$SERVICE_USER" python3 -m venv "$INSTALL_DIR/venv"
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install -q --upgrade pip
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install -q \
    -r "$INSTALL_DIR/requirements.txt"
info "Python dependencies installed."

chown -R "${SERVICE_USER}:${SERVICE_USER}" "$INSTALL_DIR"

# ── 3. Systemd service — daily report ─────────────────────────────────────────
info "Installing systemd daily report timer..."

cat > /etc/systemd/system/pihole-uptime-monitor.service <<EOF
[Unit]
Description=Pi-hole Stack — Daily Health Report (up_synthetics)
After=network.target

[Service]
Type=oneshot
User=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$PYTHON_BIN $INSTALL_DIR/monitor.py --mode daily
StandardOutput=append:$INSTALL_DIR/logs/monitor.log
StandardError=append:$INSTALL_DIR/logs/monitor.log
EOF

cat > /etc/systemd/system/pihole-uptime-monitor.timer <<EOF
[Unit]
Description=Pi-hole Stack — Daily Health Report at $REPORT_TIME

[Timer]
OnCalendar=*-*-* ${REPORT_TIME}:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

# ── 4. Systemd service — immediate alert on failure (optional) ────────────────
if [[ "$ENABLE_ALERTS" == "yes" ]]; then
    info "Installing systemd alert-on-failure timer (every 30 min)..."

    cat > /etc/systemd/system/pihole-uptime-alert.service <<EOF
[Unit]
Description=Pi-hole Stack — Failure Alert (up_synthetics alert-only)
After=network.target

[Service]
Type=oneshot
User=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$PYTHON_BIN $INSTALL_DIR/monitor.py --mode alert-only
StandardOutput=append:$INSTALL_DIR/logs/monitor.log
StandardError=append:$INSTALL_DIR/logs/monitor.log
EOF

    cat > /etc/systemd/system/pihole-uptime-alert.timer <<EOF
[Unit]
Description=Pi-hole Stack — Check for failures every 30 minutes

[Timer]
OnCalendar=*:0/30
Persistent=true

[Install]
WantedBy=timers.target
EOF

else
    warn "30-min failure alerts are DISABLED (default). To enable:"
    warn "  ENABLE_ALERTS=yes bash deploy_monitor.sh"
    warn "  Or manually: systemctl enable --now pihole-uptime-alert.timer"
fi

# ── 5. Enable and start ───────────────────────────────────────────────────────
systemctl daemon-reload
systemctl enable pihole-uptime-monitor.timer
systemctl start  pihole-uptime-monitor.timer

if [[ "$ENABLE_ALERTS" == "yes" ]]; then
    systemctl enable pihole-uptime-alert.timer
    systemctl start  pihole-uptime-alert.timer
    info "30-min alert timer enabled and started."
fi

info "Services enabled and started."

# ── 6. Run once now to verify ─────────────────────────────────────────────────
info "Running a test check now..."
sudo -u "$SERVICE_USER" "$PYTHON_BIN" "$INSTALL_DIR/monitor.py" --mode daily || \
    warn "Test run failed — check $INSTALL_DIR/config.yaml credentials."

echo ""
echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  up_synthetics installed successfully!           ${NC}"
echo -e "${GREEN}══════════════════════════════════════════════════${NC}"
echo ""
echo "  Daily report:   every day at $REPORT_TIME"
if [[ "$ENABLE_ALERTS" == "yes" ]]; then
    echo "  Failure alerts: every 30 min (alert-only mode — enabled)"
else
    echo "  Failure alerts: DISABLED  ← to enable: ENABLE_ALERTS=yes bash deploy_monitor.sh"
fi
echo "  Log:            $INSTALL_DIR/logs/monitor.log"
echo "  Config:         $INSTALL_DIR/config.yaml"
echo ""
echo "  Manual run:  sudo -u $SERVICE_USER $PYTHON_BIN $INSTALL_DIR/monitor.py --mode daily"
echo "  View timers: systemctl list-timers pihole-uptime*"
echo ""
