#!/usr/bin/env python3
"""
Tests for scripts/downloader.py

Covers: CATEGORY_MAP / SHALLALIST_CATEGORY_MAP validity,
cache invalidation, _import_tarball, build_database (single + merged sources),
download_ut1 / download_shallalist (HTTP mocked).
"""

import io
import sys
import shutil
import logging
import sqlite3
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

with patch('logging.FileHandler', lambda *a, **kw: logging.NullHandler()):
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from scripts.data import downloader as D

# All categories the project recognises
VALID_CATEGORIES = {
    'adult', 'ads_tracking', 'social_media', 'gaming', 'streaming',
    'shopping', 'news', 'educational', 'music', 'finance', 'health',
    'travel', 'food', 'productivity', 'tech', 'smart_home',
    'vpn_proxy', 'crypto', 'sports', 'government',
}


# ── Tarball factory ───────────────────────────────────────────────────────────

def _make_tarball(dest: Path, root: str, category_data: dict) -> Path:
    """
    Create a minimal tarball at dest/test.tar.gz.
    root: top-level folder name ('blacklists' for UT1, 'BL' for Shallalist)
    category_data: {folder_name: bytes_content_of_domains_file}
    """
    tarball = dest / 'test.tar.gz'
    with tarfile.open(tarball, 'w:gz') as tar:
        for cat, data in category_data.items():
            info = tarfile.TarInfo(name=f'{root}/{cat}/domains')
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return tarball


def _ut1_tarball(dest, category_data):
    return _make_tarball(dest, 'blacklists', category_data)


def _sha_tarball(dest, category_data):
    return _make_tarball(dest, 'BL', category_data)


# ── CATEGORY_MAP (UT1) ────────────────────────────────────────────────────────

class TestCategoryMap(unittest.TestCase):

    def test_all_values_are_known_project_categories(self):
        for folder, cat in D.CATEGORY_MAP.items():
            self.assertIn(cat, VALID_CATEGORIES,
                          f"UT1 folder '{folder}' maps to unknown '{cat}'")

    def test_no_empty_keys_or_values(self):
        for k, v in D.CATEGORY_MAP.items():
            self.assertTrue(k.strip())
            self.assertTrue(v.strip())

    def test_critical_ut1_folders_present(self):
        for folder in ('adult', 'publicite', 'social_networks',
                       'games', 'streamingmedia', 'shopping', 'news'):
            self.assertIn(folder, D.CATEGORY_MAP)

    def test_publicite_maps_to_ads_tracking(self):
        self.assertEqual(D.CATEGORY_MAP['publicite'], 'ads_tracking')

    def test_malware_and_phishing_map_to_ads_tracking(self):
        self.assertEqual(D.CATEGORY_MAP['malware'],   'ads_tracking')
        self.assertEqual(D.CATEGORY_MAP['phishing'],  'ads_tracking')


# ── SHALLALIST_CATEGORY_MAP ───────────────────────────────────────────────────

class TestShallalistCategoryMap(unittest.TestCase):

    def test_all_values_are_known_project_categories(self):
        for folder, cat in D.SHALLALIST_CATEGORY_MAP.items():
            self.assertIn(cat, VALID_CATEGORIES,
                          f"Shallalist folder '{folder}' maps to unknown '{cat}'")

    def test_no_empty_keys_or_values(self):
        for k, v in D.SHALLALIST_CATEGORY_MAP.items():
            self.assertTrue(k.strip())
            self.assertTrue(v.strip())

    def test_critical_shallalist_folders_present(self):
        for folder in ('porn', 'adv', 'socialnet', 'games',
                       'movies', 'shopping', 'news', 'music'):
            self.assertIn(folder, D.SHALLALIST_CATEGORY_MAP)

    def test_porn_maps_to_adult(self):
        self.assertEqual(D.SHALLALIST_CATEGORY_MAP['porn'], 'adult')

    def test_adv_maps_to_ads_tracking(self):
        self.assertEqual(D.SHALLALIST_CATEGORY_MAP['adv'], 'ads_tracking')

    def test_spyware_maps_to_ads_tracking(self):
        self.assertEqual(D.SHALLALIST_CATEGORY_MAP['spyware'], 'ads_tracking')

    def test_anonvpn_maps_to_vpn_proxy(self):
        self.assertEqual(D.SHALLALIST_CATEGORY_MAP['anonvpn'], 'vpn_proxy')

    def test_sports_maps_to_sports(self):
        self.assertEqual(D.SHALLALIST_CATEGORY_MAP['sports'], 'sports')

    def test_travel_maps_to_travel(self):
        self.assertEqual(D.SHALLALIST_CATEGORY_MAP['travel'], 'travel')

    def test_finance_maps_to_finance(self):
        self.assertEqual(D.SHALLALIST_CATEGORY_MAP['finance'], 'finance')


