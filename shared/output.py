"""Output directory management for SEO audit results."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from shared.types import FullReport

FULL_REPORT_FILE = "full-report.json"


def get_output_dir(domain: str, base: str = "output") -> Path:
    """Create and return <base>/<domain>/<timestamp>/."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out = Path(base) / domain / timestamp
    out.mkdir(parents=True, exist_ok=True)
    return out


def save_full_report(report: FullReport, output_dir: Path) -> Path:
    path = output_dir / FULL_REPORT_FILE
    path.write_text(report.to_json(), encoding="utf-8")
    return path
