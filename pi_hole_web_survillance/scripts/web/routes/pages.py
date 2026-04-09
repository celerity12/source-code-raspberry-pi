"""
Pages blueprint — / (index) and /device routes.
"""

from flask import Blueprint, render_template_string

from scripts.web.templates import DASHBOARD_HTML, DEVICE_DETAIL_HTML
from scripts.core.config import load_config
from scripts.web.auth_helpers import _require_auth

pages_bp = Blueprint('pages', __name__)


@pages_bp.route('/')
def index():
    redir = _require_auth()
    if redir:
        return redir

    cfg = load_config()
    day_start_hour = cfg.get('dashboard', {}).get('day_start_hour', 5)
    return render_template_string(DASHBOARD_HTML, day_start_hour=day_start_hour)


@pages_bp.route('/device')
def device_detail():
    redir = _require_auth()
    if redir:
        return redir
    return render_template_string(DEVICE_DETAIL_HTML)