# ── invalidate_cache ──────────────────────────────────────────────────────────

class TestInvalidateCache(unittest.TestCase):

    def _make_analytics_db(self, tmp: Path):
        db = tmp / 'data' / 'analytics.db'
        db.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db)
        conn.execute(
            "CREATE TABLE domain_categories (domain TEXT PRIMARY KEY, category TEXT)"
        )
        conn.executemany("INSERT INTO domain_categories VALUES (?,?)", [
            ('unknown1.com', 'other'),
            ('unknown2.com', 'other'),
            ('youtube.com',  'streaming'),
        ])
        conn.commit()
        conn.close()
        return db

    def test_other_entries_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_analytics_db(Path(tmp))
            with patch.object(D, 'BASE_DIR', Path(tmp)):
                D.invalidate_cache()
            conn = sqlite3.connect(Path(tmp) / 'data' / 'analytics.db')
            remaining = {r[0] for r in conn.execute(
                "SELECT domain FROM domain_categories"
            ).fetchall()}
            conn.close()
        self.assertNotIn('unknown1.com', remaining)
        self.assertNotIn('unknown2.com', remaining)

    def test_non_other_entries_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_analytics_db(Path(tmp))
            with patch.object(D, 'BASE_DIR', Path(tmp)):
                D.invalidate_cache()
            conn = sqlite3.connect(Path(tmp) / 'data' / 'analytics.db')
            remaining = {r[0] for r in conn.execute(
                "SELECT domain FROM domain_categories"
            ).fetchall()}
            conn.close()
        self.assertIn('youtube.com', remaining)

    def test_missing_analytics_db_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(D, 'BASE_DIR', Path(tmp)):
                D.invalidate_cache()


# ── _import_tarball ────────────────────────────────────────────────────────────

class TestImportTarball(unittest.TestCase):
    """Unit tests for the private _import_tarball helper."""

    def _conn(self):
        conn = sqlite3.connect(':memory:')
        conn.execute(
            "CREATE TABLE domains (domain TEXT PRIMARY KEY, category TEXT NOT NULL)"
        )
        return conn

    def _tarball(self, root, category_data):
        tmp = Path(tempfile.mkdtemp())
        return tmp, _make_tarball(tmp, root, category_data)

    def test_ut1_format_imported(self):
        tmp, tb = self._tarball('blacklists', {'adult': b'nasty.com\nbad.net\n'})
        conn = self._conn()
        D._import_tarball(conn, tb, D.CATEGORY_MAP)
        row = conn.execute("SELECT category FROM domains WHERE domain='nasty.com'").fetchone()
        shutil.rmtree(tmp)
        self.assertEqual(row[0], 'adult')

    def test_shallalist_format_imported(self):
        tmp, tb = self._tarball('BL', {'porn': b'explicit.com\n'})
        conn = self._conn()
        D._import_tarball(conn, tb, D.SHALLALIST_CATEGORY_MAP)
        row = conn.execute("SELECT category FROM domains WHERE domain='explicit.com'").fetchone()
        shutil.rmtree(tmp)
        self.assertEqual(row[0], 'adult')

    def test_unmapped_folder_skipped(self):
        tmp, tb = self._tarball('blacklists', {'unknown_folder': b'skip-me.com\n'})
        conn = self._conn()
        D._import_tarball(conn, tb, D.CATEGORY_MAP)
        row = conn.execute("SELECT * FROM domains WHERE domain='skip-me.com'").fetchone()
        shutil.rmtree(tmp)
        self.assertIsNone(row)

    def test_comment_lines_skipped(self):
        tmp, tb = self._tarball('blacklists', {'adult': b'# comment\nreal.com\n'})
        conn = self._conn()
        D._import_tarball(conn, tb, D.CATEGORY_MAP)
        domains = [r[0] for r in conn.execute("SELECT domain FROM domains").fetchall()]
        shutil.rmtree(tmp)
        self.assertNotIn('# comment', domains)
        self.assertIn('real.com', domains)

    def test_returns_count(self):
        tmp, tb = self._tarball('blacklists', {'adult': b'a.com\nb.com\nc.com\n'})
        conn = self._conn()
        n = D._import_tarball(conn, tb, D.CATEGORY_MAP)
        shutil.rmtree(tmp)
        self.assertEqual(n, 3)


