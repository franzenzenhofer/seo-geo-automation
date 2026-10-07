from __future__ import annotations

from shared.http_client import UA_DESKTOP, HeaderDict, fetch, fetch_head
from tests.conftest import EXAMPLE_URL, LOREM_URL


def test_header_dict_is_case_insensitive() -> None:
    headers = HeaderDict({"Strict-Transport-Security": "max-age=1", "x-robots-tag": "noindex"})
    assert headers.get("strict-transport-security") == "max-age=1"
    assert "X-Robots-Tag" in headers
    assert headers["X-ROBOTS-TAG"] == "noindex"
    assert headers.get("missing") == ""


def test_fetch_real_page_returns_body_and_timing() -> None:
    resp = fetch(EXAMPLE_URL, user_agent=UA_DESKTOP)
    assert resp.status_code == 200
    assert "<title>" in resp.body.lower()
    assert resp.response_time_ms > 0
    assert resp.headers.get("content-type").startswith("text/html")


def test_fetch_records_http_to_https_redirect() -> None:
    resp = fetch(LOREM_URL.replace("https://", "http://"))
    assert resp.final_url.startswith("https://")
    assert resp.redirect_chain, "http:// should redirect to https://"


def test_fetch_unresolvable_host_reports_error() -> None:
    resp = fetch("https://nonexistent.invalid/", timeout=5)
    assert resp.status_code == 0
    assert resp.error


def test_fetch_head_404_for_missing_page() -> None:
    assert fetch_head(LOREM_URL + "zz-nonexistent-page-98765").status_code == 404
