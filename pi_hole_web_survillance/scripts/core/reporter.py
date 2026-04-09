#!/usr/bin/env python3
"""
Pi-hole Analytics - Email Report Generator
White background, mobile-friendly, mirrors dashboard layout:
  stat cards → plain-English summary → alert banner → risky category cards →
  device cards → per-client hourly SVG chart → category table →
  Pi-hole protection → new domains → 7-day trend (weekly/monthly)
"""

import smtplib
import logging
import math
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from pathlib import Path

from scripts.data import analytics as A
from scripts.core import health as H
from scripts.core.config    import load_config
from scripts.core.constants import (
    CATEGORY_ICONS, CATEGORY_COLORS, DEFAULT_COLOR, DEFAULT_ICON,
    ALERT_CATEGORIES, WATCH_CATEGORIES, is_excluded_device,
)

BASE_DIR = Path(__file__).resolve().parents[2]

from scripts.core.logging_setup import get_logger
log = get_logger(__name__, log_file=BASE_DIR / 'logs' / 'reporter.log')


# Exclusion list now lives in config.yaml `excluded_devices`.
# is_excluded_device() imported from constants handles both config-driven and fallback logic.

# ── CSS ───────────────────────────────────────────────────────────────────────
CSS = """
<style>
  /* ── Reset / base ──────────────────────────────────────────────────── */
  * { box-sizing:border-box; margin:0; padding:0; }
  body { font-family:'Segoe UI',Arial,sans-serif; background:#f6f8fa; color:#1f2328;
         line-height:1.6; padding:12px; font-size:15px; }
  a    { color:#0969da; text-decoration:none; }
  a:hover { text-decoration:underline; }

  /* ── Wrapper ────────────────────────────────────────────────────────── */
  .wrap  { max-width:720px; margin:0 auto; }

  /* ── Header ─────────────────────────────────────────────────────────── */
  .hdr   { background:linear-gradient(135deg,#0969da,#0550ae); color:#fff;
           padding:20px 18px; border-radius:10px 10px 0 0; }
  .hdr h1{ margin:0 0 4px; font-size:22px; }
  .hdr p { margin:0; opacity:.85; font-size:14px; }

  /* ── Alert banner ───────────────────────────────────────────────────── */
  .alert-banner { background:#fff0f0; border:1px solid #fca5a5;
                  border-left:4px solid #cf222e; border-radius:0 0 0 0;
                  padding:12px 16px; margin-bottom:0; }
  .alert-banner h3 { color:#b91c1c; font-size:15px; margin-bottom:6px; }
  .alert-banner ul { padding-left:18px; font-size:14px; color:#7f1d1d; }
  .alert-banner li { margin-bottom:3px; }

  /* ── Cards ──────────────────────────────────────────────────────────── */
  .card  { background:#fff; border:1px solid #d0d7de; border-radius:8px;
           padding:16px; margin-bottom:12px;
           box-shadow:0 1px 3px rgba(0,0,0,.06); }
  .card h2 { font-size:16px; color:#0969da; border-bottom:1px solid #e8ecf0;
             padding-bottom:6px; margin-bottom:12px; }
  .card p  { font-size:14px; color:#3d444d; margin:6px 0; }

  /* ── Stat grid ──────────────────────────────────────────────────────── */
  .stat-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:8px; margin-bottom:12px; }
  .sbox      { background:#f6f8fa; border:1px solid #d0d7de; border-radius:6px;
               padding:10px 6px; text-align:center; }
  .sbox .num { font-size:22px; font-weight:700; color:#0969da; }
  .sbox .lbl { font-size:12px; color:#1f2328; margin-top:3px;
               text-transform:uppercase; letter-spacing:.4px; font-weight:500; }
  .sbox .chg { font-size:12px; margin-top:3px; }

  /* ── Summary box ────────────────────────────────────────────────────── */
  .summary-box { background:#f0f7ff; border:1px solid #c9dff7;
                 border-left:3px solid #0969da; border-radius:8px;
                 padding:14px 16px; margin-bottom:12px; font-size:14px; color:#1f2328; }
  .summary-box strong { color:#0550ae; }

  /* ── Risky category grid ────────────────────────────────────────────── */
  .rc-grid { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:12px; }
  .rc-card { border-radius:8px; padding:12px; }
  .rc-card.alert-card { background:#fff5f5; border:1px solid #fca5a5; }
  .rc-card.warn-card  { background:#fffbeb; border:1px solid #fde68a; }
  .rc-card.info-card  { background:#f0f7ff; border:1px solid #93c5fd; }
  .rc-card.clean-card { background:#f8fff8; border:1px solid #86efac; }
  .rc-top  { display:flex; justify-content:space-between; align-items:flex-start;
             margin-bottom:6px; }
  .rc-icon { font-size:24px; line-height:1; }
  .rc-title{ font-size:14px; font-weight:600; color:#1f2328; margin-top:2px; }
  .rc-bdg  { font-size:11px; padding:2px 7px; border-radius:8px; font-weight:600;
             white-space:nowrap; }
  .bdg-alert{ background:#fee2e2; color:#b91c1c; border:1px solid #fca5a5; }
  .bdg-warn { background:#fef3c7; color:#92400e; border:1px solid #fcd34d; }
  .bdg-info { background:#dbeafe; color:#1d4ed8; border:1px solid #93c5fd; }
  .bdg-clean{ background:#dcfce7; color:#15803d; border:1px solid #86efac; }
  .rc-count { font-size:18px; font-weight:700; margin-bottom:4px; }
  .alert-card .rc-count { color:#b91c1c; }
  .warn-card  .rc-count { color:#92400e; }
  .info-card  .rc-count { color:#1d4ed8; }
  .clean-card .rc-count { color:#15803d; }
  .rc-desc  { font-size:12px; color:#3d444d; margin-bottom:6px; line-height:1.5; }
  .rc-devs  { font-size:13px; color:#1f2328; margin-bottom:6px; }
  .rc-sites { font-size:12px; }
  .rc-site  { padding:3px 0; border-bottom:1px solid #e8ecf0; }
  .rc-site:last-child { border-bottom:none; }
  .rc-site a{ color:#0969da; font-family:monospace; font-size:12px; }
  .rc-cnt   { color:#3d444d; }

  /* ── Device cards ───────────────────────────────────────────────────── */
  .dev-grid { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:12px; }
  .dev-card { background:#fff; border:1px solid #d0d7de; border-radius:8px; padding:12px; }
  .dev-card.flagged { border-left:3px solid #cf222e; }
  .dev-hdr  { display:flex; align-items:center; gap:10px; margin-bottom:8px; }
  .dev-avi  { width:36px; height:36px; border-radius:50%;
              background:linear-gradient(135deg,#0969da,#8250df);
              display:flex; align-items:center; justify-content:center;
              font-size:16px; flex-shrink:0; color:#fff; }
  .dev-name { font-size:14px; font-weight:600; color:#1f2328; }
  .dev-type { font-size:12px; color:#0969da; font-weight:500; }
  .dev-ip   { font-size:12px; color:#3d444d; font-family:monospace; }
  .dev-mac  { font-size:12px; color:#3d444d; font-family:monospace; }
  .dev-stats{ display:flex; gap:12px; margin-bottom:8px; }
  .dev-stat .v { font-size:17px; font-weight:700; color:#0969da; }
  .dev-stat .l { font-size:11px; color:#3d444d; text-transform:uppercase; }
  .dev-bar-bg{ background:#e8ecf0; border-radius:3px; height:4px; margin-bottom:8px; }
  .dev-bar-fg{ height:4px; border-radius:3px;
               background:linear-gradient(90deg,#0969da,#8250df); }
  .dev-cats { display:flex; flex-wrap:wrap; gap:3px; margin-bottom:6px; }
  .cat-pill { display:inline-block; padding:2px 7px; border-radius:10px;
              font-size:10px; font-weight:500; }
  .dev-flags{ margin-top:6px; }
  .dev-flag { border-radius:5px; padding:7px 9px; margin-bottom:5px; }
  .dev-flag.alert-flag{ background:#fff5f5; border:1px solid #fca5a5; }
  .dev-flag.warn-flag { background:#fffbeb; border:1px solid #fde68a; }
  .flag-ttl { font-size:12px; font-weight:600; margin-bottom:4px; }
  .alert-flag .flag-ttl { color:#b91c1c; }
  .warn-flag  .flag-ttl { color:#92400e; }
  .flag-sites { font-size:12px; }
  .flag-sites a { color:#0969da; font-family:monospace; }

  /* ── Tables ─────────────────────────────────────────────────────────── */
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th    { background:#f6f8fa; color:#1f2328; text-transform:uppercase; font-size:12px;
          letter-spacing:.4px; padding:8px 8px; text-align:left;
          border-bottom:1px solid #d0d7de; font-weight:600; }
  td    { padding:8px 8px; border-bottom:1px solid #e8ecf0; color:#1f2328;
          vertical-align:middle; font-size:13px; }
  tr:last-child td { border-bottom:none; }
  .mono { font-family:monospace; font-size:12px; }

  /* ── Badge / bar ────────────────────────────────────────────────────── */
  .badge    { display:inline-block; padding:2px 7px; border-radius:8px;
              font-size:10px; color:#fff; }
  .bar-wrap { background:#e8ecf0; border-radius:3px; height:6px; width:80px;
              display:inline-block; vertical-align:middle; }
  .bar-fill { height:6px; border-radius:3px; }
  .s-alert  { background:#fee2e2; color:#b91c1c; border:1px solid #fca5a5;
              border-radius:6px; padding:2px 7px; font-size:10px; font-weight:600; }
  .s-warn   { background:#fef3c7; color:#92400e; border:1px solid #fcd34d;
              border-radius:6px; padding:2px 7px; font-size:10px; font-weight:600; }
  .s-ok     { background:#dcfce7; color:#15803d; border:1px solid #86efac;
              border-radius:6px; padding:2px 7px; font-size:10px; font-weight:600; }

  /* ── Protection box ─────────────────────────────────────────────────── */
  .prot-box { background:#f0fff4; border:1px solid #86efac; border-radius:8px;
              padding:14px; margin-bottom:12px; }
  .prot-box h2 { color:#15803d; }
  .prot-grid{ display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-bottom:10px; }
  .pbox     { background:#fff; border:1px solid #c3e6cb; border-radius:6px;
              padding:8px; text-align:center; }
  .pbox .pv { font-size:20px; font-weight:700; color:#15803d; }
  .pbox .pl { font-size:11px; color:#3d444d; margin-top:3px; text-transform:uppercase; }

  /* ── Footer ─────────────────────────────────────────────────────────── */
  .footer { text-align:center; color:#3d444d; font-size:12px; padding:14px; }
  .footer a { color:#0969da; }

  /* ── Arrows ─────────────────────────────────────────────────────────── */
  .up   { color:#cf222e; }
  .down { color:#1a7f37; }
  .same { color:#3d444d; }

  /* ── Mobile ─────────────────────────────────────────────────────────── */
  @media(max-width:500px){
    .stat-grid { grid-template-columns:repeat(2,1fr); }
    .rc-grid   { grid-template-columns:1fr; }
    .dev-grid  { grid-template-columns:1fr; }
    .prot-grid { grid-template-columns:repeat(2,1fr); }
    .bar-wrap  { width:50px; }
    .hdr h1    { font-size:17px; }
  }
  @media(min-width:501px){
    body { padding:20px; }
    .hdr { padding:24px 24px; }
    .card { padding:18px 20px; }
    .sbox .num { font-size:24px; }
    table { font-size:13px; }
    th, td { padding:8px 10px; }
  }
</style>
"""


