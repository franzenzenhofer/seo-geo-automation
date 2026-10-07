"""Favicon checks."""

from __future__ import annotations

from urllib.parse import urlparse

from shared.html_parser import ParsedPage, get_favicon
from shared.http_client import HttpResponse, fetch
from shared.tool_base import run_tool
from shared.types import Check, CheckResult, Severity, SiteConfig

C = "FAVICON"

FAVICON_001 = Check("FAVICON-001", "Favicon Exists", C)
FAVICON_002 = Check("FAVICON-002", "Favicon PNG Format", C)


def check_favicon_exists(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    fav = get_favicon(page)
    if fav["present"] and fav["href"]:
        resp = fetch(fav["href"])
        if resp.status_code == 200:
            return FAVICON_001.result(Severity.PASS, f"Favicon found: {fav['href'][:80]}")
        return FAVICON_001.result(Severity.WARN, f"Favicon link exists but returns {resp.status_code}")
    parsed = urlparse(response.final_url)
    fallback = f"{parsed.scheme}://{parsed.netloc}/favicon.ico"
    resp = fetch(fallback)
    if resp.status_code == 200:
        return FAVICON_001.result(Severity.PASS, "Favicon at /favicon.ico")
    return FAVICON_001.result(Severity.WARN, "No favicon found")


def check_favicon_format(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    fav = get_favicon(page)
    href = fav.get("href", "")
    if not href:
        return FAVICON_002.result(Severity.INFO, "No favicon link")
    if href.lower().endswith(".png") or 'type="image/png"' in str(page.soup.find("link", rel="icon")):
        return FAVICON_002.result(Severity.PASS, "Favicon is PNG format (recommended)")
    if href.lower().endswith(".svg"):
        return FAVICON_002.result(Severity.PASS, "Favicon is SVG format (also good)")
    return FAVICON_002.result(
        Severity.INFO, f"Favicon format: {href.rsplit('.', 1)[-1]} - PNG recommended (48px multiple)"
    )


checks = {"FAVICON-001": check_favicon_exists, "FAVICON-002": check_favicon_format}

if __name__ == "__main__":
    run_tool("FAVICON", checks, "Favicon checks")
