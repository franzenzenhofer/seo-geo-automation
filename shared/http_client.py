"""HTTP client for SEO auditing with redirect tracking and timing."""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass, field

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from shared.settings import ENV_USER_AGENT, env_value

# Mobile-first: Google indexes the mobile version, so the default UA is mobile.
UA_MOBILE = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.6099.199 Mobile Safari/537.36"
)
UA_DESKTOP = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
UA_GOOGLEBOT_MOBILE = (
    "Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.199 "
    "Mobile Safari/537.36 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
)
UA_GOOGLEBOT_DESKTOP = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
USER_AGENTS = {
    "mobile": UA_MOBILE,
    "desktop": UA_DESKTOP,
    "googlebot-mobile": UA_GOOGLEBOT_MOBILE,
    "googlebot-desktop": UA_GOOGLEBOT_DESKTOP,
}


def default_user_agent() -> str:
    """UA chosen by run.py --ua (env SEO_AUDIT_UA), mobile by default."""
    return USER_AGENTS.get(env_value(ENV_USER_AGENT).lower(), UA_MOBILE)


class HeaderDict(dict[str, str]):
    """Case-insensitive header mapping (RFC 9110 section 5.1); keys are stored lowercased.

    Still a plain dict subclass, so it serialises to JSON like before.
    """

    def __init__(self, items: Mapping[str, str] | None = None) -> None:
        super().__init__()
        for key, value in dict(items or {}).items():
            self[key] = value

    def __setitem__(self, key: str, value: str) -> None:
        super().__setitem__(key.lower(), value)

    def __getitem__(self, key: str) -> str:
        return super().__getitem__(key.lower())

    def __contains__(self, key: object) -> bool:
        return super().__contains__(str(key).lower())

    def get(self, key: str, default: str = "") -> str:  # type: ignore[override]
        return super().get(key.lower(), default)


@dataclass
class RedirectHop:
    url: str
    status_code: int
    headers: HeaderDict = field(default_factory=HeaderDict)


@dataclass
class HttpResponse:
    url: str
    final_url: str
    status_code: int
    headers: HeaderDict = field(default_factory=HeaderDict)
    body: str = ""
    redirect_chain: list[RedirectHop] = field(default_factory=list)
    response_time_ms: float = 0.0
    error: str = ""


def _build_session(max_retries: int, user_agent: str) -> requests.Session:
    session = requests.Session()
    retry = Retry(total=max_retries, backoff_factor=0.5, status_forcelist=[502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": user_agent})
    return session


def _to_response(url: str, resp: requests.Response, elapsed_ms: float, body: str) -> HttpResponse:
    chain = [
        RedirectHop(url=r.url, status_code=r.status_code, headers=HeaderDict(r.headers)) for r in resp.history
    ]
    return HttpResponse(
        url=url,
        final_url=resp.url,
        status_code=resp.status_code,
        headers=HeaderDict(resp.headers),
        body=body,
        redirect_chain=chain,
        response_time_ms=elapsed_ms,
    )


def fetch(url: str, user_agent: str = "", timeout: int = 30, follow_redirects: bool = True) -> HttpResponse:
    """GET a URL and return the response with redirect chain and timing."""
    session = _build_session(3, user_agent or default_user_agent())
    session.headers.update({"Accept-Encoding": "gzip, br"})
    start = time.monotonic()
    try:
        resp = session.get(url, timeout=timeout, allow_redirects=follow_redirects)
    except requests.RequestException as exc:
        elapsed = (time.monotonic() - start) * 1000
        return HttpResponse(url=url, final_url=url, status_code=0, response_time_ms=elapsed, error=str(exc))
    elapsed = (time.monotonic() - start) * 1000
    return _to_response(url, resp, elapsed, resp.text)


def fetch_head(url: str, user_agent: str = "", timeout: int = 15) -> HttpResponse:
    """HEAD request only, for quick status/header checks."""
    session = _build_session(2, user_agent or default_user_agent())
    start = time.monotonic()
    try:
        resp = session.head(url, timeout=timeout, allow_redirects=True)
    except requests.RequestException as exc:
        elapsed = (time.monotonic() - start) * 1000
        return HttpResponse(url=url, final_url=url, status_code=0, response_time_ms=elapsed, error=str(exc))
    elapsed = (time.monotonic() - start) * 1000
    return _to_response(url, resp, elapsed, "")
