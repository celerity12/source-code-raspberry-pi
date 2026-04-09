#!/usr/bin/env bash
# =============================================================================
# Pi-hole Analytics — Interactive Deployment Script
# Run from your Linux box:  bash deploy.sh
# =============================================================================
set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'

info()    { echo -e "${GREEN}[✓]${NC} $*"; }
warn()    { echo -e "${YELLOW}[!]${NC} $*"; }
error()   { echo -e "${RED}[✗]${NC} $*"; }
step()    { echo -e "\n${BOLD}${CYAN}━━━  $*  ━━━${NC}"; }
prompt()  { echo -e "${YELLOW}[?]${NC} $*"; }
note()    { echo -e "${DIM}    $*${NC}"; }
divider() { echo -e "${DIM}────────────────────────────────────────────────────${NC}"; }

pause() {
    echo ""
    read -rp "$(echo -e "${BOLD}Press Enter to continue...${NC}")" _
}

confirm() {
    # confirm "Question" — returns 0 for yes, 1 for no
    local msg="$1"
    while true; do
        read -rp "$(echo -e "${YELLOW}[?]${NC} ${msg} [y/n]: ")" yn
        case "$yn" in
            [Yy]*) return 0 ;;
            [Nn]*) return 1 ;;
            *) echo "    Please answer y or n." ;;
        esac
    done
}

# ── State (filled in during the script) ──────────────────────────────────────
PI_IP=""
PI_USER=""
PI_PORT="22"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$PROJECT_DIR/config/config.yaml"

# =============================================================================
# WELCOME
# =============================================================================
clear
echo -e "${BOLD}"
echo "  ╔══════════════════════════════════════════════════════╗"
echo "  ║        Pi-hole Analytics — Deployment Setup          ║"
echo "  ║        Linux Box  →  Raspberry Pi 5 (Ubuntu)         ║"
echo "  ╚══════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo "  This script will guide you through every step:"
echo "  1. Check prerequisites"
echo "  2. Find your Pi's IP address"
echo "  3. Verify SSH access"
echo "  4. Get your Pi-hole API token"
echo "  5. Get your Gmail App Password"
echo "  6. Map your device IPs to names"
echo "  7. Copy files to the Pi"
echo "  8. Run the installer on the Pi"
echo "  9. Lock down file permissions (security)"
echo " 10. Verify everything is working"
echo " 11. Send a test email report"
echo " 12. Final verification"
echo ""
note "Project directory: $PROJECT_DIR"
note "Config file:       $CONFIG_FILE"
pause

# =============================================================================
# PREREQUISITES CHECK
# =============================================================================
step "Prerequisites Check"

echo ""
echo "  Before we begin, ensure you have the following ready:"
echo ""
echo "  ${BOLD}Hardware/Software:${NC}"
echo "  - Raspberry Pi 5 (or compatible) with Ubuntu 22.04/24.04 (64-bit) installed"
echo "  - Pi-hole installed and running on the Pi"
echo "  - SSH enabled on the Pi"
echo "  - Internet access on the Pi"
echo "  - Your Pi's IP address (find via router, nmap, or hostname -I)"
echo ""
echo "  ${BOLD}Credentials:${NC}"
echo "  - Pi-hole API token (from Pi-hole admin → Settings → API/Web interface)"
echo "  - Gmail App Password (requires 2-Step Verification; create dedicated account)"
echo "  - Device IP mappings (optional but recommended for readable names)"
echo ""
echo "  ${BOLD}On your Linux box:${NC}"
echo "  - SSH client (ssh, scp)"
echo "  - Project files in $PROJECT_DIR"
echo ""

if ! confirm "Do you have all prerequisites ready?"; then
    echo ""
    echo "  Please prepare the prerequisites and re-run this script."
    echo "  See DEPLOYMENT.md for detailed instructions."
    exit 1
fi
pause

