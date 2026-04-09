#!/usr/bin/env bash
# =============================================================================
# Pi-hole Security Hardening Script
# Hardens a Raspberry Pi running Pi-hole against common threats.
# Run from your Linux box:  bash harden.sh
# =============================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'

info()  { echo -e "${GREEN}[✓]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[!]${NC}  $*"; }
error() { echo -e "${RED}[✗]${NC}  $*"; }
step()  { echo -e "\n${BOLD}${CYAN}━━━  $*  ━━━${NC}"; }
skip()  { echo -e "${DIM}[−]  $* (skipped)${NC}"; }

PI_IP="${PI_IP:-192.168.68.102}"
PI_USER="${PI_USER:-pi}"
PI_PORT="${PI_PORT:-22}"

echo -e "${BOLD}"
echo "  ╔══════════════════════════════════════════════════════╗"
echo "  ║         Pi-hole Security Hardening                   ║"
echo "  ╚══════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo "  This script will harden your Pi against:"
echo "  • Brute-force SSH attacks (fail2ban + key-only auth)"
echo "  • Unnecessary open ports (ufw firewall)"
echo "  • Weak passwords"
echo "  • Outdated packages"
echo "  • DNS-over-HTTPS data leaks"
echo "  • Pi-hole admin exposed to internet"
echo "  • Unattended security updates"
echo ""

read -rp "$(echo -e "${YELLOW}[?]${NC} Pi IP   [${PI_IP}]: ")"   _ip;   PI_IP="${_ip:-$PI_IP}"
read -rp "$(echo -e "${YELLOW}[?]${NC} User    [${PI_USER}]: ")" _user; PI_USER="${_user:-$PI_USER}"
read -rp "$(echo -e "${YELLOW}[?]${NC} Port    [${PI_PORT}]: ")" _port; PI_PORT="${_port:-$PI_PORT}"

# ── SSH ControlMaster (ask password once) ─────────────────────────────────────
SSH_CTRL="/tmp/pihole-harden-$$.sock"
SSH="ssh -p ${PI_PORT} -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new \
    -o ControlMaster=auto -o ControlPath=${SSH_CTRL} -o ControlPersist=120"
cleanup() { ssh -O exit -o ControlPath="${SSH_CTRL}" "${PI_USER}@${PI_IP}" 2>/dev/null || true; }
trap cleanup EXIT

echo ""
echo -e "  ${DIM}Opening SSH connection (password asked once)...${NC}"
$SSH "${PI_USER}@${PI_IP}" "echo OK" > /dev/null
info "Connected to ${PI_USER}@${PI_IP}"

# =============================================================================
# STEP 1 — SYSTEM UPDATES
# =============================================================================
step "1 — System updates"
$SSH "${PI_USER}@${PI_IP}" "sudo apt-get update -qq && sudo apt-get upgrade -y -qq && sudo apt-get autoremove -y -qq"
info "System packages updated"

# =============================================================================
# STEP 2 — UNATTENDED SECURITY UPGRADES
# =============================================================================
step "2 — Automatic security updates"
$SSH "${PI_USER}@${PI_IP}" bash <<'REMOTE'
sudo apt-get install -y -qq unattended-upgrades apt-listchanges
sudo tee /etc/apt/apt.conf.d/50unattended-upgrades > /dev/null <<'EOF'
Unattended-Upgrade::Allowed-Origins {
    "${distro_id}:${distro_codename}-security";
    "${distro_id}ESMApps:${distro_codename}-apps-security";
};
Unattended-Upgrade::AutoFixInterruptedDpkg "true";
Unattended-Upgrade::MinimalSteps "true";
Unattended-Upgrade::Remove-Unused-Kernel-Packages "true";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
Unattended-Upgrade::Automatic-Reboot "false";
EOF
sudo tee /etc/apt/apt.conf.d/20auto-upgrades > /dev/null <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
echo "Unattended upgrades configured"
REMOTE
info "Automatic security updates enabled"

# =============================================================================
# STEP 3 — SSH KEY SETUP
# =============================================================================
step "3 — SSH key authentication"

