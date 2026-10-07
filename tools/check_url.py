"""URL structure checks (URL rules 1-6: stable, short, clean, phrase-bearing URLs)."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from shared.html_parser import ParsedPage, get_canonical, parse_html
from shared.http_client import HttpResponse, fetch
from shared.tool_base import run_tool
from shared.types import Check, CheckResult, Severity, SiteConfig

C = "URL"

URL_001 = Check("URL-001", "URL Short (Rule 5)", C)
URL_002 = Check("URL-002", "URL Has Phrase (Rule 6)", C)
URL_003 = Check("URL-003", "URL No Parameters", C)
URL_004 = Check("URL-004", "URL Lowercase", C)
URL_005 = Check("URL-005", "URL Clean Characters", C)
URL_006 = Check("URL-006", "Trailing Slash Consistent", C)
URL_007 = Check("URL-007", "Single Hop Redirect", C)
URL_008 = Check("URL-008", "No Double Hyphens", C)
URL_009 = Check("URL-009", "No Edge Hyphens", C)
URL_010 = Check("URL-010", "URL Variations (Rule 1)", C)
URL_011 = Check("URL-011", "URL Permanent (Rule 2)", C)


def check_url_short(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    path = urlparse(response.final_url).path
    if len(path) <= 80:
        return URL_001.result(Severity.PASS, f"URL path length: {len(path)} chars")
    return URL_001.result(Severity.WARN, f"URL path too long: {len(path)} chars (aim for <80)")


def check_url_has_phrase(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    """URL-002: The URL path contains a word of the page's targeted phrase (Rule 6)."""
    phrase = config.phrase_for(response.final_url) if config else ""
    if not phrase:
        return URL_002.result(Severity.INFO, "No targeted phrase configured for this URL")
    path = urlparse(response.final_url).path.lower()
    if any(w in path for w in phrase.lower().split() if len(w) > 3):
        return URL_002.result(Severity.PASS, "URL contains a variation of the targeted phrase")
    return URL_002.result(Severity.WARN, "URL does not contain the targeted phrase")


