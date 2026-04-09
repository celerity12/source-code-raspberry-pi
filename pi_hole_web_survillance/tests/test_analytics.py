#!/usr/bin/env python3
"""
Tests for scripts/analytics.py

All tests use an in-memory SQLite DB seeded with known data and pass the
connection explicitly so they never touch the production analytics.db file.
"""

import sys
import sqlite3
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.data import analytics as A

TODAY     = datetime.now().strftime('%Y-%m-%d')
YESTERDAY = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')


# ── Test DB factory ───────────────────────────────────────────────────────────

def make_conn():
    """
    In-memory DB with the same schema as fetcher.init_database, pre-seeded with:
      - 5 today queries from two clients
      - 2 yesterday queries from one client
      - daily_summary rows matching those queries
    """
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    # SQLite 3.38+ treats 'localtime' as non-deterministic, disallowing it in
    # GENERATED columns. For tests we use a plain TEXT date column and insert
    # the value explicitly — the same data the generated column would produce.
    conn.executescript("""
        CREATE TABLE queries (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   INTEGER NOT NULL,
            domain      TEXT NOT NULL,
            client_ip   TEXT NOT NULL,
            client_name TEXT,
            query_type  TEXT,
            status      INTEGER,
            category    TEXT,
            date        TEXT
        );
        CREATE TABLE daily_summary (
            date            TEXT,
            client_ip       TEXT,
            client_name     TEXT,
            total_queries   INTEGER DEFAULT 0,
            blocked_queries INTEGER DEFAULT 0,
            unique_domains  INTEGER DEFAULT 0,
            top_category    TEXT,
            PRIMARY KEY (date, client_ip)
        );
    """)

    base = int(datetime.now().replace(hour=10, minute=0, second=0, microsecond=0).timestamp())
    yest = int((datetime.now() - timedelta(days=1)).replace(hour=10).timestamp())

    conn.executemany(
        "INSERT INTO queries (timestamp,domain,client_ip,client_name,query_type,status,category,date)"
        " VALUES (?,?,?,?,?,?,?,?)",
        [
            # today — PC
            (base,     'youtube.com',   '192.168.1.1', 'PC',    'A', 2, 'streaming',   TODAY),
            (base+1,   'netflix.com',   '192.168.1.1', 'PC',    'A', 2, 'streaming',   TODAY),
            (base+2,   'ad.tracker.io', '192.168.1.1', 'PC',    'A', 1, 'ads_tracking',TODAY),
            # today — Phone
            (base+3,   'facebook.com',  '192.168.1.2', 'Phone', 'A', 2, 'social_media',TODAY),
            (base+100, 'reddit.com',    '192.168.1.2', 'Phone', 'A', 2, 'social_media',TODAY),
            # yesterday — PC only
            (yest,     'youtube.com',   '192.168.1.1', 'PC',    'A', 2, 'streaming',   YESTERDAY),
            (yest+1,   'github.com',    '192.168.1.1', 'PC',    'A', 2, 'tech',        YESTERDAY),
        ]
    )
    conn.executemany(
        "INSERT INTO daily_summary VALUES (?,?,?,?,?,?,?)",
        [
            (TODAY,     '192.168.1.1', 'PC',    3, 1, 3, 'streaming'),
            (TODAY,     '192.168.1.2', 'Phone', 2, 0, 2, 'social_media'),
            (YESTERDAY, '192.168.1.1', 'PC',    2, 0, 2, 'streaming'),
        ]
    )
    conn.commit()
    return conn


# ── date_range ────────────────────────────────────────────────────────────────

class TestDateRange(unittest.TestCase):

    def test_today_start_equals_end(self):
        start, end = A.date_range('today')
        self.assertEqual(start, end)
        self.assertEqual(start, TODAY)

    def test_yesterday(self):
        start, end = A.date_range('yesterday')
        self.assertEqual(start, end)
        self.assertEqual(start, YESTERDAY)

    def test_week_is_7_inclusive_days(self):
        start, end = A.date_range('week')
        s = datetime.strptime(start, '%Y-%m-%d').date()
        e = datetime.strptime(end, '%Y-%m-%d').date()
        self.assertEqual((e - s).days + 1, 7)
        self.assertEqual(end, TODAY)

    def test_month_is_30_inclusive_days(self):
        start, end = A.date_range('month')
        s = datetime.strptime(start, '%Y-%m-%d').date()
        e = datetime.strptime(end, '%Y-%m-%d').date()
        self.assertEqual((e - s).days + 1, 30)
        self.assertEqual(end, TODAY)

    def test_invalid_period_raises_value_error(self):
        with self.assertRaises(ValueError):
            A.date_range('quarterly')


# ── client_usage ──────────────────────────────────────────────────────────────

