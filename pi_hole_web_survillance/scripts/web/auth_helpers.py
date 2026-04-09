"""
Shared auth helpers used by all route blueprints.

Using current_app / session avoids the module-level injection pattern that
previously required app.py to monkey-patch blueprint globals after import.
"""
from flask import current_app, session, redirect


def _require_auth():
    """Return a redirect response if the request is not authenticated, else None.

    When TESTING is True in app.config the check is skipped so tests don't
    need to set up a session.
    """
    if current_app.config.get('TESTING'):
        return None
    if not session.get('auth'):
        return redirect('/login')
    return None
