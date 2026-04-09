"""
Comprehensive tests for pihole-mcp-server.

Covers:
  - config/loader.py           — path resolution, missing file errors
  - connectors/pihole_client   — all API methods (mocked HTTP)
  - connectors/telegram_client — all methods (mocked HTTP)
  - mcp/server.py              — tool list, every tool handler, error handling
  - llm/gemini_agent.py        — _mcp_to_gemini_tool, _map_type, config loading

Run:
    python3 -m pytest tests/test_all.py -v
"""

import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

# ── ensure project root is on path ──────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


# ═══════════════════════════════════════════════════════════════════════════
# 1. config/loader.py
# ═══════════════════════════════════════════════════════════════════════════

class TestConfigLoader(unittest.TestCase):

    def setUp(self):
        import importlib, config.loader as m
        importlib.reload(m)
        self.loader = m

    def test_load_connector_pihole_exists(self):
        """load_connector('pihole') returns a dict with url and password."""
        cfg = self.loader.load_connector('pihole')
        self.assertIsInstance(cfg, dict)
        self.assertIn('url', cfg)
        self.assertIn('password', cfg)

    def test_load_connector_telegram_exists(self):
        """load_connector('telegram') returns a dict with bot_token."""
        cfg = self.loader.load_connector('telegram')
        self.assertIsInstance(cfg, dict)
        self.assertIn('bot_token', cfg)
        self.assertIn('default_chat_id', cfg)

    def test_load_mcp(self):
        """load_mcp() returns server_name and log_level."""
        cfg = self.loader.load_mcp()
        self.assertIsInstance(cfg, dict)
        self.assertIn('server_name', cfg)
        self.assertIn('log_level', cfg)

    def test_load_prompts(self):
        """load_prompts() returns system_prompt, watch_prompt, interval."""
        cfg = self.loader.load_prompts()
        self.assertIsInstance(cfg, dict)
        self.assertIn('system_prompt', cfg)
        self.assertIn('watch_prompt', cfg)
        self.assertIn('watch_interval_minutes', cfg)
        self.assertIsInstance(cfg['watch_interval_minutes'], int)

    def test_load_llm_example_values_are_placeholders(self):
        """gemini.yaml still has placeholder — verify loader doesn't crash."""
        cfg = self.loader.load_llm()
        self.assertIsInstance(cfg, dict)
        self.assertIn('api_key', cfg)
        self.assertIn('model', cfg)

    def test_missing_file_raises_file_not_found(self):
        """_load() raises FileNotFoundError for a non-existent config."""
        with self.assertRaises(FileNotFoundError) as ctx:
            self.loader.load_connector('nonexistent')
        self.assertIn('nonexistent', str(ctx.exception))

    def test_error_message_includes_path(self):
        """FileNotFoundError message includes the expected path fragment."""
        try:
            self.loader.load_connector('missing')
        except FileNotFoundError as e:
            self.assertIn('missing', str(e))


# ═══════════════════════════════════════════════════════════════════════════
# 2. connectors/pihole_client.py
# ═══════════════════════════════════════════════════════════════════════════

def _make_pihole():
    """Return a PiholeClient with a mocked requests.Session."""
    from connectors.pihole_client import PiholeClient
    with patch('connectors.pihole_client.requests.Session') as MockSession:
        sess = MockSession.return_value
        # login succeeds
        sess.post.return_value = MagicMock(ok=True, status_code=200)
        sess.post.return_value.raise_for_status = MagicMock()
        client = PiholeClient('http://localhost:8080', 'testpass')
        client.session = sess          # replace with the mock
        return client, sess


def _json_resp(data):
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json.return_value = data
    return m


class TestPiholeClientAuth(unittest.TestCase):

    def test_login_called_on_init(self):
        from connectors.pihole_client import PiholeClient
        with patch('connectors.pihole_client.requests.Session') as MockSession:
            sess = MockSession.return_value
            sess.post.return_value = MagicMock(raise_for_status=MagicMock())
            PiholeClient('http://localhost:8080', 'secret')
            sess.post.assert_called_once()
            call_kwargs = sess.post.call_args
            self.assertIn('/login', call_kwargs[0][0])

    def test_login_raises_on_failure(self):
        from connectors.pihole_client import PiholeClient
        import requests as req
        with patch('connectors.pihole_client.requests.Session') as MockSession:
            sess = MockSession.return_value
            resp = MagicMock()
            resp.raise_for_status.side_effect = req.HTTPError("401")
            sess.post.return_value = resp
            with self.assertRaises(req.HTTPError):
                PiholeClient('http://localhost:8080', 'wrong')