# ── Small helpers ──────────────────────────────────────────────────────────────

def pct_change(now, prev):
    if not prev:
        return None
    return round(((now - prev) / prev) * 100, 1)


def arrow(val):
    if val is None: return ''
    if val > 0:  return f'<span style="color:#e74c3c">▲ {abs(val):.1f}%</span>'
    if val < 0:  return f'<span style="color:#27ae60">▼ {abs(val):.1f}%</span>'
    return '<span style="color:#3d444d">—</span>'


def stat_box(value: int, label: str, change: float = None) -> str:
    """Render a single stat card for email reports."""
    chg_html = ''
    if change is not None:
        chg_html = f'<div class="chg">{arrow(change)}</div>'
    return (
        f'<div class="stat-box">'
        f'<div class="stat-val">{value:,}</div>'
        f'<div class="stat-lbl">{label}</div>'
        f'{chg_html}'
        f'</div>'
    )


def cat_badge(cat):
    color = CATEGORY_COLORS.get(cat, DEFAULT_COLOR)
    icon  = CATEGORY_ICONS.get(cat, DEFAULT_ICON)
    return (f'<span class="badge" style="background:{color}">'
            f'{icon} {cat.replace("_"," ").title()}</span>')


def cat_pill(cat, pct_val):
    color = CATEGORY_COLORS.get(cat, DEFAULT_COLOR)
    icon  = CATEGORY_ICONS.get(cat, DEFAULT_ICON)
    return (f'<span class="cat-pill" style="background:{color}22;color:{color};'
            f'border:1px solid {color}44">{icon} {cat.replace("_"," ")} {pct_val}%</span>')


def mini_bar(value, max_val, color='#0969da'):
    p = min(100, int((value / max_val) * 100)) if max_val else 0
    return (f'<span class="bar-wrap"><span class="bar-fill" '
            f'style="width:{p}%;background:{color}"></span></span>')


def _skip_device(name, ip, cfg=None):
    return is_excluded_device(name, ip, cfg)


DEVICE_ICONS = ['💻', '📱', '🖥️', '🎮', '📺', '🏠', '⌚', '🖨️']


# ── SVG time-series chart ─────────────────────────────────────────────────────

