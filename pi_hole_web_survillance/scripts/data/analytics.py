#!/usr/bin/env python3
"""
Pi-hole Analytics - Query Engine
Provides all analytics queries used by reports and the dashboard.
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH  = BASE_DIR / "data" / "analytics.db"


def _ensure_schema(conn):
    """Create all tables if they don't exist.

    Mirrors fetcher.init_database() so that the reporter and dashboard
    never crash with 'no such table' on a fresh install or empty DB.
    This is intentionally lightweight — fetcher.py is still the
    canonical schema owner; this just guarantees the tables exist.
    """
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS queries (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   INTEGER NOT NULL,
            domain      TEXT NOT NULL,
            client_ip   TEXT NOT NULL,
            client_name TEXT,
            query_type  TEXT,
            status      INTEGER,
            category    TEXT,
            date        TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_queries_date     ON queries(date);
        CREATE INDEX IF NOT EXISTS idx_queries_client   ON queries(client_ip);
        CREATE INDEX IF NOT EXISTS idx_queries_domain   ON queries(domain);
        CREATE INDEX IF NOT EXISTS idx_queries_category ON queries(category);

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
    # Migrate existing DBs: add run_type column if absent (ALTER TABLE fails silently)
    try:
        conn.execute("ALTER TABLE ai_summaries ADD COLUMN run_type TEXT NOT NULL DEFAULT 'ondemand'")
    except Exception:
        pass  # Column already exists
    conn.commit()


def get_conn():
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        _ensure_schema(conn)
        return conn
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to connect to database at {DB_PATH}: {e}")


def safe_execute(conn, query, params=()):
    """Execute a query with error handling."""
    try:
        return conn.execute(query, params).fetchall()
    except sqlite3.Error as e:
        raise RuntimeError(f"Database query failed: {e}")


# ── Helper ────────────────────────────────────────────────────────────────────

def _date_filter(date: str, end_date: str = None):
    """Return (where_fragment, params_list) for single date or range."""
    if end_date and end_date != date:
        return "date BETWEEN ? AND ?", [date, end_date]
    return "date = ?", [date]


def date_range(period: str):
    """Return (start_date, end_date) strings for a named period."""
    today = datetime.now().date()
    if period == 'today':
        return str(today), str(today)
    elif period == 'yesterday':
        d = today - timedelta(days=1)
        return str(d), str(d)
    elif period == 'week':
        # days=6 back + today = 7 total days (inclusive on both ends)
        return str(today - timedelta(days=6)), str(today)
    elif period == 'month':
        # days=29 back + today = 30 total days
        return str(today - timedelta(days=29)), str(today)
    else:
        raise ValueError(f"Unknown period: {period}")


# ── Client Usage ──────────────────────────────────────────────────────────────

def client_usage(date: str, end_date: str = None, conn=None) -> list:
    """Total/blocked queries per client for a given date or date range."""
    close = conn is None
    if conn is None: conn = get_conn()
    frag, params = _date_filter(date, end_date)
    rows = safe_execute(conn, f"""
        SELECT client_ip, MAX(client_name) AS client_name,
               SUM(total_queries) AS total_queries,
               SUM(blocked_queries) AS blocked_queries,
               SUM(unique_domains) AS unique_domains,
               MAX(top_category) AS top_category
        FROM daily_summary
        WHERE {frag}
        GROUP BY client_ip
        ORDER BY total_queries DESC
    """, params)
    if close: conn.close()
    return [dict(r) for r in rows]


def client_hourly(client_ip: str, date: str, conn=None) -> list:
    """Queries per hour for a client on a given date (for timeline charts)."""
    close = conn is None
    if conn is None: conn = get_conn()
    rows = safe_execute(conn, """
        SELECT
            strftime('%H', timestamp, 'unixepoch', 'localtime') AS hour,
            COUNT(*) AS queries
        FROM queries
        WHERE client_ip = ? AND date = ?
        GROUP BY hour
        ORDER BY hour
    """, (client_ip, date))
    if close: conn.close()
    return [dict(r) for r in rows]


def all_clients_hourly(date: str, cfg: dict = None, conn=None) -> dict:
    """Queries per hour per client for a date. Returns {client_ip: [{hour, queries}]}."""
    close = conn is None
    if conn is None: conn = get_conn()
    params = [date]
    where_extra = ""
    if cfg:
        excluded = cfg.get('excluded_devices', [])
        if excluded:
            conditions = []
            for ex in excluded:
                ex_lower = ex.lower()
                conditions.append("client_name NOT LIKE ?")
                params.append(f'%{ex_lower}%')
                conditions.append("client_ip NOT LIKE ?")
                params.append(f'%{ex_lower}%')
            where_extra = " AND (" + " AND ".join(conditions) + ")"
    rows = safe_execute(conn, f"""
        SELECT
            client_ip, client_name,
            strftime('%H', timestamp, 'unixepoch', 'localtime') AS hour,
            COUNT(*) AS queries
        FROM queries
        WHERE date = ?{where_extra}
        GROUP BY client_ip, hour
        ORDER BY client_ip, hour
    """, params)
    if close: conn.close()

    result = {}
    for r in rows:
        key = r['client_ip']
        if key not in result:
            result[key] = {'name': r['client_name'], 'hours': []}
        result[key]['hours'].append({'hour': r['hour'], 'queries': r['queries']})
    return result


# ── Domain Analysis ───────────────────────────────────────────────────────────

def top_domains(date: str, end_date: str = None, limit: int = 20, client_ip: str = None, cfg: dict = None, conn=None) -> list:
    close = conn is None
    if conn is None: conn = get_conn()
    frag, params = _date_filter(date, end_date)
    where = f"WHERE {frag}"
    if client_ip:
        where += " AND client_ip = ?"
        params.append(client_ip)
    if cfg:
        excluded = cfg.get('excluded_devices', [])
        if excluded:
            conditions = []
            for ex in excluded:
                ex_lower = ex.lower()
                conditions.append("client_name NOT LIKE ?")
                params.append(f'%{ex_lower}%')
                conditions.append("client_ip NOT LIKE ?")
                params.append(f'%{ex_lower}%')
            where += " AND (" + " AND ".join(conditions) + ")"
    ign_frag, ign_params = _ignored_fragment(conn)
    where += ign_frag
    params.extend(ign_params)
    query = f"""
        SELECT domain, category, COUNT(*) AS queries,
               MAX(client_name) AS client_name
        FROM queries {where}
        GROUP BY domain
        ORDER BY queries DESC
        LIMIT ?
    """
    rows = safe_execute(conn, query, params + [limit])
    if close: conn.close()
    return [dict(r) for r in rows]


def category_breakdown(date: str, end_date: str = None, client_ip: str = None, cfg: dict = None, conn=None) -> list:
    close = conn is None
    if conn is None: conn = get_conn()
    frag, params = _date_filter(date, end_date)
    where = f"WHERE {frag}"
    if client_ip:
        where += " AND client_ip = ?"
        params.append(client_ip)
    if cfg:
        excluded = cfg.get('excluded_devices', [])
        if excluded:
            conditions = []
            for ex in excluded:
                ex_lower = ex.lower()
                conditions.append("client_name NOT LIKE ?")
                params.append(f'%{ex_lower}%')
                conditions.append("client_ip NOT LIKE ?")
                params.append(f'%{ex_lower}%')
            where += " AND (" + " AND ".join(conditions) + ")"
    query = f"""
        SELECT category, COUNT(*) AS queries,
               COUNT(DISTINCT domain) AS unique_domains
        FROM queries {where}
        GROUP BY category
        ORDER BY queries DESC
    """
    rows = safe_execute(conn, query, params)
    if close: conn.close()
    return [dict(r) for r in rows]


def new_domains(date: str, end_date: str = None, cfg: dict = None, conn=None) -> list:
    """Domains seen for the first time in the given period."""
    close = conn is None
    if conn is None: conn = get_conn()
    frag, params = _date_filter(date, end_date)
    where_extra = ""
    if cfg:
        excluded = cfg.get('excluded_devices', [])
        if excluded:
            conditions = []
            for ex in excluded:
                ex_lower = ex.lower()
                conditions.append("client_name NOT LIKE ?")
                params.append(f'%{ex_lower}%')
                conditions.append("client_ip NOT LIKE ?")
                params.append(f'%{ex_lower}%')
            where_extra = " AND (" + " AND ".join(conditions) + ")"
    ign_frag, ign_params = _ignored_fragment(conn)
    # Domains that appear in the period but never before the period start
    rows = safe_execute(conn, f"""
        SELECT domain, category, client_ip, client_name, COUNT(*) AS queries
        FROM queries
        WHERE {frag}{where_extra}{ign_frag}
          AND domain NOT IN (
              SELECT DISTINCT domain FROM queries WHERE date < ?
          )
        GROUP BY domain
        ORDER BY queries DESC
        LIMIT 50
    """, params + ign_params + [date])
    if close: conn.close()
    return [dict(r) for r in rows]


def client_range_summary(start_date: str, end_date: str, conn=None) -> list:
    """Per-client totals aggregated over a date range (for weekly/monthly device cards)."""
    close = conn is None
    if conn is None: conn = get_conn()
    rows = conn.execute("""
        SELECT client_ip, MAX(client_name) AS client_name,
               SUM(total_queries) AS today_q,
               SUM(unique_domains) AS today_d,
               0 AS yesterday_q,
               0 AS week_avg_q
        FROM daily_summary
        WHERE date BETWEEN ? AND ?
        GROUP BY client_ip
        ORDER BY today_q DESC
    """, (start_date, end_date)).fetchall()
    if close: conn.close()
    return [dict(r) for r in rows]


# ── Time Comparisons ─────────────────────────────────────────────────────────

def daily_trend(days: int = 30, client_ip: str = None, conn=None) -> list:
    """Total queries per day for the last N days."""
    close = conn is None
    if conn is None: conn = get_conn()
    start = str((datetime.now().date() - timedelta(days=days-1)))
    where = "WHERE date >= ?"
    params = [start]
    if client_ip:
        where += " AND client_ip = ?"
        params.append(client_ip)
    rows = conn.execute(f"""
        SELECT date,
               SUM(total_queries)   AS total_queries,
               SUM(blocked_queries) AS blocked_queries,
               SUM(unique_domains)  AS unique_domains
        FROM daily_summary {where}
        GROUP BY date
        ORDER BY date
    """, params).fetchall()
    if close: conn.close()
    return [dict(r) for r in rows]


def compare_periods(date: str, conn=None) -> dict:
    """Compare today's stats with yesterday, 7d avg, 30d avg."""
    close = conn is None
    if conn is None: conn = get_conn()

    def avg(start, end):
        row = conn.execute("""
            SELECT AVG(total_q) AS avg_q, AVG(unique_d) AS avg_d
            FROM (
                SELECT date, SUM(total_queries) AS total_q,
                             SUM(unique_domains) AS unique_d
                FROM daily_summary WHERE date BETWEEN ? AND ?
                GROUP BY date
            )
        """, (start, end)).fetchone()
        return dict(row) if row else {'avg_q': 0, 'avg_d': 0}

    today     = date
    yesterday = str((datetime.strptime(date, '%Y-%m-%d').date() - timedelta(days=1)))
    w_start   = str((datetime.strptime(date, '%Y-%m-%d').date() - timedelta(days=7)))
    m_start   = str((datetime.strptime(date, '%Y-%m-%d').date() - timedelta(days=30)))

    def day_total(d):
        row = conn.execute("""
            SELECT SUM(total_queries) AS tq, SUM(unique_domains) AS ud
            FROM daily_summary WHERE date = ?
        """, (d,)).fetchone()
        return {'avg_q': row['tq'] or 0, 'avg_d': row['ud'] or 0}

    result = {
        'today':     day_total(today),
        'yesterday': day_total(yesterday),
        # week_avg and month_avg end at *yesterday* (not today) so the averages
        # represent completed days only — comparing today against a full-day baseline
        'week_avg':  avg(w_start, yesterday),
        'month_avg': avg(m_start, yesterday),
    }
    if close: conn.close()
    return result