class TestPiholeClientMethods(unittest.TestCase):

    def setUp(self):
        self.client, self.sess = _make_pihole()

    def _mock_get(self, data):
        self.sess.get.return_value = _json_resp(data)

    def _mock_post(self, data):
        self.sess.post.return_value = _json_resp(data)

    # ── overview ──────────────────────────────────────────────────────────

    def test_stats(self):
        self._mock_get({'summary': {}, 'categories': []})
        result = self.client.stats()
        self.assertIn('summary', result)
        self.sess.get.assert_called_once()
        self.assertIn('/api/stats', self.sess.get.call_args[0][0])

    def test_stats_with_date_range(self):
        self._mock_get({'summary': {}})
        self.client.stats(date='2025-01-01', end_date='2025-01-07')
        params = self.sess.get.call_args[1]['params']
        self.assertEqual(params['date'], '2025-01-01')
        self.assertEqual(params['end_date'], '2025-01-07')

    def test_summary(self):
        self._mock_get({'total_queries': 100})
        result = self.client.summary(date='2025-01-01')
        self.assertEqual(result['total_queries'], 100)

    def test_compare(self):
        self._mock_get({'today': {}, 'yesterday': {}})
        self.client.compare()
        self.assertIn('/api/compare', self.sess.get.call_args[0][0])

    def test_trend(self):
        self._mock_get([{'date': '2025-01-01', 'queries': 500}])
        result = self.client.trend()
        self.assertIsInstance(result, list)

    def test_health(self):
        self._mock_get({'disk_percent': 42, 'ram_percent': 30})
        result = self.client.health()
        self.assertEqual(result['disk_percent'], 42)

    # ── devices ───────────────────────────────────────────────────────────

    def test_devices(self):
        self._mock_get([{'client_ip': '192.168.1.1'}])
        result = self.client.devices()
        self.assertIsInstance(result, list)

    def test_device_registry(self):
        self._mock_get([{'mac': 'aa:bb:cc:dd:ee:ff', 'name': 'TestDevice'}])
        result = self.client.device_registry()
        self.assertIsInstance(result, list)

    def test_device_detail_sends_ip(self):
        self._mock_get({'client_ip': '10.0.0.1', 'categories': []})
        self.client.device_detail('10.0.0.1')
        params = self.sess.get.call_args[1]['params']
        self.assertEqual(params['ip'], '10.0.0.1')

    def test_device_hourly(self):
        self._mock_get([{'hour': 8, 'queries': 20}])
        result = self.client.device_hourly('10.0.0.1')
        self.assertIsInstance(result, list)

    def test_device_domains(self):
        self._mock_get([{'domain': 'example.com'}])
        result = self.client.device_domains('10.0.0.1', limit=10)
        params = self.sess.get.call_args[1]['params']
        self.assertEqual(params['limit'], 10)

    def test_all_clients_hourly(self):
        self._mock_get({'10.0.0.1': [0] * 24})
        self.client.all_clients_hourly()
        self.assertIn('/api/all_clients_hourly', self.sess.get.call_args[0][0])

    def test_client_category_usage(self):
        self._mock_get({'streaming': 100})
        self.client.client_category_usage(ip='10.0.0.1')
        params = self.sess.get.call_args[1]['params']
        self.assertEqual(params['ip'], '10.0.0.1')

    def test_date_range(self):
        self._mock_get([])
        self.client.date_range('2025-01-01', '2025-01-07')
        params = self.sess.get.call_args[1]['params']
        self.assertEqual(params['start_date'], '2025-01-01')
        self.assertEqual(params['end_date'], '2025-01-07')

    # ── categories ────────────────────────────────────────────────────────

    def test_categories(self):
        self._mock_get([{'category': 'streaming', 'queries': 200}])
        result = self.client.categories()
        self.assertIsInstance(result, list)

    def test_top_by_category(self):
        self._mock_get([{'domain': 'netflix.com'}])
        self.client.top_by_category('streaming', limit=5)
        params = self.sess.get.call_args[1]['params']
        self.assertEqual(params['category'], 'streaming')
        self.assertEqual(params['limit'], 5)

    def test_categorization_stats(self):
        self._mock_get({'categorized': 900, 'uncategorized': 100})
        self.client.categorization_stats()
        self.assertIn('/api/categorization_stats', self.sess.get.call_args[0][0])

    def test_uncategorized_domains(self):
        self._mock_get([{'domain': 'mystery.io'}])
        result = self.client.uncategorized_domains(limit=5)
        params = self.sess.get.call_args[1]['params']
        self.assertEqual(params['limit'], 5)

    # ── alerts ────────────────────────────────────────────────────────────

    def test_alerts(self):
        self._mock_get([{'category': 'adult', 'title': 'Adult content'}])
        result = self.client.alerts()
        self.assertIsInstance(result, list)

    def test_excessive_usage(self):
        self._mock_get([])
        self.client.excessive_usage(threshold_minutes=30)
        params = self.sess.get.call_args[1]['params']
        self.assertEqual(params['threshold_minutes'], 30)

    def test_blocked_summary(self):
        self._mock_get({'blocked': 500, 'allowed': 10000})
        self.client.blocked_summary()
        self.assertIn('/api/blocked_summary', self.sess.get.call_args[0][0])

    def test_blocked_top(self):
        self._mock_get([{'domain': 'ads.example.com'}])
        result = self.client.blocked_top()
        self.assertIsInstance(result, list)

    def test_manually_blocked(self):
        self._mock_get([{'domain': 'tracker.io'}])
        self.client.manually_blocked()
        self.assertIn('/api/manually_blocked', self.sess.get.call_args[0][0])

    # ── blocking ─────────────────────────────────────────────────────────

    def test_block_domain(self):
        self._mock_post({'status': 'blocked'})
        result = self.client.block_domain('ads.example.com')
        self.sess.post.assert_called()
        call_args = self.sess.post.call_args
        self.assertIn('/api/block_domain', call_args[0][0])
        self.assertEqual(call_args[1]['json']['domain'], 'ads.example.com')

    def test_unblock_domain(self):
        self._mock_post({'status': 'unblocked'})
        self.client.unblock_domain('ads.example.com')
        call_args = self.sess.post.call_args
        self.assertIn('/api/unblock_domain', call_args[0][0])

    def test_send_report(self):
        self._mock_post({'status': 'sent'})
        self.client.send_report('weekly')
        call_args = self.sess.post.call_args
        self.assertIn('/api/send_report', call_args[0][0])
        self.assertEqual(call_args[1]['json']['period'], 'weekly')

    # ── search & log ──────────────────────────────────────────────────────

    def test_search(self):
        self._mock_get({'results': [{'domain': 'netflix.com'}]})
        self.client.search('netflix')
        params = self.sess.get.call_args[1]['params']
        self.assertEqual(params['q'], 'netflix')

    def test_query_log_blocked_filter(self):
        self._mock_get([])
        self.client.query_log(blocked=True)
        params = self.sess.get.call_args[1]['params']
        self.assertEqual(params['blocked'], '1')

    def test_query_log_not_blocked_omitted(self):
        self._mock_get([])
        self.client.query_log(blocked=False)
        params = self.sess.get.call_args[1]['params']
        self.assertNotIn('blocked', params)

    def test_new_domains(self):
        self._mock_get([{'domain': 'new-site.com'}])
        result = self.client.new_domains()
        self.assertIsInstance(result, list)

    # ── none params are stripped ──────────────────────────────────────────

    def test_none_params_not_sent(self):
        self._mock_get({})
        self.client.stats(date=None, end_date=None)
        params = self.sess.get.call_args[1]['params']
        self.assertNotIn('date', params)
        self.assertNotIn('end_date', params)


