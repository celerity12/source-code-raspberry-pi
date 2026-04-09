# pihole-mcp-server — Deployment Guide

Step-by-step instructions for deploying the MCP server on a Raspberry Pi or any Linux host.

---

## Prerequisites

Before starting, you need:

| Requirement | How to get it |
|---|---|
| Pi-hole Analytics dashboard | Deploy [pi_hole_web_survillance](https://github.com/simplyauditmanager/pi_hole_web_survillance) first |
| Dashboard URL + password | Set during dashboard deployment (e.g. `http://192.168.1.10:8080`) |
| Python 3.10+ | `python3 --version` |
| Gemini API key | [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) — free tier available |
| Telegram bot token | Create a bot via [@BotFather](https://t.me/BotFather) on Telegram |
| Your Telegram chat ID | Message [@userinfobot](https://t.me/userinfobot) on Telegram |

---

## Step 1 — Clone the repo

```bash
git clone https://github.com/simplyauditmanager/pihole-mcp-server
cd pihole-mcp-server
```

---

## Step 2 — Install dependencies

```bash
pip3 install -r requirements.txt
```

If your system blocks pip (Debian/Ubuntu PEP 668):

```bash
pip3 install --break-system-packages -r requirements.txt
```

Or use a virtual environment:

```bash
sudo apt install python3.12-venv        # if not installed
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# then use .venv/bin/python instead of python3
```

---

## Step 3 — Create secret config files

Copy the example templates — never edit the `.example.yaml` files directly.

```bash
cp config/connectors/pihole.example.yaml    config/connectors/pihole.yaml
cp config/connectors/telegram.example.yaml  config/connectors/telegram.yaml
cp config/llm/gemini.example.yaml           config/llm/gemini.yaml
```

---

## Step 4 — Fill in your credentials

### config/connectors/pihole.yaml
```yaml
url: http://192.168.1.10:8080       # IP of your Raspberry Pi running the dashboard
password: your_dashboard_password   # Password set in dashboard config.yaml → dashboard.password
```

### config/connectors/telegram.yaml
```yaml
bot_token: 1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ   # From @BotFather
default_chat_id: "123456789"                         # From @userinfobot
```

### config/llm/gemini.yaml
```yaml
api_key: AIzaSy...        # From aistudio.google.com/app/apikey
model: gemini-2.0-flash   # gemini-2.0-flash (faster) or gemini-1.5-pro (deeper)
```

---

## Step 5 — (Optional) Tune behaviour

These files are **not secrets** — edit freely and commit them.

### config/mcp/server.yaml
```yaml
server_name: pihole-analytics   # Name shown in Claude Desktop tool list
log_level: INFO                  # DEBUG | INFO | WARNING | ERROR
```

### config/llm/prompts.yaml
```yaml
watch_interval_minutes: 15       # How often watch mode checks the network

system_prompt: |
  You are a home network security assistant ...   # Edit to change agent personality

watch_prompt: |
  Check Pi-hole for any security alerts ...       # Edit to change what watch mode checks
```

---

## Step 6 — Verify the setup

```bash
python3 llm/gemini_agent.py --prompt "Is my network healthy?"
```

Expected output: a plain-English health summary from Gemini.

If you see a `FileNotFoundError` — re-check Step 3 (config files not created yet).  
If you see a `ConnectionRefusedError` — the dashboard is not reachable at the configured URL.

---

## Step 7 — Run

### Interactive agent (REPL)
```bash
python3 llm/gemini_agent.py
```

### Single prompt
```bash
python3 llm/gemini_agent.py --prompt "Who is on my network right now?"
```

### Watch mode (checks on a schedule, sends Telegram alerts)
```bash
python3 llm/gemini_agent.py --watch
python3 llm/gemini_agent.py --watch --interval 30   # override interval in minutes
```

### MCP server only (for Claude Desktop / other MCP clients)
```bash
python3 mcp/server.py
```

---

## Step 8 — (Optional) Claude Desktop integration

Add to `~/.config/claude/claude_desktop_config.json` (Linux/Mac):

```json
{
  "mcpServers": {
    "pihole": {
      "command": "python3",
      "args": ["/home/pi/pihole-mcp-server/mcp/server.py"]
    }
  }
}
```

On Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Restart Claude Desktop — Pi-hole and Telegram tools appear automatically.

---

## Step 9 — (Optional) Run watch mode as a systemd service

This keeps the watch agent running permanently across reboots.

```bash
sudo nano /etc/systemd/system/pihole-mcp-watch.service
```

```ini
[Unit]
Description=Pi-hole MCP Watch Agent
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/pihole-mcp-server/llm/gemini_agent.py --watch
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
sudo systemctl status pihole-mcp-watch
sudo journalctl -u pihole-mcp-watch -f      # live logs
```

---

## Config file reference

| File | Secret | Description |
|---|---|---|
| `config/connectors/pihole.yaml` | Yes — gitignored | Dashboard URL + password |
| `config/connectors/telegram.yaml` | Yes — gitignored | Bot token + chat ID |
| `config/llm/gemini.yaml` | Yes — gitignored | Gemini API key + model |
| `config/mcp/server.yaml` | No | Server name + log level |
| `config/llm/prompts.yaml` | No | System prompt + watch settings |
| `config/loader.py` | No | Central path resolver — never edit |

Secret files are gitignored automatically. Example templates (`*.example.yaml`) are tracked in git.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `FileNotFoundError: config/connectors/pihole.yaml` | Secret file not created | Run `cp config/connectors/pihole.example.yaml config/connectors/pihole.yaml` |
| `ConnectionRefusedError` | Dashboard not running or wrong URL | Check `url` in `pihole.yaml`; verify `curl http://YOUR_PI:8080` works |
| `401 Unauthorized` from dashboard | Wrong password | Check `password` in `pihole.yaml` matches `dashboard.password` in dashboard's `config.yaml` |
| `Telegram error: Bad Request` | Wrong bot token or chat ID | Re-check `bot_token` and `default_chat_id` |
| `google.api_core.exceptions.ResourceExhausted` | Gemini free quota hit | Wait a minute; or increase `watch_interval_minutes` in `config/llm/prompts.yaml` |
| Gemini produces wrong tool calls | System prompt needs tuning | Edit `config/llm/prompts.yaml` → `system_prompt` |

---

## Running tests

```bash
python3 -m pytest tests/test_all.py -v
```

All 121 tests run offline — no live credentials required.
