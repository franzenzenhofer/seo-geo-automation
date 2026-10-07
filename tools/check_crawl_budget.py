"""Crawl budget estimate: back-of-the-envelope crawl math over the sitemap.

Model: days_to_crawl = total_urls / (crawl_rate_per_day x crawl_efficiency).
A full recrawl should take well under 30 days so ranking effects of changes can be observed.
The crawl rate and efficiency below are rough planning assumptions, not Google-published numbers.
"""

from __future__ import annotations

from functools import lru_cache

from shared.gsc_client import GscUnavailable, gsc_context, sitemap_summary
from shared.html_parser import ParsedPage
from shared.http_client import HttpResponse
from shared.sitemap_xml import SitemapCrawl, crawl_sitemaps, sitemap_url_for
from shared.tool_base import run_tool
from shared.types import Check, CheckResult, Severity, SiteConfig

C = "CRAWL_BUDGET"
CRAWL_EFFICIENCY = 0.7
PESSIMISTIC_EFFICIENCY = 0.5
DEFAULT_CRAWL_RATE = 400_000
BEST_CASE_CRAWL_RATE = 800_000
MAX_DAYS_TARGET = 30
QUICK_DAYS = 7
MAX_PAGES_THEORETICAL = 25_000_000
LARGE_SITE_PAGES = 10_000_000
SAMPLE_URLS = 500
NO_SITEMAP = "Could not determine total URL count from sitemap"

BUDGET_001 = Check("BUDGET-001", "Crawl Time Estimate", C)
BUDGET_002 = Check("BUDGET-002", "Dead Weight Ratio", C)
BUDGET_003 = Check("BUDGET-003", "Max Pages Limit", C)
BUDGET_004 = Check("BUDGET-004", "Crawl Efficiency Signals", C)
BUDGET_005 = Check("BUDGET-005", "GSC Sitemap Submissions", C)


@lru_cache(maxsize=2)
def _crawl(sitemap_url: str) -> SitemapCrawl:
    return crawl_sitemaps(sitemap_url)


def _total(config: SiteConfig | None, response: HttpResponse) -> int:
    return len(_crawl(sitemap_url_for(config, response.final_url)).urls)