def client_compare(date: str, conn=None) -> list:
    """Per-client comparison: today vs yesterday vs 7d avg."""
    close = conn is None
    if conn is None: conn = get_conn()
    yesterday = str((datetime.strptime(date, '%Y-%m-%d').date() - timedelta(days=1)))
    w_start   = str((datetime.strptime(date, '%Y-%m-%d').date() - timedelta(days=7)))

    # Three CTEs joined on client_ip so each row has today / yesterday / 7d-avg
    # in a single pass. LEFT JOINs ensure clients active today but absent
    # yesterday (or last week) still appear with 0 as their historical values.
    rows = conn.execute("""
        WITH today_data AS (
            SELECT client_ip, client_name, total_queries AS today_q, unique_domains AS today_d
            FROM daily_summary WHERE date = ?
        ),
        yest_data AS (
            SELECT client_ip, total_queries AS yest_q
            FROM daily_summary WHERE date = ?
        ),
        week_data AS (
            SELECT client_ip, AVG(total_queries) AS week_avg_q
            FROM daily_summary WHERE date BETWEEN ? AND ?
            GROUP BY client_ip
        )
        SELECT t.client_ip, t.client_name,
               t.today_q, t.today_d,
               COALESCE(y.yest_q, 0)      AS yesterday_q,
               COALESCE(w.week_avg_q, 0)  AS week_avg_q
        FROM today_data t
        LEFT JOIN yest_data y ON y.client_ip = t.client_ip
        LEFT JOIN week_data w ON w.client_ip = t.client_ip
        ORDER BY t.today_q DESC
    """, (date, yesterday, w_start, yesterday)).fetchall()
    if close: conn.close()
    return [dict(r) for r in rows]


