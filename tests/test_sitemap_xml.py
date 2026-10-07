from __future__ import annotations

from shared.sitemap_xml import crawl_sitemaps, parse_xml, sitemap_url_for
from tests.conftest import LOREM_URL


def test_sitemap_discovered_from_robots_txt() -> None:
    assert sitemap_url_for(None, LOREM_URL) == "https://loremipsum.franzai.com/sitemap-index.xml"


def test_crawl_follows_sitemap_index() -> None:
    crawl = crawl_sitemaps(sitemap_url_for(None, LOREM_URL))
    assert crawl.sitemap_count >= 2
    assert LOREM_URL in crawl.urls


def test_entity_expansion_is_rejected() -> None:
    bomb = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;">]><x>&b;</x>'
    assert parse_xml(bomb) is None
    assert parse_xml("<urlset><url><loc>https://example.com/</loc></url></urlset>") is not None
