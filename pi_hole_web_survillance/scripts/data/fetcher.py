#!/usr/bin/env python3
"""
Pi-hole Analytics - Core Data Fetcher & Database Manager
Fetches query data from Pi-hole API and stores in SQLite for analysis.
"""

import sqlite3
import requests
import logging
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

# ── Pi-hole v6 status string → v5-compatible integer ─────────────────────────
# v6 uses human-readable strings; we normalise to integers so the rest of the
# pipeline (store_queries, rebuild_daily_summary) needs no changes.
_V6_STATUS_MAP = {
    # ── Allowed ──────────────────────────────────────────────────────────────
    "FORWARDED":                 2,
    "CACHE":                     3,
    "CACHE_STALE":               3,
    "RETRIED":                   2,
    "RETRIED_DNSSEC":            2,
    "IN_PROGRESS":               2,
    "DBBUSY":                    2,
    # ── Blocked ───────────────────────────────────────────────────────────────
    "GRAVITY":                   1,
    "REGEX_BLACKLIST":           4,
    "EXACT_BLACKLIST":           5,
    "BLACKLIST":                 6,
    "DENYLIST":                  6,   # v6.4 name for blacklist
    "EXTERNAL_BLOCKED_IP":       7,
    "EXTERNAL_BLOCKED_NULL":     8,
    "EXTERNAL_BLOCKED_NXRA":     8,   # NXDOMAIN-based external block
    "EXTERNAL_BLOCKED_EDE15":    8,   # EDE15-based external block
    "GRAVITY_CNAME":             9,
    "REGEX_BLACKLIST_CNAME":     10,
    "REGEX_CNAME":               10,  # v6.4 name
    "EXACT_BLACKLIST_CNAME":     11,
    "DENYLIST_CNAME":            11,  # v6.4 name
    "SPECIAL_DOMAIN":            6,   # pi.hole, _gateway etc — Pi-hole intercepts, counts as blocked
}

from scripts.core.config import load_config
from scripts.core.device_resolver import (  # MAC/hostname-aware client identification
    refresh_device_registry, build_registry_map, resolve_client
)

BASE_DIR   = Path(__file__).resolve().parents[2]
DB_PATH    = BASE_DIR / "data" / "analytics.db"
TP_DB_PATH = BASE_DIR / "data" / "third_party.db"

from scripts.core.logging_setup import get_logger
log = get_logger(__name__, log_file=BASE_DIR / 'logs' / 'fetcher.log')


def init_database(conn):
    """Create tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS queries (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   INTEGER NOT NULL,
            domain      TEXT NOT NULL,
            client_ip   TEXT NOT NULL,
            client_name TEXT,
            query_type  TEXT,
            -- Pi-hole query status values:
            --   1=blocked(gravity)  2=forwarded(allowed)  3=cached(allowed)
            --   4=blocked(regex)    5=blocked(wildcard)    6=blocked(blacklist)
            --   9=blocked(gravity/CNAME)  10=blocked(blacklist/CNAME)
            status      INTEGER,
            category    TEXT,
            -- Plain column; value is computed in Python (datetime.fromtimestamp) and
            -- inserted explicitly so queries roll over at local midnight without
            -- relying on SQLite's 'localtime' modifier (non-deterministic in 3.38+)
            date        TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_queries_timestamp ON queries(timestamp);
        CREATE INDEX IF NOT EXISTS idx_queries_client    ON queries(client_ip);
        CREATE INDEX IF NOT EXISTS idx_queries_domain    ON queries(domain);
        CREATE INDEX IF NOT EXISTS idx_queries_date      ON queries(date);
        CREATE INDEX IF NOT EXISTS idx_queries_category  ON queries(category);

        CREATE TABLE IF NOT EXISTS fetch_state (
            key   TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS domain_categories (
            domain   TEXT PRIMARY KEY,
            category TEXT,
            updated  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS daily_summary (
            date              TEXT,
            client_ip         TEXT,
            client_name       TEXT,
            total_queries     INTEGER DEFAULT 0,
            blocked_queries   INTEGER DEFAULT 0,
            unique_domains    INTEGER DEFAULT 0,
            top_category      TEXT,
            PRIMARY KEY (date, client_ip)
        );

        -- Device registry: MAC → last known IP, hostname, auto-detected type.
        -- Populated by device_resolver.py from the Pi-hole network API.
        -- custom_name is set manually and never overwritten automatically.
        CREATE TABLE IF NOT EXISTS device_registry (
            mac         TEXT PRIMARY KEY,
            last_ip     TEXT NOT NULL,
            hostname    TEXT,
            device_type TEXT,
            custom_name TEXT,
            last_seen   TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_device_ip ON device_registry(last_ip);

        CREATE TABLE IF NOT EXISTS manually_blocked (
            domain      TEXT PRIMARY KEY,
            category    TEXT,
            blocked_at  TEXT DEFAULT (datetime('now')),
            note        TEXT
        );

        CREATE TABLE IF NOT EXISTS ai_summaries (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            period       TEXT NOT NULL,
            run_type     TEXT NOT NULL DEFAULT 'ondemand',
            start_date   TEXT NOT NULL,
            end_date     TEXT NOT NULL,
            summary_text TEXT NOT NULL,
            model        TEXT,
            generated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_ai_summaries_lookup
            ON ai_summaries(period, run_type, generated_at DESC);

        CREATE TABLE IF NOT EXISTS ignored_domains (
            domain      TEXT PRIMARY KEY,
            ignored_at  TEXT DEFAULT (datetime('now'))
        );
    """)
    # Migrate existing DBs: add run_type column if absent
    try:
        conn.execute("ALTER TABLE ai_summaries ADD COLUMN run_type TEXT NOT NULL DEFAULT 'ondemand'")
    except Exception:
        pass  # Column already exists
    conn.commit()