def check_url_no_params(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    parsed = urlparse(response.final_url)
    if not parsed.query:
        return URL_003.result(Severity.PASS, "Clean URL (no query params)")
    return URL_003.result(Severity.WARN, f"URL has query parameters: ?{parsed.query[:60]}")


def check_url_lowercase(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    path = urlparse(response.final_url).path
    if path == path.lower():
        return URL_004.result(Severity.PASS, "URL path is lowercase")
    return URL_004.result(Severity.WARN, "URL path contains uppercase characters")


def check_url_no_special_chars(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    path = urlparse(response.final_url).path
    bad = re.findall(r"[^a-zA-Z0-9/\-._~]", path)
    if not bad:
        return URL_005.result(Severity.PASS, "URL uses only clean characters")
    return URL_005.result(Severity.WARN, f"URL contains special characters: {set(bad)}")


def check_trailing_slash_consistency(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    url = response.final_url
    parsed = urlparse(url)
    if parsed.path.endswith("/"):
        alt = url.rstrip("/")
    else:
        alt = url + "/"
    resp = fetch(alt)
    if resp.redirect_chain and resp.final_url.rstrip("/") == url.rstrip("/"):
        return URL_006.result(Severity.PASS, "Opposite variant redirects correctly")
    if resp.status_code == 200 and resp.final_url != url:
        return URL_006.result(Severity.WARN, f"Both variants return 200: {url} and {alt}")
    return URL_006.result(Severity.PASS, "Trailing slash handled correctly")


def check_redirect_single_hop(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    chain = response.redirect_chain
    if len(chain) == 0:
        return URL_007.result(Severity.PASS, "No redirects")
    if len(chain) == 1:
        return URL_007.result(Severity.PASS, f"Single redirect: {chain[0].status_code}")
    return URL_007.result(
        Severity.FAIL,
        f"Redirect chain: {len(chain)} hops (must be single hop)",
        {"chain": [{"url": h.url, "status": h.status_code} for h in chain]},
    )


def check_no_double_hyphens(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    path = urlparse(response.final_url).path
    if "--" not in path:
        return URL_008.result(Severity.PASS, "URL path has no double hyphens")
    return URL_008.result(Severity.FAIL, f"URL path contains double hyphens: {path}")


def check_no_edge_hyphens(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    path = urlparse(response.final_url).path
    segments = [s for s in path.split("/") if s]
    bad = [s for s in segments if s.startswith("-") or s.endswith("-")]
    if not bad:
        return URL_009.result(Severity.PASS, "No path segments with leading/trailing hyphens")
    return URL_009.result(Severity.WARN, f"Path segments with edge hyphens: {bad}")


def url_variants(url: str) -> list[str]:
    """Uppercase path, tracking parameter and opposite trailing-slash variants of url."""
    path = urlparse(url).path
    variants = [url + ("&" if "?" in url else "?") + "utm_source=test"]
    if path and path != "/":
        variants.append(url.replace(path, path.upper(), 1))
        variants.append(url.rstrip("/") if path.endswith("/") else url + "/")
    return [v for v in variants if v != url]


def variant_issue(variant: str, original: str) -> str:
    """Empty when the variant redirects, errors, or canonicalises to the original URL."""
    resp = fetch(variant)
    if resp.status_code != 200 or resp.final_url != variant:
        return ""
    canonical = get_canonical(parse_html(resp.body, resp.final_url))["href"]
    if canonical and canonical.rstrip("/") == original.rstrip("/"):
        return ""
    return f"{variant} -> 200 (no redirect, no canonical to original)"


def check_url_variations(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    """URL-010: URL variants must redirect, 404 or canonicalise to the original (Rule 1)."""
    variants = url_variants(response.final_url)
    issues = [i for i in (variant_issue(v, response.final_url) for v in variants) if i]
    if issues:
        msg = f"{len(issues)} URL variation(s) not properly handled"
        return URL_010.result(Severity.FAIL, msg, {"issues": issues})
    msg = f"All {len(variants)} URL variations handled (redirect/canonical/404)"
    return URL_010.result(Severity.PASS, msg)


def check_url_permanent(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    """URL-011: URL permanence - no dates, categories, or coupling in URL path (Rule 2)."""
    path = urlparse(response.final_url).path.lower()
    segments = [s for s in path.split("/") if s]
    issues: list[str] = []
    date_pattern = re.compile(r"(19|20)\d{2}[/-]?\d{2}")
    for seg in segments:
        if date_pattern.search(seg):
            issues.append(f"Date in URL: '{seg}'")
    category_words = ["category", "kategorie", "cat", "tag", "archive", "archiv"]
    for seg in segments:
        if seg in category_words:
            issues.append(f"Category coupling: '{seg}'")
    if len(segments) > 3:
        issues.append(f"Deep nesting ({len(segments)} levels) suggests hierarchy coupling")
    if issues:
        return URL_011.result(
            Severity.WARN, f"URL may not be permanent: {'; '.join(issues)}", {"issues": issues}
        )
    return URL_011.result(Severity.PASS, "URL structure looks permanent (no dates, no category coupling)")


checks = {
    "URL-001": check_url_short,
    "URL-002": check_url_has_phrase,
    "URL-003": check_url_no_params,
    "URL-004": check_url_lowercase,
    "URL-005": check_url_no_special_chars,
    "URL-006": check_trailing_slash_consistency,
    "URL-007": check_redirect_single_hop,
    "URL-008": check_no_double_hyphens,
    "URL-009": check_no_edge_hyphens,
    "URL-010": check_url_variations,
    "URL-011": check_url_permanent,
}

if __name__ == "__main__":
    run_tool("URL", checks, "URL structure checks")
