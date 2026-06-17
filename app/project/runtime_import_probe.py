"""Runtime importability checks for unresolved-import diagnostics."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from functools import lru_cache

from app.bootstrap.runtime_module_probe import resolve_probe_runtime_path

RUNTIME_IMPORT_PROBE_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class RuntimeImportProbeResult:
    """Outcome of probing one top-level import inside the runtime process."""

    module_name: str
    runtime_path: str
    is_importable: bool
    failure_reason: str = ""
    detail: str = ""


def is_runtime_module_importable(module_name: str, *, runtime_path: str | None = None) -> bool:
    """Return True when *module_name* imports successfully in the runtime process."""
    return probe_runtime_module_importability(module_name, runtime_path=runtime_path).is_importable


def probe_runtime_module_importability(
    module_name: str,
    *,
    runtime_path: str | None = None,
) -> RuntimeImportProbeResult:
    """Return detailed runtime-import probe results for *module_name*."""
    top_level = module_name.split(".")[0].strip()
    effective_runtime = runtime_path or resolve_probe_runtime_path()
    if not top_level or not top_level.isidentifier():
        return RuntimeImportProbeResult(
            module_name=top_level or module_name,
            runtime_path=effective_runtime,
            is_importable=False,
            failure_reason="invalid_module_name",
            detail="Module name must be a valid top-level identifier.",
        )
    is_importable, failure_reason, detail = _probe_top_level_import(top_level, effective_runtime)
    return RuntimeImportProbeResult(
        module_name=top_level,
        runtime_path=effective_runtime,
        is_importable=is_importable,
        failure_reason=failure_reason,
        detail=detail,
    )


@lru_cache(maxsize=1024)
def _probe_top_level_import(top_level: str, runtime_path: str) -> tuple[bool, str, str]:
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
    except subprocess.TimeoutExpired:
        return False, "timeout", (
            f"Import probe timed out after {RUNTIME_IMPORT_PROBE_TIMEOUT_SECONDS} seconds."
        )
    except OSError as exc:
        return False, "runtime_unavailable", str(exc)
    if completed.returncode == 0:
        return True, "", ""
    detail = (completed.stderr or completed.stdout or "").strip()
    return False, "import_error", detail


def clear_runtime_import_probe_cache() -> None:
    """Clear memoized runtime importability results."""
    _probe_top_level_import.cache_clear()
