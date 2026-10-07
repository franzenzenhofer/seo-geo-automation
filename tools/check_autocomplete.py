"""Google Autocomplete checks: keyword discovery around the page's targeted phrase.

Uses the public suggest endpoint (suggestqueries.google.com, unofficial and rate limited).
"""

from __future__ import annotations

import requests
from defusedxml import ElementTree as SafeET

from shared.html_parser import ParsedPage
from shared.http_client import HttpResponse
from shared.tool_base import run_tool
from shared.types import Check, CheckResult, Severity, SiteConfig

C = "AUTOCOMPLETE"
SUGGEST_URL = "https://suggestqueries.google.com/complete/search"
TIMEOUT = 10
LOCAL_COUNTRIES = ("de", "fr", "es", "it", "nl", "pt")
EXPANSION_LETTERS = "abcdefghij"
NO_PHRASE = "No targeted phrase configured for this URL"

SUGGEST = Check("AC-001", "Autocomplete Suggestions", C)
BRAND = Check("AC-002", "Brand in Autocomplete", C)
VARIATIONS = Check("AC-003", "Suggest Variations", C)


def fetch_suggestions(query: str, lang: str) -> list[str]:
    """Autocomplete suggestions for query; empty list when the endpoint fails."""
    country = lang if lang in LOCAL_COUNTRIES else "us"
    params = {"output": "toolbar", "hl": lang, "gl": country, "q": query}
    try:
        resp = requests.get(SUGGEST_URL, params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        root = SafeET.fromstring(resp.text)
    except (requests.RequestException, SafeET.ParseError):
        return []
    return [s.attrib["data"] for s in root.iter("suggestion") if s.attrib.get("data")]


def phrase_and_lang(config: SiteConfig | None, url: str) -> tuple[str, str]:
    if not config:
        return "", "en"
    return config.phrase_for(url), config.language or "en"


def check_suggest_exists(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    """AC-001: The targeted phrase returns autocomplete suggestions."""
    phrase, lang = phrase_and_lang(config, response.final_url)
    if not phrase:
        return SUGGEST.result(Severity.INFO, NO_PHRASE)
    suggestions = fetch_suggestions(phrase, lang)
    if not suggestions:
        return SUGGEST.result(Severity.WARN, f"No suggestions for '{phrase}'", {"query": phrase})
    details = {"query": phrase, "suggestions": suggestions[:10]}
    return SUGGEST.result(Severity.PASS, f"{len(suggestions)} suggestions for '{phrase}'", details)


def check_brand_in_suggest(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    """AC-002: The brand appears in autocomplete for the targeted phrase."""
    phrase, lang = phrase_and_lang(config, response.final_url)
    brand = config.brand_name if config else ""
    if not phrase or not brand:
        return BRAND.result(Severity.INFO, "No targeted phrase or brand configured")
    suggestions = fetch_suggestions(phrase, lang)
    hits = [s for s in suggestions if brand.lower() in s.lower()]
    if hits:
        return BRAND.result(
            Severity.PASS, f"Brand '{brand}' in {len(hits)} suggestions", {"brand_suggestions": hits}
        )
    msg = f"Brand '{brand}' not in autocomplete for '{phrase}'"
    return BRAND.result(Severity.INFO, msg, {"suggestions": suggestions[:10]})


def check_suggest_variations(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    """AC-003: Long-tail variations via alphabet expansion (phrase + a, b, c...)."""
    phrase, lang = phrase_and_lang(config, response.final_url)
    if not phrase:
        return VARIATIONS.result(Severity.INFO, NO_PHRASE)
    found = [s for letter in EXPANSION_LETTERS for s in fetch_suggestions(f"{phrase} {letter}", lang)[:3]]
    unique = list(dict.fromkeys(found))
    msg = f"{len(unique)} long-tail variations discovered"
    return VARIATIONS.result(Severity.INFO, msg, {"variations": unique[:20]})


checks = {
    "AC-001": check_suggest_exists,
    "AC-002": check_brand_in_suggest,
    "AC-003": check_suggest_variations,
}

if __name__ == "__main__":
    run_tool(C, checks, "Google Autocomplete checks")
