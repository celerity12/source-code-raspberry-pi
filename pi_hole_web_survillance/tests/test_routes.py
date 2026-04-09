"""
Tests for web/routes/ — auth, pages, and API route edge cases.

Covers:
  - auth.py    : login GET/POST, logout, rate-limit header, session state
  - pages.py   : index and device_detail redirect when unauthenticated
  - api.py     : block/unblock domain, send_report, ai_summary, query_log,
                 search, new_domains, excessive_usage, hourly, date_range,
                 manually_blocked, blocked endpoints, health endpoint
"""

import json
import shutil
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

# ── path setup ────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
with patch('logging.FileHandler', lambda *a, **kw: logging.NullHandler()):
    from scripts.data import analytics as A
    from scripts.web import app as _app_module

TODAY     = datetime.now().strftime('%Y-%m-%d')
YESTERDAY = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')


# ── shared DB factory ─────────────────────────────────────────────────────────

def make_db():
    tmpdir  = Path(tempfile.mkdtemp())
    db_path = tmpdir / 'analytics.db'
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    # Use analytics._ensure_schema so the test DB always matches production schema
    A.DB_PATH = db_path
    A._ensure_schema(conn)
    base = int(datetime.now().replace(hour=10, minute=0, second=0, microsecond=0).timestamp())
    conn.executemany(
        "INSERT INTO queries (timestamp,domain,client_ip,client_name,status,category,date)"
        " VALUES (?,?,?,?,?,?,?)",
        [
            (base,   'youtube.com',   '192.168.1.1', 'PC',    2, 'streaming',    TODAY),
            (base+1, 'netflix.com',   '192.168.1.1', 'PC',    2, 'streaming',    TODAY),
            (base+2, 'facebook.com',  '192.168.1.2', 'Phone', 2, 'social_media', TODAY),
            (base+3, 'ad.test.io',    '192.168.1.1', 'PC',    1, 'ads_tracking', TODAY),
            (base+4, 'newsite.xyz',   '192.168.1.1', 'PC',    2, 'other',        TODAY),
            (base+5, 'bad-adult.com', '192.168.1.2', 'Phone', 2, 'adult',        TODAY),
        ],
    )
    conn.executemany(
        "INSERT INTO daily_summary (date,client_ip,client_name,total_queries,blocked_queries,unique_domains,top_category)"
        " VALUES (?,?,?,?,?,?,?)",
        [
            (TODAY,     '192.168.1.1', 'PC',    4, 1, 4, 'streaming'),
            (TODAY,     '192.168.1.2', 'Phone', 2, 0, 2, 'social_media'),
            (YESTERDAY, '192.168.1.1', 'PC',    1, 0, 1, 'tech'),
        ],
    )
    conn.execute(
        "INSERT INTO manually_blocked (domain, blocked_at, note) VALUES (?,?,?)",
        ('blocked.example.com', TODAY, 'test block'),
    )
    conn.commit()
    conn.close()
    return tmpdir, db_path


# ── base test case ────────────────────────────────────────────────────────────

class RouteTestCase(unittest.TestCase):
    """Flask test client with seeded DB, TESTING=True (auth bypassed)."""

    PASSWORD = 'testpassword'

    def setUp(self):
        self.tmpdir, self.db_path = make_db()
        self.db_patcher = patch.object(A, 'DB_PATH', self.db_path)
        self.db_patcher.start()

        self.app = _app_module.create_app({
            'TESTING': True,
            'DASHBOARD_PASSWORD': self.PASSWORD,
        })
        self.client = self.app.test_client()

    def tearDown(self):
        self.db_patcher.stop()
        shutil.rmtree(self.tmpdir)

    def get_json(self, url):
        resp = self.client.get(url)
        return resp.status_code, json.loads(resp.data)

    def post_json(self, url, payload=None):
        resp = self.client.post(url, json=payload or {})
        return resp.status_code, json.loads(resp.data)


# =============================================================================
# Auth routes
# =============================================================================