# =============================================================================
# STEP 2 — FIND THE PI'S IP ADDRESS
# =============================================================================
step "STEP 2 — Find Your Raspberry Pi's IP Address"

echo ""
echo "  You need the IP address of your Raspberry Pi on your local network."
echo ""
echo "  Option A — scan the network (requires nmap):"
echo -e "  ${DIM}nmap -sn 192.168.68.0/24 | grep -A2 -i raspberry${NC}"
echo ""
echo "  Option B — check your router's admin page:"
echo -e "  ${DIM}Usually at http://192.168.68.1 or http://192.168.1.1 → DHCP / Connected devices${NC}"
echo ""
echo "  Option C — on the Pi itself (if you have a screen):"
echo -e "  ${DIM}hostname -I${NC}"
echo ""

if confirm "Do you want me to run an nmap scan now?"; then
    read -rp "$(echo -e "${YELLOW}[?]${NC} Enter your subnet (e.g. 192.168.68.0/24): ")" SUBNET
    echo ""
    if command -v nmap &>/dev/null; then
        info "Scanning $SUBNET ..."
        nmap -sn "$SUBNET" 2>/dev/null | grep -E "(Nmap scan|raspberry|Ubuntu)" -i -A1 || true
    else
        warn "nmap is not installed. Install it with:  sudo apt install nmap"
    fi
    echo ""
fi

read -rp "$(echo -e "${YELLOW}[?]${NC} Enter your Pi's IP address: ")" PI_IP
read -rp "$(echo -e "${YELLOW}[?]${NC} Enter your Pi's SSH username (default: ubuntu): ")" PI_USER
PI_USER="${PI_USER:-ubuntu}"
read -rp "$(echo -e "${YELLOW}[?]${NC} Enter SSH port (default: 22): ")" PI_PORT_INPUT
PI_PORT="${PI_PORT_INPUT:-22}"

info "Will connect as ${BOLD}${PI_USER}@${PI_IP}:${PI_PORT}${NC}"
pause

# =============================================================================
# STEP 3 — VERIFY SSH ACCESS
# =============================================================================
step "STEP 3 — Verify SSH Access"

echo ""
echo "  Testing SSH connection to ${PI_USER}@${PI_IP} ..."
echo ""

if ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new \
       -p "$PI_PORT" "${PI_USER}@${PI_IP}" \
       "echo '__SSH_OK__' && lsb_release -d && python3 --version" 2>/dev/null | grep -q "__SSH_OK__"; then
    info "SSH connection successful"
    echo ""
    SSH_INFO=$(ssh -o ConnectTimeout=10 -p "$PI_PORT" "${PI_USER}@${PI_IP}" \
        "lsb_release -d && python3 --version" 2>/dev/null || true)
    echo "  Remote system:"
    echo "$SSH_INFO" | while IFS= read -r line; do echo "    $line"; done
else
    warn "SSH connection failed."
    echo ""
    echo "  Possible causes:"
    echo "  - Wrong IP address or username"
    echo "  - SSH not enabled on the Pi"
    echo "  - Pi not reachable on the network"
    echo "  - First login: Ubuntu forces a password change — connect manually first:"
    echo -e "    ${DIM}ssh ${PI_USER}@${PI_IP}${NC}"
    echo ""
    if ! confirm "Continue anyway?"; then
        echo "Exiting. Fix SSH access and re-run deploy.sh."
        exit 1
    fi
fi
pause

# =============================================================================
# STEP 4 — PI-HOLE API TOKEN
# =============================================================================
step "STEP 4 — Pi-hole Credentials"