# ── build_database ─────────────────────────────────────────────────────────────

class TestBuildDatabase(unittest.TestCase):

    def _run(self, sources_data: list):
        """
        Build a DB from sources_data and return (tmp_dir, db_path).
        sources_data: list of (root_folder, {cat: bytes}, category_map)
        """
        tmp = Path(tempfile.mkdtemp())
        sources = []
        for i, (root, cat_data, cat_map) in enumerate(sources_data):
            subdir = tmp / f'src{i}'
            subdir.mkdir()
            tb = _make_tarball(subdir, root, cat_data)
            sources.append((tb, cat_map))
        with patch.object(D, 'DB_PATH', tmp / 'third_party.db'):
            db_path = D.build_database(sources)
        return tmp, db_path

    def test_ut1_adult_imported(self):
        tmp, db = self._run([('blacklists', {'adult': b'nasty-site.com\n'}, D.CATEGORY_MAP)])
        conn = sqlite3.connect(db)
        row = conn.execute(
            "SELECT category FROM domains WHERE domain='nasty-site.com'"
        ).fetchone()
        conn.close()
        shutil.rmtree(tmp)
        self.assertEqual(row[0], 'adult')

    def test_shallalist_porn_imported(self):
        tmp, db = self._run([('BL', {'porn': b'explicit.com\n'}, D.SHALLALIST_CATEGORY_MAP)])
        conn = sqlite3.connect(db)
        row = conn.execute(
            "SELECT category FROM domains WHERE domain='explicit.com'"
        ).fetchone()
        conn.close()
        shutil.rmtree(tmp)
        self.assertEqual(row[0], 'adult')

    def test_both_sources_merged(self):
        tmp, db = self._run([
            ('blacklists', {'adult':   b'ut1-site.com\n'},    D.CATEGORY_MAP),
            ('BL',         {'finance': b'sha-finance.com\n'}, D.SHALLALIST_CATEGORY_MAP),
        ])
        conn = sqlite3.connect(db)
        ut1_row = conn.execute("SELECT category FROM domains WHERE domain='ut1-site.com'").fetchone()
        sha_row = conn.execute("SELECT category FROM domains WHERE domain='sha-finance.com'").fetchone()
        conn.close()
        shutil.rmtree(tmp)
        self.assertEqual(ut1_row[0], 'adult')
        self.assertEqual(sha_row[0], 'finance')

    def test_ut1_wins_on_duplicate_domain(self):
        # Same domain in both sources — UT1 (first) should win
        tmp, db = self._run([
            ('blacklists', {'adult':   b'overlap.com\n'}, D.CATEGORY_MAP),
            ('BL',         {'finance': b'overlap.com\n'}, D.SHALLALIST_CATEGORY_MAP),
        ])
        conn = sqlite3.connect(db)
        count = conn.execute(
            "SELECT COUNT(*) FROM domains WHERE domain='overlap.com'"
        ).fetchone()[0]
        cat = conn.execute(
            "SELECT category FROM domains WHERE domain='overlap.com'"
        ).fetchone()[0]
        conn.close()
        shutil.rmtree(tmp)
        self.assertEqual(count, 1)
        self.assertEqual(cat, 'adult')     # UT1 entry wins

    def test_publicite_maps_to_ads_tracking(self):
        tmp, db = self._run([('blacklists', {'publicite': b'ads.example.com\n'}, D.CATEGORY_MAP)])
        conn = sqlite3.connect(db)
        row = conn.execute(
            "SELECT category FROM domains WHERE domain='ads.example.com'"
        ).fetchone()
        conn.close()
        shutil.rmtree(tmp)
        self.assertEqual(row[0], 'ads_tracking')

    def test_unmapped_folder_skipped(self):
        tmp, db = self._run([('blacklists', {'unknown_folder': b'ignore-me.com\n'}, D.CATEGORY_MAP)])
        conn = sqlite3.connect(db)
        row = conn.execute("SELECT * FROM domains WHERE domain='ignore-me.com'").fetchone()
        conn.close()
        shutil.rmtree(tmp)
        self.assertIsNone(row)

    def test_comment_lines_skipped(self):
        tmp, db = self._run([('blacklists', {'adult': b'# comment\nreal.com\n'}, D.CATEGORY_MAP)])
        conn = sqlite3.connect(db)
        domains = [r[0] for r in conn.execute("SELECT domain FROM domains").fetchall()]
        conn.close()
        shutil.rmtree(tmp)
        self.assertNotIn('# comment', domains)
        self.assertIn('real.com', domains)

    def test_index_created(self):
        tmp, db = self._run([('blacklists', {'adult': b'site.com\n'}, D.CATEGORY_MAP)])
        conn = sqlite3.connect(db)
        idx = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_domain'"
        ).fetchone()
        conn.close()
        shutil.rmtree(tmp)
        self.assertIsNotNone(idx)

    def test_writes_to_tmp_file_first(self):
        tmp, db = self._run([('blacklists', {'adult': b'site.com\n'}, D.CATEGORY_MAP)])
        shutil.rmtree(tmp)
        self.assertTrue(str(db).endswith('.tmp'))

    def test_empty_sources_list_creates_empty_db(self):
        tmp = Path(tempfile.mkdtemp())
        with patch.object(D, 'DB_PATH', tmp / 'third_party.db'):
            db = D.build_database([])
        conn = sqlite3.connect(db)
        count = conn.execute("SELECT COUNT(*) FROM domains").fetchone()[0]
        conn.close()
        shutil.rmtree(tmp)
        self.assertEqual(count, 0)


