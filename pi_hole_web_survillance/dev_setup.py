#!/usr/bin/env python3
"""
Pi-hole Analytics — Developer Setup

Copies config/config.example.yaml → config/config.yaml and walks you through
filling in the required values interactively.

Run once after cloning:
    python3 dev_setup.py
"""
import shutil
import sys
from pathlib import Path

ROOT       = Path(__file__).parent
EXAMPLE    = ROOT / 'config' / 'config.example.yaml'
CONFIG     = ROOT / 'config' / 'config.yaml'
ENV_FILE   = ROOT / '.env'

# Placeholders in the example file and what to ask the user
PROMPTS = [
    ('YOUR_PIHOLE_API_TOKEN',       'Pi-hole API token (v5 — leave blank for v6)',    False),
    ('YOUR_PIHOLE_PASSWORD',        'Pi-hole web interface password (v6)',             False),
    ('YOUR_GMAIL_APP_PASSWORD',     'Gmail App Password for email reports',            False),
    ('you@gmail.com',               'Sender email address (must match Gmail account)', True),
    ('you@example.com',             'Recipient email address',                         True),
    ('YOUR_GEMINI_API_KEY',         'Gemini API key (optional — leave blank to skip)', False),
    ('CHOOSE_A_DASHBOARD_PASSWORD', 'Dashboard web UI password',                       True),
    ('YOUR_PI_IP',                  "Pi's IP address (e.g. 192.168.1.100)",            True),
]


def bold(text: str) -> str:
    return f'\033[1m{text}\033[0m'


def ask(prompt: str, required: bool) -> str:
    suffix = ' (required): ' if required else ' (press Enter to skip): '
    while True:
        value = input(f'  {prompt}{suffix}').strip()
        if value or not required:
            return value
        print('  ⚠  This field is required.')


def main() -> None:
    print()
    print(bold('Pi-hole Analytics — Developer Setup'))
    print('─' * 50)

    # ── Step 1: copy example → config ────────────────────────────────────────
    if CONFIG.exists():
        overwrite = input(f'\n  config/config.yaml already exists. Overwrite? [y/N] ').strip().lower()
        if overwrite != 'y':
            print('  Keeping existing config.yaml.')
            return
    shutil.copy(EXAMPLE, CONFIG)
    print(f'\n  ✅  Copied {EXAMPLE.name} → {CONFIG.name}')

    # ── Step 2: collect values ────────────────────────────────────────────────
    print('\n  Fill in the values below (or press Enter to skip optional fields).\n')
    replacements: dict[str, str] = {}
    for placeholder, prompt, required in PROMPTS:
        value = ask(prompt, required)
        if value:
            replacements[placeholder] = value

    # ── Step 3: apply substitutions ──────────────────────────────────────────
    content = CONFIG.read_text()
    for placeholder, value in replacements.items():
        content = content.replace(placeholder, value, 1)
    CONFIG.write_text(content)
    CONFIG.chmod(0o600)

    # ── Step 4: install package (editable) ───────────────────────────────────
    print('\n  Installing package in editable mode...')
    import subprocess
    result = subprocess.run(
        [sys.executable, '-m', 'pip', 'install', '-e', '.', '-q'],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print('  ✅  pip install -e . succeeded')
    else:
        print(f'  ⚠   pip install failed — run manually:\n      pip install -e .')

    # ── Done ──────────────────────────────────────────────────────────────────
    print()
    print(bold('Setup complete.'))
    print(f'  Config  : {CONFIG}')
    print( '  Test    : python3 -m pytest tests/ -q')
    print( '  Run     : python3 scripts/web/app.py')
    print()


if __name__ == '__main__':
    main()
