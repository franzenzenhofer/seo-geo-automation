"""Open Graph / Social meta tag checks."""

from __future__ import annotations

from shared.html_parser import ParsedPage, get_canonical, get_og_tags, get_twitter_tags
from shared.http_client import HttpResponse
from shared.tool_base import run_tool
from shared.types import Check, CheckResult, Severity, SiteConfig

C = "OG"

OG_001 = Check("OG-001", "OG Title", C)
OG_002 = Check("OG-002", "OG Description", C)
OG_003 = Check("OG-003", "OG URL", C)
OG_004 = Check("OG-004", "OG Image", C)
OG_005 = Check("OG-005", "Twitter Card", C)


def check_og_title(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    og = get_og_tags(page)
    val = og.get("og:title", "")
    if val:
        return OG_001.result(Severity.PASS, f"og:title: '{val[:80]}'")
    return OG_001.result(Severity.WARN, "Missing og:title")


def check_og_description(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    og = get_og_tags(page)
    val = og.get("og:description", "")
    if val:
        return OG_002.result(Severity.PASS, f"og:description ({len(val)} chars)")
    return OG_002.result(Severity.WARN, "Missing og:description")


def check_og_url(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    og = get_og_tags(page)
    val = og.get("og:url", "")
    if not val:
        return OG_003.result(Severity.WARN, "Missing og:url")
    if not val.startswith("http"):
        return OG_003.result(Severity.WARN, "og:url is not absolute")
    canon = get_canonical(page)
    if canon["href"] and val != canon["href"]:
        return OG_003.result(Severity.WARN, f"og:url differs from canonical: {val} vs {canon['href']}")
    return OG_003.result(Severity.PASS, f"og:url: {val}")


def check_og_image(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    og = get_og_tags(page)
    val = og.get("og:image", "")
    if not val:
        return OG_004.result(Severity.WARN, "Missing og:image")
    if not val.startswith("http"):
        return OG_004.result(Severity.WARN, "og:image is not absolute URL")
    return OG_004.result(Severity.PASS, f"og:image: {val[:100]}")


def check_twitter_card(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    tw = get_twitter_tags(page)
    card = tw.get("twitter:card", "")
    valid = {"summary", "summary_large_image", "app", "player"}
    if card in valid:
        return OG_005.result(Severity.PASS, f"twitter:card: {card}")
    if card:
        return OG_005.result(Severity.WARN, f"Invalid twitter:card: {card}")
    return OG_005.result(Severity.INFO, "No twitter:card meta tag")


checks = {
    "OG-001": check_og_title,
    "OG-002": check_og_description,
    "OG-003": check_og_url,
    "OG-004": check_og_image,
    "OG-005": check_twitter_card,
}

if __name__ == "__main__":
    run_tool("OG", checks, "Open Graph / Social checks")