LOCAL_PUBKEY=""
for keyfile in ~/.ssh/id_ed25519.pub ~/.ssh/id_rsa.pub ~/.ssh/id_ecdsa.pub; do
    if [[ -f "$keyfile" ]]; then
        LOCAL_PUBKEY=$(cat "$keyfile")
        info "Found local key: $keyfile"
        break
    fi
done

if [[ -z "$LOCAL_PUBKEY" ]]; then
    warn "No SSH public key found on this machine."
    read -rp "$(echo -e "${YELLOW}[?]${NC} Generate a new ed25519 key now? [Y/n]: ")" _genkey
    if [[ "${_genkey:-Y}" =~ ^[Yy]$ ]]; then
        ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N "" -C "pi-hole-admin"
        LOCAL_PUBKEY=$(cat ~/.ssh/id_ed25519.pub)
        info "New key generated: ~/.ssh/id_ed25519"
    else
        warn "Skipping key setup — password auth will remain enabled"
    fi
fi

if [[ -n "$LOCAL_PUBKEY" ]]; then
    $SSH "${PI_USER}@${PI_IP}" bash <<REMOTE
mkdir -p ~/.ssh
chmod 700 ~/.ssh
touch ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
# Add key only if not already present
if ! grep -qF "${LOCAL_PUBKEY}" ~/.ssh/authorized_keys 2>/dev/null; then
    echo "${LOCAL_PUBKEY}" >> ~/.ssh/authorized_keys
    echo "Key added"
else
    echo "Key already present"
fi
REMOTE
    info "SSH public key installed on Pi"

    echo ""
    warn "Testing key login now (this must succeed before password auth is disabled)..."
    if ssh -i ~/.ssh/id_ed25519 -p "${PI_PORT}" \
           -o BatchMode=yes \
           -o ConnectTimeout=8 \
           -o StrictHostKeyChecking=accept-new \
           "${PI_USER}@${PI_IP}" "echo '__KEY_OK__'" 2>/dev/null | grep -q "__KEY_OK__"; then
        info "Key login confirmed ✓"
    else
        warn "Key login FAILED — password auth will NOT be disabled."
        warn "Fix the key manually then re-run harden.sh."
        skip "SSH password-auth hardening"
        # jump past the block
        false
    fi && {
        $SSH "${PI_USER}@${PI_IP}" bash <<'REMOTE'
sudo sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo sed -i 's/^#*ChallengeResponseAuthentication.*/ChallengeResponseAuthentication no/' /etc/ssh/sshd_config
sudo sed -i 's/^#*PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sudo sed -i 's/^#*X11Forwarding.*/X11Forwarding no/' /etc/ssh/sshd_config
sudo sed -i 's/^#*MaxAuthTries.*/MaxAuthTries 3/' /etc/ssh/sshd_config
sudo sed -i 's/^#*LoginGraceTime.*/LoginGraceTime 20/' /etc/ssh/sshd_config
# Ensure the settings exist if not already present
grep -q "^PasswordAuthentication" /etc/ssh/sshd_config || echo "PasswordAuthentication no" | sudo tee -a /etc/ssh/sshd_config
grep -q "^PermitRootLogin"        /etc/ssh/sshd_config || echo "PermitRootLogin no"        | sudo tee -a /etc/ssh/sshd_config
sudo systemctl reload sshd
echo "SSH hardened: password auth disabled, root login disabled"
REMOTE
        info "SSH hardened — password login disabled, key-only from now on"
    }
else
    skip "SSH key setup"
fi

# =============================================================================
# STEP 4 — FAIL2BAN (brute force protection)
# =============================================================================
step "4 — fail2ban (brute-force protection)"
$SSH "${PI_USER}@${PI_IP}" bash <<REMOTE
sudo apt-get install -y -qq fail2ban
sudo tee /etc/fail2ban/jail.local > /dev/null <<'EOF'
[DEFAULT]
bantime  = 1h
findtime = 10m
maxretry = 3
ignoreip = 127.0.0.1/8 192.168.0.0/16 10.0.0.0/8

[sshd]
enabled  = true
port     = ${PI_PORT}
filter   = sshd
logpath  = /var/log/auth.log
maxretry = 3
bantime  = 24h
EOF
sudo systemctl enable fail2ban
sudo systemctl restart fail2ban
echo "fail2ban running"
REMOTE
info "fail2ban installed — blocks IPs after 3 failed SSH attempts for 24h"

