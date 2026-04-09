#!/usr/bin/env bash
# ============================================================
# Celerity — Full Deployment Script
# Deploys pi_hole_web_survillance + pihole-mcp-server to Pi
#
# Usage:
#   bash test-deployment-celerity12.sh          # full deploy
#   bash test-deployment-celerity12.sh --update # quick update only (no reinstall)
# ============================================================
set -euo pipefail

# ── Config ────────────────────────────────────────────────
PI_HOST="192.168.68.102"
PI_USER="pi"
PI_SSH="${PI_USER}@${PI_HOST}"
SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ANALYTICS_SRC="${SRC_ROOT}/pi_hole_web_survillance"
MCP_SRC="${SRC_ROOT}/pihole-mcp-server"

ANALYTICS_DEST="~/pihole-analytics"
MCP_DEST="~/pihole-mcp-server"

# ── Colours ───────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }
section() { echo -e "\n${CYAN}${BOLD}━━━ $* ━━━${NC}"; }
ok()      { echo -e "${GREEN}  ✔${NC}  $*"; }

# ── Arg parsing ───────────────────────────────────────────
UPDATE_ONLY=false
for arg in "$@"; do
    [[ "$arg" == "--update" ]] && UPDATE_ONLY=true
done

# ─────────────────────────────────────────────────────────
section "Pre-flight checks"
# ─────────────────────────────────────────────────────────

# Check source directories exist
[[ -d "$ANALYTICS_SRC" ]] || error "pi_hole_web_survillance not found at $ANALYTICS_SRC"
[[ -d "$MCP_SRC"       ]] || error "pihole-mcp-server not found at $MCP_SRC"
ok "Source directories found"

# Check required config files exist (with real values, not placeholders)
for f in \
    "$ANALYTICS_SRC/config/config.yaml" \
    "$MCP_SRC/config/connectors/pihole.yaml" \
    "$MCP_SRC/config/connectors/telegram.yaml" \
    "$MCP_SRC/config/llm/gemini.yaml"
do
    [[ -f "$f" ]] || error "Missing config: $f"
    if grep -q "YOUR_" "$f" 2>/dev/null; then
        error "Config still has placeholders: $f — fill in real values first"
    fi
done
ok "All config files present and filled in"

# Check SSH connectivity
info "Testing SSH connection to ${PI_SSH}..."
ssh -o ConnectTimeout=10 -o BatchMode=yes "$PI_SSH" "echo ok" > /dev/null 2>&1 \
    || error "Cannot SSH to ${PI_SSH}. Check the Pi is on and SSH is enabled."
ok "SSH connection to ${PI_SSH} working"

# ─────────────────────────────────────────────────────────
section "Part 1 — pi_hole_web_survillance"
# ─────────────────────────────────────────────────────────

info "Syncing files to ${PI_SSH}:${ANALYTICS_DEST}..."
rsync -az --progress \
    --exclude='.git/' \
    --exclude='.claude/' \
    --exclude='venv/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='data/' \
    --exclude='logs/' \
    --exclude='reports/' \
    "$ANALYTICS_SRC/" \
    "${PI_SSH}:${ANALYTICS_DEST}/"
ok "Files synced"

info "Copying config/config.yaml..."
scp "$ANALYTICS_SRC/config/config.yaml" \
    "${PI_SSH}:${ANALYTICS_DEST}/config/config.yaml"
ok "config.yaml copied"

if [[ "$UPDATE_ONLY" == true ]]; then
    info "Update mode — restarting dashboard only (skipping installer)..."
    ssh "$PI_SSH" "sudo systemctl restart pihole-analytics-dashboard"
    ok "Dashboard restarted"
else
    info "Running installer on Pi (this takes ~2 min for first run)..."
    ssh -t "$PI_SSH" "cd ${ANALYTICS_DEST} && sudo bash install.sh"
    ok "Installer complete"

    info "Locking down permissions..."
    ssh "$PI_SSH" "
        sudo chown -R ${PI_USER}:${PI_USER} ${ANALYTICS_DEST} &&
        chmod 600 ${ANALYTICS_DEST}/config/config.yaml &&
        chmod 700 ${ANALYTICS_DEST}/data/ ${ANALYTICS_DEST}/logs/
    "
    ok "Permissions set"

    info "Fixing PYTHONPATH in systemd service..."
    ssh "$PI_SSH" "
        grep -q PYTHONPATH /etc/systemd/system/pihole-analytics-dashboard.service 2>/dev/null || \
        sudo sed -i '/^ExecStart=/i Environment=PYTHONPATH=/home/${PI_USER}/pihole-analytics' \
            /etc/systemd/system/pihole-analytics-dashboard.service
        sudo systemctl daemon-reload &&
        sudo systemctl restart pihole-analytics-dashboard
    "
    ok "Dashboard service fixed and restarted"
fi

# ─────────────────────────────────────────────────────────
section "Part 2 — pihole-mcp-server"
# ─────────────────────────────────────────────────────────

info "Syncing files to ${PI_SSH}:${MCP_DEST}..."
rsync -az --progress \
    --exclude='.git/' \
    --exclude='.claude/' \
    --exclude='venv/' \
    --exclude='.venv/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    "$MCP_SRC/" \
    "${PI_SSH}:${MCP_DEST}/"
