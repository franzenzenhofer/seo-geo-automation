"""PageSpeed Insights API client with a per-run disk cache.

API docs: https://developers.google.com/speed/docs/insights/v5/get-started
Keyless calls share one exhausted global quota, so PSI_API_KEY is required.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

import requests

from shared.settings import ENV_PSI_KEY, cache_dir, env_value

PSI_API_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
PSI_TIMEOUT_S = 120
PSI_SKIP_MESSAGE = f"PSI skipped: set {ENV_PSI_KEY} (free key, see README)"


@dataclass(frozen=True)
class PsiResult:
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    skipped: bool = False


def psi_available() -> bool:
    return bool(env_value(ENV_PSI_KEY))


def run_psi(url: str, strategy: str) -> PsiResult:
    """Run (or read from the per-run cache) a PSI performance analysis."""
    if not psi_available():
        return PsiResult(error=PSI_SKIP_MESSAGE, skipped=True)
    cached = _read_cache(url, strategy)
    if cached is not None:
        return PsiResult(data=cached)
    params = {"url": url, "strategy": strategy, "category": "performance"}
    params["key"] = env_value(ENV_PSI_KEY)
    try:
        resp = requests.get(PSI_API_URL, params=params, timeout=PSI_TIMEOUT_S)
    except requests.RequestException as exc:
        return PsiResult(error=f"PSI request failed: {exc}")
    if resp.status_code != 200:
        return PsiResult(error=f"PSI HTTP {resp.status_code}: {resp.text[:200]}")
    data: dict[str, Any] = resp.json()
    _write_cache(url, strategy, data)
    return PsiResult(data=data)


def performance_score(data: dict[str, Any]) -> float | None:
    try:
        return float(data["lighthouseResult"]["categories"]["performance"]["score"]) * 100
    except (KeyError, TypeError, ValueError):
        return None


def audit_value(data: dict[str, Any], audit: str) -> float | None:
    try:
        return float(data["lighthouseResult"]["audits"][audit]["numericValue"])
    except (KeyError, TypeError, ValueError):
        return None


def field_percentile(data: dict[str, Any], metric: str) -> int | None:
    try:
        return int(data["loadingExperience"]["metrics"][metric]["percentile"])
    except (KeyError, TypeError, ValueError):
        return None


def final_screenshot(data: dict[str, Any]) -> str:
    """Base64 data URI of the final Lighthouse screenshot, empty if absent."""
    audits = data.get("lighthouseResult", {}).get("audits", {})
    return str(audits.get("final-screenshot", {}).get("details", {}).get("data", ""))


def _cache_file_name(url: str, strategy: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return f"psi-{strategy}-{digest}.json"


def _read_cache(url: str, strategy: str) -> dict[str, Any] | None:
    directory = cache_dir()
    if directory is None:
        return None
    path = directory / _cache_file_name(url, strategy)
    if not path.exists():
        return None
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _write_cache(url: str, strategy: str, data: dict[str, Any]) -> None:
    directory = cache_dir()
    if directory is None:
        return
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / _cache_file_name(url, strategy)
    path.write_text(json.dumps(data), encoding="utf-8")