# ═══════════════════════════════════════════════════════════════════════════
# 3. connectors/telegram_client.py
# ═══════════════════════════════════════════════════════════════════════════

def _make_telegram():
    from connectors.telegram_client import TelegramClient
    client = TelegramClient(bot_token='fake:token', default_chat_id='12345')
    return client


def _tg_ok(result):
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json.return_value = {'ok': True, 'result': result}
    return m


def _tg_err():
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json.return_value = {'ok': False, 'description': 'Bad request'}
    return m


class TestTelegramClient(unittest.TestCase):

    def setUp(self):
        self.client = _make_telegram()

    def test_send_message_basic(self):
        with patch('connectors.telegram_client.requests.post') as mock_post:
            mock_post.return_value = _tg_ok({'message_id': 1})
            result = self.client.send_message('Hello')
            self.assertEqual(result['message_id'], 1)
            payload = mock_post.call_args[1]['json']
            self.assertEqual(payload['text'], 'Hello')
            self.assertEqual(payload['chat_id'], '12345')

    def test_send_message_custom_chat(self):
        with patch('connectors.telegram_client.requests.post') as mock_post:
            mock_post.return_value = _tg_ok({})
            self.client.send_message('Hi', chat_id='99999')
            payload = mock_post.call_args[1]['json']
            self.assertEqual(payload['chat_id'], '99999')

    def test_send_message_html_parse_mode(self):
        with patch('connectors.telegram_client.requests.post') as mock_post:
            mock_post.return_value = _tg_ok({})
            self.client.send_message('Hi')
            payload = mock_post.call_args[1]['json']
            self.assertEqual(payload['parse_mode'], 'HTML')

    def test_api_error_raises_runtime_error(self):
        with patch('connectors.telegram_client.requests.post') as mock_post:
            mock_post.return_value = _tg_err()
            with self.assertRaises(RuntimeError) as ctx:
                self.client.send_message('Hello')
            self.assertIn('Telegram error', str(ctx.exception))

    def test_get_me(self):
        with patch('connectors.telegram_client.requests.post') as mock_post:
            mock_post.return_value = _tg_ok({'username': 'testbot'})
            result = self.client.get_me()
            self.assertEqual(result['username'], 'testbot')
            call_url = mock_post.call_args[0][0]
            self.assertIn('getMe', call_url)

    def test_get_updates_default_limit(self):
        with patch('connectors.telegram_client.requests.post') as mock_post:
            mock_post.return_value = _tg_ok([])
            self.client.get_updates()
            payload = mock_post.call_args[1]['json']
            self.assertEqual(payload['limit'], 10)

    def test_get_updates_with_offset(self):
        with patch('connectors.telegram_client.requests.post') as mock_post:
            mock_post.return_value = _tg_ok([])
            self.client.get_updates(offset=42)
            payload = mock_post.call_args[1]['json']
            self.assertEqual(payload['offset'], 42)

    def test_send_alert_warning(self):
        with patch.object(self.client, 'send_message') as mock_send:
            mock_send.return_value = {}
            self.client.send_alert('Title', 'Body', level='warning')
            text = mock_send.call_args[0][0]
            self.assertIn('⚠️', text)
            self.assertIn('Title', text)
            self.assertIn('Body', text)

    def test_send_alert_critical(self):
        with patch.object(self.client, 'send_message') as mock_send:
            mock_send.return_value = {}
            self.client.send_alert('Breach', 'Details', level='critical')
            text = mock_send.call_args[0][0]
            self.assertIn('🚨', text)

    def test_send_alert_info(self):
        with patch.object(self.client, 'send_message') as mock_send:
            mock_send.return_value = {}
            self.client.send_alert('Note', 'Info', level='info')
            text = mock_send.call_args[0][0]
            self.assertIn('ℹ️', text)

    def test_send_network_summary_format(self):
        stats = {
            'summary': {
                'total_queries': 10000,
                'blocked_queries': 500,
                'active_clients': 8,
                'unique_domains': 2000,
            },
            'categories': [
                {'category': 'streaming', 'queries': 3000},
                {'category': 'social_media', 'queries': 1500},
            ],
            'top_domains': [
                {'domain': 'netflix.com', 'queries': 2500},
            ],
            'date': '2025-01-01',
        }
        with patch.object(self.client, 'send_message') as mock_send:
            mock_send.return_value = {}
            self.client.send_network_summary(stats)
            text = mock_send.call_args[0][0]
            self.assertIn('10,000', text)
            self.assertIn('500', text)
            self.assertIn('streaming', text)
            self.assertIn('netflix.com', text)

    def test_send_network_summary_zero_queries(self):
        """Zero total_queries must not cause a division-by-zero."""
        stats = {
            'summary': {'total_queries': 0, 'blocked_queries': 0,
                        'active_clients': 0, 'unique_domains': 0},
            'categories': [], 'top_domains': [],
        }
        with patch.object(self.client, 'send_message') as mock_send:
            mock_send.return_value = {}
            self.client.send_network_summary(stats)   # should not raise
            mock_send.assert_called_once()

    def test_send_security_alerts_with_items(self):
        alerts = [
            {'icon': '🔞', 'title': 'Adult content', 'short': '3 devices'},
            {'icon': '🎰', 'title': 'Gambling', 'short': '1 device'},
        ]
        with patch.object(self.client, 'send_message') as mock_send:
            mock_send.return_value = {}
            self.client.send_security_alerts(alerts)
            text = mock_send.call_args[0][0]
            self.assertIn('Adult content', text)
            self.assertIn('Gambling', text)

    def test_send_security_alerts_empty(self):
        with patch.object(self.client, 'send_message') as mock_send:
            mock_send.return_value = {}
            self.client.send_security_alerts([])
            text = mock_send.call_args[0][0]
            self.assertIn('No security alerts', text)

    def test_send_device_summary(self):
        device = {'client_ip': '10.0.0.5', 'total_queries': 300,
                  'blocked_queries': 10, 'unique_domains': 80}
        detail = {'categories': [{'category': 'streaming', 'queries': 200}]}
        with patch.object(self.client, 'send_message') as mock_send:
            mock_send.return_value = {}
            self.client.send_device_summary(device, detail)
            text = mock_send.call_args[0][0]
            self.assertIn('10.0.0.5', text)
            self.assertIn('300', text)
            self.assertIn('streaming', text)

    def test_send_health_status_all_green(self):
        health = {'disk_percent': 30, 'ram_percent': 40,
                  'cpu_percent': 10, 'temperature': 45,
                  'pihole_blocking': True}
        with patch.object(self.client, 'send_message') as mock_send:
            mock_send.return_value = {}
            self.client.send_health_status(health)
            text = mock_send.call_args[0][0]
            self.assertIn('ON', text)
            self.assertIn('30%', text)
            self.assertIn('🟢', text)

    def test_send_health_status_critical_disk(self):
        health = {'disk_percent': 90, 'ram_percent': 20,
                  'cpu_percent': 5, 'temperature': 38,
                  'pihole_blocking': True}
        with patch.object(self.client, 'send_message') as mock_send:
            mock_send.return_value = {}
            self.client.send_health_status(health)
            text = mock_send.call_args[0][0]
            self.assertIn('🔴', text)

    def test_send_health_pihole_off(self):
        health = {'disk_percent': 20, 'ram_percent': 20,
                  'cpu_percent': 5, 'temperature': 38,
                  'pihole_blocking': False}
        with patch.object(self.client, 'send_message') as mock_send:
            mock_send.return_value = {}
            self.client.send_health_status(health)
            text = mock_send.call_args[0][0]
            self.assertIn('OFF', text)