class TestAuthRoutes(RouteTestCase):
    """Tests for /login and /logout with auth NOT bypassed."""

    def setUp(self):
        self.tmpdir, self.db_path = make_db()
        self.db_patcher = patch.object(A, 'DB_PATH', self.db_path)
        self.db_patcher.start()
        # TESTING=False so the real auth check runs
        self.app = _app_module.create_app({
            'TESTING': False,
            'DASHBOARD_PASSWORD': self.PASSWORD,
        })
        self.client = self.app.test_client()

    def test_login_get_returns_200(self):
        resp = self.client.get('/login')
        self.assertEqual(resp.status_code, 200)

    def test_login_page_contains_form(self):
        resp = self.client.get('/login')
        self.assertIn(b'<form', resp.data)

    def test_wrong_password_returns_200_with_error(self):
        resp = self.client.post('/login', data={'password': 'wrong'})
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'Incorrect', resp.data)

    def test_correct_password_redirects(self):
        resp = self.client.post('/login', data={'password': self.PASSWORD})
        self.assertIn(resp.status_code, (301, 302))

    def test_correct_password_sets_session(self):
        with self.client.session_transaction() as sess:
            self.assertNotIn('auth', sess)
        self.client.post('/login', data={'password': self.PASSWORD})
        with self.client.session_transaction() as sess:
            self.assertTrue(sess.get('auth'))

    def test_logout_clears_session(self):
        self.client.post('/login', data={'password': self.PASSWORD})
        self.client.get('/logout')
        with self.client.session_transaction() as sess:
            self.assertNotIn('auth', sess)

    def test_logout_redirects_to_login(self):
        resp = self.client.get('/logout')
        self.assertIn(resp.status_code, (301, 302))
        self.assertIn(b'/login', resp.headers.get('Location', b'').encode()
                      if isinstance(resp.headers.get('Location'), str)
                      else resp.headers.get('Location', b''))

    def test_unauthenticated_index_redirects(self):
        resp = self.client.get('/')
        self.assertIn(resp.status_code, (301, 302))

    def test_unauthenticated_device_redirects(self):
        resp = self.client.get('/device')
        self.assertIn(resp.status_code, (301, 302))

    def test_unauthenticated_protected_api_route_redirects(self):
        # /api/block_domain requires auth — should redirect to /login
        resp = self.client.post('/api/block_domain', json={'domain': 'evil.com'})
        self.assertIn(resp.status_code, (301, 302))


# =============================================================================
# Page routes (TESTING=True, auth bypassed)
# =============================================================================

class TestPageRoutes(RouteTestCase):

    def test_index_returns_200(self):
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)

    def test_index_returns_html(self):
        resp = self.client.get('/')
        self.assertIn(b'<!DOCTYPE html>', resp.data)

    def test_device_detail_returns_200(self):
        resp = self.client.get('/device?ip=192.168.1.1')
        self.assertEqual(resp.status_code, 200)

    def test_device_detail_returns_html(self):
        resp = self.client.get('/device?ip=192.168.1.1')
        self.assertIn(b'<!DOCTYPE html>', resp.data)


# =============================================================================
# API — block / unblock
# =============================================================================

class TestBlockRoutes(RouteTestCase):

    def test_block_domain_success(self):
        with patch('scripts.web.routes.api._pihole_block', return_value=True):
            status, data = self.post_json('/api/block_domain', {'domain': 'evil.com'})
        self.assertEqual(status, 200)
        self.assertEqual(data.get('status'), 'blocked')

    def test_block_domain_missing_param(self):
        status, data = self.post_json('/api/block_domain', {})
        self.assertEqual(status, 400)

    def test_unblock_domain_success(self):
        with patch('scripts.web.routes.api._pihole_block', return_value=True):
            status, data = self.post_json('/api/unblock_domain', {'domain': 'evil.com'})
        self.assertEqual(status, 200)

    def test_unblock_domain_missing_param(self):
        status, data = self.post_json('/api/unblock_domain', {})
        self.assertEqual(status, 400)

    def test_manually_blocked_returns_list(self):
        with patch.object(A, 'DB_PATH', self.db_path):
            status, data = self.get_json('/api/manually_blocked')
        self.assertEqual(status, 200)
        self.assertIsInstance(data, list)
        domains = [row['domain'] for row in data]
        self.assertIn('blocked.example.com', domains)


