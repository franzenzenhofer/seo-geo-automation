"""Tool discovery and execution for the audit orchestrator."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from shared.settings import PROJECT_ROOT
from shared.types import CategoryResult, CheckResult, Severity

TOOL_TIMEOUT_S = 300
TOOLS_DIR = PROJECT_ROOT / "tools"


def discover_tools() -> dict[str, Path]:
    """Map category name (e.g. HEAD) to its tools/check_*.py module."""
    return {f.stem.removeprefix("check_").upper(): f for f in sorted(TOOLS_DIR.glob("check_*.py"))}


def _error_result(category: str, name: str, message: str) -> CategoryResult:
    check = CheckResult(f"{category}-ERR", f"{category} {name}", category, Severity.ERROR, message)
    return CategoryResult(category=category, checks=[check])


def _tool_command(tool_path: Path, url: str, config_path: str | None, output_dir: Path) -> list[str]:
    cmd = [sys.executable, "-m", f"tools.{tool_path.stem}", "--url", url]
    cmd += ["--output", str(output_dir.resolve())]
    if config_path:
        cmd += ["--config", str(Path(config_path).resolve())]
    return cmd


def run_single_tool(tool_path: Path, url: str, config_path: str | None, output_dir: Path) -> CategoryResult:
    """Run one tool as a subprocess (isolates crashes and timeouts) and parse its JSON."""
    category = tool_path.stem.removeprefix("check_").upper()
    print(f"  [{category}] Running {tool_path.name}...", flush=True)
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    start = time.monotonic()
    try:
        result = subprocess.run(
            _tool_command(tool_path, url, config_path, output_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TOOL_TIMEOUT_S,
            cwd=PROJECT_ROOT,
            env=env,
        )
    except subprocess.TimeoutExpired:
        print(f"  [{category}] TIMEOUT after {TOOL_TIMEOUT_S}s")
        return _error_result(category, "Timeout", f"Tool timed out after {TOOL_TIMEOUT_S}s")
    elapsed = time.monotonic() - start
    if result.returncode != 0:
        stderr = result.stderr.strip()[-300:]
        print(f"  [{category}] FAILED ({elapsed:.1f}s): {stderr}")
        return _error_result(category, "Error", f"Tool error: {stderr}")
    return parse_tool_output(output_dir / f"{category.lower()}.json", category, elapsed)


def parse_tool_output(json_path: Path, category: str, elapsed: float) -> CategoryResult:
    """Parse a tool's JSON output into a CategoryResult."""
    if not json_path.exists():
        return _error_result(category, "Error", f"Tool wrote no output file {json_path.name}")
    data = json.loads(json_path.read_text(encoding="utf-8"))
    checks = [CheckResult.from_dict(c) for c in data.get("checks", [])]
    cat = CategoryResult(category=category, checks=checks)
    print(
        f"  [{category}] {len(checks)} checks: {cat.pass_count} PASS, "
        f"{cat.warn_count} WARN, {cat.fail_count} FAIL ({elapsed:.1f}s)"
    )
    return cat
