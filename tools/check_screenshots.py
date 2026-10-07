"""Screenshot checks: PSI Lighthouse final screenshots and GSC URL Inspection render verdict."""

from __future__ import annotations

from shared.gsc_client import GscUnavailable, gsc_context, url_inspection
from shared.html_parser import ParsedPage
from shared.http_client import HttpResponse
from shared.psi import final_screenshot, run_psi
from shared.tool_base import run_tool
from shared.types import Check, CheckResult, Severity, SiteConfig

C = "SCREENSHOTS"

SCREEN_003 = Check("SCREEN-003", "GSC Render Verdict", C)


def _screenshot_check(cid: str, name: str, url: str, strategy: str) -> CheckResult:
    result = run_psi(url, strategy)
    if result.error:
        return CheckResult(cid, name, C, Severity.INFO if result.skipped else Severity.WARN, result.error)
    shot = final_screenshot(result.data)
    if not shot:
        return CheckResult(cid, name, C, Severity.WARN, "No screenshot in PSI response")
    msg = f"{strategy.capitalize()} screenshot captured via PSI Lighthouse"
    return CheckResult(cid, name, C, Severity.PASS, msg, {"has_screenshot": True, "size": len(shot)})


def check_screenshot_mobile(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    return _screenshot_check("SCREEN-001", "Mobile Screenshot", response.final_url, "mobile")


def check_screenshot_desktop(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    return _screenshot_check("SCREEN-002", "Desktop Screenshot", response.final_url, "desktop")


def check_gsc_render_screenshot(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    """SCREEN-003: GSC URL Inspection index + mobile render verdict (how Google sees the page)."""
    ctx = gsc_context(config)
    if isinstance(ctx, GscUnavailable):
        return SCREEN_003.result(ctx.severity, ctx.reason)
    result = url_inspection(ctx, response.final_url)
    if "error" in result:
        return SCREEN_003.result(Severity.WARN, f"GSC error: {result['error']}")
    idx = result.get("indexStatusResult", {})
    mobile = result.get("mobileUsabilityResult", {})
    verdict = mobile.get("verdict", "UNKNOWN")
    details = {
        "indexVerdict": idx.get("verdict", ""),
        "coverage": idx.get("coverageState", ""),
        "renderVerdict": verdict,
        "mobileIssues": mobile.get("issues", []),
        "lastCrawled": idx.get("lastCrawlTime", ""),
    }
    if verdict == "PASS":
        return SCREEN_003.result(Severity.PASS, "Mobile render verdict PASS", details)
    if verdict == "UNKNOWN":
        return SCREEN_003.result(Severity.INFO, "Mobile render verdict unknown", details)
    return SCREEN_003.result(Severity.WARN, f"Mobile render verdict: {verdict}", details)


checks = {
    "SCREEN-001": check_screenshot_mobile,
    "SCREEN-002": check_screenshot_desktop,
    "SCREEN-003": check_gsc_render_screenshot,
}

if __name__ == "__main__":
    run_tool(C, checks, "Screenshot capture via PSI and GSC")
