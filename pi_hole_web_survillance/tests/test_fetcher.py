#!/usr/bin/env python3
"""
Tests for scripts/fetcher.py

Covers: domain categorization, third-party lookup, cache behaviour,
database initialisation, query storage, daily summary rebuild, purge,
fetch-state round-trips, and the Pi-hole HTTP fetch (mocked).
"""

import sys
import logging
import sqlite3
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

# Patch FileHandler before importing the module so the logger's attempt to open
# /home/pi/pihole-analytics/logs/fetcher.log does not fail in CI / dev machines.
with patch('logging.FileHandler', lambda *a, **kw: logging.NullHandler()):
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from scripts.data import fetcher as F


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_conn():
    """Return an isolated in-memory DB with the full schema."""
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    F.init_database(conn)
    return conn


NOW_TS  = int(datetime.now().timestamp())
BASE_TS = int((datetime.now() - timedelta(minutes=30)).timestamp())  # 30 min ago


# ── categorize_domain ─────────────────────────────────────────────────────────

class TestCategorizeDomain(unittest.TestCase):

    def setUp(self):
        self.rules = {
            'streaming': {
                'keywords': ['netflix', 'youtube'],
                'domains':  ['ytimg.com', 'googlevideo.com'],
            },
            'ads_tracking': {
                'keywords': ['doubleclick'],
                'domains':  ['googlesyndication.com'],
            },
        }

    def test_exact_domain_match(self):
        self.assertEqual(F.categorize_domain('ytimg.com', self.rules), 'streaming')

    def test_suffix_domain_match(self):
        # 'i.ytimg.com' ends with '.ytimg.com' → streaming
        self.assertEqual(F.categorize_domain('i.ytimg.com', self.rules), 'streaming')

    def test_keyword_match(self):
        self.assertEqual(F.categorize_domain('www.netflix.com', self.rules), 'streaming')

    def test_no_match_returns_other(self):
        self.assertEqual(F.categorize_domain('unknown-site.xyz', self.rules), 'other')

    def test_case_insensitive(self):
        # Pi-hole domains can arrive in any case
        self.assertEqual(F.categorize_domain('YOUTUBE.COM', self.rules), 'streaming')

    def test_trailing_dot_stripped(self):
        # Pi-hole sometimes returns fully-qualified names with a trailing dot
        self.assertEqual(F.categorize_domain('ytimg.com.', self.rules), 'streaming')

    def test_domain_rule_beats_keyword(self):
        # Domain list is checked before keywords within the same category;
        # here we verify the exact-match path is reached before keyword scanning.
        self.assertEqual(F.categorize_domain('googlesyndication.com', self.rules), 'ads_tracking')

    def test_first_category_in_dict_order_wins(self):
        # Both categories match 'test'; the first one defined should win.
        rules = {
            'a': {'keywords': ['test'], 'domains': []},
            'b': {'keywords': ['test'], 'domains': []},
        }
        self.assertEqual(F.categorize_domain('test.com', rules), 'a')

    def test_empty_rules_returns_other(self):
        self.assertEqual(F.categorize_domain('example.com', {}), 'other')

    def test_partial_keyword_not_matched_as_domain(self):
        # 'netflixcdn.com' contains 'netflix' → keyword match, not domain match
        result = F.categorize_domain('netflixcdn.com', self.rules)
        self.assertEqual(result, 'streaming')


# ── lookup_third_party ────────────────────────────────────────────────────────

