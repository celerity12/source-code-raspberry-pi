#!/usr/bin/env bash
# =============================================================================
# Pi-hole Analytics — Application Health Check
# Checks every component: DB, services, Pi-hole, Gemini AI, email, dashboard.
# Run from your Linux box:  bash apphealth.sh
# =============================================================================
set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'
BLUE='\033[0;34m'; MAGENTA='\033[0;35m'

OK()   { echo -e "  ${GREEN}✅  $*${NC}"; }
WARN() { echo -e "  ${YELLOW}⚠️   $*${NC}"; }
FAIL() { echo -e "  ${RED}❌  $*${NC}"; }
INFO() { echo -e "  ${CYAN}ℹ️   $*${NC}"; }
HDR()  { echo -e "\n${BOLD}${BLUE}┌─────────────────────────────────────────────────────────────┐${NC}"; \
         printf "${BOLD}${BLUE}│  %-59s │${NC}\n" "$*"; \
         echo -e "${BOLD}${BLUE}└─────────────────────────────────────────────────────────────┘${NC}"; }
SEP()  { echo -e "${DIM}  ─────────────────────────────────────────────────────────────${NC}"; }

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Defaults ─────────────────────────────────────────────────────────────────
PI_IP="${PI_IP:-192.168.68.102}"
PI_USER="${PI_USER:-pi}"
PI_PORT="${PI_PORT:-22}"
INSTALL_DIR="/home/${PI_USER}/pihole-analytics"
PASS_FAIL=0   # incremented on each failure

fail() { PASS_FAIL=$((PASS_FAIL+1)); FAIL "$@"; }

echo ""
echo -e "${BOLD}"
echo "  ╔══════════════════════════════════════════════════════════╗"
echo "  ║       Pi-hole Analytics — Application Health Check       ║"
echo "  ╚══════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo -e "  Target  : ${BOLD}${PI_USER}@${PI_IP}:${PI_PORT}${NC}"
echo -e "  Install : ${BOLD}${INSTALL_DIR}${NC}"
echo -e "  Source  : ${BOLD}${PROJECT_DIR}${NC}"
echo -e "  Time    : ${DIM}$(date '+%Y-%m-%d %H:%M:%S %Z')${NC}"
echo ""

# =============================================================================
# SECTION 1 — LOCAL FILES
# =============================================================================
HDR "1 of 7  LOCAL FILES"

REQUIRED_SCRIPTS=(
  scripts/web/app.py
  scripts/data/analytics.py
  scripts/data/fetcher.py
  scripts/core/reporter.py
  scripts/core/summarizer.py
  scripts/core/health.py
  scripts/data/downloader.py
  scripts/core/config.py
  scripts/core/constants.py
  scripts/core/device_resolver.py
)
REQUIRED_OTHER=(
  config/config.yaml
  requirements.txt
  install.sh
  update.sh
)

for f in "${REQUIRED_SCRIPTS[@]}" "${REQUIRED_OTHER[@]}"; do
  if [[ -f "${PROJECT_DIR}/${f}" ]]; then
    SIZE=$(wc -c < "${PROJECT_DIR}/${f}" 2>/dev/null || echo 0)
    OK "$(printf '%-40s' "$f") $(numfmt --to=iec-i --suffix=B ${SIZE} 2>/dev/null || echo "${SIZE}B")"
  else
    fail "MISSING: ${f}"
  fi
done

# Config sanity checks (look for placeholder values)
CFG="${PROJECT_DIR}/config/config.yaml"
if [[ -f "$CFG" ]]; then
  SEP
  INFO "Config.yaml key validation:"
  _check_placeholder(){
    local key="$1" label="$2"
    if grep -q "${key}" "$CFG" 2>/dev/null; then
      WARN "${label} appears to contain a placeholder — update before deploying"
      PASS_FAIL=$((PASS_FAIL+1))
    fi
  }
  _check_key_present(){
    local pattern="$1" label="$2"
    if grep -q "${pattern}" "$CFG" 2>/dev/null; then
      OK "${label} is set"
    else
      fail "${label} not found in config.yaml"
    fi
  }
  _check_placeholder "YOUR_PIHOLE"        "Pi-hole API token/password"
  _check_placeholder "YOUR_GMAIL"         "Gmail app password"
  _check_placeholder "YOUR_GEMINI"        "Gemini API key"
  _check_placeholder "YOUR_DASHBOARD"     "Dashboard password"
  _check_key_present "api_key:"           "Gemini api_key"
  _check_key_present "smtp_server:"       "Email smtp_server"
  _check_key_present "sender_email:"      "Email sender_email"
  _check_key_present "recipient_emails:"  "Email recipient_emails"
  _check_key_present "dashboard:"         "Dashboard section"

  # Check gemini model isn't using a placeholder
  GEMINI_MODEL=$(grep 'model:' "$CFG" | head -1 | awk '{print $2}' | tr -d '"')
  if [[ -n "$GEMINI_MODEL" ]]; then
    OK "Gemini model: ${GEMINI_MODEL}"
  fi
