"""
Flask extension singletons.

Defined here so app.py and route blueprints can both import the same instance
without circular imports.
"""
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Rate limiter — initialised against the Flask app in create_app()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],          # no global limit; limits are set per-route
    storage_uri="memory://",
)