def categorize_domain(domain: str, category_rules: dict) -> str:
    """Categorize a domain based on config rules."""
    domain_lower = domain.lower().rstrip('.')  # normalise + strip trailing FQDN dot

    # Categories are checked in config order; the FIRST matching category wins.
    # Within each category, domain list is checked before keywords — more specific
    # rules take precedence over broad keyword matches.
    for category, rules in category_rules.items():
        # Domain match: exact ('ytimg.com') or suffix ('i.ytimg.com' ends with '.ytimg.com')
        for d in rules.get('domains', []):
            if domain_lower == d or domain_lower.endswith('.' + d):
                return category
        # Keyword match: substring anywhere in the full domain string
        for kw in rules.get('keywords', []):
            if kw in domain_lower:
                return category

    return 'other'


def lookup_third_party(tp_conn, domain: str) -> str:
    """
    Check the UT1 third-party DB for a category.
    Tries exact match first, then walks up the domain tree
    (e.g. sub.example.com → example.com) to handle subdomains.
    Returns 'other' if not found.
    """
    parts = domain.split('.')
    # Walk from the full domain up to the registrable domain.
    # i=0: 'cdn.social.example.com'  i=1: 'social.example.com'  i=2: 'example.com'
    # We stop one level before the bare TLD (range stops at len-1) so we never
    # match a naked TLD like 'com'.
    for i in range(len(parts) - 1):
        candidate = '.'.join(parts[i:])
        row = tp_conn.execute(
            "SELECT category FROM domains WHERE domain = ?", (candidate,)
        ).fetchone()
        if row:
            return row[0]
    return 'other'


def open_third_party_db():
    """Open the third-party DB read-only if it exists, else return None."""
    if TP_DB_PATH.exists():
        conn = sqlite3.connect(f"file:{TP_DB_PATH}?mode=ro", uri=True)
        return conn
    return None


def get_cached_category(conn, domain: str, rules: dict, tp_conn=None) -> str:
    """Return cached category or compute and cache it."""
    # Cache hit: skip recomputation for domains we've seen before
    row = conn.execute(
        "SELECT category FROM domain_categories WHERE domain = ?", (domain,)
    ).fetchone()
    if row:
        return row[0]

    # Priority: user-defined config rules first (more specific / intentional),
    # third-party UT1 DB second (broad coverage), 'other' as final fallback.
    cat = categorize_domain(domain, rules)
    if cat == 'other' and tp_conn:
        cat = lookup_third_party(tp_conn, domain)

    # Persist to cache — next call for this domain is an instant lookup
    conn.execute(
        "INSERT OR REPLACE INTO domain_categories (domain, category) VALUES (?, ?)",
        (domain, cat)
    )
    return cat


def _is_pihole_v6(cfg: dict) -> bool:
    """Return True if the Pi-hole instance exposes the v6 REST API.
    v6 serves /api/info/version with any HTTP response (200 or 401).
    v5 returns 404 or does not route that path at all.
    """
    try:
        r = requests.get(f"{cfg['pihole']['host']}/api/info/version", timeout=5)
        return r.status_code in (200, 401)
    except Exception:
        return False


