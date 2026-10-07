"""Sitemap and distribution checks: XML sitemaps, news sitemaps, feeds, robots.txt declaration.

Sitemap limits (50,000 URLs per file): https://www.sitemaps.org/protocol.html
News sitemaps: https://developers.google.com/search/docs/crawling-indexing/sitemaps/news-sitemap
"""

from __future__ import annotations

from collections import Counter
from urllib.parse import urlparse

from shared.gsc_client import GscUnavailable, gsc_context, sitemap_summary
from shared.html_parser import ParsedPage, attr, get_links, get_meta_robots, tags
from shared.http_client import HttpResponse, fetch
from shared.sitemap_xml import (
    NEWS_NS,
    SM_NS,
    child_sitemap_locs,
    crawl_sitemaps,
    fetch_sitemap_root,
    news_sitemap_candidates,
    parse_xml,
    robots_sitemap_directives,
    robots_url_for,
    site_base,
    sitemap_url_for,
    url_entries,
)
from shared.tool_base import run_tool
from shared.types import Check, CheckResult, Severity, SiteConfig

C = "SITEMAP"
MAX_URLS_PER_SITEMAP = 50_000
FEED_PATHS = ("feed", "feed/", "rss", "rss.xml", "atom.xml", "feed.xml", "index.rss")
SEGMENT_LABELS = ("news", "post", "page", "product", "categor", "tag", "video", "image", "author")

SITEMAP_001 = Check("SITEMAP-001", "Sitemap Exists", C)
SITEMAP_002 = Check("SITEMAP-002", "Sitemap Valid XML", C)
SITEMAP_003 = Check("SITEMAP-003", "Sitemap URL Count", C)
SITEMAP_004 = Check("SITEMAP-004", "Sitemap Has Lastmod", C)
SITEMAP_005 = Check("SITEMAP-005", "Page in Sitemap", C)
SITEMAP_006 = Check("SITEMAP-006", "Noindex Not in Sitemap", C)
SITEMAP_007 = Check("SITEMAP-007", "Total Sitemap URLs", C)
SITEMAP_008 = Check("SITEMAP-008", "Sitemap GSC Cross-check", C)
SITEMAP_009 = Check("SITEMAP-009", "Important Pages in Sitemap", C)
SITEMAP_010 = Check("SITEMAP-010", "Google News Sitemap", C)
SITEMAP_011 = Check("SITEMAP-011", "RSS/Atom Feed", C)
SITEMAP_012 = Check("SITEMAP-012", "Sitemap Declared in robots.txt", C)
SITEMAP_013 = Check("SITEMAP-013", "Sitemap Completeness", C)
SITEMAP_014 = Check("SITEMAP-014", "Sitemap Segmentation", C)
SITEMAP_015 = Check("SITEMAP-015", "News Sitemap Valid", C)


def _sitemap(response: HttpResponse, config: SiteConfig | None) -> tuple[HttpResponse, str]:
    url = sitemap_url_for(config, response.final_url)
    return fetch(url), url


def _url_in_body(url: str, body: str) -> bool:
    page_url = url.rstrip("/")
    return page_url in body or page_url + "/" in body