# ═══════════════════════════════════════════════════════════════════════════
# 4. mcp/server.py — tool list and every handler
# ═══════════════════════════════════════════════════════════════════════════

def _load_server_module():
    """
    Import mcp/server.py with PiholeClient and TelegramClient mocked out
    so it never tries to make real HTTP connections.

    The project's mcp/ directory shadows the installed 'mcp' library when
    running from the repo root.  We work around this by:
      1. Temporarily removing ROOT from sys.path so 'mcp' resolves to the
         installed library (needed for 'from mcp.server import Server' etc.)
      2. Loading our mcp/server.py via importlib.util.spec_from_file_location
         under an alias name so it doesn't collide with the library module.
    """
    import importlib.util

    pihole_mock   = MagicMock()
    telegram_mock = MagicMock()

    loader_mock = MagicMock()
    loader_mock.load_mcp.return_value = {
        'server_name': 'test-server', 'log_level': 'ERROR'
    }
    loader_mock.load_connector.side_effect = lambda name: (
        {'url': 'http://localhost:8080', 'password': 'x'} if name == 'pihole'
        else {'bot_token': 'tok', 'default_chat_id': '1'}
    )

    # Stub connectors so PiholeClient() / TelegramClient() never do real I/O
    pihole_mod   = MagicMock()
    telegram_mod = MagicMock()
    pihole_mod.PiholeClient.return_value   = pihole_mock
    telegram_mod.TelegramClient.return_value = telegram_mock

    # Remove ROOT from sys.path while loading so 'mcp' → installed library
    clean_path = [p for p in sys.path if p != str(ROOT)]

    server_path = ROOT / 'mcp' / 'server.py'
    spec = importlib.util.spec_from_file_location('pihole_mcp_server', server_path)
    mod  = importlib.util.module_from_spec(spec)

    extra_stubs = {
        'config.loader':              loader_mock,
        'connectors.pihole_client':   pihole_mod,
        'connectors.telegram_client': telegram_mod,
        'pihole_mcp_server':          mod,
    }

    original_path = sys.path[:]
    sys.path = clean_path
    try:
        with patch.dict('sys.modules', extra_stubs):
            spec.loader.exec_module(mod)
    finally:
        sys.path = original_path

    mod._pihole_mock   = pihole_mock
    mod._telegram_mock = telegram_mock
    return mod


