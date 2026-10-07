"""End-to-end: run the orchestrator as a user would, against a real public page."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from shared.settings import PROJECT_ROOT
from tests.conftest import EXAMPLE_URL

SMOKE_TOOLS = "HEAD,HTTP,BODY,SCHEMA,ROBOTS,SITEMAP"


def run_cli(args: list[str], tmp_path: Path) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != "OPENROUTER_API_KEY"}
    cmd = [sys.executable, str(PROJECT_ROOT / "run.py"), *args, "--output-base", str(tmp_path)]
    return subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", timeout=600, cwd=tmp_path, env=env
    )


def test_no_ai_run_writes_json_and_html(tmp_path: Path) -> None:
    proc = run_cli(["--url", EXAMPLE_URL, "--no-ai", "--tools", SMOKE_TOOLS], tmp_path)
    assert proc.returncode == 0, proc.stderr
    report_dir = next((tmp_path / "example.com").iterdir())
    data = json.loads((report_dir / "full-report.json").read_text(encoding="utf-8"))
    categories = {c["category"] for c in data["categories"]}
    assert categories == set(SMOKE_TOOLS.split(","))
    assert all(c["checks"][0]["severity"] != "ERROR" for c in data["categories"])
    html = (report_dir / "report.html").read_text(encoding="utf-8")
    assert "<title>SEO Audit: example.com</title>" in html


def test_ai_without_key_fails_fast(tmp_path: Path) -> None:
    proc = run_cli(["--url", EXAMPLE_URL, "--tools", "HEAD"], tmp_path)
    assert proc.returncode != 0
    assert "OPENROUTER_API_KEY" in proc.stderr


def test_unknown_tool_is_rejected(tmp_path: Path) -> None:
    proc = run_cli(["--url", EXAMPLE_URL, "--no-ai", "--tools", "NOPE"], tmp_path)
    assert proc.returncode != 0
    assert "Unknown tools" in proc.stderr


def test_report_fonts_are_at_least_16px() -> None:
    from shared.report_css import REPORT_CSS

    sizes = [int(s) for s in re.findall(r"font-size:\s*(\d+)px", REPORT_CSS)]
    assert sizes and min(sizes) >= 16
