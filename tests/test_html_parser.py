from __future__ import annotations

from shared.html_parser import (
    ParsedPage,
    get_body_text,
    get_canonical,
    get_headings,
    get_links,
    get_title,
    parse_html,
    tags,
    urls_match,
)
from shared.http_client import HttpResponse


def test_title_and_h1_on_real_page(lorem_page: ParsedPage) -> None:
    assert get_title(lorem_page)["count"] == 1
    assert "Lorem Ipsum" in get_title(lorem_page)["text"]
    assert get_headings(lorem_page)["h1_count"] == 1


def test_canonical_is_self_referencing(lorem_page: ParsedPage) -> None:
    canonical = get_canonical(lorem_page)
    assert canonical["href"].startswith("https://loremipsum.franzai.com")
    assert canonical["is_self_referencing"] is True
    assert canonical["in_head"] is True


def test_links_split_internal_external(lorem_page: ParsedPage) -> None:
    links = get_links(lorem_page)
    assert links["internal_count"] > 0
    assert all(link["href"].startswith("http") for link in links["internal"])


def test_body_text_does_not_mutate_the_soup(lorem_response: HttpResponse) -> None:
    page = parse_html(lorem_response.body, lorem_response.final_url)
    scripts_before = len(tags(page.soup, "script"))
    text = get_body_text(page)
    assert len(text.split()) > 100
    assert len(tags(page.soup, "script")) == scripts_before


def test_body_text_skips_scripts_and_styles() -> None:
    page = parse_html(
        "<html><body><p>visible words</p><script>var hidden=1</script><style>p{}</style></body></html>"
    )
    assert get_body_text(page) == "visible words"


def test_urls_match_ignores_trailing_slash() -> None:
    assert urls_match("https://example.com/a/", "https://example.com/a")
    assert not urls_match("https://example.com/a", "https://www.example.com/a")
