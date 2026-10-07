"""AI synthesis: turns a finished audit report into a prioritised executive summary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from shared.llm import LlmError, complete
from shared.types import FullReport

MAX_PROMPT_CHARS = 50_000
SYNTHESIS_FILE = "ai-synthesis.md"

SYNTHESIS_INSTRUCTIONS = (
    "You are an SEO and GEO (generative engine optimisation) expert reviewing automated "
    "audit results. Write a concise executive summary in Markdown with:\n"
    "1. Top 3-5 critical findings\n"
    "2. Prioritised action items (critical / high / medium / low), each tied to check IDs\n"
    "3. Overall assessment\n"
    "Only use facts present in the audit data. Do not invent numbers.\n\n"
)


def compress_report(data: dict[str, Any]) -> str:
    """Keep only non-PASS checks so large reports fit the model context."""
    lines = [
        f"SEO Audit: {data.get('domain', '')} | {data.get('url', '')}",
        f"Summary: {json.dumps(data.get('summary', {}))}",
        "",
        "Issues (non-PASS checks only):",
    ]
    for cat in data.get("categories", []):
        issues = [c for c in cat.get("checks", []) if c.get("severity") != "PASS"]
        if issues:
            lines.append(f"\n## {cat['category']}")
            lines.extend(f"  [{c['severity']}] {c['check_id']}: {c['message']}" for c in issues)
    return "\n".join(lines)


def build_prompt(report: FullReport) -> str:
    data = report.to_dict()
    body = json.dumps(data, indent=2, ensure_ascii=False)
    if len(body) > MAX_PROMPT_CHARS:
        body = compress_report(data)
    return SYNTHESIS_INSTRUCTIONS + "Audit results:\n" + body


def run_ai_synthesis(report: FullReport, output_dir: Path) -> str | None:
    """Write ai-synthesis.md and return its text; None (with a printed reason) on failure."""
    print("\n  [AI] Running AI synthesis via OpenRouter...", flush=True)
    try:
        summary = complete(build_prompt(report))
    except LlmError as exc:
        print(f"  [AI] Synthesis failed: {exc}")
        return None
    (output_dir / SYNTHESIS_FILE).write_text(summary, encoding="utf-8")
    print(f"  [AI] Synthesis written to {output_dir / SYNTHESIS_FILE}")
    return summary
