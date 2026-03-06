"""Configuration loader with .env file support."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.yaml"
EXAMPLE_CONFIG_PATH = PROJECT_ROOT / "config.example.yaml"
ENV_PATH = PROJECT_ROOT / ".env"


def load_dotenv() -> None:
    """Load .env file into os.environ if it exists."""
    if not ENV_PATH.exists():
        return

    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:  # Don't override existing env vars
            os.environ[key] = value


def load_config(path: Path | None = None) -> dict:
    """Load config from YAML, falling back to example config."""
    # Load .env first so env vars are available for substitution
    load_dotenv()

    path = path or CONFIG_PATH
    if not path.exists():
        path = EXAMPLE_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"No config found at {path} or {EXAMPLE_CONFIG_PATH}")

    with open(path) as f:
        raw = f.read()

    # Substitute ${ENV_VAR} references
    for key, value in os.environ.items():
        raw = raw.replace(f"${{{key}}}", value)

    return yaml.safe_load(raw)
