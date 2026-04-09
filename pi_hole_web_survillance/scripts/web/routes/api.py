"""
API blueprint — all /api/* routes.
"""
from flask import Blueprint, jsonify, request
from datetime import datetime
import threading

import sys
from pathlib import Path

from scripts.data import analytics as A
from scripts.core.config import load_config
from scripts.core import constants as _C
from scripts.core.constants import is_excluded_device
from scripts.web.auth_helpers import _require_auth
from scripts.core.pihole import pihole_block as _pihole_block

api_bp = Blueprint('api', __name__)

@api_bp.route('/api/summary')
def api_summary():
    date     = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date')
    start_ts = request.args.get('start_ts')
    end_ts   = request.args.get('end_ts')
    
    # Handle custom time ranges
    if start_ts and end_ts:
        start_date = datetime.fromtimestamp(int(start_ts)).strftime('%Y-%m-%d')
        end_date = datetime.fromtimestamp(int(end_ts)).strftime('%Y-%m-%d')
        date = start_date
    
    return jsonify(A.network_summary(date, end_date=end_date))


@api_bp.route('/api/compare')
def api_compare():
    date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    start_ts = request.args.get('start_ts')
    end_ts   = request.args.get('end_ts')
    
    # Handle custom time ranges - use end date for comparison
    if start_ts and end_ts:
        date = datetime.fromtimestamp(int(end_ts)).strftime('%Y-%m-%d')
    
    return jsonify(A.compare_periods(date))


@api_bp.route('/api/clients')
def api_clients():
    date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    start_ts = request.args.get('start_ts')
    end_ts   = request.args.get('end_ts')
    
    # Handle custom time ranges - use end date for comparison
    if start_ts and end_ts:
        date = datetime.fromtimestamp(int(end_ts)).strftime('%Y-%m-%d')
    
    return jsonify(A.client_compare(date))


@api_bp.route('/api/devices')
def api_devices():
    """Clients enriched with MAC, hostname, device_type from device_registry.
    Excluded devices (per config.yaml `excluded_devices`) are filtered out.
    """
    date     = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date')
    cfg      = load_config()
    clients  = A.client_range_summary(date, end_date or date)
    conn = A.get_conn()
    registry = {
        row['last_ip']: dict(row)
        for row in conn.execute(
            "SELECT last_ip, mac, hostname, device_type, custom_name FROM device_registry"
        ).fetchall()
    }
    conn.close()
    result = []
    for c in clients:
        ip  = c.get('client_ip', '')
        reg = registry.get(ip, {})
        c['mac']         = reg.get('mac', '')
        c['hostname']    = reg.get('hostname', '')
        c['device_type'] = reg.get('device_type', '')
        c['custom_name'] = reg.get('custom_name', '')
        name = c.get('client_name') or c['hostname'] or ip
        if not is_excluded_device(name, ip, cfg):
            result.append(c)
    return jsonify(result)


@api_bp.route('/api/categories')
def api_categories():
    date     = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date')
    start_ts = request.args.get('start_ts')
    end_ts   = request.args.get('end_ts')
    client   = request.args.get('client')
    cfg      = load_config()
    
    # Handle custom time ranges
    if start_ts and end_ts:
        start_date = datetime.fromtimestamp(int(start_ts)).strftime('%Y-%m-%d')
        end_date = datetime.fromtimestamp(int(end_ts)).strftime('%Y-%m-%d')
        date = start_date
    
    return jsonify(A.category_breakdown(date, end_date=end_date, client_ip=client, cfg=cfg))


@api_bp.route('/api/domains')
def api_domains():
    date     = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date')
    start_ts = request.args.get('start_ts')
    end_ts   = request.args.get('end_ts')
    try:
        limit = max(1, min(int(request.args.get('limit', 15)), 100))
    except (ValueError, TypeError):
        limit = 15
    client = request.args.get('client')
    cfg      = load_config()
    
    # Handle custom time ranges
    if start_ts and end_ts:
        start_date = datetime.fromtimestamp(int(start_ts)).strftime('%Y-%m-%d')
        end_date = datetime.fromtimestamp(int(end_ts)).strftime('%Y-%m-%d')
        date = start_date
    
    return jsonify(A.top_domains(date, end_date=end_date, limit=limit, client_ip=client, cfg=cfg))


