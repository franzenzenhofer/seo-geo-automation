"""Loader for per-site audit configuration JSON files."""

from __future__ import annotations

import json
from pathlib import Path

from shared.types import SiteConfig

REQUIRED_FIELDS = ("domain", "start_url")


class ConfigError(ValueError):
    """Raised when a config file is missing or invalid."""


def load_config(config_path: str | Path) -> SiteConfig:
    """Load and validate a site configuration JSON file."""
    path = Path(config_path)
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    missing = [k for k in REQUIRED_FIELDS if k not in data]
    if missing:
        raise ConfigError(f"Missing required config fields in {path}: {missing}")
    config = SiteConfig.from_dict(data)
    if not config.robots_url:
        config.robots_url = f"https://{config.domain}/robots.txt"
    return config
