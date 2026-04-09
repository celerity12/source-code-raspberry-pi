#!/usr/bin/env python3
"""
Pi-hole Analytics + Telegram MCP Server.

Exposes Pi-hole network surveillance and Telegram messaging as MCP tools
so any MCP-compatible LLM client (Claude Desktop, Gemini agent, etc.)
can query your network and send Telegram notifications.

Run directly:
    python mcp/server.py

Or register in Claude Desktop ~/.config/claude/claude_desktop_config.json:
    {
      "mcpServers": {
        "pihole": {
          "command": "python",
          "args": ["/path/to/pihole-mcp-server/mcp/server.py"]
        }
      }
    }

Layer: MCP — protocol server only.
Imports connectors; knows nothing about which LLM is calling it.
"""

import json
import sys
import logging
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool, TextContent,
    CallToolResult, ListToolsResult,
)

sys.path.insert(0, str(Path(__file__).parent.parent))
from connectors.pihole_client   import PiholeClient
from connectors.telegram_client import TelegramClient
from config.loader import load_connector, load_mcp

# ── Logging (stderr so it doesn't pollute stdio transport) ────────────────────
logging.basicConfig(
    stream=sys.stderr, level=logging.INFO,
    format='%(asctime)s [MCP] %(levelname)s %(message)s'
)
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

mcp_cfg      = load_mcp()
pihole_cfg   = load_connector('pihole')
telegram_cfg = load_connector('telegram')

# Apply log level from config before anything else logs
logging.getLogger().setLevel(
    getattr(logging, mcp_cfg.get('log_level', 'INFO').upper(), logging.INFO)
)

pihole   = PiholeClient(
    base_url = pihole_cfg['url'],
    password = pihole_cfg['password'],
)
telegram = TelegramClient(
    bot_token       = telegram_cfg['bot_token'],
    default_chat_id = str(telegram_cfg['default_chat_id']),
)

# ── MCP Server ────────────────────────────────────────────────────────────────

server = Server(mcp_cfg.get('server_name', 'pihole-analytics'))

# ── Tool definitions ──────────────────────────────────────────────────────────

