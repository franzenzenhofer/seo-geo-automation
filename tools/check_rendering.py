"""JS rendering dependency checks: SPA signals, noscript, frameworks, overlays, consent banners."""

from __future__ import annotations

import re

from bs4 import Tag

from shared.browser import detect_js_rendering
from shared.html_parser import ParsedPage, attr, tags
from shared.http_client import HttpResponse
from shared.tool_base import run_tool
from shared.types import Check, CheckResult, Severity, SiteConfig

C = "RENDERING"
OVERLAY_PATTERN = re.compile(r"overlay|modal|cookie|consent|gdpr|privacy.?banner", re.IGNORECASE)
HIGH_Z_FIXED = re.compile(r"position\s*:\s*(fixed|absolute)[^\"']*z-index\s*:\s*(\d+)", re.IGNORECASE)
HIGH_Z_INDEX = 1000
JS_VOID_HREFS = {"#", "javascript:void(0)", "javascript:void(0);", "javascript:;", ""}
CMP_SCRIPTS = (
    "cookiebot", "onetrust", "cookieconsent", "cookie-consent", "cookie_consent", "cookiefirst",
    "usercentrics", "didomi", "quantcast", "trustarc", "cookie-law", "gdpr", "cookie-notice",
    "cookie-banner", "consent-manager", "consentmanager", "klaro", "iubenda", "osano", "termly",
    "complianz", "borlabs-cookie", "real-cookie-banner", "sourcepoint", "sp-cmp", "privacy-mgmt",
)  # fmt: skip
CMP_INLINE_KEYWORDS = (
    "cookieconsent", "onetrust", "cookiebot", "usercentrics", "didomi", "consentmanager",
    "sourcepoint", "__tcfapi", "__cmp(", "window.sp", "sp_ccpa", "sp_gdpr", "trustarc", "iubenda",
    "klaro.config",
)  # fmt: skip
CMP_CLASSES = re.compile(
    r"cookie|consent|cmp|gdpr|privacy.?banner|cc-banner|cc-window|ot-sdk|usercentrics|didomi|qc-cmp|"
    r"notice-banner",
    re.IGNORECASE,
)

RENDER_001 = Check("RENDER-001", "Not SPA Dependent", C)
RENDER_002 = Check("RENDER-002", "Noscript Fallback", C)
RENDER_003 = Check("RENDER-003", "JS Framework", C)
RENDER_004 = Check("RENDER-004", "Content Without JS", C)
RENDER_005 = Check("RENDER-005", "No Overlays", C)
RENDER_006 = Check("RENDER-006", "Nav Links Without JS", C)
RENDER_007 = Check("RENDER-007", "Cookie Banner Googlebot", C)


def selector(el: Tag) -> str:
    el_id, classes = attr(el, "id"), attr(el, "class").split()
    if el_id:
        return f"{el.name}#{el_id}"
    return f"{el.name}.{'.'.join(classes)}" if classes else el.name


