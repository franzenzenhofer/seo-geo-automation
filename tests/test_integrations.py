"""Optional integrations (OpenRouter, PSI, GSC) skip cleanly without credentials and work with them."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from shared.ai import build_prompt, compress_report
from shared.gsc_client import GscUnavailable, gsc_context, sitemap_summary
from shared.llm import LlmError, complete, llm_status
from shared.psi import run_psi
from shared.types import CategoryResult, CheckResult, FullReport, Severity, SiteConfig
from tests.conftest import LOREM_URL

LIVE_KEY = os.environ.get("OPENROUTER_API_KEY", "")


def sample_report() -> FullReport:
    checks = [
        CheckResult("HEAD-001", "title_present", "HEAD", Severity.PASS, "Title found"),
        CheckResult("HEAD-005", "meta_description_length", "HEAD", Severity.WARN, "Length 20"),
    ]
    return FullReport(
        "example.com", "https://example.com/", "2026-01-01T00:00:00", [CategoryResult("HEAD", checks)]
    )


def test_llm_without_key_reports_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("SEO_AUDIT_NO_AI", "0")
    assert "OPENROUTER_API_KEY" in llm_status()
    with pytest.raises(LlmError):
        complete("hello")


def test_no_ai_flag_disables_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "set-but-unused")
    monkeypatch.setenv("SEO_AUDIT_NO_AI", "1")
    assert "no-ai" in llm_status()


def test_compressed_report_keeps_only_issues() -> None:
    text = compress_report(sample_report().to_dict())
    assert "HEAD-005" in text and "HEAD-001" not in text
    assert "HEAD-005" in build_prompt(sample_report())


@pytest.mark.skipif(not LIVE_KEY, reason="OPENROUTER_API_KEY not set")
def test_openrouter_live_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEO_AUDIT_NO_AI", "0")
    prompt = "Name one HTML element that holds a page title. Answer in one short sentence."
    answer = complete(prompt, max_tokens=400)
    assert len(answer.split()) >= 1


def test_psi_without_key_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PSI_API_KEY", raising=False)
    result = run_psi(LOREM_URL, "mobile")
    assert result.skipped and "PSI_API_KEY" in result.error


def test_gsc_not_configured_is_info(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GSC_CREDENTIALS", raising=False)
    ctx = gsc_context(SiteConfig(domain="example.com", start_url="https://example.com/", gsc_property="x"))
    assert isinstance(ctx, GscUnavailable) and ctx.severity is Severity.INFO


def test_gsc_missing_credentials_file_is_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GSC_CREDENTIALS", str(tmp_path / "nope.json"))
    config = SiteConfig(
        domain="example.com", start_url="https://example.com/", gsc_property="sc-domain:example.com"
    )
    ctx = gsc_context(config)
    assert isinstance(ctx, GscUnavailable) and ctx.severity is Severity.ERROR


GSC_PROPERTY = os.environ.get("GSC_TEST_PROPERTY", "")


@pytest.mark.skipif(
    not (GSC_PROPERTY and os.environ.get("GSC_CREDENTIALS")),
    reason="GSC_CREDENTIALS / GSC_TEST_PROPERTY not set",
)
def test_gsc_live_sitemap_summary() -> None:
    config = SiteConfig(domain="example.com", start_url="https://example.com/", gsc_property=GSC_PROPERTY)
    ctx = gsc_context(config)
    assert not isinstance(ctx, GscUnavailable), ctx
    summary = sitemap_summary(ctx)
    assert "error" not in summary, summary
    assert summary["submitted"] >= 0
