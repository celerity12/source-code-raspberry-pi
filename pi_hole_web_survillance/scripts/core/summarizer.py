#!/usr/bin/env python3
"""
Pi-hole Analytics - AI Summary using Google Gemini API

Queries the last 24 hours of DNS data and sends it to Gemini for:
  - Executive summary of network activity
  - Per-device breakdown of websites/apps used
  - Educational sites visited (per device)
  - Unusual or concerning activity flagged

Usage:
  python3 scripts/summarizer.py                    # print to stdout
  python3 scripts/summarizer.py --email            # send via email
  python3 scripts/summarizer.py --period weekly    # last 7 days
  python3 scripts/summarizer.py --period monthly   # last 30 days
"""

import argparse
import json
import logging
import smtplib
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests

from scripts.core.config import load_config
from scripts.core.constants import is_excluded_device

BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH  = BASE_DIR / "data" / "analytics.db"

from scripts.core.logging_setup import get_logger
log = get_logger(__name__, log_file=BASE_DIR / 'logs' / 'summarizer.log')

# ── Category labels ───────────────────────────────────────────────────────────
CATEGORY_LABELS = {
    'streaming':    'Streaming (Netflix/YouTube/etc)',
    'social_media': 'Social Media',
    'gaming':       'Gaming',
    'adult':        'Adult Content',
    'educational':  'Educational',
    'ads_tracking': 'Ads & Tracking',
    'tech':         'Tech & Development',
    'shopping':     'Shopping',
    'finance':      'Finance & Banking',
    'health':       'Health & Medical',
    'news':         'News & Media',
    'travel':       'Travel',
    'music':        'Music',
    'food':         'Food & Delivery',
    'productivity': 'Productivity & Work',
    'smart_home':   'Smart Home',
    'vpn_proxy':    'VPN / Proxy',
    'crypto':       'Crypto',
    'sports':       'Sports',
    'government':   'Government',
    'other':        'Other / Uncategorized',
}

ALERT_CATEGORIES = {'adult', 'vpn_proxy', 'crypto'}


# ── Data collection ───────────────────────────────────────────────────────────

def _period_dates(period: str):
    today = datetime.now().date()
    if period == 'daily':
        return str(today), str(today)
    elif period == 'weekly':
        return str(today - timedelta(days=6)), str(today)
    elif period == 'monthly':
        return str(today - timedelta(days=29)), str(today)
    return str(today), str(today)


