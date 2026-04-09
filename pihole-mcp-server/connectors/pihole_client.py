"""
Pi-hole Analytics API client.
Wraps all dashboard /api/* endpoints into typed Python methods.
"""
import requests
from datetime import datetime


class PiholeClient:
    """HTTP client for the Pi-hole Analytics dashboard API."""

    def __init__(self, base_url: str, password: str):
        self.base_url  = base_url.rstrip('/')
        self.session   = requests.Session()
        self._login(password)

    # ── Auth ─────────────────────────────────────────────────────────────────

    def _login(self, password: str):
        resp = self.session.post(f"{self.base_url}/login",
                                 data={'password': password},
                                 allow_redirects=True)
        resp.raise_for_status()

    def _get(self, path: str, **params) -> dict | list:
        params = {k: v for k, v in params.items() if v is not None}
        resp = self.session.get(f"{self.base_url}{path}", params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, json: dict = None) -> dict:
        resp = self.session.post(f"{self.base_url}{path}", json=json or {}, timeout=30)
        resp.raise_for_status()
        return resp.json()

    # ── Overview ──────────────────────────────────────────────────────────────

    def stats(self, date: str = None, end_date: str = None) -> dict:
        """All-in-one snapshot: summary, categories, blocked counts, top domains, 7d trend."""
        return self._get('/api/stats', date=date, end_date=end_date)

    def summary(self, date: str = None, end_date: str = None) -> dict:
        """Network totals for a date."""
        return self._get('/api/summary', date=date, end_date=end_date)

    def compare(self, date: str = None) -> dict:
        """Compare today vs yesterday."""
        return self._get('/api/compare', date=date)

    def trend(self, days: int = 30) -> list:
        """Daily query totals for the last N days."""
        return self._get('/api/trend')

    # ── Devices ───────────────────────────────────────────────────────────────

    def devices(self, date: str = None) -> list:
        """All active devices with stats for a date."""
        return self._get('/api/devices', date=date)

    def device_registry(self) -> list:
        """All known devices from the MAC registry (name, IP, type, last seen)."""
        return self._get('/api/device_registry')

    def device_detail(self, ip: str, date: str = None) -> dict:
        """Deep summary + category breakdown for one device."""
        return self._get('/api/device_detail', ip=ip,
                         date=date or datetime.now().strftime('%Y-%m-%d'))

    def device_hourly(self, ip: str, date: str = None) -> list:
        """Hourly query counts for one device."""
        return self._get('/api/device_hourly', ip=ip,
                         date=date or datetime.now().strftime('%Y-%m-%d'))

    def device_domains(self, ip: str, date: str = None, limit: int = 50) -> list:
        """All domains accessed by a device."""
        return self._get('/api/device_domains', ip=ip,
                         date=date or datetime.now().strftime('%Y-%m-%d'), limit=limit)

    def all_clients_hourly(self, date: str = None) -> dict:
        """Hourly activity for every device — useful for heatmap views."""
        return self._get('/api/all_clients_hourly', date=date)

    def client_category_usage(self, ip: str = None, date: str = None) -> dict:
        """Category breakdown for one device or all devices."""
        return self._get('/api/client_category_usage', ip=ip, date=date)

    def date_range(self, start_date: str, end_date: str) -> list:
        """Per-device summary over an arbitrary date range."""
        return self._get('/api/date_range', start_date=start_date, end_date=end_date)

    # ── Categories ────────────────────────────────────────────────────────────

    def categories(self, date: str = None) -> list:
        """Category breakdown for a date."""
        return self._get('/api/categories', date=date)

    def top_by_category(self, category: str, ip: str = None,
                        date: str = None, limit: int = 10) -> list:
        """Top domains for a specific category, optionally filtered by device."""
        return self._get('/api/top_by_category', category=category,
                         ip=ip, date=date, limit=limit)

    def categorization_stats(self, date: str = None) -> dict:
        """How many domains are categorized vs uncategorized."""
        return self._get('/api/categorization_stats', date=date)

    def uncategorized_domains(self, date: str = None, limit: int = 20) -> list:
        """Domains that couldn't be categorized (category = 'other')."""
        return self._get('/api/uncategorized_domains', date=date, limit=limit)

    # ── Security & Alerts ────────────────────────────────────────────────────

    def alerts(self, date: str = None) -> list:
        """Security alerts: adult content, VPN, crypto, excessive usage."""
        return self._get('/api/alerts', date=date)

    def excessive_usage(self, date: str = None, threshold_minutes: int = 60) -> list:
        """Devices exceeding usage thresholds for social/streaming/gaming."""
        return self._get('/api/excessive_usage', date=date,
                         threshold_minutes=threshold_minutes)

    def blocked_summary(self, date: str = None, end_date: str = None) -> dict:
        """Blocked vs allowed query counts."""
        return self._get('/api/blocked_summary', date=date, end_date=end_date)

    def blocked_top(self, date: str = None) -> list:
        """Top domains blocked by Pi-hole."""
        return self._get('/api/blocked_top', date=date)

    def manually_blocked(self) -> list:
        """Domains manually blocked via the dashboard."""
        return self._get('/api/manually_blocked')

    def block_domain(self, domain: str) -> dict:
        """Block a domain via Pi-hole."""
        return self._post('/api/block_domain', json={'domain': domain})

    def unblock_domain(self, domain: str) -> dict:
        """Unblock a domain via Pi-hole."""
        return self._post('/api/unblock_domain', json={'domain': domain})

    # ── Search & Query Log ────────────────────────────────────────────────────

    def search(self, q: str, date: str = None, limit: int = 50) -> dict:
        """Search domains by keyword across a date."""
        return self._get('/api/search', q=q, date=date, limit=limit)

    def query_log(self, date: str = None, ip: str = None, category: str = None,
                  domain: str = None, blocked: bool = None, limit: int = 100) -> list:
        """Raw query log with optional filters."""
        return self._get('/api/query_log', date=date, ip=ip,
                         category=category, domain=domain,
                         blocked='1' if blocked else None, limit=limit)

    def new_domains(self, date: str = None) -> list:
        """Domains seen for the first time today."""
        return self._get('/api/new_domains', date=date)

    # ── System Health ────────────────────────────────────────────────────────

    def health(self) -> dict:
        """System health: disk, RAM, CPU, temperature, service states."""
        return self._get('/api/health')

    # ── Reports ──────────────────────────────────────────────────────────────

    def send_report(self, period: str = 'daily') -> dict:
        """Trigger an email report (daily / weekly / monthly)."""
        return self._post('/api/send_report', json={'period': period})
