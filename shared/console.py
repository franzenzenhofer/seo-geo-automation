"""Console helpers that keep output identical on macOS, Linux and Windows."""

from __future__ import annotations

import sys


def ensure_utf8_stdio() -> None:
    """Force UTF-8 on stdout/stderr so non-ASCII output never crashes a Windows console."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
