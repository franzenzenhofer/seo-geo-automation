"""Optional wrapper around the open-source SEO Live Test CLI.

Project: https://github.com/franzenzenhofer/franz-enzenhofer-seo-live-test-v7
Enable it by cloning that repo, running `npm install` in its `v7` folder and setting
LIVETEST_PATH to that `v7` folder. Without LIVETEST_PATH the tool reports INFO and skips.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from shared.config import load_config
from shared.console import ensure_utf8_stdio
from shared.gsc_client import access_token
from shared.settings import ENV_LIVETEST_PATH, optional_path
from shared.tool_base import parse_tool_args, write_category
from shared.types import CategoryResult, CheckResult, Severity, SiteConfig

C = "LIVETEST"
TIMEOUT_SECONDS = 120
SKIP_MESSAGE = f"Live Test skipped: set {ENV_LIVETEST_PATH} to the v7 folder of the Live Test repo"
TYPE_TO_SEVERITY: dict[str, Severity] = {
    "ok": Severity.PASS,
    "warn": Severity.WARN,
    "error": Severity.FAIL,
    "info": Severity.INFO,
    "runtime_error": Severity.ERROR,
}


class LiveTestError(RuntimeError):
    """The Live Test CLI could not be run or returned unusable output."""


def _cli_env(config: SiteConfig | None) -> dict[str, str]:
    env = dict(os.environ)
    token = access_token()
    if token:
        env["GOOGLE_API_ACCESS_TOKEN"] = token
    if config and config.gsc_property:
        env["LIVETEST_VAR_gsc_site_url"] = config.gsc_property
    return env


def run_cli(cli_path: Path, url: str, config: SiteConfig | None) -> list[dict[str, Any]]:
    npm = shutil.which("npm")
    if npm is None:
        raise LiveTestError("npm not found on PATH (Node.js is required for the Live Test)")
    if not cli_path.exists():
        raise LiveTestError(f"{ENV_LIVETEST_PATH} does not exist: {cli_path}")
    try:
        result = subprocess.run(
            [npm, "run", "cli", "--", "url", url, "-f", "json"],
            cwd=cli_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_SECONDS,
            env=_cli_env(config),
        )
    except subprocess.TimeoutExpired as exc:
        raise LiveTestError(f"Live Test CLI timed out after {TIMEOUT_SECONDS}s") from exc
    start = result.stdout.find("[")
    if start == -1:
        raise LiveTestError(f"No JSON array in CLI output. stderr: {result.stderr[:500]}")
    rules: list[dict[str, Any]] = json.loads(result.stdout[start:])
    return rules


def rule_group(rule: dict[str, Any]) -> str:
    """Group name from ruleId (e.g. 'HEAD-001' -> 'HEAD'), else the first label word."""
    rule_id = str(rule.get("ruleId", ""))
    if "-" in rule_id:
        return rule_id.split("-")[0].upper()
    label = str(rule.get("label", "UNKNOWN"))
    return label.split()[0].upper() if label.strip() else "UNKNOWN"


def _group_summary(group: str, rules: list[dict[str, Any]]) -> CheckResult:
    counts = Counter(str(r.get("type", "info")) for r in rules)
    sev = Severity.PASS
    if counts["error"] or counts["runtime_error"]:
        sev = Severity.FAIL
    elif counts["warn"]:
        sev = Severity.WARN
    parts = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
    msg = f"{group}: {parts} ({len(rules)} rules)"
    details = {"counts": dict(counts), "total": len(rules)}
    return CheckResult(f"LT-{group}", f"livetest_{group.lower()}_summary", C, sev, msg, details)


def _rule_result(rule: dict[str, Any]) -> CheckResult | None:
    sev = TYPE_TO_SEVERITY.get(str(rule.get("type", "info")), Severity.INFO)
    if sev not in (Severity.WARN, Severity.FAIL, Severity.ERROR):
        return None
    details: dict[str, Any] = {k: rule[k] for k in ("details", "ruleId", "type") if k in rule}
    message = str(rule.get("message", rule.get("label", "")))
    return CheckResult(
        f"LT-{rule.get('ruleId', 'UNKNOWN')}", str(rule.get("name", "rule")), C, sev, message, details
    )


def build_results(rules: list[dict[str, Any]]) -> list[CheckResult]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rule in rules:
        grouped[rule_group(rule)].append(rule)
    results = [_group_summary(g, rs) for g, rs in sorted(grouped.items())]
    results += [r for r in (_rule_result(rule) for rule in rules) if r is not None]
    return results


def run_livetest(url: str, config: SiteConfig | None) -> CategoryResult:
    cli_path = optional_path(ENV_LIVETEST_PATH)
    if cli_path is None:
        return CategoryResult(C, [CheckResult("LT-000", "cli_available", C, Severity.INFO, SKIP_MESSAGE)])
    try:
        return CategoryResult(C, build_results(run_cli(cli_path, url, config)))
    except (LiveTestError, json.JSONDecodeError) as exc:
        return CategoryResult(C, [CheckResult("LT-000", "cli_error", C, Severity.ERROR, str(exc))])


def main() -> None:
    ensure_utf8_stdio()
    args = parse_tool_args("SEO Live Test wrapper")
    config = load_config(args.config) if args.config else None
    write_category(run_livetest(args.url, config), args.output)


if __name__ == "__main__":
    main()