def build_hourly_svg(hourly_data: dict, top_n: int = 5, cfg: dict = None) -> str:
    """
    Build an inline SVG bar+line chart showing queries per hour for the top N clients.
    hourly_data: {client_ip: {'name': str, 'hours': [{'hour': '09', 'queries': 42}, ...]}}
    """
    if not hourly_data:
        return '<p style="color:#3d444d;font-size:12px">No hourly data available.</p>'

    # Sort clients by total queries, take top N, skip infrastructure
    totals = {
        ip: sum(h['queries'] for h in v['hours'])
        for ip, v in hourly_data.items()
        if not _skip_device(v.get('name', ''), ip, cfg)
    }
    top_ips = sorted(totals, key=lambda x: totals[x], reverse=True)[:top_n]
    if not top_ips:
        return '<p style="color:#3d444d;font-size:12px">No personal device data available.</p>'

    # Build hour → {ip: queries} map
    hours = [str(h).zfill(2) for h in range(24)]
    data = {}
    for ip in top_ips:
        hour_map = {row['hour']: row['queries'] for row in hourly_data[ip]['hours']}
        data[ip] = [hour_map.get(h, 0) for h in hours]

    global_max = max((max(vals) for vals in data.values()), default=1) or 1

    # SVG dimensions
    W, H   = 660, 200
    PAD_L  = 40
    PAD_R  = 10
    PAD_T  = 16
    PAD_B  = 28
    chart_w = W - PAD_L - PAD_R
    chart_h = H - PAD_T - PAD_B
    bar_w   = chart_w / 24

    PALETTE = ['#0969da', '#cf222e', '#1a7f37', '#8250df', '#e3b341']

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'style="width:100%;max-width:{W}px;height:auto;display:block">'
    ]

    # Background
    parts.append(f'<rect width="{W}" height="{H}" fill="#ffffff" rx="6"/>')

    # Gridlines (4 horizontal)
    for g in range(1, 5):
        y = PAD_T + chart_h * g / 4
        parts.append(f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{W-PAD_R}" y2="{y:.1f}" '
                     f'stroke="#e8ecf0" stroke-width="1"/>')

    # Y-axis label (top value)
    parts.append(f'<text x="{PAD_L-4}" y="{PAD_T+6}" text-anchor="end" '
                 f'font-size="9" fill="#656d76">{global_max}</text>')
    parts.append(f'<text x="{PAD_L-4}" y="{PAD_T+chart_h//2}" text-anchor="end" '
                 f'font-size="9" fill="#656d76">{global_max//2}</text>')

    # Bars for first client (stacked behind lines)
    first_ip = top_ips[0]
    first_color = PALETTE[0]
    for i, v in enumerate(data[first_ip]):
        bh = (v / global_max) * chart_h
        bx = PAD_L + i * bar_w
        by = PAD_T + chart_h - bh
        parts.append(
            f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w-1:.1f}" height="{bh:.1f}" '
            f'fill="{first_color}20" rx="1"/>'
        )

    # Lines for each client
    for idx, ip in enumerate(top_ips):
        color = PALETTE[idx % len(PALETTE)]
        vals  = data[ip]
        pts   = []
        for i, v in enumerate(vals):
            cx = PAD_L + i * bar_w + bar_w / 2
            cy = PAD_T + chart_h - (v / global_max) * chart_h
            pts.append(f'{cx:.1f},{cy:.1f}')
        parts.append(
            f'<polyline points="{" ".join(pts)}" fill="none" '
            f'stroke="{color}" stroke-width="2" stroke-linejoin="round"/>'
        )
        # Dots at peaks
        peak_val = max(vals)
        if peak_val > 0:
            peak_i = vals.index(peak_val)
            cx = PAD_L + peak_i * bar_w + bar_w / 2
            cy = PAD_T + chart_h - (peak_val / global_max) * chart_h
            parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="3" fill="{color}"/>')
            parts.append(
                f'<text x="{cx:.1f}" y="{cy-6:.1f}" text-anchor="middle" '
                f'font-size="8" fill="{color}">{peak_val}</text>'
            )

    # X-axis: every 3 hours
    for i, h in enumerate(hours):
        if int(h) % 3 == 0:
            cx = PAD_L + i * bar_w + bar_w / 2
            parts.append(
                f'<text x="{cx:.1f}" y="{PAD_T+chart_h+14}" text-anchor="middle" '
                f'font-size="9" fill="#656d76">{h}:00</text>'
            )

    # Legend (right side → bottom for mobile so we keep SVG width manageable)
    legend_y = PAD_T
    for idx, ip in enumerate(top_ips):
        color = PALETTE[idx % len(PALETTE)]
        name  = (hourly_data[ip].get('name') or ip)[:20]
        lx = PAD_L + 4
        ly = PAD_T + chart_h + 22 + idx * 13
        parts.append(f'<rect x="{lx}" y="{ly-7}" width="10" height="10" fill="{color}" rx="2"/>')
        parts.append(
            f'<text x="{lx+13}" y="{ly+1}" font-size="9" fill="#1f2328">{name}</text>'
        )

    # Extend SVG height for legend rows below chart
    legend_extra = len(top_ips) * 13 + 8
    svg_h = H + legend_extra
    # Replace viewBox and height
    parts[0] = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {svg_h}" '
        f'style="width:100%;max-width:{W}px;height:auto;display:block">'
    )
    parts.append('</svg>')
    return ''.join(parts)


# ── Report sections ────────────────────────────────────────────────────────────

