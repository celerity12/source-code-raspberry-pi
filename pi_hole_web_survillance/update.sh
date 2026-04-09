#!/usr/bin/env bash
# =============================================================================
# Pi-hole Analytics — Update Script (existing deployment)
# Syncs scripts to the Pi, reloads systemd units, restarts the dashboard.
# Run from your Linux box:  bash update.sh
# =============================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'

info()  { echo -e "${GREEN}[✓]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[!]${NC}  $*"; }
error() { echo -e "${RED}[✗]${NC}  $*"; exit 1; }
step()  { echo -e "\n${BOLD}${CYAN}━━━  $*  ━━━${NC}"; }

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Defaults (edit if your Pi differs) ────────────────────────────────────────
PI_IP="${PI_IP:-192.168.68.102}"
PI_USER="${PI_USER:-pi}"
PI_PORT="${PI_PORT:-22}"
INSTALL_DIR="/home/${PI_USER}/pihole-analytics"

echo -e "${BOLD}"
echo "  ╔══════════════════════════════════════════════════════╗"
echo "  ║       Pi-hole Analytics — Update Deployment          ║"
echo "  ╚══════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo "  Target : ${BOLD}${PI_USER}@${PI_IP}:${PI_PORT}${NC}"
echo "  Remote : ${BOLD}${INSTALL_DIR}${NC}"
echo "  Source : ${BOLD}${PROJECT_DIR}${NC}"
echo ""

read -rp "$(echo -e "${YELLOW}[?]${NC} Pi IP address [${PI_IP}]: ")" _ip
PI_IP="${_ip:-$PI_IP}"
read -rp "$(echo -e "${YELLOW}[?]${NC} SSH username  [${PI_USER}]: ")" _user
PI_USER="${_user:-$PI_USER}"
read -rp "$(echo -e "${YELLOW}[?]${NC} SSH port      [${PI_PORT}]: ")" _port
PI_PORT="${_port:-$PI_PORT}"
INSTALL_DIR="/home/${PI_USER}/pihole-analytics"

# ── SSH ControlMaster — authenticate once, reuse for all connections ──────────
SSH_CTRL="/tmp/pihole-update-$$.sock"
SSH_BASE="ssh -p ${PI_PORT} -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new \
    -o ControlMaster=auto -o ControlPath=${SSH_CTRL} -o ControlPersist=120"
SCP_BASE="scp -P ${PI_PORT} -o ControlPath=${SSH_CTRL}"

cleanup() { ssh -O exit -o ControlPath="${SSH_CTRL}" "${PI_USER}@${PI_IP}" 2>/dev/null || true; }
trap cleanup EXIT

# Open the master connection (prompts for password once)
echo ""
echo -e "  ${DIM}Opening SSH connection (you will be asked for the password once)...${NC}"
if ! $SSH_BASE "${PI_USER}@${PI_IP}" "echo '__OK__'" 2>/dev/null | grep -q "__OK__"; then
    error "Cannot reach ${PI_USER}@${PI_IP}:${PI_PORT} — check IP/user/port and retry"
fi
info "SSH connection established (password cached for this session)"

# =============================================================================
# STEP 1 — SSH CHECK (already done above)
# =============================================================================
step "1 — SSH verified"
info "Connected to ${PI_USER}@${PI_IP}:${PI_PORT}"

# =============================================================================
# STEP 2 — SYNC FILES
# =============================================================================
step "2 — Syncing scripts"

echo ""
echo "  Syncing scripts/ → ${INSTALL_DIR}/scripts/"
echo "  (config/, data/, logs/ are untouched)"
echo ""

if command -v rsync &>/dev/null; then
    rsync -az --delete \
        --exclude='__pycache__/' \
        --exclude='*.pyc' \
        -e "ssh -p ${PI_PORT} -o ControlPath=${SSH_CTRL}" \
        "${PROJECT_DIR}/scripts/" \
        "${PI_USER}@${PI_IP}:${INSTALL_DIR}/scripts/"
    info "scripts/ synced via rsync"
else
    warn "rsync not found — using scp"
    $SCP_BASE -r "${PROJECT_DIR}/scripts/." \
        "${PI_USER}@${PI_IP}:${INSTALL_DIR}/scripts/"
    info "scripts/ synced via scp"
fi

$SCP_BASE \
    "${PROJECT_DIR}/install.sh" \
    "${PI_USER}@${PI_IP}:${INSTALL_DIR}/install.sh"
info "install.sh synced"

# Sync config (preserves passwords already set, but updates categories/schedules)
$SCP_BASE \
    "${PROJECT_DIR}/config/config.yaml" \
    "${PI_USER}@${PI_IP}:${INSTALL_DIR}/config/config.yaml"
