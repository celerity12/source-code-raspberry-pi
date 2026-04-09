#!/usr/bin/env bash
# =============================================================================
# Pi-hole Analytics — Local Test Runner
# Tests the full stack locally inside Docker before deploying to the Pi.
#
# Usage:  bash test_locally.sh
#
# What it does:
#   1.  Checks prerequisites (Docker)
#   2.  Asks whether to use a mock Pi-hole or your real Pi
#   3.  Asks for email credentials (or skips email testing)
#   4.  Asks for device name mappings
#   5.  Writes config/config.test.yaml  (never touches your real config.yaml)
#   6.  Builds Docker images
#   7.  Starts the mock Pi-hole (or skips if using real Pi)
#   8.  Runs the fetcher — populates data/analytics.db
#   9.  Verifies data was stored in the database
#  10.  Starts the dashboard at http://localhost:8080
#  11.  Runs the unit test suite inside the container
#  12.  Sends a test email report (optional)
#  13.  Prints a pass/fail summary
#  14.  Offers to clean up containers when done
# =============================================================================
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.test.yml"
TEST_CONFIG="$PROJECT_DIR/config/config.test.yaml"

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'

pass()    { echo -e "${GREEN}[PASS]${NC} $*"; PASSES=$((PASSES+1)); }
fail()    { echo -e "${RED}[FAIL]${NC} $*"; FAILURES=$((FAILURES+1)); }
info()    { echo -e "${GREEN}[✓]${NC}   $*"; }
warn()    { echo -e "${YELLOW}[!]${NC}   $*"; }
step()    { echo -e "\n${BOLD}${CYAN}━━━  $*  ━━━${NC}"; }
note()    { echo -e "${DIM}      $*${NC}"; }
divider() { echo -e "${DIM}──────────────────────────────────────────────────${NC}"; }

confirm() {
    read -rp "$(echo -e "${YELLOW}[?]${NC} $1 [y/n]: ")" yn
    [[ "$yn" =~ ^[Yy] ]]
}

ask() {
    # ask "prompt" "default_value"  → sets REPLY
    local prompt="$1" default="${2:-}"
    if [[ -n "$default" ]]; then
        read -rp "$(echo -e "${YELLOW}[?]${NC} ${prompt} [${DIM}${default}${NC}]: ")" REPLY
        REPLY="${REPLY:-$default}"
    else
        read -rp "$(echo -e "${YELLOW}[?]${NC} ${prompt}: ")" REPLY
    fi
}

ask_secret() {
    read -rsp "$(echo -e "${YELLOW}[?]${NC} $1 (hidden): ")" REPLY
    echo ""
}

PASSES=0
FAILURES=0

# ── State set during prompts ──────────────────────────────────────────────────
USE_MOCK=true
PI_HOST=""
PI_TOKEN="TEST_TOKEN_LOCAL"
GMAIL_SENDER=""
GMAIL_PASS=""
GMAIL_RECIPIENT=""
TEST_EMAIL=false
# Device name storage — plain strings to avoid set -u issues with empty arrays
MACS_YAML=""       # YAML lines for client_macs block
HOSTS_YAML=""      # YAML lines for client_hostnames block
MAC_COUNT=0
HOST_COUNT=0

# ── Docker compose command detection ─────────────────────────────────────────
if docker compose version &>/dev/null 2>&1; then
    DC="docker compose"
elif command -v docker-compose &>/dev/null; then
    DC="docker-compose"
else
    DC=""
fi

# =============================================================================
# PRE-FLIGHT CHECKS
# =============================================================================
step "Pre-flight Checks"

echo ""
# Docker
if ! command -v docker &>/dev/null; then
    fail "Docker is not installed. Install it from https://docs.docker.com/get-docker/"
    exit 1
fi
info "Docker found: $(docker --version)"

# Docker daemon
if ! docker info &>/dev/null 2>&1; then
    fail "Docker daemon is not running. Start it with:  sudo systemctl start docker"
    exit 1
fi
info "Docker daemon is running"

# Docker Compose
if [[ -z "$DC" ]]; then
    fail "Docker Compose not found. Install docker-compose-plugin or docker-compose."
    exit 1