def collect_data(period: str = 'daily', *,
                 start_ts: int = None, end_ts: int = None) -> dict:
    """Pull structured data from SQLite for the given period.

    When start_ts/end_ts (unix epoch) are provided, queries are filtered by
    the timestamp column (hour-precise) instead of the date column.
    This allows aligning the AI window with the dashboard's custom time range.
    """
    if start_ts and end_ts:
        # Hour-precise mode: filter on timestamp column
        ts_start_dt = datetime.fromtimestamp(start_ts)
        ts_end_dt   = datetime.fromtimestamp(end_ts)
        start_date  = ts_start_dt.strftime('%Y-%m-%d')
        end_date    = ts_end_dt.strftime('%Y-%m-%d')
        # Dates spanned for daily_summary (which aggregates by day)
        date_filter  = "date BETWEEN ? AND ?"
        date_params  = [start_date, end_date]
        # Precise filter for the raw queries table
        ts_filter    = "timestamp BETWEEN ? AND ?"
        ts_params    = [start_ts, end_ts]
        period_label = (f"{ts_start_dt.strftime('%b %d %H:%M')} – "
                        f"{ts_end_dt.strftime('%b %d %H:%M')}")
    else:
        start_date, end_date = _period_dates(period)
        date_filter  = "date BETWEEN ? AND ?" if start_date != end_date else "date = ?"
        date_params  = [start_date, end_date] if start_date != end_date else [start_date]
        ts_params    = date_params
        period_label = None
        start_ts     = None

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # ── Network totals ────────────────────────────────────────────────────────
    row = conn.execute(f"""
        SELECT SUM(total_queries) AS tq, SUM(blocked_queries) AS bq,
               SUM(unique_domains) AS ud, COUNT(DISTINCT client_ip) AS ac
        FROM daily_summary WHERE {date_filter}
    """, date_params).fetchone()
    totals = dict(row) if row else {}

    # ── Per-device summary ────────────────────────────────────────────────────
    devices_raw = conn.execute(f"""
        SELECT client_ip, MAX(client_name) AS client_name,
               SUM(total_queries) AS total_queries,
               SUM(blocked_queries) AS blocked_queries,
               SUM(unique_domains) AS unique_domains
        FROM daily_summary WHERE {date_filter}
        GROUP BY client_ip ORDER BY total_queries DESC
    """, date_params).fetchall()

    cfg     = load_config()
    devices = []
    for d in devices_raw:
        ip   = d['client_ip']
        name = d['client_name'] or ip

        if is_excluded_device(name, ip, cfg):
            continue

        # Skip very low-activity devices — not worth including in AI prompt
        if (d['total_queries'] or 0) < 50:
            continue

        # Top 3 categories only
        cats = conn.execute(f"""
            SELECT category, COUNT(*) AS queries
            FROM queries WHERE {date_filter} AND client_ip = ?
            GROUP BY category ORDER BY queries DESC LIMIT 3
        """, date_params + [ip]).fetchall()

        # Top 5 domains (non-ads/other)
        top_domains = conn.execute(f"""
            SELECT domain, COUNT(*) AS queries
            FROM queries
            WHERE {date_filter} AND client_ip = ?
              AND category NOT IN ('ads_tracking','other')
            GROUP BY domain ORDER BY queries DESC LIMIT 5
        """, date_params + [ip]).fetchall()

        # Alert categories only (high-value signal)
        alerts = conn.execute(f"""
            SELECT category, COUNT(*) AS queries
            FROM queries
            WHERE {date_filter} AND client_ip = ?
              AND category IN ('adult','vpn_proxy','crypto')
            GROUP BY category
        """, date_params + [ip]).fetchall()

        devices.append({
            'name':          name,
            'ip':            ip,
            'total_queries': d['total_queries'] or 0,
            'blocked':       d['blocked_queries'] or 0,
            'categories':    [f"{CATEGORY_LABELS.get(r['category'], r['category'])}:{r['queries']}"
                               for r in cats],
            'top_domains':   [r['domain'] for r in top_domains],
            'alerts':        [{'category': r['category'], 'queries': r['queries']}
                               for r in alerts],
        })

    # ── Top blocked domains network-wide ─────────────────────────────────────
    blocked_top = conn.execute(f"""
        SELECT domain, MAX(category) AS category, COUNT(*) AS cnt
        FROM queries
        WHERE {date_filter} AND status IN (1,4,5,6,7,8,9,10,11)
        GROUP BY domain ORDER BY cnt DESC LIMIT 15
    """, date_params).fetchall()

    # ── New domains (first seen in period) ────────────────────────────────────
    new_domains = conn.execute(f"""
        SELECT domain, category, COUNT(*) AS queries
        FROM queries
        WHERE {date_filter}
          AND domain NOT IN (SELECT DISTINCT domain FROM queries WHERE date < ?)
          AND category NOT IN ('ads_tracking','other')
        GROUP BY domain ORDER BY queries DESC LIMIT 20
    """, date_params + [start_date]).fetchall()

    conn.close()

    return {
        'period':      period,
        'start_date':  start_date,
        'end_date':    end_date,
        'totals':      totals,
        'devices':     devices,
        'blocked_top': [{'domain': r['domain'], 'category': r['category'],
                          'count': r['cnt']} for r in blocked_top],
        'new_domains': [{'domain': r['domain'], 'category': r['category'],
                          'queries': r['queries']} for r in new_domains],
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
    }


# ── Prompt builders ───────────────────────────────────────────────────────────

_BULLET_INSTRUCTION = (
    "Use ONLY bullet points (- item). Keep each bullet concise and actionable. "
    "Focus on key facts, concerns, and recommendations. Be specific but brief."
)

