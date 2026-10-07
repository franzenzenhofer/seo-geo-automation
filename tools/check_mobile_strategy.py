"""Detect the mobile strategy: responsive, dynamic serving, m. subdomain or separate URLs.

Fetches the page with a mobile and a desktop User-Agent and compares the responses.
Reference: https://developers.google.com/search/docs/crawling-indexing/mobile/mobile-sites-mobile-first-indexing
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from shared.html_parser import ParsedPage, attr, first_tag, parse_html, tags
from shared.http_client import UA_DESKTOP, UA_MOBILE, HttpResponse, fetch
from shared.tool_base import run_tool
from shared.types import CheckResult, Severity, SiteConfig

C = "MOBILE_STRATEGY"
CID, NAME = "MOBILE-STRATEGY-001", "Mobile Strategy Detection"


def _result(sev: Severity, msg: str, details: dict[str, Any]) -> CheckResult:
    return CheckResult(CID, NAME, C, sev, msg, details)


def _signature(page: ParsedPage) -> dict[str, Any]:
    title = first_tag(page.soup, "title")
    return {
        "title": title.get_text(strip=True) if title else "",
        "h1": [h.get_text(strip=True) for h in tags(page.soup, "h1")],
        "canonical": attr(first_tag(page.soup, "link", rel="canonical"), "href"),
        "viewport": first_tag(page.soup, "meta", attrs={"name": "viewport"}) is not None,
    }


def compare(mobile: HttpResponse, desktop: HttpResponse) -> dict[str, Any]:
    m_sig = _signature(parse_html(mobile.body, mobile.final_url))
    d_sig = _signature(parse_html(desktop.body, desktop.final_url))
    m_len, d_len = len(mobile.body), len(desktop.body)
    return {
        "mobile_url": mobile.final_url,
        "desktop_url": desktop.final_url,
        "mobile_html_size": m_len,
        "desktop_html_size": d_len,
        "html_size_diff_pct": round(abs(m_len - d_len) / max(d_len, 1) * 100, 1),
        "vary_user_agent": "user-agent" in mobile.headers.get("Vary", "").lower(),
        "same_title": m_sig["title"] == d_sig["title"],
        "same_h1": m_sig["h1"] == d_sig["h1"],
        "mobile_canonical": m_sig["canonical"],
        "desktop_canonical": d_sig["canonical"],
        "viewport": m_sig["viewport"],
    }


def classify(d: dict[str, Any]) -> CheckResult:
    diff, vary = d["html_size_diff_pct"], d["vary_user_agent"]
    if d["mobile_url"] != d["desktop_url"]:
        mobile_host = urlparse(d["mobile_url"]).hostname or ""
        kind = "m. subdomain" if mobile_host.startswith("m.") else "Separate mobile URL"
        msg = (
            f"{kind}: mobile={d['mobile_url']}, desktop={d['desktop_url']}. Responsive design is recommended."
        )
        return _result(Severity.WARN, msg, d)
    if vary and diff > 20:
        msg = f"Dynamic serving: Vary: User-Agent set, HTML differs by {diff:.0f}% between mobile and desktop"
        return _result(Severity.WARN, msg, d)
    if diff > 30:
        msg = f"HTML differs by {diff:.0f}% without Vary: User-Agent - add the header if serving per UA"
        return _result(Severity.WARN, msg, d)
    if diff < 5 and d["same_title"] and d["same_h1"]:
        if d["viewport"]:
            msg = f"Responsive design: same HTML for mobile and desktop ({diff:.1f}% diff), viewport set"
            return _result(Severity.PASS, msg, d)
        return _result(Severity.WARN, f"Same HTML ({diff:.1f}% diff) but NO viewport meta tag", d)
    msg = (
        f"HTML differs by {diff:.1f}% (Vary: User-Agent = {vary}, same title: {d['same_title']}, "
        f"same H1: {d['same_h1']}); likely responsive with dynamic elements"
    )
    return _result(Severity.INFO, msg, d)


def check_mobile_strategy(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    mobile = fetch(response.url, user_agent=UA_MOBILE, timeout=20)
    desktop = fetch(response.url, user_agent=UA_DESKTOP, timeout=20)
    failed = next((r for r in (mobile, desktop) if r.error), None)
    if failed:
        return _result(Severity.ERROR, f"Could not fetch {failed.url}: {failed.error}", {})
    return classify(compare(mobile, desktop))


checks = {CID: check_mobile_strategy}

if __name__ == "__main__":
    run_tool(C, checks, "Mobile strategy detection")