def _get_v6_sid(cfg: dict) -> str:
    """Authenticate with Pi-hole v6 and return a session ID.
    Tries password first (v6 uses the web password), then api_token as fallback."""
    base = cfg['pihole']['host']
    for cred in filter(None, [
        cfg['pihole'].get('password', ''),
        cfg['pihole'].get('api_token', ''),
    ]):
        resp = requests.post(f"{base}/api/auth", json={"password": cred}, timeout=10)
        if resp.ok:
            sid = resp.json().get("session", {}).get("sid", "")
            if sid:
                return sid
    raise ValueError(
        "Pi-hole v6 auth failed — check that 'password' in config.yaml "
        "matches your Pi-hole web interface password"
    )


def _fetch_pihole_data_v6(cfg: dict) -> list:
    """Fetch queries from Pi-hole v6 REST API since the last stored timestamp."""
    base = cfg['pihole']['host']
    try:
        sid = _get_v6_sid(cfg)
    except Exception as e:
        log.error(f"Pi-hole v6 auth failed: {e}")
        return []

    headers  = {"X-FTL-SID": sid}
    since_ts = int((datetime.now() - timedelta(hours=24)).timestamp())
    until_ts = int(datetime.now().timestamp())

    queries = []
    try:
        # Fetch up to 10 000 queries in one request — avoids unbounded pagination
        # hanging on large history. 15-min incremental fetches will never hit this.
        params = {"from": since_ts, "until": until_ts, "length": 10000}
        resp = requests.get(f"{base}/api/queries", params=params,
                            headers=headers, timeout=60)
        resp.raise_for_status()
        data  = resp.json()
        batch = data.get("queries", [])

        for q in batch:
            ts        = int(q.get("time", 0))
            qtype     = q.get("type", "A")
            domain    = q.get("domain", "")
            client_ip = (q.get("client") or {}).get("ip", "")
            status_v6 = q.get("status", "")
            status = _V6_STATUS_MAP.get(
                status_v6,
                1 if "BLOCK" in status_v6.upper() or "GRAVITY" in status_v6.upper() else 2
            )
            queries.append([ts, qtype, domain, client_ip, status])

        log.info(f"Fetched {len(queries)} queries from Pi-hole (v6)")
        return queries
    except requests.RequestException as e:
        log.error(f"Failed to fetch Pi-hole v6 data: {e}")
        return []


def fetch_pihole_data(cfg: dict) -> list:
    """Fetch recent queries from Pi-hole API (v5 and v6 supported)."""
    if _is_pihole_v6(cfg):
        return _fetch_pihole_data_v6(cfg)

    # ── Pi-hole v5 path ───────────────────────────────────────────────────────
    base  = cfg['pihole']['host'] + cfg['pihole'].get('api_path', '/admin/api.php')
    token = cfg['pihole']['api_token']
    try:
        # Token may contain '/' and '=' — percent-encode for safe URL transport
        url  = f"{base}?getAllQueries&auth={quote(token, safe='')}"
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        queries = resp.json().get('data', [])
        log.info(f"Fetched {len(queries)} queries from Pi-hole (v5)")
        return queries
    except requests.RequestException as e:
        log.error(f"Failed to fetch Pi-hole data: {e}")
        return []


def get_last_fetch_time(conn) -> int:
    """Get the last fetched timestamp from state table."""
    row = conn.execute(
        "SELECT value FROM fetch_state WHERE key='last_timestamp'"
    ).fetchone()
    if row:
        return int(row[0])
    # Default: 24h ago
    return int((datetime.now() - timedelta(hours=24)).timestamp())


def set_last_fetch_time(conn, ts: int):
    conn.execute(
        "INSERT OR REPLACE INTO fetch_state (key, value) VALUES ('last_timestamp', ?)",
        (str(ts),)
    )
    conn.commit()


