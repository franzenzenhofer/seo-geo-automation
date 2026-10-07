"""Homepage-specific SEO checks - root path, redirects, nav, brand, links."""

from __future__ import annotations

from urllib.parse import urlparse

from shared.html_parser import ParsedPage as Pg
from shared.html_parser import attr, first_tag, tags
from shared.http_client import HttpResponse as Rsp
from shared.tool_base import run_tool
from shared.types import CheckResult as R
from shared.types import Severity, SiteConfig

C, P, W, F, INF = "HOMEPAGE", Severity.PASS, Severity.WARN, Severity.FAIL, Severity.INFO


def check_is_root_domain(page: Pg, rsp: Rsp, cfg: SiteConfig | None) -> R:
    path = urlparse(rsp.final_url).path
    is_root = path in ("", "/")
    if not is_root:
        return R("HOME-001", "is_root_domain", C, INF, f"Not homepage (path={path}), skipping")
    return R("HOME-001", "is_root_domain", C, P, "URL is the root path /")


def check_no_redirect(page: Pg, rsp: Rsp, cfg: SiteConfig | None) -> R:
    if rsp.redirect_chain:
        hops = " -> ".join(h.url for h in rsp.redirect_chain)
        return R("HOME-002", "no_redirect", C, F, f"Homepage redirects: {hops}")
    return R("HOME-002", "no_redirect", C, P, "Homepage serves directly without redirects")


def check_links_to_important_pages(page: Pg, rsp: Rsp, cfg: SiteConfig | None) -> R:
    if not cfg or not cfg.important_pages:
        return R("HOME-003", "links_to_important_pages", C, INF, "No important_pages in config")
    hrefs = {attr(a, "href") for a in tags(page.soup, "a", href=True)}
    missing = [p.url for p in cfg.important_pages if not any(p.url in h for h in hrefs)]
    if missing:
        return R(
            "HOME-003",
            "links_to_important_pages",
            C,
            W,
            f"Missing links to: {', '.join(missing[:5])}",
            {"missing": missing},
        )
    return R(
        "HOME-003", "links_to_important_pages", C, P, f"All {len(cfg.important_pages)} important pages linked"
    )


def check_brand_in_title(page: Pg, rsp: Rsp, cfg: SiteConfig | None) -> R:
    if not cfg or not cfg.brand_name:
        return R("HOME-004", "brand_in_title", C, INF, "No brand_name in config, skipping")
    title_tag = page.soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""
    found = cfg.brand_name.lower() in title.lower()
    return R(
        "HOME-004",
        "brand_in_title",
        C,
        P if found else W,
        f"Brand '{cfg.brand_name}' {'found' if found else 'missing'} in title",
    )


def check_navigation_links_visible(page: Pg, rsp: Rsp, cfg: SiteConfig | None) -> R:
    nav = first_tag(page.soup, "nav")
    if nav is None:
        return R("HOME-005", "navigation_links_visible", C, W, "No <nav> element found")
    links = tags(nav, "a", href=True)
    real = [a for a in links if attr(a, "href").strip() not in ("", "#", "javascript:void(0)")]
    count = len(real)
    if count >= 3:
        return R("HOME-005", "navigation_links_visible", C, P, f"Nav has {count} real links")
    return R(
        "HOME-005", "navigation_links_visible", C, W, f"Nav has only {count} real link(s), expected >= 3"
    )


checks = {
    "HOME-001": check_is_root_domain,
    "HOME-002": check_no_redirect,
    "HOME-003": check_links_to_important_pages,
    "HOME-004": check_brand_in_title,
    "HOME-005": check_navigation_links_visible,
}

if __name__ == "__main__":
    run_tool("HOMEPAGE", checks, description="Homepage-specific SEO checks")