def _safe(fn, *args, **kwargs):
    """Call a section function; return a styled error card on failure instead of crashing the whole report."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        log.warning(f"Section {fn.__name__} failed: {exc}")
        return (f'<div class="card" style="border-color:#fca5a5;border-left:3px solid #cf222e">'
                f'<p style="color:#b91c1c;font-size:12px;padding:4px 0">'
                f'⚠️ {fn.__name__} could not load: {exc}</p></div>')


def section_stat_cards(start_date: str, end_date: str, comp: dict) -> str:
    ns   = A.network_summary(start_date, end_date)
    yest = comp['yesterday']
    tq   = int(ns.get('total_queries') or 0)
    bq   = int(ns.get('blocked_queries') or 0)
    ud   = int(ns.get('unique_domains') or 0)
    ac   = int(ns.get('active_clients') or 0)
    bp   = round((bq / tq * 100) if tq else 0, 1)
    tq_chg = pct_change(tq, int(yest.get('avg_q') or 0))
    ud_chg = pct_change(ud, int(yest.get('avg_d') or 0))

    def sbox(num, lbl, chg=None):
        c = f'<div class="chg">{arrow(chg)}</div>' if chg is not None else ''
        return (f'<div class="sbox"><div class="num">{num:,}</div>'
                f'<div class="lbl">{lbl}</div>{c}</div>')

    return f"""
    <div class="stat-grid">
      {sbox(tq,  'Total Requests', tq_chg)}
      {sbox(bq,  f'Blocked ({bp}%)')}
      {sbox(ud,  'Unique Sites', ud_chg)}
      {sbox(ac,  'Active Devices')}
    </div>"""


def section_plain_english(start_date: str, end_date: str, cats: list, comp: dict, period: str = 'daily') -> str:
    ns   = A.network_summary(start_date, end_date)
    yest = comp['yesterday']
    tq   = int(ns.get('total_queries') or 0)
    bq   = int(ns.get('blocked_queries') or 0)
    ac   = int(ns.get('active_clients') or 0)
    bp   = round((bq / tq * 100) if tq else 0, 1)
    ytq  = int(yest.get('avg_q') or 0)

    period_noun = {'daily': 'Today', 'weekly': 'This week', 'monthly': 'This month'}.get(period, 'In this period')
    period_desc = {'daily': 'today', 'weekly': 'over the past 7 days', 'monthly': 'over the past 30 days'}.get(period, 'in this period')

    total_cat_q = sum(c['queries'] for c in cats) or 1
    top_cat = max(cats, key=lambda c: c['queries'], default=None)
    top_cat_pct = int((top_cat['queries'] / total_cat_q) * 100) if top_cat else 0
    top_cat_lbl = top_cat['category'].replace('_', ' ') if top_cat else 'unknown'

    flagged = [c for c in cats if
               (c['category'] in ALERT_CATEGORIES and c['queries'] > 0) or
               (c['category'] in WATCH_CATEGORIES and c['queries'] >= WATCH_CATEGORIES[c['category']])]

    compare_txt = ''
    if period == 'daily' and ytq:
        if tq > ytq:
            compare_txt = f" That's <strong>more than yesterday</strong> ({ytq:,} requests)."
        else:
            compare_txt = f" That's <strong>less than yesterday</strong> ({ytq:,} requests)."

    if flagged:
        flag_txt = (f'<strong style="color:#b91c1c">⚠️ {len(flagged)} '
                    f'categor{"y" if len(flagged)==1 else "ies"} need your attention</strong> — '
                    + ', '.join(c['category'].replace('_', ' ') for c in flagged[:3]) + '.')
    else:
        flag_txt = '<strong style="color:#1a7f37">✅ All categories look normal.</strong>'

    return f"""
    <div class="summary-box">
      {period_noun} your network made <strong>{tq:,} DNS requests</strong> {period_desc} from
      <strong>{ac} device{"s" if ac != 1 else ""}</strong>.
      Pi-hole blocked <strong>{bq:,} ({bp}%)</strong> — stopping ads, trackers and
      unwanted traffic before they reach your devices.{compare_txt}
      The most activity was <strong>{top_cat_lbl} ({top_cat_pct}% of traffic)</strong>.
      {flag_txt}
    </div>"""


def section_alert_banner(start_date: str, end_date: str, cats: list, conn) -> str:
    alerts = []
    frag, fparams = A._date_filter(start_date, end_date)
    for c in cats:
        q = c['queries']
        if c['category'] in ALERT_CATEGORIES and q > 0:
            devs = conn.execute(
                f"SELECT DISTINCT COALESCE(client_name,client_ip) AS n "
                f"FROM queries WHERE {frag} AND category=? LIMIT 4",
                fparams + [c['category']]
            ).fetchall()
            dev_str = ', '.join(r['n'] for r in devs)
            alerts.append(
                f"<li>🚨 <strong>{c['category'].replace('_',' ').title()}</strong>: "
                f"{q:,} requests on {dev_str}</li>"
            )

    if not alerts:
        return ''

    return f"""
    <div class="alert-banner">
      <h3>⚠️ Content Alert — Review Required</h3>
      <ul>{"".join(alerts)}</ul>
    </div>"""


def section_risky_categories(start_date: str, end_date: str, cats: list, conn) -> str:
    RISK = [
        ('adult',        '🔞', 'Adult Content',       'alert',
         'Explicit/adult websites — not appropriate for children.'),
        ('vpn_proxy',    '🔒', 'VPN / Proxy',          'alert',
         'VPN or proxy services can bypass parental controls and filters.'),
        ('crypto',       '₿',  'Crypto / Blockchain',  'alert',
         'Cryptocurrency activity — watch for scams or unsupervised spending.'),
        ('social_media', '📱', 'Social Media',         'watch',
         'Social platforms — monitor screen time especially for children.'),
        ('gaming',       '🎮', 'Gaming',               'watch',
         'Online gaming — check for excessive hours or in-app purchases.'),
        ('streaming',    '🎬', 'Video Streaming',      'watch',
         'Streaming — high usage may mean extended screen time.'),
    ]

    cat_map = {c['category']: c for c in cats}
    cards = []

    for cat, icon, title, level, desc in RISK:
        row = cat_map.get(cat, {'queries': 0, 'unique_domains': 0})
        q   = int(row.get('queries', 0))
        ud  = int(row.get('unique_domains', 0))

        # Badge + card class
        if level == 'alert' and q > 0:
            card_cls, bdg_cls, bdg_txt = 'alert-card', 'bdg-alert', '🚨 Alert'
        elif level == 'watch' and q >= WATCH_CATEGORIES.get(cat, 9999):
            card_cls, bdg_cls, bdg_txt = 'warn-card',  'bdg-warn',  '⚠️ High Usage'
        elif level == 'watch' and q > 0:
            card_cls, bdg_cls, bdg_txt = 'info-card',  'bdg-info',  'ℹ️ Active'
        else:
            card_cls, bdg_cls, bdg_txt = 'clean-card', 'bdg-clean', '✅ Clear'

        count_txt  = f'{q:,} requests' if q else 'None today'
        unique_txt = f'<span class="rc-cnt"> · {ud} sites</span>' if ud else ''

        # Top sites
        sites_html = ''
        _frag, _fparams = A._date_filter(start_date, end_date)
        if q > 0:
            sites = A.top_domains_by_category(start_date, cat, end_date=end_date, limit=5, conn=conn)
            if sites:
                rows_html = ''.join(
                    f'<div class="rc-site"><a href="https://{s["domain"]}" '
                    f'target="_blank">{s["domain"]}</a> '
                    f'<span class="rc-cnt">({s["queries"]:,})</span></div>'
                    for s in sites
                )
                sites_html = f'<div class="rc-sites">{rows_html}</div>'
            devs = conn.execute(
                f"SELECT DISTINCT COALESCE(client_name,client_ip) AS n "
                f"FROM queries WHERE {_frag} AND category=? LIMIT 4",
                _fparams + [cat]
            ).fetchall()
            dev_str = ', '.join(r['n'] for r in devs)
            dev_html = f'<div class="rc-devs">📱 <strong>Devices:</strong> {dev_str}</div>' if dev_str else ''
        else:
            dev_html = ''
            sites_html = ('<div style="font-size:11px;color:#1a7f37">'
                          '✅ None accessed today</div>')

        threshold_note = ''
        if level == 'watch' and q > 0 and q < WATCH_CATEGORIES.get(cat, 0):
            threshold_note = (f' Below watch threshold of '
                              f'{WATCH_CATEGORIES[cat]:,}.')

        cards.append(f"""
      <div class="rc-card {card_cls}">
        <div class="rc-top">
          <div>
            <div class="rc-icon">{icon}</div>
            <div class="rc-title">{title}</div>
          </div>
          <span class="rc-bdg {bdg_cls}">{bdg_txt}</span>
        </div>
        <div class="rc-count">{count_txt}{unique_txt}</div>
        <div class="rc-desc">{desc}{threshold_note}</div>
        {dev_html}
        {sites_html}
      </div>""")

    return f"""
    <div class="card">
      <h2>🚨 Categories That Need Your Attention</h2>
      <div class="rc-grid">{"".join(cards)}</div>
    </div>"""


def section_device_cards(start_date: str, end_date: str, conn, dashboard_url: str = '', cfg: dict = None) -> str:
    clients  = A.client_compare(start_date) if start_date == end_date else A.client_range_summary(start_date, end_date, conn=conn)
    registry = {
        row['last_ip']: dict(row)
        for row in conn.execute(
            "SELECT last_ip, mac, hostname, device_type, custom_name FROM device_registry"
        ).fetchall()
    }

    personal = [c for c in clients
                if not _skip_device(c.get('client_name', ''), c.get('client_ip', ''), cfg)]
    if not personal:
        return ''

    max_q = max((c['today_q'] for c in personal), default=1) or 1
    cards = []

    for i, c in enumerate(personal):
        ip   = c['client_ip']
        name = c['client_name'] or ip
        reg  = registry.get(ip, {})
        dtype   = reg.get('device_type', '')
        hostname= reg.get('hostname', '')
        mac     = reg.get('mac', '')

        # Per-device category breakdown
        dev_cats = A.category_breakdown(start_date, end_date=end_date, client_ip=ip, conn=conn)
        total_cat_q = sum(x['queries'] for x in dev_cats) or 1
        top_cats = sorted(dev_cats, key=lambda x: x['queries'], reverse=True)[:4]

        cat_pills = ''.join(
            cat_pill(x['category'], int(x['queries'] / total_cat_q * 100))
            for x in top_cats if x['queries'] > 0
        )

        # Flags
        alert_flags = [x for x in dev_cats if x['category'] in ALERT_CATEGORIES and x['queries'] > 0]
        warn_flags  = [x for x in dev_cats
                       if x['category'] in WATCH_CATEGORIES
                       and x['queries'] >= WATCH_CATEGORIES[x['category']]
                       and x['category'] not in {f['category'] for f in alert_flags}]

        flags_html = ''
        for f in alert_flags + warn_flags:
            cls  = 'alert-flag' if f['category'] in ALERT_CATEGORIES else 'warn-flag'
            icon = '🚨' if f['category'] in ALERT_CATEGORIES else '⚠️'
            sites = A.top_domains_by_category(start_date, f['category'], end_date=end_date, limit=4,
                                               client_ip=ip, conn=conn)
            links = ' '.join(
                f'<a href="https://{s["domain"]}" target="_blank">'
                f'{s["domain"]} ({s["queries"]:,})</a>'
                for s in sites
            )
            flags_html += f"""
        <div class="dev-flag {cls}">
          <div class="flag-ttl">{icon} {f['category'].replace('_',' ').title()}: {f['queries']:,} requests</div>
          <div class="flag-sites">{links or 'No specific sites found'}</div>
        </div>"""

        bar_pct = int((c['today_q'] / max_q) * 100)
        chg     = pct_change(c['today_q'], c['yesterday_q']) if start_date == end_date else None
        flagged_cls = ' flagged' if alert_flags else ''

        hostname_line = ''
        if hostname and hostname != name:
            hostname_line = f' · {hostname}'
        mac_line = f'<div class="dev-mac">{mac}</div>' if mac else ''
        dtype_line = f'<div class="dev-type">{dtype}</div>' if dtype else ''

        chg_cell = (f'<div class="dev-stat"><div class="v" style="font-size:13px">{arrow(chg)}</div>'
                    f'<div class="l">vs Yesterday</div></div>') if chg is not None else ''

        detail_url = f'{dashboard_url}/device?ip={ip}&date={end_date}' if dashboard_url else ''
        if alert_flags and detail_url:
            view_btn = (f'<a href="{detail_url}" target="_blank" '
                        f'style="display:inline-block;margin-top:10px;padding:6px 14px;'
                        f'background:#fff0f0;border:1px solid #fca5a5;border-radius:6px;'
                        f'font-size:11px;font-weight:600;color:#b91c1c;text-decoration:none">'
                        f'🔍 View Full Details</a>')
        elif (alert_flags or warn_flags) and detail_url:
            view_btn = (f'<a href="{detail_url}" target="_blank" '
                        f'style="display:inline-block;margin-top:10px;padding:6px 14px;'
                        f'background:#fffbeb;border:1px solid #fde68a;border-radius:6px;'
                        f'font-size:11px;font-weight:600;color:#92400e;text-decoration:none">'
                        f'🔍 View Full Details</a>')
        elif detail_url:
            view_btn = (f'<a href="{detail_url}" target="_blank" '
                        f'style="display:inline-block;margin-top:10px;padding:6px 14px;'
                        f'background:#f0f7ff;border:1px solid #c9dff7;border-radius:6px;'
                        f'font-size:11px;color:#0969da;text-decoration:none">'
                        f'🔍 View Details</a>')
        else:
            view_btn = ''

        cards.append(f"""
      <div class="dev-card{flagged_cls}">
        <div class="dev-hdr">
          <div class="dev-avi">{DEVICE_ICONS[i % len(DEVICE_ICONS)]}</div>
          <div>
            <div class="dev-name">{name}</div>
            {dtype_line}
            <div class="dev-ip">{ip}{hostname_line}</div>
            {mac_line}
          </div>
        </div>
        <div class="dev-stats">
          <div class="dev-stat">
            <div class="v">{c['today_q']:,}</div><div class="l">Requests</div>
          </div>
          <div class="dev-stat">
            <div class="v">{c['today_d']:,}</div><div class="l">Sites</div>
          </div>
          {chg_cell}
        </div>
        <div class="dev-bar-bg">
          <div class="dev-bar-fg" style="width:{bar_pct}%"></div>
        </div>
        <div class="dev-cats">{cat_pills}</div>
        {('<div class="dev-flags">' + flags_html + '</div>') if flags_html else ''}
        {view_btn}
      </div>""")

    period_lbl = 'today' if start_date == end_date else f'{start_date} – {end_date}'
    return f"""
    <div class="card">
      <h2>📱 Your Devices — Activity {period_lbl}</h2>
      <div class="dev-grid">{"".join(cards)}</div>
    </div>"""


def section_client_timeseries(start_date: str, end_date: str, conn, cfg: dict = None) -> str:
    # Hourly chart is only meaningful for single-day reports
    if start_date != end_date:
        return ''
    hourly = A.all_clients_hourly(start_date, conn=conn)
    if not hourly:
        return ''
    svg = build_hourly_svg(hourly, top_n=5, cfg=cfg)
    return f"""
    <div class="card">
      <h2>📈 Hourly Activity by Device</h2>
      <p>Queries per hour for your top devices today — peak hour marked with a dot.</p>
      {svg}
    </div>"""


def section_category_chart(cats: list) -> str:
    """Inline SVG donut chart for category breakdown."""
    if not cats:
        return ''
    top8 = sorted(cats, key=lambda c: c['queries'], reverse=True)[:8]
    total = sum(c['queries'] for c in top8) or 1

    W, H = 300, 160
    cx, cy = 90, 80
    r_outer, r_inner = 65, 40

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'style="width:100%;max-width:{W}px;height:auto;display:block">'
    ]
    parts.append(f'<rect width="{W}" height="{H}" fill="#ffffff" rx="6"/>')

    angle = -math.pi / 2  # start at top
    for cat in top8:
        pct = cat['queries'] / total
        slice_angle = pct * 2 * math.pi
        end_angle = angle + slice_angle
        color = CATEGORY_COLORS.get(cat['category'], DEFAULT_COLOR)

        x1 = cx + r_outer * math.cos(angle)
        y1 = cy + r_outer * math.sin(angle)
        x2 = cx + r_outer * math.cos(end_angle)
        y2 = cy + r_outer * math.sin(end_angle)
        ix1 = cx + r_inner * math.cos(angle)
        iy1 = cy + r_inner * math.sin(angle)
        ix2 = cx + r_inner * math.cos(end_angle)
        iy2 = cy + r_inner * math.sin(end_angle)
        large_arc = 1 if slice_angle > math.pi else 0

        path = (f'M {x1:.2f} {y1:.2f} '
                f'A {r_outer} {r_outer} 0 {large_arc} 1 {x2:.2f} {y2:.2f} '
                f'L {ix2:.2f} {iy2:.2f} '
                f'A {r_inner} {r_inner} 0 {large_arc} 0 {ix1:.2f} {iy1:.2f} Z')
        parts.append(f'<path d="{path}" fill="{color}" stroke="#fff" stroke-width="1.5"/>')
        angle = end_angle

    # Legend
    lx = 165
    for i, cat in enumerate(top8):
        pct_val = int(cat['queries'] / total * 100)
        color = CATEGORY_COLORS.get(cat['category'], DEFAULT_COLOR)
        label = cat['category'].replace('_', ' ').title()[:14]
        ly = 18 + i * 18
        parts.append(f'<rect x="{lx}" y="{ly-8}" width="10" height="10" fill="{color}" rx="2"/>')
        parts.append(f'<text x="{lx+13}" y="{ly}" font-size="9" fill="#1f2328">{label} {pct_val}%</text>')

    parts.append('</svg>')
    return f'<div style="margin-bottom:8px">{"".join(parts)}</div>'


def section_category_table(date: str, cats: list) -> str:
    if not cats:
        return ''
    max_q = max((c['queries'] for c in cats), default=1) or 1

    sorted_cats = sorted(cats, key=lambda c: (
        -(2 if (c['category'] in ALERT_CATEGORIES and c['queries'] > 0) else
          1 if (c['category'] in WATCH_CATEGORIES and c['queries'] >= WATCH_CATEGORIES.get(c['category'], 9999)) else 0),
        -c['queries']
    ))

    rows = ''
    for c in sorted_cats:
        q   = c['queries']
        col = CATEGORY_COLORS.get(c['category'], DEFAULT_COLOR)
        if c['category'] in ALERT_CATEGORIES and q > 0:
            status = '<span class="s-alert">🚨 Alert</span>'
        elif c['category'] in WATCH_CATEGORIES and q >= WATCH_CATEGORIES.get(c['category'], 9999):
            status = '<span class="s-warn">⚠️ Watch</span>'
        else:
            status = '<span class="s-ok">✅ Normal</span>'
        total_q = sum(x['queries'] for x in cats) or 1
        rows += f"""
        <tr>
          <td>{cat_badge(c['category'])}</td>
          <td>{q:,} {mini_bar(q, max_q, col)}</td>
          <td>{int(q/total_q*100)}%</td>
          <td>{c['unique_domains']:,}</td>
          <td>{status}</td>
        </tr>"""

    return f"""
    <div class="card">
      <h2>📂 Full Category Breakdown</h2>
      <table>
        <tr><th>Category</th><th>Requests</th><th>% of Traffic</th>
            <th>Unique Sites</th><th>Status</th></tr>
        {rows}
      </table>
    </div>"""


def section_protection(start_date: str, end_date: str, conn) -> str:
    b = A.blocked_queries_summary(start_date, end_date, conn=conn)
    if not b or not b['total_queries']:
        return ''
    total   = b['total_queries']
    blocked = b['blocked_queries']
    bp      = round(blocked / total * 100, 1) if total else 0
    allowed = total - blocked
    quality = 'Excellent' if bp > 20 else 'Good' if bp > 10 else 'Moderate'
    tip = ('Your Pi-hole is working very hard — well-protected network.'
           if bp > 20 else
           'Pi-hole is providing solid protection.'
           if bp > 10 else
           'Consider reviewing your blocklists to improve protection.')

    def pbox(v, l):
        return (f'<div class="pbox"><div class="pv">{v:,}</div>'
                f'<div class="pl">{l}</div></div>')

    return f"""
    <div class="prot-box">
      <div class="card" style="background:#f0fff4;border:none;box-shadow:none;padding:0;margin:0">
        <h2 style="color:#15803d">🛡️ Pi-hole Protection</h2>
        <div class="prot-grid">
          {pbox(total,   'Total Requests')}
          {pbox(blocked, f'Blocked ({bp}%)')}
          {pbox(allowed, 'Passed Through')}
        </div>
        <p style="font-size:12px;color:#3d444d">
          Out of {total:,} requests, Pi-hole blocked <strong>{blocked:,} ({bp}%)</strong>
          — ads, trackers and unwanted domains never reached your devices.
          Protection quality: <strong>{quality}</strong>. {tip}
        </p>
      </div>
    </div>"""


def section_new_domains(start_date: str, end_date: str) -> str:
    nd = A.new_domains(start_date, end_date)
    if not nd:
        return ''
    period_lbl = 'Today' if start_date == end_date else f'{start_date} – {end_date}'
    rows = ''
    for d in nd[:12]:
        rows += (f'<tr><td class="mono">{d["domain"]}</td>'
                 f'<td>{d["client_name"] or d["client_ip"]}</td>'
                 f'<td>{cat_badge(d["category"])}</td>'
                 f'<td>{d["queries"]:,}</td></tr>')
    return f"""
    <div class="card">
      <h2>🆕 New Sites — First Seen {period_lbl}</h2>
      <table>
        <tr><th>Domain</th><th>First Seen By</th><th>Category</th><th>Requests</th></tr>
        {rows}
      </table>
    </div>"""


def section_trend_table(conn, days: int) -> str:
    trend = A.daily_trend(days, conn=conn)
    if not trend:
        return ''
    rows = ''
    for r in reversed(trend):
        rows += (f'<tr><td>{r["date"]}</td>'
                 f'<td>{int(r["total_queries"] or 0):,}</td>'
                 f'<td>{int(r["blocked_queries"] or 0):,}</td>'
                 f'<td>{int(r["unique_domains"] or 0):,}</td></tr>')
    return f"""
    <div class="card">
      <h2>📅 {days}-Day Trend</h2>
      <table>
        <tr><th>Date</th><th>Total Requests</th><th>Blocked</th><th>Unique Sites</th></tr>
        {rows}
      </table>
    </div>"""


# ── Health section ────────────────────────────────────────────────────────────

def section_health(cfg: dict) -> str:
    """Render a Pi-hole + system health summary for the email report footer."""
    data = H.collect_all(cfg)
    sys_h  = data.get('system', {})
    db_h   = data.get('db', {})
    svcs   = data.get('services', [])
    ph     = data.get('pihole', {})
    errors = data.get('recent_errors', [])
    collected = data.get('collected_at', '')

    # ── Helper builders ──────────────────────────────────────────────────────
    def pill(text, color):
        bg = {'green': '#dcfce7', 'red': '#fee2e2', 'yellow': '#fef3c7',
              'blue': '#dbeafe', 'gray': '#f3f4f6'}.get(color, '#f3f4f6')
        border = {'green': '#86efac', 'red': '#fca5a5', 'yellow': '#fcd34d',
                  'blue': '#93c5fd', 'gray': '#e5e7eb'}.get(color, '#e5e7eb')
        fg = {'green': '#15803d', 'red': '#b91c1c', 'yellow': '#854d0e',
              'blue': '#1d4ed8', 'gray': '#374151'}.get(color, '#374151')
        return (f'<span style="background:{bg};border:1px solid {border};color:{fg};'
                f'border-radius:10px;padding:2px 8px;font-size:10px;font-weight:600">{text}</span>')

    def row(label, value, indent=False):
        pad = '16px' if indent else '0'
        return (f'<tr><td style="padding:5px {pad} 5px 0;font-size:12px;color:#3d444d;'
                f'width:50%;vertical-align:top">{label}</td>'
                f'<td style="padding:5px 0;font-size:12px;color:#1f2328;font-weight:500">'
                f'{value}</td></tr>')

    def section_card(title, rows_html, border_color='#d0d7de'):
        return f"""
        <div style="background:#fff;border:1px solid {border_color};border-radius:8px;
                    padding:14px;margin-bottom:10px">
          <div style="font-size:12px;font-weight:600;color:#0969da;margin-bottom:10px;
                      border-bottom:1px solid #e8ecf0;padding-bottom:6px">{title}</div>
          <table style="width:100%;border-collapse:collapse">{rows_html}</table>
        </div>"""

    # ── Pi-hole status card ──────────────────────────────────────────────────
    if ph.get('reachable'):
        blocking_pill = pill('✅ Blocking ON', 'green') if ph.get('blocking') else pill('⛔ Blocking OFF', 'red')
        pihole_rows = ''.join([
            row('Status',      blocking_pill),
            row('Gravity',     f"{ph['gravity_count_h']} domains" if ph.get('gravity_count_h') else '—'),
            row('Version',     ph.get('version') or '—'),
            row('Upstream DNS', ph.get('upstream_dns') or '—'),
            row('FTL',         pill('Running', 'green') if ph.get('ftl_running') else pill('Unknown', 'gray')),
        ])
        ph_card = section_card('🛡️ Pi-hole Status', pihole_rows)
    else:
        err = ph.get('error', 'Cannot reach Pi-hole API')
        ph_card = section_card('🛡️ Pi-hole Status',
            row('Reachable', pill('⚠️ Unreachable', 'red')) +
            row('Error', f'<span style="font-size:11px;color:#b91c1c">{err[:80]}</span>'),
            border_color='#fca5a5')

    # ── System resources card ────────────────────────────────────────────────
    disk_pct = sys_h.get('disk_pct', 0)
    disk_color = 'red' if disk_pct > 90 else 'yellow' if disk_pct > 75 else 'green'
    mem_pct = sys_h.get('mem_pct', 0)
    mem_color = 'red' if mem_pct > 90 else 'yellow' if mem_pct > 75 else 'green'
    cpu_pct = sys_h.get('cpu_load_pct', 0)
    cpu_color = 'red' if cpu_pct > 90 else 'yellow' if cpu_pct > 50 else 'green'

    temp = sys_h.get('cpu_temp_c')
    temp_str = '—'
    if temp is not None:
        temp_color = 'red' if temp > 75 else 'yellow' if temp > 60 else 'green'
        temp_str = pill(f'{temp}°C', temp_color)

    sys_rows = ''.join([
        row('Disk Used',  f"{pill(f'{disk_pct}%', disk_color)} "
                          f"({sys_h.get('disk_used_h','—')} used · {sys_h.get('disk_free_h','—')} free)"),
        row('RAM',        f"{pill(f'{mem_pct}%', mem_color)} "
                          f"({sys_h.get('mem_used_h','—')} / {sys_h.get('mem_total_h','—')})"),
        row('CPU Load',   f"{pill(f'{cpu_pct}%', cpu_color)} "
                          f"({sys_h.get('cpu_load1','0')} · {sys_h.get('cpu_load5','0')} · {sys_h.get('cpu_load15','0')} avg)"),
        row('Uptime',     sys_h.get('uptime_str', '—')),
        row('CPU Temp',   temp_str),
    ])
    sys_card = section_card('💻 System Resources', sys_rows)

    # ── Analytics DB card ────────────────────────────────────────────────────
    stale = db_h.get('last_fetch_stale', False)
    fetch_pill = pill(f"⚠️ {db_h['last_fetch_ago']}", 'red') if stale else pill(db_h.get('last_fetch_ago', '—'), 'green')
    gaps = db_h.get('data_gaps', [])
    gap_str = ', '.join(gaps) if gaps else pill('None', 'green')

    db_rows = ''.join([
        row('DB Size',       db_h.get('db_size_h', '—')),
        row('Total Records', f"{db_h.get('total_queries', 0):,}"),
        row('Days Tracked',  f"{db_h.get('total_days', 0)} days"),
        row('Today\'s Queries', f"{db_h.get('today_queries', 0):,}"),
        row('Last Fetch',    f"{db_h.get('last_fetch_time','—')} ({fetch_pill})"),
        row('Log Files',     db_h.get('logs_total_h', '—') + ' total'),
        row('Data Gaps (7d)', gap_str),
    ])
    db_card = section_card('📊 Analytics Data', db_rows,
                            border_color='#fca5a5' if stale or gaps else '#d0d7de')

    # ── Services card ────────────────────────────────────────────────────────
    svc_rows = ''
    for svc in svcs:
        active = svc.get('active', 'unknown')
        sub    = svc.get('sub', '')
        if active == 'no systemd':
            p = pill('Dev mode', 'gray')
        elif active == 'active':
            p = pill('✅ Active', 'green')
        elif active == 'inactive':
            p = pill('⏸ Inactive', 'yellow')
        elif active == 'failed':
            p = pill('❌ Failed', 'red')
        else:
            p = pill(active, 'gray')

        trigger = svc.get('last_trigger', '')
        detail  = f' <span style="font-size:10px;color:#3d444d">· last: {trigger}</span>' if trigger else ''
        svc_rows += row(svc['label'], p + detail)
    svc_card = section_card('⚙️ Services', svc_rows)

    # ── Recent errors card (only if there are any) ───────────────────────────
    errors_card = ''
    if errors:
        err_rows = ''.join(
            f'<tr><td style="padding:3px 0;font-size:10px;font-family:monospace;'
            f'color:#b91c1c;word-break:break-all">'
            f'<span style="color:#3d444d">[{e["file"]}]</span> {e["line"][:120]}</td></tr>'
            for e in errors[-5:]
        )
        errors_card = f"""
        <div style="background:#fff5f5;border:1px solid #fca5a5;border-left:3px solid #cf222e;
                    border-radius:8px;padding:12px 14px;margin-bottom:10px">
          <div style="font-size:12px;font-weight:600;color:#b91c1c;margin-bottom:8px">
            ⚠️ Recent Errors ({len(errors)} found)
          </div>
          <table style="width:100%;border-collapse:collapse">{err_rows}</table>
        </div>"""

    # ── Layout: 2-column grid ────────────────────────────────────────────────
    return f"""
    <div class="card">
      <h2>🏥 System Health</h2>
      <p style="font-size:11px;color:#3d444d;margin-bottom:12px">
        Collected at {collected}
      </p>
      {errors_card}
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
        <div>{ph_card}{db_card}</div>
        <div>{sys_card}{svc_card}</div>
      </div>
    </div>"""


def section_blocked_domains(start_date: str, end_date: str, conn) -> str:
    """Top domains blocked by Pi-hole — what Pi-hole caught."""
    rows = A.top_blocked_domains(start_date, end_date=end_date, limit=15, conn=conn)
    if not rows:
        return ''
    table_rows = ''
    for r in rows:
        table_rows += (
            f'<tr>'
            f'<td class="mono">{r["domain"]}</td>'
            f'<td>{cat_badge(r["category"] or "other")}</td>'
            f'<td style="color:#cf222e;font-weight:600">{r["blocked_count"]:,}</td>'
            f'<td>{r["device_count"]:,}</td>'
            f'</tr>'
        )
    return f"""
    <div class="card">
      <h2>🚫 Top Blocked Domains — What Pi-hole caught</h2>
      <table>
        <tr><th>Domain</th><th>Category</th><th>Times Blocked</th><th>Devices</th></tr>
        {table_rows}
      </table>
    </div>"""


def _ai_md_to_html(text: str) -> str:
    """Convert AI summary markdown to email-safe HTML."""
    import re
    html_lines = []
    for line in text.split('\n'):
        line = line.rstrip()
        if line.startswith('## '):
            html_lines.append(
                f'<h3 style="margin:14px 0 6px;color:#0969da;font-size:15px">{line[3:]}</h3>')
        elif line.startswith('# '):
            html_lines.append(
                f'<h2 style="margin:16px 0 8px;color:#1f2328;font-size:16px;'
                f'border-bottom:1px solid #e8ecf0;padding-bottom:4px">{line[2:]}</h2>')
        elif line.startswith('- ') or line.startswith('* '):
            body = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line[2:])
            html_lines.append(f'<li style="margin:4px 0;font-size:14px;color:#1f2328">{body}</li>')
        elif line.startswith('  - ') or line.startswith('  * '):
            body = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line[4:])
            html_lines.append(
                f'<li style="margin:2px 0 2px 18px;font-size:13px;color:#3d444d">{body}</li>')
        elif '⚠️' in line or 'ALERT' in line:
            html_lines.append(
                f'<p style="color:#b91c1c;font-weight:600;margin:4px 0;font-size:13px">{line}</p>')
        elif line == '':
            html_lines.append('<br>')
        else:
            line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
            html_lines.append(f'<p style="margin:4px 0;font-size:14px;color:#1f2328">{line}</p>')
    return '\n'.join(html_lines)


def section_ai_summary(period: str) -> str:
    """Embed the stored AI summary (from the 5 AM scheduled run) into the report."""
    try:
        import summarizer as S
        row = S.get_latest_summary(period)
    except Exception:
        return ''
    if not row:
        return ''

    generated = (row.get('generated_at') or '')[:16]
    model     = row.get('model', 'Gemini')
    src_label = 'Scheduled (5 AM)' if row.get('run_type') == 'scheduled' else 'On-demand'
    body_html = _ai_md_to_html(row['summary_text'])

    return (
        '<div class="card">'
        '<h2>\U0001f916 AI Network Summary</h2>'
        f'<p style="font-size:13px;color:#3d444d;margin-bottom:12px">'
        f'{src_label} \u00b7 {model} \u00b7 Generated {generated}</p>'
        '<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;'
        'padding:16px 20px;font-size:14px;line-height:1.6">'
        f'{body_html}'
        '</div></div>'
    )


# ── Build full report ──────────────────────────────────────────────────────────

def build_report_html(end_date: str, period: str = 'daily', *, start_date: str = None) -> str:
    if start_date is None:
        days = {'weekly': 6, 'monthly': 29}.get(period, 0)
        start_date = str((datetime.strptime(end_date, '%Y-%m-%d').date() - timedelta(days=days)))
    conn = A.get_conn()
    try:
        comp  = A.compare_periods(end_date, conn=conn)
        cats  = A.category_breakdown(start_date, end_date=end_date, conn=conn)
        label = {'daily': 'Daily', 'weekly': 'Weekly', 'monthly': 'Monthly'}.get(period, 'Daily')
        date_range_lbl = end_date if start_date == end_date else f'{start_date} – {end_date}'
        trend_days = {'weekly': 7, 'monthly': 7}.get(period, 0)
        cfg = load_config()
        dashboard_url = cfg.get('dashboard', {}).get('url', 'http://localhost:8080')

        html = f"""<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{CSS}