@api_bp.route('/api/hourly')
def api_hourly():
    date     = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date')
    start_ts = request.args.get('start_ts')
    end_ts   = request.args.get('end_ts')
    client   = request.args.get('client')
    cfg      = load_config()
    
    # Handle custom time ranges - use start date for hourly data
    if start_ts and end_ts:
        date = datetime.fromtimestamp(int(start_ts)).strftime('%Y-%m-%d')
    
    if client:
        return jsonify(A.client_hourly(client, date))
    return jsonify(A.all_clients_hourly(date, cfg=cfg))


@api_bp.route('/api/trend')
def api_trend():
    try:
        days = max(1, min(int(request.args.get('days', 7)), 365))
    except (ValueError, TypeError):
        days = 7
    client = request.args.get('client')
    return jsonify(A.daily_trend(days, client_ip=client))


@api_bp.route('/api/new_domains')
def api_new_domains():
    date     = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date')
    start_ts = request.args.get('start_ts')
    end_ts   = request.args.get('end_ts')
    cfg      = load_config()
    
    # Handle custom time ranges
    if start_ts and end_ts:
        start_date = datetime.fromtimestamp(int(start_ts)).strftime('%Y-%m-%d')
        end_date = datetime.fromtimestamp(int(end_ts)).strftime('%Y-%m-%d')
        date = start_date
    
    return jsonify(A.new_domains(date, end_date=end_date, cfg=cfg))


# ── New routes ────────────────────────────────────────────────────────────────

@api_bp.route('/api/blocking')
def api_blocking():
    """Pi-hole blocking effectiveness summary."""
    date     = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date')
    start_ts = request.args.get('start_ts')
    end_ts   = request.args.get('end_ts')
    
    # Handle custom time ranges
    if start_ts and end_ts:
        start_date = datetime.fromtimestamp(int(start_ts)).strftime('%Y-%m-%d')
        end_date = datetime.fromtimestamp(int(end_ts)).strftime('%Y-%m-%d')
        date = start_date
    
    return jsonify(A.blocked_queries_summary(date, end_date=end_date))


@api_bp.route('/api/category_detail')
def api_category_detail():
    """Top domains for a specific category — used by the drill-down modal."""
    date     = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date')
    start_ts = request.args.get('start_ts')
    end_ts   = request.args.get('end_ts')
    category = request.args.get('category', '')
    client   = request.args.get('client')
    try:
        limit = max(1, min(int(request.args.get('limit', 20)), 100))
    except (ValueError, TypeError):
        limit = 20
    
    # Handle custom time ranges
    if start_ts and end_ts:
        start_date = datetime.fromtimestamp(int(start_ts)).strftime('%Y-%m-%d')
        end_date = datetime.fromtimestamp(int(end_ts)).strftime('%Y-%m-%d')
        date = start_date
    
    if not category:
        return jsonify([])
    return jsonify(A.top_domains_by_category(date, category, end_date=end_date, limit=limit, client_ip=client))