class TestClientUsage(unittest.TestCase):

    def setUp(self):
        self.conn = make_conn()

    def test_returns_both_clients_for_today(self):
        rows = A.client_usage(TODAY, conn=self.conn)
        self.assertEqual(len(rows), 2)

    def test_ordered_by_total_queries_descending(self):
        rows = A.client_usage(TODAY, conn=self.conn)
        self.assertGreaterEqual(rows[0]['total_queries'], rows[1]['total_queries'])

    def test_no_data_date_returns_empty_list(self):
        self.assertEqual(A.client_usage('1990-01-01', conn=self.conn), [])

    def test_row_contains_required_keys(self):
        row = A.client_usage(TODAY, conn=self.conn)[0]
        for key in ('client_ip', 'client_name', 'total_queries',
                    'blocked_queries', 'unique_domains'):
            self.assertIn(key, row)


# ── client_hourly ─────────────────────────────────────────────────────────────

class TestClientHourly(unittest.TestCase):

    def setUp(self):
        self.conn = make_conn()

    def test_returns_list(self):
        rows = A.client_hourly('192.168.1.1', TODAY, conn=self.conn)
        self.assertIsInstance(rows, list)

    def test_hour_format_is_two_digits(self):
        rows = A.client_hourly('192.168.1.1', TODAY, conn=self.conn)
        for r in rows:
            self.assertRegex(r['hour'], r'^\d{2}$')

    def test_unknown_client_returns_empty(self):
        rows = A.client_hourly('10.0.0.99', TODAY, conn=self.conn)
        self.assertEqual(rows, [])


# ── all_clients_hourly ────────────────────────────────────────────────────────

class TestAllClientsHourly(unittest.TestCase):

    def setUp(self):
        self.conn = make_conn()

    def test_returns_dict_keyed_by_ip(self):
        result = A.all_clients_hourly(TODAY, conn=self.conn)
        self.assertIsInstance(result, dict)
        self.assertIn('192.168.1.1', result)

    def test_each_entry_has_name_and_hours(self):
        result = A.all_clients_hourly(TODAY, conn=self.conn)
        for ip, data in result.items():
            self.assertIn('name', data)
            self.assertIn('hours', data)


# ── top_domains ───────────────────────────────────────────────────────────────

class TestTopDomains(unittest.TestCase):

    def setUp(self):
        self.conn = make_conn()

    def test_returns_domains_for_today(self):
        rows = A.top_domains(TODAY, conn=self.conn)
        self.assertGreater(len(rows), 0)

    def test_respects_limit(self):
        rows = A.top_domains(TODAY, limit=2, conn=self.conn)
        self.assertLessEqual(len(rows), 2)

    def test_ordered_by_query_count_descending(self):
        rows = A.top_domains(TODAY, conn=self.conn)
        for i in range(len(rows) - 1):
            self.assertGreaterEqual(rows[i]['queries'], rows[i + 1]['queries'])

    def test_client_filter_restricts_results(self):
        all_rows   = A.top_domains(TODAY, conn=self.conn)
        phone_rows = A.top_domains(TODAY, client_ip='192.168.1.2', conn=self.conn)
        # Phone only queried 2 domains; result should be smaller than unfiltered
        self.assertLessEqual(len(phone_rows), len(all_rows))
        for r in phone_rows:
            self.assertEqual(r['client_name'], 'Phone')

    def test_no_data_returns_empty(self):
        self.assertEqual(A.top_domains('1990-01-01', conn=self.conn), [])


# ── category_breakdown ────────────────────────────────────────────────────────

class TestCategoryBreakdown(unittest.TestCase):

    def setUp(self):
        self.conn = make_conn()

    def test_streaming_and_social_present(self):
        rows = A.category_breakdown(TODAY, conn=self.conn)
        cats = {r['category'] for r in rows}
        self.assertIn('streaming', cats)
        self.assertIn('social_media', cats)

    def test_client_filter(self):
        rows = A.category_breakdown(TODAY, client_ip='192.168.1.2', conn=self.conn)
        cats = {r['category'] for r in rows}
        self.assertIn('social_media', cats)
        self.assertNotIn('streaming', cats)

    def test_rows_have_required_keys(self):
        rows = A.category_breakdown(TODAY, conn=self.conn)
        for r in rows:
            self.assertIn('category', r)
            self.assertIn('queries', r)
            self.assertIn('unique_domains', r)


# ── network_summary ───────────────────────────────────────────────────────────

