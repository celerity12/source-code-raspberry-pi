#!/bin/bash
# =============================================================================
# NAS Setup Script — Runs ON the Raspberry Pi (as root via SSH)
# Sets up Samba NAS on /mnt/nas with password-protected LAN access
# + Tailscale VPN for remote access from anywhere
# =============================================================================
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[OK]${NC}   $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# =============================================================================
# CONFIG — passed as env vars from deploy script, with defaults
# =============================================================================
DRIVE="${NAS_DRIVE:-/dev/sda1}"
MOUNT_POINT="${NAS_MOUNT:-/mnt/nas}"
NAS_USER="${NAS_USER:-nasuser}"
SMB_PASSWORD="${SMB_PASSWORD:-}"   # must be set by deploy script
SHARE_NAME="${SHARE_NAME:-NAS}"
LAN_SUBNET="${LAN_SUBNET:-192.168.1.0/24}"
FORMAT_DRIVE="${FORMAT_DRIVE:-no}"  # set to "yes" to format (DESTRUCTIVE)

# =============================================================================
# STEP 1: Validate
# =============================================================================
info "Checking for drive: $DRIVE"
if [ ! -b "$DRIVE" ]; then
    warn "Drive $DRIVE not found. Listing available block devices:"
    lsblk
    error "Set NAS_DRIVE env var to the correct device (e.g. /dev/sda1) and re-run."
fi

[ -z "$SMB_PASSWORD" ] && error "SMB_PASSWORD must be set. Export it before running."

# =============================================================================
# STEP 2: Format (optional, only if FORMAT_DRIVE=yes)
# =============================================================================
if [ "$FORMAT_DRIVE" = "yes" ]; then
    warn "Formatting $DRIVE as ext4 — ALL DATA WILL BE LOST"
    read -p "Type 'CONFIRM' to proceed: " confirm
    [ "$confirm" = "CONFIRM" ] || error "Aborted."
    mkfs.ext4 -F "$DRIVE"
    success "Drive formatted."
fi

# =============================================================================
# STEP 3: Mount drive
# =============================================================================
info "Mounting $DRIVE at $MOUNT_POINT"
mkdir -p "$MOUNT_POINT"

# Unmount first if already mounted elsewhere
if mountpoint -q "$MOUNT_POINT"; then
    warn "$MOUNT_POINT already mounted, skipping mount."
else
    mount "$DRIVE" "$MOUNT_POINT" || error "Failed to mount $DRIVE. Is it formatted? Run with FORMAT_DRIVE=yes to format."
fi

# Auto-mount on boot via fstab (idempotent)
FSTAB_ENTRY="$DRIVE  $MOUNT_POINT  ext4  defaults,nofail  0  2"
if grep -qF "$DRIVE" /etc/fstab; then
    warn "fstab entry for $DRIVE already exists, skipping."
else
    echo "$FSTAB_ENTRY" >> /etc/fstab
    success "Added fstab entry for auto-mount on boot."
fi

# =============================================================================
# STEP 4: Install Samba
# =============================================================================
info "Installing Samba..."
apt-get update -qq
apt-get install -y samba samba-common-bin >/dev/null
success "Samba installed."

# =============================================================================
# STEP 5: Create NAS user
# =============================================================================
info "Setting up NAS user: $NAS_USER"
if id "$NAS_USER" &>/dev/null; then
    warn "User $NAS_USER already exists, skipping creation."
else
    useradd -M -s /usr/sbin/nologin "$NAS_USER"
    success "Linux user $NAS_USER created."
fi

# Set Samba password non-interactively
echo -e "$SMB_PASSWORD\n$SMB_PASSWORD" | smbpasswd -a -s "$NAS_USER"
smbpasswd -e "$NAS_USER"
success "Samba password set for $NAS_USER."

# Set permissions on mount point
chown -R "${NAS_USER}:${NAS_USER}" "$MOUNT_POINT"
chmod 770 "$MOUNT_POINT"
success "Permissions set on $MOUNT_POINT."

# =============================================================================
# STEP 6: Configure Samba share
# =============================================================================
info "Configuring Samba share [$SHARE_NAME]..."
SMB_CONF="/etc/samba/smb.conf"
SHARE_MARKER="# NAS-SETUP-SHARE-BEGIN"

