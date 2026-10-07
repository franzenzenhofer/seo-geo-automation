"""Environment-based settings. Every external integration is opt-in via env vars."""

from __future__ import annotations

import os
from pathlib import Path

ENV_USER_AGENT = "SEO_AUDIT_UA"
ENV_NO_AI = "SEO_AUDIT_NO_AI"
ENV_CACHE_DIR = "SEO_AUDIT_CACHE_DIR"
ENV_OPENROUTER_KEY = "OPENROUTER_API_KEY"
ENV_OPENROUTER_MODEL = "OPENROUTER_MODEL"
ENV_PSI_KEY = "PSI_API_KEY"
ENV_GSC_CREDENTIALS = "GSC_CREDENTIALS"
ENV_LIVETEST_PATH = "LIVETEST_PATH"

DEFAULT_OPENROUTER_MODEL = "google/gemini-3.1-flash-lite"
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def env_value(name: str) -> str:
    """Return a stripped env var value, empty string when unset."""
    return os.environ.get(name, "").strip()


def ai_disabled() -> bool:
    """True when the run was started with --no-ai."""
    return env_value(ENV_NO_AI) == "1"


def openrouter_model() -> str:
    return env_value(ENV_OPENROUTER_MODEL) or DEFAULT_OPENROUTER_MODEL


def cache_dir() -> Path | None:
    """Per-run cache directory (set by run.py), or None when a tool runs standalone."""
    value = env_value(ENV_CACHE_DIR)
    return Path(value) if value else None


def optional_path(name: str) -> Path | None:
    """Return the path in env var `name`, expanded, or None when unset."""
    value = env_value(name)
    return Path(value).expanduser() if value else None
