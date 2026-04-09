"""
Config loader — single source of truth for config file paths.

Each layer imports only the function it needs:

    from config.loader import load_connector, load_mcp, load_llm, load_prompts

No layer ever builds a path itself — paths live here only.
"""

from pathlib import Path
import yaml

_CONFIG_DIR = Path(__file__).parent


def _load(rel_path: str) -> dict:
    path = _CONFIG_DIR / rel_path
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {path}\n"
            f"Copy the example and fill in your values."
        )
    with open(path) as f:
        return yaml.safe_load(f) or {}


# ── Public loaders — one per config file ─────────────────────────────────────

def load_connector(name: str) -> dict:
    """Load a connector config.  name = 'pihole' | 'telegram'"""
    return _load(f"connectors/{name}.yaml")


def load_mcp() -> dict:
    """Load MCP server config."""
    return _load("mcp/server.yaml")


def load_llm() -> dict:
    """Load LLM credentials config (Gemini API key, model)."""
    return _load("llm/gemini.yaml")


def load_prompts() -> dict:
    """Load LLM prompts and watch settings (no secrets)."""
    return _load("llm/prompts.yaml")
