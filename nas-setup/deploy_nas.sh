#!/bin/bash
# =============================================================================
# NAS Deploy Script — Runs on YOUR LAPTOP
# SSHs into the Pi and runs install_nas.sh remotely
#
# Usage:
#   bash deploy_nas.sh
#   bash deploy_nas.sh --drive /dev/sdb1      # specify drive
#   bash deploy_nas.sh --format               # format drive first (DESTRUCTIVE)
# =============================================================================
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC}   $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# =============================================================================
# CONFIG — edit these to match your Pi
# =============================================================================
PI_HOST="${PI_HOST:-raspberrypi.local}"
PI_USER="${PI_USER:-pi}"
PI_SSH_KEY="${PI_SSH_KEY:-$HOME/.ssh/id_rsa}"

NAS_DRIVE="${NAS_DRIVE:-/dev/sda1}"
NAS_MOUNT="${NAS_MOUNT:-/mnt/nas}"
NAS_USER="${NAS_USER:-nasuser}"
SHARE_NAME="${SHARE_NAME:-NAS}"
LAN_SUBNET="${LAN_SUBNET:-192.168.1.0/24}"
FORMAT_DRIVE="no"

# =============================================================================
# Parse args
# =============================================================================
while [[ $# -gt 0 ]]; do
    case $1 in
        --drive)   NAS_DRIVE="$2"; shift 2 ;;
        --mount)   NAS_MOUNT="$2"; shift 2 ;;
        --host)    PI_HOST="$2";   shift 2 ;;
        --user)    PI_USER="$2";   shift 2 ;;
        --key)     PI_SSH_KEY="$2"; shift 2 ;;
        --subnet)  LAN_SUBNET="$2"; shift 2 ;;
        --format)  FORMAT_DRIVE="yes"; shift ;;
        *) error "Unknown option: $1" ;;
    esac
done

SSH_CMD="ssh -i $PI_SSH_KEY -o StrictHostKeyChecking=no ${PI_USER}@${PI_HOST}"

# =============================================================================
# Pre-flight checks
# =============================================================================
info "Checking SSH connection to $PI_HOST..."
$SSH_CMD "echo connected" &>/dev/null || error "Cannot SSH into ${PI_USER}@${PI_HOST}. Check PI_HOST, PI_USER, PI_SSH_KEY."
success "SSH connection OK."

# =============================================================================
# Prompt for Samba password
# =============================================================================
echo ""
echo "  Set a password for the NAS share."
echo "  All LAN users will use: username=$NAS_USER and this password."
echo ""
while true; do
    read -s -p "  Enter Samba password: " SMB_PASSWORD; echo
    read -s -p "  Confirm password:     " SMB_CONFIRM;  echo
    [ "$SMB_PASSWORD" = "$SMB_CONFIRM" ] && break
    warn "Passwords do not match. Try again."
done
echo ""

# =============================================================================
# Copy install script to Pi
# =============================================================================
info "Copying install_nas.sh to Pi..."
scp -i "$PI_SSH_KEY" -o StrictHostKeyChecking=no \
    "$SCRIPT_DIR/install_nas.sh" \
    "${PI_USER}@${PI_HOST}:/tmp/install_nas.sh"
success "Script copied."

# =============================================================================
# Run install script on Pi as root
# =============================================================================
info "Running install_nas.sh on Pi (as sudo)..."
echo ""

$SSH_CMD "
    export NAS_DRIVE='$NAS_DRIVE'
    export NAS_MOUNT='$NAS_MOUNT'
    export NAS_USER='$NAS_USER'
    export SMB_PASSWORD='$SMB_PASSWORD'
    export SHARE_NAME='$SHARE_NAME'
    export LAN_SUBNET='$LAN_SUBNET'
    export FORMAT_DRIVE='$FORMAT_DRIVE'
    sudo -E bash /tmp/install_nas.sh
    rm -f /tmp/install_nas.sh
"

echo ""
success "NAS deployment complete."
echo ""
echo -e "${YELLOW}Next step — complete Tailscale setup on the Pi:${NC}"
echo "  ssh ${PI_USER}@${PI_HOST}"
echo "  sudo tailscale up"
echo "  (open the URL shown, sign in at tailscale.com)"
echo ""