</head>
<body><div class="wrap">

  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-radius:10px 10px 0 0;overflow:hidden;">
    <tr><td bgcolor="#0969da" style="background:#0969da;padding:20px 18px;border-radius:10px 10px 0 0;">
      <h1 style="margin:0 0 4px;font-size:22px;color:#ffffff;font-family:Arial,sans-serif;">🛡️ Pi-hole Network Report</h1>
      <p style="margin:0;font-size:14px;color:#ffffff;opacity:.85;font-family:Arial,sans-serif;">{label} Report · {datetime.now().strftime('%B %d, %Y at %H:%M')} · Raspberry Pi</p>
    </td></tr>
  </table>

  {_safe(section_alert_banner, start_date, end_date, cats, conn)}

  <div class="card" style="margin-top:12px">
    <h2>🌐 Network Overview — {date_range_lbl}</h2>
    {_safe(section_stat_cards, start_date, end_date, comp)}
    {_safe(section_plain_english, start_date, end_date, cats, comp, period)}
  </div>

  {_safe(section_ai_summary, period)}
  {_safe(section_risky_categories, start_date, end_date, cats, conn)}
  {_safe(section_device_cards, start_date, end_date, conn, dashboard_url=dashboard_url, cfg=cfg)}
  {_safe(section_client_timeseries, start_date, end_date, conn, cfg=cfg)}
  {_safe(section_category_chart, cats)}
  {_safe(section_category_table, end_date, cats)}
  {_safe(section_protection, start_date, end_date, conn)}
  {_safe(section_blocked_domains, start_date, end_date, conn)}
  {_safe(section_new_domains, start_date, end_date)}
  {_safe(section_trend_table, conn, trend_days) if trend_days else ''}
  {_safe(section_health, cfg)}

  <div class="footer">
    Generated by Pi-hole Analytics · Raspberry Pi<br>
    <a href="{dashboard_url}">Open Live Dashboard</a> ·
    <a href="{dashboard_url.replace(':8080','')}/admin">Pi-hole Admin</a>
  </div>