fi
info "Compose found: $($DC version --short 2>/dev/null || echo 'ok')"

# Project structure
if [[ ! -f "$PROJECT_DIR/scripts/fetcher.py" ]]; then
    fail "Run this script from the pi-hole-analytics project root directory."
    exit 1
fi
info "Project directory: $PROJECT_DIR"

mkdir -p "$PROJECT_DIR/data" "$PROJECT_DIR/logs" "$PROJECT_DIR/reports"

# =============================================================================
# WELCOME
# =============================================================================
clear
echo -e "${BOLD}"
echo "  ╔══════════════════════════════════════════════════════════╗"
echo "  ║      Pi-hole Analytics — Local Docker Test Runner        ║"
echo "  ╚══════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo "  Tests the full stack locally before deploying to your Pi."
echo "  A config/config.test.yaml is written — your real config.yaml is untouched."
echo ""
divider

# =============================================================================
# STEP 1 — PI-HOLE SOURCE
# =============================================================================
step "Step 1 — Pi-hole Data Source"

echo ""
echo "  Option A — Mock Pi-hole (recommended for first test)"
echo "    Starts a local fake Pi-hole that returns 2,000 realistic DNS queries."
echo "    No real Pi-hole needed. Perfect for smoke-testing."
echo ""
echo "  Option B — Real Pi-hole"
echo "    Points the analytics stack at your actual Pi-hole on the network."
echo "    Tests real data but requires your Pi to be reachable."
echo ""

if confirm "Use mock Pi-hole (recommended)?"; then
    USE_MOCK=true
    PI_HOST="http://mock-pihole"   # docker internal hostname
    PI_TOKEN="mock-token-local"
    info "Using mock Pi-hole (container: mock-pihole)"
else
    USE_MOCK=false
    ask "Enter your Pi-hole IP address" "192.168.68.102"
    PI_IP="$REPLY"
    PI_HOST="http://${PI_IP}"
    echo ""
    echo "  How to get your API token:"
    echo "  1. Open http://${PI_IP}/admin in a browser"
    echo "  2. Settings → API / Web interface → Show API token"
    echo ""
    ask "Paste your Pi-hole API token"
    PI_TOKEN="$REPLY"
    info "Using real Pi-hole at $PI_HOST"
fi

# =============================================================================
# STEP 2 — EMAIL TESTING
# =============================================================================
step "Step 2 — Email Report Testing"

echo ""
echo "  Skip this to test everything except email sending."
echo "  To test email you need a Gmail App Password (16 chars)."
echo ""

if confirm "Test email sending?"; then
    TEST_EMAIL=true
    ask "Gmail sender address"
    GMAIL_SENDER="$REPLY"
    ask "Gmail recipient address" "$GMAIL_SENDER"
    GMAIL_RECIPIENT="$REPLY"
    ask_secret "Gmail App Password"
    GMAIL_PASS="$REPLY"
    info "Email testing enabled → $GMAIL_RECIPIENT"
else
    TEST_EMAIL=false
    GMAIL_SENDER="test@example.com"
    GMAIL_RECIPIENT="test@example.com"
    GMAIL_PASS="TEST_APP_PASSWORD"
    warn "Email testing skipped — using placeholder credentials"
fi

# =============================================================================
# STEP 3 — DEVICE NAMES
# =============================================================================
step "Step 3 — Device Identification"

echo ""
if [[ "$USE_MOCK" == true ]]; then
    echo "  The mock Pi-hole returns these 5 test devices:"
    echo "    192.168.68.10  AA:BB:CC:11:22:01  johns-iphone   (Apple)"
    echo "    192.168.68.11  AA:BB:CC:11:22:02  moms-macbook   (Apple)"
    echo "    192.168.68.12  AA:BB:CC:11:22:03  kids-ipad      (Apple)"
    echo "    192.168.68.13  AA:BB:CC:11:22:04  samsung-tv     (Samsung)"
    echo "    192.168.68.14  AA:BB:CC:11:22:05  echo-kitchen   (Amazon)"
    echo ""
    echo "  Auto-detection will label them: iPhone, MacBook, iPad, Samsung Device, Amazon Echo"
    echo "  You can override specific ones with MAC-based names below."
    echo ""
    if confirm "Add custom MAC-based names? (or press n to use auto-detection)"; then
        echo "  Format: paste the MAC and name. Press Enter with empty MAC when done."
        while true; do
            ask "MAC address (e.g. AA:BB:CC:11:22:01)"
            [[ -z "$REPLY" ]] && break
            mac="$REPLY"
            ask "Name for $mac"
            if [[ -n "$REPLY" ]]; then
                MACS_YAML+="  \"${mac}\": \"${REPLY}\""$'\n'
                MAC_COUNT=$((MAC_COUNT+1))
                info "  $mac → $REPLY"
            fi
        done
    fi