echo ""
echo "  Two credentials are needed:"
echo ""
echo "  ${BOLD}A) Pi-hole Admin Password${NC} (Pi-hole v6)"
echo "  The same password you use to log into http://${PI_IP}/admin"
echo "  Used by the dashboard block/unblock feature."
echo ""
echo "  ${BOLD}B) Pi-hole API Token${NC} (legacy fallback)"
echo "  ┌─────────────────────────────────────────────────────┐"
echo "  │ 1. Open http://${PI_IP}/admin in your browser        "
echo "  │ 2. Go to Settings → API / Web interface              "
echo "  │ 3. Click  Show API token  and copy the string        "
echo "  └─────────────────────────────────────────────────────┘"
echo ""
echo -e "  ${YELLOW}Security note:${NC}"
echo "  • Both are stored in config.yaml — locked down in Step 10"
echo "  • Never share them or commit config.yaml to git"
echo ""

if confirm "Open Pi-hole admin in your default browser now?"; then
    xdg-open "http://${PI_IP}/admin" 2>/dev/null || \
    open "http://${PI_IP}/admin" 2>/dev/null || \
    echo -e "  Could not open browser. Go to: ${CYAN}http://${PI_IP}/admin${NC}"
    echo ""
fi

read -rsp "$(echo -e "${YELLOW}[?]${NC} Enter your Pi-hole admin password (input hidden): ")" PIHOLE_PASSWORD
echo ""
if [[ -z "$PIHOLE_PASSWORD" ]]; then
    warn "No password entered. Block/unblock from dashboard will not push to Pi-hole."
    warn "Add it manually to config/config.yaml as  password: YOUR_PASSWORD"
    PIHOLE_PASSWORD=""
else
    info "Admin password captured"
fi

echo ""
read -rp "$(echo -e "${YELLOW}[?]${NC} Paste your Pi-hole API token (legacy): ")" API_TOKEN
if [[ -z "$API_TOKEN" ]]; then
    warn "No token entered. You can add it manually to config/config.yaml later."
    API_TOKEN="YOUR_PIHOLE_API_TOKEN_HERE"
else
    info "API token captured (${#API_TOKEN} characters)"
fi
pause

# =============================================================================
# STEP 5 — GMAIL APP PASSWORD
# =============================================================================
step "STEP 5 — Gmail App Password"

echo ""
echo "  The App Password lets this system send email reports via Gmail SMTP."
echo "  Google blocks automated logins with your real password — the App"
echo "  Password is the approved alternative."
echo ""
echo "  How to get it:"
echo "  ┌─────────────────────────────────────────────────────┐"
echo "  │ 1. Go to myaccount.google.com                        "
echo "  │ 2. Click Security in the left sidebar                "
echo "  │ 3. Confirm 2-Step Verification is ON                 "
echo "  │    (App Passwords are unavailable without it)        "
echo "  │ 4. Search for  App passwords  at the top of the page "
echo "  │ 5. App name: type  Pi-hole Analytics  → Create       "
echo "  │ 6. Copy the 16-character password shown              "
echo "  │    It is shown ONCE — save it now                    "
echo "  └─────────────────────────────────────────────────────┘"
echo ""
echo -e "  ${YELLOW}Security note:${NC}"
echo "  • Grants email send access to your Gmail account"
echo "  • Also stored in config.yaml — locked down in Step 10"
echo "  • Recommendation: create a separate Gmail account just for sending"
echo "    these reports so a leak only affects a throwaway address"
echo "  • Revoke at any time: myaccount.google.com → Security → App passwords → trash icon"
echo ""

if confirm "Open Google account security page in your browser now?"; then
    xdg-open "https://myaccount.google.com/security" 2>/dev/null || \
    open "https://myaccount.google.com/security" 2>/dev/null || \
    echo -e "  Go to: ${CYAN}https://myaccount.google.com/security${NC}"
    echo ""
fi

read -rp "$(echo -e "${YELLOW}[?]${NC} Enter your Gmail sender address: ")" GMAIL_SENDER
read -rp "$(echo -e "${YELLOW}[?]${NC} Enter your Gmail recipient address (can be same): ")" GMAIL_RECIPIENT
read -rsp "$(echo -e "${YELLOW}[?]${NC} Paste your Gmail App Password (input hidden): ")" GMAIL_APP_PASS
echo ""

