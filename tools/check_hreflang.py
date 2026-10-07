"""Hreflang / multi-language checks."""

from __future__ import annotations

import re

from shared.html_parser import ParsedPage, get_canonical, get_hreflang, get_lang
from shared.http_client import HttpResponse
from shared.tool_base import run_tool
from shared.types import Check, CheckResult, Severity, SiteConfig

C = "HREFLANG"

HREFLANG_001 = Check("HREFLANG-001", "Hreflang Present", C)
HREFLANG_002 = Check("HREFLANG-002", "Hreflang Self-Reference", C)
HREFLANG_003 = Check("HREFLANG-003", "Hreflang Valid Values", C)
HREFLANG_004 = Check("HREFLANG-004", "Hreflang x-default", C)
HREFLANG_005 = Check("HREFLANG-005", "Hreflang/Canonical Alignment", C)
HREFLANG_006 = Check("HREFLANG-006", "Single Language", C)


def check_hreflang_present(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    links = get_hreflang(page)
    if links:
        langs = [lnk["hreflang"] for lnk in links]
        return HREFLANG_001.result(Severity.INFO, f"{len(links)} hreflang tags: {', '.join(langs[:10])}")
    return HREFLANG_001.result(Severity.INFO, "No hreflang tags (single language site)")


def check_hreflang_self_reference(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    links = get_hreflang(page)
    if not links:
        return HREFLANG_002.result(Severity.INFO, "No hreflang")
    page_url = response.final_url.rstrip("/")
    has_self = any(lnk["href"].rstrip("/") == page_url for lnk in links)
    if has_self:
        return HREFLANG_002.result(Severity.PASS, "Self-reference found in hreflang")
    return HREFLANG_002.result(Severity.FAIL, "Missing self-reference in hreflang cluster")


def check_hreflang_valid_values(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    links = get_hreflang(page)
    if not links:
        return HREFLANG_003.result(Severity.INFO, "No hreflang")
    bcp47 = re.compile(r"^(x-default|[a-z]{2,3}(-[A-Za-z]{2,8})*)$")
    invalid = [lnk["hreflang"] for lnk in links if not bcp47.match(lnk["hreflang"])]
    if not invalid:
        return HREFLANG_003.result(Severity.PASS, "All hreflang values are valid")
    return HREFLANG_003.result(Severity.FAIL, f"Invalid hreflang values: {invalid}")


def check_hreflang_x_default(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    links = get_hreflang(page)
    if not links:
        return HREFLANG_004.result(Severity.INFO, "No hreflang")
    has_default = any(lnk["hreflang"] == "x-default" for lnk in links)
    if has_default:
        return HREFLANG_004.result(Severity.PASS, "x-default hreflang present")
    return HREFLANG_004.result(Severity.WARN, "Missing x-default hreflang")


def check_hreflang_canonical_align(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    links = get_hreflang(page)
    if not links:
        return HREFLANG_005.result(Severity.INFO, "No hreflang")
    canon = get_canonical(page)
    if not canon["href"]:
        return HREFLANG_005.result(Severity.INFO, "No canonical")
    hrefs = [lnk["href"].rstrip("/") for lnk in links]
    if canon["href"].rstrip("/") in hrefs:
        return HREFLANG_005.result(Severity.PASS, "Canonical URL is in hreflang cluster")
    return HREFLANG_005.result(Severity.WARN, "Canonical URL not found in hreflang cluster")


def check_page_single_language(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    lang = get_lang(page)
    if lang["present"]:
        return HREFLANG_006.result(Severity.PASS, f"Page language: {lang['value']}")
    return HREFLANG_006.result(Severity.WARN, "No lang attribute - page must use exactly one language")


checks = {
    "HREFLANG-001": check_hreflang_present,
    "HREFLANG-002": check_hreflang_self_reference,
    "HREFLANG-003": check_hreflang_valid_values,
    "HREFLANG-004": check_hreflang_x_default,
    "HREFLANG-005": check_hreflang_canonical_align,
    "HREFLANG-006": check_page_single_language,
}

if __name__ == "__main__":
    run_tool("HREFLANG", checks, "Hreflang / multi-language checks")
