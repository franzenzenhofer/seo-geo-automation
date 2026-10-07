"""Redirect checks: chain depth, permanent redirects, HTTP->HTTPS, www/non-www, trailing slash."""

from __future__ import annotations

from urllib.parse import urlparse

from shared.html_parser import ParsedPage
from shared.http_client import HttpResponse, fetch
from shared.tool_base import run_tool
from shared.types import Check, CheckResult, Severity, SiteConfig

C = "REDIRECTS"
TIMEOUT = 15

DEPTH = Check("RED-001", "Redirect Chain Depth", C)
TYPES = Check("RED-002", "Redirect Types", C)
HTTPS = Check("RED-003", "HTTP->HTTPS Redirect", C)
WWW = Check("RED-004", "www/non-www Redirect", C)
SLASH = Check("RED-005", "Trailing Slash Redirect", C)


def hops(resp: HttpResponse) -> list[dict[str, object]]:
    return [{"url": h.url, "status": h.status_code} for h in resp.redirect_chain]


def check_redirect_chain_depth(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    """RED-001: At most one redirect hop (ideally none)."""
    chain = response.redirect_chain
    if not chain:
        return DEPTH.result(Severity.PASS, "No redirects - direct response")
    if len(chain) == 1:
        return DEPTH.result(
            Severity.WARN, f"1 redirect: {chain[0].status_code} {chain[0].url} -> {response.final_url}"
        )
    details = {"chain": hops(response), "final": response.final_url}
    return DEPTH.result(Severity.FAIL, f"{len(chain)} redirects in chain (max 1 recommended)", details)


def check_redirect_types(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    """RED-002: Redirects should be permanent (301/308), not 302/307."""
    if not response.redirect_chain:
        return TYPES.result(Severity.PASS, "No redirects to check")
    temporary = [h for h in response.redirect_chain if h.status_code not in (301, 308)]
    if not temporary:
        return TYPES.result(Severity.PASS, "All redirects are permanent (301/308)")
    details = {"non_permanent": [{"url": h.url, "status": h.status_code} for h in temporary]}
    return TYPES.result(Severity.WARN, f"{len(temporary)} temporary redirects (use 301/308)", details)


def check_http_to_https(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    """RED-003: The http:// version redirects to https://."""
    url = response.final_url
    if urlparse(url).scheme != "https":
        return HTTPS.result(Severity.FAIL, f"Final URL is not HTTPS: {url}")
    probe = fetch("http://" + url.removeprefix("https://"), timeout=TIMEOUT)
    if probe.error:
        return HTTPS.result(Severity.WARN, f"Could not verify HTTP->HTTPS redirect: {probe.error[:100]}")
    if probe.final_url.startswith("https://") and probe.redirect_chain:
        return HTTPS.result(
            Severity.PASS, f"http:// redirects to https:// ({len(probe.redirect_chain)} hop(s))"
        )
    return HTTPS.result(Severity.FAIL, f"HTTP does not redirect to HTTPS. Final: {probe.final_url}")


def check_www_nonwww(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    """RED-004: The other www/non-www host redirects to the canonical host."""
    parsed = urlparse(response.final_url)
    host = parsed.hostname or ""
    alt_host = host.removeprefix("www.") if host.startswith("www.") else f"www.{host}"
    alt_url = parsed._replace(netloc=alt_host).geturl()
    probe = fetch(alt_url, timeout=TIMEOUT)
    if probe.error:
        return WWW.result(Severity.INFO, f"{alt_host} does not resolve (fine if the host is never used)")
    final_host = urlparse(probe.final_url).hostname or ""
    if final_host == host:
        return WWW.result(Severity.PASS, f"{alt_host} redirects to {host}")
    details = {"alt_url": alt_url, "final": probe.final_url}
    return WWW.result(Severity.WARN, f"{alt_host} resolves to {final_host} (expected {host})", details)


def trailing_slash_variant(url: str) -> str:
    """The opposite trailing-slash form of url, or '' for the root path."""
    parsed = urlparse(url)
    if parsed.path in ("", "/"):
        return ""
    path = parsed.path.rstrip("/") if parsed.path.endswith("/") else parsed.path + "/"
    return parsed._replace(path=path).geturl()


def check_trailing_slash_redirect(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    """RED-005: The trailing-slash variant redirects to the canonical form."""
    url = response.final_url
    variant = trailing_slash_variant(url)
    if not variant:
        return SLASH.result(Severity.PASS, "Root URL - trailing slash check not applicable")
    probe = fetch(variant, timeout=TIMEOUT)
    if probe.final_url.rstrip("/") == url.rstrip("/") and probe.final_url != variant:
        return SLASH.result(Severity.PASS, "Trailing slash variant redirects correctly")
    if probe.status_code >= 400:
        return SLASH.result(Severity.PASS, f"Trailing slash variant returns {probe.status_code}")
    details = {"tested": variant, "final": probe.final_url, "status": probe.status_code}
    return SLASH.result(
        Severity.WARN, f"Trailing slash variant resolves separately: {probe.final_url}", details
    )


checks = {
    "RED-001": check_redirect_chain_depth,
    "RED-002": check_redirect_types,
    "RED-003": check_http_to_https,
    "RED-004": check_www_nonwww,
    "RED-005": check_trailing_slash_redirect,
}

if __name__ == "__main__":
    run_tool(C, checks, "Redirect chain analysis")
