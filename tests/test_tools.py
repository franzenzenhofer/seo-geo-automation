"""Tool contract tests plus real runs of every check against a real page."""

from __future__ import annotations

import importlib
from types import ModuleType

import pytest

from shared.html_parser import ParsedPage
from shared.http_client import HttpResponse
from shared.run_tool import discover_tools
from shared.types import CheckResult, Severity

TOOLS = discover_tools()
# Tools that only parse the already-fetched page or make a handful of quick requests.
FAST_TOOLS = ["ANALYTICS", "BODY", "DISCOVER", "DOM", "EXTERNAL_LINKS", "HEAD", "HOMEPAGE", "HREFLANG",
              "IMAGES", "MOBILE", "OG", "SCHEMA", "TARGETING", "VIDEO", "RENDERING", "SPEED", "GSC",
              "SCREENSHOTS", "TRENDS", "ROBOTS", "URL"]  # fmt: skip


def tool_module(category: str) -> ModuleType:
    return importlib.import_module(f"tools.{TOOLS[category].stem}")


def test_discovers_all_tools() -> None:
    assert len(TOOLS) >= 30
    assert "LIVETEST" in TOOLS and "HEAD" in TOOLS


@pytest.mark.parametrize("category", sorted(set(TOOLS) - {"LIVETEST"}))
def test_tool_checks_are_well_formed(category: str) -> None:
    checks = tool_module(category).checks
    assert checks, f"{category} has no checks"
    prefixes = {check_id.rsplit("-", 1)[0] for check_id in checks}
    assert len(prefixes) == 1, f"{category} mixes check id prefixes: {prefixes}"


def test_tool_category_matches_file_name() -> None:
    """run.py reads <category>.json; a tool writing another name loses its results."""
    for category, path in TOOLS.items():
        source = path.read_text(encoding="utf-8")
        assert (
            f'C = "{category}"' in source
            or f'CAT = "{category}"' in source
            or f'run_tool("{category}"' in source
        )


@pytest.mark.parametrize("category", FAST_TOOLS)
def test_every_check_runs_on_real_page(
    category: str, lorem_page: ParsedPage, lorem_response: HttpResponse, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SEO_AUDIT_NO_AI", "1")
    for check_id, fn in tool_module(category).checks.items():
        result = fn(lorem_page, lorem_response, None)
        assert isinstance(result, CheckResult)
        assert result.check_id == check_id
        assert result.severity in Severity
        assert result.severity is not Severity.ERROR, f"{check_id}: {result.message}"