# ── Network-wide Stats ────────────────────────────────────────────────────────

def network_summary(date: str, end_date: str = None, conn=None) -> dict:
    close = conn is None
    if conn is None: conn = get_conn()
    frag, params = _date_filter(date, end_date)
    row = conn.execute(f"""
        SELECT
            SUM(total_queries)   AS total_queries,
            SUM(blocked_queries) AS blocked_queries,
            SUM(unique_domains)  AS unique_domains,
            COUNT(DISTINCT client_ip) AS active_clients
        FROM daily_summary WHERE {frag}
    """, params).fetchone()
    if close: conn.close()
    return dict(row) if row else {}


def blocked_domains_top(date: str, limit: int = 10, conn=None) -> list:
    close = conn is None
    if conn is None: conn = get_conn()
    # Exclude status 2 (forwarded/allowed) and 3 (cached/allowed) —
    # everything else (gravity blocks, regex blocks, blacklist, etc.) is treated
    # as a blocked query for the purposes of this top-blocked-domains list.
    rows = conn.execute("""
        SELECT domain, COUNT(*) AS blocked_count, MAX(category) AS category
        FROM queries
        WHERE date = ? AND status IN (1,4,5,6,7,8,9,10,11)
        GROUP BY domain
        ORDER BY blocked_count DESC
        LIMIT ?
    """, (date, limit)).fetchall()
    if close: conn.close()
    return [dict(r) for r in rows]


