"""
Centralised configuration loader for Pi-hole Analytics.

All scripts import load_config() from here so there is one definition,
one CONFIG_PATH, and one place to add validation.

Online category rules:
    downloader.py may save a categories_online.yaml into the config/ directory.
    load_config() auto-merges it on every load — online rules supplement local
    rules, they never override them (local always wins on key conflicts).
"""

from pathlib import Path
import yaml

# Load a .env file at the project root if present (dev convenience).
# This never overrides real environment variables already set.
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(Path(__file__).resolve().parents[2] / '.env', override=False)
except ImportError:
    pass  # python-dotenv is optional at runtime

# Config file is always at  <project_root>/config/config.yaml
CONFIG_PATH: Path = Path(__file__).resolve().parents[2] / 'config' / 'config.yaml'

# Downloaded by downloader.py when rules_update_url is set
_ONLINE_CATEGORIES_PATH: Path = CONFIG_PATH.parent / 'categories_online.yaml'

# Required top-level keys that must be present in config.yaml
_REQUIRED_KEYS = ('pihole', 'email', 'clients', 'categories', 'reporting', 'dashboard')


def _merge_online_categories(local_cats: dict, online_path: Path) -> dict:
    """
    Deep-merge online category rules into local ones.
    Local rules always take priority:
      - For existing categories: local keywords/domains are kept first;
        online adds any entries not already present.
      - New categories from online are appended after all local ones.
    Returns the merged dict (local_cats is mutated in-place and returned).
    """
    try:
        with open(online_path) as f:
            online = yaml.safe_load(f) or {}
    except Exception:
        return local_cats  # non-fatal: silently ignore unreadable file

    if not isinstance(online, dict):
        return local_cats

    for cat, rules in online.items():
        if not isinstance(rules, dict):
            continue
        if cat not in local_cats:
            # Brand-new category from online — add it
            local_cats[cat] = rules
        else:
            # Merge keywords and domains without duplicates; local entries stay first
            local = local_cats[cat]
            local_kw  = set(local.get('keywords', []))
            local_dom = set(local.get('domains',  []))
            extra_kw  = [k for k in rules.get('keywords', []) if k not in local_kw]
            extra_dom = [d for d in rules.get('domains',  []) if d not in local_dom]
            if extra_kw:
                local.setdefault('keywords', []).extend(extra_kw)
            if extra_dom:
                local.setdefault('domains', []).extend(extra_dom)

    return local_cats


def load_config(path: Path = None) -> dict:
    """
    Load and return the YAML configuration.

    Args:
        path: Override the default CONFIG_PATH (useful for tests).

    Raises:
        FileNotFoundError: If the config file does not exist.
        KeyError: If a required top-level key is missing.
    """
    p = path or CONFIG_PATH
    with open(p) as f:
        cfg = yaml.safe_load(f)

    # Validate that the skeleton is present so callers get a clear error
    # instead of a confusing KeyError deep in business logic.
    for key in _REQUIRED_KEYS:
        if key not in cfg:
            raise KeyError(
                f"config.yaml is missing required section '{key}'. "
                f"Check {p} against the example config."
            )

    # Normalise optional sections that YAML parses as None when the key exists
    # but has no child entries (e.g. "client_macs:" with no indented values).
    for optional in ('client_macs', 'client_hostnames'):
        if cfg.get(optional) is None:
            cfg[optional] = {}

    # Normalise excluded_devices to a list of lowercase strings
    excluded = cfg.get('excluded_devices') or []
    cfg['excluded_devices'] = [str(s).lower() for s in excluded if s]

    # Merge online category rules if downloader.py has fetched them
    if _ONLINE_CATEGORIES_PATH.exists():
        _merge_online_categories(cfg['categories'], _ONLINE_CATEGORIES_PATH)

    return cfg
