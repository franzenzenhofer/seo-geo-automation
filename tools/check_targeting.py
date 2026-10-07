"""Targeting element checks: is the page's targeted phrase in title, H1 and meta description?

Needs a config with targeted_phrases ({url: phrase}); otherwise every check reports INFO.
"""

from __future__ import annotations

import re

from shared.html_parser import ParsedPage, get_headings, get_meta_description, get_title
from shared.http_client import HttpResponse
from shared.tool_base import run_tool
from shared.types import Check, CheckResult, Severity, SiteConfig

C = "TARGETING"
NO_PHRASE = "No targeted phrase configured for this URL"
MIN_WORD_SHARE = 0.5

TARGET_001 = Check("TARGET-001", "Targeted Phrase Configured", C)
TARGET_002 = Check("TARGET-002", "Phrase in Title", C)
TARGET_003 = Check("TARGET-003", "Phrase in H1", C)
TARGET_004 = Check("TARGET-004", "Phrase in Meta Desc", C)
TARGET_005 = Check("TARGET-005", "Brand in Title", C)
TARGET_006 = Check("TARGET-006", "Meta Desc Has Number", C)


def phrase_for(config: SiteConfig | None, url: str) -> str:
    return config.phrase_for(url) if config else ""


def word_share(phrase: str, text: str) -> float:
    """Share of phrase words that occur in text (case-insensitive)."""
    words = phrase.lower().split()
    lowered = text.lower()
    return sum(1 for w in words if w in lowered) / len(words) if words else 0.0


def check_has_targeted_phrase(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    phrase = phrase_for(config, response.final_url)
    if not phrase:
        return TARGET_001.result(Severity.INFO, NO_PHRASE)
    msg = f"Targeted phrase: '{phrase}'"
    return TARGET_001.result(Severity.PASS, msg)


def check_phrase_in_title(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    phrase = phrase_for(config, response.final_url)
    if not phrase:
        return TARGET_002.result(Severity.INFO, NO_PHRASE)
    title = get_title(page)["text"]
    if phrase.lower() in title.lower():
        return TARGET_002.result(Severity.PASS, "Targeted phrase found in title")
    share = word_share(phrase, title)
    if share >= MIN_WORD_SHARE:
        msg = f"Partial match: {share:.0%} of phrase words in title"
        return TARGET_002.result(Severity.WARN, msg)
    return TARGET_002.result(Severity.FAIL, "Targeted phrase NOT in title")


def check_phrase_in_h1(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    phrase = phrase_for(config, response.final_url)
    if not phrase:
        return TARGET_003.result(Severity.INFO, NO_PHRASE)
    h1s = get_headings(page)["h1_texts"]
    if not h1s:
        return TARGET_003.result(Severity.FAIL, "No H1 found")
    if word_share(phrase, h1s[0]) >= MIN_WORD_SHARE:
        return TARGET_003.result(Severity.PASS, "Phrase variation found in H1")
    return TARGET_003.result(Severity.WARN, "Targeted phrase NOT in H1")


def check_phrase_in_meta_desc(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    phrase = phrase_for(config, response.final_url)
    if not phrase:
        return TARGET_004.result(Severity.INFO, NO_PHRASE)
    if word_share(phrase, get_meta_description(page)["content"]) >= MIN_WORD_SHARE:
        msg = "Phrase variation in meta description"
        return TARGET_004.result(Severity.PASS, msg)
    msg = "Targeted phrase NOT in meta description"
    return TARGET_004.result(Severity.WARN, msg)


def check_title_has_brand(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    if not config or not config.brand_name:
        return TARGET_005.result(Severity.INFO, "No brand configured")
    if config.brand_name.lower() in get_title(page)["text"].lower():
        return TARGET_005.result(Severity.PASS, "Brand name found in title")
    return TARGET_005.result(Severity.WARN, "Brand name NOT in title")


def check_meta_desc_has_number(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    if re.search(r"\d+", get_meta_description(page)["content"]):
        msg = "Meta description contains a number (good for CTR)"
        return TARGET_006.result(Severity.PASS, msg)
    msg = "Meta description has no number - consider adding one for CTR"
    return TARGET_006.result(Severity.INFO, msg)


checks = {
    "TARGET-001": check_has_targeted_phrase,
    "TARGET-002": check_phrase_in_title,
    "TARGET-003": check_phrase_in_h1,
    "TARGET-004": check_phrase_in_meta_desc,
    "TARGET-005": check_title_has_brand,
    "TARGET-006": check_meta_desc_has_number,
}

if __name__ == "__main__":
    run_tool(C, checks, "Targeting element checks")