def _period_label(period: str) -> str:
    return {'daily': 'last 24 hours', 'weekly': 'last 7 days',
            'monthly': 'last 30 days'}.get(period, period)


def build_prompt(data: dict) -> str:
    """Single compact prompt — entire network summary in one API call."""
    pl = _period_label(data['period'])
    t  = data['totals']
    bp = round(t.get('bq', 0) / max(t.get('tq', 1), 1) * 100, 1)

    lines = [
        f"Home network DNS report ({pl}, {data['start_date']}).",
        f"Stats: {t.get('tq',0):,} queries, {bp}% blocked, {t.get('ac',0)} devices.",
        "",
        "Reply with ONLY these 3 sections (bullet points, be brief):",
        "## Key Highlights",
        "## Alerts & Concerns",
        "## Action Items",
        "",
    ]

    # Alerts first — highest signal
    alert_devs = [d for d in data['devices'] if d['alerts']]
    if alert_devs:
        lines.append("ALERTS:")
        for d in alert_devs:
            for a in d['alerts']:
                lines.append(f"  {d['name']}: {a['category'].upper()} {a['queries']}q")
        lines.append("")

    # Device summary — compact single line per device
    if data['devices']:
        lines.append("Devices (name: queries, top-categories, top-sites):")
        for d in data['devices']:
            cats  = ", ".join(d['categories'][:2])
            sites = ", ".join(d['top_domains'][:3])
            lines.append(f"  {d['name']}: {d['total_queries']}q | {cats} | {sites}")
        lines.append("")

    # Top blocked
    if data['blocked_top']:
        blocked = ", ".join(f"{b['domain']}({b['count']})" for b in data['blocked_top'][:5])
        lines.append(f"Top blocked: {blocked}")

    # New domains
    if data['new_domains']:
        new = ", ".join(n['domain'] for n in data['new_domains'][:5])
        lines.append(f"New domains: {new}")

    return "\n".join(lines)


# ── Gemini API call ───────────────────────────────────────────────────────────

class GeminiRateLimitError(Exception):
    """Raised when the Gemini API returns HTTP 429 Too Many Requests."""


def call_gemini(prompt: str, api_key: str, model: str = "gemini-2.0-flash") -> str:
    """Call Gemini API and return the response text.

    Raises GeminiRateLimitError on 429 so callers can fall back to cached data
    instead of blocking with long retries.
    """
    url = (f"https://generativelanguage.googleapis.com/v1/models/"
           f"{model}:generateContent?key={api_key}")

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature":     0.2,
            "maxOutputTokens": 600,
            "topP":            0.8,
        },
    }

    resp = requests.post(url, json=payload, timeout=60)
    if resp.status_code == 429:
        log.warning(f"Gemini rate-limited (429) for model '{model}'")
        raise GeminiRateLimitError(
            f"Gemini quota exceeded for model '{model}'. "
            f"gemini-1.5-flash allows 15 requests/minute on the free tier."
        )
    resp.raise_for_status()
    candidates = resp.json().get("candidates", [])
    if not candidates:
        raise ValueError("Gemini returned no candidates")
    return candidates[0]["content"]["parts"][0]["text"]


# ── HTML formatter ────────────────────────────────────────────────────────────