else
    echo "  You can map device MACs or hostname substrings to friendly names."
    echo "  Check your Pi-hole admin → Network tab for MACs."
    echo ""
    if confirm "Add MAC-based device names?"; then
        while true; do
            ask "MAC address"
            [[ -z "$REPLY" ]] && break
            mac="$REPLY"
            ask "Friendly name for $mac"
            if [[ -n "$REPLY" ]]; then
                MACS_YAML+="  \"${mac}\": \"${REPLY}\""$'\n'
                MAC_COUNT=$((MAC_COUNT+1))
                info "  $mac → $REPLY"
            fi
        done
    fi
    if confirm "Add hostname-pattern device names? (e.g. 'johns-iphone' → \"John's iPhone\")"; then
        while true; do
            ask "Hostname substring"
            [[ -z "$REPLY" ]] && break
            pat="$REPLY"
            ask "Friendly name for '$pat'"
            if [[ -n "$REPLY" ]]; then
                HOSTS_YAML+="  \"${pat}\": \"${REPLY}\""$'\n'
                HOST_COUNT=$((HOST_COUNT+1))
                info "  $pat → $REPLY"
            fi
        done
    fi
fi

# =============================================================================
# STEP 4 — WRITE TEST CONFIG
# =============================================================================
step "Step 4 — Writing config/config.test.yaml"

echo ""

# Build client_macs block
if [[ $MAC_COUNT -eq 0 ]]; then
    MACS_BLOCK="client_macs:"$'\n  # No custom MAC names — auto-detection will be used'
else
    MACS_BLOCK="client_macs:"$'\n'"${MACS_YAML}"
fi

# Build client_hostnames block
if [[ $HOST_COUNT -eq 0 ]]; then
    HOSTS_BLOCK="client_hostnames:"$'\n  # No hostname patterns — auto-detection will be used'
else
    HOSTS_BLOCK="client_hostnames:"$'\n'"${HOSTS_YAML}"
fi

cat > "$TEST_CONFIG" <<YAML
# Pi-hole Analytics — LOCAL TEST CONFIGURATION
# Generated by test_locally.sh — do not commit this file.
# Your real config/config.yaml is untouched.

pihole:
  host: "${PI_HOST}"
  admin_path: "/admin"
  api_path: "/admin/api.php"
  api_token: "${PI_TOKEN}"

email:
  smtp_server: "smtp.gmail.com"
  smtp_port: 587
  sender_email: "${GMAIL_SENDER}"
  sender_password: "${GMAIL_PASS}"
  recipient_emails:
    - "${GMAIL_RECIPIENT}"
  subject_prefix: "[Pi-hole Analytics TEST]"

${MACS_BLOCK}

${HOSTS_BLOCK}

clients:
  "192.168.68.10": "Test Device A"
  "192.168.68.11": "Test Device B"
  "192.168.68.12": "Test Device C"

rules_update_url: ""

