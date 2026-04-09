#!/usr/bin/env python3
"""
Pi-hole Analytics - Health Monitor
Collects system, app, Pi-hole, and database health metrics.
Used by the email reporter and dashboard.
"""

import os
import shutil
import sqlite3
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote
import sys

from scripts.core.config import load_config

BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH  = BASE_DIR / "data" / "analytics.db"
LOG_DIR  = BASE_DIR / "logs"


# ── Formatting helpers ────────────────────────────────────────────────────────

def _human_bytes(n: int) -> str:
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _ago(secs: int) -> str:
    if secs < 60:
        return f"{secs}s ago"
    if secs < 3600:
        return f"{secs // 60}m ago"
    h, m = divmod(secs, 3600)
    return f"{h}h {m // 60}m ago"


# ── System resources ──────────────────────────────────────────────────────────

def system_health() -> dict:
    """Disk usage, RAM, CPU load, uptime, CPU temperature."""
    r = {}

    # ── Disk (partition containing the install dir) ──
    try:
        du = shutil.disk_usage(str(BASE_DIR))
        r['disk_total']   = du.total
        r['disk_used']    = du.used
        r['disk_free']    = du.free
        r['disk_pct']     = round(du.used / du.total * 100, 1)
        r['disk_total_h'] = _human_bytes(du.total)
        r['disk_used_h']  = _human_bytes(du.used)
        r['disk_free_h']  = _human_bytes(du.free)
    except Exception:
        r.update(disk_total=0, disk_used=0, disk_free=0, disk_pct=0,
                 disk_total_h='—', disk_used_h='—', disk_free_h='—')

    # ── RAM (/proc/meminfo) ──
    try:
        mem = {}
        with open('/proc/meminfo') as f:
            for line in f:
                k, v = line.split(':')
                mem[k.strip()] = int(v.split()[0]) * 1024  # kB → bytes
        total = mem.get('MemTotal', 0)
        avail = mem.get('MemAvailable', 0)
        used  = total - avail
        r['mem_total']   = total
        r['mem_used']    = used
        r['mem_free']    = avail
        r['mem_pct']     = round(used / total * 100, 1) if total else 0
        r['mem_total_h'] = _human_bytes(total)
        r['mem_used_h']  = _human_bytes(used)
        r['mem_free_h']  = _human_bytes(avail)
    except Exception:
        r.update(mem_total=0, mem_used=0, mem_free=0, mem_pct=0,
                 mem_total_h='—', mem_used_h='—', mem_free_h='—')

    # ── CPU load average ──
    try:
        l1, l5, l15 = os.getloadavg()
        ncpu = os.cpu_count() or 1
        r['cpu_load1']  = round(l1, 2)
        r['cpu_load5']  = round(l5, 2)
        r['cpu_load15'] = round(l15, 2)
        r['cpu_count']  = ncpu
        r['cpu_load_pct'] = round((l1 / ncpu) * 100, 1)
    except Exception:
        r.update(cpu_load1=0, cpu_load5=0, cpu_load15=0, cpu_count=1, cpu_load_pct=0)

    # ── Uptime ──
    try:
        with open('/proc/uptime') as f:
            secs = int(float(f.read().split()[0]))
        r['uptime_seconds'] = secs
        d, rem = divmod(secs, 86400)
        h, rem = divmod(rem, 3600)
        m = rem // 60
        r['uptime_str'] = (f"{d}d {h}h {m}m" if d
                           else f"{h}h {m}m" if h
                           else f"{m}m")
    except Exception:
        r.update(uptime_seconds=0, uptime_str='unknown')

    # ── CPU temperature (Raspberry Pi / Linux) ──
    try:
        tp = Path('/sys/class/thermal/thermal_zone0/temp')
        r['cpu_temp_c'] = round(int(tp.read_text().strip()) / 1000, 1) if tp.exists() else None
    except Exception:
        r['cpu_temp_c'] = None

    return r


# ── Analytics database ────────────────────────────────────────────────────────

