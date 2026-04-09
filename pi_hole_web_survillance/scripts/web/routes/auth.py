"""
Auth blueprint — /login and /logout routes.
"""

from flask import Blueprint, render_template_string, request, session, redirect, current_app

from scripts.web.templates import LOGIN_HTML
from scripts.web.extensions import limiter

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    error = ''
    if request.method == 'POST':
        password = current_app.config.get('DASHBOARD_PASSWORD', 'summit12')
        if request.form.get('password') == password:
            session['auth'] = True
            return redirect('/')
        error = 'Incorrect password. Try again.'
    return render_template_string(LOGIN_HTML, error=error)


@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect('/login')
