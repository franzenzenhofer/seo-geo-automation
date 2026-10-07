"""JS-rendering dependency analysis.

Two modes:
1. Heuristic (always): analyses the raw HTML for SPA signals and frameworks.
2. Playwright (optional): renders the page in Chromium and compares with the raw HTML.
   Install: pip install playwright && python -m playwright install chromium
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shared.html_parser import ParsedPage, first_tag, get_body_text, get_links, parse_html, tags
from shared.http_client import HttpResponse

RENDER_TIMEOUT_MS = 30_000
FRAMEWORK_MARKERS = (
    ("Next.js", ("__next", "_next/static")),
    ("Angular", ("ng-app", "ng-version")),
    ("Nuxt/Vue", ("__nuxt",)),
    ("Svelte", ("svelte",)),
    ("Gatsby", ("gatsby",)),
    ("Astro", ("astro",)),
)
_cache: dict[str, RenderComparison] = {}


@dataclass
class RenderComparison:
    url: str
    has_noscript: bool
    noscript_content: str
    js_framework_detected: str
    empty_body: bool
    spa_signals: list[str] = field(default_factory=list)
    playwright_available: bool = False
    js_rendered_word_count: int = 0
    no_js_word_count: int = 0
    word_count_delta: int = 0
    js_rendered_link_count: int = 0
    no_js_link_count: int = 0


def playwright_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        return False
    return True


def render_with_playwright(url: str) -> dict[str, Any]:
    """Render URL in headless Chromium and return word and link counts."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=RENDER_TIMEOUT_MS)
        body_text = str(page.evaluate("document.body ? document.body.innerText : ''"))
        link_count = int(page.evaluate("document.querySelectorAll('a[href^=\"http\"]').length"))
        browser.close()
    return {"word_count": len(body_text.split()), "link_count": link_count}


def detect_framework(html: str) -> str:
    head = html[:5000].lower()
    if 'id="root"' in head and "react" in head:
        return "React"
    for name, markers in FRAMEWORK_MARKERS:
        if any(marker in head or marker in html for marker in markers):
            return name
    return ""


def _spa_signals(page: ParsedPage, words: int, links: int) -> list[str]:
    signals: list[str] = []
    root = first_tag(page.soup, "div", id="root") or first_tag(page.soup, "div", id="app")
    if root is not None and len(root.get_text(strip=True)) < 20:
        signals.append("empty #root/#app div")
    scripts = len(tags(page.body, "script"))
    if scripts > 10:
        signals.append(f"{scripts} scripts in body")
    if words < 10 and links < 3:
        signals.append("very little visible content without JS")
    return signals


def _add_rendered(result: RenderComparison) -> None:
    try:
        rendered = render_with_playwright(result.url)
    except Exception as exc:  # Playwright raises its own error hierarchy plus OS errors
        result.spa_signals.append(f"Playwright render failed: {str(exc)[:80]}")
        return
    result.playwright_available = True
    result.js_rendered_word_count = rendered["word_count"]
    result.js_rendered_link_count = rendered["link_count"]
    result.word_count_delta = rendered["word_count"] - result.no_js_word_count
    if result.no_js_word_count and result.word_count_delta > result.no_js_word_count * 0.5:
        result.spa_signals.append(f"JS adds {result.word_count_delta} words")


def detect_js_rendering(response: HttpResponse) -> RenderComparison:
    """Heuristic analysis, plus a Playwright comparison when installed. Cached per URL."""
    if response.final_url in _cache:
        return _cache[response.final_url]
    page = parse_html(response.body, response.final_url)
    words = len(get_body_text(page).split())
    link_info = get_links(page)
    links = link_info["internal_count"] + link_info["external_count"]
    noscript = tags(page.soup, "noscript")
    framework = detect_framework(response.body)
    result = RenderComparison(
        url=response.final_url,
        has_noscript=bool(noscript),
        noscript_content=" ".join(t.get_text(strip=True) for t in noscript)[:200],
        js_framework_detected=framework,
        empty_body=words < 10,
        spa_signals=_spa_signals(page, words, links),
        no_js_word_count=words,
        no_js_link_count=links,
    )
    if playwright_available():
        _add_rendered(result)
    _cache[response.final_url] = result
    return result
