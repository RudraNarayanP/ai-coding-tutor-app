"""Make CLI output printable on a Windows console.

Windows' default cp1252 stdout cannot encode the ✓/✗/→ marks these audit
scripts print, so `python -m backend.validate_curriculum` used to raise
UnicodeEncodeError *after* a passing audit and exit non-zero on healthy data.
The failure looked like a curriculum bug and cost time to diagnose.

Call :func:`configure` at the top of any CLI entry point that prints status
marks. It is a no-op when stdout is already UTF-8 or has been replaced by a
test harness.
"""
from __future__ import annotations

import sys


def configure(streams=None) -> None:
    for stream in (streams if streams is not None else (sys.stdout, sys.stderr)):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):  # pragma: no cover - closed/redirected stream
            pass
