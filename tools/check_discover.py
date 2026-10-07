"""Google Discover eligibility checks."""

from __future__ import annotations

from shared.html_parser import ParsedPage, get_headings, get_json_ld, get_lang, get_meta_robots, get_og_tags
from shared.http_client import HttpResponse
from shared.tool_base import run_tool
from shared.types import Check, CheckResult, Severity, SiteConfig

C = "DISCOVER"

DISCOVER_001 = Check("DISCOVER-001", "max-image-preview:large", C)
DISCOVER_002 = Check("DISCOVER-002", "Article Structured Data", C)
DISCOVER_003 = Check("DISCOVER-003", "Published/Modified Time", C)
DISCOVER_004 = Check("DISCOVER-004", "Author Present", C)
DISCOVER_005 = Check("DISCOVER-005", "Headline Length", C)
DISCOVER_006 = Check("DISCOVER-006", "Page Indexable", C)
DISCOVER_007 = Check("DISCOVER-007", "Large OG Image", C)
DISCOVER_008 = Check("DISCOVER-008", "Primary Language", C)


def check_max_image_preview(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    robots = get_meta_robots(page)
    for tag in robots["tags"]:
        if "max-image-preview:large" in tag["content"].lower():
            return DISCOVER_001.result(Severity.PASS, "max-image-preview:large is set")
    x_robots = response.headers.get("X-Robots-Tag", "")
    if "max-image-preview:large" in x_robots.lower():
        return DISCOVER_001.result(Severity.PASS, "max-image-preview:large in X-Robots-Tag")
    return DISCOVER_001.result(Severity.WARN, "Missing max-image-preview:large (required for Discover)")


def check_article_structured_data(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    blocks = get_json_ld(page)
    article_types = {"Article", "NewsArticle", "BlogPosting"}
    for b in blocks:
        t = b.get("@type", "")
        types = t if isinstance(t, list) else [t]
        if any(at in article_types for at in types):
            return DISCOVER_002.result(Severity.PASS, f"Found {types[0]} structured data")
    return DISCOVER_002.result(Severity.WARN, "No Article/NewsArticle structured data")


def check_published_time(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    blocks = get_json_ld(page)
    for b in blocks:
        if b.get("datePublished") and b.get("dateModified"):
            return DISCOVER_003.result(
                Severity.PASS, f"datePublished: {b['datePublished']}, dateModified: {b['dateModified']}"
            )
        if b.get("datePublished"):
            return DISCOVER_003.result(Severity.WARN, "Has datePublished but missing dateModified")
    return DISCOVER_003.result(Severity.WARN, "Missing datePublished and dateModified")


def check_author(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    blocks = get_json_ld(page)
    for b in blocks:
        author = b.get("author", {})
        if isinstance(author, dict) and author.get("name"):
            return DISCOVER_004.result(Severity.PASS, f"Author: {author['name']}")
        if isinstance(author, list) and author:
            return DISCOVER_004.result(Severity.PASS, f"Authors: {len(author)}")
    return DISCOVER_004.result(Severity.WARN, "No author found")


def check_headline_length(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    h = get_headings(page)
    if h["h1_count"] == 0:
        return DISCOVER_005.result(Severity.WARN, "No H1")
    text = h["h1_texts"][0]
    if len(text) >= 20:
        return DISCOVER_005.result(Severity.PASS, f"H1: {len(text)} chars (min 20 for Discover)")
    return DISCOVER_005.result(Severity.WARN, f"H1 too short: {len(text)} chars (min 20)")


def check_indexable(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    robots = get_meta_robots(page)
    if robots["has_noindex"]:
        return DISCOVER_006.result(Severity.FAIL, "Page has noindex - cannot appear in Discover")
    return DISCOVER_006.result(Severity.PASS, "Page is indexable")


def check_og_image_large(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    og = get_og_tags(page)
    if not og.get("og:image"):
        return DISCOVER_007.result(Severity.WARN, "No og:image")
    width = og.get("og:image:width", "")
    height = og.get("og:image:height", "")
    if width and height:
        try:
            if int(width) >= 1200 or int(height) >= 1200:
                return DISCOVER_007.result(Severity.PASS, f"OG image: {width}x{height}px (>=1200)")
            return DISCOVER_007.result(Severity.WARN, f"OG image too small: {width}x{height}px (need >=1200)")
        except ValueError:
            pass
    return DISCOVER_007.result(Severity.WARN, "og:image size metadata missing (need >=1200px)")


def check_primary_language(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    lang = get_lang(page)
    if lang["present"]:
        return DISCOVER_008.result(Severity.PASS, f"html lang='{lang['value']}'")
    return DISCOVER_008.result(Severity.WARN, "Missing lang attribute on <html>")


checks = {
    "DISCOVER-001": check_max_image_preview,
    "DISCOVER-002": check_article_structured_data,
    "DISCOVER-003": check_published_time,
    "DISCOVER-004": check_author,
    "DISCOVER-005": check_headline_length,
    "DISCOVER-006": check_indexable,
    "DISCOVER-007": check_og_image_large,
    "DISCOVER-008": check_primary_language,
}

if __name__ == "__main__":
    run_tool("DISCOVER", checks, "Google Discover checks")
