"""
Shared display constants used by both reporter.py (Python HTML) and
dashboard.py (injected into the JavaScript template).

Single source of truth for category colours and icons — update here and
both the email reports and the web dashboard stay in sync.
"""

# Maps category name → emoji used in HTML reports and dashboard badges
CATEGORY_ICONS: dict[str, str] = {
    'streaming':    '🎬',
    'social_media': '📱',
    'gaming':       '🎮',
    'educational':  '📚',
    'news':         '📰',
    'shopping':     '🛒',
    'tech':         '💻',
    'adult':        '🔞',
    'ads_tracking': '📊',
    'smart_home':   '🏠',
    'other':        '🌐',
}

# Maps category name → hex colour used for badges, chart segments, and bars
CATEGORY_COLORS: dict[str, str] = {
    'streaming':    '#e50914',
    'social_media': '#1877f2',
    'gaming':       '#6441a5',
    'educational':  '#27ae60',
    'news':         '#2980b9',
    'shopping':     '#ff9900',
    'tech':         '#00b4d8',
    'adult':        '#e74c3c',
    'ads_tracking': '#95a5a6',
    'smart_home':   '#f39c12',
    'other':        '#7f8c8d',
}

# Default colour/icon for categories not in the maps above
DEFAULT_COLOR = '#7f8c8d'
DEFAULT_ICON  = '🌐'

# Alert categories — always flagged if any queries found
ALERT_CATEGORIES: set = {'adult', 'vpn_proxy', 'crypto'}

# Warning categories — flagged when queries exceed the threshold
WATCH_CATEGORIES: dict = {
    'social_media': 900,
    'gaming':       1500,
    'streaming':    3000,
}

# Fallback device exclusions used when config is unavailable.
# The authoritative list lives in config.yaml under `excluded_devices`.
SKIP_DEVICE_NAMES: set = {
    'pi.hole', 'tp-link', 'tplink', 'router', 'gateway',
    'switch', 'access-point', 'accesspoint',
}


def is_excluded_device(name: str, ip: str, cfg: dict = None) -> bool:
    """Return True if a device should be hidden from all views.

    Checks against config.yaml `excluded_devices` (preferred) then falls
    back to the hardcoded SKIP_DEVICE_NAMES set.
    """
    needle = (name or ip or '').lower()
    patterns = cfg.get('excluded_devices', []) if cfg else []
    exclusions = patterns if patterns else SKIP_DEVICE_NAMES
    return any(s in needle for s in exclusions)