class TestLookupThirdParty(unittest.TestCase):

    def setUp(self):
        self.tp = sqlite3.connect(':memory:')
        self.tp.execute(
            "CREATE TABLE domains (domain TEXT PRIMARY KEY, category TEXT NOT NULL)"
        )
        self.tp.executemany("INSERT INTO domains VALUES (?,?)", [
            ('example.com',    'news'),
            ('adult-site.com', 'adult'),
            ('tracker.io',     'ads_tracking'),
        ])
        self.tp.commit()

    def tearDown(self):
        self.tp.close()

    def test_exact_match(self):
        self.assertEqual(F.lookup_third_party(self.tp, 'example.com'), 'news')

    def test_one_subdomain_resolved(self):
        # sub.example.com → falls back to example.com
        self.assertEqual(F.lookup_third_party(self.tp, 'sub.example.com'), 'news')

    def test_deep_subdomain_resolved(self):
        # a.b.adult-site.com → walks up to adult-site.com
        self.assertEqual(F.lookup_third_party(self.tp, 'a.b.adult-site.com'), 'adult')

    def test_no_match_returns_other(self):
        self.assertEqual(F.lookup_third_party(self.tp, 'notlisted.xyz'), 'other')

    def test_single_label_no_crash(self):
        # Bare label (no dot) — should not raise, just return 'other'
        self.assertEqual(F.lookup_third_party(self.tp, 'localhost'), 'other')

    def test_tld_not_matched(self):
        # 'com' alone should not match even if a com entry existed
        self.assertEqual(F.lookup_third_party(self.tp, 'com'), 'other')


# ── get_cached_category ───────────────────────────────────────────────────────

class TestGetCachedCategory(unittest.TestCase):

    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.execute(
            "CREATE TABLE domain_categories "
            "(domain TEXT PRIMARY KEY, category TEXT, updated TEXT)"
        )
        self.conn.commit()
        self.rules = {
            'streaming': {'keywords': ['youtube'], 'domains': []},
        }

    def _tp(self, entries):
        """Create a minimal third-party DB with the given {domain: cat} mapping."""
        tp = sqlite3.connect(':memory:')
        tp.execute("CREATE TABLE domains (domain TEXT PRIMARY KEY, category TEXT NOT NULL)")
        tp.executemany("INSERT INTO domains VALUES (?,?)", entries.items())
        tp.commit()
        return tp

    def test_cache_hit_returns_cached_value(self):
        self.conn.execute(
            "INSERT INTO domain_categories VALUES ('youtube.com','streaming',datetime('now'))"
        )
        self.conn.commit()
        result = F.get_cached_category(self.conn, 'youtube.com', self.rules)
        self.assertEqual(result, 'streaming')

    def test_config_match_is_written_to_cache(self):
        F.get_cached_category(self.conn, 'youtube.com', self.rules)
        row = self.conn.execute(
            "SELECT category FROM domain_categories WHERE domain='youtube.com'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 'streaming')

    def test_third_party_fallback_when_config_misses(self):
        tp = self._tp({'news-site.com': 'news'})
        result = F.get_cached_category(self.conn, 'news-site.com', self.rules, tp_conn=tp)
        self.assertEqual(result, 'news')
        tp.close()

    def test_no_tp_conn_falls_back_to_other(self):
        result = F.get_cached_category(self.conn, 'unlisted.xyz', self.rules, tp_conn=None)
        self.assertEqual(result, 'other')

    def test_config_takes_priority_over_tp(self):
        # 'youtube.com' matches config rule → should never reach TP even if TP says adult
        tp = self._tp({'youtube.com': 'adult'})
        result = F.get_cached_category(self.conn, 'youtube.com', self.rules, tp_conn=tp)
        self.assertEqual(result, 'streaming')
        tp.close()


# ── init_database ─────────────────────────────────────────────────────────────

class TestInitDatabase(unittest.TestCase):

    def test_creates_all_tables(self):
        conn = sqlite3.connect(':memory:')
        F.init_database(conn)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        for expected in ('queries', 'daily_summary', 'domain_categories', 'fetch_state'):
            self.assertIn(expected, tables)

    def test_creates_indexes(self):
        conn = sqlite3.connect(':memory:')
        F.init_database(conn)
        indexes = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()}
        for idx in ('idx_queries_timestamp', 'idx_queries_client',
                    'idx_queries_domain', 'idx_queries_date', 'idx_queries_category'):
            self.assertIn(idx, indexes)

    def test_idempotent_double_call(self):
        conn = sqlite3.connect(':memory:')
        F.init_database(conn)
        # Second call must not raise (uses CREATE TABLE IF NOT EXISTS)
        F.init_database(conn)


# ── fetch_state ───────────────────────────────────────────────────────────────