info "config/config.yaml synced"

# =============================================================================
# STEP 3 — RELOAD SYSTEMD TIMER UNITS
# =============================================================================
step "3 — Reloading systemd timer units"

# Read gemini.scheduled from local config (grep-based — no yaml dependency)
if grep -qE "^\s+scheduled:\s*false" "${PROJECT_DIR}/config/config.yaml" 2>/dev/null; then
  AI_SCHEDULED="false"
else
  AI_SCHEDULED="true"
fi

echo ""
echo "  Writing updated timer/service unit files and reloading..."
echo "  AI scheduled run: ${AI_SCHEDULED}"
echo ""

$SSH_BASE "${PI_USER}@${PI_IP}" bash <<REMOTE
set -e
INSTALL_DIR="${INSTALL_DIR}"
PI_USER="${PI_USER}"

sudo bash <<SUDO
# Daily — last 24 hours, every day at 7 AM
cat > /etc/systemd/system/pihole-analytics-daily.service <<EOF
[Unit]
Description=Pi-hole Analytics - Daily Email Report (last 24 hours)
After=network.target pihole-analytics-fetch.service
[Service]
Type=oneshot
User=${PI_USER}
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/venv/bin/python3 ${INSTALL_DIR}/scripts/core/reporter.py --period daily
StandardOutput=append:${INSTALL_DIR}/logs/reporter.log
StandardError=append:${INSTALL_DIR}/logs/reporter.log
EOF

cat > /etc/systemd/system/pihole-analytics-daily.timer <<EOF
[Unit]
Description=Pi-hole Analytics - Daily report every day at 7 AM
[Timer]
OnCalendar=*-*-* 07:00:00
Persistent=true
[Install]
WantedBy=timers.target
EOF

# Weekly — last 7 days, Saturday and Sunday at 7 AM (after daily report)
cat > /etc/systemd/system/pihole-analytics-weekly.service <<EOF
[Unit]
Description=Pi-hole Analytics - Weekly Email Report (last 7 days)
After=network.target
[Service]
Type=oneshot
User=${PI_USER}
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/venv/bin/python3 ${INSTALL_DIR}/scripts/core/reporter.py --period weekly
StandardOutput=append:${INSTALL_DIR}/logs/reporter.log
StandardError=append:${INSTALL_DIR}/logs/reporter.log
EOF

cat > /etc/systemd/system/pihole-analytics-weekly.timer <<EOF
[Unit]
Description=Pi-hole Analytics - Weekly report Saturday and Sunday at 7 AM
[Timer]
OnCalendar=Sat,Sun *-*-* 07:00:00
Persistent=true
[Install]
WantedBy=timers.target
EOF

# Monthly — last 30 days, 30th of each month at 7 AM
cat > /etc/systemd/system/pihole-analytics-monthly.service <<EOF
[Unit]
Description=Pi-hole Analytics - Monthly Email Report (last 30 days)
After=network.target
[Service]
Type=oneshot
User=${PI_USER}
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/venv/bin/python3 ${INSTALL_DIR}/scripts/core/reporter.py --period monthly
StandardOutput=append:${INSTALL_DIR}/logs/reporter.log
StandardError=append:${INSTALL_DIR}/logs/reporter.log
EOF

cat > /etc/systemd/system/pihole-analytics-monthly.timer <<EOF
[Unit]
Description=Pi-hole Analytics - Monthly report on 30th of each month at 7 AM
[Timer]
OnCalendar=*-*-30 07:00:00
Persistent=true
[Install]
WantedBy=timers.target
EOF

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
StandardOutput=append:${INSTALL_DIR}/logs/sysupdate.log
StandardError=append:${INSTALL_DIR}/logs/sysupdate.log
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

# AI summary — daily at 5 AM (2 hours before the 7 AM report)
cat > /etc/systemd/system/pihole-analytics-aisummary.service <<EOF
[Unit]
Description=Pi-hole Analytics - Daily AI Summary (Gemini)
After=network-online.target
[Service]
Type=oneshot
User=${PI_USER}
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/venv/bin/python3 ${INSTALL_DIR}/scripts/core/summarizer.py --period daily
StandardOutput=append:${INSTALL_DIR}/logs/summarizer.log
StandardError=append:${INSTALL_DIR}/logs/summarizer.log
EOF

