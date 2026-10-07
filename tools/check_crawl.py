"""Multi-page crawl checks over the config's important_pages: link graph, inbound links, dead links."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from urllib.parse import urljoin, urlparse

from shared.gsc_client import GscUnavailable, gsc_context, url_inspection
from shared.html_parser import ParsedPage, attr, parse_html, tags
from shared.http_client import HttpResponse, fetch, fetch_head
from shared.tool_base import run_tool
from shared.types import Check, CheckResult, Severity, SiteConfig

C = "CRAWL"
NO_PAGES = "No important_pages in config"
MAX_LINKS_PER_PAGE = 50

CRAWL_001 = Check("CRAWL-001", "All Pages Reachable", C)
CRAWL_002 = Check("CRAWL-002", "Inbound Links", C)
CRAWL_003 = Check("CRAWL-003", "Link Importance", C)
CRAWL_004 = Check("CRAWL-004", "No Dead Weight Links", C)
CRAWL_005 = Check("CRAWL-005", "GSC All Pages Indexed", C)


@dataclass
class Node:
    status: int
    outbound: list[str] = field(default_factory=list)
    inbound: list[str] = field(default_factory=list)


def normalize(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").removeprefix("www.")
    return f"{host}{parsed.path.rstrip('/')}/"


def internal_links(html: str, base_url: str) -> list[str]:
    """Absolute same-host links (www-insensitive), without query or fragment."""
    base_host = (urlparse(base_url).hostname or "").removeprefix("www.")
    links: list[str] = []
    for a in tags(parse_html(html, base_url).soup, "a", href=True):
        parsed = urlparse(urljoin(base_url, attr(a, "href")))
        if (parsed.hostname or "").removeprefix("www.") == base_host:
            links.append(f"{parsed.scheme}://{parsed.hostname}{parsed.path}")
    return links


@lru_cache(maxsize=4)
def link_graph(urls: tuple[str, ...]) -> dict[str, Node]:
    graph: dict[str, Node] = {}
    for url in urls:
        resp = fetch(url)
        graph[url] = Node(resp.status_code, internal_links(resp.body, url) if resp.body else [])
    by_norm = {normalize(u): u for u in graph}
    for src, node in graph.items():
        for link in set(node.outbound):
            target = by_norm.get(normalize(link))
            if target and target != src:
                graph[target].inbound.append(src)
    return graph


def _graph(config: SiteConfig | None) -> dict[str, Node]:
    if not config or not config.important_pages:
        return {}
    return link_graph(tuple(p.url for p in config.important_pages))


def check_all_pages_reachable(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    """CRAWL-001: All important_pages are reachable (HTTP 200)."""
    graph = _graph(config)
    if not graph:
        return CRAWL_001.result(Severity.INFO, NO_PAGES)
    bad = {u: n.status for u, n in graph.items() if n.status != 200}
    if bad:
        msg = f"{len(bad)} pages not reachable"
        return CRAWL_001.result(Severity.FAIL, msg, {"unreachable": bad})
    msg = f"All {len(graph)} important pages return 200"
    return CRAWL_001.result(Severity.PASS, msg)


def check_inbound_links(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    """CRAWL-002: Every important page gets at least one link from another important page."""
    graph = _graph(config)
    if not graph:
        return CRAWL_002.result(Severity.INFO, NO_PAGES)
    orphans = [u for u, n in graph.items() if not n.inbound]
    if orphans:
        msg = f"{len(orphans)} pages have no inbound links from other important pages"
        return CRAWL_002.result(Severity.WARN, msg, {"orphans": orphans})
    return CRAWL_002.result(Severity.PASS, f"All {len(graph)} pages have inbound links")


def check_link_importance(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    """CRAWL-003: The homepage should receive the most inbound links."""
    graph = _graph(config)
    if not graph or not config:
        return CRAWL_003.result(Severity.INFO, NO_PAGES)
    types = {p.url: p.page_type for p in config.important_pages}
    counts = sorted(((len(n.inbound), u) for u, n in graph.items()), reverse=True)
    rank = [{"url": u, "type": types.get(u, "page"), "inbound": n} for n, u in counts]
    home_inbound = [n for n, u in counts if types.get(u) == "homepage"]
    if home_inbound and home_inbound[0] < counts[0][0]:
        msg = "Homepage does not have the most inbound links"
        return CRAWL_003.result(Severity.WARN, msg, {"ranking": rank})
    msg = "Link distribution looks reasonable"
    return CRAWL_003.result(Severity.PASS, msg, {"ranking": rank})


def check_no_links_to_deadweight(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    """CRAWL-004: Important pages should not link to URLs returning 4xx/5xx."""
    graph = _graph(config)
    if not graph:
        return CRAWL_004.result(Severity.INFO, NO_PAGES)
    status: dict[str, int] = {}
    dead: list[dict[str, object]] = []
    for src, node in graph.items():
        for link in list(dict.fromkeys(node.outbound))[:MAX_LINKS_PER_PAGE]:
            if link not in status:
                status[link] = fetch_head(link).status_code
            if status[link] >= 400 or status[link] == 0:
                dead.append({"from": src, "to": link, "status": status[link]})
    if dead:
        msg = f"{len(dead)} links to dead/error pages"
        return CRAWL_004.result(Severity.WARN, msg, {"dead_links": dead[:20]})
    return CRAWL_004.result(Severity.PASS, "No links to dead pages found")


def check_gsc_all_indexed(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    """CRAWL-005: GSC URL Inspection for every important page."""
    if not config or not config.important_pages:
        return CRAWL_005.result(Severity.INFO, NO_PAGES)
    ctx = gsc_context(config)
    if isinstance(ctx, GscUnavailable):
        return CRAWL_005.result(ctx.severity, ctx.reason)
    rows = []
    for p in config.important_pages:
        idx = url_inspection(ctx, p.url).get("indexStatusResult", {})
        crawled = str(idx.get("lastCrawlTime", ""))[:10]
        rows.append({"url": p.url, "verdict": idx.get("verdict", "UNKNOWN"), "lastCrawled": crawled})
    missing = [r["url"] for r in rows if r["verdict"] != "PASS"]
    total = len(rows)
    if missing:
        msg = f"{len(missing)}/{total} pages NOT indexed in Google"
        return CRAWL_005.result(Severity.FAIL, msg, {"not_indexed": missing, "all": rows})
    return CRAWL_005.result(Severity.PASS, f"All {total} pages indexed", {"all": rows})


checks = {
    "CRAWL-001": check_all_pages_reachable,
    "CRAWL-002": check_inbound_links,
    "CRAWL-003": check_link_importance,
    "CRAWL-004": check_no_links_to_deadweight,
    "CRAWL-005": check_gsc_all_indexed,
}

if __name__ == "__main__":
    run_tool(C, checks, "Multi-page crawl checks")
