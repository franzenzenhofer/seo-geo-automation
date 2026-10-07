"""HTTP/protocol SEO checks."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from shared.html_parser import ParsedPage
from shared.http_client import HttpResponse, fetch, fetch_head
from shared.tool_base import run_tool
from shared.types import CheckResult, Severity, SiteConfig

CAT = "HTTP"


def _result(cid: str, name: str, sev: Severity, msg: str, **kw: object) -> CheckResult:
    return CheckResult(check_id=cid, name=name, category=CAT, severity=sev, message=msg, details=dict(kw))


def check_status_ok(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    ok = response.status_code == 200
    return _result(
        "HTTP-001",
        "status_ok",
        Severity.PASS if ok else Severity.FAIL,
        f"Status {response.status_code}",
        status_code=response.status_code,
    )


def check_gzip_or_brotli(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    enc = response.headers.get("Content-Encoding", "").lower()
    ok = "br" in enc or "gzip" in enc
    return _result(
        "HTTP-002",
        "gzip_or_brotli",
        Severity.PASS if ok else Severity.WARN,
        f"Content-Encoding: {enc or 'none'}",
        encoding=enc,
    )


def check_https_scheme(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    ok = urlparse(response.final_url).scheme == "https"
    return _result(
        "HTTP-003",
        "https_scheme",
        Severity.PASS if ok else Severity.FAIL,
        f"Scheme: {urlparse(response.final_url).scheme}",
        url=response.final_url,
    )


def check_hsts_header(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    val = response.headers.get("Strict-Transport-Security", "")
    return _result(
        "HTTP-004",
        "hsts_header",
        Severity.PASS if val else Severity.WARN,
        f"HSTS: {val or 'missing'}",
        hsts=val,
    )


def check_no_mixed_content(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    if urlparse(response.final_url).scheme != "https":
        return _result("HTTP-005", "no_mixed_content", Severity.INFO, "Page not HTTPS, skipping")
    pattern = re.compile(r'(?:src|href)\s*=\s*["\']http://[^"\']+["\']', re.IGNORECASE)
    matches = pattern.findall(response.body or "")
    ok = len(matches) == 0
    return _result(
        "HTTP-005",
        "no_mixed_content",
        Severity.PASS if ok else Severity.FAIL,
        f"{len(matches)} mixed content references",
        count=len(matches),
        samples=matches[:5],
    )


def check_redirect_chain(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    n = len(response.redirect_chain)
    sev = Severity.PASS if n == 0 else (Severity.WARN if n == 1 else Severity.FAIL)
    urls = [h.url for h in response.redirect_chain]
    return _result("HTTP-006", "redirect_chain", sev, f"Redirect chain length: {n}", chain=urls)


def check_redirect_permanent(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    if not response.redirect_chain:
        return _result("HTTP-007", "redirect_permanent", Severity.PASS, "No redirects")
    non_perm = [h for h in response.redirect_chain if h.status_code not in (301, 308)]
    ok = len(non_perm) == 0
    codes = [{"url": h.url, "status": h.status_code} for h in non_perm]
    return _result(
        "HTTP-007",
        "redirect_permanent",
        Severity.PASS if ok else Severity.WARN,
        f"{len(non_perm)} non-permanent redirects",
        non_permanent=codes,
    )


def check_no_redirect_loop(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    urls = [h.url for h in response.redirect_chain]
    dupes = [u for u in urls if urls.count(u) > 1]
    ok = len(dupes) == 0
    return _result(
        "HTTP-008",
        "no_redirect_loop",
        Severity.PASS if ok else Severity.FAIL,
        "No loop detected" if ok else f"Loop detected: {dupes[0]}",
        duplicates=list(set(dupes)),
    )


def check_response_time(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    ms = response.response_time_ms
    sev = Severity.PASS if ms < 400 else (Severity.WARN if ms <= 1000 else Severity.FAIL)
    return _result("HTTP-009", "response_time", sev, f"Response time: {ms:.0f}ms", time_ms=round(ms))


def check_security_headers(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    expected = {"Content-Security-Policy": "CSP", "X-Content-Type-Options": "XCTO", "Referrer-Policy": "RP"}
    missing = [label for hdr, label in expected.items() if not response.headers.get(hdr)]
    sev = Severity.PASS if not missing else (Severity.WARN if len(missing) < 3 else Severity.FAIL)
    return _result(
        "HTTP-010",
        "security_headers",
        sev,
        f"Missing: {', '.join(missing)}" if missing else "All present",
        missing=missing,
    )


def check_x_robots_tag(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    val = response.headers.get("X-Robots-Tag", "").lower()
    blocked = "noindex" in val
    return _result(
        "HTTP-011",
        "x_robots_tag",
        Severity.FAIL if blocked else Severity.PASS,
        f"X-Robots-Tag: {val or 'none'}",
        value=val,
        blocked=blocked,
    )


def check_soft_404(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    parsed = urlparse(response.final_url)
    base = parsed.path.rsplit("/", 1)[0] + "/"
    fake_url = urljoin(response.final_url, base + "zz-nonexistent-page-test-98765")
    probe = fetch_head(fake_url)
    ok = probe.status_code in (404, 410)
    return _result(
        "HTTP-012",
        "soft_404",
        Severity.PASS if ok else Severity.WARN,
        f"Fake URL returned {probe.status_code}",
        probe_url=fake_url,
        probe_status=probe.status_code,
    )


def check_www_redirect(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    parsed = urlparse(response.final_url)
    host = parsed.hostname or ""
    alt_host = host[4:] if host.startswith("www.") else f"www.{host}"
    alt_url = parsed._replace(netloc=alt_host + (f":{parsed.port}" if parsed.port else "")).geturl()
    probe = fetch(alt_url, follow_redirects=True)
    if probe.error:
        return _result(
            "HTTP-013", "www_redirect", Severity.INFO, f"{alt_host} does not resolve (fine if unused)"
        )
    chain_len = len(probe.redirect_chain)
    is_301 = all(h.status_code == 301 for h in probe.redirect_chain) if probe.redirect_chain else True
    ok = chain_len == 1 and is_301
    sev = Severity.PASS if ok else (Severity.WARN if chain_len <= 1 else Severity.FAIL)
    return _result(
        "HTTP-013",
        "www_redirect",
        sev,
        f"www variant: {chain_len} hops, all-301={is_301}",
        alt_url=alt_url,
        hops=chain_len,
    )


def check_http2_or_h3(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    alt_svc = response.headers.get("Alt-Svc", "")
    has_h2 = "h2" in alt_svc.lower()
    has_h3 = "h3" in alt_svc.lower()
    ok = has_h2 or has_h3
    return _result(
        "HTTP-014",
        "http2_or_h3",
        Severity.PASS if ok else Severity.INFO,
        f"Alt-Svc: {alt_svc or 'none'}",
        alt_svc=alt_svc,
        h2=has_h2,
        h3=has_h3,
    )


checks = {
    "HTTP-001": check_status_ok,
    "HTTP-002": check_gzip_or_brotli,
    "HTTP-003": check_https_scheme,
    "HTTP-004": check_hsts_header,
    "HTTP-005": check_no_mixed_content,
    "HTTP-006": check_redirect_chain,
    "HTTP-007": check_redirect_permanent,
    "HTTP-008": check_no_redirect_loop,
    "HTTP-009": check_response_time,
    "HTTP-010": check_security_headers,
    "HTTP-011": check_x_robots_tag,
    "HTTP-012": check_soft_404,
    "HTTP-013": check_www_redirect,
    "HTTP-014": check_http2_or_h3,
}

if __name__ == "__main__":
    run_tool("HTTP", checks)
