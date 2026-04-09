#!/usr/bin/env bash
# =============================================================================
# up_synthetics Deploy Script — Run on YOUR LAPTOP
# Copies files to the Pi and runs the installer remotely via SSH
#
# Usage:
#   bash deploy_monitor.sh
#   REPORT_TIME=09:00 bash deploy_monitor.sh   # change daily report time
# =============================================================================
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()  { echo -e "${BLUE}[INFO]${NC}  $1"; }
success(){ echo -e "${GREEN}[OK]${NC}   $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Config — edit or set via env vars ────────────────────────────────────────
PI_HOST="${PI_HOST:-192.168.68.102}"
PI_USER="${PI_USER:-pi}"
PI_SSH_KEY="${PI_SSH_KEY:-$HOME/.ssh/id_rsa}"
REPORT_TIME="${REPORT_TIME:-08:00}"
ENABLE_ALERTS="${ENABLE_ALERTS:-no}"   # Set to "yes" to enable 30-min failure alerts

SSH="ssh -i $PI_SSH_KEY -o StrictHostKeyChecking=no ${PI_USER}@${PI_HOST}"
SCP="scp -i $PI_SSH_KEY -o StrictHostKeyChecking=no"

# ── Pre-flight ────────────────────────────────────────────────────────────────
info "Checking SSH connection to $PI_HOST..."
$SSH "echo connected" &>/dev/null || error "Cannot SSH into ${PI_USER}@${PI_HOST}"
success "SSH OK."

# ── Copy files to Pi ──────────────────────────────────────────────────────────
info "Copying uptime-synthetics files to Pi..."
$SSH "mkdir -p /tmp/uptime-synthetics"

$SCP "$SCRIPT_DIR/monitor.py"           "${PI_USER}@${PI_HOST}:/tmp/uptime-synthetics/"
$SCP "$SCRIPT_DIR/install_monitor.sh"   "${PI_USER}@${PI_HOST}:/tmp/uptime-synthetics/"
$SCP "$SCRIPT_DIR/requirements.txt"     "${PI_USER}@${PI_HOST}:/tmp/uptime-synthetics/"
$SCP "$SCRIPT_DIR/config.example.yaml"  "${PI_USER}@${PI_HOST}:/tmp/uptime-synthetics/"

# Copy config.yaml if it exists locally (filled in by user)
if [[ -f "$SCRIPT_DIR/config.yaml" ]]; then
    $SCP "$SCRIPT_DIR/config.yaml" "${PI_USER}@${PI_HOST}:/tmp/uptime-synthetics/"
    success "config.yaml copied."
else
    echo -e "${YELLOW}[WARN]${NC}  No config.yaml found — you must edit config.yaml on the Pi after deploy."
fi

success "Files copied."

# ── Run installer on Pi ───────────────────────────────────────────────────────
info "Running installer on Pi..."
$SSH "export REPORT_TIME='$REPORT_TIME' ENABLE_ALERTS='$ENABLE_ALERTS' && sudo -E bash /tmp/uptime-synthetics/install_monitor.sh"

# ── Cleanup ───────────────────────────────────────────────────────────────────
$SSH "rm -rf /tmp/uptime-synthetics"

echo ""
success "Deployment complete!"
echo ""
echo "  To edit config on the Pi:"
echo "    ssh ${PI_USER}@${PI_HOST}"
echo "    nano ~/uptime-synthetics/config.yaml"
echo ""
echo "  To run a manual check:"
echo "    ssh ${PI_USER}@${PI_HOST} 'sudo -u ${PI_USER} ~/uptime-synthetics/venv/bin/python3 ~/uptime-synthetics/monitor.py --mode daily'"
echo ""