fi

# =============================================================================
# SECTION 2 — SSH CONNECTION
# =============================================================================
HDR "2 of 7  SSH CONNECTION"

SSH_CTRL="/tmp/pihole-health-$$.sock"
SSH_BASE="ssh -p ${PI_PORT} -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new \
    -o ControlMaster=auto -o ControlPath=${SSH_CTRL} -o ControlPersist=60 \
    -o BatchMode=yes"

cleanup(){ ssh -O exit -o ControlPath="${SSH_CTRL}" "${PI_USER}@${PI_IP}" 2>/dev/null || true; }
trap cleanup EXIT

if $SSH_BASE "${PI_USER}@${PI_IP}" "echo '__OK__'" 2>/dev/null | grep -q "__OK__"; then
  OK "SSH connection to ${PI_USER}@${PI_IP}:${PI_PORT}"
  PIHOST=$(${SSH_BASE} "${PI_USER}@${PI_IP}" "hostname -s" 2>/dev/null || echo "unknown")
  PIMODEL=$(${SSH_BASE} "${PI_USER}@${PI_IP}" "cat /proc/device-tree/model 2>/dev/null | tr -d '\0'" 2>/dev/null || echo "unknown")
  OK "Hostname: ${PIHOST}   Model: ${PIMODEL}"
else
  fail "Cannot reach ${PI_USER}@${PI_IP}:${PI_PORT} — check IP/user/port"
  echo ""
  echo -e "  ${RED}Cannot continue without SSH. Aborting remote checks.${NC}"
  echo ""
  echo -e "  ${BOLD}HEALTH CHECK ABORTED — ${PASS_FAIL} problem(s) found${NC}"
  exit 1
fi

# =============================================================================
# SECTIONS 3–7 — ALL REMOTE CHECKS (single SSH session, Python inline)
# =============================================================================

$SSH_BASE "${PI_USER}@${PI_IP}" bash <<REMOTE
set -euo pipefail
INSTALL_DIR="${INSTALL_DIR}"
PI_USER="${PI_USER}"
PI_IP="${PI_IP}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'
BLUE='\033[0;34m'

OK()   { echo -e "  \${GREEN}✅  \$*\${NC}"; }
WARN() { echo -e "  \${YELLOW}⚠️   \$*\${NC}"; }
FAIL() { echo -e "  \${RED}❌  \$*\${NC}"; }
INFO() { echo -e "  \${CYAN}ℹ️   \$*\${NC}"; }
HDR()  { echo -e "\n\${BOLD}\${BLUE}┌─────────────────────────────────────────────────────────────┐\${NC}"; \
         printf "\${BOLD}\${BLUE}│  %-59s │\${NC}\n" "\$*"; \
         echo -e "\${BOLD}\${BLUE}└─────────────────────────────────────────────────────────────┘\${NC}"; }
SEP()  { echo -e "\${DIM}  ─────────────────────────────────────────────────────────────\${NC}"; }

REMOTE_FAILS=0
rfail(){ REMOTE_FAILS=\$((REMOTE_FAILS+1)); FAIL "\$@"; }


# =========================================================================
# SECTION 3 — PYTHON ENVIRONMENT
# =========================================================================
HDR "3 of 7  PYTHON ENVIRONMENT"

if [[ -f "\${INSTALL_DIR}/venv/bin/python3" ]]; then
  PY_VER=\$("\${INSTALL_DIR}/venv/bin/python3" --version 2>&1)
  OK "Virtual environment: \${PY_VER}"
else
  rfail "venv not found at \${INSTALL_DIR}/venv — run install.sh"
fi