def categorization_stats(date: str, conn=None) -> dict:
    """Get statistics on how domains were categorized for a given date."""
    close = conn is None
    if conn is None: conn = get_conn()
    
    # Get all unique domains for the date
    domains_row = conn.execute("""
        SELECT COUNT(DISTINCT domain) AS total_domains
        FROM queries WHERE date = ?
    """, (date,)).fetchone()
    
    total_domains = domains_row['total_domains'] if domains_row else 0
    
    # For now, we'll count categories. In a future enhancement, we could
    # distinguish between config-based and third-party categorizations
    # by checking against the config rules and third-party DB
    category_counts = conn.execute("""
        SELECT category, COUNT(DISTINCT domain) AS domain_count
        FROM queries 
        WHERE date = ?
        GROUP BY category
        ORDER BY domain_count DESC
    """, (date,)).fetchall()
    
    stats = {
        'total_domains': total_domains,
        'categories': {row['category']: row['domain_count'] for row in category_counts}
    }
    
    if close: conn.close()
    return stats


def uncategorized_domains(date: str, limit: int = 20, conn=None) -> list:
    """Get domains categorized as 'other' (uncategorized) for a given date."""
    close = conn is None
    if conn is None: conn = get_conn()
    rows = conn.execute("""
        SELECT domain, client_name, client_ip, COUNT(*) AS queries
        FROM queries
        WHERE date = ? AND category = 'other'
        GROUP BY domain
        ORDER BY queries DESC
        LIMIT ?
    """, (date, limit)).fetchall()
    if close: conn.close()
    return [dict(r) for r in rows]