class TestFetchState(unittest.TestCase):

    def setUp(self):
        self.conn = make_conn()

    def test_default_is_approximately_24h_ago(self):
        ts = F.get_last_fetch_time(self.conn)
        expected = int((datetime.now() - timedelta(hours=24)).timestamp())
        self.assertAlmostEqual(ts, expected, delta=5)

    def test_set_then_get_roundtrip(self):
        F.set_last_fetch_time(self.conn, 1_234_567_890)
        self.assertEqual(F.get_last_fetch_time(self.conn), 1_234_567_890)

    def test_overwrite_works(self):
        F.set_last_fetch_time(self.conn, 100)
        F.set_last_fetch_time(self.conn, 200)
        self.assertEqual(F.get_last_fetch_time(self.conn), 200)


# ── store_queries ─────────────────────────────────────────────────────────────

class TestStoreQueries(unittest.TestCase):

    def setUp(self):
        self.conn = make_conn()
        # Set last_ts just before our test rows so they count as "new"
        F.set_last_fetch_time(self.conn, BASE_TS - 10)
        self.cfg = {
            'clients': {'192.168.1.1': 'TestPC'},
            'categories': {
                'streaming': {'keywords': ['youtube'], 'domains': []},
            },
        }

    def _row(self, offset=1, domain='youtube.com', client='192.168.1.1', status='2'):
        return [str(BASE_TS + offset), 'A', domain, client, status]

    def test_inserts_new_queries(self):
        inserted = F.store_queries(self.conn, [self._row(1), self._row(2)], self.cfg)
        self.assertEqual(inserted, 2)
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM queries").fetchone()[0], 2
        )

    def test_skips_queries_older_than_last_ts(self):
        old_row = [str(BASE_TS - 100), 'A', 'youtube.com', '192.168.1.1', '2']
        inserted = F.store_queries(self.conn, [old_row], self.cfg)
        self.assertEqual(inserted, 0)

    def test_skips_malformed_rows(self):
        bad = [[], ['only-one-field'], [None, None, None, None, None]]
        inserted = F.store_queries(self.conn, bad, self.cfg)
        self.assertEqual(inserted, 0)

    def test_known_client_ip_resolved_to_name(self):
        F.store_queries(self.conn, [self._row(1)], self.cfg)
        row = self.conn.execute("SELECT client_name FROM queries").fetchone()
        self.assertEqual(row[0], 'TestPC')

    def test_unknown_client_ip_used_as_name(self):
        F.store_queries(self.conn, [self._row(1, client='10.0.0.99')], self.cfg)
        row = self.conn.execute(
            "SELECT client_name FROM queries WHERE client_ip='10.0.0.99'"
        ).fetchone()
        self.assertEqual(row[0], '10.0.0.99')

    def test_category_assigned_from_config(self):
        F.store_queries(self.conn, [self._row(1, domain='youtube.com')], self.cfg)
        row = self.conn.execute("SELECT category FROM queries").fetchone()
        self.assertEqual(row[0], 'streaming')

    def test_max_timestamp_advanced(self):
        F.store_queries(self.conn, [self._row(1), self._row(5)], self.cfg)
        self.assertEqual(F.get_last_fetch_time(self.conn), BASE_TS + 5)

    def test_no_queries_does_not_change_timestamp(self):
        F.store_queries(self.conn, [], self.cfg)
        ts = F.get_last_fetch_time(self.conn)
        self.assertEqual(ts, BASE_TS - 10)


# ── rebuild_daily_summary ─────────────────────────────────────────────────────

