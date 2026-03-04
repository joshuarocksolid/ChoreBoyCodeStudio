"""Runtime importability checks for unresolved-import diagnostics."""

from __future__ import annotations

import subprocess
from functools import lru_cache

from app.bootstrap.runtime_module_probe import resolve_probe_runtime_path

RUNTIME_IMPORT_PROBE_TIMEOUT_SECONDS = 5


def is_runtime_module_importable(module_name: str, *, runtime_path: str | None = None) -> bool:
    """Return True when *module_name* imports successfully in the runtime process."""
    top_level = module_name.split(".")[0].strip()
    if not top_level or not top_level.isidentifier():
        return False
    effective_runtime = runtime_path or resolve_probe_runtime_path()
    return _probe_top_level_import(top_level, effective_runtime)


@lru_cache(maxsize=1024)
def _probe_top_level_import(top_level: str, runtime_path: str) -> bool:
    probe_script = (
        "import importlib;"
        f"importlib.import_module({top_level!r})"
    )
    try:
        completed = subprocess.run(
            [runtime_path, "-c", probe_script],
            capture_output=True,
            text=True,
            check=False,
            timeout=RUNTIME_IMPORT_PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def clear_runtime_import_probe_cache() -> None:
    """Clear memoized runtime importability results."""
    _probe_top_level_import.cache_clear()