if grep -qF "$SHARE_MARKER" "$SMB_CONF"; then
    warn "Samba share [$SHARE_NAME] already configured, skipping."
else
    cat >> "$SMB_CONF" <<EOF

$SHARE_MARKER
[$SHARE_NAME]
   path = $MOUNT_POINT
   browseable = yes
   read only = no
   valid users = $NAS_USER
   create mask = 0660
   directory mask = 0770
   force user = $NAS_USER
   comment = Raspberry Pi NAS
EOF
    success "Samba share [$SHARE_NAME] added to $SMB_CONF."
fi

# Validate config
testparm -s "$SMB_CONF" &>/dev/null && success "Samba config valid." || error "Samba config invalid — check $SMB_CONF."

# =============================================================================
# STEP 7: Open firewall for LAN + Tailscale (if ufw is active)
# =============================================================================
if command -v ufw &>/dev/null && ufw status | grep -q "Status: active"; then
    info "Configuring ufw to allow Samba from LAN ($LAN_SUBNET)..."
    ufw allow from "$LAN_SUBNET" to any port 139 proto tcp comment "Samba NetBIOS"
    ufw allow from "$LAN_SUBNET" to any port 445 proto tcp comment "Samba SMB"
    success "Firewall rules added for Samba (LAN)."

    info "Configuring ufw to allow Samba from Tailscale (100.64.0.0/10)..."
    ufw allow from 100.64.0.0/10 to any port 139 proto tcp comment "Samba NetBIOS (Tailscale)"
    ufw allow from 100.64.0.0/10 to any port 445 proto tcp comment "Samba SMB (Tailscale)"
    success "Firewall rules added for Samba (Tailscale)."
else
    warn "ufw not active — skipping firewall config. Samba is accessible on all interfaces."
fi

# =============================================================================
# STEP 8: Enable and start Samba
# =============================================================================
info "Enabling and starting Samba services..."
systemctl enable smbd nmbd
systemctl restart smbd nmbd
success "Samba running."

# =============================================================================
# STEP 9: Install Tailscale (for remote access from anywhere)
# =============================================================================
info "Installing Tailscale VPN for remote access..."
if command -v tailscale &>/dev/null; then
    warn "Tailscale already installed."
else
    curl -fsSL https://tailscale.com/install.sh | sh
    success "Tailscale installed."
fi

# Enable Tailscale to start on boot
systemctl enable tailscaled
systemctl start tailscaled

echo ""
echo -e "${YELLOW}============================================================${NC}"
echo -e "${YELLOW}  TAILSCALE SETUP REQUIRED — run this manually on the Pi:  ${NC}"
echo -e "${YELLOW}  sudo tailscale up                                         ${NC}"
echo -e "${YELLOW}  Then open the URL shown and sign in at tailscale.com      ${NC}"
echo -e "${YELLOW}============================================================${NC}"
echo ""

# =============================================================================
# STEP 10: Verify everything is up
# =============================================================================
info "Verifying services..."
systemctl is-active --quiet smbd && success "smbd is running." || warn "smbd is NOT running."
systemctl is-active --quiet nmbd && success "nmbd is running." || warn "nmbd is NOT running."
mountpoint -q "$MOUNT_POINT"    && success "$MOUNT_POINT is mounted." || warn "$MOUNT_POINT is NOT mounted."

PI_IP=$(hostname -I | awk '{print $1}')
TAILSCALE_IP=$(tailscale ip -4 2>/dev/null || echo "not connected yet")

echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}  NAS Setup Complete!                                       ${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
echo "  Share name : $SHARE_NAME"
echo "  Username   : $NAS_USER"
echo "  Drive      : $DRIVE -> $MOUNT_POINT"
echo ""
echo "  LAN access:"
echo "    Windows  : \\\\${PI_IP}\\${SHARE_NAME}"
echo "    macOS    : smb://${PI_IP}/${SHARE_NAME}"
echo ""
echo "  Remote access (after tailscale up):"
echo "    Tailscale IP : $TAILSCALE_IP"
echo "    Windows  : \\\\${TAILSCALE_IP}\\${SHARE_NAME}"
echo "    macOS    : smb://${TAILSCALE_IP}/${SHARE_NAME}"
echo ""
echo "  Existing services are NOT affected."
echo ""
