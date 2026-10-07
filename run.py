"""Audit orchestrator: runs every tools/check_*.py module and writes JSON + HTML reports.

Usage:
    python run.py --url https://example.com/ --no-ai
    python run.py --config configs/example.config.json
    python run.py --url https://example.com/ --tools HEAD,HTTP,BODY --no-ai
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from shared.ai import run_ai_synthesis
from shared.config import ConfigError, load_config
from shared.console import ensure_utf8_stdio
from shared.llm import llm_status
from shared.output import get_output_dir, save_full_report
from shared.report import generate_aggregate_report, generate_html_report
from shared.run_tool import discover_tools, run_single_tool
from shared.settings import ENV_CACHE_DIR, ENV_NO_AI, ENV_OPENROUTER_KEY, ENV_USER_AGENT
from shared.types import FullReport, MultiPageReport, PageConfig, PageResult, SiteConfig

USER_AGENT_CHOICES = ["mobile", "desktop", "googlebot-mobile", "googlebot-desktop"]
RULE = "=" * 60


def url_to_slug(url: str) -> str:
    """Derive a page slug from a URL path."""
    path = urlparse(url).path.strip("/")
    return path.replace("/", "-") if path else "homepage"


def bare_domain(url_or_host: str) -> str:
    host = urlparse(url_or_host).hostname if "://" in url_or_host else url_or_host
    return (host or "unknown").removeprefix("www.")


@dataclass(frozen=True)
class AuditJob:
    """What to run: selected tools, optional config path, and whether AI synthesis is on."""

    tools: dict[str, Path]
    config_path: str | None
    use_ai: bool


def audit_single_page(url: str, job: AuditJob, output_dir: Path) -> FullReport:
    """Run all tools against one URL, save JSON + HTML, return the report."""
    print(f"\n{RULE}\nAUDITING: {url}\nTools: {len(job.tools)} | Output: {output_dir}\n{RULE}\n")
    os.environ[ENV_CACHE_DIR] = str((output_dir / ".cache").resolve())
    start = time.monotonic()
    categories = [run_single_tool(path, url, job.config_path, output_dir) for path in job.tools.values()]
    report = FullReport(
        domain=bare_domain(url), url=url, timestamp=datetime.now().isoformat(), categories=categories
    )
    save_full_report(report, output_dir)
    ai_summary = run_ai_synthesis(report, output_dir) if job.use_ai else None
    html_path = generate_html_report(report, output_dir, ai_summary)
    print(
        f"\n  Done in {time.monotonic() - start:.1f}s: {report.total_pass} PASS, "
        f"{report.total_warn} WARN, {report.total_fail} FAIL\n  HTML: {html_path}"
    )
    return report


def select_tools(all_tools: dict[str, Path], filter_str: str | None) -> dict[str, Path]:
    """Filter tools by comma-separated names; unknown names abort the run."""
    if not filter_str:
        return all_tools
    selected = [t.strip().upper() for t in filter_str.split(",") if t.strip()]
    missing = sorted(set(selected) - set(all_tools))
    if missing:
        sys.exit(f"Unknown tools: {missing}. Available: {sorted(all_tools)}")
    return {k: v for k, v in all_tools.items() if k in selected}


def pages_to_audit(url: str | None, config: SiteConfig | None) -> list[PageConfig]:
    if url:
        return [PageConfig(url=url)]
    if config and config.important_pages:
        return config.important_pages
    if config:
        return [PageConfig(url=config.start_url)]
    sys.exit("Provide --url, --config, or both")


def run_multi_page(pages: list[PageConfig], job: AuditJob, base_dir: Path) -> None:
    results: list[PageResult] = []
    for pc in pages:
        slug = url_to_slug(pc.url)
        page_dir = base_dir / slug
        page_dir.mkdir(parents=True, exist_ok=True)
        report = audit_single_page(pc.url, job, page_dir)
        results.append(PageResult(url=pc.url, slug=slug, page_type=pc.page_type, report=report))
    multi = MultiPageReport(
        domain=bare_domain(pages[0].url), timestamp=datetime.now().isoformat(), pages=results
    )
    (base_dir / "multi-report.json").write_text(multi.to_json(), encoding="utf-8")
    index = generate_aggregate_report(multi, base_dir)
    print(
        f"\n{RULE}\nMULTI-PAGE AUDIT COMPLETE: {len(results)} pages\n"
        f"  Total: {multi.total_checks} checks | {multi.total_pass} PASS | "
        f"{multi.total_warn} WARN | {multi.total_fail} FAIL\n  Aggregate: {index}\n{RULE}\n"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SEO/GEO audit orchestrator")
    parser.add_argument("--url", help="Single URL to audit (overrides important_pages)")
    parser.add_argument("--config", help="Path to a site config JSON")
    parser.add_argument("--tools", help="Comma-separated tool names, e.g. HEAD,HTTP,BODY")
    parser.add_argument("--no-ai", action="store_true", help="Skip all AI features (no key needed)")
    parser.add_argument("--output-base", default="output", help="Base output directory")
    parser.add_argument("--ua", default="mobile", choices=USER_AGENT_CHOICES, help="User-Agent")
    return parser.parse_args()


def configure_environment(args: argparse.Namespace) -> None:
    """Pass run-wide settings to the tool subprocesses via environment variables."""
    os.environ[ENV_USER_AGENT] = args.ua
    os.environ[ENV_NO_AI] = "1" if args.no_ai else "0"
    if not args.no_ai and llm_status():
        sys.exit(f"AI synthesis needs {ENV_OPENROUTER_KEY}. Set it, or run with --no-ai.")


def main() -> None:
    ensure_utf8_stdio()
    args = parse_args()
    configure_environment(args)
    try:
        config = load_config(args.config) if args.config else None
    except ConfigError as exc:
        sys.exit(str(exc))
    job = AuditJob(select_tools(discover_tools(), args.tools), args.config, not args.no_ai)
    pages = pages_to_audit(args.url, config)
    domain = bare_domain(config.domain if config else pages[0].url)
    base_dir = get_output_dir(domain, args.output_base)
    if len(pages) > 1:
        run_multi_page(pages, job, base_dir)
        return
    audit_single_page(pages[0].url, job, base_dir)


if __name__ == "__main__":
    main()