categories:
  adult:
    keywords: [porn, xxx, adult, nsfw]
    domains: []
  ads_tracking:
    keywords: [doubleclick, googlesyndication, analytics, tracking]
    domains: [doubleclick.net, googlesyndication.com, googletagmanager.com]
  social_media:
    keywords: [facebook, instagram, twitter, tiktok, reddit]
    domains: [fbcdn.net, twimg.com]
  streaming:
    keywords: [youtube, netflix, spotify, twitch, hulu]
    domains: [googlevideo.com, ytimg.com, nflxvideo.net, scdn.co]
  gaming:
    keywords: [steam, xbox, roblox, epic, playstation]
    domains: [steampowered.com, xboxlive.com, roblox.com]
  educational:
    keywords: [khanacademy, duolingo, coursera, wikipedia]
    domains: [khanacademy.org, duolingo.com]
  news:
    keywords: [cnn, bbc, guardian, reuters]
    domains: [cnn.com, bbc.com, theguardian.com]
  shopping:
    keywords: [amazon, ebay, bestbuy]
    domains: [amazon.com, ebay.com]
  tech:
    keywords: [github, stackoverflow, cloudflare, google]
    domains: [github.com, stackoverflow.com]
  smart_home:
    keywords: [alexa, ring, nest, echo]
    domains: [amazontrust.com, ring.com]
  finance:
    keywords: [chase, paypal, bank]
    domains: [chase.com, paypal.com]
  health:
    keywords: [webmd, fitness, health]
    domains: [webmd.com, myfitnesspal.com]

reporting:
  data_retention_days: 90
  top_domains_count: 15
  top_clients_count: 5
  report_time: "07:00"

dashboard:
  port: 8080
  host: "0.0.0.0"
YAML

info "config/config.test.yaml written"
note "Pi-hole host:  $PI_HOST"
note "Email sender:  $GMAIL_SENDER"
note "MAC names:     $MAC_COUNT"
note "Host patterns: $HOST_COUNT"

# =============================================================================
# STEP 5 — BUILD DOCKER IMAGES
# =============================================================================
step "Step 5 — Build Docker Images"

echo ""
info "Building analytics image (this takes ~60s on first run) ..."
BUILD_LOG=$(mktemp)
$DC -f "$COMPOSE_FILE" build analytics >"$BUILD_LOG" 2>&1
BUILD_RC=$?
# Always show the last 15 lines so the user sees what happened
tail -15 "$BUILD_LOG"
rm -f "$BUILD_LOG"
if [[ $BUILD_RC -eq 0 ]]; then
    pass "Analytics image built"
else
    fail "Analytics image build failed (exit $BUILD_RC)"
    echo "  Run manually:  $DC -f docker-compose.test.yml build analytics"
    exit 1
fi

if [[ "$USE_MOCK" == true ]]; then
    info "Building mock Pi-hole image ..."
    MOCK_LOG=$(mktemp)
    $DC -f "$COMPOSE_FILE" build mock-pihole >"$MOCK_LOG" 2>&1
    MOCK_RC=$?
    tail -5 "$MOCK_LOG"
    rm -f "$MOCK_LOG"
    if [[ $MOCK_RC -eq 0 ]]; then
        pass "Mock Pi-hole image built"
    else
        fail "Mock Pi-hole build failed (exit $MOCK_RC)"
        exit 1
    fi
fi