cat > /etc/systemd/system/pihole-analytics-aisummary.timer <<EOF
[Unit]
Description=Pi-hole Analytics - Daily AI summary at 5 AM
[Timer]
OnCalendar=*-*-* 05:00:00
Persistent=true
[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now pihole-analytics-daily.timer      2>/dev/null || true
systemctl enable --now pihole-analytics-weekly.timer     2>/dev/null || true
systemctl enable --now pihole-analytics-monthly.timer    2>/dev/null || true
systemctl enable --now pihole-analytics-sysupdate.timer  2>/dev/null || true
if [ "${AI_SCHEDULED}" = "true" ]; then
  systemctl enable --now pihole-analytics-aisummary.timer 2>/dev/null || true
else
  systemctl disable --now pihole-analytics-aisummary.timer 2>/dev/null || true
fi
echo "Timers reloaded OK"
SUDO
REMOTE

info "Systemd timer units reloaded"

# =============================================================================
# STEP 4 — FIX + RESTART DASHBOARD
# =============================================================================
step "4 — Restarting dashboard"

echo ""
echo "  Rewriting dashboard service file with correct paths..."
echo ""

$SSH_BASE "${PI_USER}@${PI_IP}" bash <<REMOTE
set -e
INSTALL_DIR="${INSTALL_DIR}"
PI_USER="${PI_USER}"

mkdir -p "\${INSTALL_DIR}/logs"

sudo bash <<SUDO
cat > /etc/systemd/system/pihole-analytics-dashboard.service <<EOF
[Unit]
Description=Pi-hole Analytics Dashboard
After=network.target
[Service]
Type=simple
User=${PI_USER}
WorkingDirectory=${INSTALL_DIR}
Environment=PYTHONPATH=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/venv/bin/python3 ${INSTALL_DIR}/scripts/web/app.py
Restart=always
RestartSec=5
StandardOutput=append:${INSTALL_DIR}/logs/dashboard.log
StandardError=append:${INSTALL_DIR}/logs/dashboard.log
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable pihole-analytics-dashboard
systemctl restart pihole-analytics-dashboard
SUDO
REMOTE

sleep 3
STATUS=$($SSH_BASE "${PI_USER}@${PI_IP}" "systemctl is-active pihole-analytics-dashboard 2>/dev/null || echo 'inactive'")
if [ "$STATUS" = "active" ]; then
    info "Dashboard is running"
else
    warn "Dashboard status: ${STATUS}"
    echo ""
    echo "  Last 10 log lines:"
    $SSH_BASE "${PI_USER}@${PI_IP}" "tail -10 ${INSTALL_DIR}/logs/dashboard.log 2>/dev/null || journalctl -u pihole-analytics-dashboard -n 10 --no-pager" || true
fi

# =============================================================================
# STEP 5 — VERIFY
# =============================================================================
step "5 — Verification"

echo ""
echo "  Service status:"
$SSH_BASE "${PI_USER}@${PI_IP}" "
    for svc in pihole-analytics-dashboard pihole-analytics-fetch.timer pihole-analytics-daily.timer pihole-analytics-weekly.timer pihole-analytics-monthly.timer pihole-analytics-sysupdate.timer; do
        state=\$(systemctl is-active \$svc 2>/dev/null || echo 'not-found')
        printf '    %-45s %s\n' \"\$svc\" \"\$state\"
    done
" || true

echo ""
echo "  Timer schedule:"
$SSH_BASE "${PI_USER}@${PI_IP}" "systemctl list-timers pihole-analytics* --no-pager 2>/dev/null | head -10" || true

echo ""
echo "  Scripts on Pi:"
$SSH_BASE "${PI_USER}@${PI_IP}" "ls -lh ${INSTALL_DIR}/scripts/core/*.py ${INSTALL_DIR}/scripts/web/app.py 2>/dev/null | awk '{print \"    \"\$NF\" (\"\$5\")\"}" || true

echo ""
echo "  Quick smoke test (import check):"
$SSH_BASE "${PI_USER}@${PI_IP}" "
    cd ${INSTALL_DIR}
    venv/bin/python3 -c '
import sys; sys.path.insert(0, \".\")
from scripts.core import reporter, health
from scripts.web import app
print(\"    All modules import OK\")
' 2>&1 | head -5
" || warn "Import check failed — review logs on the Pi"

# =============================================================================
# DONE
# =============================================================================
echo ""
echo -e "${GREEN}${BOLD}━━━  Update complete  ━━━${NC}"
echo ""
echo "  Dashboard : http://${PI_IP}:8080"
echo ""
echo "  To send a test report now:"
echo -e "  ${DIM}ssh ${PI_USER}@${PI_IP} '${INSTALL_DIR}/venv/bin/python3 ${INSTALL_DIR}/scripts/core/reporter.py --period daily'${NC}"
echo ""
echo "  To watch the dashboard logs:"
echo -e "  ${DIM}ssh ${PI_USER}@${PI_IP} 'journalctl -u pihole-analytics-dashboard -f'${NC}"
echo ""