@api_bp.route('/api/alerts')
def api_alerts():
    """
    Returns structured alert objects for the banner and attention cards.
    Levels: 'critical' (adult, vpn, crypto) and 'warning' (excessive social/gaming/streaming).
    """
    date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    start_ts = request.args.get('start_ts')
    end_ts   = request.args.get('end_ts')
    
    # Handle custom time ranges - use start date for alerts
    if start_ts and end_ts:
        date = datetime.fromtimestamp(int(start_ts)).strftime('%Y-%m-%d')
    
    conn = A.get_conn()

    critical = []
    warnings = []

    def load_top_sites(category, limit=4):
        return [f"{row['domain']} ({int(row['queries']):,})"
                for row in A.top_domains_by_category(date, category, limit=limit, conn=conn)]

    def load_devices(category, limit=4):
        rows = conn.execute(
            "SELECT DISTINCT COALESCE(client_name, client_ip) AS name"
            " FROM queries WHERE date = ? AND category = ? ORDER BY name LIMIT ?",
            (date, category, limit)
        ).fetchall()
        return [row['name'] for row in rows]

    totals = {row['category']: row for row in A.category_breakdown(date, conn=conn)}

    def add_critical(category, title, icon, description):
        row = totals.get(category)
        if not row or row['queries'] <= 0:
            return
        top_domains = load_top_sites(category, limit=5)
        devices = load_devices(category, limit=4)
        critical.append({
            'category':    category,
            'level':       'critical',
            'icon':        icon,
            'title':       title,
            'short':       f"{int(row['queries']):,} requests detected",
            'description': description,
            'queries':     int(row['queries']),
            'devices':     ', '.join(devices) or 'Unknown',
            'top_domains': top_domains,
        })

    add_critical('adult', 'Adult Content', '🔞', 'Adult / explicit content was accessed on your network today.')
    add_critical('vpn_proxy', 'VPN / Proxy Usage', '🔒', 'VPN or proxy services were used — these can bypass network filters.')
    add_critical('crypto', 'Crypto / Blockchain', '₿', 'Cryptocurrency or blockchain activity detected on your network.')

    icons = {'social_media': '📱', 'gaming': '🎮', 'streaming': '🎬'}
    titles = {
        'social_media': 'High Social Media Usage',
        'gaming': 'High Gaming Usage',
        'streaming': 'High Streaming Usage',
    }
    descriptions = {
        'social_media': 'Social media traffic is above the configured watch threshold.',
        'gaming': 'Gaming traffic is above the configured watch threshold.',
        'streaming': 'Streaming traffic is above the configured watch threshold.',
    }

    # Add warnings for categories that exceed watch thresholds.
    for category, threshold in _C.WATCH_CATEGORIES.items():
        row = totals.get(category)
        if row and row['queries'] >= threshold:
            warnings.append({
                'category':    category,
                'level':       'warning',
                'icon':        icons.get(category, '⚠️'),
                'title':       titles.get(category, category.replace('_',' ').title()),
                'short':       f"{int(row['queries']):,} requests across {row['unique_domains']:,} sites",
                'description': descriptions.get(category, f"{category.replace('_',' ').title()} traffic is higher than expected."),
                'queries':     int(row['queries']),
                'devices':     ', '.join(load_devices(category, limit=4)) or 'Unknown',
                'top_domains': load_top_sites(category, limit=5),
            })

    # Also include client-specific alerts for heavy usage when category thresholds were not already triggered.
    seen_categories = {item['category'] for item in warnings}
    excessive = A.excessive_social_media_check(date, threshold_minutes=60, conn=conn)
    for usage in excessive:
        category = usage['category']
        if category in seen_categories:
            continue
        warnings.append({
            'category':    category,
            'level':       'warning',
            'icon':        icons.get(category, '⚠️'),
            'title':       titles.get(category, category.replace('_',' ').title()),
            'short':       f"{usage['queries']:,} requests, {usage['domains']} sites",
            'description': f"{usage['client_name'] or usage['client_ip']} generated heavy {category.replace('_',' ')} traffic today.",
            'queries':     int(usage['queries']),
            'devices':     usage['client_name'] or usage['client_ip'] or 'Unknown',
            'top_domains': load_top_sites(category, limit=5),
        })
        seen_categories.add(category)

    conn.close()
    return jsonify({'critical': critical, 'warnings': warnings})


@api_bp.route('/api/blocked_domains')
def api_blocked_domains():
    redir = _require_auth()
    if redir: return redir
    return jsonify(A.get_blocked_domains())


@api_bp.route('/api/block_domain', methods=['POST'])
def api_block_domain():
    redir = _require_auth()
    if redir: return redir
    data     = request.get_json(silent=True) or {}
    domain   = (data.get('domain') or '').strip().lower()
    category = data.get('category', '')
    if not domain:
        return jsonify({'status': 'error', 'message': 'Domain required'}), 400

    A.add_blocked_domain(domain, category)

    cfg     = load_config()
    pihole_ok = _pihole_block(domain, True, cfg)

    return jsonify({
        'status':    'blocked',
        'domain':    domain,
        'pihole_ok': pihole_ok,
        'message':   f'{domain} blocked' + ('' if pihole_ok else ' (saved locally; Pi-hole API call failed)'),
    })


@api_bp.route('/api/unblock_domain', methods=['POST'])
def api_unblock_domain():
    redir = _require_auth()
    if redir: return redir
    data   = request.get_json(silent=True) or {}
    domain = (data.get('domain') or '').strip().lower()
    if not domain:
        return jsonify({'status': 'error', 'message': 'Domain required'}), 400

    A.remove_blocked_domain(domain)

    cfg       = load_config()
    pihole_ok = _pihole_block(domain, False, cfg)

    return jsonify({
        'status':    'unblocked',
        'domain':    domain,
        'pihole_ok': pihole_ok,
        'message':   f'{domain} unblocked' + ('' if pihole_ok else ' (removed locally; Pi-hole API call failed)'),
    })