def store_queries(conn, queries: list, cfg: dict, tp_conn=None, registry=None):
    """Parse and store new queries into the database.

    Args:
        registry: Pre-loaded device registry dict from build_registry_map().
                  When None, falls back to cfg['clients'] IP mapping (legacy).
    """
    cat_rules  = cfg.get('categories', {})
    last_ts    = get_last_fetch_time(conn)
    new_max_ts = last_ts
    inserted   = 0
    _registry  = registry or {}

    for q in queries:
        # Pi-hole getAllQueries row format: [timestamp, type, domain, client, status, ...]
        try:
            ts         = int(q[0])
            qtype      = str(q[1])
            domain     = str(q[2]).lower().strip()
            client_ip  = str(q[3])
            status     = int(q[4])
        except (IndexError, ValueError, TypeError):
            continue  # skip malformed rows silently

        # Incremental fetch: skip anything we already stored on a previous run
        if ts <= last_ts:
            continue

        # Resolve IP → best available name via MAC/hostname/config/auto-detection
        client_name = resolve_client(client_ip, cfg, _registry)
        category    = get_cached_category(conn, domain, cat_rules, tp_conn)
        # Compute date in Python using local time (avoids SQLite 3.38+ non-determinism)
        date_str    = datetime.fromtimestamp(ts).strftime('%Y-%m-%d')

        # INSERT OR IGNORE: duplicate timestamps (same query seen twice) are skipped
        conn.execute("""
            INSERT OR IGNORE INTO queries
                (timestamp, domain, client_ip, client_name, query_type, status, category, date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (ts, domain, client_ip, client_name, qtype, status, category, date_str))

        if ts > new_max_ts:
            new_max_ts = ts
        inserted += 1

    conn.commit()
    set_last_fetch_time(conn, new_max_ts)
    log.info(f"Inserted {inserted} new queries. New max timestamp: {new_max_ts}")
    return inserted


def rebuild_daily_summary(conn, date_str: str = None):
    """Rebuild the daily_summary table for a specific date (or today)."""
    if not date_str:
        date_str = datetime.now().strftime('%Y-%m-%d')

    # Delete before re-inserting so a partial day can be rebuilt incrementally
    conn.execute("DELETE FROM daily_summary WHERE date = ?", (date_str,))

    conn.execute("""
        INSERT INTO daily_summary
            (date, client_ip, client_name, total_queries, blocked_queries, unique_domains, top_category)
        SELECT
            date,
            client_ip,
            MAX(client_name)                              AS client_name,
            COUNT(*)                                       AS total_queries,
            -- Blocked statuses (explicit): 1=GRAVITY, 4=REGEX_BLACKLIST, 5=EXACT_BLACKLIST,
            --   6=BLACKLIST, 7=EXT_BLOCKED_IP, 8=EXT_BLOCKED_NULL, 9=GRAVITY_CNAME,
            --   10=REGEX_CNAME, 11=BLACKLIST_CNAME
            -- Allowed: 2=FORWARDED, 3=CACHED, 0=UNKNOWN, 12=RETRIED, 13=RETRIED_DNSSEC,
            --   14=IN_PROGRESS, 15=DBBUSY, 16=SPECIAL
            SUM(CASE WHEN status IN (1,4,5,6,7,8,9,10,11) THEN 1 ELSE 0 END) AS blocked_queries,
            COUNT(DISTINCT domain)                         AS unique_domains,
            -- Correlated subquery: find the most-queried category for this client today,
            -- ignoring ads/tracking and uncategorised noise so the label is meaningful
            (
                SELECT category FROM queries q2
                WHERE q2.date = q1.date AND q2.client_ip = q1.client_ip
                  AND category NOT IN ('ads_tracking','other')
                GROUP BY category ORDER BY COUNT(*) DESC LIMIT 1
            )                                              AS top_category
        FROM queries q1
        WHERE date = ?
        GROUP BY date, client_ip
    """, (date_str,))
    conn.commit()
    log.info(f"Daily summary rebuilt for {date_str}")


def purge_old_data(conn, retention_days: int = 90):
    """Remove data older than retention period."""
    cutoff = (datetime.now() - timedelta(days=retention_days)).strftime('%Y-%m-%d')
    conn.execute("DELETE FROM queries WHERE date < ?", (cutoff,))
    conn.execute("DELETE FROM daily_summary WHERE date < ?", (cutoff,))
    conn.commit()
    log.info(f"Purged data older than {cutoff}")


def run_fetch():
    """Main entry point: fetch, store, summarize."""
    cfg = load_config()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    Path(BASE_DIR / "logs").mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    init_database(conn)

    tp_conn = open_third_party_db()
    if tp_conn:
        log.info("Third-party category DB loaded.")
    else:
        log.info("No third-party DB found — using config rules only.")

    # Refresh device registry from Pi-hole network API (MAC + hostname + vendor)
    # then build an in-memory map for O(1) lookup during query processing.
    refresh_device_registry(conn, cfg)
    registry = build_registry_map(conn)

    queries = fetch_pihole_data(cfg)
    if queries:
        store_queries(conn, queries, cfg, tp_conn, registry)

    if tp_conn:
        tp_conn.close()

    rebuild_daily_summary(conn)
    purge_old_data(conn, cfg['reporting'].get('data_retention_days', 90))
    conn.close()
    log.info("Fetch complete.")


if __name__ == '__main__':
    run_fetch()