def _md_to_html(text: str) -> str:
    """Minimal markdown → HTML conversion for the email."""
    import re
    lines = text.split('\n')
    out = []
    for line in lines:
        line = line.rstrip()
        # Headers
        if line.startswith('### '):
            out.append(f'<h3 style="margin:16px 0 6px;color:#0969da">{line[4:]}</h3>')
        elif line.startswith('## '):
            out.append(f'<h2 style="margin:20px 0 8px;color:#1f2328;border-bottom:1px solid #d0d7de;padding-bottom:6px">{line[3:]}</h2>')
        elif line.startswith('# '):
            out.append(f'<h1 style="margin:0 0 16px;color:#1f2328">{line[2:]}</h1>')
        # Bold
        elif re.match(r'^\*\*(.+)\*\*$', line):
            out.append(f'<p style="font-weight:600;margin:6px 0">{line[2:-2]}</p>')
        # Bullets
        elif line.startswith('- ') or line.startswith('* '):
            out.append(f'<li style="margin:3px 0;font-size:13px">{line[2:]}</li>')
        # Alert lines
        elif '⚠️' in line or 'ALERT' in line:
            out.append(f'<p style="color:#b91c1c;font-weight:600;margin:4px 0;font-size:13px">{line}</p>')
        # Dividers
        elif line.startswith('═══') or line.startswith('───'):
            out.append('<hr style="border:none;border-top:1px solid #d0d7de;margin:12px 0">')
        # Empty lines
        elif line == '':
            out.append('<br>')
        else:
            # Inline bold
            line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
            out.append(f'<p style="margin:4px 0;font-size:13px">{line}</p>')
    return '\n'.join(out)


def build_email_html(summary_text: str, data: dict) -> str:
    period_label = {'daily': 'Daily AI Summary', 'weekly': 'Weekly AI Summary',
                    'monthly': 'Monthly AI Summary'}.get(data['period'], 'AI Summary')
    date_str = (data['end_date'] if data['start_date'] == data['end_date']
                else f"{data['start_date']} – {data['end_date']}")
    t = data['totals']
    bp = round(t.get('bq', 0) / max(t.get('tq', 1), 1) * 100, 1)

    body = _md_to_html(summary_text)

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
             background:#f6f8fa;padding:24px;color:#1f2328">
<div style="max-width:700px;margin:0 auto;background:#fff;border:1px solid #d0d7de;
            border-radius:12px;padding:32px 40px">

  <div style="background:linear-gradient(135deg,#0969da,#0550ae);border-radius:8px;
              padding:20px 24px;margin-bottom:24px;color:#fff">
    <h1 style="margin:0 0 4px;font-size:22px">🤖 {period_label}</h1>
    <p style="margin:0;font-size:13px;opacity:.85">
      {date_str} · Powered by Gemini AI · Generated {data['generated_at']}
    </p>
  </div>

  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:24px">
    <div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;
                padding:12px;text-align:center">
      <div style="font-size:20px;font-weight:700;color:#0369a1">{t.get('tq',0):,}</div>
      <div style="font-size:11px;color:#0369a1">Total Queries</div>
    </div>
    <div style="background:#fef3c7;border:1px solid #fcd34d;border-radius:8px;
                padding:12px;text-align:center">
      <div style="font-size:20px;font-weight:700;color:#854d0e">{bp}%</div>
      <div style="font-size:11px;color:#854d0e">Blocked</div>
    </div>
    <div style="background:#f0fdf4;border:1px solid #86efac;border-radius:8px;
                padding:12px;text-align:center">
      <div style="font-size:20px;font-weight:700;color:#15803d">{t.get('ac',0)}</div>
      <div style="font-size:11px;color:#15803d">Active Devices</div>
    </div>
  </div>

  <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;
              padding:20px 24px">
    {body}
  </div>

  <div style="margin-top:16px;font-size:11px;color:#656d76;text-align:center">
    Pi-hole Analytics · AI Summary · All data stays on your Pi
  </div>
