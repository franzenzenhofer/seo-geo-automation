"""robots.txt checks: presence, size, sitemap directives, Googlebot access, blocked assets.

Spec: https://developers.google.com/search/docs/crawling-indexing/robots/robots_txt
"""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlparse

from shared.html_parser import ParsedPage
from shared.http_client import HttpResponse, fetch
from shared.sitemap_xml import robots_sitemap_directives, robots_url_for
from shared.tool_base import run_tool
from shared.types import Check, CheckResult, Severity, SiteConfig

C = "ROBOTS"
MAX_ROBOTS_BYTES = 512_000
GOOGLE_AGENTS = ("googlebot", "googlebot-mobile")
ASSET_EXTENSIONS = (".js", ".css", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".woff")
ASSET_DIRS = ("/wp-content/", "/static/", "/assets/", "/js/", "/css/", "/images/", "/media/")
FEED_MARKERS = (".rss", "/rss", "/feed", "atom")
NO_ROBOTS = "No robots.txt"

EXISTS = Check("ROBOTS-001", "robots.txt Exists", C)
SIZE = Check("ROBOTS-002", "robots.txt Size", C)
SITEMAP_REF = Check("ROBOTS-003", "Sitemap Reference", C)
GOOGLEBOT = Check("ROBOTS-004", "Googlebot Allowed", C)
COMPLEXITY = Check("ROBOTS-005", "robots.txt Complexity", C)
ALL_SITEMAPS = Check("ROBOTS-006", "All Sitemap Directives", C)
ASSETS = Check("ROBOTS-007", "Assets Not Blocked", C)


@lru_cache(maxsize=2)
def _fetch_robots(url: str) -> HttpResponse:
    return fetch(url)


def robots_for(config: SiteConfig | None, response: HttpResponse) -> HttpResponse:
    return _fetch_robots(robots_url_for(config, response.final_url))


def disallow_rules(body: str, agents: tuple[str, ...]) -> list[str]:
    """Disallow paths in groups addressed to any of `agents` (simplified group parsing)."""
    rules: list[str] = []
    in_group = False
    for raw in body.lower().splitlines():
        line = raw.split("#", 1)[0].strip()
        if line.startswith("user-agent:"):
            in_group = line.split(":", 1)[1].strip() in agents
        elif line.startswith("disallow:") and in_group:
            path = line.split(":", 1)[1].strip()
            if path:
                rules.append(path)
    return rules


def check_robots_exists(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    robots = robots_for(config, response)
    if robots.status_code == 200:
        return EXISTS.result(Severity.PASS, "robots.txt found", {"size": len(robots.body)})
    return EXISTS.result(Severity.WARN, f"robots.txt returned {robots.status_code}")


def check_robots_size(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    robots = robots_for(config, response)
    if robots.status_code != 200:
        return SIZE.result(Severity.INFO, NO_ROBOTS)
    size = len(robots.body.encode("utf-8"))
    sev = Severity.PASS if size < MAX_ROBOTS_BYTES else Severity.WARN
    return SIZE.result(sev, f"Size: {size} bytes (Google reads the first {MAX_ROBOTS_BYTES:,})")


def check_robots_sitemap_ref(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    robots = robots_for(config, response)
    if robots.status_code != 200:
        return SITEMAP_REF.result(Severity.INFO, NO_ROBOTS)
    if robots_sitemap_directives(robots):
        return SITEMAP_REF.result(Severity.PASS, "robots.txt contains a Sitemap directive")
    return SITEMAP_REF.result(Severity.WARN, "No Sitemap directive in robots.txt")


def check_robots_allows_googlebot(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    """ROBOTS-004: No Disallow rule for Googlebot or * matches this page's path (prefix match)."""
    robots = robots_for(config, response)
    if robots.status_code != 200:
        return GOOGLEBOT.result(Severity.PASS, "No robots.txt - all allowed")
    path = urlparse(response.final_url).path or "/"
    blocking = [r for r in disallow_rules(robots.body, (*GOOGLE_AGENTS, "*")) if path.startswith(r)]
    if blocking:
        return GOOGLEBOT.result(Severity.FAIL, f"Googlebot may be blocked from {path}", {"rules": blocking})
    return GOOGLEBOT.result(Severity.PASS, "Page URL is allowed for Googlebot")


def check_robots_complexity(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    robots = robots_for(config, response)
    if robots.status_code != 200:
        return COMPLEXITY.result(Severity.INFO, NO_ROBOTS)
    lines = [ln.strip().lower() for ln in robots.body.splitlines()]
    counts = {
        "disallow_count": sum(1 for ln in lines if ln.startswith("disallow:")),
        "allow_count": sum(1 for ln in lines if ln.startswith("allow:")),
        "total_lines": len(lines),
    }
    msg = f"Disallow: {counts['disallow_count']}, Allow: {counts['allow_count']}, lines: {len(lines)}"
    return COMPLEXITY.result(Severity.INFO, msg, dict(counts))


def check_robots_all_sitemaps(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    """ROBOTS-006: All Sitemap directives, split into regular, news and RSS/Atom."""
    robots = robots_for(config, response)
    if robots.status_code != 200:
        return ALL_SITEMAPS.result(Severity.INFO, NO_ROBOTS)
    urls = robots_sitemap_directives(robots)
    if not urls:
        tip = {"recommendation": "Add: Sitemap: https://<your-domain>/sitemap.xml"}
        return ALL_SITEMAPS.result(Severity.FAIL, "NO Sitemap directives in robots.txt", tip)
    news = [u for u in urls if "news" in u.lower()]
    feeds = [u for u in urls if any(m in u.lower() for m in FEED_MARKERS)]
    regular = [u for u in urls if u not in news and u not in feeds]
    details = {"regular_sitemaps": regular, "news_sitemaps": news, "rss_feeds": feeds, "all": urls}
    msg = f"{len(urls)} Sitemap directive(s): {len(regular)} regular, {len(news)} news, {len(feeds)} RSS/Atom"
    return ALL_SITEMAPS.result(Severity.PASS, msg, dict(details))


def check_assets_not_blocked(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    """ROBOTS-007: JS/CSS/images must not be blocked; Googlebot needs them to render."""
    robots = robots_for(config, response)
    if robots.status_code != 200:
        return ASSETS.result(Severity.PASS, "No robots.txt - all assets accessible")
    blocked = [
        rule
        for rule in disallow_rules(robots.body, ("*", "googlebot"))
        if rule.endswith(ASSET_EXTENSIONS) or any(d in rule for d in ASSET_DIRS)
    ]
    if not blocked:
        return ASSETS.result(Severity.PASS, "No asset directories/extensions blocked for Googlebot")
    msg = f"{len(blocked)} asset path(s) blocked - Googlebot may not render the page"
    return ASSETS.result(Severity.FAIL, msg, {"blocked": blocked[:10]})


checks = {
    "ROBOTS-001": check_robots_exists,
    "ROBOTS-002": check_robots_size,
    "ROBOTS-003": check_robots_sitemap_ref,
    "ROBOTS-004": check_robots_allows_googlebot,
    "ROBOTS-005": check_robots_complexity,
    "ROBOTS-006": check_robots_all_sitemaps,
    "ROBOTS-007": check_assets_not_blocked,
}

if __name__ == "__main__":
    run_tool(C, checks, "robots.txt checks")