if [[ -z "$GMAIL_APP_PASS" ]]; then
    warn "No App Password entered. You can add it manually to config/config.yaml later."
    GMAIL_APP_PASS="YOUR_APP_PASSWORD"
else
    info "App Password captured (${#GMAIL_APP_PASS} characters)"
fi
pause

# =============================================================================
# STEP 6 — DEVICE NAMES
# =============================================================================
step "STEP 6 — Map Device IPs to Names"

echo ""
echo "  Pi-hole records DNS queries by IP address only."
echo "  Mapping IPs to device names makes reports readable."
echo ""
echo "  How to find your device IPs:"
echo "  ┌─────────────────────────────────────────────────────┐"
echo "  │ Option A — Router admin page (easiest)               "
echo "  │   http://192.168.68.1 → DHCP / Connected devices     "
echo "  │                                                       "
echo "  │ Option B — Pi-hole Network page                      "
echo "  │   http://${PI_IP}/admin → Network                     "
echo "  │                                                       "
echo "  │ Option C — ARP table (run on any machine)            "
echo "  │   arp -n                                              "
echo "  └─────────────────────────────────────────────────────┘"
echo ""
echo -e "  ${YELLOW}Security note:${NC}"
echo "  • DNS history + device names = a per-person activity log"
echo "  • Assign static DHCP leases in your router so IPs never change"
echo "  • Avoid names that identify individuals if config.yaml were leaked"
echo ""
echo "  Enter your devices below. Press Enter with an empty IP when done."
echo "  (You can also edit config/config.yaml directly at any time)"
echo ""

declare -A DEVICE_MAP=()
while true; do
    read -rp "$(echo -e "  ${CYAN}Device IP${NC} (or press Enter to finish): ")" DEV_IP
    [[ -z "$DEV_IP" ]] && break
    read -rp "$(echo -e "  ${CYAN}Device name${NC} for ${DEV_IP}: ")" DEV_NAME
    if [[ -n "$DEV_NAME" ]]; then
        DEVICE_MAP["$DEV_IP"]="$DEV_NAME"
        info "Added: ${DEV_IP} → ${DEV_NAME}"
    fi
done

