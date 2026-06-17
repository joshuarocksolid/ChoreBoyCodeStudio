"""Environment flags used when the editor runs under the pytest AppRun harness."""

from __future__ import annotations

import os


def background_runtime_disabled() -> bool:
    """Return True when tests should not auto-start plugin host or REPL subprocesses."""
    return os.environ.get("CBCS_DISABLE_BACKGROUND_RUNTIME") == "1"
