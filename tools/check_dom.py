"""DOM analysis checks."""

from __future__ import annotations

import re
from collections import Counter

from bs4 import Tag

from shared.html_parser import ParsedPage, get_body_text, get_json_ld, tags
from shared.http_client import HttpResponse
from shared.tool_base import run_tool
from shared.types import Check, CheckResult, Severity, SiteConfig

C = "DOM"

DOM_001 = Check("DOM-001", "JSON-LD Blocks", C)
DOM_002 = Check("DOM-002", "DOM Node Count", C)
DOM_003 = Check("DOM-003", "DOM Depth", C)
DOM_004 = Check("DOM-004", "Data-nosnippet Usage", C)
DOM_005 = Check("DOM-005", "Client-Side Rendering", C)
DOM_006 = Check("DOM-006", "Top Words", C)


def dom_depth(root: Tag) -> int:
    """Maximum element nesting depth below root (iterative, safe for deep documents)."""
    deepest, stack = 0, [(root, 0)]
    while stack:
        el, depth = stack.pop()
        deepest = max(deepest, depth)
        stack.extend((child, depth + 1) for child in el.children if isinstance(child, Tag))
    return deepest


def check_json_ld_count(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    blocks = get_json_ld(page)
    types = [b.get("@type", "unknown") for b in blocks]
    return DOM_001.result(Severity.INFO, f"{len(blocks)} JSON-LD blocks: {types[:5]}")


def check_dom_node_count(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    count = len(page.soup.find_all())
    if count < 1500:
        return DOM_002.result(Severity.PASS, f"{count} DOM nodes")
    if count < 3000:
        return DOM_002.result(Severity.WARN, f"{count} DOM nodes (large - may slow rendering)")
    return DOM_002.result(Severity.FAIL, f"{count} DOM nodes (excessive - reduce DOM complexity)")


def check_dom_depth(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    max_depth = dom_depth(page.soup)
    if max_depth < 20:
        return DOM_003.result(Severity.PASS, f"Max depth: {max_depth}")
    return DOM_003.result(Severity.WARN, f"Deep DOM nesting: {max_depth} levels")


def check_data_nosnippet(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    nosnippet = tags(page.soup, attrs={"data-nosnippet": True})
    if not nosnippet:
        return DOM_004.result(Severity.PASS, "No data-nosnippet attributes")
    return DOM_004.result(
        Severity.WARN, f"{len(nosnippet)} elements with data-nosnippet - content hidden from snippets"
    )


def check_csr_heuristic(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    text = get_body_text(page)
    scripts = page.soup.find_all("script", src=True)
    if len(text) < 40 and len(scripts) > 5:
        return DOM_005.result(
            Severity.WARN, f"Possible CSR: only {len(text)} chars text but {len(scripts)} scripts"
        )
    return DOM_005.result(Severity.PASS, "Server-rendered content likely present")


def check_top_words(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    text = get_body_text(page)
    words = re.findall(r"\b[a-zA-ZäöüÄÖÜß]{4,}\b", text.lower())
    top = Counter(words).most_common(10)
    return DOM_006.result(Severity.INFO, f"Top words: {top[:5]}", {"top_10": top})


checks = {
    "DOM-001": check_json_ld_count,
    "DOM-002": check_dom_node_count,
    "DOM-003": check_dom_depth,
    "DOM-004": check_data_nosnippet,
    "DOM-005": check_csr_heuristic,
    "DOM-006": check_top_words,
}

if __name__ == "__main__":
    run_tool("DOM", checks, "DOM analysis checks")