# ── download_ut1 / download_shallalist (HTTP mocked) ─────────────────────────

class TestDownloads(unittest.TestCase):

    def _mock_get(self):
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__  = MagicMock(return_value=False)
        mock_resp.raise_for_status.return_value = None
        mock_resp.iter_content.return_value = [b'fake tarball data']
        return mock_resp

    @patch('requests.get')
    def test_ut1_writes_file(self, mock_get):
        mock_get.return_value = self._mock_get()
        with tempfile.TemporaryDirectory() as tmp:
            result = D.download_ut1(Path(tmp))
            self.assertTrue(result.exists())
            self.assertEqual(result.name, 'blacklists.tar.gz')

    @patch('requests.get')
    def test_shallalist_writes_file(self, mock_get):
        mock_get.return_value = self._mock_get()
        with tempfile.TemporaryDirectory() as tmp:
            result = D.download_shallalist(Path(tmp))
            self.assertTrue(result.exists())
            self.assertEqual(result.name, 'shallalist.tar.gz')

    @patch('requests.get')
    def test_ut1_http_error_propagates(self, mock_get):
        import requests
        mock_resp = self._mock_get()
        mock_resp.raise_for_status.side_effect = requests.HTTPError('404')
        mock_get.return_value = mock_resp
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(Exception):
                D.download_ut1(Path(tmp))

    @patch('requests.get')
    def test_shallalist_http_error_propagates(self, mock_get):
        import requests
        mock_resp = self._mock_get()
        mock_resp.raise_for_status.side_effect = requests.HTTPError('503')
        mock_get.return_value = mock_resp
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(Exception):
                D.download_shallalist(Path(tmp))


if __name__ == '__main__':
    unittest.main()
