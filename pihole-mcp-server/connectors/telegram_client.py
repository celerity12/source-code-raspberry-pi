"""
Telegram Bot API client.
Handles sending messages, alerts, and formatted network reports to Telegram.
"""
import requests
import json
from datetime import datetime


class TelegramClient:
    """Lightweight Telegram Bot API client."""

    API = "https://api.telegram.org/bot{token}/{method}"

    def __init__(self, bot_token: str, default_chat_id: str):
        self.token          = bot_token
        self.default_chat   = str(default_chat_id)

    def _call(self, method: str, payload: dict) -> dict:
        url  = self.API.format(token=self.token, method=method)
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if not data.get('ok'):
            raise RuntimeError(f"Telegram error: {data.get('description', 'unknown')}")
        return data['result']

    # ── Core ─────────────────────────────────────────────────────────────────

    def send_message(self, text: str, chat_id: str = None,
                     parse_mode: str = 'HTML') -> dict:
        """Send a plain text message."""
        return self._call('sendMessage', {
            'chat_id':    chat_id or self.default_chat,
            'text':       text,
            'parse_mode': parse_mode,
        })

    def get_me(self) -> dict:
        """Get bot info — verifies the token works."""
        return self._call('getMe', {})

    def get_updates(self, offset: int = None, limit: int = 10) -> list:
        """Fetch recent messages sent to the bot."""
        payload = {'limit': limit, 'timeout': 0}
        if offset:
            payload['offset'] = offset
        return self._call('getUpdates', payload)

    # ── Formatted messages ────────────────────────────────────────────────────

    def send_alert(self, title: str, body: str,
                   level: str = 'warning', chat_id: str = None) -> dict:
        """Send a formatted alert with an emoji prefix."""
        icon = {'critical': '🚨', 'warning': '⚠️', 'info': 'ℹ️'}.get(level, '⚠️')
        text = (
            f"{icon} <b>{title}</b>\n"
            f"<i>{datetime.now().strftime('%Y-%m-%d %H:%M')}</i>\n\n"
            f"{body}"
        )
        return self.send_message(text, chat_id=chat_id)

    def send_network_summary(self, stats: dict, chat_id: str = None) -> dict:
        """Send a formatted network overview from /api/stats data."""
        s   = stats.get('summary', {})
        tot = s.get('total_queries', 0)
        blk = s.get('blocked_queries', 0)
        pct = round(blk / tot * 100, 1) if tot else 0
        dev = s.get('active_clients', 0)
        dom = s.get('unique_domains', 0)

        cats = stats.get('categories', [])
        top_cats = ', '.join(
            f"{r.get('category','?')} ({r.get('queries',0):,})"
            for r in cats[:3]
        ) or 'none'

        top_doms = stats.get('top_domains', [])
        top_dom_lines = '\n'.join(
            f"  • {r.get('domain','?')} ({r.get('queries',0):,})"
            for r in top_doms[:5]
        ) or '  none'

        date = stats.get('date', datetime.now().strftime('%Y-%m-%d'))

        text = (
            f"🛡️ <b>Pi-hole Network Report — {date}</b>\n\n"
            f"📊 <b>Overview</b>\n"
            f"  Total queries:   <b>{tot:,}</b>\n"
            f"  Blocked:         <b>{blk:,} ({pct}%)</b>\n"
            f"  Active devices:  <b>{dev}</b>\n"
            f"  Unique domains:  <b>{dom:,}</b>\n\n"
            f"📂 <b>Top categories</b>\n  {top_cats}\n\n"
            f"🌐 <b>Top domains</b>\n{top_dom_lines}"
        )
        return self.send_message(text, chat_id=chat_id)

    def send_security_alerts(self, alerts: list, chat_id: str = None) -> dict:
        """Send formatted security alerts from /api/alerts."""
        if not alerts:
            return self.send_message(
                "✅ <b>No security alerts today.</b>", chat_id=chat_id)

        lines = []
        for a in alerts:
            icon  = a.get('icon', '⚠️')
            title = a.get('title', a.get('category', '?'))
            short = a.get('short', '')
            lines.append(f"{icon} <b>{title}</b>\n   {short}")

        text = (
            f"🚨 <b>Security Alerts — {datetime.now().strftime('%Y-%m-%d')}</b>\n\n"
            + '\n\n'.join(lines)
        )
        return self.send_message(text, chat_id=chat_id)

    def send_device_summary(self, device: dict, detail: dict,
                            chat_id: str = None) -> dict:
        """Send a summary for a specific device."""
        name  = device.get('client_name') or device.get('client_ip', '?')
        total = device.get('total_queries', 0)
        blkd  = device.get('blocked_queries', 0)
        uniq  = device.get('unique_domains', 0)

        cats  = detail.get('categories', [])
        cat_lines = '\n'.join(
            f"  • {r.get('category','?')}: {r.get('queries',0):,}"
            for r in cats[:5]
        ) or '  none'

        text = (
            f"📱 <b>Device: {name}</b>\n\n"
            f"  Queries:  {total:,}\n"
            f"  Blocked:  {blkd:,}\n"
            f"  Domains:  {uniq:,}\n\n"
            f"<b>Top categories:</b>\n{cat_lines}"
        )
        return self.send_message(text, chat_id=chat_id)

    def send_health_status(self, health: dict, chat_id: str = None) -> dict:
        """Send system health status. Handles nested dashboard response structure."""
        sys  = health.get('system', health)   # dashboard returns {system:{...}, pihole:{...}}
        ph   = health.get('pihole', {})

        disk_pct = sys.get('disk_pct',     sys.get('disk_percent', 0)) or 0
        ram_pct  = sys.get('mem_pct',      sys.get('ram_percent',  0)) or 0
        cpu_pct  = sys.get('cpu_load_pct', sys.get('cpu_percent',  0)) or 0
        temp     = sys.get('cpu_temp_c',   sys.get('temperature',  0)) or 0

        disk_icon = '🔴' if disk_pct > 85 else ('🟡' if disk_pct > 70 else '🟢')
        ram_icon  = '🔴' if ram_pct  > 85 else ('🟡' if ram_pct  > 70 else '🟢')

        pihole_ok = ph.get('blocking', health.get('pihole_blocking', False))
        ph_icon   = '🟢' if pihole_ok else '🔴'

        uptime = sys.get('uptime_str', '')
        uptime_line = f"\n⏱ Uptime: {uptime}" if uptime else ''

        text = (
            f"💻 <b>System Health — {datetime.now().strftime('%Y-%m-%d %H:%M')}</b>\n\n"
            f"{ph_icon} Pi-hole blocking: {'ON' if pihole_ok else 'OFF'}\n"
            f"{disk_icon} Disk:  {disk_pct}%\n"
            f"{ram_icon} RAM:   {ram_pct}%\n"
            f"🌡️ CPU:   {cpu_pct}%\n"
            f"🌡️ Temp:  {temp}°C"
            f"{uptime_line}"
        )
        return self.send_message(text, chat_id=chat_id)