# =============================================================================
# STEP 6 — START MOCK PI-HOLE
# =============================================================================
if [[ "$USE_MOCK" == true ]]; then
    step "Step 6 — Start Mock Pi-hole"
    echo ""

    # Stop any previous run
    $DC -f "$COMPOSE_FILE" rm -sf mock-pihole 2>/dev/null || true

    $DC -f "$COMPOSE_FILE" up -d mock-pihole
    info "Mock Pi-hole starting ..."

    # Wait for Docker's own health status (no curl needed on the host)
    MAX=30; n=0
    while [[ $n -lt $MAX ]]; do
        STATUS=$(docker inspect --format='{{.State.Health.Status}}' pihole-mock 2>/dev/null || echo "none")
        [[ "$STATUS" == "healthy" ]] && break
        [[ "$STATUS" == "none"    ]] && break   # no health check configured — proceed anyway
        sleep 2; n=$((n+1))
    done

    FINAL_STATUS=$(docker inspect --format='{{.State.Health.Status}}' pihole-mock 2>/dev/null || echo "unknown")
    if [[ "$FINAL_STATUS" == "healthy" || "$FINAL_STATUS" == "none" ]]; then
        QUERY_COUNT=$(python3 -c "
import urllib.request, json
try:
    r = urllib.request.urlopen('http://localhost:8053/health', timeout=3)
    print(json.loads(r.read())['queries'])
except:
    print('?')
" 2>/dev/null)
        pass "Mock Pi-hole healthy — $QUERY_COUNT fake queries available"
        note "Mock admin UI: http://localhost:8053/admin"
    else
        fail "Mock Pi-hole did not become healthy (status: $FINAL_STATUS)"
        $DC -f "$COMPOSE_FILE" logs mock-pihole
        exit 1
    fi
else
    step "Step 6 — Using Real Pi-hole"
    echo ""
    info "Skipping mock — will query $PI_HOST"
    # Quick connectivity check (python3 is always available on the host)
    if python3 -c "
import urllib.request
try:
    urllib.request.urlopen('${PI_HOST}/admin', timeout=5)
    print('ok')
except:
    exit(1)
" >/dev/null 2>&1; then
        pass "Real Pi-hole reachable at $PI_HOST"
    else
        warn "Could not reach $PI_HOST — fetch may fail"
    fi
fi

# =============================================================================
# STEP 7 — RUN THE FETCHER
# =============================================================================
step "Step 7 — Run Data Fetcher"

echo ""
info "Cleaning previous test data..."
# Use sudo if needed for root-owned files from previous container runs
# Preserve third_party.db as it takes time to download and can be reused
if [[ -f "$PROJECT_DIR/data/analytics.db" ]]; then
    sudo rm -f "$PROJECT_DIR/data/analytics.db" 2>/dev/null || \
    rm -f "$PROJECT_DIR/data/analytics.db" 2>/dev/null || \
    warn "Could not clean analytics database — results may be affected by stale data"
fi
info "Running fetcher inside analytics container ..."
echo ""

if $DC -f "$COMPOSE_FILE" run --rm --no-deps \
      -v "$TEST_CONFIG:/app/config/config.yaml:ro" \
      -v "$PROJECT_DIR/data:/app/data" \
      -v "$PROJECT_DIR/logs:/app/logs" \
      analytics \
      python3 scripts/fetcher.py 2>&1; then
    pass "Fetcher completed without error"
else
    fail "Fetcher exited with an error"
fi

# =============================================================================
# STEP 8 — VERIFY DATABASE
# =============================================================================
step "Step 8 — Verify Database"

echo ""
DB="$PROJECT_DIR/data/analytics.db"

if [[ ! -f "$DB" ]]; then
    fail "analytics.db not created — fetcher may have failed silently"
else
    QUERY_COUNT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM queries;" 2>/dev/null || echo 0)
    CLIENT_COUNT=$(sqlite3 "$DB" "SELECT COUNT(DISTINCT client_ip) FROM queries;" 2>/dev/null || echo 0)
    SUMMARY_COUNT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM daily_summary;" 2>/dev/null || echo 0)
    CATEGORY_COUNT=$(sqlite3 "$DB" "SELECT COUNT(DISTINCT category) FROM queries;" 2>/dev/null || echo 0)
    DEVICE_COUNT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM device_registry;" 2>/dev/null || echo 0)

    # Third-party database statistics
    TP_DB="$PROJECT_DIR/data/third_party.db"
    if [[ -f "$TP_DB" ]]; then
        TP_DOMAIN_COUNT=$(sqlite3 "$TP_DB" "SELECT COUNT(*) FROM domains;" 2>/dev/null || echo 0)
        TP_CATEGORY_COUNT=$(sqlite3 "$TP_DB" "SELECT COUNT(DISTINCT category) FROM domains;" 2>/dev/null || echo 0)
        TP_COVERAGE="$TP_DOMAIN_COUNT domains across $TP_CATEGORY_COUNT categories"
    else
        TP_COVERAGE="Not available (run 'python3 scripts/downloader.py' to download ~3M domains)"
    fi

    echo ""
    echo "  Database contents:"
    echo -e "  ${CYAN}Queries stored:${NC}       $QUERY_COUNT"
    echo -e "  ${CYAN}Unique clients:${NC}       $CLIENT_COUNT"
    echo -e "  ${CYAN}Daily summary rows:${NC}   $SUMMARY_COUNT"
    echo -e "  ${CYAN}Categories assigned:${NC}  $CATEGORY_COUNT"
    echo -e "  ${CYAN}Devices in registry:${NC}  $DEVICE_COUNT"
    echo -e "  ${CYAN}Third-party coverage:${NC} $TP_COVERAGE"
    echo ""

    # Show category breakdown
    echo "  Category breakdown:"
    sqlite3 "$DB" \
        "SELECT '  ' || category, COUNT(*) as n FROM queries GROUP BY category ORDER BY n DESC LIMIT 10;" \
        2>/dev/null | column -t || true
    echo ""

    # Show third-party categorization effectiveness
    if [[ -f "$TP_DB" && $CATEGORY_COUNT -gt 0 ]]; then
        echo "  Third-party categorization:"
        echo -e "  ${CYAN}Database coverage:${NC}      ${TP_DOMAIN_COUNT} domains in ${TP_CATEGORY_COUNT} categories"
        echo -e "  ${CYAN}Categorization boost:${NC}   Third-party data enhances config rules"
        echo ""
    fi

    # Show device names resolved
    echo "  Device names resolved:"
    sqlite3 "$DB" \
        "SELECT '  ' || client_ip, client_name FROM queries GROUP BY client_ip LIMIT 10;" \
        2>/dev/null | column -t || true
    echo ""

    [[ "$QUERY_COUNT" -gt 0 ]] && pass "Queries stored: $QUERY_COUNT" \
                                || fail "No queries stored — check fetcher log"
    [[ "$SUMMARY_COUNT" -gt 0 ]] && pass "Daily summary populated" \
                                  || fail "Daily summary is empty"
    [[ "$CATEGORY_COUNT" -gt 0 ]] && pass "Categories assigned ($CATEGORY_COUNT distinct)" \
                                   || fail "No categories assigned"
    [[ "$DEVICE_COUNT" -gt 0 ]] && pass "Device registry populated ($DEVICE_COUNT devices)" \
                                 || warn "Device registry empty (Pi-hole network API may not be available)"
fi

# =============================================================================
# STEP 9 — RUN UNIT TESTS
# =============================================================================
step "Step 9 — Run Unit Test Suite"

echo ""
info "Running pytest inside analytics container ..."
echo ""

if $DC -f "$COMPOSE_FILE" run --rm --no-deps \
      -v "$TEST_CONFIG:/app/config/config.yaml:ro" \
      -v "$PROJECT_DIR/tests:/app/tests" \
      analytics \
      python3 -m pytest tests/ -q --tb=short 2>&1; then
    pass "All unit tests passed"
else
    fail "Some unit tests failed — see output above"
fi

# =============================================================================
# STEP 10 — START DASHBOARD
# =============================================================================
step "Step 10 — Start Dashboard"

echo ""
# Stop previous dashboard container if any
$DC -f "$COMPOSE_FILE" rm -sf analytics 2>/dev/null || true

info "Starting dashboard container ..."
$DC -f "$COMPOSE_FILE" up -d --no-deps analytics

# Wait for dashboard to respond — use python3 (no curl dependency on host)
MAX=20; n=0
while [[ $n -lt $MAX ]]; do
    if python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/', timeout=1)" >/dev/null 2>&1; then
        break
    fi
    sleep 1; n=$((n+1))
done

if python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/', timeout=2)" >/dev/null 2>&1; then
    pass "Dashboard is running at http://localhost:8080"
    # Quick API smoke tests
    echo ""
    echo "  Smoke-testing API endpoints:"
    endpoints=("/api/summary" "/api/compare" "/api/clients" "/api/categories" "/api/domains" "/api/trend?days=7")
    for ep in "${endpoints[@]}"; do
        STATUS=$(python3 -c "
import urllib.request
try:
    r = urllib.request.urlopen('http://localhost:8080${ep}', timeout=3)
    print(r.status)
except urllib.error.HTTPError as e:
    print(e.code)
except:
    print(0)
" 2>/dev/null)
        if [[ "$STATUS" == "200" ]]; then
            pass "  GET $ep → 200"
        else
            fail "  GET $ep → $STATUS"
        fi
    done
else
    fail "Dashboard did not start in time"
    $DC -f "$COMPOSE_FILE" logs analytics
fi

# =============================================================================
# STEP 11 — TEST EMAIL (optional)
# =============================================================================
if [[ "$TEST_EMAIL" == true ]]; then
    step "Step 11 — Send Test Email Report"
    echo ""
    info "Sending daily report to $GMAIL_RECIPIENT ..."
    if $DC -f "$COMPOSE_FILE" run --rm --no-deps \
          -v "$TEST_CONFIG:/app/config/config.yaml:ro" \
          -v "$PROJECT_DIR/data:/app/data" \
          -v "$PROJECT_DIR/logs:/app/logs" \
          -v "$PROJECT_DIR/reports:/app/reports" \
          analytics \
          python3 scripts/reporter.py --period daily 2>&1; then
        pass "Email sent — check $GMAIL_RECIPIENT inbox (and spam folder)"
    else
        fail "Email sending failed — check logs/reporter.log"
    fi
else
    step "Step 11 — Email Test Skipped"
    echo ""
    warn "To test email later, re-run test_locally.sh and answer 'y' to email testing."
fi

# =============================================================================
# SUMMARY
# =============================================================================
echo ""
divider
echo ""
echo -e "${BOLD}  Test Summary${NC}"
echo ""
echo -e "  ${GREEN}Passed:${NC}  $PASSES"
[[ $FAILURES -gt 0 ]] && echo -e "  ${RED}Failed:${NC}  $FAILURES" \
                       || echo -e "  ${DIM}Failed:  0${NC}"
echo ""
divider

if [[ $FAILURES -eq 0 ]]; then
    echo -e "\n  ${BOLD}${GREEN}All checks passed — ready to deploy!${NC}"
    echo ""
    echo -e "  ${BOLD}Dashboard:${NC}  ${CYAN}http://localhost:8080${NC}  (running now)"
    if [[ "$USE_MOCK" == true ]]; then
        echo -e "  ${BOLD}Mock admin:${NC} ${CYAN}http://localhost:8053/admin${NC}"
    fi
else
    echo -e "\n  ${BOLD}${YELLOW}Some checks failed — review the output above.${NC}"
    echo ""
    echo "  Useful debugging commands:"
    echo -e "  ${DIM}# Fetcher logs${NC}"
    echo "  cat logs/fetcher.log"
    echo -e "  ${DIM}# Dashboard logs${NC}"
    echo "  $DC -f docker-compose.test.yml logs analytics"
    echo -e "  ${DIM}# Inspect database${NC}"
    echo "  sqlite3 data/analytics.db '.tables'"
fi

echo ""
divider
echo ""
echo -e "  ${BOLD}Useful commands while containers are running:${NC}"
echo ""
echo -e "  ${DIM}# Tail fetcher log${NC}"
echo "  tail -f logs/fetcher.log"
echo ""
echo -e "  ${DIM}# Live dashboard container logs${NC}"
echo "  $DC -f docker-compose.test.yml logs -f analytics"
echo ""
echo -e "  ${DIM}# Open a shell inside the analytics container${NC}"
echo "  docker exec -it pihole-analytics bash"
echo ""
echo -e "  ${DIM}# Query the database directly${NC}"
echo "  sqlite3 data/analytics.db 'SELECT client_name, COUNT(*) FROM queries GROUP BY client_name;'"
echo ""
echo -e "  ${DIM}# Inspect generated HTML report${NC}"
echo "  ls reports/"
echo ""
divider
echo ""

# =============================================================================
# CLEANUP PROMPT
# =============================================================================
if confirm "Stop and remove all test containers now?"; then
    echo ""
    $DC -f "$COMPOSE_FILE" down --remove-orphans
    info "Containers stopped and removed"
    info "Cleaning up test artifacts..."
    # Preserve third_party.db but remove other test data
    rm -f "$PROJECT_DIR/data/analytics.db"
    rm -rf "$PROJECT_DIR/logs" "$PROJECT_DIR/reports" "$TEST_CONFIG"
    info "Test data, logs, reports, and config cleaned up"
    info "Third-party database preserved for reuse"
else
    echo ""
    info "Containers left running. Stop them later with:"
    echo "  $DC -f docker-compose.test.yml down"
fi

echo ""
echo -e "${BOLD}  Done.${NC}  Deploy guide: ${CYAN}DEPLOYMENT.md${NC}"
echo ""

exit 0