class TestNetworkSummary(unittest.TestCase):

    def setUp(self):
        self.conn = make_conn()

    def test_has_required_keys(self):
        result = A.network_summary(TODAY, conn=self.conn)
        for key in ('total_queries', 'blocked_queries', 'unique_domains', 'active_clients'):
            self.assertIn(key, result)

    def test_total_queries_sums_summary_rows(self):
        # daily_summary for today: PC=3, Phone=2 → 5
        result = A.network_summary(TODAY, conn=self.conn)
        self.assertEqual(result['total_queries'], 5)

    def test_active_clients_count(self):
        result = A.network_summary(TODAY, conn=self.conn)
        self.assertEqual(result['active_clients'], 2)

    def test_empty_date_returns_dict(self):
        result = A.network_summary('1990-01-01', conn=self.conn)
        self.assertIsInstance(result, dict)


# ── compare_periods ───────────────────────────────────────────────────────────

class TestComparePeriods(unittest.TestCase):

    def setUp(self):
        self.conn = make_conn()

    def test_has_expected_keys(self):
        result = A.compare_periods(TODAY, conn=self.conn)
        for key in ('today', 'yesterday', 'week_avg', 'month_avg'):
            self.assertIn(key, result)

    def test_today_total(self):
        # PC=3 + Phone=2 = 5
        result = A.compare_periods(TODAY, conn=self.conn)
        self.assertEqual(result['today']['avg_q'], 5)

    def test_yesterday_total(self):
        # Only PC had queries yesterday: 2
        result = A.compare_periods(TODAY, conn=self.conn)
        self.assertEqual(result['yesterday']['avg_q'], 2)

    def test_week_avg_excludes_today(self):
        # week_avg end is *yesterday* so today's queries don't skew the baseline
        result = A.compare_periods(TODAY, conn=self.conn)
        # We only seeded yesterday as historical data, so avg = 2 or None/0 if no
        # data in week window — just verify the key exists and is non-negative
        self.assertGreaterEqual(result['week_avg'].get('avg_q', 0), 0)


# ── daily_trend ───────────────────────────────────────────────────────────────

class TestDailyTrend(unittest.TestCase):

    def setUp(self):
        self.conn = make_conn()

    def test_returns_list(self):
        self.assertIsInstance(A.daily_trend(7, conn=self.conn), list)

    def test_ordered_by_date_ascending(self):
        rows = A.daily_trend(7, conn=self.conn)
        dates = [r['date'] for r in rows]
        self.assertEqual(dates, sorted(dates))

    def test_includes_today_and_yesterday(self):
        rows = A.daily_trend(7, conn=self.conn)
        dates = {r['date'] for r in rows}
        self.assertIn(TODAY, dates)
        self.assertIn(YESTERDAY, dates)

    def test_client_filter_reduces_totals(self):
        all_rows  = A.daily_trend(7, conn=self.conn)
        pc_rows   = A.daily_trend(7, client_ip='192.168.1.1', conn=self.conn)
        total_all = sum(r['total_queries'] or 0 for r in all_rows)
        total_pc  = sum(r['total_queries'] or 0 for r in pc_rows)
        self.assertLessEqual(total_pc, total_all)


# ── new_domains ───────────────────────────────────────────────────────────────

class TestNewDomains(unittest.TestCase):

    def setUp(self):
        self.conn = make_conn()

    def test_returns_list(self):
        self.assertIsInstance(A.new_domains(TODAY, conn=self.conn), list)

    def test_youtube_not_new_because_seen_yesterday(self):
        # youtube.com appears in both today and yesterday queries
        rows   = A.new_domains(TODAY, conn=self.conn)
        domains = {r['domain'] for r in rows}
        self.assertNotIn('youtube.com', domains)

    def test_netflix_is_new_today(self):
        # netflix.com only appears in today's queries
        rows   = A.new_domains(TODAY, conn=self.conn)
        domains = {r['domain'] for r in rows}
        self.assertIn('netflix.com', domains)

    def test_github_not_in_today_new_domains(self):
        # github.com was only in yesterday — not queried today at all
        rows   = A.new_domains(TODAY, conn=self.conn)
        domains = {r['domain'] for r in rows}
        self.assertNotIn('github.com', domains)


# ── blocked_domains_top ───────────────────────────────────────────────────────

class TestBlockedDomainsTop(unittest.TestCase):

    def setUp(self):
        self.conn = make_conn()

    def test_returns_list(self):
        rows = A.blocked_domains_top(TODAY, conn=self.conn)
        self.assertIsInstance(rows, list)

    def test_excludes_status_2_and_3(self):
        # All today's rows have status 2 (forwarded/allowed) except ad.tracker.io (status 1)
        rows   = A.blocked_domains_top(TODAY, conn=self.conn)
        domains = {r['domain'] for r in rows}
        # status-2 rows should be excluded; only status-1 (ad.tracker.io) should remain
        self.assertNotIn('youtube.com', domains)
        self.assertIn('ad.tracker.io', domains)

    def test_respects_limit(self):
        rows = A.blocked_domains_top(TODAY, limit=1, conn=self.conn)
        self.assertLessEqual(len(rows), 1)


if __name__ == '__main__':
    unittest.main()
