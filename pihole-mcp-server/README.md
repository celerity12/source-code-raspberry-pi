# pihole-mcp-server

Monitor and control your home network from **Telegram**. Ask questions, get alerts, and block domains — all from your phone.

Connects to the [pi_hole_web_survillance](https://github.com/simplyauditmanager/pi_hole_web_survillance) dashboard over HTTP.

---

## What you can do from Telegram

### Slash commands

| Command | What it does |
|---|---|
| `/status` | Network overview — queries, blocked %, active devices |
| `/alerts` | Security alerts today (adult content, VPN, crypto) |
| `/health` | System health — disk, RAM, CPU, temperature |
| `/devices` | List all active devices today |
| `/block domain.com` | Block a domain via Pi-hole |
| `/unblock domain.com` | Unblock a domain |
| `/report` | Trigger a daily email report |
| `/help` | Show all commands |

### Natural language

You can also ask anything in plain English:

> "Who was online last night?"
> "Did anyone visit anything suspicious this week?"
> "What was the kids' tablet doing yesterday?"
> "Show me all gaming sites visited today."
> "Block YouTube for now."

---

## How it works

```
Your Telegram message
        ↓
  gemini_agent.py  (polls Telegram every 3s for new messages)
        ↓
  Gemini AI  (decides which data to fetch)
        ↓
  mcp/server.py  (29 tools — Pi-hole data + Telegram sending)
        ↓
  Pi-hole Analytics dashboard  (your network data)
        ↓
  Reply sent back to your Telegram
```

---

## Setup

### Prerequisites

| Requirement | Where to get it |
|---|---|
| Pi-hole Analytics dashboard running | Deploy [pi_hole_web_survillance](https://github.com/simplyauditmanager/pi_hole_web_survillance) first |
| Gemini API key | [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) — free |
| Telegram bot token | Message [@BotFather](https://t.me/BotFather) → /newbot |
| Your Telegram chat ID | Message [@userinfobot](https://t.me/userinfobot) |

### Install

```bash
git clone https://github.com/simplyauditmanager/pihole-mcp-server
cd pihole-mcp-server
pip3 install -r requirements.txt
```

### Configure

```bash
cp config/connectors/pihole.example.yaml    config/connectors/pihole.yaml
cp config/connectors/telegram.example.yaml  config/connectors/telegram.yaml
cp config/llm/gemini.example.yaml           config/llm/gemini.yaml
```

Fill in the three files:

**config/connectors/pihole.yaml**
```yaml
url: http://192.168.1.10:8080   # your Pi's IP
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
model: gemini-2.0-flash
```

### Verify

```bash
python3 llm/gemini_agent.py --prompt "Is my network healthy?"
```

---

## Running

### Telegram bot + watch mode (recommended)

Bot listens for your commands **and** sends automatic alerts every 6 hours:

```bash
python3 llm/gemini_agent.py --telegram --watch
```

Once running, open Telegram and send `/help` to your bot.

### Telegram bot only

Responds to commands and questions, no automatic alerts:

```bash
python3 llm/gemini_agent.py --telegram
```

### Watch mode only

Periodic checks on a schedule, no command listening:

```bash
python3 llm/gemini_agent.py --watch
python3 llm/gemini_agent.py --watch --interval 120   # every 2 hours
```

Watch schedule (configured in `config/llm/prompts.yaml`):
- Checks every 6 hours by default
- Skips 4 AM–10 AM quiet window automatically
- Sends Telegram alert only if issues found

---

## Run as a permanent systemd service

Keeps the bot running across reboots. Replace `pi` and `/home/pi` with your username.

```bash
sudo nano /etc/systemd/system/pihole-mcp-watch.service
```

```ini
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
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now pihole-mcp-watch
sudo journalctl -u pihole-mcp-watch -f    # view live logs
```

---

## Config files

| File | Secret | Description |
|---|---|---|
| `config/connectors/pihole.yaml` | Yes — gitignored | Dashboard URL + password |
| `config/connectors/telegram.yaml` | Yes — gitignored | Bot token + chat ID |
| `config/llm/gemini.yaml` | Yes — gitignored | Gemini API key + model |
| `config/llm/prompts.yaml` | No | Watch schedule + agent behaviour |
| `config/mcp/server.yaml` | No | Server name + log level |

### Watch schedule (config/llm/prompts.yaml)

```yaml
watch_interval_minutes: 360   # check every 6 hours
watch_skip_start_hour: 4      # quiet window start (4 AM)
watch_skip_end_hour: 10       # quiet window end (10 AM)
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Bot not responding | Check `bot_token` in `telegram.yaml`; verify bot exists in Telegram |
| `ConnectionRefusedError` | Dashboard not running — start `pihole-analytics-dashboard` first |
| `401 Unauthorized` | Wrong `password` in `pihole.yaml` |
| Gemini quota error | Wait 1 min; increase `watch_interval_minutes` in `prompts.yaml` |
| Bot sends "⏳ Checking..." but no reply | Run `journalctl -u pihole-mcp-watch -f` and check for errors |

---

## Testing

```bash
python3 -m pytest tests/test_all.py -v
```

All tests run offline — no live credentials required.