@api_bp.route('/api/send_report', methods=['POST'])
def api_send_report():
    """Trigger an email report in a background thread. Non-blocking."""
    data   = request.get_json(silent=True) or {}
    period = data.get('period', 'daily')
    if period not in ('daily', 'weekly', 'monthly'):
        return jsonify({'status': 'error', 'message': 'Invalid period. Use daily, weekly, or monthly.'}), 400

    from scripts.core import reporter as R

    def _send():
        try:
            R.send_report(period)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Background report failed: {e}")

    t = threading.Thread(target=_send, daemon=True)
    t.start()

    period_label = period.capitalize()
    return jsonify({
        'status':  'queued',
        'message': f'{period_label} report is being generated and will be emailed shortly.',
    })


from scripts.core import health as H


@api_bp.route('/api/health')
def api_health():
    redir = _require_auth()
    if redir: return redir
    cfg = load_config()
    return jsonify(H.collect_all(cfg))


@api_bp.route('/api/blocked_top')
def api_blocked_top():
    redir = _require_auth()
    if redir: return redir
    date     = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date')
    start_ts = request.args.get('start_ts')
    end_ts   = request.args.get('end_ts')
    
    # Handle custom time ranges
    if start_ts and end_ts:
        start_date = datetime.fromtimestamp(int(start_ts)).strftime('%Y-%m-%d')
        end_date = datetime.fromtimestamp(int(end_ts)).strftime('%Y-%m-%d')
        date = start_date
    
    return jsonify(A.top_blocked_domains(date, end_date=end_date))


@api_bp.route('/api/ai_summary_stored', methods=['GET'])
def api_ai_summary_stored():
    """Return the best stored AI summary for the given period (no Gemini call)."""
    redir = _require_auth()
    if redir: return redir
    from scripts.core import summarizer as S
    period = request.args.get('period', 'daily')
    if period not in ('daily', 'weekly', 'monthly'):
        return jsonify({'error': 'Invalid period'}), 400
    row = S.get_latest_summary(period)
    if not row:
        return jsonify({}), 204
    return jsonify({
        'summary':      row['summary_text'],
        'period':       row['period'],
        'start':        row['start_date'],
        'end':          row['end_date'],
        'model':        row['model'],
        'generated_at': row['generated_at'],
        'run_type':     row.get('run_type', 'ondemand'),
    })


@api_bp.route('/api/ai_eta', methods=['GET'])
def api_ai_eta():
    """Return ETA info for the AI summary generation so the UI can show a countdown.

    Returns: {num_devices, num_calls, delay_s, eta_seconds, rpm}
    """
    redir = _require_auth()
    if redir: return redir

    from scripts.core import summarizer as S
    period = request.args.get('period', 'daily')
    start_ts = request.args.get('start_ts')
    end_ts = request.args.get('end_ts')
    
    cfg        = load_config()
    gemini_cfg = cfg.get('gemini', {})
    rpm        = int(gemini_cfg.get('rate_limit_rpm', 10))

    try:
        data       = S.collect_data(period, start_ts=start_ts, end_ts=end_ts)
        num_dev    = len(data.get('devices', []))
        num_calls  = 1 + num_dev
        delay_s    = S.calc_call_delay(rpm)
        eta_s      = round((num_calls - 1) * delay_s)
        return jsonify({
            'num_devices': num_dev,
            'num_calls':   num_calls,
            'delay_s':     delay_s,
            'eta_seconds': eta_s,
            'rpm':         rpm,
        })
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