TOOLS: list[Tool] = [

    # ── Pi-hole: overview ─────────────────────────────────────────────────────
    Tool(
        name        = "pihole_stats",
        description = "Network snapshot: queries, blocked, categories, top domains, 7d trend.",
        inputSchema = {
            "type": "object",
            "properties": {
                "date":     {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"},
            },
        },
    ),

    Tool(
        name        = "pihole_summary",
        description = "Quick totals: queries, blocked, unique domains, active devices.",
        inputSchema = {
            "type": "object",
            "properties": {
                "date":     {"type": "string"},
                "end_date": {"type": "string"},
            },
        },
    ),

    Tool(
        name        = "pihole_health",
        description = "System health: disk, RAM, CPU, temp, blocking status.",
        inputSchema = {"type": "object", "properties": {}},
    ),

    Tool(
        name        = "pihole_alerts",
        description = "Security alerts: adult, VPN, crypto, excessive usage.",
        inputSchema = {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "YYYY-MM-DD"},
            },
        },
    ),

    Tool(
        name        = "pihole_excessive_usage",
        description = "Devices over usage threshold for social/streaming/gaming.",
        inputSchema = {
            "type": "object",
            "properties": {
                "date":              {"type": "string"},
                "threshold_minutes": {"type": "integer"},
            },
        },
    ),

    # ── Pi-hole: devices ──────────────────────────────────────────────────────
    Tool(
        name        = "pihole_devices",
        description = "Active devices with query stats for a date.",
        inputSchema = {
            "type": "object",
            "properties": {
                "date": {"type": "string"},
            },
        },
    ),

    Tool(
        name        = "pihole_device_registry",
        description = "All known devices: name, IP, type, last seen.",
        inputSchema = {"type": "object", "properties": {}},
    ),

    Tool(
        name        = "pihole_device_detail",
        description = "One device: queries, blocked, categories, peak hour.",
        inputSchema = {
            "type": "object",
            "required": ["ip"],
            "properties": {
                "ip":   {"type": "string"},
                "date": {"type": "string"},
            },
        },
    ),

    Tool(
        name        = "pihole_device_domains",
        description = "Domains accessed by a device.",
        inputSchema = {
            "type": "object",
            "required": ["ip"],
            "properties": {
                "ip":    {"type": "string"},
                "date":  {"type": "string"},
                "limit": {"type": "integer"},
            },
        },
    ),

    Tool(
        name        = "pihole_client_category_usage",
        description = "Category breakdown for one device or all devices.",
        inputSchema = {
            "type": "object",
            "properties": {
                "ip":   {"type": "string"},
                "date": {"type": "string"},
            },
        },
    ),

    Tool(
        name        = "pihole_date_range",
        description = "Per-device summary over a date range.",
        inputSchema = {
            "type": "object",
            "required": ["start_date", "end_date"],
            "properties": {
                "start_date": {"type": "string"},
                "end_date":   {"type": "string"},
            },
        },
    ),

    # ── Pi-hole: categories ───────────────────────────────────────────────────
    Tool(
        name        = "pihole_categories",
        description = "Traffic by category: streaming, gaming, social, etc.",
        inputSchema = {
            "type": "object",
            "properties": {
                "date": {"type": "string"},
            },
        },
    ),

    Tool(
        name        = "pihole_top_by_category",
        description = "Top domains for a category, optionally by device.",
        inputSchema = {
            "type": "object",
            "required": ["category"],
            "properties": {
                "category": {"type": "string", "description": "streaming|social_media|gaming|adult"},
                "ip":       {"type": "string"},
                "date":     {"type": "string"},
                "limit":    {"type": "integer"},
            },
        },
    ),

    Tool(
        name        = "pihole_uncategorized_domains",
        description = "Domains with no category.",
        inputSchema = {
            "type": "object",
            "properties": {
                "date":  {"type": "string"},
                "limit": {"type": "integer"},
            },
        },
    ),

    # ── Pi-hole: search & query log ───────────────────────────────────────────
    Tool(
        name        = "pihole_search",
        description = "Search domains by keyword.",
        inputSchema = {
            "type": "object",
            "required": ["q"],
            "properties": {
                "q":     {"type": "string"},
                "date":  {"type": "string"},
                "limit": {"type": "integer"},
            },
        },
    ),

    Tool(
        name        = "pihole_query_log",
        description = "Raw DNS log filtered by date/IP/category/domain/blocked.",
        inputSchema = {
            "type": "object",
            "properties": {
                "date":     {"type": "string"},
                "ip":       {"type": "string"},
                "category": {"type": "string"},
                "domain":   {"type": "string"},
                "blocked":  {"type": "boolean"},
                "limit":    {"type": "integer"},
            },
        },
    ),

    Tool(
        name        = "pihole_new_domains",
        description = "Domains seen for the first time today.",
        inputSchema = {
            "type": "object",
            "properties": {
                "date": {"type": "string"},
            },
        },
    ),

    # ── Pi-hole: blocking ─────────────────────────────────────────────────────
    Tool(
        name        = "pihole_blocked_top",
        description = "Top blocked domains for a date.",
        inputSchema = {
            "type": "object",
            "properties": {
                "date": {"type": "string"},
            },
        },
    ),

    Tool(
        name        = "pihole_blocked_summary",
        description = "Blocked vs allowed query counts.",
        inputSchema = {
            "type": "object",
            "properties": {
                "date":     {"type": "string"},
                "end_date": {"type": "string"},
            },
        },
    ),

    Tool(
        name        = "pihole_manually_blocked",
        description = "Domains manually blocked via dashboard.",
        inputSchema = {"type": "object", "properties": {}},
    ),

    Tool(
        name        = "pihole_block_domain",
        description = "Block a domain.",
        inputSchema = {
            "type": "object",
            "required": ["domain"],
            "properties": {
                "domain": {"type": "string"},
            },
        },
    ),

    Tool(
        name        = "pihole_unblock_domain",
        description = "Unblock a domain.",
        inputSchema = {
            "type": "object",
            "required": ["domain"],
            "properties": {
                "domain": {"type": "string"},
            },
        },
    ),

    Tool(
        name        = "pihole_send_report",
        description = "Trigger email report.",
        inputSchema = {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["daily", "weekly", "monthly"],
                },
            },
        },
    ),

    # ── Telegram ──────────────────────────────────────────────────────────────
    Tool(
        name        = "telegram_send_message",
        description = "Send text to Telegram (HTML ok).",
        inputSchema = {
            "type": "object",
            "required": ["text"],
            "properties": {
                "text":    {"type": "string"},
                "chat_id": {"type": "string"},
            },
        },
    ),

    Tool(
        name        = "telegram_send_alert",
        description = "Formatted alert to Telegram with severity.",
        inputSchema = {
            "type": "object",
            "required": ["title", "body"],
            "properties": {
                "title":   {"type": "string"},
                "body":    {"type": "string"},
                "level":   {"type": "string", "enum": ["info", "warning", "critical"]},
                "chat_id": {"type": "string"},
            },
        },
    ),

    Tool(
        name        = "telegram_send_network_summary",
        description = "Fetch pihole_stats and send summary to Telegram.",
        inputSchema = {
            "type": "object",
            "properties": {
                "date":    {"type": "string"},
                "chat_id": {"type": "string"},
            },
        },
    ),

    Tool(
        name        = "telegram_send_security_alerts",
        description = "Fetch pihole_alerts and send to Telegram.",
        inputSchema = {
            "type": "object",
            "properties": {
                "date":    {"type": "string"},
                "chat_id": {"type": "string"},
            },
        },
    ),

    Tool(
        name        = "telegram_send_health",
        description = "Fetch health and send to Telegram.",
        inputSchema = {
            "type": "object",
            "properties": {
                "chat_id": {"type": "string"},
            },
        },
    ),

    Tool(
        name        = "telegram_get_updates",
        description = "Get recent Telegram bot messages.",
        inputSchema = {
            "type": "object",
            "properties": {
                "limit": {"type": "integer"},
            },
        },
    ),
]