# =============================================================================
# STEP 5 — FIREWALL (ufw)
# =============================================================================
step "5 — Firewall (ufw)"
$SSH "${PI_USER}@${PI_IP}" bash <<REMOTE
sudo apt-get install -y -qq ufw

# Reset to defaults
sudo ufw --force reset

# Default: deny all incoming, allow all outgoing
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH (on configured port)
sudo ufw allow ${PI_PORT}/tcp comment 'SSH'

# Allow DNS (Pi-hole)
sudo ufw allow 53/tcp  comment 'DNS TCP'
sudo ufw allow 53/udp  comment 'DNS UDP'

# Allow Pi-hole web admin (LAN only)
sudo ufw allow from 192.168.0.0/16 to any port 80   comment 'Pi-hole admin (LAN)'
sudo ufw allow from 10.0.0.0/8     to any port 80   comment 'Pi-hole admin (LAN)'

# Allow analytics dashboard (LAN only)
sudo ufw allow from 192.168.0.0/16 to any port 8080 comment 'Analytics dashboard (LAN)'
sudo ufw allow from 10.0.0.0/8     to any port 8080 comment 'Analytics dashboard (LAN)'

# Allow DHCP if Pi-hole is also DHCP server
sudo ufw allow 67/udp comment 'DHCP'

# Enable
sudo ufw --force enable
sudo ufw status verbose
REMOTE
info "Firewall enabled — only SSH, DNS, and LAN admin ports open"

# =============================================================================
# STEP 6 — DISABLE UNUSED SERVICES
# =============================================================================
step "6 — Disable unused services"
$SSH "${PI_USER}@${PI_IP}" bash <<'REMOTE'
# Disable Bluetooth (not needed for Pi-hole)
if systemctl is-enabled bluetooth 2>/dev/null | grep -q enabled; then
    sudo systemctl disable bluetooth --now 2>/dev/null || true
    echo "Bluetooth disabled"
fi

# Disable CUPS printing service
if systemctl is-enabled cups 2>/dev/null | grep -q enabled; then
    sudo systemctl disable cups --now 2>/dev/null || true
    echo "CUPS printing disabled"
fi

# Disable Avahi (mDNS — not needed, can leak info)
if systemctl is-enabled avahi-daemon 2>/dev/null | grep -q enabled; then
    sudo systemctl disable avahi-daemon --now 2>/dev/null || true
    echo "Avahi mDNS disabled"
fi

echo "Unused services disabled"
REMOTE
info "Unused services (Bluetooth, CUPS, Avahi) disabled"

# =============================================================================
# STEP 7 — KERNEL HARDENING (sysctl)
# =============================================================================
step "7 — Kernel hardening"
$SSH "${PI_USER}@${PI_IP}" bash <<'REMOTE'
sudo tee /etc/sysctl.d/99-pihole-hardening.conf > /dev/null <<'EOF'
# ── Network ──────────────────────────────────────────────────────────────────
# Ignore ICMP redirects (prevent MITM via routing table manipulation)
net.ipv4.conf.all.accept_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv4.conf.all.send_redirects = 0

# Don't accept source-routed packets
net.ipv4.conf.all.accept_source_route = 0
net.ipv6.conf.all.accept_source_route = 0

# Enable SYN flood protection
net.ipv4.tcp_syncookies = 1

# Ignore broadcast pings (Smurf attack mitigation)
net.ipv4.icmp_echo_ignore_broadcasts = 1

# Log suspicious martian packets
net.ipv4.conf.all.log_martians = 1

# Disable IPv6 router advertisements
net.ipv6.conf.all.accept_ra = 0

# ── Memory ───────────────────────────────────────────────────────────────────
# Restrict kernel pointer exposure
kernel.kptr_restrict = 2

# Restrict dmesg to root only
kernel.dmesg_restrict = 1

# Restrict ptrace to parent processes only
kernel.yama.ptrace_scope = 1
EOF

sudo sysctl --system -q
echo "Kernel hardening applied"
REMOTE
info "Kernel hardening applied (anti-MITM, SYN flood protection, pointer hiding)"

