"""Shared fixtures. Every test talks to real public pages; nothing is mocked."""

from __future__ import annotations

import pytest

from shared.html_parser import ParsedPage, parse_html
from shared.http_client import HttpResponse, fetch

LOREM_URL = "https://loremipsum.franzai.com/"
LOREM_ARTICLE = "https://loremipsum.franzai.com/lorem-ipsum-history/"
EXAMPLE_URL = "https://example.com/"


@pytest.fixture(scope="session")
def lorem_response() -> HttpResponse:
    resp = fetch(LOREM_URL)
    assert resp.status_code == 200, resp.error
    return resp


@pytest.fixture(scope="session")
def lorem_page(lorem_response: HttpResponse) -> ParsedPage:
    return parse_html(lorem_response.body, lorem_response.final_url)


@pytest.fixture(scope="session")
def article_response() -> HttpResponse:
    resp = fetch(LOREM_ARTICLE)
    assert resp.status_code == 200, resp.error
    return resp