# ── Tool handlers ─────────────────────────────────────────────────────────────

def _ok(data) -> CallToolResult:
    # Compact JSON — no indent or extra spaces saves ~30% tokens on typical responses
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(data, separators=(',', ':'), default=str))]
    )

def _err(msg: str) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=f"ERROR: {msg}")],
        isError=True,
    )


@server.list_tools()
async def list_tools() -> ListToolsResult:
    return ListToolsResult(tools=TOOLS)


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> CallToolResult:
    log.info("Tool called: %s  args=%s", name, arguments)
    a = arguments or {}

    try:
        # ── Pi-hole overview ──────────────────────────────────────────────────
        if name == "pihole_stats":
            return _ok(pihole.stats(a.get('date'), a.get('end_date')))

        if name == "pihole_summary":
            return _ok(pihole.summary(a.get('date'), a.get('end_date')))

        if name == "pihole_health":
            return _ok(pihole.health())

        if name == "pihole_alerts":
            return _ok(pihole.alerts(a.get('date')))

        if name == "pihole_excessive_usage":
            return _ok(pihole.excessive_usage(a.get('date'), a.get('threshold_minutes', 60)))

        # ── Pi-hole devices ───────────────────────────────────────────────────
        if name == "pihole_devices":
            return _ok(pihole.devices(a.get('date')))

        if name == "pihole_device_registry":
            return _ok(pihole.device_registry())

        if name == "pihole_device_detail":
            if not a.get('ip'):
                return _err("ip is required")
            return _ok(pihole.device_detail(a['ip'], a.get('date')))

        if name == "pihole_device_domains":
            if not a.get('ip'):
                return _err("ip is required")
            return _ok(pihole.device_domains(a['ip'], a.get('date'), a.get('limit', 20)))

        if name == "pihole_client_category_usage":
            return _ok(pihole.client_category_usage(a.get('ip'), a.get('date')))

        if name == "pihole_date_range":
            if not a.get('start_date') or not a.get('end_date'):
                return _err("start_date and end_date are required")
            return _ok(pihole.date_range(a['start_date'], a['end_date']))

        # ── Pi-hole categories ────────────────────────────────────────────────
        if name == "pihole_categories":
            return _ok(pihole.categories(a.get('date')))

        if name == "pihole_top_by_category":
            if not a.get('category'):
                return _err("category is required")
            return _ok(pihole.top_by_category(
                a['category'], a.get('ip'), a.get('date'), a.get('limit', 10)))

        if name == "pihole_uncategorized_domains":
            return _ok(pihole.uncategorized_domains(a.get('date'), a.get('limit', 20)))

        # ── Pi-hole search & log ──────────────────────────────────────────────
        if name == "pihole_search":
            if not a.get('q'):
                return _err("q (search term) is required")
            return _ok(pihole.search(a['q'], a.get('date'), a.get('limit', 20)))

        if name == "pihole_query_log":
            return _ok(pihole.query_log(
                a.get('date'), a.get('ip'), a.get('category'),
                a.get('domain'), a.get('blocked'), a.get('limit', 25)))

        if name == "pihole_new_domains":
            return _ok(pihole.new_domains(a.get('date')))

        # ── Pi-hole blocking ──────────────────────────────────────────────────
        if name == "pihole_blocked_top":
            return _ok(pihole.blocked_top(a.get('date')))

        if name == "pihole_blocked_summary":
            return _ok(pihole.blocked_summary(a.get('date'), a.get('end_date')))

        if name == "pihole_manually_blocked":
            return _ok(pihole.manually_blocked())

        if name == "pihole_block_domain":
            if not a.get('domain'):
                return _err("domain is required")
            return _ok(pihole.block_domain(a['domain']))

        if name == "pihole_unblock_domain":
            if not a.get('domain'):
                return _err("domain is required")
            return _ok(pihole.unblock_domain(a['domain']))

        if name == "pihole_send_report":
            return _ok(pihole.send_report(a.get('period', 'daily')))

        # ── Telegram ──────────────────────────────────────────────────────────
        if name == "telegram_send_message":
            if not a.get('text'):
                return _err("text is required")
            return _ok(telegram.send_message(a['text'], chat_id=a.get('chat_id')))

        if name == "telegram_send_alert":
            return _ok(telegram.send_alert(
                a.get('title', 'Alert'), a.get('body', ''),
                a.get('level', 'warning'), a.get('chat_id')))

        if name == "telegram_send_network_summary":
            stats = pihole.stats(a.get('date'))
            return _ok(telegram.send_network_summary(stats, a.get('chat_id')))

        if name == "telegram_send_security_alerts":
            alerts = pihole.alerts(a.get('date'))
            return _ok(telegram.send_security_alerts(alerts, a.get('chat_id')))

        if name == "telegram_send_health":
            health = pihole.health()
            return _ok(telegram.send_health_status(health, a.get('chat_id')))

        if name == "telegram_get_updates":
            return _ok(telegram.get_updates(limit=a.get('limit', 10)))

        return _err(f"Unknown tool: {name}")

    except Exception as exc:
        log.exception("Tool %s failed: %s", name, exc)
        return _err(str(exc))


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
    log.info("Pi-hole Analytics MCP Server starting — %d tools registered", len(TOOLS))
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream,
                         server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
