#!/usr/bin/env python3
"""
Tests for scripts/dashboard.py — Flask API routes.

Uses Flask's built-in test client.  All database calls are redirected to a
seeded in-memory (file-backed temp) SQLite DB via patch.object on analytics.DB_PATH.
"""

import sys
import json
import shutil
import sqlite3
import tempfile
import unittest
import logging
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

# Prevent FileHandler from trying to open /home/pi paths during import
with patch('logging.FileHandler', lambda *a, **kw: logging.NullHandler()):
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from scripts.data import analytics as A
    from scripts.web import app as dashboard  # imports Flask app

TODAY     = datetime.now().strftime('%Y-%m-%d')
YESTERDAY = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')


# ── Shared test DB factory ────────────────────────────────────────────────────

def make_file_db():
    """
    File-based SQLite DB in a temp dir, seeded with known data.
    Returns (tmpdir, db_path).  Caller must clean up tmpdir with shutil.rmtree.
    """
    tmpdir  = Path(tempfile.mkdtemp())
    db_path = tmpdir / 'analytics.db'
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE queries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER NOT NULL,
            domain TEXT NOT NULL,
            client_ip TEXT NOT NULL,
            client_name TEXT,
            query_type TEXT,
            status INTEGER,
            category TEXT,
            date TEXT
        );
        CREATE TABLE daily_summary (
            date TEXT, client_ip TEXT, client_name TEXT,
            total_queries INTEGER DEFAULT 0,
            blocked_queries INTEGER DEFAULT 0,
            unique_domains INTEGER DEFAULT 0,
            top_category TEXT,
            PRIMARY KEY (date, client_ip)
        );
    """)
    base = int(datetime.now().replace(hour=10, minute=0, second=0, microsecond=0).timestamp())
    yest = int((datetime.now() - timedelta(days=1)).replace(hour=10).timestamp())

    conn.executemany(
        "INSERT INTO queries (timestamp,domain,client_ip,client_name,status,category,date)"
        " VALUES (?,?,?,?,?,?,?)",
        [
            (base,   'youtube.com',  '192.168.1.1', 'PC',    2, 'streaming',   TODAY),
            (base+1, 'netflix.com',  '192.168.1.1', 'PC',    2, 'streaming',   TODAY),
            (base+2, 'facebook.com', '192.168.1.2', 'Phone', 2, 'social_media',TODAY),
            (base+3, 'ad.test.io',   '192.168.1.1', 'PC',    1, 'ads_tracking',TODAY),
            (yest,   'github.com',   '192.168.1.1', 'PC',    2, 'tech',        YESTERDAY),
        ]
    )
    conn.executemany(
        "INSERT INTO daily_summary VALUES (?,?,?,?,?,?,?)",
        [
            (TODAY,     '192.168.1.1', 'PC',    3, 1, 3, 'streaming'),
            (TODAY,     '192.168.1.2', 'Phone', 1, 0, 1, 'social_media'),
            (YESTERDAY, '192.168.1.1', 'PC',    1, 0, 1, 'tech'),
        ]
    )
    conn.commit()
    conn.close()
    return tmpdir, db_path


# ── Base test class ───────────────────────────────────────────────────────────

class DashboardTestCase(unittest.TestCase):
    """Sets up a Flask test client backed by a seeded temp DB."""

    def setUp(self):
        self.tmpdir, self.db_path = make_file_db()
        self.db_patcher = patch.object(A, 'DB_PATH', self.db_path)
        self.db_patcher.start()
        dashboard.app.config['TESTING'] = True
        self.client = dashboard.app.test_client()

    def tearDown(self):
        self.db_patcher.stop()
        shutil.rmtree(self.tmpdir)

    def get_json(self, url):
        """GET url and return parsed JSON body."""
        resp = self.client.get(url)
        return resp.status_code, json.loads(resp.data)


# ── / (index) ────────────────────────────────────────────────────────────────

class TestIndex(DashboardTestCase):

    def test_returns_200(self):
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)

    def test_returns_html(self):
        resp = self.client.get('/')
        self.assertIn(b'<!DOCTYPE html>', resp.data)

    def test_page_mentions_pi_hole(self):
        resp = self.client.get('/')
        self.assertIn(b'Pi-hole', resp.data)


# ── /api/summary ─────────────────────────────────────────────────────────────

class TestApiSummary(DashboardTestCase):

    def test_returns_200(self):
        status, _ = self.get_json(f'/api/summary?date={TODAY}')
        self.assertEqual(status, 200)

    def test_has_required_keys(self):
        _, data = self.get_json(f'/api/summary?date={TODAY}')
        for key in ('total_queries', 'blocked_queries', 'unique_domains', 'active_clients'):
            self.assertIn(key, data)

    def test_total_queries_value(self):
        _, data = self.get_json(f'/api/summary?date={TODAY}')
        self.assertEqual(data['total_queries'], 4)  # 3 PC + 1 Phone

    def test_defaults_to_today_without_date_param(self):
        status, _ = self.get_json('/api/summary')
        self.assertEqual(status, 200)

    def test_empty_date_returns_empty_values(self):
        _, data = self.get_json('/api/summary?date=1990-01-01')
        # All fields should be None or 0 when no data exists
        self.assertIsNotNone(data)


# ── /api/compare ──────────────────────────────────────────────────────────────

class TestApiCompare(DashboardTestCase):

    def test_returns_200(self):
        status, _ = self.get_json(f'/api/compare?date={TODAY}')
        self.assertEqual(status, 200)

    def test_has_period_keys(self):
        _, data = self.get_json(f'/api/compare?date={TODAY}')
        for key in ('today', 'yesterday', 'week_avg', 'month_avg'):
            self.assertIn(key, data)

    def test_today_total(self):
        _, data = self.get_json(f'/api/compare?date={TODAY}')
        # 3 PC + 1 Phone = 4
        self.assertEqual(data['today']['avg_q'], 4)


# ── /api/clients ──────────────────────────────────────────────────────────────

class TestApiClients(DashboardTestCase):

    def test_returns_200(self):
        status, _ = self.get_json(f'/api/clients?date={TODAY}')
        self.assertEqual(status, 200)

    def test_returns_list(self):
        _, data = self.get_json(f'/api/clients?date={TODAY}')
        self.assertIsInstance(data, list)

    def test_two_clients_today(self):
        _, data = self.get_json(f'/api/clients?date={TODAY}')
        self.assertEqual(len(data), 2)

    def test_rows_have_required_keys(self):
        _, data = self.get_json(f'/api/clients?date={TODAY}')
        for row in data:
            self.assertIn('client_ip', row)
            self.assertIn('today_q', row)


# ── /api/categories ───────────────────────────────────────────────────────────

class TestApiCategories(DashboardTestCase):

    def test_returns_200(self):
        status, _ = self.get_json(f'/api/categories?date={TODAY}')
        self.assertEqual(status, 200)

    def test_returns_list(self):
        _, data = self.get_json(f'/api/categories?date={TODAY}')
        self.assertIsInstance(data, list)

    def test_streaming_present(self):
        _, data = self.get_json(f'/api/categories?date={TODAY}')
        cats = [r['category'] for r in data]
        self.assertIn('streaming', cats)

    def test_client_filter_works(self):
        _, all_data    = self.get_json(f'/api/categories?date={TODAY}')
        _, phone_data  = self.get_json(f'/api/categories?date={TODAY}&client=192.168.1.2')
        phone_cats = [r['category'] for r in phone_data]
        self.assertIn('social_media', phone_cats)
        self.assertNotIn('streaming', phone_cats)

class TestApiAlerts(DashboardTestCase):

    def test_returns_200(self):
        status, data = self.get_json(f'/api/alerts?date={TODAY}')
        self.assertEqual(status, 200)
        self.assertIsInstance(data, dict)
        self.assertIn('critical', data)
        self.assertIn('warnings', data)

    def test_returns_empty_when_no_alerts(self):
        _, data = self.get_json(f'/api/alerts?date={TODAY}')
        self.assertEqual(data['critical'], [])
        self.assertEqual(data['warnings'], [])

    @patch('scripts.core.constants.WATCH_CATEGORIES', {'social_media': 1, 'gaming': 1, 'streaming': 1})
    def test_warning_categories_include_top_sites(self):
        _, data = self.get_json(f'/api/alerts?date={TODAY}')
        categories = [item['category'] for item in data['warnings']]
        self.assertIn('social_media', categories)
        self.assertIn('streaming', categories)
        for item in data['warnings']:
            self.assertIn('top_domains', item)
            self.assertIsInstance(item['top_domains'], list)

# ── /api/domains ──────────────────────────────────────────────────────────────

class TestApiDomains(DashboardTestCase):

    def test_returns_200(self):
        status, _ = self.get_json(f'/api/domains?date={TODAY}')
        self.assertEqual(status, 200)

    def test_returns_list(self):
        _, data = self.get_json(f'/api/domains?date={TODAY}')
        self.assertIsInstance(data, list)

    def test_limit_respected(self):
        _, data = self.get_json(f'/api/domains?date={TODAY}&limit=1')
        self.assertLessEqual(len(data), 1)

    def test_limit_clamped_at_100(self):
        # Requesting 9999 should silently cap at 100
        _, data = self.get_json(f'/api/domains?date={TODAY}&limit=9999')
        self.assertLessEqual(len(data), 100)

    def test_bad_limit_falls_back_to_default(self):
        # Non-numeric limit must not crash the server
        status, _ = self.get_json(f'/api/domains?date={TODAY}&limit=abc')
        self.assertEqual(status, 200)


# ── /api/hourly ───────────────────────────────────────────────────────────────

class TestApiHourly(DashboardTestCase):

    def test_returns_200(self):
        status, _ = self.get_json(f'/api/hourly?date={TODAY}')
        self.assertEqual(status, 200)

    def test_returns_dict_keyed_by_ip(self):
        _, data = self.get_json(f'/api/hourly?date={TODAY}')
        self.assertIsInstance(data, dict)

    def test_each_entry_has_hours_list(self):
        _, data = self.get_json(f'/api/hourly?date={TODAY}')
        for ip, entry in data.items():
            self.assertIn('hours', entry)
            self.assertIsInstance(entry['hours'], list)


# ── /api/trend ────────────────────────────────────────────────────────────────

class TestApiTrend(DashboardTestCase):

    def test_returns_200(self):
        status, _ = self.get_json('/api/trend?days=7')
        self.assertEqual(status, 200)

    def test_returns_list(self):
        _, data = self.get_json('/api/trend?days=7')
        self.assertIsInstance(data, list)

    def test_days_clamped_at_365(self):
        # days=99999 must not crash
        status, _ = self.get_json('/api/trend?days=99999')
        self.assertEqual(status, 200)

    def test_bad_days_falls_back_to_default(self):
        status, _ = self.get_json('/api/trend?days=xyz')
        self.assertEqual(status, 200)

    def test_includes_today_in_results(self):
        _, data = self.get_json('/api/trend?days=7')
        dates = [r['date'] for r in data]
        self.assertIn(TODAY, dates)


# ── /api/new_domains ──────────────────────────────────────────────────────────

class TestApiNewDomains(DashboardTestCase):

    def test_returns_200(self):
        status, _ = self.get_json(f'/api/new_domains?date={TODAY}')
        self.assertEqual(status, 200)

    def test_returns_list(self):
        _, data = self.get_json(f'/api/new_domains?date={TODAY}')
        self.assertIsInstance(data, list)

    def test_youtube_not_new(self):
        # youtube.com appears in YESTERDAY data so it is not new today
        _, data = self.get_json(f'/api/new_domains?date={TODAY}')
        domains = [r['domain'] for r in data]
        # github.com is only in yesterday; facebook.com / netflix.com are new today
        self.assertNotIn('github.com', domains)


if __name__ == '__main__':
    unittest.main()