if [[ ${#DEVICE_MAP[@]} -eq 0 ]]; then
    warn "No devices entered. You can add them manually to config/config.yaml later."
fi
pause

# =============================================================================
# STEP 7 — WRITE CONFIG.YAML
# =============================================================================
step "STEP 7 — Write config/config.yaml"

echo ""
echo "  Writing your settings into config/config.yaml ..."
echo ""

# Write all values in a single Python pass to avoid read/write races
python3 - <<PYEOF
import yaml
from pathlib import Path

cfg_path = Path("$CONFIG_FILE")
with open(cfg_path) as f:
    cfg = yaml.safe_load(f)

# Pi-hole connection — always localhost since analytics runs on the same Pi
cfg['pihole']['host']      = "http://localhost"
cfg['pihole']['api_token'] = "$API_TOKEN"
if "$PIHOLE_PASSWORD":
    cfg['pihole']['password'] = "$PIHOLE_PASSWORD"

# Email
cfg['email']['sender_email']     = "$GMAIL_SENDER"
cfg['email']['sender_password']  = "$GMAIL_APP_PASS"
cfg['email']['recipient_emails'] = ["$GMAIL_RECIPIENT"]

# Clients — replace example entries with what the user entered;
# use empty dict (not the template placeholders) when none were entered
new_clients = {}
$(for ip in "${!DEVICE_MAP[@]}"; do
    echo "new_clients['${ip}'] = '${DEVICE_MAP[$ip]}'"
done)
cfg['clients'] = new_clients

with open(cfg_path, 'w') as f:
    yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

print("  config.yaml written successfully")
PYEOF

info "config/config.yaml updated"
echo ""
echo "  Preview of key settings:"
echo -e "  ${DIM}pihole.host:      http://${PI_IP}${NC}"
echo -e "  ${DIM}pihole.api_token: ${API_TOKEN:0:8}... (${#API_TOKEN} chars)${NC}"
echo -e "  ${DIM}email.sender:     ${GMAIL_SENDER}${NC}"
echo -e "  ${DIM}devices mapped:   ${#DEVICE_MAP[@]}${NC}"
pause

# =============================================================================
# STEP 8 — COPY FILES TO THE PI
# =============================================================================
step "STEP 8 — Copy Project Files to the Pi"

echo ""
echo "  Copying ${PROJECT_DIR} → ${PI_USER}@${PI_IP}:~/pihole-analytics"
echo ""

# Use rsync when available (handles missing dest dir, excludes .git/.claude, faster).
# Fall back to creating the dir first then using scp.
if command -v rsync &>/dev/null; then
    rsync -az --delete \
        --exclude='.git/' \
        --exclude='.claude/' \
        --exclude='__pycache__/' \
        --exclude='*.pyc' \
        --exclude='.env' \
        --exclude='venv/' \
        -e "ssh -p $PI_PORT" \
        "$PROJECT_DIR/" "${PI_USER}@${PI_IP}:~/pihole-analytics/"
else
    warn "rsync not found — falling back to scp (install rsync for better reliability)"
    ssh -p "$PI_PORT" "${PI_USER}@${PI_IP}" "mkdir -p ~/pihole-analytics"
    scp -P "$PI_PORT" -r \
        "$PROJECT_DIR/scripts" \
        "$PROJECT_DIR/config" \
        "$PROJECT_DIR/requirements.txt" \
        "$PROJECT_DIR/install.sh" \
        "${PI_USER}@${PI_IP}:~/pihole-analytics/"
fi

echo ""
info "Files copied. Verifying..."

REMOTE_LS=$(ssh -p "$PI_PORT" "${PI_USER}@${PI_IP}" "ls ~/pihole-analytics/" 2>/dev/null)
echo ""
echo "  Remote directory contents:"
echo "$REMOTE_LS" | while IFS= read -r line; do echo "    $line"; done
echo ""
info "Copy verified"
pause

# =============================================================================
# STEP 9 — RUN THE INSTALLER ON THE PI
# =============================================================================
step "STEP 9 — Run the Installer on the Pi"

echo ""
echo "  The installer will:"
echo "  • Install python3, python3-pip, python3-venv, sqlite3 via apt"
echo "  • Create the install directory at /home/${PI_USER}/pihole-analytics/"
echo "  • Set up a Python virtual environment"
echo "  • Install flask, pyyaml, requests"
echo "  • Create and enable all systemd services and timers"
echo "  • Add adult content blocklist to Pi-hole"
echo "  • Block DoH providers so browsers cannot bypass Pi-hole"
echo "  • Download the UT1 third-party domain database (~50 MB)"
echo "  • Run the first data fetch from Pi-hole"
echo ""
echo -e "  ${YELLOW}Note:${NC} The installer defaults to SERVICE_USER=pi."
echo "  Patching it now to use: ${BOLD}${PI_USER}${NC}"
echo ""

# Patch install.sh on the Pi to use the correct username
ssh -p "$PI_PORT" "${PI_USER}@${PI_IP}" bash <<REMOTE
    sed -i "s/SERVICE_USER=\"pi\"/SERVICE_USER=\"${PI_USER}\"/" ~/pihole-analytics/install.sh
    sed -i "s|/home/pi/pihole-analytics|/home/${PI_USER}/pihole-analytics|g" ~/pihole-analytics/install.sh
    echo "install.sh patched for user: ${PI_USER}"
REMOTE

echo ""
if confirm "Run sudo bash install.sh on the Pi now?"; then
    echo ""
    info "Running installer — this will take 2–4 minutes..."
    echo ""
    ssh -p "$PI_PORT" -t "${PI_USER}@${PI_IP}" \
        "cd ~/pihole-analytics && sudo bash install.sh"
else
    warn "Skipped. Run manually on the Pi:"
    echo -e "  ${DIM}ssh ${PI_USER}@${PI_IP}${NC}"
    echo -e "  ${DIM}cd ~/pihole-analytics && sudo bash install.sh${NC}"
fi
pause

# =============================================================================
# STEP 10 — LOCK DOWN FILE PERMISSIONS
# =============================================================================
step "STEP 10 — Lock Down File Permissions (Security)"

echo ""
echo "  config.yaml contains your API token and Gmail App Password in plaintext."
echo "  These commands ensure only the service account can read it."
echo ""
echo "  Commands to run:"
echo -e "  ${DIM}chmod 600 /home/${PI_USER}/pihole-analytics/config/config.yaml${NC}"
echo -e "  ${DIM}chown ${PI_USER}:${PI_USER} /home/${PI_USER}/pihole-analytics/config/config.yaml${NC}"
echo -e "  ${DIM}chmod 700 /home/${PI_USER}/pihole-analytics/data/${NC}"
echo -e "  ${DIM}chmod 700 /home/${PI_USER}/pihole-analytics/logs/${NC}"
echo ""

if confirm "Apply these permissions now?"; then
    ssh -p "$PI_PORT" "${PI_USER}@${PI_IP}" bash <<REMOTE
        sudo chown -R ${PI_USER}:${PI_USER} /home/${PI_USER}/pihole-analytics/
        chmod 600 /home/${PI_USER}/pihole-analytics/config/config.yaml
        chmod 700 /home/${PI_USER}/pihole-analytics/data/
        chmod 700 /home/${PI_USER}/pihole-analytics/logs/
        echo ""
        echo "Permissions applied:"
        ls -la /home/${PI_USER}/pihole-analytics/config/config.yaml
        ls -ld /home/${PI_USER}/pihole-analytics/data/
        ls -ld /home/${PI_USER}/pihole-analytics/logs/
REMOTE
    info "Permissions locked down"
else
    warn "Skipped. Run these commands manually on the Pi — important for security."
fi
pause

# =============================================================================
# STEP 11 — VERIFY THE INSTALLATION
# =============================================================================
step "STEP 11 — Verify the Installation"

echo ""
info "Checking dashboard service status..."
ssh -p "$PI_PORT" "${PI_USER}@${PI_IP}" \
    "systemctl is-active pihole-analytics-dashboard && echo 'Dashboard: running' || echo 'Dashboard: NOT running'"

echo ""
info "Checking scheduled timers..."
ssh -p "$PI_PORT" "${PI_USER}@${PI_IP}" \
    "systemctl list-timers pihole-analytics* --no-pager 2>/dev/null || echo 'No timers found'"

echo ""
info "Checking database..."
ssh -p "$PI_PORT" "${PI_USER}@${PI_IP}" \
    "sqlite3 /home/${PI_USER}/pihole-analytics/data/analytics.db 'SELECT COUNT(*) || \" queries in database\" FROM queries;' 2>/dev/null || echo 'Database not found or empty'"

echo ""
echo -e "  ${BOLD}Dashboard URL:${NC}  ${CYAN}http://${PI_IP}:8080${NC}"
echo ""
if confirm "Open the dashboard in your browser now?"; then
    xdg-open "http://${PI_IP}:8080" 2>/dev/null || \
    open "http://${PI_IP}:8080" 2>/dev/null || \
    echo -e "  Go to: ${CYAN}http://${PI_IP}:8080${NC}"
fi
pause

# =============================================================================
# STEP 12 — TEST EMAIL REPORT
# =============================================================================
step "STEP 12 — Send a Test Email Report"

echo ""
echo "  This sends a daily report email to: ${GMAIL_RECIPIENT}"
echo "  Check your inbox (and spam folder) after running this."
echo ""

if confirm "Send a test email report now?"; then
    echo ""
    info "Sending — check your inbox in 30 seconds..."
    ssh -p "$PI_PORT" "${PI_USER}@${PI_IP}" bash <<REMOTE
        sudo -u ${PI_USER} /home/${PI_USER}/pihole-analytics/venv/bin/python3 \
            /home/${PI_USER}/pihole-analytics/scripts/core/reporter.py --period daily \
        && echo "" && echo "[✓] Email sent successfully" \
        || echo "[!] Email failed — check /home/${PI_USER}/pihole-analytics/logs/reporter.log"
REMOTE
else
    warn "Skipped. To test later:"
    echo -e "  ${DIM}ssh ${PI_USER}@${PI_IP}${NC}"
    echo -e "  ${DIM}sudo -u ${PI_USER} /home/${PI_USER}/pihole-analytics/venv/bin/python3 \\${NC}"
    echo -e "  ${DIM}    /home/${PI_USER}/pihole-analytics/scripts/core/reporter.py --period daily${NC}"
fi
pause

# =============================================================================
# DONE
# =============================================================================
clear
echo -e "${BOLD}${GREEN}"
echo "  ╔══════════════════════════════════════════════════════╗"
echo "  ║          Deployment Complete!                        ║"
echo "  ╚══════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo -e "  ${BOLD}Dashboard:${NC}       ${CYAN}http://${PI_IP}:8080${NC}  (password is in config.yaml)"
echo -e "  ${BOLD}Pi address:${NC}      ${PI_IP}"
echo -e "  ${BOLD}SSH user:${NC}        ${PI_USER}"
echo -e "  ${BOLD}Install dir:${NC}     /home/${PI_USER}/pihole-analytics/"
echo -e "  ${BOLD}Config:${NC}          /home/${PI_USER}/pihole-analytics/config/config.yaml"
echo ""
divider
echo ""
echo -e "  ${BOLD}What runs automatically:${NC}"
echo "  • Adult sites blocked via Pi-hole blocklist"
echo "  • DoH bypass blocked at DNS level"
echo ""
echo -e "  ${BOLD}What runs automatically:${NC}"
echo "  • Data fetch          every 15 minutes"
echo "  • Daily email report  every morning at 7:00 AM"
echo "  • Weekly report       Monday at 7:10 AM"
echo "  • Monthly report      1st of each month at 7:20 AM"
echo "  • UT1 DB refresh      every Sunday at 3:00 AM"
echo ""
divider
echo ""
echo -e "  ${BOLD}Useful commands on the Pi:${NC}"
echo -e "  ${DIM}# Watch the live fetch log${NC}"
echo -e "  journalctl -u pihole-analytics-fetch -f"
echo ""
echo -e "  ${DIM}# Check all timer schedules${NC}"
echo -e "  systemctl list-timers pihole-analytics*"
echo ""
echo -e "  ${DIM}# Restart the dashboard${NC}"
echo -e "  sudo systemctl restart pihole-analytics-dashboard"
echo ""
echo -e "  ${DIM}# Add a new device — edit the clients section${NC}"
echo -e "  nano /home/${PI_USER}/pihole-analytics/config/config.yaml"
echo ""
divider
echo ""
echo -e "  ${BOLD}${YELLOW}Security reminders:${NC}"
echo "  • config.yaml permissions locked to 600 (only service user can read)"
echo "  • Never commit config.yaml to git"
echo "  • Regenerate your Pi-hole API token if it is ever exposed"
echo "  • Revoke the Gmail App Password at myaccount.google.com if needed"
echo "  • Assign static DHCP leases in your router to keep device IPs stable"
echo ""
divider
echo ""
echo -e "  Full guide: ${CYAN}DEPLOYMENT.md${NC}"
echo ""