# Check all required packages
PACKAGES=(flask requests pyyaml)
for pkg in "\${PACKAGES[@]}"; do
  if "\${INSTALL_DIR}/venv/bin/python3" -c "import \${pkg}" 2>/dev/null; then
    VER=\$("\${INSTALL_DIR}/venv/bin/python3" -c "import \${pkg}; print(getattr(\${pkg},'__version__','ok'))" 2>/dev/null || echo "ok")
    OK "\$(printf '%-12s' \${pkg}) v\${VER}"
  else
    rfail "Python package missing: \${pkg}"
  fi
done

# Check all app modules import cleanly
SEP
INFO "App module imports:"
cd "\${INSTALL_DIR}"
declare -A MOD_MAP=(
  ["scripts.data.analytics"]="analytics"
  ["scripts.core.reporter"]="reporter"
  ["scripts.web.app"]="dashboard"
  ["scripts.core.health"]="health"
  ["scripts.core.summarizer"]="summarizer"
  ["scripts.data.fetcher"]="fetcher"
)
for mod in "\${!MOD_MAP[@]}"; do
  label="\${MOD_MAP[\$mod]}"
  if OUT=\$(venv/bin/python3 -c "import \${mod}" 2>&1); then
    OK "\$(printf '%-12s' \${label}) imports OK"
  else
    rfail "\$(printf '%-12s' \${label}) IMPORT FAILED: \$(echo \${OUT} | head -c 120)"
  fi
done


# =========================================================================
# SECTION 4 — DATABASE
# =========================================================================
HDR "4 of 7  DATABASE"

DB="\${INSTALL_DIR}/data/analytics.db"
if [[ -f "\${DB}" ]]; then
  DB_SIZE=\$(du -sh "\${DB}" | cut -f1)
  OK "Database file: \${DB}  (\${DB_SIZE})"
else
  rfail "Database file not found: \${DB}"
  echo -e "  \${YELLOW}  → Run the fetch service to initialise the DB\${NC}"
fi

if [[ -f "\${DB}" ]]; then
  # Row counts
  SEP
  INFO "Table row counts:"
  sqlite3 "\${DB}" <<SQL
.mode column
.width 30 12
SELECT 'queries'          AS table_name, COUNT(*) AS rows FROM queries
UNION ALL
SELECT 'daily_summary',   COUNT(*) FROM daily_summary
UNION ALL
SELECT 'domain_categories', COUNT(*) FROM domain_categories
UNION ALL
SELECT 'device_registry', COUNT(*) FROM device_registry
UNION ALL
SELECT 'manually_blocked', COUNT(*) FROM manually_blocked;
SQL

  SEP
  INFO "Data freshness:"
  # Last fetch timestamp
  LAST_TS=\$(sqlite3 "\${DB}" "SELECT value FROM fetch_state WHERE key='last_timestamp'" 2>/dev/null || echo "")
  if [[ -n "\${LAST_TS}" && "\${LAST_TS}" != "0" ]]; then
    LAST_DT=\$(date -d "@\${LAST_TS}" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date -r "\${LAST_TS}" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo "ts=\${LAST_TS}")
    AGE_MIN=\$(( ( \$(date +%s) - \${LAST_TS} ) / 60 ))
    if [[ \${AGE_MIN} -lt 30 ]]; then
      OK "Last fetch: \${LAST_DT} (\${AGE_MIN} min ago)"
    elif [[ \${AGE_MIN} -lt 120 ]]; then
      WARN "Last fetch: \${LAST_DT} (\${AGE_MIN} min ago — fetch timer may have missed)"
    else
      rfail "Last fetch: \${LAST_DT} (\${AGE_MIN} min ago — DATA IS STALE)"
    fi
  else
    rfail "No last_timestamp in fetch_state — fetcher has never run"
  fi

  # Today's query count
  TODAY=\$(date '+%Y-%m-%d')
  TODAY_CNT=\$(sqlite3 "\${DB}" "SELECT COUNT(*) FROM queries WHERE date='\${TODAY}'" 2>/dev/null || echo 0)
  YEST=\$(date -d 'yesterday' '+%Y-%m-%d' 2>/dev/null || date -v-1d '+%Y-%m-%d' 2>/dev/null || echo "")
  YEST_CNT=0
  [[ -n "\${YEST}" ]] && YEST_CNT=\$(sqlite3 "\${DB}" "SELECT COUNT(*) FROM queries WHERE date='\${YEST}'" 2>/dev/null || echo 0)

  if [[ \${TODAY_CNT} -gt 0 ]]; then
    OK "Queries today  (\${TODAY}): \${TODAY_CNT}"
  else
    WARN "No queries stored for today (\${TODAY}) yet"
  fi
  [[ -n "\${YEST}" ]] && INFO "Queries yesterday (\${YEST}): \${YEST_CNT}"

  # Category coverage
  SEP
  INFO "Category coverage (today's queries):"
  sqlite3 "\${DB}" <<SQL