class TestRebuildDailySummary(unittest.TestCase):

    def setUp(self):
        self.conn = make_conn()
        base_ts = int(datetime.now().replace(
            hour=10, minute=0, second=0, microsecond=0
        ).timestamp())
        cfg = {
            'clients': {'192.168.1.1': 'PC'},
            'categories': {'streaming': {'keywords': ['yt'], 'domains': []}},
        }
        F.set_last_fetch_time(self.conn, base_ts - 100)
        rows = [[str(base_ts + i), 'A', f'site{i}.com', '192.168.1.1', '2']
                for i in range(5)]
        F.store_queries(self.conn, rows, cfg)
        F.rebuild_daily_summary(self.conn)
        self.today = datetime.now().strftime('%Y-%m-%d')

    def test_summary_row_exists(self):
        row = self.conn.execute(
            "SELECT * FROM daily_summary WHERE date=? AND client_ip='192.168.1.1'",
            (self.today,)
        ).fetchone()
        self.assertIsNotNone(row)

    def test_total_queries_count(self):
        row = self.conn.execute(
            "SELECT total_queries FROM daily_summary WHERE date=?", (self.today,)
        ).fetchone()
        self.assertEqual(row[0], 5)

    def test_unique_domains_count(self):
        row = self.conn.execute(
            "SELECT unique_domains FROM daily_summary WHERE date=?", (self.today,)
        ).fetchone()
        # 5 distinct domains: site0.com … site4.com
        self.assertEqual(row[0], 5)

    def test_rebuild_replaces_old_data(self):
        # Calling rebuild again should not double the row count
        F.rebuild_daily_summary(self.conn)
        count = self.conn.execute(
            "SELECT COUNT(*) FROM daily_summary WHERE date=?", (self.today,)
        ).fetchone()[0]
        self.assertEqual(count, 1)


# ── purge_old_data ────────────────────────────────────────────────────────────

class TestPurgeOldData(unittest.TestCase):

    def _seed_old(self, conn):
        old_ts = int((datetime.now() - timedelta(days=100)).timestamp())
        old_date = (datetime.now() - timedelta(days=100)).strftime('%Y-%m-%d')
        F.set_last_fetch_time(conn, old_ts - 100)
        F.store_queries(conn,
                        [[str(old_ts), 'A', 'old.com', '1.2.3.4', '2']],
                        {'clients': {}, 'categories': {}})
        conn.execute(
            "INSERT INTO daily_summary (date,client_ip,client_name,total_queries) "
            "VALUES (?,?,?,?)", (old_date, '1.2.3.4', 'OldDev', 10)
        )
        conn.commit()

    def test_old_queries_removed(self):
        conn = make_conn()
        self._seed_old(conn)
        F.purge_old_data(conn, retention_days=90)
        self.assertEqual(
            conn.execute("SELECT COUNT(*) FROM queries").fetchone()[0], 0
        )

    def test_old_summary_removed(self):
        conn = make_conn()
        self._seed_old(conn)
        F.purge_old_data(conn, retention_days=90)
        self.assertEqual(
            conn.execute("SELECT COUNT(*) FROM daily_summary").fetchone()[0], 0
        )

    def test_recent_data_kept(self):
        conn = make_conn()
        self._seed_old(conn)
        recent_ts = NOW_TS - 5
        F.set_last_fetch_time(conn, recent_ts - 10)
        F.store_queries(conn,
                        [[str(recent_ts), 'A', 'recent.com', '1.2.3.4', '2']],
                        {'clients': {}, 'categories': {}})
        F.purge_old_data(conn, retention_days=90)
        count = conn.execute(
            "SELECT COUNT(*) FROM queries WHERE domain='recent.com'"
        ).fetchone()[0]
        self.assertEqual(count, 1)


# ── fetch_pihole_data (HTTP mocked) ──────────────────────────────────────────

class TestFetchPiholeData(unittest.TestCase):

    CFG = {'pihole': {'host': 'http://pi.hole', 'api_path': '/api.php', 'api_token': 'tok'}}

    @patch('requests.get')
    def test_success_returns_query_list(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {'data': [['123', 'A', 'ex.com', '1.1.1.1', '2']]}
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp
        result = F.fetch_pihole_data(self.CFG)
        self.assertEqual(result, [['123', 'A', 'ex.com', '1.1.1.1', '2']])

    @patch('requests.get')
    def test_missing_data_key_returns_empty(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {}   # no 'data' key
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp
        self.assertEqual(F.fetch_pihole_data(self.CFG), [])

    @patch('requests.get')
    def test_network_error_returns_empty_list(self, mock_get):
        import requests
        mock_get.side_effect = requests.RequestException('timeout')
        self.assertEqual(F.fetch_pihole_data(self.CFG), [])


if __name__ == '__main__':
    unittest.main()
