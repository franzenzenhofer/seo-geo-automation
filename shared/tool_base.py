"""Standard CLI runner shared by every tools/check_*.py module.

Run a tool on its own from the repository root:
    python -m tools.check_head --url https://example.com/
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

from shared.config import load_config
from shared.console import ensure_utf8_stdio
from shared.html_parser import ParsedPage, parse_html
from shared.http_client import HttpResponse, fetch
from shared.types import CategoryResult, CheckResult, SiteConfig

CheckFn = Callable[[ParsedPage, HttpResponse, SiteConfig | None], CheckResult]


def parse_tool_args(description: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--url", required=True, help="URL to check")
    parser.add_argument("--config", help="Path to site config JSON")
    parser.add_argument("--check", help="Run a single check by ID")
    parser.add_argument("--output", help="Output directory for results")
    return parser.parse_args()


def write_category(result: CategoryResult, output: str | None) -> None:
    """Write <category>.json into the output dir, or print the JSON to stdout."""
    text = json.dumps(result.to_dict(), indent=2, ensure_ascii=False)
    if not output:
        print(text)
        return
    out_path = Path(output) / f"{result.category.lower()}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    print(f"Results written to {out_path}")


def select_checks(checks: Mapping[str, CheckFn], check_id: str | None) -> list[CheckFn]:
    if not check_id:
        return list(checks.values())
    if check_id not in checks:
        sys.exit(f"Unknown check: {check_id}. Available: {list(checks)}")
    return [checks[check_id]]


def run_tool(category: str, checks: Mapping[str, CheckFn], description: str = "") -> None:
    """Fetch the page once, run every check (or --check), write the category JSON."""
    ensure_utf8_stdio()
    args = parse_tool_args(description or f"SEO {category} checks")
    config = load_config(args.config) if args.config else None
    response = fetch(args.url)
    if response.error:
        sys.exit(f"Failed to fetch {args.url}: {response.error}")
    page = parse_html(response.body, response.final_url)
    results = [fn(page, response, config) for fn in select_checks(checks, args.check)]
    write_category(CategoryResult(category=category, checks=results), args.output)
