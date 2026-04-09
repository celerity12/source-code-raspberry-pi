# Pi-hole Telegram Bot (pihole-mcp-server)

Monitor and control your home network from **Telegram**. Ask questions, get security alerts, and block domains — all from your phone.

> Deploy [pi_hole_web_survillance](../pi_hole_web_survillance) first — this bot connects to its dashboard.

---

## Telegram Commands

| Command | What you get |
|---|---|
| `/status` | Network overview — queries, blocked %, active devices |
| `/alerts` | Security alerts today (adult content, VPN, crypto) |
| `/health` | System health — disk, RAM, CPU, temperature |
| `/devices` | All active devices today with query counts |
| `/block domain.com` | Block a domain via Pi-hole |
| `/unblock domain.com` | Unblock a domain |
| `/report` | Trigger daily email report |
| `/help` | Show all commands |

You can also ask anything in plain English:

> "Who was online last night?"
> "What was the kids' tablet doing this week?"
> "Show me all gaming sites visited today."
> "Block YouTube for now."

---

## How It Works

```
Your Telegram message
        ↓
  gemini_agent.py  (polls Telegram every 3s)
        ↓
  Gemini AI  (decides which data to fetch)
        ↓
  mcp/server.py  (29 tools — Pi-hole data + Telegram)
        ↓
  Pi-hole Analytics dashboard  (:8080)
        ↓
  Reply sent back to your Telegram
```

---

## Setup

### Prerequisites

| Requirement | How to get it |
|---|---|
| Pi-hole Analytics dashboard running | Deploy `1_analytics` project first |
| Gemini API key | [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) — free |
| Telegram bot token | Message [@BotFather](https://t.me/BotFather) → `/newbot` |
| Your Telegram chat ID | Message [@userinfobot](https://t.me/userinfobot) |

### 1. Install dependencies

```bash
cd pihole-mcp-server
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

If pip is blocked by PEP 668:
```bash
pip3 install --break-system-packages -r requirements.txt
```

### 2. Configure

```bash
cp config/connectors/pihole.example.yaml    config/connectors/pihole.yaml
cp config/connectors/telegram.example.yaml  config/connectors/telegram.yaml
cp config/llm/gemini.example.yaml           config/llm/gemini.yaml
```

**config/connectors/pihole.yaml**
```yaml
url: http://localhost:8080      # use localhost if bot runs on same Pi as dashboard
password: your_dashboard_password
```

**config/connectors/telegram.yaml**
```yaml
bot_token: 1234567890:ABCdef...   # from @BotFather
default_chat_id: "123456789"      # from @userinfobot
```

**config/llm/gemini.yaml**
```yaml
api_key: AIzaSy...
model: gemini-2.5-flash
```

### 3. Verify

```bash
.venv/bin/python3 llm/gemini_agent.py --prompt "Is my network healthy?"
```

Expected: a plain-English health summary. If `ConnectionRefusedError` — dashboard isn't running.

---

## Deploy

### Copy files to Pi

```bash
rsync -az --exclude='.git/' --exclude='.venv/' --exclude='__pycache__/' \
    . pi@192.168.68.102:~/pihole-mcp-server/

# Copy secret configs
scp config/connectors/pihole.yaml    pi@192.168.68.102:~/pihole-mcp-server/config/connectors/
scp config/connectors/telegram.yaml  pi@192.168.68.102:~/pihole-mcp-server/config/connectors/
scp config/llm/gemini.yaml           pi@192.168.68.102:~/pihole-mcp-server/config/llm/
```

### Install on Pi

```bash
ssh pi@192.168.68.102 "
  cd ~/pihole-mcp-server &&
  python3 -m venv .venv &&
  .venv/bin/pip install -r requirements.txt
"
```

### Install as a systemd service

```bash
ssh pi@192.168.68.102 "sudo tee /etc/systemd/system/pihole-mcp-watch.service > /dev/null" << 'EOF'
[Unit]
Description=Pi-hole Telegram Bot + Watch Agent
After=network.target pihole-analytics-dashboard.service

[Service]
ExecStart=/home/pi/pihole-mcp-server/.venv/bin/python3 /home/pi/pihole-mcp-server/llm/gemini_agent.py --telegram --watch
WorkingDirectory=/home/pi/pihole-mcp-server
Restart=on-failure
RestartSec=30
User=pi

[Install]
WantedBy=multi-user.target
EOF

ssh pi@192.168.68.102 "
  sudo systemctl daemon-reload &&
  sudo systemctl enable --now pihole-mcp-watch
"
```

Check it's running:
```bash
ssh pi@192.168.68.102 "systemctl status pihole-mcp-watch"
ssh pi@192.168.68.102 "journalctl -u pihole-mcp-watch -f"
```

Then send `/help` to your Telegram bot to confirm it's working.

---

## Running Modes

### Telegram bot + watch mode (recommended — one command does everything)

```bash
.venv/bin/python3 llm/gemini_agent.py --telegram --watch
```

### Telegram bot only (responds to commands, no automatic alerts)

```bash
.venv/bin/python3 llm/gemini_agent.py --telegram
```

### Watch mode only (automatic alerts, no command listening)

```bash
.venv/bin/python3 llm/gemini_agent.py --watch
.venv/bin/python3 llm/gemini_agent.py --watch --interval 120   # every 2 hours
```

---

## Watch Mode Schedule

Automatic alerts are sent to Telegram without you asking — only when issues are found.

- Checks every **6 hours** by default (10 AM, 4 PM, 10 PM)
- Skips **4 AM–10 AM** quiet window automatically
- Sends alert only if adult content, VPN, crypto, or excessive usage detected
- Silent "all clear" — no message if nothing found

Tune in `config/llm/prompts.yaml`:
```yaml
watch_interval_minutes: 360   # every 6 hours
watch_skip_start_hour: 4      # quiet window start
watch_skip_end_hour: 10       # quiet window end
```

---

## Config Files

| File | Secret | Description |
|---|---|---|
| `config/connectors/pihole.yaml` | Yes — gitignored | Dashboard URL + password |
| `config/connectors/telegram.yaml` | Yes — gitignored | Bot token + chat ID |
| `config/llm/gemini.yaml` | Yes — gitignored | Gemini API key + model |
| `config/llm/prompts.yaml` | No | Watch schedule + agent behaviour |
| `config/mcp/server.yaml` | No | Server name + log level |

All `*.example.yaml` files are tracked in git — copy them to create the real files.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Bot not responding | Check `bot_token` in `telegram.yaml` is correct |
| `ConnectionRefusedError` | Dashboard not running — start `pihole-analytics-dashboard` first |
| `401 Unauthorized` | Wrong `password` in `pihole.yaml` — must match dashboard's `dashboard.password` |
| Gemini quota error | Wait 1 min; increase `watch_interval_minutes` in `prompts.yaml` |
| Bot says "⏳ Checking..." then nothing | Run `journalctl -u pihole-mcp-watch -f` for the error |
| `FileNotFoundError: config/connectors/pihole.yaml` | Config files not created — run the `cp` commands in Setup step 2 |

---

## Testing

```bash
python3 -m pytest tests/test_all.py -v
```

All tests run offline — no live credentials required.