@api_bp.route('/api/ai_summary', methods=['POST'])
def api_ai_summary():
    """Generate an AI summary on-demand via Gemini, store it, and return it.

    Flow:
      1. Call Gemini live → store result → return {source: 'live', ...}
      2. On 429 rate-limit → fall back to last stored result → return {source: 'cached', cache_notice: ...}
      3. On 429 with no stored result → return 429 with quota-exhausted message
      4. On missing API key → return 400
      5. On other errors → return 500
    """
    redir = _require_auth()
    if redir: return redir
    data   = request.get_json(silent=True) or {}
    period = data.get('period', 'daily')
    start_ts = data.get('start_ts')
    end_ts = data.get('end_ts')
    
    if period not in ('daily', 'weekly', 'monthly') and not (start_ts and end_ts):
        return jsonify({'error': 'Invalid period or missing start_ts/end_ts'}), 400

    from scripts.core import summarizer as S
    import logging
    _log = logging.getLogger(__name__)

    cfg        = load_config()
    gemini_cfg = cfg.get('gemini', {})
    api_key    = gemini_cfg.get('api_key', '')
    model      = gemini_cfg.get('model', 'gemini-2.0-flash')

    if not api_key or api_key.startswith('YOUR_'):
        return jsonify({'error': 'Gemini API key not configured in config.yaml'}), 400

    # ── Attempt live generation (single API call) ─────────────────────────────
    try:
        query_data   = S.collect_data(period, start_ts=start_ts, end_ts=end_ts)
        summary_text = S.call_gemini(S.build_prompt(query_data), api_key, model)
        S.store_summary(period, query_data['start_date'], query_data['end_date'],
                        summary_text, model, run_type='ondemand')
        return jsonify({
            'source':       'live',
            'summary':      summary_text,
            'period':       period,
            'start':        query_data['start_date'],
            'end':          query_data['end_date'],
            'model':        model,
            'generated_at': None,   # just now
        })

    except S.GeminiRateLimitError:
        # ── Quota hit — show best available stored result ─────────────────────
        # Priority: scheduled (5 AM) → ondemand (last manual run) → error
        row = S.get_latest_summary(period)
        if row:
            src_label = 'scheduled (5 AM)' if row.get('run_type') == 'scheduled' else 'last on-demand run'
            _log.warning("Gemini 429 — serving %s summary from %s", src_label, row['generated_at'])
            return jsonify({
                'source':       'cached',
                'summary':      row['summary_text'],
                'period':       row['period'],
                'start':        row['start_date'],
                'end':          row['end_date'],
                'model':        row['model'],
                'generated_at': row['generated_at'],
                'run_type':     row.get('run_type', 'ondemand'),
                'cache_notice': (
                    f"Quota exceeded — showing {src_label} result from {row['generated_at']}."
                ),
            })
        # No cache at all
        return jsonify({
            'error': (
                '🚫 Quota exhausted and no stored summary available. '
                'The scheduled 5 AM result will appear here tomorrow. '
                'Or wait a minute and try again.'
            )
        }), 429

    except Exception as exc:
        _log.error("AI summary failed: %s", exc)
        return jsonify({'error': str(exc)}), 500


# ── Device Detail APIs ────────────────────────────────────────────────────────

@api_bp.route('/api/device_detail')
def api_device_detail():
    redir = _require_auth()
    if redir: return redir
    ip   = request.args.get('ip', '').strip()
    date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    if not ip:
        return jsonify({'error': 'ip required'}), 400
    summary = A.device_summary(ip, date)
    cats    = A.category_breakdown(date, client_ip=ip)
    return jsonify({'summary': summary, 'categories': cats})


@api_bp.route('/api/device_hourly')
def api_device_hourly():
    redir = _require_auth()
    if redir: return redir
    ip   = request.args.get('ip', '').strip()
    date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    if not ip:
        return jsonify([])
    return jsonify(A.device_hourly_stats(ip, date))


@api_bp.route('/api/device_hourly_categories')
def api_device_hourly_categories():
    redir = _require_auth()
    if redir: return redir
    ip   = request.args.get('ip', '').strip()
    date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    if not ip:
        return jsonify([])
    return jsonify(A.device_hourly_by_category(ip, date))


@api_bp.route('/api/device_domains')
def api_device_domains():
    redir = _require_auth()
    if redir: return redir
    ip   = request.args.get('ip', '').strip()
    date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    try:
        limit = max(1, min(int(request.args.get('limit', 200)), 500))
    except (ValueError, TypeError):
        limit = 200
    if not ip:
        return jsonify([])
    return jsonify(A.device_domains_full(ip, date, limit=limit))


@api_bp.route('/api/device_flagged_category')
def api_device_flagged_category():
    redir = _require_auth()
    if redir: return redir
    ip       = request.args.get('ip', '').strip()
    date     = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    category = request.args.get('category', '').strip()
    if not ip or not category:
        return jsonify({'error': 'ip and category required'}), 400
    return jsonify(A.device_flagged_category_detail(ip, date, category))


# ── MCP-ready endpoints ───────────────────────────────────────────────────────
# These are designed for programmatic/LLM consumption — rich, self-contained
# responses that a future MCP server can surface as tools.

