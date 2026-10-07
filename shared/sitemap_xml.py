"""Sitemap and robots.txt helpers shared by the sitemap, robots and crawl-budget tools.

Sitemap protocol: https://www.sitemaps.org/protocol.html
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from functools import lru_cache
from urllib.parse import urlparse

from defusedxml import ElementTree as SafeET

from shared.http_client import HttpResponse, fetch
from shared.types import SiteConfig

SM_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
NEWS_NS = "http://www.google.com/schemas/sitemap-news/0.9"
NEWS_PATHS = ("sitemap-news.xml", "news-sitemap.xml", "sitemap_news.xml", "googlenews-sitemap.xml")


@dataclass
class SitemapCrawl:
    urls: list[str] = field(default_factory=list)
    sitemap_count: int = 0


def site_base(page_url: str) -> str:
    parsed = urlparse(page_url)
    return f"{parsed.scheme}://{parsed.netloc}"


@lru_cache(maxsize=4)
def fetch_cached(url: str) -> HttpResponse:
    return fetch(url)


def sitemap_url_for(config: SiteConfig | None, page_url: str) -> str:
    """Configured sitemap, else the first non-feed Sitemap: line in robots.txt, else /sitemap.xml."""
    if config and config.sitemap_url:
        return config.sitemap_url
    robots = fetch_cached(robots_url_for(config, page_url))
    declared = [
        u for u in robots_sitemap_directives(robots) if not u.lower().endswith((".rss", "/feed", ".atom"))
    ]
    return declared[0] if declared else f"{site_base(page_url)}/sitemap.xml"


def robots_url_for(config: SiteConfig | None, page_url: str) -> str:
    return config.robots_url if config else f"{site_base(page_url)}/robots.txt"


def parse_xml(body: str) -> ET.Element | None:
    """Parse untrusted XML safely; None when it is not well-formed or uses forbidden constructs."""
    try:
        return SafeET.fromstring(body)
    except (ET.ParseError, ValueError):
        return None


def child_sitemap_locs(root: ET.Element) -> list[str]:
    locs = root.findall(".//sm:sitemap/sm:loc", SM_NS) or root.findall(".//sitemap/loc")
    return [loc.text.strip() for loc in locs if loc.text]


def url_entries(root: ET.Element) -> list[ET.Element]:
    return root.findall(".//sm:url", SM_NS) or root.findall(".//url")


def url_locs(root: ET.Element) -> list[str]:
    locs = root.findall(".//sm:url/sm:loc", SM_NS) or root.findall(".//url/loc")
    return [loc.text.strip() for loc in locs if loc.text]


def fetch_sitemap_root(url: str) -> ET.Element | None:
    resp = fetch(url)
    return parse_xml(resp.body) if resp.status_code == 200 else None


def crawl_sitemaps(sitemap_url: str, max_depth: int = 3, max_urls: int = 0) -> SitemapCrawl:
    """Follow sitemap indexes breadth-first; collect page URLs (max_urls=0 means unlimited)."""
    crawl = SitemapCrawl()
    batch = [sitemap_url]
    for _depth in range(max_depth):
        next_batch: list[str] = []
        for smap_url in batch:
            root = fetch_sitemap_root(smap_url)
            if root is None:
                continue
            crawl.sitemap_count += 1
            next_batch.extend(child_sitemap_locs(root))
            crawl.urls.extend(url_locs(root))
            if max_urls and len(crawl.urls) >= max_urls:
                crawl.urls = crawl.urls[:max_urls]
                return crawl
        batch = next_batch
    return crawl


def robots_sitemap_directives(robots: HttpResponse) -> list[str]:
    """All `Sitemap:` URLs declared in a robots.txt response (empty if not 200)."""
    if robots.status_code != 200:
        return []
    return [
        line.strip().split(":", 1)[1].strip()
        for line in robots.body.splitlines()
        if line.strip().lower().startswith("sitemap:")
    ]


def news_sitemap_candidates(config: SiteConfig | None, page_url: str) -> list[str]:
    """News sitemaps listed in the sitemap index first, then the common file names."""
    base = site_base(page_url)
    candidates = [f"{base}/{name}" for name in NEWS_PATHS]
    root = fetch_sitemap_root(sitemap_url_for(config, page_url))
    if root is not None:
        listed = [loc for loc in child_sitemap_locs(root) if "news" in loc.lower()]
        candidates = listed + candidates
    return list(dict.fromkeys(candidates))
