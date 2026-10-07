"""Analytics detection: GA4, GTM, Universal Analytics and other trackers in the raw HTML."""

from __future__ import annotations

import re

from shared.html_parser import ParsedPage
from shared.http_client import HttpResponse
from shared.tool_base import run_tool
from shared.types import Check, CheckResult, Severity, SiteConfig

C = "ANALYTICS"
GA4_ID = r"G-[A-Z0-9]{7,}"
GTM_ID = r"GTM-[A-Z0-9]{5,}"
UA_ID = r"UA-\d{5,}-\d{1,2}"
GOOGLE_PATTERNS = (
    (GA4_ID, "GA4 Measurement ID"),
    (r"gtag\s*\(\s*['\"]config['\"]", "gtag config call"),
    (r"googletagmanager\.com/gtag", "GA4 gtag.js"),
    (GTM_ID, "GTM Container ID"),
    (r"googletagmanager\.com/gtm\.js", "GTM script"),
    (r"googletagmanager\.com/ns\.html", "GTM noscript"),
    (UA_ID, "Universal Analytics ID"),
    (r"google-analytics\.com/analytics\.js", "UA analytics.js"),
)
OTHER_ANALYTICS = (
    (r"matomo|piwik", "Matomo/Piwik"),
    (r"plausible\.io", "Plausible"),
    (r"analytics\.amplitude\.com", "Amplitude"),
    (r"hotjar\.com", "Hotjar"),
    (r"clarity\.ms", "Microsoft Clarity"),
    (r"connect\.facebook\.net", "Facebook Pixel"),
    (r"snap\.licdn\.com", "LinkedIn Insight"),
    (r"static\.ads-twitter\.com", "X/Twitter Pixel"),
    (r"bat\.bing\.com", "Bing UET"),
    (r"chartbeat\.com", "Chartbeat"),
    (r"segment\.com|cdn\.segment\.io", "Segment"),
    (r"mixpanel\.com", "Mixpanel"),
)

PRESENT = Check("ANALYTICS-001", "Analytics Present", C)
OTHER = Check("ANALYTICS-002", "Other Analytics", C)
IDS = Check("ANALYTICS-003", "Tracking IDs", C)


def google_tools(html: str) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    for pattern, name in GOOGLE_PATTERNS:
        matches = sorted(set(re.findall(pattern, html, re.IGNORECASE)))
        if matches:
            found.append({"tool": name, "ids": matches[:3]})
    return found


def check_analytics_present(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    """ANALYTICS-001: Google Analytics or Tag Manager is on the page."""
    found = google_tools(response.body)
    if not found:
        return PRESENT.result(Severity.WARN, "No Google Analytics or GTM detected on page")
    names = ", ".join(str(f["tool"]) for f in found)
    return PRESENT.result(Severity.PASS, f"Analytics detected: {names}", {"found": found})


def check_analytics_other(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    """ANALYTICS-002: Other analytics and tracking tools."""
    found = sorted({name for pattern, name in OTHER_ANALYTICS if re.search(pattern, response.body, re.I)})
    if found:
        return OTHER.result(Severity.INFO, f"Other tracking: {', '.join(found)}", {"tools": found})
    return OTHER.result(Severity.INFO, "No other analytics tools detected")


def check_gtm_container(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    """ANALYTICS-003: Tracking IDs (GTM, GA4, UA) for further investigation."""
    ids = {
        name: sorted(set(re.findall(p, response.body)))
        for name, p in (("gtm", GTM_ID), ("ga4", GA4_ID), ("ua", UA_ID))
    }
    flat = [i for values in ids.values() for i in values]
    if not flat:
        return IDS.result(Severity.WARN, "No tracking IDs found (GTM/GA4/UA)")
    return IDS.result(Severity.PASS, f"Tracking IDs: {', '.join(flat)}", dict(ids))


checks = {
    "ANALYTICS-001": check_analytics_present,
    "ANALYTICS-002": check_analytics_other,
    "ANALYTICS-003": check_gtm_container,
}

if __name__ == "__main__":
    run_tool(C, checks, "Analytics and tracking detection")
