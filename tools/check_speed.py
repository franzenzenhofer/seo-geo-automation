"""SPEED/performance checks: response time, render-blocking, images, PSI scores, Core Web Vitals.

Core Web Vitals thresholds follow web.dev (good / poor):
LCP 2500/4000 ms https://web.dev/articles/lcp, INP 200/500 ms https://web.dev/articles/inp,
CLS 0.1/0.25 https://web.dev/articles/cls, FCP 1800/3000 ms https://web.dev/articles/fcp,
TTFB 800/1800 ms https://web.dev/articles/ttfb.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from shared.html_parser import ParsedPage, attr, get_images, get_scripts_in_head, tags
from shared.http_client import HttpResponse
from shared.psi import PsiResult, audit_value, field_percentile, performance_score, run_psi
from shared.tool_base import run_tool
from shared.types import CheckResult, Severity, SiteConfig

CAT = "SPEED"
P, W, F, INF, E = Severity.PASS, Severity.WARN, Severity.FAIL, Severity.INFO, Severity.ERROR
FONT_CDNS = ("fonts.googleapis.com", "fonts.gstatic.com", "use.typekit.net")
FONT_FACE = re.compile(r"@font-face\s*\{[^}]*\}", re.S)
ABOVE_FOLD_IMAGES = 3


@dataclass(frozen=True)
class Metric:
    check_id: str
    name: str
    field_key: str
    lab_audit: str
    good: float
    poor: float
    field_scale: float = 1.0


CWV = {
    "lcp": Metric(
        "SPEED-014", "psi_cwv_lcp", "LARGEST_CONTENTFUL_PAINT_MS", "largest-contentful-paint", 2500, 4000
    ),
    "cls": Metric(
        "SPEED-015",
        "psi_cwv_cls",
        "CUMULATIVE_LAYOUT_SHIFT_SCORE",
        "cumulative-layout-shift",
        0.1,
        0.25,
        0.01,
    ),
    "inp": Metric("SPEED-016", "psi_cwv_inp", "INTERACTION_TO_NEXT_PAINT", "total-blocking-time", 200, 500),
    "fcp": Metric(
        "SPEED-017", "psi_cwv_fcp", "FIRST_CONTENTFUL_PAINT_MS", "first-contentful-paint", 1800, 3000
    ),
    "ttfb": Metric(
        "SPEED-018", "psi_ttfb", "EXPERIMENTAL_TIME_TO_FIRST_BYTE", "server-response-time", 800, 1800
    ),
}


def _grade(value: float, good: float, poor: float) -> Severity:
    return P if value <= good else W if value <= poor else F


def _psi_problem(cid: str, name: str, result: PsiResult) -> CheckResult | None:
    if not result.error:
        return None
    return CheckResult(cid, name, CAT, INF if result.skipped else E, result.error)


def _metric_check(metric: Metric, url: str) -> CheckResult:
    """Prefer CrUX field data (75th percentile); fall back to the Lighthouse lab value, labelled."""
    result = run_psi(url, "mobile")
    problem = _psi_problem(metric.check_id, metric.name, result)
    if problem:
        return problem
    field = field_percentile(result.data, metric.field_key)
    value, source = (
        (field * metric.field_scale, "field")
        if field is not None
        else (audit_value(result.data, metric.lab_audit), "lab")
    )
    if value is None:
        return CheckResult(metric.check_id, metric.name, CAT, E, f"{metric.name} not in PSI response")
    label = metric.lab_audit if source == "lab" else metric.field_key
    sev = _grade(value, metric.good, metric.poor)
    return CheckResult(metric.check_id, metric.name, CAT, sev, f"{label} ({source}): {value:g}")


def _score_check(cid: str, name: str, url: str, strategy: str) -> CheckResult:
    result = run_psi(url, strategy)
    problem = _psi_problem(cid, name, result)
    if problem:
        return problem
    score = performance_score(result.data)
    if score is None:
        return CheckResult(cid, name, CAT, E, f"PSI missing score ({strategy})")
    return CheckResult(cid, name, CAT, _grade(100 - score, 10, 20), f"PSI {strategy}: {score:.0f}/100")


def check_response_time_html(p: ParsedPage, r: HttpResponse, c: SiteConfig | None) -> CheckResult:
    ms = r.response_time_ms
    return CheckResult("SPEED-001", "response_time_html", CAT, _grade(ms, 400, 800), f"HTML {ms:.0f}ms")


def check_blocking_scripts(p: ParsedPage, r: HttpResponse, c: SiteConfig | None) -> CheckResult:
    blocking = [s for s in get_scripts_in_head(p) if s["blocking"]]
    if not blocking:
        return CheckResult("SPEED-002", "blocking_scripts", CAT, P, "No render-blocking scripts")
    return CheckResult("SPEED-002", "blocking_scripts", CAT, F, f"{len(blocking)} blocking script(s)")


def check_preload_links(p: ParsedPage, r: HttpResponse, c: SiteConfig | None) -> CheckResult:
    count = len(tags(p.head, "link", rel="preload"))
    return CheckResult("SPEED-003", "preload_links", CAT, INF, f"{count} preload(s)")


def check_preconnect_links(p: ParsedPage, r: HttpResponse, c: SiteConfig | None) -> CheckResult:
    count = len(tags(p.head, "link", rel="preconnect"))
    return CheckResult("SPEED-004", "preconnect_links", CAT, INF, f"{count} preconnect(s)")


def check_font_display(p: ParsedPage, r: HttpResponse, c: SiteConfig | None) -> CheckResult:
    faces = [f for s in tags(p.head, "style") for f in FONT_FACE.findall(s.string or "")]
    if not faces:
        return CheckResult("SPEED-005", "font_display", CAT, INF, "No inline @font-face")
    missing = sum(1 for f in faces if "font-display" not in f or "swap" not in f)
    if missing:
        return CheckResult("SPEED-005", "font_display", CAT, W, f"{missing} @font-face missing swap")
    return CheckResult("SPEED-005", "font_display", CAT, P, "All @font-face have font-display: swap")


def check_no_third_party_fonts(p: ParsedPage, r: HttpResponse, c: SiteConfig | None) -> CheckResult:
    hrefs = [attr(link, "href") for link in tags(p.head, "link", href=True)]
    bad = [h for h in hrefs if any(cdn in h for cdn in FONT_CDNS)]
    sev = W if bad else P
    return CheckResult("SPEED-006", "no_third_party_fonts", CAT, sev, f"{len(bad)} 3rd-party font link(s)")


def check_images_have_dimensions(p: ParsedPage, r: HttpResponse, c: SiteConfig | None) -> CheckResult:
    imgs = get_images(p)
    if not imgs:
        return CheckResult("SPEED-007", "images_have_dimensions", CAT, P, "No images")
    missing = sum(1 for i in imgs if not i["has_dimensions"])
    msg = f"{missing}/{len(imgs)} missing dimensions"
    return CheckResult("SPEED-007", "images_have_dimensions", CAT, W if missing else P, msg)


def check_above_fold_not_lazy(p: ParsedPage, r: HttpResponse, c: SiteConfig | None) -> CheckResult:
    first = get_images(p)[:ABOVE_FOLD_IMAGES]
    if not first:
        return CheckResult("SPEED-008", "above_fold_not_lazy", CAT, INF, "No images")
    lazy = sum(1 for i in first if i["loading"] == "lazy")
    msg = f"{lazy}/{len(first)} above-fold images lazy-loaded"
    return CheckResult("SPEED-008", "above_fold_not_lazy", CAT, W if lazy else P, msg)


def check_below_fold_lazy(p: ParsedPage, r: HttpResponse, c: SiteConfig | None) -> CheckResult:
    rest = get_images(p)[ABOVE_FOLD_IMAGES:]
    if not rest:
        return CheckResult("SPEED-009", "below_fold_lazy", CAT, INF, f"<={ABOVE_FOLD_IMAGES} images")
    eager = sum(1 for i in rest if i["loading"] != "lazy")
    msg = f"{eager}/{len(rest)} below-fold not lazy"
    return CheckResult("SPEED-009", "below_fold_lazy", CAT, W if eager else P, msg)


def check_css_in_head_size(p: ParsedPage, r: HttpResponse, c: SiteConfig | None) -> CheckResult:
    sheets, inline = len(tags(p.head, "link", rel="stylesheet")), len(tags(p.head, "style"))
    return CheckResult("SPEED-010", "css_in_head_size", CAT, INF, f"{sheets} CSS, {inline} inline")


def check_psi_mobile_score(p: ParsedPage, r: HttpResponse, c: SiteConfig | None) -> CheckResult:
    return _score_check("SPEED-011", "psi_mobile_score", r.final_url, "mobile")


def check_psi_desktop_score(p: ParsedPage, r: HttpResponse, c: SiteConfig | None) -> CheckResult:
    return _score_check("SPEED-012", "psi_desktop_score", r.final_url, "desktop")


def check_dom_size(p: ParsedPage, r: HttpResponse, c: SiteConfig | None) -> CheckResult:
    if p.body is None:
        return CheckResult("SPEED-013", "dom_size", CAT, INF, "No <body>")
    n = len(tags(p.body, True))
    return CheckResult("SPEED-013", "dom_size", CAT, W if n > 1500 else INF, f"{n} DOM elements")


def check_psi_cwv_lcp(p: ParsedPage, r: HttpResponse, c: SiteConfig | None) -> CheckResult:
    return _metric_check(CWV["lcp"], r.final_url)


def check_psi_cwv_cls(p: ParsedPage, r: HttpResponse, c: SiteConfig | None) -> CheckResult:
    return _metric_check(CWV["cls"], r.final_url)


def check_psi_cwv_inp(p: ParsedPage, r: HttpResponse, c: SiteConfig | None) -> CheckResult:
    """Field INP when CrUX has it; otherwise lab Total Blocking Time as a proxy."""
    return _metric_check(CWV["inp"], r.final_url)


def check_psi_cwv_fcp(p: ParsedPage, r: HttpResponse, c: SiteConfig | None) -> CheckResult:
    return _metric_check(CWV["fcp"], r.final_url)


def check_psi_ttfb(p: ParsedPage, r: HttpResponse, c: SiteConfig | None) -> CheckResult:
    return _metric_check(CWV["ttfb"], r.final_url)


def check_html_size(p: ParsedPage, r: HttpResponse, c: SiteConfig | None) -> CheckResult:
    kb = len(r.body.encode("utf-8")) / 1024
    return CheckResult("SPEED-019", "html_size", CAT, _grade(kb, 100, 200), f"HTML: {kb:.0f}KB")


checks = {
    "SPEED-001": check_response_time_html,
    "SPEED-002": check_blocking_scripts,
    "SPEED-003": check_preload_links,
    "SPEED-004": check_preconnect_links,
    "SPEED-005": check_font_display,
    "SPEED-006": check_no_third_party_fonts,
    "SPEED-007": check_images_have_dimensions,
    "SPEED-008": check_above_fold_not_lazy,
    "SPEED-009": check_below_fold_lazy,
    "SPEED-010": check_css_in_head_size,
    "SPEED-011": check_psi_mobile_score,
    "SPEED-012": check_psi_desktop_score,
    "SPEED-013": check_dom_size,
    "SPEED-014": check_psi_cwv_lcp,
    "SPEED-015": check_psi_cwv_cls,
    "SPEED-016": check_psi_cwv_inp,
    "SPEED-017": check_psi_cwv_fcp,
    "SPEED-018": check_psi_ttfb,
    "SPEED-019": check_html_size,
}

if __name__ == "__main__":
    run_tool(CAT, checks, "SEO speed/performance audit checks")