def top_domains_by_category(date: str, category: str, end_date: str = None, limit: int = 10, client_ip: str = None, conn=None) -> list:
    """Get top domains for a specific category, optionally filtered by client IP."""
    close = conn is None
    if conn is None: conn = get_conn()
    frag, params = _date_filter(date, end_date)
    ign_frag, ign_params = _ignored_fragment(conn)
    if client_ip:
        rows = conn.execute(f"""
            SELECT domain, COUNT(*) AS queries, MAX(client_name) AS client_name
            FROM queries
            WHERE {frag} AND category = ? AND client_ip = ?{ign_frag}
            GROUP BY domain
            ORDER BY queries DESC
            LIMIT ?
        """, params + [category, client_ip] + ign_params + [limit]).fetchall()
    else:
        rows = conn.execute(f"""
            SELECT domain, COUNT(*) AS queries, MAX(client_name) AS client_name
            FROM queries
            WHERE {frag} AND category = ?{ign_frag}
            GROUP BY domain
            ORDER BY queries DESC
            LIMIT ?
        """, params + [category] + ign_params + [limit]).fetchall()
    if close: conn.close()
    return [dict(r) for r in rows]


def client_category_usage(date: str, client_ip: str = None, conn=None) -> dict:
    """Get category usage for a specific client or all clients."""
    close = conn is None
    if conn is None: conn = get_conn()
    
    where_clause = "WHERE date = ?"
    params = [date]
    if client_ip:
        where_clause += " AND client_ip = ?"
        params.append(client_ip)
    
    rows = conn.execute(f"""
        SELECT category, COUNT(*) AS queries, COUNT(DISTINCT domain) AS domains
        FROM queries {where_clause}
        GROUP BY category
        ORDER BY queries DESC
    """, params).fetchall()
    
    if close: conn.close()
    return {row['category']: {'queries': row['queries'], 'domains': row['domains']} for row in rows}


def excessive_social_media_check(date: str, threshold_minutes: int = 60, conn=None) -> list:
    """Check for clients with excessive social media usage (> threshold minutes)."""
    close = conn is None
    if conn is None: conn = get_conn()
    
    # Convert threshold to approximate queries (rough estimate: 10-20 queries per minute)
    threshold_queries = threshold_minutes * 15  # Conservative estimate
    
    rows = conn.execute("""
        SELECT client_name, client_ip, category, COUNT(*) AS queries,
               COUNT(DISTINCT domain) AS domains
        FROM queries
        WHERE date = ? AND category IN ('social_media', 'streaming', 'gaming')
        GROUP BY client_ip, category
        HAVING queries > ?
        ORDER BY queries DESC
    """, (date, threshold_queries)).fetchall()
    
    if close: conn.close()
    return [dict(r) for r in rows]


def blocked_queries_summary(date: str, end_date: str = None, conn=None) -> dict:
    """Get summary of blocked vs allowed queries."""
    close = conn is None
    if conn is None: conn = get_conn()
    frag, params = _date_filter(date, end_date)
    row = conn.execute(f"""
        SELECT
            COUNT(*) AS total_queries,
            SUM(CASE WHEN status IN (1,4,5,6,7,8,9,10,11) THEN 1 ELSE 0 END) AS blocked_queries,
            COUNT(DISTINCT domain) AS unique_domains,
            COUNT(DISTINCT client_ip) AS active_clients
        FROM queries WHERE {frag}
    """, params).fetchone()

    if close: conn.close()
    return dict(row) if row else {}


# ── Device Deep-Dive ─────────────────────────────────────────────────────────