</div>
</body></html>"""


# ── Email sender ──────────────────────────────────────────────────────────────

def send_email(html: str, subject: str, cfg: dict):
    ec   = cfg['email']
    msg  = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = ec['sender_email']
    msg['To']      = ', '.join(ec['recipient_emails'])
    msg.attach(MIMEText(html, 'html'))

    with smtplib.SMTP(ec['smtp_server'], ec['smtp_port']) as s:
        s.starttls()
        s.login(ec['sender_email'], ec['sender_password'])
        s.sendmail(ec['sender_email'], ec['recipient_emails'], msg.as_string())
    log.info(f"AI summary email sent to {ec['recipient_emails']}")


# ── DB persistence ───────────────────────────────────────────────────────────

def store_summary(period: str, start_date: str, end_date: str,
                  summary_text: str, model: str,
                  run_type: str = 'ondemand') -> None:
    """Persist an AI summary to the database.

    Keeps exactly ONE row per (period, run_type) — the newest replaces the old.
    This gives us two permanent slots:
      • run_type='scheduled'  → the 5 AM cron result
      • run_type='ondemand'   → the last manual Generate click
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("""
            INSERT INTO ai_summaries (period, run_type, start_date, end_date, summary_text, model)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (period, run_type, start_date, end_date, summary_text, model))
        # Keep only the most recent row per (period, run_type)
        conn.execute("""
            DELETE FROM ai_summaries
            WHERE period = ? AND run_type = ?
              AND id NOT IN (
                  SELECT id FROM ai_summaries
                  WHERE period = ? AND run_type = ?
                  ORDER BY generated_at DESC
                  LIMIT 1
              )
        """, (period, run_type, period, run_type))
        conn.commit()
        log.info(f"AI summary stored period={period} run_type={run_type} end_date={end_date}")
    finally:
        conn.close()


def get_latest_summary(period: str = 'daily') -> dict | None:
    """Return the best available stored summary for the given period.

    Priority: scheduled (5 AM cron) → ondemand (last manual run) → None.
    """
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        # Prefer scheduled; fall back to ondemand
        row = conn.execute("""
            SELECT period, run_type, start_date, end_date, summary_text, model, generated_at
            FROM ai_summaries
            WHERE period = ?
            ORDER BY CASE run_type WHEN 'scheduled' THEN 0 ELSE 1 END,
                     generated_at DESC
            LIMIT 1
        """, (period,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Gemini AI network summary')
    parser.add_argument('--period', choices=['daily', 'weekly', 'monthly'],
                        default='daily')
    parser.add_argument('--email', action='store_true',
                        help='Send result via email instead of printing')
    parser.add_argument('--model', default='gemini-2.0-flash',
                        help='Gemini model to use (default: gemini-2.0-flash)')
    args = parser.parse_args()

    cfg = load_config()
    api_key = cfg.get('gemini', {}).get('api_key', '')
    if not api_key:
        log.error("No Gemini API key found. Add to config.yaml:\n  gemini:\n    api_key: YOUR_KEY")
        sys.exit(1)

    # For scheduled daily runs, use last 24 hours ending at 5 AM
    start_ts = None
    end_ts = None
    if args.period == 'daily':
        now = datetime.now()
        # Check if current hour is 5 (scheduled run)
        if now.hour == 5:
            end_ts = int(now.replace(hour=5, minute=0, second=0, microsecond=0).timestamp())
            start_ts = end_ts - (24 * 60 * 60)  # 24 hours ago
            log.info(f"Scheduled run detected - using last 24h: {datetime.fromtimestamp(start_ts)} to {datetime.fromtimestamp(end_ts)}")

    log.info(f"Collecting {args.period} data...")
    data = collect_data(args.period, start_ts=start_ts, end_ts=end_ts)
    model = cfg.get('gemini', {}).get('model', args.model)

    log.info("Generating summary: single API call")
    summary = call_gemini(build_prompt(data), api_key, model)

    # Persist as 'scheduled' — this is the authoritative 5 AM cron copy
    store_summary(args.period, data['start_date'], data['end_date'], summary, model,
                  run_type='scheduled')

    if args.email:
        period_label = {'daily': 'Daily', 'weekly': 'Weekly',
                        'monthly': 'Monthly'}.get(args.period, '')
        subject = (f"{cfg['email'].get('subject_prefix','[Pi-hole]')} "
                   f"{period_label} AI Network Summary — {data['end_date']}")
        html = build_email_html(summary, data)
        send_email(html, subject, cfg)
        log.info("Done.")
    else:
        print("\n" + "═" * 60)
        print(f"  AI NETWORK SUMMARY — {args.period.upper()}")
        print("═" * 60 + "\n")
        print(summary)
        print("\n" + "═" * 60)


if __name__ == '__main__':
    main()
