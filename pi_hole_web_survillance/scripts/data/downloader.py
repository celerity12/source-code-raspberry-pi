#!/usr/bin/env python3
"""
Pi-hole Analytics - Third-party domain category downloader

Downloads two complementary domain blacklists and merges them into a single
SQLite lookup database (data/third_party.db) used by fetcher.py.

Sources:
  UT1  — University of Toulouse (~3M domains, 90 categories)
          https://dsi.ut-capitole.fr/blacklists/
  Shallalist — community-maintained (~2M domains, 70 categories)
              http://www.shallalist.de/

Together they cover significantly more of the long tail than either alone.
Run weekly via systemd timer.
"""

import sqlite3
import tarfile
import tempfile
import requests
import logging
import yaml
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

# Ensure log directory exists before configuring the file handler
_LOG_DIR = BASE_DIR / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(_LOG_DIR / 'downloader.log'),
    ]
)
log = logging.getLogger(__name__)

DB_PATH = BASE_DIR / "data" / "third_party.db"

# ── Source URLs ───────────────────────────────────────────────────────────────

UT1_URL       = "https://dsi.ut-capitole.fr/blacklists/download/blacklists.tar.gz"
SHALLALIST_URL = "http://www.shallalist.de/Downloads/shallalist.tar.gz"

# ── Category maps ─────────────────────────────────────────────────────────────
# Each map translates source-specific folder names → internal project categories.
# Only folders present in the map are imported; everything else is skipped.

# UT1 (University of Toulouse) folder names → project categories.
# "publicite" is French for advertising.
CATEGORY_MAP = {
    "adult":           "adult",
    "publicite":       "ads_tracking",
    "social_networks": "social_media",
    "games":           "gaming",
    "streamingmedia":  "streaming",
    "shopping":        "shopping",
    "news":            "news",
    "education":       "educational",
    "malware":         "ads_tracking",
    "phishing":        "ads_tracking",
    "cryptojacking":   "ads_tracking",
}

# Shallalist folder names → project categories.
# Tarball structure: BL/<category>/domains  (root is "BL", not "blacklists")
# Non-commercial use only — see http://www.shallalist.de/licence.html
SHALLALIST_CATEGORY_MAP = {
    "adv":           "ads_tracking",
    "anonvpn":       "vpn_proxy",
    "chat":          "social_media",
    "education":     "educational",
    "finance":       "finance",
    "forum":         "social_media",
    "games":         "gaming",
    "government":    "government",
    "hacking":       "ads_tracking",   # hacking tool CDNs
    "hospitals":     "health",
    "library":       "educational",
    "models":        "adult",
    "movies":        "streaming",
    "music":         "music",
    "news":          "news",
    "podcasts":      "music",
    "porn":          "adult",
    "radiotv":       "streaming",
    "redirector":    "ads_tracking",   # URL shorteners / redirectors used by trackers
    "science":       "educational",
    "searchengines": "tech",
    "sex":           "adult",
    "shopping":      "shopping",
    "socialnet":     "social_media",
    "software":      "tech",
    "spyware":       "ads_tracking",
    "sports":        "sports",
    "travel":        "travel",
    "webmail":       "productivity",
    "webradio":      "music",
    "webtv":         "streaming",
}


# ── Download helpers ──────────────────────────────────────────────────────────

def _download(url: str, dest: Path, label: str) -> Path:
    """Stream-download url to dest. Returns dest path."""
    log.info(f"Downloading {label} from {url} ...")
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(dest, 'wb') as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
    log.info(f"{label} download complete: {dest.stat().st_size / 1_048_576:.1f} MB")
    return dest


def download_ut1(tmp_dir: Path) -> Path:
    """Download the UT1 tarball into tmp_dir and return its path."""
    return _download(UT1_URL, tmp_dir / "blacklists.tar.gz", "UT1")


def download_shallalist(tmp_dir: Path) -> Path:
    """Download the Shallalist tarball into tmp_dir and return its path."""
    return _download(SHALLALIST_URL, tmp_dir / "shallalist.tar.gz", "Shallalist")


# ── Database builder ──────────────────────────────────────────────────────────

def _import_tarball(conn, tarball: Path, category_map: dict) -> int:
    """
    Extract domain entries from one tarball and INSERT OR IGNORE into an
    already-open DB connection.

    Both UT1 and Shallalist use the same 3-level structure:
        <root>/<category>/domains
    where <root> is "blacklists" (UT1) or "BL" (Shallalist).
    The root folder name is ignored — only the category folder and the
    literal filename "domains" matter.

    Returns the number of rows inserted from this tarball.
    """
    inserted = 0
    with tarfile.open(tarball, 'r:gz') as tar:
        for member in tar.getmembers():
            parts = Path(member.name).parts
            # Expect exactly: <root> / <category> / domains
            if len(parts) != 3 or parts[2] != 'domains':
                continue
            source_cat = parts[1]
            project_cat = category_map.get(source_cat)
            if not project_cat:
                continue  # not in our map — skip

            f = tar.extractfile(member)
            if not f:
                continue

            batch = []
            for line in f:
                domain = line.decode('utf-8', errors='ignore').strip().lower()
                if domain and not domain.startswith('#'):
                    batch.append((domain, project_cat))
                    if len(batch) >= 10_000:
                        conn.executemany(
                            "INSERT OR IGNORE INTO domains (domain, category) VALUES (?, ?)",
                            batch,
                        )
                        inserted += len(batch)
                        batch = []
            if batch:
                conn.executemany(
                    "INSERT OR IGNORE INTO domains (domain, category) VALUES (?, ?)",
                    batch,
                )
                inserted += len(batch)

            log.info(f"  '{source_cat}' → '{project_cat}'  (+{inserted:,} total so far)")

    return inserted