def device_summary(ip: str, date: str, end_date: str = None, conn=None) -> dict:
    """Total/blocked queries, unique domains, active hours, peak hour for one device."""
    close = conn is None
    if conn is None: conn = get_conn()
    frag, params = _date_filter(date, end_date)
    row = conn.execute(f"""
        SELECT
            COUNT(*)                                                     AS total_queries,
            SUM(CASE WHEN status IN (1,4,5,6,7,8,9,10,11) THEN 1 ELSE 0 END)        AS blocked_queries,
            COUNT(DISTINCT domain)                                       AS unique_domains,
            MAX(COALESCE(client_name, client_ip))                        AS client_name,
            MIN(timestamp)                                               AS first_seen,
            MAX(timestamp)                                               AS last_seen
        FROM queries
        WHERE {frag} AND client_ip = ?
    """, params + [ip]).fetchone()

    peak_row = conn.execute(f"""
        SELECT strftime('%H', timestamp, 'unixepoch', 'localtime') AS hr,
               COUNT(*) AS cnt
        FROM queries WHERE {frag} AND client_ip = ?
        GROUP BY hr ORDER BY cnt DESC LIMIT 1
    """, params + [ip]).fetchone()

    if close: conn.close()
    result = dict(row) if row else {}
    if peak_row:
        result['peak_hour'] = int(peak_row['hr'])
        result['peak_hour_queries'] = int(peak_row['cnt'])
    return result


def device_hourly_stats(ip: str, date: str, end_date: str = None, conn=None) -> list:
    """Queries per hour (0–23) for a device over a date or range."""
    close = conn is None
    if conn is None: conn = get_conn()
    frag, params = _date_filter(date, end_date)
    rows = conn.execute(f"""
        SELECT strftime('%H', timestamp, 'unixepoch', 'localtime') AS hour,
               COUNT(*) AS queries,
               SUM(CASE WHEN status IN (1,4,5,6,7,8,9,10,11) THEN 1 ELSE 0 END) AS blocked
        FROM queries
        WHERE {frag} AND client_ip = ?
        GROUP BY hour ORDER BY hour
    """, params + [ip]).fetchall()
    if close: conn.close()
    return [dict(r) for r in rows]


def device_hourly_by_category(ip: str, date: str, end_date: str = None, conn=None) -> list:
    """Queries per hour per category for a device — used to show when flagged activity happened."""
    close = conn is None
    if conn is None: conn = get_conn()
    frag, params = _date_filter(date, end_date)
    rows = conn.execute(f"""
        SELECT strftime('%H', timestamp, 'unixepoch', 'localtime') AS hour,
               category,
               COUNT(*) AS queries
        FROM queries
        WHERE {frag} AND client_ip = ?
        GROUP BY hour, category
        ORDER BY hour, queries DESC
    """, params + [ip]).fetchall()
    if close: conn.close()
    return [dict(r) for r in rows]


def device_domains_full(ip: str, date: str, end_date: str = None, limit: int = 200, conn=None) -> list:
    """All domains accessed by a device with category, count, blocked ratio, first/last seen."""
    close = conn is None
    if conn is None: conn = get_conn()
    frag, params = _date_filter(date, end_date)
    rows = conn.execute(f"""
        SELECT domain,
               MAX(category)  AS category,
               COUNT(*)       AS queries,
               SUM(CASE WHEN status IN (1,4,5,6,7,8,9,10,11) THEN 1 ELSE 0 END) AS blocked,
               MIN(strftime('%H:%M', timestamp, 'unixepoch', 'localtime')) AS first_seen_time,
               MAX(strftime('%H:%M', timestamp, 'unixepoch', 'localtime')) AS last_seen_time,
               COUNT(DISTINCT strftime('%H', timestamp, 'unixepoch', 'localtime')) AS active_hours
        FROM queries
        WHERE {frag} AND client_ip = ?
        GROUP BY domain
        ORDER BY queries DESC
        LIMIT ?
    """, params + [ip, limit]).fetchall()
    if close: conn.close()
    return [dict(r) for r in rows]


def device_flagged_category_detail(ip: str, date: str, category: str, end_date: str = None, conn=None) -> dict:
    """
    For a flagged category on a device: full hourly breakdown + all domains in that category.
    Returns {hourly: [...], domains: [...], total_queries, unique_domains}.
    """
    close = conn is None
    if conn is None: conn = get_conn()
    frag, params = _date_filter(date, end_date)

    hourly = conn.execute(f"""
        SELECT strftime('%H', timestamp, 'unixepoch', 'localtime') AS hour,
               COUNT(*) AS queries
        FROM queries
        WHERE {frag} AND client_ip = ? AND category = ?
        GROUP BY hour ORDER BY hour
    """, params + [ip, category]).fetchall()

    domains = conn.execute(f"""
        SELECT domain, COUNT(*) AS queries,
               MIN(strftime('%H:%M', timestamp, 'unixepoch', 'localtime')) AS first_seen_time,
               MAX(strftime('%H:%M', timestamp, 'unixepoch', 'localtime')) AS last_seen_time
        FROM queries
        WHERE {frag} AND client_ip = ? AND category = ?
        GROUP BY domain ORDER BY queries DESC
    """, params + [ip, category]).fetchall()

    total_row = conn.execute(f"""
        SELECT COUNT(*) AS total_queries, COUNT(DISTINCT domain) AS unique_domains
        FROM queries WHERE {frag} AND client_ip = ? AND category = ?
    """, params + [ip, category]).fetchone()

    if close: conn.close()
    return {
        'hourly':         [dict(r) for r in hourly],
        'domains':        [dict(r) for r in domains],
        'total_queries':  int(total_row['total_queries']) if total_row else 0,
        'unique_domains': int(total_row['unique_domains']) if total_row else 0,
    }