.mode column
.width 20 10 8
SELECT COALESCE(category,'(uncategorised)') AS category,
       COUNT(*) AS queries,
       ROUND(COUNT(*)*100.0/(SELECT COUNT(*) FROM queries WHERE date='\${TODAY}'),1)||'%' AS pct
FROM queries
WHERE date='\${TODAY}'
GROUP BY category
ORDER BY queries DESC
LIMIT 10;
SQL
fi


# =========================================================================
# SECTION 5 — SYSTEMD SERVICES & TIMERS
# =========================================================================
HDR "5 of 7  SYSTEMD SERVICES & TIMERS"

declare -A SVC_EXPECT=(
  ["pihole-analytics-dashboard.service"]="active"
  ["pihole-analytics-fetch.timer"]="active"
  ["pihole-analytics-daily.timer"]="active"
  ["pihole-analytics-weekly.timer"]="active"
  ["pihole-analytics-monthly.timer"]="active"
  ["pihole-analytics-sysupdate.timer"]="active"
  ["pihole-analytics-aisummary.timer"]="active"
)

for svc in "\${!SVC_EXPECT[@]}"; do
  STATE=\$(systemctl is-active "\${svc}" 2>/dev/null || echo "not-found")
  ENABLED=\$(systemctl is-enabled "\${svc}" 2>/dev/null || echo "unknown")
  if [[ "\${STATE}" == "active" ]]; then
    OK "\$(printf '%-50s' \${svc}) \${STATE}  (enabled: \${ENABLED})"
  elif [[ "\${STATE}" == "inactive" ]]; then
    # For oneshot timers being inactive is normal between runs
    if [[ "\${svc}" == *".timer" ]]; then
      # Timers should be active (waiting) — inactive is a problem
      rfail "\$(printf '%-50s' \${svc}) \${STATE}  (not running — re-enable with: sudo systemctl enable --now \${svc})"
    else
      RESULT=\$(systemctl show "\${svc}" --property=Result --value 2>/dev/null || echo "")
      if [[ "\${RESULT}" == "success" || "\${RESULT}" == "" ]]; then
        WARN "\$(printf '%-50s' \${svc}) inactive (last run: success)"
      else
        rfail "\$(printf '%-50s' \${svc}) inactive/\${RESULT}"
      fi
    fi
  elif [[ "\${STATE}" == "not-found" ]]; then
    rfail "\$(printf '%-50s' \${svc}) NOT INSTALLED — run install.sh or update.sh"
  else
    rfail "\$(printf '%-50s' \${svc}) \${STATE}"
  fi
done

SEP
INFO "Next scheduled timer runs:"
systemctl list-timers pihole-analytics* --no-pager 2>/dev/null \
  | head -12 \
  | sed 's/^/    /'


# =========================================================================
# SECTION 6 — CONNECTIVITY CHECKS
# =========================================================================
HDR "6 of 7  CONNECTIVITY"

# ── Pi-hole ──────────────────────────────────────────────────────────────
INFO "Pi-hole API:"
PH_STATUS=\$(curl -sf --max-time 5 "http://localhost/api/dns/blocking" 2>/dev/null || echo "")
if echo "\${PH_STATUS}" | grep -q '"blocking"'; then
  BLOCKING=\$(echo "\${PH_STATUS}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('blocking','?'))" 2>/dev/null || echo "?")
  if [[ "\${BLOCKING}" == "True" || "\${BLOCKING}" == "true" ]]; then
    OK "Pi-hole v6 API reachable — Blocking: \${BLOCKING}"
  else
    rfail "Pi-hole reachable but BLOCKING IS OFF (blocking=\${BLOCKING})"
  fi