</div></body></html>"""

        return html
    finally:
        conn.close()


# ── Email sender ───────────────────────────────────────────────────────────────

def _period_dates(period: str):
    """Return (start_date, end_date) strings for a report period."""
    today = datetime.now().date()
    if period == 'daily':
        return str(today), str(today)
    elif period == 'weekly':
        return str(today - timedelta(days=6)), str(today)
    elif period == 'monthly':
        return str(today - timedelta(days=29)), str(today)
    return str(today), str(today)


def _get_dates_from_params(period: str = None, start_ts: int = None, end_ts: int = None,
                           report_start_date: str = None, report_end_date: str = None):
    """
    Determine start_date and end_date based on provided parameters.
    Priority: (start_ts, end_ts) > (report_start_date, report_end_date) > period.
    """
    if start_ts and end_ts:
        start_dt = datetime.fromtimestamp(start_ts).date()
        end_dt = datetime.fromtimestamp(end_ts).date()
        return str(start_dt), str(end_dt)
    elif report_start_date and report_end_date:
        return report_start_date, report_end_date
    elif period:
        return _period_dates(period)
    else:
        # Default to daily if no specific period or dates are given
        return _period_dates('daily')


def send_report(period: str = 'daily', start_ts: int = None, end_ts: int = None,
                report_start_date: str = None, report_end_date: str = None):
    cfg  = load_config()
    actual_start_date, actual_end_date = _get_dates_from_params(period, start_ts, end_ts, report_start_date, report_end_date)

    log.info(f"Building {period} report for {actual_start_date} – {actual_end_date}…")

    try:
        html = build_report_html(actual_end_date, period, start_date=actual_start_date)
        report_status = "success"
    except Exception as e:
        log.error(f"Failed to build report: {e}")
        html = build_error_report_html(f"{actual_start_date} – {actual_end_date}", period, str(e))
        report_status = "error"

    reports_dir = BASE_DIR / "reports"
    reports_dir.mkdir(exist_ok=True)
    report_label = actual_end_date if actual_start_date == actual_end_date else f"{actual_start_date}_to_{actual_end_date}"
    (reports_dir / f"report_{period}_{report_label}.html").write_text(html)
    log.info(f"Report saved to reports/report_{period}_{report_label}.html")

    ecfg   = cfg['email']
    emoji  = "✅" if report_status == "success" else "❌"
    subject = f"{ecfg['subject_prefix']} {emoji} {period.capitalize()} Report — {actual_start_date} to {actual_end_date}"

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = ecfg['sender_email']
    msg['To']      = ', '.join(ecfg['recipient_emails'])
    msg.attach(MIMEText(html, 'html'))

    try:
        with smtplib.SMTP(ecfg['smtp_server'], ecfg['smtp_port']) as smtp:
            smtp.starttls()
            smtp.login(ecfg['sender_email'], ecfg['sender_password'])
            smtp.sendmail(ecfg['sender_email'], ecfg['recipient_emails'], msg.as_string())
        log.info(f"Report emailed to {ecfg['recipient_emails']}")
    except Exception as e:
        log.error(f"Failed to send email: {e}")


def build_error_report_html(date: str, period: str, error_msg: str) -> str:
    label = {'daily': 'Daily', 'weekly': 'Weekly', 'monthly': 'Monthly'}.get(period, 'Daily')
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8">{CSS}</head>
<body><div class="wrap">
  <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-radius:10px 10px 0 0;overflow:hidden;">
    <tr><td bgcolor="#cf222e" style="background:#cf222e;padding:20px 18px;border-radius:10px 10px 0 0;">
      <h1 style="margin:0 0 4px;font-size:22px;color:#ffffff;font-family:Arial,sans-serif;">❌ Report Generation Failed</h1>
      <p style="margin:0;font-size:14px;color:#ffffff;opacity:.85;font-family:Arial,sans-serif;">{label} Report · {datetime.now().strftime('%B %d, %Y at %H:%M')}</p>
    </td></tr>
  </table>
  <div class="card">
    <h2>🚨 Report Generation Error</h2>
    <p>The {period} report for {date} could not be generated:</p>
    <div style="background:#fff5f5;border:1px solid #fca5a5;border-radius:6px;
                padding:14px;margin:12px 0;font-family:monospace;white-space:pre-wrap;
                color:#b91c1c;font-size:12px">{error_msg}</div>
    <p><strong>Troubleshooting:</strong></p>
    <ul style="font-size:12px;color:#3d444d;padding-left:18px">
      <li>Check fetcher log: <code>tail -f logs/fetcher.log</code></li>
      <li>Check DB: <code>sqlite3 data/analytics.db "SELECT COUNT(*) FROM queries;"</code></li>
      <li>Service logs: <code>journalctl -u pihole-analytics-* --since "1 hour ago"</code></li>
    </ul>
  </div>
  <div class="footer">Pi-hole Analytics · Error recovery mode</div>
</div></body></html>"""


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--period', choices=['daily', 'weekly', 'monthly'], default='daily')
    p.add_argument('--start_ts', type=int, help='Start timestamp for custom range')
    p.add_argument('--end_ts', type=int, help='End timestamp for custom range')
    p.add_argument('--start_date', type=str, help='Start date (YYYY-MM-DD) for custom range')
    p.add_argument('--end_date', type=str, help='End date (YYYY-MM-DD) for custom range')
    args = p.parse_args()

    try:
        send_report(period=args.period, start_ts=args.start_ts, end_ts=args.end_ts, report_start_date=args.start_date, report_end_date=args.end_date)
    except Exception as e:
        log.error(f"Unexpected error: {e}")
        try:
            cfg = load_config()
            actual_start_date, actual_end_date = _get_dates_from_params(args.period, args.start_ts, args.end_ts, args.start_date, args.end_date)
            html = build_error_report_html(f"{actual_start_date} – {actual_end_date}", args.period, f"Critical: {e}")
            ecfg = cfg['email']
            msg  = MIMEMultipart('alternative')
            msg['Subject'] = f"{ecfg['subject_prefix']} 🚨 CRITICAL ERROR — {actual_end_date}"
            msg['From']    = ecfg['sender_email']
            msg['To']      = ', '.join(ecfg['recipient_emails'])
            msg.attach(MIMEText(html, 'html'))
            with smtplib.SMTP(ecfg['smtp_server'], ecfg['smtp_port']) as smtp:
                smtp.starttls()
                smtp.login(ecfg['sender_email'], ecfg['sender_password'])
                smtp.sendmail(ecfg['sender_email'], ecfg['recipient_emails'], msg.as_string())
        except Exception as email_err:
            log.error(f"Failed to send emergency error email: {email_err}")
        exit(0)