def db_health() -> dict:
    """DB file size, record counts, last fetch time, data-gap detection."""
    r = {
        'db_size': 0, 'db_size_h': '—',
        'total_queries': 0, 'total_days': 0,
        'today_queries': 0,
        'last_fetch_time': None, 'last_fetch_ago': None,
        'data_gaps': [],
        'log_sizes': {}, 'logs_total_h': '—',
    }

    # ── DB file ──
    try:
        sz = DB_PATH.stat().st_size if DB_PATH.exists() else 0
        r['db_size']   = sz
        r['db_size_h'] = _human_bytes(sz)
    except Exception:
        pass

    # ── Log files ──
    try:
        log_sizes = {f.name: f.stat().st_size for f in sorted(LOG_DIR.glob('*.log'))}
        r['log_sizes']    = {k: _human_bytes(v) for k, v in log_sizes.items()}
        r['logs_total_h'] = _human_bytes(sum(log_sizes.values()))
    except Exception:
        pass

    # ── DB queries ──
    if not DB_PATH.exists():
        return r
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        row = conn.execute("SELECT COUNT(*) AS n FROM queries").fetchone()
        r['total_queries'] = int(row['n']) if row else 0

        row = conn.execute("SELECT COUNT(DISTINCT date) AS n FROM daily_summary").fetchone()
        r['total_days'] = int(row['n']) if row else 0

        today = datetime.now().strftime('%Y-%m-%d')
        row = conn.execute("SELECT COUNT(*) AS n FROM queries WHERE date=?", (today,)).fetchone()
        r['today_queries'] = int(row['n']) if row else 0

        # Last fetch timestamp
        row = conn.execute(
            "SELECT value FROM fetch_state WHERE key='last_timestamp'"
        ).fetchone()
        if row:
            ts = int(row['value'])
            last_dt = datetime.fromtimestamp(ts)
            r['last_fetch_time'] = last_dt.strftime('%Y-%m-%d %H:%M')
            ago = int((datetime.now() - last_dt).total_seconds())
            r['last_fetch_ago'] = _ago(ago)
            r['last_fetch_stale'] = ago > 1800  # >30 min is stale

        # Data gaps over past 7 days (days with no data at all)
        gaps = []
        for i in range(1, 8):
            d = (datetime.now().date() - timedelta(days=i)).strftime('%Y-%m-%d')
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM daily_summary WHERE date=?", (d,)
            ).fetchone()
            if not row or int(row['n']) == 0:
                gaps.append(d)
        r['data_gaps'] = gaps

        conn.close()
    except Exception as e:
        r['db_error'] = str(e)

    return r


# ── Systemd services ──────────────────────────────────────────────────────────

def service_health() -> list:
    """Active state + last trigger for each pihole-analytics systemd unit."""
    units = [
        ('pihole-analytics-fetch.timer',      'Data Fetcher',      '15-min'),
        ('pihole-analytics-daily.timer',      'Daily Report',      '7 PM daily'),
        ('pihole-analytics-weekly.timer',     'Weekly Report',     'Sat/Sun 7 PM'),
        ('pihole-analytics-monthly.timer',    'Monthly Report',    '30th 7 PM'),
        ('pihole-analytics-download.timer',   'Rules Updater',     'Weekly Sun 3 AM'),
        ('pihole-analytics-sysupdate.timer',  'System Updates',    'Weekly Sun 4 AM'),
        ('pihole-analytics-fetch.service',    'Fetch Service',     'oneshot'),
    ]
    results = []
    for unit, label, schedule in units:
        info = {
            'unit': unit, 'label': label, 'schedule': schedule,
            'active': 'unknown', 'sub': '', 'since': None, 'last_trigger': None,
        }
        try:
            out = subprocess.run(
                ['systemctl', 'show', unit,
                 '--property=ActiveState,SubState,ActiveEnterTimestamp,LastTriggerUSec,Result'],
                capture_output=True, text=True, timeout=5
            ).stdout
            props = {}
            for line in out.strip().splitlines():
                if '=' in line:
                    k, v = line.split('=', 1)
                    props[k] = v

            info['active'] = props.get('ActiveState', 'unknown')
            info['sub']    = props.get('SubState', '')
            info['result'] = props.get('Result', '')

            ts_raw = props.get('LastTriggerUSec', '0')
            if ts_raw not in ('0', 'n/a', ''):
                try:
                    ts_us = int(ts_raw)
                    if ts_us > 0:
                        info['last_trigger'] = datetime.fromtimestamp(
                            ts_us / 1_000_000
                        ).strftime('%Y-%m-%d %H:%M')
                except ValueError:
                    pass

            since_raw = props.get('ActiveEnterTimestamp', '')
            if since_raw and since_raw not in ('n/a', ''):
                info['since'] = since_raw

        except FileNotFoundError:
            info['active'] = 'no systemd'   # running outside systemd (dev env)
        except Exception:
            pass
        results.append(info)
    return results


# ── Pi-hole API health ────────────────────────────────────────────────────────