@api_bp.route('/api/stats')
def api_stats():
    """Single-call network snapshot — all key metrics for a date.
    MCP use: 'What is happening on my network right now?'
    """
    redir = _require_auth()
    if redir: return redir
    date     = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date')
    conn     = A.get_conn()
    summary  = A.network_summary(date, end_date=end_date, conn=conn)
    cats     = A.category_breakdown(date, end_date=end_date, conn=conn)
    blocked  = A.blocked_queries_summary(date, end_date=end_date, conn=conn)
    top_dom  = A.top_domains(date, end_date=end_date, limit=5, conn=conn)
    trend    = A.daily_trend(days=7, conn=conn)
    conn.close()
    return jsonify({
        'date':          date,
        'end_date':      end_date,
        'summary':       summary,
        'categories':    [dict(r) for r in cats],
        'blocked':       blocked,
        'top_domains':   top_dom,
        'trend_7d':      trend,
    })


@api_bp.route('/api/categorization_stats')
def api_categorization_stats():
    """How many domains are categorized vs uncategorized for a date.
    MCP use: 'How well is the categorization engine working?'
    """
    redir = _require_auth()
    if redir: return redir
    date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    return jsonify(A.categorization_stats(date))


@api_bp.route('/api/uncategorized_domains')
def api_uncategorized_domains():
    """Domains that could not be categorized (category = 'other').
    MCP use: 'What domains are we missing category rules for?'
    """
    redir = _require_auth()
    if redir: return redir
    date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    try:
        limit = max(1, min(int(request.args.get('limit', 20)), 200))
    except (ValueError, TypeError):
        limit = 20
    return jsonify(A.uncategorized_domains(date, limit=limit))


@api_bp.route('/api/top_by_category')
def api_top_by_category():
    """Top domains for a specific category, optionally filtered by device.
    MCP use: 'What streaming sites is John's iPhone visiting?'
    """
    redir = _require_auth()
    if redir: return redir
    date     = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date')
    category = request.args.get('category', '').strip()
    ip       = request.args.get('ip', '').strip() or None
    try:
        limit = max(1, min(int(request.args.get('limit', 10)), 100))
    except (ValueError, TypeError):
        limit = 10
    if not category:
        return jsonify({'error': 'category required'}), 400
    return jsonify(A.top_domains_by_category(date, category, end_date=end_date, limit=limit, client_ip=ip))


@api_bp.route('/api/client_category_usage')
def api_client_category_usage():
    """Category breakdown for one client or all clients.
    MCP use: 'What categories is a specific device hitting the most?'
    """
    redir = _require_auth()
    if redir: return redir
    date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    ip   = request.args.get('ip', '').strip() or None
    return jsonify(A.client_category_usage(date, client_ip=ip))


@api_bp.route('/api/excessive_usage')
def api_excessive_usage():
    """Clients exceeding usage thresholds for social media, streaming, gaming.
    MCP use: 'Who is spending too much time on social media today?'
    """
    redir = _require_auth()
    if redir: return redir
    date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    try:
        threshold = max(1, int(request.args.get('threshold_minutes', 60)))
    except (ValueError, TypeError):
        threshold = 60
    return jsonify(A.excessive_social_media_check(date, threshold_minutes=threshold))


@api_bp.route('/api/blocked_summary')
def api_blocked_summary():
    """Blocked vs allowed query counts with per-status breakdown.
    MCP use: 'How effective is Pi-hole blocking today?'
    """
    redir = _require_auth()
    if redir: return redir
    date     = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date')
    return jsonify(A.blocked_queries_summary(date, end_date=end_date))


@api_bp.route('/api/date_range')
def api_date_range():
    """Per-device summary over an arbitrary date range.
    MCP use: 'Show me network activity for the past week by device.'
    """
    redir = _require_auth()
    if redir: return redir
    start_date = request.args.get('start_date', '')
    end_date   = request.args.get('end_date', '')
    if not start_date or not end_date:
        return jsonify({'error': 'start_date and end_date required (YYYY-MM-DD)'}), 400
    return jsonify(A.client_range_summary(start_date, end_date))