def build_database(sources: list) -> Path:
    """
    Build a new third_party.db from one or more (tarball, category_map) pairs.

    sources: list of (Path, dict) — each tuple is a tarball path and the
             category map to use for it.

    Writes to a .tmp file first; caller atomically renames it to DB_PATH.
    Returns the .tmp path.

    When the same domain appears in multiple sources, the first source wins
    (INSERT OR IGNORE). UT1 should be passed first as it is more curated.
    """
    tmp_db = DB_PATH.with_suffix('.tmp')
    if tmp_db.exists():
        tmp_db.unlink()

    conn = sqlite3.connect(tmp_db)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("""
        CREATE TABLE domains (
            domain   TEXT PRIMARY KEY,
            category TEXT NOT NULL
        )
    """)

    total = 0
    for tarball, category_map in sources:
        label = tarball.name
        log.info(f"Importing {label} ...")
        n = _import_tarball(conn, tarball, category_map)
        total += n
        log.info(f"{label} imported {n:,} entries (running total: {total:,})")

    conn.execute("CREATE INDEX idx_domain ON domains(domain)")
    conn.commit()
    conn.close()
    log.info(f"Database built with {total:,} domain entries total")
    return tmp_db


# ── Cache invalidation ────────────────────────────────────────────────────────

def invalidate_cache():
    """
    Clear 'other'-categorized entries from the domain_categories cache so
    fetcher.py re-evaluates them against the new third-party data next run.
    """
    analytics_db = BASE_DIR / "data" / "analytics.db"
    if not analytics_db.exists():
        return
    conn = sqlite3.connect(analytics_db)
    rows = conn.execute(
        "DELETE FROM domain_categories WHERE category = 'other'"
    ).rowcount
    conn.commit()
    conn.close()
    log.info(f"Cleared {rows:,} 'other' entries from domain_categories cache")


# ── Online category rules ─────────────────────────────────────────────────────

_ONLINE_CATEGORIES_PATH = BASE_DIR / "config" / "categories_online.yaml"


def update_category_rules(rules_update_url: str):
    """
    Download an updated categories YAML from rules_update_url and save it to
    config/categories_online.yaml.  config.py merges this on every load.
    Non-fatal — if download fails, existing file is left untouched.
    """
    if not rules_update_url:
        log.info("rules_update_url not set — skipping online category rules update")
        return

    log.info(f"Fetching online category rules from {rules_update_url} ...")
    try:
        resp = requests.get(rules_update_url, timeout=30)
        resp.raise_for_status()
        rules = yaml.safe_load(resp.text)
        if not isinstance(rules, dict):
            raise ValueError(f"Expected a YAML dict, got {type(rules).__name__}")
        _ONLINE_CATEGORIES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_ONLINE_CATEGORIES_PATH, 'w') as f:
            yaml.dump(rules, f, default_flow_style=False, allow_unicode=True)
        log.info(f"Online category rules saved: {len(rules)} categories → {_ONLINE_CATEGORIES_PATH}")
    except Exception as e:
        log.warning(f"Online category rules update failed: {e}")


# ── Entry point ───────────────────────────────────────────────────────────────

def run_download():
    import sys
    from scripts.core.config import load_config

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        sources  = []

        # ── Source 1: UT1 (required) ──────────────────────────────────────────
        try:
            ut1_tarball = download_ut1(tmp_path)
            sources.append((ut1_tarball, CATEGORY_MAP))
        except Exception as e:
            log.error(f"UT1 download failed: {e}")
            # UT1 is the primary source — if it fails, abort rather than
            # building a DB from Shallalist alone (incomplete coverage).
            raise

        # Shallalist (shallalist.de) has been offline since 2024 — skipped.

        tmp_db = build_database(sources)
        # Atomic swap — replaces live DB only after new one is fully built
        tmp_db.replace(DB_PATH)
        log.info(f"Third-party DB live at {DB_PATH}")

    invalidate_cache()

    # Refresh online category rules if a URL is configured
    try:
        cfg = load_config()
        update_category_rules(cfg.get("rules_update_url", ""))
    except Exception as e:
        log.warning(f"Could not load config for category rules update: {e}")

    log.info("Download complete.")


if __name__ == '__main__':
    run_download()
