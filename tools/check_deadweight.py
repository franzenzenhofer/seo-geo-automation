"""Dead weight / ballast page detection."""

from __future__ import annotations

from shared.html_parser import ParsedPage, get_body_text, get_meta_description, get_meta_robots, get_title
from shared.http_client import HttpResponse
from shared.tool_base import run_tool
from shared.types import Check, CheckResult, Severity, SiteConfig

C = "DEADWEIGHT"

DEAD_001 = Check("DEAD-001", "Page Has Purpose", C)
DEAD_002 = Check("DEAD-002", "Noindex if Dead Weight", C)
DEAD_003 = Check("DEAD-003", "Not Soft 404", C)
DEAD_004 = Check("DEAD-004", "Dead Page Status Code", C)


def check_has_purpose(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    title = get_title(page)
    desc = get_meta_description(page)
    text = get_body_text(page)
    words = len(text.split())
    if title["text"] and desc["content"] and words >= 50:
        return DEAD_001.result(Severity.PASS, f"Page has title, description, and {words} words of content")
    issues = []
    if not title["text"]:
        issues.append("no title")
    if not desc["content"]:
        issues.append("no meta description")
    if words < 50:
        issues.append(f"only {words} words")
    return DEAD_001.result(Severity.WARN, f"Possible dead weight: {', '.join(issues)}")


def check_noindex_if_deadweight(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    robots = get_meta_robots(page)
    text = get_body_text(page)
    words = len(text.split())
    if words >= 50:
        return DEAD_002.result(Severity.INFO, "Page has content - not dead weight")
    if robots["has_noindex"]:
        return DEAD_002.result(Severity.PASS, "Thin page correctly has noindex")
    return DEAD_002.result(
        Severity.WARN, f"Thin page ({words} words) without noindex - consider noindex or adding content"
    )


def check_not_soft_404(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    if response.status_code == 200:
        text = get_body_text(page)
        error_phrases = ["page not found", "404", "nicht gefunden", "seite nicht gefunden"]
        lower = text.lower()
        if any(p in lower for p in error_phrases) and len(text.split()) < 100:
            return DEAD_003.result(Severity.WARN, "Page returns 200 but looks like error page (soft 404)")
    return DEAD_003.result(Severity.PASS, "Page does not appear to be a soft 404")


def check_dead_page_status_code(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    robots = get_meta_robots(page)
    if not robots["has_noindex"]:
        return DEAD_004.result(Severity.INFO, "Page is indexable - check not applicable")
    code = response.status_code
    if code in (404, 410):
        return DEAD_004.result(Severity.PASS, f"Noindex page returns {code} - proper dead weight handling")
    return DEAD_004.result(
        Severity.INFO, f"Noindex page returns {code} - consider 404/410 for true dead weight removal"
    )


checks = {
    "DEAD-001": check_has_purpose,
    "DEAD-002": check_noindex_if_deadweight,
    "DEAD-003": check_not_soft_404,
    "DEAD-004": check_dead_page_status_code,
}

if __name__ == "__main__":
    run_tool("DEADWEIGHT", checks, "Dead weight / ballast checks")