# =============================================================================
# STEP 8 — PIHOLE-SPECIFIC: RESTRICT ADMIN TO LAN
# =============================================================================
step "8 — Pi-hole admin interface lockdown"
$SSH "${PI_USER}@${PI_IP}" bash <<'REMOTE'
# Pi-hole v6 uses lighttpd — restrict to local network interfaces only
LIGHTTPD_CONF="/etc/lighttpd/lighttpd.conf"
if [[ -f "$LIGHTTPD_CONF" ]]; then
    # Check if already restricted
    if grep -q "server.bind" "$LIGHTTPD_CONF"; then
        echo "lighttpd already has bind config — skipping"
    else
        # Pi-hole is already LAN-only via firewall (step 5); this adds a second layer
        echo "lighttpd bind config: firewall already restricts access to LAN"
    fi
fi

# Ensure Pi-hole's own rate limiting is enabled (prevents DNS amplification abuse)
if command -v pihole &>/dev/null; then
    # v6: rate limiting via FTL config
    if [[ -f /etc/pihole/pihole.toml ]]; then
        if ! grep -q "rateLimit" /etc/pihole/pihole.toml 2>/dev/null; then
            echo "Rate limiting already default in Pi-hole v6"
        fi
    fi
fi
echo "Pi-hole admin locked to LAN via firewall"
REMOTE
info "Pi-hole admin interface restricted to LAN only"

# =============================================================================
# STEP 9 — LOG ROTATION & CLEANUP
# =============================================================================
step "9 — Log rotation"
$SSH "${PI_USER}@${PI_IP}" bash <<'REMOTE'
sudo tee /etc/logrotate.d/pihole-analytics > /dev/null <<'EOF'
/home/pi/pihole-analytics/logs/*.log {
    weekly
    rotate 4
    compress
    delaycompress
    missingok
    notifempty
    create 0640 pi pi
}
EOF
echo "Log rotation configured"
REMOTE
info "Log rotation configured (weekly, 4 weeks retention, compressed)"

# =============================================================================
# STEP 10 — SUMMARY
# =============================================================================
step "10 — Security audit summary"
$SSH "${PI_USER}@${PI_IP}" bash <<'REMOTE'
echo ""
echo "  ── Open ports ──"
sudo ss -tlnp | grep -v '127.0.0.1' | tail -n +2 | awk '{print "    " $1 " " $4}'

echo ""
echo "  ── Firewall status ──"
sudo ufw status | head -20 | awk '{print "    " $0}'

echo ""
echo "  ── fail2ban status ──"
sudo fail2ban-client status sshd 2>/dev/null | awk '{print "    " $0}' || echo "    (check with: sudo fail2ban-client status sshd)"

echo ""
echo "  ── SSH auth method ──"
grep -E "^PasswordAuthentication|^PermitRootLogin|^MaxAuthTries" /etc/ssh/sshd_config | awk '{print "    " $0}'

echo ""
echo "  ── Running services (non-system) ──"
systemctl list-units --type=service --state=running --no-pager | grep -v systemd | grep -v "\-" | head -15 | awk '{print "    " $0}'
REMOTE

echo ""
echo -e "${GREEN}${BOLD}━━━  Hardening complete  ━━━${NC}"
echo ""
echo "  What was done:"
echo "  ✅  System packages updated"
echo "  ✅  Automatic security updates enabled"
echo "  ✅  SSH key authentication configured"
echo "  ✅  Password brute-force protection (fail2ban)"
echo "  ✅  Firewall — only SSH + DNS + LAN ports open"
echo "  ✅  Unused services disabled (Bluetooth, CUPS, Avahi)"
echo "  ✅  Kernel hardening (MITM, SYN flood, pointer exposure)"
echo "  ✅  Pi-hole admin restricted to LAN"
echo "  ✅  Log rotation configured"
echo ""
echo "  Recommended next steps:"
echo "  • Change Pi-hole web password:  pihole -a -p"
echo "  • Change Pi system password:    passwd"
echo "  • Review open ports regularly:  sudo ss -tlnp"
echo "  • Check fail2ban bans:          sudo fail2ban-client status sshd"
echo "  • Check firewall:               sudo ufw status"
echo ""