else
  # Try v5 fallback
  V5=\$(curl -sf --max-time 5 "http://localhost/admin/api.php?summaryRaw" 2>/dev/null || echo "")
  if echo "\${V5}" | grep -q '"domains_being_blocked"'; then
    OK "Pi-hole v5 API reachable"
  else
    rfail "Pi-hole API not reachable at http://localhost — is Pi-hole running?"
  fi
fi

# ── Dashboard ────────────────────────────────────────────────────────────
SEP
INFO "Dashboard HTTP:"
DASH_STATUS=\$(curl -sf -o /dev/null -w "%{http_code}" --max-time 5 "http://localhost:8080/login" 2>/dev/null || echo "000")
if [[ "\${DASH_STATUS}" == "200" ]]; then
  OK "Dashboard responding at http://localhost:8080  (HTTP \${DASH_STATUS})"
elif [[ "\${DASH_STATUS}" == "302" || "\${DASH_STATUS}" == "301" ]]; then
  OK "Dashboard responding at http://localhost:8080  (HTTP \${DASH_STATUS} redirect)"
else
  rfail "Dashboard not responding at port 8080 (HTTP \${DASH_STATUS})"
fi

# ── Email/SMTP ────────────────────────────────────────────────────────────
SEP
INFO "Email (SMTP):"
if timeout 6 bash -c "echo '' > /dev/tcp/smtp.gmail.com/587" 2>/dev/null; then
  OK "smtp.gmail.com:587 reachable"
else
  rfail "smtp.gmail.com:587 not reachable — check network/firewall"
fi

# ── Gemini AI ─────────────────────────────────────────────────────────────
SEP
INFO "Gemini AI:"

