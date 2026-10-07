"""Google Search Console and PageSpeed Insights checks (both optional, env-configured)."""

from __future__ import annotations

from shared.gsc_client import GscContext, GscUnavailable, gsc_context, page_top_queries, url_inspection
from shared.html_parser import ParsedPage
from shared.http_client import HttpResponse
from shared.psi import performance_score, run_psi
from shared.settings import ENV_GSC_CREDENTIALS
from shared.tool_base import run_tool
from shared.types import Check, CheckResult, Severity, SiteConfig

C = "GSC"
PSI_GOOD, PSI_OK = 90, 80

GSC_003 = Check("GSC-003", "GSC Connected", C)
GSC_004 = Check("GSC-004", "Page Indexed (URL Inspection)", C)
GSC_005 = Check("GSC-005", "Top Queries", C)


def _psi_check(cid: str, name: str, url: str, strategy: str) -> CheckResult:
    result = run_psi(url, strategy)
    if result.error:
        sev = Severity.INFO if result.skipped else Severity.ERROR
        return CheckResult(cid, name, C, sev, result.error)
    score = performance_score(result.data)
    if score is None:
        return CheckResult(cid, name, C, Severity.ERROR, "Could not parse PSI response")
    sev = Severity.PASS if score >= PSI_GOOD else Severity.WARN if score >= PSI_OK else Severity.FAIL
    return CheckResult(cid, name, C, sev, f"PSI {strategy}: {score:.0f}/100")


def check_psi_mobile(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    return _psi_check("GSC-001", "PSI Mobile Score", response.final_url, "mobile")


def check_psi_desktop(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    return _psi_check("GSC-002", "PSI Desktop Score", response.final_url, "desktop")


def check_gsc_available(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    ctx = gsc_context(config)
    if isinstance(ctx, GscUnavailable):
        return GSC_003.result(ctx.severity, ctx.reason)
    msg = f"GSC connected via {ENV_GSC_CREDENTIALS}, property {ctx.site_url}"
    return GSC_003.result(Severity.PASS, msg)


def _inspection_details(idx: dict[str, str]) -> dict[str, object]:
    return {
        "verdict": idx.get("verdict", "UNKNOWN"),
        "coverage": idx.get("coverageState", ""),
        "lastCrawled": idx.get("lastCrawlTime", ""),
        "robotsTxt": idx.get("robotsTxtState", ""),
        "indexing": idx.get("indexingState", ""),
    }


def check_gsc_indexed(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    ctx = gsc_context(config)
    if isinstance(ctx, GscUnavailable):
        return GSC_004.result(ctx.severity, ctx.reason)
    result = url_inspection(ctx, response.final_url)
    if "error" in result:
        return GSC_004.result(Severity.WARN, f"GSC error: {result['error']}")
    idx = result.get("indexStatusResult", {})
    details = _inspection_details(idx)
    if details["verdict"] == "PASS":
        crawled = str(details["lastCrawled"])[:10] or "unknown"
        msg = f"Indexed (crawled: {crawled}, {details['coverage']})"
        return GSC_004.result(Severity.PASS, msg, details)
    msg = f"GSC verdict: {details['verdict']} - {details['coverage']}"
    return GSC_004.result(Severity.WARN, msg, details)


def _top_queries(ctx: GscContext, url: str) -> CheckResult:
    data = page_top_queries(ctx, url)
    if "error" in data:
        return GSC_005.result(Severity.WARN, f"Error: {data['error']}")
    queries = [
        {"query": r["keys"][0], "clicks": r["clicks"], "impressions": r["impressions"]}
        for r in data.get("rows", [])[:5]
    ]
    return GSC_005.result(Severity.INFO, f"Top {len(queries)} queries", {"queries": queries})


def check_gsc_top_queries(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    ctx = gsc_context(config)
    if isinstance(ctx, GscUnavailable):
        return GSC_005.result(ctx.severity, ctx.reason)
    return _top_queries(ctx, response.final_url)


checks = {
    "GSC-001": check_psi_mobile,
    "GSC-002": check_psi_desktop,
    "GSC-003": check_gsc_available,
    "GSC-004": check_gsc_indexed,
    "GSC-005": check_gsc_top_queries,
}

if __name__ == "__main__":
    run_tool(C, checks, "Google Search Console / PSI checks")