def top_blocked_domains(date: str, end_date: str = None, limit: int = 15, conn=None) -> list:
    """Top domains blocked by Pi-hole."""
    close = conn is None
    if conn is None: conn = get_conn()
    frag, params = _date_filter(date, end_date)
    rows = conn.execute(f"""
        SELECT domain, MAX(category) AS category,
               COUNT(*) AS blocked_count,
               COUNT(DISTINCT client_ip) AS device_count
        FROM queries
        WHERE {frag} AND status IN (1,4,5,6,7,8,9,10,11)
        GROUP BY domain
        ORDER BY blocked_count DESC
        LIMIT ?
    """, params + [limit]).fetchall()
    if close: conn.close()
    return [dict(r) for r in rows]


# ── Manual block list ─────────────────────────────────────────────────────────

def get_blocked_domains(conn=None) -> list:
    close = conn is None
    if conn is None: conn = get_conn()
    rows = conn.execute(
        "SELECT domain, category, blocked_at FROM manually_blocked ORDER BY blocked_at DESC"
    ).fetchall()
    if close: conn.close()
    return [dict(r) for r in rows]


def add_blocked_domain(domain: str, category: str = '', conn=None):
    close = conn is None
    if conn is None: conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO manually_blocked (domain, category, blocked_at) "
        "VALUES (?, ?, datetime('now'))",
        (domain.lower().strip(), category)
    )
    conn.commit()
    if close: conn.close()


def remove_blocked_domain(domain: str, conn=None):
    close = conn is None
    if conn is None: conn = get_conn()
    conn.execute("DELETE FROM manually_blocked WHERE domain = ?",
                 (domain.lower().strip(),))
    conn.commit()
    if close: conn.close()


# ── Ignored domains ───────────────────────────────────────────────────────────

def _ignored_fragment(conn) -> str:
    """Return a SQL fragment ' AND domain NOT IN (...)' for ignored domains.
    Returns empty string when the ignored list is empty."""
    rows = conn.execute("SELECT domain FROM ignored_domains").fetchall()
    if not rows:
        return "", []
    placeholders = ",".join("?" * len(rows))
    return f" AND domain NOT IN ({placeholders})", [r[0] for r in rows]


def get_ignored_domains(conn=None) -> list:
    close = conn is None
    if conn is None: conn = get_conn()
    rows = conn.execute(
        "SELECT domain, ignored_at FROM ignored_domains ORDER BY ignored_at DESC"
    ).fetchall()
    if close: conn.close()
    return [dict(r) for r in rows]


def add_ignored_domain(domain: str, conn=None):
    close = conn is None
    if conn is None: conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO ignored_domains (domain, ignored_at) VALUES (?, datetime('now'))",
        (domain.lower().strip(),)
    )
    conn.commit()
    if close: conn.close()


def remove_ignored_domain(domain: str, conn=None):
    close = conn is None
    if conn is None: conn = get_conn()
    conn.execute("DELETE FROM ignored_domains WHERE domain = ?",
                 (domain.lower().strip(),))
    conn.commit()
    if close: conn.close()


if __name__ == '__main__':
    today = datetime.now().strftime('%Y-%m-%d')
    print("=== Network Summary ===")
    print(network_summary(today))
    print("\n=== Client Usage ===")
    for c in client_usage(today):
        print(c)
    print("\n=== Category Breakdown ===")
    for c in category_breakdown(today):
        print(c)
