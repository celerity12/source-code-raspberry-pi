#!/usr/bin/env python3
"""
Tests for scripts/device_resolver.py

Covers: detect_device_type, resolve_client priority ordering,
fetch_network_devices (HTTP mocked), refresh_device_registry,
build_registry_map.
"""

import sys
import sqlite3
import logging
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

with patch('logging.FileHandler', lambda *a, **kw: logging.NullHandler()):
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from scripts.core import device_resolver as DR


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_conn():
    """In-memory DB with device_registry table."""
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE device_registry (
            mac         TEXT PRIMARY KEY,
            last_ip     TEXT NOT NULL,
            hostname    TEXT,
            device_type TEXT,
            custom_name TEXT,
            last_seen   TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX idx_device_ip ON device_registry(last_ip);
    """)
    return conn


BASE_CFG = {
    'pihole':           {'host': 'http://pi', 'api_path': '/api.php', 'api_token': 'tok'},
    'client_macs':      {},
    'client_hostnames': {},
    'clients':          {},
}


# ── detect_device_type ────────────────────────────────────────────────────────

class TestDetectDeviceType(unittest.TestCase):

    def test_iphone_hostname(self):
        self.assertEqual(DR.detect_device_type("johns-iphone"), "iPhone")

    def test_ipad_hostname(self):
        self.assertEqual(DR.detect_device_type("moms-ipad-2"), "iPad")

    def test_macbook_hostname(self):
        self.assertEqual(DR.detect_device_type("my-macbook-pro"), "MacBook")

    def test_playstation_hostname(self):
        self.assertEqual(DR.detect_device_type("ps5-living-room"), "PlayStation")

    def test_xbox_hostname(self):
        self.assertEqual(DR.detect_device_type("kids-xbox"), "Xbox")

    def test_chromecast_hostname(self):
        self.assertEqual(DR.detect_device_type("chromecast-bedroom"), "Chromecast")

    def test_roku_hostname(self):
        self.assertEqual(DR.detect_device_type("roku-tv-upstairs"), "Roku")

    def test_echo_hostname(self):
        self.assertEqual(DR.detect_device_type("echo-kitchen"), "Amazon Echo")

    def test_case_insensitive(self):
        self.assertEqual(DR.detect_device_type("iPhone-John"), "iPhone")

    def test_unknown_hostname_falls_to_vendor(self):
        # hostname has no match, vendor string is used
        result = DR.detect_device_type("device-42", vendor="Apple, Inc.")
        self.assertEqual(result, "Apple Device")

    def test_samsung_vendor(self):
        result = DR.detect_device_type("", vendor="Samsung Electronics")
        self.assertEqual(result, "Samsung Device")

    def test_espressif_vendor(self):
        result = DR.detect_device_type("", vendor="Espressif Inc.")
        self.assertEqual(result, "IoT Device")

    def test_empty_hostname_and_vendor_returns_empty(self):
        self.assertEqual(DR.detect_device_type("", ""), "")

    def test_hostname_beats_vendor(self):
        # hostname matches → should not fall through to vendor
        result = DR.detect_device_type("family-ipad", vendor="Samsung Electronics")
        self.assertEqual(result, "iPad")

    def test_raspberry_pi(self):
        self.assertEqual(DR.detect_device_type("raspberrypi-nas"), "Raspberry Pi")


# ── resolve_client priority ───────────────────────────────────────────────────

class TestResolveClient(unittest.TestCase):

    IP   = "192.168.1.100"
    MAC  = "AA:BB:CC:DD:EE:FF"

    def _registry(self, **kwargs):
        defaults = {"mac": self.MAC, "hostname": "", "device_type": "", "custom_name": ""}
        defaults.update(kwargs)
        return {self.IP: defaults}

    # Priority 1 — MAC-based name
    def test_mac_based_name_wins(self):
        cfg = {**BASE_CFG, 'client_macs': {self.MAC: "Dad's iPhone"},
               'client_hostnames': {}, 'clients': {self.IP: "Old IP Name"}}
        result = DR.resolve_client(self.IP, cfg, self._registry())
        self.assertEqual(result, "Dad's iPhone")

    def test_mac_key_case_insensitive(self):
        # Config may use lowercase MAC
        cfg = {**BASE_CFG, 'client_macs': {self.MAC.lower(): "Dad's iPhone"}}
        result = DR.resolve_client(self.IP, cfg, self._registry())
        self.assertEqual(result, "Dad's iPhone")

    # Priority 2 — hostname pattern
    def test_hostname_pattern_match(self):
        cfg = {**BASE_CFG, 'client_hostnames': {"johns-iphone": "John's iPhone"}}
        result = DR.resolve_client(self.IP, cfg,
                                   self._registry(hostname="johns-iphone-7"))
        self.assertEqual(result, "John's iPhone")

    def test_hostname_pattern_case_insensitive(self):
        cfg = {**BASE_CFG, 'client_hostnames': {"ipad": "Kids iPad"}}
        result = DR.resolve_client(self.IP, cfg,
                                   self._registry(hostname="FAMILY-IPAD"))
        self.assertEqual(result, "Kids iPad")

    # Priority 3 — legacy IP name
    def test_legacy_ip_name(self):
        cfg = {**BASE_CFG, 'clients': {self.IP: "Smart TV"}}
        result = DR.resolve_client(self.IP, cfg, self._registry(mac=""))
        self.assertEqual(result, "Smart TV")

    # Priority 4 — auto-detected device type
    def test_auto_type_with_hostname(self):
        cfg = BASE_CFG
        result = DR.resolve_client(
            self.IP, cfg,
            self._registry(mac="", hostname="johns-ps5", device_type="PlayStation")
        )
        self.assertIn("PlayStation", result)
        self.assertIn("johns-ps5", result)

    def test_auto_type_without_hostname(self):
        cfg = BASE_CFG
        result = DR.resolve_client(
            self.IP, cfg,
            self._registry(mac="", hostname="", device_type="Roku")
        )
        self.assertEqual(result, "Roku")

    # Priority 5 — raw hostname
    def test_raw_hostname_fallback(self):
        cfg = BASE_CFG
        result = DR.resolve_client(
            self.IP, cfg,
            self._registry(mac="", hostname="my-laptop", device_type="")
        )
        self.assertEqual(result, "my-laptop")

    # Priority 6 — raw IP
    def test_raw_ip_last_resort(self):
        result = DR.resolve_client(self.IP, BASE_CFG, {})
        self.assertEqual(result, self.IP)

    def test_empty_registry_falls_to_ip_map(self):
        cfg = {**BASE_CFG, 'clients': {self.IP: "Mapped Name"}}
        result = DR.resolve_client(self.IP, cfg, {})
        self.assertEqual(result, "Mapped Name")


# ── fetch_network_devices ─────────────────────────────────────────────────────

class TestFetchNetworkDevices(unittest.TestCase):

    CFG = {'pihole': {'host': 'http://pi', 'api_path': '/api.php', 'api_token': 'tok'}}

    @patch('requests.get')
    def test_success_returns_ip_map(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "network": [{
                "ip": ["192.168.1.1"],
                "name": ["my-macbook"],
                "macaddr": "AA:BB:CC:DD:EE:FF",
                "hwVendor": "Apple, Inc.",
            }]
        }
        mock_get.return_value = mock_resp
        result = DR.fetch_network_devices(self.CFG)
        self.assertIn("192.168.1.1", result)
        self.assertEqual(result["192.168.1.1"]["hostname"], "my-macbook")
        self.assertEqual(result["192.168.1.1"]["mac"], "AA:BB:CC:DD:EE:FF")

    @patch('requests.get')
    def test_multiple_ips_per_device(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "network": [{
                "ip": ["192.168.1.1", "192.168.1.50"],
                "name": ["echo-kitchen"],
                "macaddr": "11:22:33:44:55:66",
                "hwVendor": "Amazon",
            }]
        }
        mock_get.return_value = mock_resp
        result = DR.fetch_network_devices(self.CFG)
        self.assertIn("192.168.1.1", result)
        self.assertIn("192.168.1.50", result)

    @patch('requests.get')
    def test_network_error_returns_empty(self, mock_get):
        import requests
        mock_get.side_effect = requests.RequestException("timeout")
        result = DR.fetch_network_devices(self.CFG)
        self.assertEqual(result, {})

    @patch('requests.get')
    def test_empty_network_list(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"network": []}
        mock_get.return_value = mock_resp
        self.assertEqual(DR.fetch_network_devices(self.CFG), {})

    @patch('requests.get')
    def test_missing_name_handled(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "network": [{
                "ip": ["192.168.1.5"],
                "name": [],
                "macaddr": "AA:BB:CC:00:11:22",
                "hwVendor": "",
            }]
        }
        mock_get.return_value = mock_resp
        result = DR.fetch_network_devices(self.CFG)
        self.assertEqual(result["192.168.1.5"]["hostname"], "")


# ── refresh_device_registry + build_registry_map ─────────────────────────────

class TestDeviceRegistry(unittest.TestCase):

    def setUp(self):
        self.conn = make_conn()

    def _inject(self, devices: dict):
        """Patch fetch_network_devices to return given dict."""
        return patch.object(DR, 'fetch_network_devices', return_value=devices)

    def test_refresh_inserts_rows(self):
        devices = {
            "192.168.1.1": {"mac": "AA:BB:CC:DD:EE:FF",
                             "hostname": "iphone-john", "vendor": "Apple, Inc."},
        }
        with self._inject(devices):
            DR.refresh_device_registry(self.conn, BASE_CFG)

        row = self.conn.execute(
            "SELECT * FROM device_registry WHERE last_ip='192.168.1.1'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["hostname"], "iphone-john")
        self.assertEqual(row["device_type"], "iPhone")

    def test_refresh_updates_existing_ip(self):
        devices1 = {"192.168.1.1": {"mac": "AA:BB:CC:DD:EE:FF",
                                     "hostname": "old-name", "vendor": ""}}
        devices2 = {"192.168.1.2": {"mac": "AA:BB:CC:DD:EE:FF",  # same MAC, new IP
                                     "hostname": "old-name", "vendor": ""}}
        with self._inject(devices1):
            DR.refresh_device_registry(self.conn, BASE_CFG)
        with self._inject(devices2):
            DR.refresh_device_registry(self.conn, BASE_CFG)

        row = self.conn.execute(
            "SELECT last_ip FROM device_registry WHERE mac='AA:BB:CC:DD:EE:FF'"
        ).fetchone()
        self.assertEqual(row["last_ip"], "192.168.1.2")

    def test_custom_name_not_overwritten(self):
        # Pre-seed a custom_name
        self.conn.execute(
            "INSERT INTO device_registry (mac, last_ip, hostname, device_type, custom_name) "
            "VALUES ('AA:BB:CC:DD:EE:FF', '192.168.1.1', 'iphone', 'iPhone', 'Grandma')"
        )
        self.conn.commit()

        devices = {"192.168.1.1": {"mac": "AA:BB:CC:DD:EE:FF",
                                    "hostname": "iphone", "vendor": ""}}
        with self._inject(devices):
            DR.refresh_device_registry(self.conn, BASE_CFG)

        row = self.conn.execute(
            "SELECT custom_name FROM device_registry WHERE mac='AA:BB:CC:DD:EE:FF'"
        ).fetchone()
        self.assertEqual(row["custom_name"], "Grandma")

    def test_build_registry_map_keyed_by_ip(self):
        self.conn.execute(
            "INSERT INTO device_registry (mac, last_ip, hostname, device_type) "
            "VALUES ('AA:BB:CC:DD:EE:FF', '192.168.1.10', 'roku-tv', 'Roku')"
        )
        self.conn.commit()
        reg = DR.build_registry_map(self.conn)
        self.assertIn("192.168.1.10", reg)
        self.assertEqual(reg["192.168.1.10"]["device_type"], "Roku")

    def test_build_registry_empty_db_returns_empty_dict(self):
        reg = DR.build_registry_map(self.conn)
        self.assertEqual(reg, {})

    def test_refresh_no_devices_does_not_crash(self):
        with self._inject({}):
            DR.refresh_device_registry(self.conn, BASE_CFG)  # should not raise


if __name__ == '__main__':
    unittest.main()