ok "Files synced"

info "Copying secret config files..."
scp "$MCP_SRC/config/connectors/pihole.yaml" \
    "${PI_SSH}:${MCP_DEST}/config/connectors/pihole.yaml"
scp "$MCP_SRC/config/connectors/telegram.yaml" \
    "${PI_SSH}:${MCP_DEST}/config/connectors/telegram.yaml"
scp "$MCP_SRC/config/llm/gemini.yaml" \
    "${PI_SSH}:${MCP_DEST}/config/llm/gemini.yaml"
ok "Secret configs copied"

info "Locking down secret config permissions..."
ssh "$PI_SSH" "
    chmod 600 ${MCP_DEST}/config/connectors/pihole.yaml
    chmod 600 ${MCP_DEST}/config/connectors/telegram.yaml
    chmod 600 ${MCP_DEST}/config/llm/gemini.yaml
"
ok "Permissions set"

if [[ "$UPDATE_ONLY" == false ]]; then
    info "Installing Python dependencies on Pi..."
    ssh "$PI_SSH" "
        cd ${MCP_DEST} &&
        python3 -m venv .venv &&
        .venv/bin/pip install --quiet -r requirements.txt
    " || {
        warn "venv pip failed — trying --break-system-packages fallback..."
        ssh "$PI_SSH" "
            cd ${MCP_DEST} &&
            pip3 install --break-system-packages --quiet -r requirements.txt
        "
    }
    ok "Python dependencies installed"

    info "Installing pihole-mcp-watch systemd service..."
    ssh "$PI_SSH" "sudo tee /etc/systemd/system/pihole-mcp-watch.service > /dev/null" << EOF
[Unit]
Description=Pi-hole Telegram Bot + Watch Agent
After=network.target pihole-analytics-dashboard.service

[Service]
ExecStart=/home/${PI_USER}/pihole-mcp-server/.venv/bin/python3 /home/${PI_USER}/pihole-mcp-server/llm/gemini_agent.py --telegram --watch
WorkingDirectory=/home/${PI_USER}/pihole-mcp-server
Restart=on-failure
RestartSec=30
User=${PI_USER}

[Install]
WantedBy=multi-user.target
EOF

    ssh "$PI_SSH" "
        sudo systemctl daemon-reload &&
        sudo systemctl enable pihole-mcp-watch &&
        sudo systemctl restart pihole-mcp-watch
    "
    ok "pihole-mcp-watch service installed and started"
else
    info "Update mode — restarting pihole-mcp-watch..."
    ssh "$PI_SSH" "sudo systemctl restart pihole-mcp-watch"
    ok "pihole-mcp-watch restarted"
fi

# ─────────────────────────────────────────────────────────
section "Verification"
# ─────────────────────────────────────────────────────────

info "Checking service statuses..."

DASHBOARD_STATUS=$(ssh "$PI_SSH" "systemctl is-active pihole-analytics-dashboard 2>/dev/null || echo inactive")
MCP_STATUS=$(ssh "$PI_SSH" "systemctl is-active pihole-mcp-watch 2>/dev/null || echo inactive")

if [[ "$DASHBOARD_STATUS" == "active" ]]; then
    ok "pihole-analytics-dashboard: active"
else
    warn "pihole-analytics-dashboard: ${DASHBOARD_STATUS}"
fi

if [[ "$MCP_STATUS" == "active" ]]; then
    ok "pihole-mcp-watch (Telegram bot): active"
else
    warn "pihole-mcp-watch: ${MCP_STATUS}"
fi

if [[ "$UPDATE_ONLY" == false ]]; then
    info "Checking scheduled timers..."
    ssh "$PI_SSH" "systemctl list-timers pihole-analytics* --no-pager 2>/dev/null | head -12" || true

    info "Checking initial data fetch..."
    QUERY_COUNT=$(ssh "$PI_SSH" \
        "sqlite3 ${ANALYTICS_DEST}/data/analytics.db 'SELECT COUNT(*) FROM queries;' 2>/dev/null || echo 0")
    if [[ "$QUERY_COUNT" -gt 0 ]]; then
        ok "Database has ${QUERY_COUNT} queries"
    else
        warn "Database has 0 queries — fetcher may still be running (check in a minute)"
    fi
fi

# ─────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}═══════════════════════════════════════════${NC}"
echo -e "${GREEN}${BOLD}  Deployment complete!${NC}"
echo -e "${GREEN}${BOLD}═══════════════════════════════════════════${NC}"
echo ""
echo -e "  Dashboard:     ${CYAN}http://${PI_HOST}:8080${NC}"
echo -e "  Pi-hole admin: ${CYAN}http://${PI_HOST}/admin${NC}"
echo ""
echo -e "  Telegram bot:  send ${BOLD}/help${NC} to your bot to verify"
echo ""
echo -e "  Dashboard logs:  ssh ${PI_SSH} 'journalctl -u pihole-analytics-dashboard -f'"
echo -e "  Telegram logs:   ssh ${PI_SSH} 'journalctl -u pihole-mcp-watch -f'"
echo ""
