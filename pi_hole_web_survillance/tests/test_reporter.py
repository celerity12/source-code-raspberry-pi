#!/usr/bin/env python3
"""
Tests for scripts/reporter.py

Pure helper functions (pct_change, arrow, stat_box, mini_bar, cat_badge) are
tested directly.  build_report_html is tested by pointing analytics.DB_PATH
at a temp file DB so every internal get_conn() call resolves correctly.
"""

import sys
import logging
import sqlite3
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

# Prevent FileHandler from trying to open /home/pi paths during import
with patch('logging.FileHandler', lambda *a, **kw: logging.NullHandler()):
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from scripts.core import reporter as R
    from scripts.data import analytics as A

TODAY = datetime.now().strftime('%Y-%m-%d')


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_file_db():
    """
    Create a temp-directory file-based SQLite DB seeded with minimal data.
    Returns (tmpdir_path, db_path). Caller must clean up tmpdir.
    """
    tmpdir = Path(tempfile.mkdtemp())
    db_path = tmpdir / 'analytics.db'
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    # Plain date column (not GENERATED) to avoid SQLite 3.38+ localtime restriction
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
    conn.execute(
        "INSERT INTO queries (timestamp,domain,client_ip,client_name,status,category,date)"
        " VALUES (?,?,?,?,?,?,?)",
        (base, 'youtube.com', '192.168.1.1', 'PC', 2, 'streaming', TODAY)
    )
    conn.execute(
        "INSERT INTO daily_summary VALUES (?,?,?,?,?,?,?)",
        (TODAY, '192.168.1.1', 'PC', 10, 2, 5, 'streaming')
    )
    conn.commit()
    conn.close()
    return tmpdir, db_path


# ── pct_change ────────────────────────────────────────────────────────────────

class TestPctChange(unittest.TestCase):

    def test_increase(self):
        self.assertEqual(R.pct_change(110, 100), 10.0)

    def test_decrease(self):
        self.assertEqual(R.pct_change(90, 100), -10.0)

    def test_zero_baseline_returns_none(self):
        # "No baseline" → None, not 0 (0 would imply "no change")
        self.assertIsNone(R.pct_change(50, 0))

    def test_no_change(self):
        self.assertEqual(R.pct_change(100, 100), 0.0)

    def test_result_is_rounded_to_one_decimal(self):
        # 103/100 = 3.0 %
        self.assertEqual(R.pct_change(103, 100), 3.0)

    def test_large_decrease(self):
        self.assertEqual(R.pct_change(0, 100), -100.0)


# ── arrow ─────────────────────────────────────────────────────────────────────

class TestArrow(unittest.TestCase):

    def test_positive_uses_red_up_arrow(self):
        html = R.arrow(5.0)
        self.assertIn('▲', html)
        self.assertIn('#e74c3c', html)

    def test_negative_uses_green_down_arrow(self):
        html = R.arrow(-3.5)
        self.assertIn('▼', html)
        self.assertIn('#27ae60', html)

    def test_zero_uses_neutral_dash(self):
        html = R.arrow(0)
        self.assertIn('—', html)
        self.assertIn('#3d444d', html)

    def test_none_returns_empty_string(self):
        self.assertEqual(R.arrow(None), '')

    def test_absolute_value_shown_not_signed(self):
        # The number shown should be positive even for negative change
        html = R.arrow(-7.3)
        self.assertIn('7.3', html)
        self.assertNotIn('-7.3', html)


# ── stat_box ──────────────────────────────────────────────────────────────────

class TestStatBox(unittest.TestCase):

    def test_renders_formatted_number(self):
        html = R.stat_box(1_234, 'Total')
        self.assertIn('1,234', html)

    def test_renders_label(self):
        html = R.stat_box(100, 'Queries')
        self.assertIn('Queries', html)

    def test_with_positive_change_shows_up_arrow(self):
        html = R.stat_box(100, 'Queries', change=10.0)
        self.assertIn('▲', html)

    def test_without_change_omits_chg_div(self):
        html = R.stat_box(100, 'Queries')
        # No change arg → no <div class="chg"> section
        self.assertNotIn('class="chg"', html)


# ── mini_bar ──────────────────────────────────────────────────────────────────

class TestMiniBar(unittest.TestCase):

    def test_full_width_at_max(self):
        self.assertIn('width:100%', R.mini_bar(100, 100))

    def test_half_width(self):
        self.assertIn('width:50%', R.mini_bar(50, 100))

    def test_zero_max_yields_zero_width(self):
        self.assertIn('width:0%', R.mini_bar(10, 0))

    def test_value_above_max_clipped_to_100(self):
        self.assertIn('width:100%', R.mini_bar(200, 100))

    def test_custom_color_applied(self):
        html = R.mini_bar(50, 100, color='#ff0000')
        self.assertIn('#ff0000', html)


# ── cat_badge ─────────────────────────────────────────────────────────────────

class TestCatBadge(unittest.TestCase):

    def test_streaming_has_film_icon_and_color(self):
        html = R.cat_badge('streaming')
        self.assertIn('🎬', html)
        self.assertIn('#e50914', html)

    def test_adult_has_correct_icon(self):
        html = R.cat_badge('adult')
        self.assertIn('🔞', html)

    def test_unknown_category_uses_globe_icon(self):
        html = R.cat_badge('unknown_category')
        self.assertIn('🌐', html)

    def test_label_replaces_underscores_with_spaces(self):
        html = R.cat_badge('social_media')
        self.assertIn('Social Media', html)


# ── build_report_html ─────────────────────────────────────────────────────────

class TestBuildReportHtml(unittest.TestCase):

    def setUp(self):
        self.tmpdir, self.db_path = make_file_db()
        self.patcher = patch.object(A, 'DB_PATH', self.db_path)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        shutil.rmtree(self.tmpdir)

    def test_html_is_valid_structure(self):
        html = R.build_report_html(TODAY, 'daily')
        self.assertIn('<!DOCTYPE html>', html)
        self.assertIn('</html>', html)

    def test_report_contains_date(self):
        html = R.build_report_html(TODAY, 'daily')
        self.assertIn(TODAY, html)

    def test_daily_does_not_include_trend_section(self):
        html = R.build_report_html(TODAY, 'daily')
        self.assertNotIn('7-Day Trend', html)

    def test_weekly_includes_trend_section(self):
        html = R.build_report_html(TODAY, 'weekly')
        self.assertIn('7-Day Trend', html)

    def test_monthly_includes_trend_section(self):
        html = R.build_report_html(TODAY, 'monthly')
        self.assertIn('7-Day Trend', html)

    def test_report_mentions_pi_hole(self):
        html = R.build_report_html(TODAY, 'daily')
        self.assertIn('Pi-hole', html)


if __name__ == '__main__':
    unittest.main()
