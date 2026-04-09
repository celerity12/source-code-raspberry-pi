#!/usr/bin/env python3
"""
Pi-hole Analytics — Web Dashboard

Flask application factory.  Blueprints are registered in create_app() so the
app can be constructed cleanly for tests without side-effects at import time.
"""

import os
import secrets
from pathlib import Path


from flask import Flask

from scripts.core.config import load_config
from scripts.web.extensions import limiter


# ── Secret-key persistence ────────────────────────────────────────────────────

def _load_secret_key() -> bytes:
    """Return a persistent random secret key, generating one on first run.

    The key is stored in data/.secret_key (mode 0600).  Generating a fresh
    key on every startup would invalidate all existing sessions, so we persist
    it across restarts while still keeping it out of source control.
    """
    key_path = Path(__file__).resolve().parents[2] / 'data' / '.secret_key'
    try:
        key_path.parent.mkdir(parents=True, exist_ok=True)
        if key_path.exists():
            return key_path.read_bytes()
        key = secrets.token_bytes(32)
        key_path.write_bytes(key)
        key_path.chmod(0o600)
        return key
    except OSError:
        # Read-only filesystem or no permission (e.g. CI) — use ephemeral key
        return secrets.token_bytes(32)


# ── Application factory ───────────────────────────────────────────────────────

def create_app(config_overrides: dict = None) -> Flask:
    """Create and configure the Flask application.

    Args:
        config_overrides: Optional dict merged into app.config after normal
                          setup.  Intended for tests (e.g. TESTING=True,
                          DASHBOARD_PASSWORD='test').
    """
    _app = Flask(__name__)

    # Secret key — loaded from data/.secret_key, generated on first run
    _app.secret_key = _load_secret_key()

    # Load dashboard password from config.yaml at startup (not at import time)
    try:
        cfg = load_config()
        _app.config['DASHBOARD_PASSWORD'] = cfg.get('dashboard', {}).get('password', 'summit12')
    except Exception:
        _app.config['DASHBOARD_PASSWORD'] = os.environ.get('DASHBOARD_PASSWORD', 'summit12')

    if config_overrides:
        _app.config.update(config_overrides)

    # Initialise extensions
    limiter.init_app(_app)

    # Register blueprints
    from scripts.web.routes.auth import auth_bp
    from scripts.web.routes.pages import pages_bp
    from scripts.web.routes.api import api_bp
    from scripts.core import health as _H  # noqa: F401 — registers health helpers

    _app.register_blueprint(auth_bp)
    _app.register_blueprint(api_bp)
    _app.register_blueprint(pages_bp)

    return _app


# ── Module-level app instance (used by systemd / direct execution) ────────────
app = create_app()


if __name__ == '__main__':
    cfg  = load_config()
    host = cfg['dashboard'].get('host', '0.0.0.0')
    port = cfg['dashboard'].get('port', 8080)
    app.run(host=host, port=port, debug=False)