def pihole_health(cfg: dict) -> dict:
    """Blocking status, gravity size, version, upstream DNS."""
    r = {
        'reachable': False,
        'blocking': None,
        'gravity_count': None,
        'gravity_count_h': None,
        'version': None,
        'upstream_dns': None,
        'ftl_running': None,
        'error': None,
    }
    try:
        import requests as req

        host     = cfg['pihole']['host']
        token    = cfg['pihole'].get('api_token', '')
        password = cfg['pihole'].get('password', '')

        # ── Try v6 API ──
        for cred in filter(None, [password, token]):
            try:
                ar = req.post(f"{host}/api/auth",
                              json={"password": cred}, timeout=8)
                if ar.status_code != 200:
                    continue
                sid = ar.json().get("session", {}).get("sid", "")
                if not sid:
                    continue

                hdrs    = {"X-FTL-SID": sid}
                r['reachable'] = True

                # Blocking status (v6: /api/dns/blocking)
                br = req.get(f"{host}/api/dns/blocking", headers=hdrs, timeout=8)
                if br.ok:
                    bd = br.json()
                    blocking_raw = bd.get('blocking')
                    r['blocking'] = (blocking_raw is True
                                     or str(blocking_raw).lower() in ('enabled', 'true'))

                # Summary (gravity count)
                sr = req.get(f"{host}/api/stats/summary",
                             headers=hdrs, timeout=8)
                if sr.ok:
                    sd = sr.json()
                    gc = (sd.get('gravity', {}) or {}).get('domains_being_blocked') \
                         or sd.get('domains_being_blocked')
                    r['gravity_count']   = int(gc) if gc else None
                    r['gravity_count_h'] = f"{int(gc):,}" if gc else None
                    # fallback: some v6 builds include blocking in summary too
                    if r['blocking'] is None:
                        blocking_raw = sd.get('blocking')
                        r['blocking'] = (blocking_raw is True
                                         or str(blocking_raw).lower() in ('enabled', 'true'))

                # Version
                vr = req.get(f"{host}/api/info/version",
                             headers=hdrs, timeout=8)
                if vr.ok:
                    vd = vr.json()
                    r['version'] = (
                        (vd.get('version') or {}).get('core', {})
                        .get('local', {}).get('version')
                        or vd.get('version')
                    )

                # FTL info
                ir = req.get(f"{host}/api/info/ftl",
                             headers=hdrs, timeout=8)
                r['ftl_running'] = ir.ok

                # DNS upstreams
                dr = req.get(f"{host}/api/config/dns",
                             headers=hdrs, timeout=8)
                if dr.ok:
                    ups = (dr.json().get('config', {}) or {}) \
                              .get('dns', {}).get('upstreams', [])
                    r['upstream_dns'] = ', '.join(ups[:3]) if ups else None

                # Logout
                req.post(f"{host}/api/auth",
                         headers=hdrs, json={}, timeout=5)
                return r

            except Exception:
                continue

        # ── v5 fallback ──
        try:
            api_path = cfg['pihole'].get('api_path', '/admin/api.php')
            base     = host + api_path
            resp     = req.get(
                f"{base}?summary&auth={quote(token, safe='')}",
                timeout=8
            )
            if resp.ok:
                sd = resp.json()
                r['reachable']       = True
                r['blocking']        = sd.get('status') == 'enabled'
                gc = sd.get('domains_being_blocked')
                r['gravity_count']   = int(gc) if gc else None
                r['gravity_count_h'] = f"{int(gc):,}" if gc else None
        except Exception:
            pass

    except Exception as e:
        r['error'] = str(e)

    return r


# ── Recent errors from log files ──────────────────────────────────────────────

def recent_errors(lines: int = 50) -> list:
    """Return the last N ERROR/WARNING lines across all log files."""
    errors = []
    for lf in sorted(LOG_DIR.glob('*.log')):
        try:
            text = lf.read_text(errors='replace')
            for line in text.splitlines()[-lines:]:
                if '[ERROR]' in line or '[WARNING]' in line or 'ERROR' in line.upper():
                    errors.append({'file': lf.name, 'line': line.strip()})
        except Exception:
            pass
    # Return last 10 unique errors
    seen = set()
    unique = []
    for e in reversed(errors):
        key = e['line'][:100]
        if key not in seen:
            seen.add(key)
            unique.append(e)
        if len(unique) >= 10:
            break
    return list(reversed(unique))


# ── Public entry point ────────────────────────────────────────────────────────

def collect_all(cfg: dict = None) -> dict:
    """Collect all health metrics. Safe — never raises."""
    if cfg is None:
        try:
            cfg = load_config()
        except Exception:
            cfg = {}
    try:
        sys_h  = system_health()
    except Exception as e:
        sys_h  = {'error': str(e)}
    try:
        db_h   = db_health()
    except Exception as e:
        db_h   = {'error': str(e)}
    try:
        svc_h  = service_health()
    except Exception as e:
        svc_h  = []
    try:
        ph_h   = pihole_health(cfg)
    except Exception as e:
        ph_h   = {'reachable': False, 'error': str(e)}
    try:
        errors = recent_errors()
    except Exception:
        errors = []

    return {
        'system':       sys_h,
        'db':           db_h,
        'services':     svc_h,
        'pihole':       ph_h,
        'recent_errors': errors,
        'collected_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