def check_crawl_time_estimate(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    """BUDGET-001: Estimated days for a full crawl of all sitemap URLs."""
    total = _total(config, response)
    if total == 0:
        return BUDGET_001.result(Severity.WARN, NO_SITEMAP)
    days = total / (DEFAULT_CRAWL_RATE * CRAWL_EFFICIENCY)
    details: dict[str, object] = {
        "total_urls": total,
        "crawl_efficiency": CRAWL_EFFICIENCY,
        "days_conservative": round(days, 1),
        "days_pessimistic": round(total / (DEFAULT_CRAWL_RATE * PESSIMISTIC_EFFICIENCY), 1),
        "days_best_case": round(total / (BEST_CASE_CRAWL_RATE * CRAWL_EFFICIENCY), 1),
        "formula": f"{total} / ({DEFAULT_CRAWL_RATE} x {CRAWL_EFFICIENCY}) = {days:.1f} days",
    }
    sev = Severity.FAIL if days > MAX_DAYS_TARGET else Severity.WARN if days > QUICK_DAYS else Severity.PASS
    msg = f"Full crawl takes ~{days:.1f} days for {total} URLs (target < {MAX_DAYS_TARGET} days)"
    return BUDGET_001.result(sev, msg, details)


def check_deadweight_ratio(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    """BUDGET-002: Share of targeted pages among all sitemap URLs."""
    total = _total(config, response)
    if total == 0:
        return BUDGET_002.result(Severity.WARN, NO_SITEMAP)
    targeted = len(config.important_pages) if config else 0
    if targeted == 0:
        msg = f"{total} URLs in sitemap, no important_pages configured to compare"
        return BUDGET_002.result(Severity.INFO, msg)
    ratio = targeted / total
    details: dict[str, object] = {
        "total_urls": total,
        "targeted_pages": targeted,
        "targeted_ratio": round(ratio, 4),
    }
    msg = f"{targeted}/{total} sitemap URLs are targeted pages ({ratio:.1%})"
    sev = Severity.WARN if ratio < 0.01 else Severity.INFO if ratio < 0.1 else Severity.PASS
    return BUDGET_002.result(sev, msg, details)


def check_max_pages_limit(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    """BUDGET-003: Total URL count against a practical per-domain ceiling."""
    total = _total(config, response)
    if total == 0:
        return BUDGET_003.result(Severity.WARN, NO_SITEMAP)
    details: dict[str, object] = {"total_urls": total, "theoretical_max": MAX_PAGES_THEORETICAL}
    if total > MAX_PAGES_THEORETICAL:
        sev, msg = (
            Severity.FAIL,
            f"{total} URLs exceeds {MAX_PAGES_THEORETICAL:,} - consider splitting domains",
        )
    elif total > LARGE_SITE_PAGES:
        sev, msg = Severity.WARN, f"{total} URLs - approaching the limit, monitor crawl health"
    else:
        sev, msg = Severity.PASS, f"{total} URLs - well within limits"
    return BUDGET_003.result(sev, msg, details)


def _efficiency_issues(urls: list[str]) -> tuple[list[str], dict[str, object]]:
    params = [u for u in urls if "?" in u]
    seen: set[str] = set()
    dupes = []
    for u in urls:
        if u.rstrip("/") in seen:
            dupes.append(u)
        seen.add(u.rstrip("/"))
    non_https = [u for u in urls if not u.startswith("https://")]
    issues = [
        f"{n} {label}"
        for n, label in (
            (len(params), "URLs with query parameters"),
            (len(dupes), "duplicate URLs (trailing slash variants)"),
            (len(non_https), "non-HTTPS URLs"),
        )
        if n
    ]
    details: dict[str, object] = {
        "total_checked": len(urls),
        "param_urls": len(params),
        "duplicates": len(dupes),
        "non_https": len(non_https),
        "examples_param": params[:3],
        "examples_dupe": dupes[:3],
    }
    return issues, details


def check_crawl_efficiency_signals(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    """BUDGET-004: Sitemap signals that waste crawls (params, duplicates, http URLs)."""
    urls = _crawl(sitemap_url_for(config, response.final_url)).urls[:SAMPLE_URLS]
    if not urls:
        return BUDGET_004.result(Severity.WARN, "Could not collect URLs from sitemap")
    issues, details = _efficiency_issues(urls)
    if issues:
        return BUDGET_004.result(Severity.WARN, f"Issues: {'; '.join(issues)}", details)
    msg = f"No crawl efficiency issues in {len(urls)} sampled sitemap URLs"
    return BUDGET_004.result(Severity.PASS, msg, details)


def check_gsc_crawl_stats(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    """BUDGET-005: URLs submitted via sitemaps in GSC compared with the live sitemap count."""
    ctx = gsc_context(config)
    if isinstance(ctx, GscUnavailable):
        return BUDGET_005.result(ctx.severity, ctx.reason)
    summary = sitemap_summary(ctx)
    if "error" in summary:
        return BUDGET_005.result(Severity.WARN, f"GSC error: {summary['error']}")
    if not summary["sitemaps"]:
        return BUDGET_005.result(Severity.WARN, "No sitemaps in GSC - submit your sitemap")
    live = _total(config, response)
    details = {**summary, "live_sitemap_urls": live}
    msg = f"GSC knows {summary['submitted']} submitted URLs; live sitemaps list {live}"
    sev = Severity.WARN if live and summary["submitted"] < live else Severity.INFO
    return BUDGET_005.result(sev, msg, details)


checks = {
    "BUDGET-001": check_crawl_time_estimate,
    "BUDGET-002": check_deadweight_ratio,
    "BUDGET-003": check_max_pages_limit,
    "BUDGET-004": check_crawl_efficiency_signals,
    "BUDGET-005": check_gsc_crawl_stats,
}

if __name__ == "__main__":
    run_tool(C, checks, "Crawl budget estimate")
