"""External link analysis checks."""

from __future__ import annotations

from shared.html_parser import ParsedPage, get_links
from shared.http_client import HttpResponse
from shared.tool_base import run_tool
from shared.types import Check, CheckResult, Severity, SiteConfig

C = "EXTERNAL_LINKS"

EXT_001 = Check("EXT-001", "External Links Present", C)
EXT_002 = Check("EXT-002", "No Unnecessary Nofollow", C)
EXT_003 = Check("EXT-003", "External Link Ratio", C)


def check_external_links_present(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    links = get_links(page)
    count = links["external_count"]
    if count > 0:
        return EXT_001.result(Severity.PASS, f"{count} external links - good for user intent fulfillment")
    return EXT_001.result(Severity.INFO, "No external links - consider linking to helpful external resources")


def check_no_unnecessary_nofollow(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    links = get_links(page)
    ext_nf = [lnk for lnk in links["external"] if lnk["nofollow"]]
    if not links["external"]:
        return EXT_002.result(Severity.INFO, "No external links")
    if not ext_nf:
        return EXT_002.result(Severity.PASS, "No unnecessary nofollow on external links")
    return EXT_002.result(
        Severity.WARN,
        f"{len(ext_nf)} external links with nofollow - only paid links should be nofollow/sponsored",
        {"nofollow_links": [lnk["href"][:80] for lnk in ext_nf[:5]]},
    )


def check_external_link_count(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    links = get_links(page)
    total = links["internal_count"] + links["external_count"]
    ext = links["external_count"]
    if total == 0:
        return EXT_003.result(Severity.INFO, "No links")
    ratio = ext / total * 100
    return EXT_003.result(Severity.INFO, f"{ext} external / {total} total links ({ratio:.1f}%)")


checks = {
    "EXT-001": check_external_links_present,
    "EXT-002": check_no_unnecessary_nofollow,
    "EXT-003": check_external_link_count,
}

if __name__ == "__main__":
    run_tool(C, checks, "External link analysis")