def check_sitemap_exists(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    resp, url = _sitemap(response, config)
    if resp.status_code == 200:
        return SITEMAP_001.result(Severity.PASS, f"Sitemap found at {url}")
    return SITEMAP_001.result(Severity.FAIL, f"Sitemap returned {resp.status_code}: {url}")


def check_sitemap_valid_xml(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    resp, _ = _sitemap(response, config)
    if resp.status_code != 200:
        return SITEMAP_002.result(Severity.INFO, "No sitemap")
    if parse_xml(resp.body) is None:
        return SITEMAP_002.result(Severity.FAIL, "Sitemap is not well-formed XML")
    return SITEMAP_002.result(Severity.PASS, "Sitemap is valid XML")


def check_sitemap_url_count(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    resp, _ = _sitemap(response, config)
    root = parse_xml(resp.body) if resp.status_code == 200 else None
    if root is None:
        return SITEMAP_003.result(Severity.INFO, "No parseable sitemap")
    children = child_sitemap_locs(root)
    if children:
        return SITEMAP_003.result(Severity.INFO, f"Sitemap index with {len(children)} children")
    count = len(url_entries(root))
    if count > MAX_URLS_PER_SITEMAP:
        msg = f"{count} URLs exceeds {MAX_URLS_PER_SITEMAP:,} limit - use a sitemap index"
        return SITEMAP_003.result(Severity.WARN, msg)
    return SITEMAP_003.result(Severity.PASS, f"{count} URLs in sitemap")


def check_sitemap_has_lastmod(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    resp, _ = _sitemap(response, config)
    root = parse_xml(resp.body) if resp.status_code == 200 else None
    entries = url_entries(root) if root is not None else []
    if not entries:
        return SITEMAP_004.result(Severity.INFO, "No URL entries to check")
    dated = sum(
        1 for u in entries if u.find("sm:lastmod", SM_NS) is not None or u.find("lastmod") is not None
    )
    pct = dated / len(entries) * 100
    sev = Severity.PASS if pct >= 90 else Severity.WARN
    return SITEMAP_004.result(sev, f"{dated}/{len(entries)} URLs have lastmod ({pct:.0f}%)")


def check_page_in_sitemap(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    resp, _ = _sitemap(response, config)
    if resp.status_code != 200:
        return SITEMAP_005.result(Severity.INFO, "No sitemap")
    if _url_in_body(response.final_url, resp.body):
        return SITEMAP_005.result(Severity.PASS, "Current page URL found in sitemap")
    return SITEMAP_005.result(Severity.WARN, "Current page URL NOT found in sitemap")


def check_noindex_not_in_sitemap(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    if not get_meta_robots(page)["has_noindex"]:
        return SITEMAP_006.result(Severity.INFO, "Page is indexable - check not applicable")
    resp, _ = _sitemap(response, config)
    if resp.status_code != 200:
        return SITEMAP_006.result(Severity.INFO, "No sitemap")
    if _url_in_body(response.final_url, resp.body):
        return SITEMAP_006.result(Severity.FAIL, "Noindex page found in sitemap - contradictory signals")
    return SITEMAP_006.result(Severity.PASS, "Noindex page correctly absent from sitemap")


def check_sitemap_total_urls(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    """SITEMAP-007: Total URLs across all sitemaps (follows sitemap indexes)."""
    crawl = crawl_sitemaps(sitemap_url_for(config, response.final_url))
    if crawl.sitemap_count == 0:
        return SITEMAP_007.result(Severity.WARN, "Could not fetch or parse sitemap")
    msg = f"{len(crawl.urls)} total URLs across {crawl.sitemap_count} sitemap(s)"
    details: dict[str, object] = {"total_urls": len(crawl.urls), "sitemap_count": crawl.sitemap_count}
    return SITEMAP_007.result(Severity.INFO, msg, details)


def check_sitemap_gsc_crosscheck(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    """SITEMAP-008: The site's sitemap is registered in GSC and GSC reports no errors for it."""
    ctx = gsc_context(config)
    if isinstance(ctx, GscUnavailable):
        return SITEMAP_008.result(ctx.severity, ctx.reason)
    summary = sitemap_summary(ctx)
    if "error" in summary:
        return SITEMAP_008.result(Severity.WARN, f"GSC sitemaps error: {summary['error']}")
    expected = sitemap_url_for(config, response.final_url)
    registered = [str(r["path"]) for r in summary["sitemaps"]]
    if expected not in registered:
        msg = f"{expected} is not registered in GSC (registered: {len(registered)})"
        return SITEMAP_008.result(Severity.WARN, msg, summary)
    if summary["errors"]:
        return SITEMAP_008.result(Severity.FAIL, f"GSC reports {summary['errors']} sitemap error(s)", summary)
    msg = f"Sitemap registered in GSC, {summary['submitted']} URLs submitted, no errors"
    return SITEMAP_008.result(Severity.PASS, msg, summary)


def check_important_pages_in_sitemap(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    """SITEMAP-009: All important_pages from the config must be in the sitemap."""
    if not config or not config.important_pages:
        return SITEMAP_009.result(Severity.INFO, "No important_pages in config")
    listed = {u.rstrip("/") for u in crawl_sitemaps(sitemap_url_for(config, response.final_url)).urls}
    missing = [p.url for p in config.important_pages if p.url.rstrip("/") not in listed]
    total = len(config.important_pages)
    if missing:
        msg = f"{len(missing)}/{total} important pages NOT in sitemap"
        return SITEMAP_009.result(Severity.FAIL, msg, {"missing": missing})
    return SITEMAP_009.result(Severity.PASS, f"All {total} important pages found in sitemap")


def _find_news_sitemap(config: SiteConfig | None, page_url: str) -> tuple[str, str, list[str]]:
    """(news sitemap URL, body, candidates checked); URL is '' when none is found."""
    candidates = news_sitemap_candidates(config, page_url)
    for candidate in candidates:
        resp = fetch(candidate)
        if resp.status_code == 200 and NEWS_NS in resp.body:
            return candidate, resp.body, candidates
    return "", "", candidates


def check_news_sitemap(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    """SITEMAP-010: Google News sitemap present (needed for Google News inclusion)."""
    url, body, candidates = _find_news_sitemap(config, response.final_url)
    if not url:
        msg = "No Google News sitemap found (only relevant for news publishers)"
        return SITEMAP_010.result(Severity.WARN, msg, {"checked_urls": candidates})
    root = parse_xml(body)
    count = len(url_entries(root)) if root is not None else 0
    msg = f"News sitemap found: {url} ({count} URLs)"
    return SITEMAP_010.result(Severity.PASS, msg, {"url": url, "urls": count})


def _html_feeds(page: ParsedPage) -> list[dict[str, str]]:
    return [
        {"url": attr(link, "href"), "type": attr(link, "type").lower(), "source": "html_link"}
        for link in tags(page.soup, "link", rel="alternate")
        if "rss" in attr(link, "type").lower() or "atom" in attr(link, "type").lower()
    ]


def _probed_feeds(page_url: str, known: set[str]) -> list[dict[str, str]]:
    found = []
    for path in FEED_PATHS:
        candidate = f"{site_base(page_url)}/{path}"
        if candidate in known:
            continue
        resp = fetch(candidate)
        head = resp.body[:500].lower() if resp.status_code == 200 else ""
        if "<rss" in head or "<feed" in head:
            found.append({"url": candidate, "type": "detected", "source": "url_probe"})
    return found


def check_rss_feed(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    """SITEMAP-011: RSS/Atom feeds for content distribution."""
    feeds = _html_feeds(page)
    feeds += _probed_feeds(response.final_url, {f["url"] for f in feeds})
    robots = fetch(robots_url_for(config, response.final_url))
    for url in robots_sitemap_directives(robots):
        if any(x in url.lower() for x in ("/feed", "/rss", ".rss", "atom")):
            feeds.append({"url": url, "type": "rss/atom", "source": "robots.txt"})
    if not feeds:
        return SITEMAP_011.result(Severity.WARN, "No RSS/Atom feed found")
    listed = ", ".join(f"{f['url']} ({f['source']})" for f in feeds[:3])
    return SITEMAP_011.result(Severity.PASS, f"{len(feeds)} feed(s): {listed}", {"feeds": feeds})


def check_sitemap_in_robots(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    """SITEMAP-012: The sitemap URL is declared in robots.txt."""
    robots = fetch(robots_url_for(config, response.final_url))
    if robots.status_code != 200:
        return SITEMAP_012.result(Severity.WARN, "No robots.txt - cannot verify sitemap declaration")
    directives = robots_sitemap_directives(robots)
    expected = sitemap_url_for(config, response.final_url)
    if not directives:
        msg = f"robots.txt has NO Sitemap directive - add 'Sitemap: {expected}'"
        return SITEMAP_012.result(Severity.FAIL, msg, {"expected": expected})
    if any(d.rstrip("/").lower() == expected.rstrip("/").lower() for d in directives):
        msg = f"Sitemap declared in robots.txt: {expected}"
        return SITEMAP_012.result(Severity.PASS, msg, {"directives": directives})
    msg = "robots.txt declares other sitemap(s), not the expected one"
    return SITEMAP_012.result(Severity.WARN, msg, {"expected": expected, "found": directives})


def check_sitemap_completeness(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    """SITEMAP-013: Internal links on this page that are missing from the sitemap."""
    listed = {u.rstrip("/") for u in crawl_sitemaps(sitemap_url_for(config, response.final_url)).urls}
    if not listed:
        return SITEMAP_013.result(Severity.INFO, "No sitemap URLs to compare")
    domain = urlparse(response.final_url).netloc
    linked = {
        link["href"].split("?")[0].split("#")[0].rstrip("/")
        for link in get_links(page)["internal"]
        if urlparse(link["href"]).netloc == domain
    }
    missing = sorted(linked - listed)
    if not missing:
        msg = f"All {len(linked)} unique internal links found in sitemap"
        return SITEMAP_013.result(Severity.PASS, msg)
    msg = f"{len(missing)}/{len(linked)} linked pages NOT in sitemap"
    return SITEMAP_013.result(Severity.WARN, msg, {"missing": missing[:15]})


def _segment_counts(child_locs: list[str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for loc in child_locs:
        name = loc.rsplit("/", 1)[-1].lower()
        counts[next((label for label in SEGMENT_LABELS if label in name), "other")] += 1
    return counts


def check_sitemap_segmentation(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    """SITEMAP-014: Sitemaps segmented by content type (news, products, categories...)."""
    root = fetch_sitemap_root(sitemap_url_for(config, response.final_url))
    if root is None:
        return SITEMAP_014.result(Severity.INFO, "No parseable sitemap")
    children = child_sitemap_locs(root)
    if not children:
        count = len(url_entries(root))
        sev = Severity.WARN if count > 1000 else Severity.INFO
        return SITEMAP_014.result(sev, f"Single flat sitemap with {count} URLs")
    segments = _segment_counts(children)
    listed = ", ".join(f"{k}({v})" for k, v in segments.items())
    details: dict[str, object] = {"types": dict(segments), "child_count": len(children)}
    if len(segments) >= 2:
        return SITEMAP_014.result(Severity.PASS, f"{len(children)} child sitemaps: {listed}", details)
    return SITEMAP_014.result(Severity.INFO, f"{len(children)} child sitemaps - name them by type", details)


def _news_issues(body: str) -> list[str]:
    root = parse_xml(body)
    if root is None:
        return ["XML parse error"]
    entries = url_entries(root)
    if not entries:
        return ["No <url> entries"]
    ns = {"n": NEWS_NS}
    required = ("publication", "publication_date", "title")
    return [f"Missing <news:{tag}>" for tag in required if entries[0].find(f".//n:{tag}", ns) is None]


def check_news_sitemap_valid(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    """SITEMAP-015: Google News sitemap has publication, publication_date and title."""
    url, body, _ = _find_news_sitemap(config, response.final_url)
    if not url:
        return SITEMAP_015.result(Severity.INFO, "No Google News sitemap - skipped")
    issues = _news_issues(body)
    if issues:
        msg = f"News sitemap {url} has issues: {', '.join(issues)}"
        return SITEMAP_015.result(Severity.FAIL, msg, {"issues": issues})
    return SITEMAP_015.result(Severity.PASS, f"News sitemap {url} has valid structure")


checks = {
    "SITEMAP-001": check_sitemap_exists,
    "SITEMAP-002": check_sitemap_valid_xml,
    "SITEMAP-003": check_sitemap_url_count,
    "SITEMAP-004": check_sitemap_has_lastmod,
    "SITEMAP-005": check_page_in_sitemap,
    "SITEMAP-006": check_noindex_not_in_sitemap,
    "SITEMAP-007": check_sitemap_total_urls,
    "SITEMAP-008": check_sitemap_gsc_crosscheck,
    "SITEMAP-009": check_important_pages_in_sitemap,
    "SITEMAP-010": check_news_sitemap,
    "SITEMAP-011": check_rss_feed,
    "SITEMAP-012": check_sitemap_in_robots,
    "SITEMAP-013": check_sitemap_completeness,
    "SITEMAP-014": check_sitemap_segmentation,
    "SITEMAP-015": check_news_sitemap_valid,
}

if __name__ == "__main__":
    run_tool(C, checks, "Sitemap / distribution checks")
