"""Mobile optimization checks."""

from __future__ import annotations

from shared.html_parser import ParsedPage, attr, first_tag, get_viewport
from shared.http_client import HttpResponse
from shared.tool_base import run_tool
from shared.types import Check, CheckResult, Severity, SiteConfig

C = "MOBILE"

MOBILE_001 = Check("MOBILE-001", "Responsive Design", C)
MOBILE_002 = Check("MOBILE-002", "No Separate Mobile URLs", C)
MOBILE_003 = Check("MOBILE-003", "Apple Touch Icon", C)
MOBILE_004 = Check("MOBILE-004", "Text Readable on Mobile", C)


def check_responsive(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    vp = get_viewport(page)
    if vp["present"] and "width=device-width" in vp["content"]:
        return MOBILE_001.result(Severity.PASS, "Viewport meta tag with width=device-width")
    if vp["present"]:
        return MOBILE_001.result(Severity.WARN, f"Viewport present but content: {vp['content']}")
    return MOBILE_001.result(Severity.FAIL, "No viewport meta tag - not mobile-friendly")


def check_no_separate_mobile_urls(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    alt_mobile = page.soup.find("link", rel="alternate", media=True)
    if alt_mobile:
        return MOBILE_002.result(
            Severity.WARN,
            "Separate mobile URLs detected - responsive design strongly recommended",
            {"media": alt_mobile.get("media"), "href": alt_mobile.get("href")},
        )
    return MOBILE_002.result(Severity.PASS, "No separate mobile URL pattern detected")


def check_touch_icon(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    icon = first_tag(page.soup, "link", rel="apple-touch-icon")
    if icon:
        return MOBILE_003.result(Severity.PASS, f"apple-touch-icon: {attr(icon, 'href')[:60]}")
    return MOBILE_003.result(Severity.INFO, "No apple-touch-icon (nice to have for mobile)")


def check_text_readable(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    vp = get_viewport(page)
    if not vp["present"]:
        return MOBILE_004.result(Severity.WARN, "No viewport - text may not be readable on mobile")
    if "user-scalable=no" in vp["content"] or "maximum-scale=1" in vp["content"]:
        return MOBILE_004.result(Severity.WARN, "Zoom disabled - users cannot resize text")
    return MOBILE_004.result(Severity.PASS, "Viewport allows user zoom")


checks = {
    "MOBILE-001": check_responsive,
    "MOBILE-002": check_no_separate_mobile_urls,
    "MOBILE-003": check_touch_icon,
    "MOBILE-004": check_text_readable,
}

if __name__ == "__main__":
    run_tool("MOBILE", checks, "Mobile optimization checks")