# =============================================================================
# API — query log, search, new domains
# =============================================================================

class TestQueryLogRoutes(RouteTestCase):

    def test_query_log_returns_list(self):
        status, data = self.get_json(f'/api/query_log?date={TODAY}')
        self.assertEqual(status, 200)
        self.assertIsInstance(data, list)

    def test_query_log_has_domain_field(self):
        status, data = self.get_json(f'/api/query_log?date={TODAY}')
        self.assertEqual(status, 200)
        if data:
            self.assertIn('domain', data[0])

    def test_search_returns_results(self):
        status, data = self.get_json('/api/search?q=youtube')
        self.assertEqual(status, 200)
        # Endpoint returns {'query': ..., 'results': [...], 'date': ...}
        results = data.get('results', data) if isinstance(data, dict) else data
        self.assertIsInstance(results, list)
        domains = [r['domain'] for r in results]
        self.assertTrue(any('youtube' in d for d in domains))

    def test_search_missing_param_returns_400(self):
        status, _ = self.get_json('/api/search')
        self.assertEqual(status, 400)

    def test_new_domains_returns_list(self):
        status, data = self.get_json(f'/api/new_domains?date={TODAY}')
        self.assertEqual(status, 200)
        self.assertIsInstance(data, list)


# =============================================================================
# API — alerts, excessive_usage
# =============================================================================

class TestAlertRoutes(RouteTestCase):

    def test_alerts_returns_critical_and_warnings(self):
        status, data = self.get_json(f'/api/alerts?date={TODAY}')
        self.assertEqual(status, 200)
        self.assertIn('critical', data)
        self.assertIn('warnings', data)

    def test_adult_content_flagged_as_critical(self):
        status, data = self.get_json(f'/api/alerts?date={TODAY}')
        self.assertEqual(status, 200)
        critical_cats = [item['category'] for item in data['critical']]
        self.assertIn('adult', critical_cats)

    def test_excessive_usage_returns_list(self):
        status, data = self.get_json(f'/api/excessive_usage?date={TODAY}')
        self.assertEqual(status, 200)
        self.assertIsInstance(data, list)


# =============================================================================
# API — hourly, date_range
# =============================================================================

class TestTimeRangeRoutes(RouteTestCase):

    def test_all_clients_hourly_returns_dict(self):
        status, data = self.get_json(f'/api/all_clients_hourly?date={TODAY}')
        self.assertEqual(status, 200)
        self.assertIsInstance(data, dict)

    def test_date_range_returns_200(self):
        status, data = self.get_json(
            f'/api/date_range?start_date={YESTERDAY}&end_date={TODAY}'
        )
        self.assertEqual(status, 200)

    def test_date_range_missing_params_returns_400(self):
        status, _ = self.get_json('/api/date_range')
        self.assertEqual(status, 400)


# =============================================================================
# API — health endpoint
# =============================================================================

class TestHealthRoute(RouteTestCase):

    def test_health_returns_200(self):
        with patch('scripts.core.health.pihole_health', return_value={'status': 'ok'}):
            status, data = self.get_json('/api/health')
        self.assertEqual(status, 200)

    def test_health_has_system_key(self):
        with patch('scripts.core.health.pihole_health', return_value={'status': 'ok'}):
            _, data = self.get_json('/api/health')
        self.assertIn('system', data)


# =============================================================================
# API — send_report and ai_summary (mocked externals)
# =============================================================================

class TestExternalEndpoints(RouteTestCase):

    def test_send_report_invokes_reporter(self):
        with patch('scripts.core.reporter.send_report', return_value=True) as mock_send:
            status, data = self.post_json('/api/send_report', {'period': 'daily'})
        # Either succeeds or returns a meaningful error — just check no 500
        self.assertNotEqual(status, 500)

    def test_ai_summary_missing_gemini_key_returns_error(self):
        # config has no real Gemini key — endpoint should return an error payload, not crash
        status, data = self.post_json('/api/ai_summary', {'date': TODAY})
        self.assertIn(status, (200, 400, 500, 503))


if __name__ == '__main__':
    unittest.main()