class TestMCPToolList(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_server_module()

    def test_tool_count(self):
        # 23 pihole_ + 6 telegram_ = 29
        self.assertEqual(len(self.mod.TOOLS), 29)

    def test_all_tools_have_names(self):
        for tool in self.mod.TOOLS:
            self.assertTrue(tool.name, f"Tool missing name: {tool}")

    def test_all_tools_have_descriptions(self):
        for tool in self.mod.TOOLS:
            self.assertTrue(tool.description,
                            f"Tool '{tool.name}' has no description")

    def test_all_tools_have_input_schema(self):
        for tool in self.mod.TOOLS:
            self.assertIsNotNone(tool.inputSchema,
                                 f"Tool '{tool.name}' has no inputSchema")

    def test_pihole_tools_count(self):
        pihole_tools = [t for t in self.mod.TOOLS if t.name.startswith('pihole_')]
        self.assertEqual(len(pihole_tools), 23)

    def test_telegram_tools_count(self):
        tg_tools = [t for t in self.mod.TOOLS if t.name.startswith('telegram_')]
        self.assertEqual(len(tg_tools), 6)

    def test_no_duplicate_tool_names(self):
        names = [t.name for t in self.mod.TOOLS]
        self.assertEqual(len(names), len(set(names)))

    def test_required_tools_present(self):
        names = {t.name for t in self.mod.TOOLS}
        for expected in ['pihole_stats', 'pihole_alerts', 'pihole_block_domain',
                         'telegram_send_message', 'telegram_send_alert']:
            self.assertIn(expected, names)


class TestMCPToolHandlers(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_server_module()

    def setUp(self):
        # Reset call history and side effects before every test so they
        # don't bleed from one test into the next.
        self.mod._pihole_mock.reset_mock(side_effect=True, return_value=True)
        self.mod._telegram_mock.reset_mock(side_effect=True, return_value=True)

    def _pihole(self):
        return self.mod._pihole_mock

    def _tg(self):
        return self.mod._telegram_mock

    async def _call(self, name, args=None):
        return await self.mod.call_tool(name, args or {})

    # ── overview ──────────────────────────────────────────────────────────

    async def test_pihole_stats(self):
        self._pihole().stats.return_value = {'summary': {}}
        result = await self._call('pihole_stats', {'date': '2025-01-01'})
        self.assertFalse(result.isError)
        self._pihole().stats.assert_called_with('2025-01-01', None)

    async def test_pihole_summary(self):
        self._pihole().summary.return_value = {'total': 100}
        result = await self._call('pihole_summary')
        self.assertFalse(result.isError)

    async def test_pihole_health(self):
        self._pihole().health.return_value = {'disk_percent': 20}
        result = await self._call('pihole_health')
        self.assertFalse(result.isError)
        self._pihole().health.assert_called_once()

    async def test_pihole_alerts(self):
        self._pihole().alerts.return_value = []
        result = await self._call('pihole_alerts', {'date': '2025-01-01'})
        self.assertFalse(result.isError)
        self._pihole().alerts.assert_called_once_with('2025-01-01')

    async def test_pihole_excessive_usage(self):
        self._pihole().excessive_usage.return_value = []
        result = await self._call('pihole_excessive_usage',
                                  {'date': '2025-01-01', 'threshold_minutes': 30})
        self.assertFalse(result.isError)
        self._pihole().excessive_usage.assert_called_once_with('2025-01-01', 30)

    # ── devices ───────────────────────────────────────────────────────────

    async def test_pihole_devices(self):
        self._pihole().devices.return_value = []
        result = await self._call('pihole_devices')
        self.assertFalse(result.isError)

    async def test_pihole_device_registry(self):
        self._pihole().device_registry.return_value = []
        result = await self._call('pihole_device_registry')
        self.assertFalse(result.isError)

    async def test_pihole_device_detail_missing_ip(self):
        result = await self._call('pihole_device_detail', {})
        self.assertTrue(result.isError)
        self.assertIn('ip is required', result.content[0].text)

    async def test_pihole_device_detail_with_ip(self):
        self._pihole().device_detail.return_value = {'client_ip': '10.0.0.1'}
        result = await self._call('pihole_device_detail', {'ip': '10.0.0.1'})
        self.assertFalse(result.isError)
        self._pihole().device_detail.assert_called_once_with('10.0.0.1', None)

    async def test_pihole_device_domains_missing_ip(self):
        result = await self._call('pihole_device_domains', {})
        self.assertTrue(result.isError)

    async def test_pihole_device_domains_with_ip(self):
        self._pihole().device_domains.return_value = []
        result = await self._call('pihole_device_domains',
                                  {'ip': '10.0.0.1', 'limit': 20})
        self.assertFalse(result.isError)
        self._pihole().device_domains.assert_called_once_with('10.0.0.1', None, 20)

    async def test_pihole_client_category_usage(self):
        self._pihole().client_category_usage.return_value = {}
        result = await self._call('pihole_client_category_usage', {'ip': '10.0.0.1'})
        self.assertFalse(result.isError)

    async def test_pihole_date_range_missing_dates(self):
        result = await self._call('pihole_date_range', {'start_date': '2025-01-01'})
        self.assertTrue(result.isError)

    async def test_pihole_date_range_with_dates(self):
        self._pihole().date_range.return_value = []
        result = await self._call('pihole_date_range',
                                  {'start_date': '2025-01-01', 'end_date': '2025-01-07'})
        self.assertFalse(result.isError)

    # ── categories ────────────────────────────────────────────────────────

    async def test_pihole_categories(self):
        self._pihole().categories.return_value = []
        result = await self._call('pihole_categories')
        self.assertFalse(result.isError)

    async def test_pihole_top_by_category_missing_category(self):
        result = await self._call('pihole_top_by_category', {})
        self.assertTrue(result.isError)

    async def test_pihole_top_by_category(self):
        self._pihole().top_by_category.return_value = []
        result = await self._call('pihole_top_by_category', {'category': 'streaming'})
        self.assertFalse(result.isError)
        self._pihole().top_by_category.assert_called_once_with(
            'streaming', None, None, 10)

    async def test_pihole_uncategorized_domains(self):
        self._pihole().uncategorized_domains.return_value = []
        result = await self._call('pihole_uncategorized_domains', {'limit': 5})
        self.assertFalse(result.isError)

    # ── search & log ──────────────────────────────────────────────────────

    async def test_pihole_search_missing_q(self):
        result = await self._call('pihole_search', {})
        self.assertTrue(result.isError)

    async def test_pihole_search(self):
        self._pihole().search.return_value = {'results': []}
        result = await self._call('pihole_search', {'q': 'netflix'})
        self.assertFalse(result.isError)
        self._pihole().search.assert_called_once_with('netflix', None, 50)

    async def test_pihole_query_log(self):
        self._pihole().query_log.return_value = []
        result = await self._call('pihole_query_log', {'blocked': True})
        self.assertFalse(result.isError)

    async def test_pihole_new_domains(self):
        self._pihole().new_domains.return_value = []
        result = await self._call('pihole_new_domains')
        self.assertFalse(result.isError)

    # ── blocking ──────────────────────────────────────────────────────────

    async def test_pihole_blocked_top(self):
        self._pihole().blocked_top.return_value = []
        result = await self._call('pihole_blocked_top')
        self.assertFalse(result.isError)

    async def test_pihole_blocked_summary(self):
        self._pihole().blocked_summary.return_value = {}
        result = await self._call('pihole_blocked_summary')
        self.assertFalse(result.isError)

    async def test_pihole_manually_blocked(self):
        self._pihole().manually_blocked.return_value = []
        result = await self._call('pihole_manually_blocked')
        self.assertFalse(result.isError)

    async def test_pihole_block_domain_missing(self):
        result = await self._call('pihole_block_domain', {})
        self.assertTrue(result.isError)

    async def test_pihole_block_domain(self):
        self._pihole().block_domain.return_value = {'status': 'blocked'}
        result = await self._call('pihole_block_domain', {'domain': 'ads.example.com'})
        self.assertFalse(result.isError)
        self._pihole().block_domain.assert_called_once_with('ads.example.com')

    async def test_pihole_unblock_domain_missing(self):
        result = await self._call('pihole_unblock_domain', {})
        self.assertTrue(result.isError)

    async def test_pihole_unblock_domain(self):
        self._pihole().unblock_domain.return_value = {'status': 'unblocked'}
        result = await self._call('pihole_unblock_domain', {'domain': 'ads.example.com'})
        self.assertFalse(result.isError)

    async def test_pihole_send_report_default(self):
        self._pihole().send_report.return_value = {'status': 'sent'}
        result = await self._call('pihole_send_report', {})
        self.assertFalse(result.isError)
        self._pihole().send_report.assert_called_once_with('daily')

    async def test_pihole_send_report_weekly(self):
        self._pihole().send_report.return_value = {'status': 'sent'}
        await self._call('pihole_send_report', {'period': 'weekly'})
        self._pihole().send_report.assert_called_with('weekly')

    # ── telegram ──────────────────────────────────────────────────────────

    async def test_telegram_send_message_missing_text(self):
        result = await self._call('telegram_send_message', {})
        self.assertTrue(result.isError)

    async def test_telegram_send_message(self):
        self._tg().send_message.return_value = {'message_id': 99}
        result = await self._call('telegram_send_message', {'text': 'Hello'})
        self.assertFalse(result.isError)
        self._tg().send_message.assert_called_once_with('Hello', chat_id=None)

    async def test_telegram_send_alert(self):
        self._tg().send_alert.return_value = {}
        result = await self._call('telegram_send_alert',
                                  {'title': 'T', 'body': 'B', 'level': 'critical'})
        self.assertFalse(result.isError)
        self._tg().send_alert.assert_called_once_with('T', 'B', 'critical', None)

    async def test_telegram_send_network_summary(self):
        self._pihole().stats.return_value = {'summary': {}}
        self._tg().send_network_summary.return_value = {}
        result = await self._call('telegram_send_network_summary', {'date': '2025-01-01'})
        self.assertFalse(result.isError)
        self._pihole().stats.assert_called_with('2025-01-01')

    async def test_telegram_send_security_alerts(self):
        self._pihole().alerts.return_value = []
        self._tg().send_security_alerts.return_value = {}
        result = await self._call('telegram_send_security_alerts')
        self.assertFalse(result.isError)

    async def test_telegram_send_health(self):
        self._pihole().health.return_value = {}
        self._tg().send_health_status.return_value = {}
        result = await self._call('telegram_send_health')
        self.assertFalse(result.isError)

    async def test_telegram_get_updates(self):
        self._tg().get_updates.return_value = []
        result = await self._call('telegram_get_updates', {'limit': 5})
        self.assertFalse(result.isError)
        self._tg().get_updates.assert_called_once_with(limit=5)

    async def test_telegram_get_updates_default_limit(self):
        self._tg().get_updates.return_value = []
        await self._call('telegram_get_updates', {})
        self._tg().get_updates.assert_called_with(limit=10)

    # ── unknown tool & exception handling ────────────────────────────────

    async def test_unknown_tool_returns_error(self):
        result = await self._call('pihole_does_not_exist')
        self.assertTrue(result.isError)
        self.assertIn('Unknown tool', result.content[0].text)

    async def test_exception_returns_error(self):
        self._pihole().health.side_effect = ConnectionError("unreachable")
        result = await self._call('pihole_health')
        self.assertTrue(result.isError)
        self.assertIn('unreachable', result.content[0].text)

    async def test_ok_response_is_valid_json(self):
        self._pihole().stats.return_value = {'summary': {'total': 500}}
        result = await self._call('pihole_stats')
        text = result.content[0].text
        parsed = json.loads(text)        # must not raise
        self.assertEqual(parsed['summary']['total'], 500)


# ═══════════════════════════════════════════════════════════════════════════
# 5. llm/gemini_agent.py — pure utility functions (no Gemini API calls)
# ═══════════════════════════════════════════════════════════════════════════

class TestGeminiAgentUtils(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Import gemini_agent with google.generativeai stubbed out."""
        genai_stub = types.ModuleType('google.generativeai')

        # Build minimal proto stubs
        class _Type:
            STRING  = 'STRING'
            INTEGER = 'INTEGER'
            NUMBER  = 'NUMBER'
            BOOLEAN = 'BOOLEAN'
            ARRAY   = 'ARRAY'
            OBJECT  = 'OBJECT'

        class _Schema:
            def __init__(self, **kw): self.__dict__.update(kw)

        class _FunctionDeclaration:
            def __init__(self, **kw): self.__dict__.update(kw)

        class _Tool:
            def __init__(self, **kw): self.__dict__.update(kw)

        class _FunctionResponse:
            def __init__(self, **kw): self.__dict__.update(kw)

        class _Part:
            def __init__(self, **kw): self.__dict__.update(kw)

        protos_stub = types.SimpleNamespace(
            Type=_Type,
            Schema=_Schema,
            FunctionDeclaration=_FunctionDeclaration,
            Tool=_Tool,
            FunctionResponse=_FunctionResponse,
            Part=_Part,
        )
        genai_stub.protos = protos_stub
        genai_stub.configure = MagicMock()
        genai_stub.GenerativeModel = MagicMock()

        google_stub = types.ModuleType('google')
        google_stub.generativeai = genai_stub

        # Stub mcp modules
        mcp_stub         = types.ModuleType('mcp')
        client_stub      = types.ModuleType('mcp.client')
        stdio_stub       = types.ModuleType('mcp.client.stdio')
        mcp_stub.ClientSession         = MagicMock()
        mcp_stub.StdioServerParameters = MagicMock()
        stdio_stub.stdio_client        = MagicMock()

        loader_stub = MagicMock()
        loader_stub.load_llm.return_value = {
            'api_key': 'TEST_KEY', 'model': 'gemini-2.0-flash'
        }
        loader_stub.load_prompts.return_value = {
            'system_prompt': 'You are a test assistant.',
            'watch_prompt': 'Check now.',
            'watch_interval_minutes': 10,
        }

        with patch.dict('sys.modules', {
            'google':                 google_stub,
            'google.generativeai':    genai_stub,
            'mcp':                    mcp_stub,
            'mcp.client':             client_stub,
            'mcp.client.stdio':       stdio_stub,
            'config.loader':          loader_stub,
        }):
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                'gemini_agent_test', ROOT / 'llm' / 'gemini_agent.py'
            )
            cls.mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.mod)
            cls.genai_protos = protos_stub

    def test_map_type_string(self):
        self.assertEqual(self.mod._map_type('string'), 'STRING')

    def test_map_type_integer(self):
        self.assertEqual(self.mod._map_type('integer'), 'INTEGER')

    def test_map_type_boolean(self):
        self.assertEqual(self.mod._map_type('boolean'), 'BOOLEAN')

    def test_map_type_number(self):
        self.assertEqual(self.mod._map_type('number'), 'NUMBER')

    def test_map_type_array(self):
        self.assertEqual(self.mod._map_type('array'), 'ARRAY')

    def test_map_type_object(self):
        self.assertEqual(self.mod._map_type('object'), 'OBJECT')

    def test_map_type_unknown_defaults_to_string(self):
        self.assertEqual(self.mod._map_type('foobar'), 'STRING')

    def test_mcp_to_gemini_tool_basic(self):
        mcp_tool = MagicMock()
        mcp_tool.name        = 'pihole_health'
        mcp_tool.description = 'Get health.'
        mcp_tool.inputSchema = {'type': 'object', 'properties': {}, 'required': []}
        tool = self.mod._mcp_to_gemini_tool(mcp_tool)
        self.assertIsNotNone(tool)

    def test_mcp_to_gemini_tool_with_properties(self):
        mcp_tool = MagicMock()
        mcp_tool.name        = 'pihole_stats'
        mcp_tool.description = 'Stats.'
        mcp_tool.inputSchema = {
            'type': 'object',
            'properties': {
                'date':     {'type': 'string', 'description': 'Date'},
                'end_date': {'type': 'string'},
            },
            'required': ['date'],
        }
        tool = self.mod._mcp_to_gemini_tool(mcp_tool)
        self.assertIsNotNone(tool)

    def test_mcp_to_gemini_tool_no_schema(self):
        mcp_tool = MagicMock()
        mcp_tool.name        = 'pihole_health'
        mcp_tool.description = 'Health check.'
        mcp_tool.inputSchema = None
        # Should not raise
        tool = self.mod._mcp_to_gemini_tool(mcp_tool)
        self.assertIsNotNone(tool)

    def test_agent_init_loads_config(self):
        agent = self.mod.PiholeGeminiAgent()
        self.assertEqual(agent._llm_cfg['api_key'], 'TEST_KEY')
        self.assertEqual(agent._llm_cfg['model'], 'gemini-2.0-flash')
        self.assertEqual(agent._prompts['watch_interval_minutes'], 10)

    def test_agent_init_loads_prompts(self):
        agent = self.mod.PiholeGeminiAgent()
        self.assertIn('test assistant', agent._prompts['system_prompt'])

    def test_fallback_prompts_exist(self):
        self.assertTrue(self.mod._SYSTEM_PROMPT_FALLBACK)
        self.assertTrue(self.mod._WATCH_PROMPT_FALLBACK)


# ═══════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    unittest.main(verbosity=2)