@api_bp.route('/api/device_registry')
def api_device_registry():
    """All known devices from the MAC registry — name, IP, type, last seen.
    MCP use: 'What devices are registered on my network?'
    """
    redir = _require_auth()
    if redir: return redir
    conn  = A.get_conn()
    rows  = conn.execute(
        "SELECT mac, last_ip, hostname, device_type, custom_name, last_seen FROM device_registry ORDER BY last_seen DESC"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@api_bp.route('/api/search')
def api_search():
    """Search domains and clients by keyword across a date.
    MCP use: 'Did anyone visit anything related to netflix today?'
    ?q=keyword  &date=YYYY-MM-DD  &limit=50
    """
    redir = _require_auth()
    if redir: return redir
    q    = request.args.get('q', '').strip()
    date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    try:
        limit = max(1, min(int(request.args.get('limit', 50)), 200))
    except (ValueError, TypeError):
        limit = 50
    if not q:
        return jsonify({'error': 'q (search term) required'}), 400
    conn  = A.get_conn()
    rows  = conn.execute("""
        SELECT domain, category,
               COALESCE(client_name, client_ip) AS client,
               client_ip,
               COUNT(*) AS queries,
               SUM(CASE WHEN status IN (1,4,5,6,7,8,9,10,11) THEN 1 ELSE 0 END) AS blocked
        FROM queries
        WHERE date = ? AND domain LIKE ?
        GROUP BY domain, client_ip
        ORDER BY queries DESC
        LIMIT ?
    """, (date, f'%{q}%', limit)).fetchall()
    conn.close()
    return jsonify({'query': q, 'date': date, 'results': [dict(r) for r in rows]})


@api_bp.route('/api/query_log')
def api_query_log():
    """Raw query log with optional filters: date, client IP, category, domain, blocked-only.
    MCP use: 'Show me the last 100 blocked queries from John's iPhone.'
    ?date=  &ip=  &category=  &domain=  &blocked=1  &limit=100
    """
    redir = _require_auth()
    if redir: return redir
    date     = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    ip       = request.args.get('ip', '').strip()
    category = request.args.get('category', '').strip()
    domain   = request.args.get('domain', '').strip()
    blocked  = request.args.get('blocked', '').strip()
    try:
        limit = max(1, min(int(request.args.get('limit', 100)), 500))
    except (ValueError, TypeError):
        limit = 100

    where  = ['date = ?']
    params = [date]
    if ip:
        where.append('client_ip = ?'); params.append(ip)
    if category:
        where.append('category = ?'); params.append(category)
    if domain:
        where.append('domain LIKE ?'); params.append(f'%{domain}%')
    if blocked == '1':
        where.append('status IN (1,4,5,6,7,8,9,10,11)')

    conn = A.get_conn()
    rows = conn.execute(f"""
        SELECT timestamp, domain, COALESCE(client_name, client_ip) AS client,
               client_ip, category, status, query_type
        FROM queries
        WHERE {' AND '.join(where)}
        ORDER BY timestamp DESC
        LIMIT ?
    """, params + [limit]).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@api_bp.route('/api/ignored_domains', methods=['GET'])
def api_ignored_domains():
    """List all ignored domains."""
    redir = _require_auth()
    if redir: return redir
    return jsonify(A.get_ignored_domains())


@api_bp.route('/api/ignore_domain', methods=['POST'])
def api_ignore_domain():
    """Add or remove a domain from the ignore list."""
    redir = _require_auth()
    if redir: return redir
    data   = request.get_json(silent=True) or {}
    domain = (data.get('domain') or '').strip().lower()
    action = data.get('action', 'ignore')   # 'ignore' | 'unignore'
    if not domain:
        return jsonify({'status': 'error', 'message': 'Domain required'}), 400
    if action == 'unignore':
        A.remove_ignored_domain(domain)
        return jsonify({'status': 'unignored', 'domain': domain})
    A.add_ignored_domain(domain)
    return jsonify({'status': 'ignored', 'domain': domain})


@api_bp.route('/api/manually_blocked')
def api_manually_blocked():
    """List all domains manually blocked via the dashboard.
    MCP use: 'What domains have been manually blocked?'
    """
    redir = _require_auth()
    if redir: return redir
    return jsonify(A.get_blocked_domains())


@api_bp.route('/api/all_clients_hourly')
def api_all_clients_hourly():
    """Hourly query counts for every active client — useful for heatmap/timeline views.
    MCP use: 'Show me per-device hourly activity for today.'
    """
    redir = _require_auth()
    if redir: return redir
    date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    cfg  = load_config()
    return jsonify(A.all_clients_hourly(date, cfg=cfg))