def check_not_spa_dependent(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    signals = detect_js_rendering(response).spa_signals
    if not signals:
        return RENDER_001.result(Severity.PASS, "No SPA/JS-rendering signals detected")
    msg = f"JS rendering signals: {', '.join(signals)}"
    return RENDER_001.result(Severity.WARN, msg, {"signals": signals})


def check_noscript_fallback(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    comp = detect_js_rendering(response)
    if not comp.spa_signals:
        return RENDER_002.result(Severity.INFO, "Not JS-dependent - noscript not critical")
    if comp.has_noscript:
        msg = f"Has <noscript> fallback: {comp.noscript_content[:100]}"
        return RENDER_002.result(Severity.PASS, msg)
    return RENDER_002.result(Severity.WARN, "JS-dependent page without <noscript> fallback")


def check_framework_detected(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    framework = detect_js_rendering(response).js_framework_detected
    if framework:
        msg = f"Detected: {framework} - ensure SSR/SSG for SEO"
        return RENDER_003.result(Severity.INFO, msg, {"framework": framework})
    return RENDER_003.result(Severity.PASS, "No JS framework detected - server-rendered HTML")


def check_content_visible_without_js(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    if detect_js_rendering(response).empty_body:
        msg = "Body has <10 words without JS - Google may not see content"
        return RENDER_004.result(Severity.FAIL, msg)
    return RENDER_004.result(Severity.PASS, "Content is present in raw HTML")


def _overlay_hits(el: Tag) -> list[str]:
    hits = []
    if OVERLAY_PATTERN.search(attr(el, "class")) or OVERLAY_PATTERN.search(attr(el, "id")):
        hits.append(selector(el))
    match = HIGH_Z_FIXED.search(attr(el, "style"))
    if match and int(match.group(2)) >= HIGH_Z_INDEX:
        hits.append(f"{el.name}[style*='{match.group(0)[:40]}']")
    return hits


def check_no_overlays(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    """RENDER-005: Cookie/privacy overlays or high z-index fixed layers in the raw HTML."""
    found = list(dict.fromkeys(hit for el in tags(page.soup, True) for hit in _overlay_hits(el)))[:10]
    if found:
        msg = f"Potential overlays found: {', '.join(found)}"
        return RENDER_005.result(Severity.WARN, msg, {"selectors": found})
    return RENDER_005.result(Severity.PASS, "No cookie/privacy overlay patterns detected")


def check_navigation_links_without_js(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    """RENDER-006: <nav> elements contain real <a href> links."""
    navs = tags(page.soup, "nav")
    if not navs:
        return RENDER_006.result(Severity.INFO, "No <nav> element found in HTML")
    real = sum(
        1 for nav in navs for a in tags(nav, "a", href=True) if attr(a, "href").strip() not in JS_VOID_HREFS
    )
    if real >= 3:
        return RENDER_006.result(Severity.PASS, f"{real} real navigation links without JS")
    msg = f"Only {real} real nav links found - navigation may depend on JS"
    return RENDER_006.result(Severity.WARN, msg, {"real_link_count": real})


def cmp_script_findings(page: ParsedPage) -> list[str]:
    findings = [
        f"CMP script: {src[:80]}"
        for src in (attr(s, "src").lower() for s in tags(page.soup, "script", src=True))
        if any(cmp in src for cmp in CMP_SCRIPTS)
    ]
    for script in tags(page.soup, "script", src=False):
        text = (script.string or "").lower()[:2000]
        keyword = next((kw for kw in CMP_INLINE_KEYWORDS if kw in text), "")
        if keyword:
            findings.append(f"Inline CMP init: {keyword}")
    return findings


def banner_elements(page: ParsedPage) -> list[tuple[str, bool]]:
    """(selector, has_server_rendered_text) for consent-banner-like elements."""
    return [
        (selector(el), len(el.get_text(strip=True)) > 10)
        for el in tags(page.soup, True)
        if CMP_CLASSES.search(attr(el, "class")) or CMP_CLASSES.search(attr(el, "id"))
    ]


def check_cookie_banner_googlebot(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    """RENDER-007: JS-only consent banners can cover content for Googlebot's renderer."""
    scripts, banners = cmp_script_findings(page), banner_elements(page)
    empty = [sel for sel, has_text in banners if not has_text]
    details: dict[str, object] = {"cmp_scripts": scripts, "banner_elements": [sel for sel, _ in banners]}
    if not scripts and not banners:
        return RENDER_007.result(Severity.PASS, "No cookie/consent banner detected")
    if empty:
        msg = f"JS-only consent element(s) - rendered overlay may cover content: {', '.join(empty[:3])}"
        return RENDER_007.result(Severity.WARN, msg, details)
    if scripts and not banners:
        msg = f"CMP injected by JS with no HTML container: {', '.join(scripts[:3])}"
        return RENDER_007.result(Severity.WARN, msg, details)
    msg = "Consent elements found - verify they do not block main content when rendered"
    return RENDER_007.result(Severity.INFO, msg, details)


checks = {
    "RENDER-001": check_not_spa_dependent,
    "RENDER-002": check_noscript_fallback,
    "RENDER-003": check_framework_detected,
    "RENDER-004": check_content_visible_without_js,
    "RENDER-005": check_no_overlays,
    "RENDER-006": check_navigation_links_without_js,
    "RENDER-007": check_cookie_banner_googlebot,
}

if __name__ == "__main__":
    run_tool(C, checks, "JS rendering dependency checks")
