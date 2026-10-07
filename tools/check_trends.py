"""Search-trend assessment for the configured targeted phrase via an LLM (OpenRouter).

The model answers from its own knowledge, not from live Google Trends data; results are INFO only.
Skipped with INFO when the run uses --no-ai or OPENROUTER_API_KEY is not set.
"""

from __future__ import annotations

from shared.html_parser import ParsedPage
from shared.http_client import HttpResponse
from shared.llm import LlmError, complete, llm_status
from shared.tool_base import run_tool
from shared.types import CheckResult, Severity, SiteConfig

C = "TRENDS"
NO_PHRASE = "No targeted phrase configured for this URL"


def targeted_phrase(config: SiteConfig | None, url: str) -> str:
    return config.phrase_for(url) if config else ""


def _ai_check(cid: str, name: str, phrase: str, prompt: str) -> CheckResult:
    if not phrase:
        return CheckResult(cid, name, C, Severity.INFO, NO_PHRASE)
    reason = llm_status()
    if reason:
        return CheckResult(cid, name, C, Severity.INFO, f"AI check skipped: {reason}")
    try:
        analysis = complete(prompt, max_tokens=600)
    except LlmError as exc:
        return CheckResult(cid, name, C, Severity.WARN, f"AI unavailable: {exc}")
    return CheckResult(
        cid, name, C, Severity.INFO, f"{name} for '{phrase}'", {"phrase": phrase, "analysis": analysis}
    )


def check_trend_analysis(page: ParsedPage, response: HttpResponse, config: SiteConfig | None) -> CheckResult:
    """TREND-001: AI assessment of the search trend for the targeted phrase."""
    phrase = targeted_phrase(config, response.final_url)
    lang = config.language if config else "en"
    prompt = (
        f"Assess the Google search interest for the phrase '{phrase}' (language: {lang}). "
        "Is it growing, stable or declining? Seasonal patterns? Related rising terms? "
        "Is the intent navigational, informational or transactional? "
        "Say clearly where you are uncertain. Reply in under 200 words."
    )
    return _ai_check("TREND-001", "Trend Analysis", phrase, prompt)


def check_trend_competitors(
    page: ParsedPage, response: HttpResponse, config: SiteConfig | None
) -> CheckResult:
    """TREND-002: AI suggests competing search phrases."""
    phrase = targeted_phrase(config, response.final_url)
    brand = f" (brand: {config.brand_name})" if config and config.brand_name else ""
    prompt = (
        f"For the search phrase '{phrase}'{brand}: list the top 5 alternative phrases searchers use. "
        "For each, estimate relative volume (high/medium/low) and commercial vs informational intent. "
        "Reply as a list, under 150 words."
    )
    return _ai_check("TREND-002", "Competing Terms", phrase, prompt)


checks = {"TREND-001": check_trend_analysis, "TREND-002": check_trend_competitors}

if __name__ == "__main__":
    run_tool(C, checks, "Search trend assessment via AI")