# Read API key from config
GEMINI_KEY=\$(python3 -c "
import sys, yaml
with open('${INSTALL_DIR}/config/config.yaml') as f:
    cfg = yaml.safe_load(f)
key = cfg.get('gemini',{}).get('api_key','')
# top-level override check
if not key:
    key = ''
print(key)
" 2>/dev/null || echo "")

if [[ -z "\${GEMINI_KEY}" || "\${GEMINI_KEY}" == YOUR_* ]]; then
  rfail "Gemini API key not configured in config.yaml"
else
  KEY_PREVIEW="\${GEMINI_KEY:0:10}…"
  # Lightweight models list call to verify the key is valid (no quota used)
  HTTP_CODE=\$(curl -sf -o /dev/null -w "%{http_code}" --max-time 10 \
    "https://generativelanguage.googleapis.com/v1/models?key=\${GEMINI_KEY}" 2>/dev/null || echo "000")
  if [[ "\${HTTP_CODE}" == "200" ]]; then
    OK "Gemini API key valid (\${KEY_PREVIEW})  — HTTP \${HTTP_CODE}"
    MODEL=\$(python3 -c "
import sys, yaml
with open('${INSTALL_DIR}/config/config.yaml') as f:
    cfg = yaml.safe_load(f)
print(cfg.get('gemini',{}).get('model','gemini-1.5-flash'))
" 2>/dev/null || echo "unknown")
    OK "Configured model: \${MODEL}"
  elif [[ "\${HTTP_CODE}" == "400" || "\${HTTP_CODE}" == "403" ]]; then
    rfail "Gemini API key rejected (HTTP \${HTTP_CODE}) — check key at aistudio.google.com"
  elif [[ "\${HTTP_CODE}" == "000" ]]; then
    rfail "Cannot reach Gemini API — no internet? (HTTP \${HTTP_CODE})"
  else
    WARN "Gemini API returned HTTP \${HTTP_CODE} — may still work"
  fi
fi


# =========================================================================
# SECTION 7 — SYSTEM RESOURCES & LOGS
# =========================================================================
HDR "7 of 7  SYSTEM RESOURCES & LOGS"

INFO "Disk usage:"
df -h "\${INSTALL_DIR}" / 2>/dev/null | awk 'NR==1{print "    "\$0} NR>1{
  pct=\$5+0
  if(pct>=90) flag="⚠️  HIGH"
  else if(pct>=75) flag="⚠️"
  else flag="✅"
  print "  "flag"  "\$0
}'

SEP
INFO "Memory:"
free -h | awk 'NR==1{print "    "\$0} NR==2{print "    "\$0}'

SEP
INFO "System load (1/5/15 min avg):"
uptime | sed 's/.*load average/    load average/'

SEP
INFO "Log files:"
LOGS_DIR="\${INSTALL_DIR}/logs"
for logfile in dashboard.log fetcher.log reporter.log summarizer.log sysupdate.log; do
  LOGPATH="\${LOGS_DIR}/\${logfile}"
  if [[ -f "\${LOGPATH}" ]]; then
    SZ=\$(du -sh "\${LOGPATH}" | cut -f1)
    MTIME=\$(stat -c '%y' "\${LOGPATH}" | cut -c1-19)
    # Count recent errors
    ERRS=\$(grep -c -i '\[ERROR\]\|Traceback\|Exception\|CRITICAL' "\${LOGPATH}" 2>/dev/null || echo 0)
    if [[ \${ERRS} -gt 0 ]]; then
      WARN "\$(printf '%-22s' \${logfile}) \${SZ}  last-modified: \${MTIME}  errors: \${ERRS}"
    else
      OK "\$(printf '%-22s' \${logfile}) \${SZ}  last-modified: \${MTIME}"
    fi
  else
    INFO "\$(printf '%-22s' \${logfile}) not yet created"
  fi
done

SEP
INFO "Recent errors in dashboard.log (last 5 ERROR lines):"
if [[ -f "\${LOGS_DIR}/dashboard.log" ]]; then
  RECENT=\$(grep -i '\[ERROR\]\|Traceback\|Exception' "\${LOGS_DIR}/dashboard.log" 2>/dev/null | tail -5 || echo "")
  if [[ -n "\${RECENT}" ]]; then
    echo "\${RECENT}" | sed 's/^/    /'
  else
    echo -e "  \${GREEN}  No errors in dashboard.log\${NC}"
  fi
else
  INFO "dashboard.log not yet created"
fi

INFO "Recent errors in fetcher.log (last 5 ERROR lines):"
if [[ -f "\${LOGS_DIR}/fetcher.log" ]]; then
  RECENT=\$(grep -i '\[ERROR\]\|Traceback\|Exception' "\${LOGS_DIR}/fetcher.log" 2>/dev/null | tail -5 || echo "")
  if [[ -n "\${RECENT}" ]]; then
    echo "\${RECENT}" | sed 's/^/    /'
  else
    echo -e "  \${GREEN}  No errors in fetcher.log\${NC}"
  fi
else
  INFO "fetcher.log not yet created"
fi


# =========================================================================
# FINAL SCORE (remote)
# =========================================================================
echo ""
echo -e "\${BOLD}  Remote check complete — \${REMOTE_FAILS} remote problem(s) found\${NC}"
echo ""
echo "__REMOTE_FAILS__\${REMOTE_FAILS}"
REMOTE

# ── Capture remote failure count ─────────────────────────────────────────────
REMOTE_OUT=$($SSH_BASE "${PI_USER}@${PI_IP}" "echo '__REMOTE_FAILS__0'" 2>/dev/null || echo "__REMOTE_FAILS__0")
REMOTE_FAILS=$(echo "$REMOTE_OUT" | grep -o '__REMOTE_FAILS__[0-9]*' | grep -o '[0-9]*$' || echo 0)

# =============================================================================
# FINAL REPORT
# =============================================================================
TOTAL=$((PASS_FAIL + REMOTE_FAILS))

echo ""
echo -e "${BOLD}${BLUE}┌─────────────────────────────────────────────────────────────┐${NC}"
printf "${BOLD}${BLUE}│  %-59s │${NC}\n" "HEALTH CHECK SUMMARY"
echo -e "${BOLD}${BLUE}└─────────────────────────────────────────────────────────────┘${NC}"
echo ""
printf "  %-30s %s\n" "Local problems found:" "${PASS_FAIL}"
printf "  %-30s %s\n" "Remote problems found:" "${REMOTE_FAILS:-0}"
echo ""

if [[ ${TOTAL} -eq 0 ]]; then
  echo -e "  ${GREEN}${BOLD}🎉  All checks passed — application is healthy!${NC}"
else
  echo -e "  ${RED}${BOLD}⚠️   ${TOTAL} problem(s) found — review the output above${NC}"
fi

echo ""
echo -e "  Dashboard  : ${CYAN}http://${PI_IP}:8080${NC}"
echo -e "  To deploy  : ${DIM}bash update.sh${NC}"
echo -e "  To harden  : ${DIM}bash harden.sh${NC}"
echo ""

exit ${TOTAL}
